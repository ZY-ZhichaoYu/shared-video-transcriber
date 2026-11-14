use anyhow::{bail, Context, Result};
use fs2::FileExt;
use std::{env, fs::{self, File, OpenOptions}, path::{Path, PathBuf}, time::Duration};

#[derive(Clone)]
pub struct Config {
    pub data: PathBuf,
    pub model: PathBuf,
    pub chromium: String,
    pub whisper: String,
    pub login_timeout: Duration,
}

impl Config {
    pub fn load() -> Result<Self> {
        let data = PathBuf::from(env::var("VIDEO_DATA_DIR").unwrap_or_else(|_| ".data/rust".into()));
        fs::create_dir_all(&data)?;
        let data = data.canonicalize()?;
        private_dir(&data)?;
        let login_timeout = env::var("VIDEO_LOGIN_TIMEOUT").unwrap_or_else(|_| "1800".into())
            .parse::<u64>().context("VIDEO_LOGIN_TIMEOUT 必须是秒数")?;
        Ok(Self {
            data,
            model: env::var("WHISPER_MODEL").unwrap_or_else(|_| "/models/ggml-small.bin".into()).into(),
            chromium: env::var("CHROMIUM_BIN").unwrap_or_else(|_| "chromium".into()),
            whisper: env::var("WHISPER_BIN").unwrap_or_else(|_| "whisper-cli".into()),
            login_timeout: Duration::from_secs(login_timeout),
        })
    }

    pub fn profile(&self) -> PathBuf { self.data.join("profile") }

    pub fn lock(&self) -> Result<File> {
        let file = OpenOptions::new().create(true).truncate(false).read(true).write(true)
            .open(self.data.join(".instance.lock"))?;
        file.try_lock_exclusive().context("这个数据目录已有任务运行，请等待结束或使用另一个 VIDEO_DATA_DIR")?;
        Ok(file)
    }
}

pub fn private_dir(path: &Path) -> Result<()> {
    fs::create_dir_all(path)?;
    #[cfg(unix)] {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    }
    Ok(())
}

pub fn required(name: &str) -> Result<String> {
    let value = env::var(name).with_context(|| format!("缺少配置 {name}"))?;
    if value.trim().is_empty() { bail!("配置 {name} 不能为空"); }
    Ok(value)
}
