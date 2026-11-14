use anyhow::{bail, Context, Result};
use clap::{Parser, Subcommand};
use shared_video_transcriber::{
    browser::{AuthState, Browser},
    config::Config,
    media, network,
    profile::{self, Store},
    telegram,
};
use std::{
    fs::{self, File},
    io,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread,
    time::{Duration, Instant},
};

#[derive(Parser)]
#[command(
    version,
    about = "抖音分享链接转文字；Docker 登录，远端 CI 处理，Telegram 收取文字稿"
)]
struct Cli {
    #[command(subcommand)]
    command: Action,
}

#[derive(Subcommand)]
enum Action {
    /// 在容器浏览器登录抖音，确认登录后自动加密上传完整档案
    Login,
    /// 单独重试上传上次已经正常关闭并验证的登录档案
    Upload,
    /// 从 R2 恢复完整登录档案到空数据目录
    Restore,
    /// 抖音分享文字转成 TXT / SRT / JSON
    Transcribe {
        input: String,
        #[arg(long)]
        file: bool,
        #[arg(long, default_value = "zh")]
        language: String,
    },
    /// CI 专用：读取 VIDEO_INPUT 和 TELEGRAM_CHAT_ID，转文字并发送到 Telegram
    TelegramJob,
    /// 下载 whisper.cpp 官方模型（不需要 Python）
    Model {
        #[arg(default_value = "small")]
        size: String,
    },
    /// 生成档案加密密钥；请保存到 Infisical，不要公开
    Keygen,
    /// 检查 Docker 中的 headed Chromium 和 CDP 是否可用
    BrowserCheck,
}

fn main() {
    let _ = dotenvy::dotenv();
    if let Err(error) = execute(Cli::parse()) {
        eprintln!("操作未完成：{error}");
        std::process::exit(1);
    }
}

fn execute(cli: Cli) -> Result<()> {
    if matches!(cli.command, Action::Keygen) {
        use age::secrecy::ExposeSecret;
        println!(
            "{}",
            age::x25519::Identity::generate()
                .to_string()
                .expose_secret()
        );
        return Ok(());
    }
    let config = Config::load()?;
    let _lock = config.lock()?;
    match cli.command {
        Action::Login => login(&config),
        Action::Upload => {
            network::check()?;
            Store::load()?.upload(&config)
        }
        Action::Restore => {
            network::check()?;
            Store::load()?.restore(&config)
        }
        Action::Transcribe {
            input,
            file,
            language,
        } => {
            let output = media::transcribe(&config, &input, file, &language)?;
            println!("{}", output.transcript.text);
            eprintln!("文字稿保存在 {}", output.directory.display());
            Ok(())
        }
        Action::TelegramJob => telegram::job(&config),
        Action::Model { size } => download_model(&config, &size),
        Action::BrowserCheck => {
            let mut browser = Browser::open(&config, false)?;
            browser.navigate("data:text/html,<title>Rust browser check</title>")?;
            let value = browser.cdp.call("Runtime.evaluate", serde_json::json!({"expression":"({title:document.title,headed:!navigator.userAgent.includes('HeadlessChrome')})", "returnByValue":true}))?;
            if value["result"]["value"]["title"] != "Rust browser check"
                || value["result"]["value"]["headed"] != true
            {
                bail!("浏览器检查失败");
            }
            browser.close()?;
            println!("headed Chromium、CDP 和正常关闭检查通过");
            Ok(())
        }
        Action::Keygen => unreachable!(),
    }
}

fn login(config: &Config) -> Result<()> {
    network::check()?;
    let store = Store::load()?;
    store.preflight()?;
    let marker = config.profile().join("login-valid.json");
    if marker.exists() {
        fs::remove_file(&marker)?;
    }
    eprintln!("请打开 http://127.0.0.1:6080/vnc_lite.html，在工具的浏览器里登录抖音。");
    eprintln!("登录确认后，本工具会正常关闭浏览器，将完整 browser.ini 和 user-data 加密上传到你配置的私有 R2。");
    let cancelled = Arc::new(AtomicBool::new(false));
    let signal = cancelled.clone();
    ctrlc::set_handler(move || signal.store(true, Ordering::Relaxed))?;
    let mut browser = Browser::open(config, true)?;
    browser.navigate("https://www.douyin.com/")?;
    let deadline = Instant::now() + config.login_timeout;
    let mut valid = false;
    while Instant::now() < deadline && !cancelled.load(Ordering::Relaxed) {
        match browser.login_state()? {
            AuthState::Valid => {
                valid = true;
                break;
            }
            AuthState::Expired => eprintln!("等待抖音登录"),
            AuthState::Unknown => eprintln!("尚未确认登录，等待页面加载或人工验证"),
        }
        thread::sleep(Duration::from_secs(3));
    }
    browser.close()?;
    if !valid {
        bail!("登录取消、超时或状态未知，未上传档案");
    }
    profile::write_private(&marker, br#"{"state":"VALID"}"#)?;
    store.upload(config)?;
    fs::remove_dir_all(config.profile())?;
    eprintln!("上传完成，本次本地明文档案已清理；下次任务会从 R2 恢复");
    Ok(())
}

fn download_model(config: &Config, size: &str) -> Result<()> {
    if !matches!(size, "tiny" | "base" | "small" | "medium" | "large-v3") {
        bail!("不支持的模型名称");
    }
    let parent = config.model.parent().context("模型路径无效")?;
    fs::create_dir_all(parent)?;
    let mut temporary = tempfile::NamedTempFile::new_in(parent)?;
    let url = format!("https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{size}.bin");
    let mut response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(1800))
        .build()?
        .get(url)
        .send()
        .context("模型下载失败")?
        .error_for_status()
        .context("模型下载失败")?;
    io::copy(&mut response, &mut temporary)?;
    File::open(temporary.path())?.sync_all()?;
    temporary.persist(&config.model).context("模型保存失败")?;
    eprintln!("模型已保存到 {}", config.model.display());
    Ok(())
}
