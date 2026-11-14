use crate::{
    config::{required, Config},
    media,
};
use anyhow::{bail, Context, Result};
use reqwest::blocking::{multipart, Client};
use serde_json::{json, Value};
use std::{fs, path::PathBuf, time::Duration};

pub fn transcribe_job(config: &Config) -> Result<()> {
    let input = required("VIDEO_INPUT")?;
    let directory = PathBuf::from(required("VIDEO_RESULT_DIR")?);
    fs::create_dir_all(&directory)?;
    match media::transcribe(config, &input, false, "zh") {
        Ok(output) => {
            for name in ["transcript.txt", "transcript.srt", "result.json"] {
                fs::copy(output.directory.join(name), directory.join(name))?;
            }
            Ok(())
        }
        Err(error) => {
            fs::write(directory.join("error.txt"), error.to_string())?;
            Err(error)
        }
    }
}

pub fn deliver() -> Result<()> {
    let chat = required("TELEGRAM_CHAT_ID")?;
    let allowed = required("TELEGRAM_ALLOWED_USER_IDS")?;
    if !allowed.split(',').any(|id| id.trim() == chat) {
        bail!("这个 Telegram 聊天未获授权");
    }
    let token = required("TELEGRAM_BOT_TOKEN")?;
    let directory = PathBuf::from(required("VIDEO_RESULT_DIR")?);
    let client = Client::builder()
        .timeout(Duration::from_secs(120))
        .build()?;
    if !directory.join("result.json").is_file() {
        let reason = fs::read_to_string(directory.join("error.txt"))
            .unwrap_or_else(|_| "CI 在获取文字稿前失败，请查看 GitHub Actions".into());
        message(&client, &token, &chat, &format!("转文字未完成：{reason}"))?;
        bail!("没有完成文字稿，已通知 Telegram");
    }
    for filename in ["transcript.txt", "transcript.srt", "result.json"] {
        let form = multipart::Form::new()
            .text("chat_id", chat.clone())
            .file("document", directory.join(filename))
            .context("文字稿文件读取失败")?;
        let value: Value = client
            .post(format!("https://api.telegram.org/bot{token}/sendDocument"))
            .multipart(form)
            .send()
            .map_err(|_| anyhow::anyhow!("Telegram 文件发送失败"))?
            .json()
            .map_err(|_| anyhow::anyhow!("Telegram 文件发送响应异常"))?;
        if value["ok"] != true {
            bail!("Telegram 拒绝文件发送");
        }
    }
    message(
        &client,
        &token,
        &chat,
        "转文字完成，TXT、SRT 和时间戳 JSON 已发送。",
    )?;
    Ok(())
}

pub fn message(client: &Client, token: &str, chat: &str, text: &str) -> Result<()> {
    let value: Value = client
        .post(format!("https://api.telegram.org/bot{token}/sendMessage"))
        .json(&json!({"chat_id":chat,"text":text}))
        .send()
        .map_err(|_| anyhow::anyhow!("Telegram 消息发送失败"))?
        .json()
        .map_err(|_| anyhow::anyhow!("Telegram 消息响应异常"))?;
    if value["ok"] != true {
        bail!("Telegram 拒绝发送消息，请先向机器人发送 /start");
    }
    Ok(())
}
