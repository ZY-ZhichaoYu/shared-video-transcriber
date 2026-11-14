use crate::{
    browser::{AuthState, Browser},
    config::{private_dir, Config},
    profile::Store,
    run,
};
use anyhow::{bail, Context, Result};
use base64::Engine;
use regex::Regex;
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::HashSet,
    fs::{self, File},
    io,
    path::{Path, PathBuf},
    process::Command,
    thread,
    time::{Duration, Instant},
};
use url::Url;
use uuid::Uuid;

#[derive(Debug, Serialize, Deserialize)]
pub struct Segment {
    pub start: f64,
    pub end: f64,
    pub text: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Transcript {
    pub source: String,
    pub title: String,
    pub text: String,
    pub language: String,
    pub segments: Vec<Segment>,
}

pub struct Output {
    pub directory: PathBuf,
    pub transcript: Transcript,
}

pub fn transcribe(config: &Config, input: &str, local: bool, language: &str) -> Result<Output> {
    if !matches!(language, "auto" | "zh" | "en" | "ja" | "ko") {
        bail!("不支持的转录语言");
    }
    if !config.model.is_file() {
        bail!("找不到 Whisper 模型，请先设置 WHISPER_MODEL 或下载模型");
    }
    let source = if local {
        fs::canonicalize(input)
            .context("本地音视频文件不存在")?
            .to_string_lossy()
            .into_owned()
    } else {
        extract_url(input)?
    };
    let directory = config.data.join("jobs").join(Uuid::new_v4().to_string());
    private_dir(&directory)?;
    let (media, title) = if local {
        (PathBuf::from(&source), "本地音视频".into())
    } else {
        crate::network::check()?;
        if !config.profile().exists() {
            Store::load()?.restore(config)?;
        }
        eprintln!("检查抖音登录并获取视频");
        download(config, &source, &directory)?
    };
    eprintln!("提取音轨");
    let audio = directory.join("audio.wav");
    run(
        Command::new("ffmpeg")
            .args(["-nostdin", "-v", "error", "-y", "-i"])
            .arg(media)
            .args(["-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le"])
            .arg(&audio),
        "提取音轨",
    )?;
    eprintln!("正在转文字");
    let prefix = directory.join("transcript");
    run(
        Command::new(&config.whisper)
            .arg("-m")
            .arg(&config.model)
            .arg("-f")
            .arg(&audio)
            .args(["-l", language, "-oj", "-osrt", "-otxt", "-of"])
            .arg(&prefix),
        "Whisper 语音识别",
    )?;
    let value: Value = serde_json::from_reader(File::open(directory.join("transcript.json"))?)?;
    let transcript = parse_whisper(&value, &source, &title)?;
    fs::write(
        directory.join("result.json"),
        serde_json::to_vec_pretty(&transcript)?,
    )?;
    // Media are only intermediate inputs; the original local file is never removed.
    fs::remove_file(audio)?;
    let downloaded = directory.join("source.mp4");
    if downloaded.exists() {
        fs::remove_file(downloaded)?;
    }
    Ok(Output {
        directory,
        transcript,
    })
}

pub fn extract_url(text: &str) -> Result<String> {
    let regex = Regex::new(
        r#"(?i)(?:https?://)?(?:(?:www\.|v\.)?douyin\.com|(?:www\.)?iesdouyin\.com)/[^\s<>\"“”\u{4e00}-\u{9fff}]+"#,
    )?;
    let matched = regex
        .find(text)
        .context("请发送抖音视频分享链接")?
        .as_str()
        .trim_end_matches(['。', '，', '！', '？', '；', '）', ')', '】', ']', '》']);
    let value = if matched.to_ascii_lowercase().starts_with("http") {
        matched.to_owned()
    } else {
        format!("https://{matched}")
    };
    let mut parsed = Url::parse(&value)?;
    if !matches!(parsed.scheme(), "http" | "https")
        || !parsed.username().is_empty()
        || parsed.password().is_some()
        || parsed.port().is_some()
        || !matches!(
            parsed.host_str(),
            Some(
                "douyin.com"
                    | "www.douyin.com"
                    | "v.douyin.com"
                    | "iesdouyin.com"
                    | "www.iesdouyin.com"
            )
        )
    {
        bail!("请输入正常的抖音分享链接");
    }
    // A URL embedded in another host must not become a different accepted destination.
    let start = regex.find(text).unwrap().start();
    if start > 0
        && text[..start]
            .chars()
            .next_back()
            .is_some_and(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '/' | '@' | '-' | '_'))
    {
        bail!("请发送独立的抖音分享链接");
    }
    parsed.set_fragment(None);
    Ok(parsed.to_string())
}

pub fn verify_login(browser: &mut Browser) -> Result<()> {
    browser.navigate("https://www.douyin.com/")?;
    for _ in 0..10 {
        thread::sleep(Duration::from_secs(2));
        if browser.login_state()? == AuthState::Valid {
            return Ok(());
        }
    }
    bail!("抖音登录已过期或无法确认，请重新运行 Docker login；旧 R2 备份保留")
}

fn download(config: &Config, source: &str, directory: &Path) -> Result<(PathBuf, String)> {
    let mut browser = Browser::open(config, false)?;
    verify_login(&mut browser)?;
    browser.cdp.call(
        "Network.enable",
        json!({"maxTotalBufferSize": 20000000,"maxResourceBufferSize":10000000}),
    )?;
    browser.navigate(source)?;
    let deadline = Instant::now() + Duration::from_secs(60);
    let mut requests = HashSet::new();
    let mut video = None;
    while Instant::now() < deadline {
        let Some(event) = browser.cdp.event()? else {
            continue;
        };
        let params = &event["params"];
        if event["method"] == "Network.responseReceived"
            && params["response"]["url"]
                .as_str()
                .is_some_and(|url| url.contains("/aweme/v1/web/aweme/detail/"))
        {
            if let Some(id) = params["requestId"].as_str() {
                requests.insert(id.to_owned());
            }
        }
        if event["method"] == "Network.loadingFinished"
            && params["requestId"]
                .as_str()
                .is_some_and(|id| requests.contains(id))
        {
            let response = browser.cdp.call(
                "Network.getResponseBody",
                json!({"requestId":params["requestId"]}),
            )?;
            let body = response["body"].as_str().context("抖音没有返回视频信息")?;
            let data = if response["base64Encoded"] == true {
                base64::engine::general_purpose::STANDARD.decode(body)?
            } else {
                body.as_bytes().to_vec()
            };
            let payload: Value = serde_json::from_slice(&data)?;
            if payload["status_code"] == 0 {
                video = Some(payload["aweme_detail"].clone());
                break;
            }
        }
    }
    if video.is_none() {
        let embedded = browser.cdp.call(
            "Runtime.evaluate",
            json!({"expression":"window._ROUTER_DATA || null", "returnByValue":true}),
        )?;
        video = find_video(&embedded["result"]["value"]);
    }
    let detail =
        video.context("抖音未返回可读取的视频信息，请确认视频可播放，或重新登录完成验证码")?;
    let (url, title) = select_video(&detail)?;
    browser.close()?;
    let client = Client::builder()
        .timeout(Duration::from_secs(300))
        .build()?;
    let mut response = client
        .get(url)
        .header("Referer", "https://www.douyin.com/")
        .header("User-Agent", "Mozilla/5.0")
        .send()
        .context("抖音视频下载失败")?
        .error_for_status()?;
    let maximum: u64 = std::env::var("VIDEO_MAX_DOWNLOAD_MB")
        .unwrap_or_else(|_| "2048".into())
        .parse::<u64>()?
        .checked_mul(1048576)
        .context("下载大小设置过大")?;
    if response.content_length().is_some_and(|size| size > maximum) {
        bail!("视频超过下载大小上限");
    }
    let path = directory.join("source.mp4");
    let mut file = File::create(&path)?;
    use std::io::Read;
    let copied = io::copy(&mut response.by_ref().take(maximum + 1), &mut file)?;
    if copied > maximum {
        fs::remove_file(&path)?;
        bail!("视频超过下载大小上限");
    }
    Ok((path, title))
}

fn find_video(value: &Value) -> Option<Value> {
    if value
        .get("video")
        .is_some_and(|video| video.get("play_addr").is_some())
    {
        return Some(value.clone());
    }
    match value {
        Value::Object(items) => items.values().find_map(find_video),
        Value::Array(items) => items.iter().find_map(find_video),
        _ => None,
    }
}

pub fn select_video(detail: &Value) -> Result<(String, String)> {
    let video = &detail["video"];
    let mut progressive: Vec<_> = video["bit_rate"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|item| item["format"] == "mp4")
        .collect();
    progressive.sort_by_key(|item| item["bit_rate"].as_u64().unwrap_or(0));
    let addresses = progressive
        .first()
        .map(|item| &item["play_addr"]["url_list"])
        .unwrap_or(&video["play_addr"]["url_list"]);
    let url = addresses
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .find(|value| {
            Url::parse(value).ok().is_some_and(|url| {
                matches!(url.scheme(), "http" | "https") && url.host_str().is_some()
            })
        })
        .context("视频没有可下载的音视频地址")?;
    Ok((
        url.to_owned(),
        detail["desc"].as_str().unwrap_or("抖音视频").to_owned(),
    ))
}

#[derive(Deserialize)]
struct WhisperOutput {
    transcription: Vec<WhisperSegment>,
    result: WhisperLanguage,
}
#[derive(Deserialize)]
struct WhisperSegment {
    offsets: Offsets,
    text: String,
}
#[derive(Deserialize)]
struct Offsets {
    from: u64,
    to: u64,
}
#[derive(Deserialize)]
struct WhisperLanguage {
    language: String,
}

pub fn parse_whisper(value: &Value, source: &str, title: &str) -> Result<Transcript> {
    let raw: WhisperOutput =
        serde_json::from_value(value.clone()).context("Whisper 输出格式不兼容")?;
    let segments: Vec<_> = raw
        .transcription
        .into_iter()
        .map(|part| Segment {
            start: part.offsets.from as f64 / 1000.0,
            end: part.offsets.to as f64 / 1000.0,
            text: part.text.trim().to_owned(),
        })
        .filter(|segment| !segment.text.is_empty())
        .collect();
    if segments.is_empty() {
        bail!("没有识别到语音，请确认视频包含可听清的人声");
    }
    let text = segments
        .iter()
        .map(|part| part.text.as_str())
        .collect::<Vec<_>>()
        .join("\n");
    Ok(Transcript {
        source: source.into(),
        title: title.into(),
        text,
        language: raw.result.language,
        segments,
    })
}
