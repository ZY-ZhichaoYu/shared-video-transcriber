use crate::config::{private_dir, required, Config};
use age::{x25519, Identity, Recipient};
use anyhow::{bail, Context, Result};
use flate2::{read::GzDecoder, write::GzEncoder, Compression};
use reqwest::blocking::{Body, Client};
use rusty_s3::{Bucket, Credentials, S3Action, UrlStyle};
use serde::{Deserialize, Serialize};
use std::{
    fs::{self, File},
    io::{self, BufReader, Write},
    path::Path,
    time::Duration,
};
use tempfile::{NamedTempFile, TempDir};
use uuid::Uuid;

#[derive(Serialize, Deserialize)]
struct Pointer {
    schema: u32,
    object: String,
}

pub struct Store {
    bucket: Bucket,
    credentials: Credentials,
    client: Client,
    prefix: String,
    identity: x25519::Identity,
}

impl Store {
    pub fn load() -> Result<Self> {
        let endpoint: url::Url = required("R2_ENDPOINT")?
            .parse()
            .context("R2_ENDPOINT 不是有效地址")?;
        if endpoint.scheme() != "https" {
            bail!("R2_ENDPOINT 必须使用 HTTPS");
        }
        let identity = parse_identity(&required("PROFILE_ENCRYPTION_KEY")?)?;
        Ok(Self {
            bucket: Bucket::new(endpoint, UrlStyle::Path, required("R2_BUCKET")?, "auto")?,
            credentials: Credentials::new(
                required("R2_ACCESS_KEY_ID")?,
                required("R2_SECRET_ACCESS_KEY")?,
            ),
            client: Client::builder()
                .timeout(Duration::from_secs(600))
                .build()?,
            prefix: std::env::var("R2_PROFILE_PREFIX").unwrap_or_else(|_| "profiles/douyin".into()),
            identity,
        })
    }

    pub fn preflight(&self) -> Result<()> {
        let url = self
            .bucket
            .head_bucket(Some(&self.credentials))
            .sign(Duration::from_secs(60));
        self.client
            .head(url)
            .send()
            .context("R2 连接失败")?
            .error_for_status()
            .context("R2 Bucket 权限检查失败")?;
        Ok(())
    }

    pub fn upload(&self, config: &Config) -> Result<()> {
        if !config.profile().join("login-valid.json").is_file() {
            bail!("没有通过登录验证的完整档案，请先运行 login");
        }
        let encrypted = NamedTempFile::new_in(&config.data)?;
        encrypt_archive(&config.profile(), encrypted.path(), &self.identity)?;
        let object = format!("{}/{}.tar.gz.age", self.prefix, Uuid::new_v4());
        let file = File::open(encrypted.path())?;
        let url = self
            .bucket
            .put_object(Some(&self.credentials), &object)
            .sign(Duration::from_secs(600));
        self.client
            .put(url)
            .header("Content-Length", file.metadata()?.len())
            .body(Body::new(file))
            .send()
            .context("R2 档案上传失败；旧版本保留")?
            .error_for_status()
            .context("R2 拒绝档案上传；旧版本保留")?;
        let pointer = serde_json::to_vec(&Pointer { schema: 1, object })?;
        let key = format!("{}/latest.json", self.prefix);
        let url = self
            .bucket
            .put_object(Some(&self.credentials), &key)
            .sign(Duration::from_secs(60));
        self.client
            .put(url)
            .body(pointer)
            .send()
            .context("R2 最新版本更新失败；旧版本保留")?
            .error_for_status()
            .context("R2 拒绝最新版本更新；旧版本保留")?;
        eprintln!("完整 browser.ini 和 user-data 已加密上传到 R2（旧版本保留）");
        Ok(())
    }

    pub fn restore(&self, config: &Config) -> Result<()> {
        if config.profile().exists() {
            bail!("本地已有档案；请更换空的数据目录，避免覆盖现有登录");
        }
        let key = format!("{}/latest.json", self.prefix);
        let url = self
            .bucket
            .get_object(Some(&self.credentials), &key)
            .sign(Duration::from_secs(60));
        let pointer: Pointer = self
            .client
            .get(url)
            .send()
            .context("R2 版本读取失败")?
            .error_for_status()
            .context("没有可恢复的 R2 档案")?
            .json()?;
        if pointer.schema != 1 || !pointer.object.starts_with(&format!("{}/", self.prefix)) {
            bail!("R2 档案格式或前缀不匹配");
        }
        let url = self
            .bucket
            .get_object(Some(&self.credentials), &pointer.object)
            .sign(Duration::from_secs(600));
        let mut response = self
            .client
            .get(url)
            .send()
            .context("R2 档案下载失败")?
            .error_for_status()?;
        let mut encrypted = NamedTempFile::new_in(&config.data)?;
        io::copy(&mut response, &mut encrypted)?;
        let staging = TempDir::new_in(&config.data)?;
        private_dir(staging.path())?;
        decrypt_archive(encrypted.path(), staging.path(), &self.identity)?;
        if !staging.path().join("browser.ini").is_file()
            || !staging.path().join("user-data").is_dir()
        {
            bail!("档案缺少 browser.ini 或完整用户目录");
        }
        fs::rename(staging.path(), config.profile())?;
        eprintln!("完整档案已恢复；转文字前仍会检查抖音登录是否有效");
        Ok(())
    }
}

pub fn parse_identity(value: &str) -> Result<x25519::Identity> {
    value.parse().map_err(|_| {
        anyhow::anyhow!("PROFILE_ENCRYPTION_KEY 必须是 age X25519 私钥（AGE-SECRET-KEY- 开头）")
    })
}

pub fn encrypt_archive(profile: &Path, output: &Path, identity: &x25519::Identity) -> Result<()> {
    let recipient = identity.to_public();
    let encryptor = age::Encryptor::with_recipients(std::iter::once(&recipient as &dyn Recipient))?;
    let encrypted = encryptor.wrap_output(File::create(output)?)?;
    let compressed = GzEncoder::new(encrypted, Compression::default());
    let mut archive = tar::Builder::new(compressed);
    archive.follow_symlinks(false);
    for entry in walkdir::WalkDir::new(profile).min_depth(1) {
        let entry = entry?;
        if entry.file_name().to_string_lossy().starts_with("Singleton") {
            continue;
        }
        let relative = entry.path().strip_prefix(profile)?;
        archive.append_path_with_name(entry.path(), relative)?;
    }
    archive.into_inner()?.finish()?.finish()?;
    Ok(())
}

pub fn decrypt_archive(
    input: &Path,
    destination: &Path,
    identity: &x25519::Identity,
) -> Result<()> {
    // Authenticate the entire stream before exposing any restored profile, including its tail.
    let decryptor = age::Decryptor::new_buffered(BufReader::new(File::open(input)?))?;
    let mut reader = decryptor.decrypt(std::iter::once(identity as &dyn Identity))?;
    let mut plaintext = tempfile::tempfile()?;
    io::copy(&mut reader, &mut plaintext).context("档案认证解密失败，原登录目录未改动")?;
    use std::io::{Seek, SeekFrom};
    plaintext.seek(SeekFrom::Start(0))?;
    tar::Archive::new(GzDecoder::new(plaintext)).unpack(destination)?;
    Ok(())
}

pub fn write_private(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = File::create(path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        file.set_permissions(fs::Permissions::from_mode(0o600))?;
    }
    file.write_all(bytes)?;
    Ok(())
}
