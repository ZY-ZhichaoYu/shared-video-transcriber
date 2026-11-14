use crate::{
    config::{required, Config},
    media,
};
use anyhow::{bail, Result};
use reqwest::blocking::{multipart, Client};
use serde_json::{json, Value};
use std::time::Duration;

pub fn job(config: &Config) -> Result<()> {
    let chat = required("TELEGRAM_CHAT_ID")?;
    let allowed = required("TELEGRAM_ALLOWED_USER_IDS")?;
    if !allowed.split(',').any(|id| id.trim() == chat) {
        bail!("这个 Telegram 聊天未获授权");
    }
    let token = required("TELEGRAM_BOT_TOKEN")?;
    let input = required("VIDEO_INPUT")?;
    let client = Client::builder()
        .timeout(Duration::from_secs(120))
        .build()?;
    message(
        &client,
        &token,
        &chat,
        "已开始处理抖音视频，正在获取音轨和转文字。",
    )?;
    let result = media::transcribe(config, &input, false, "zh");
    match result {
        Ok(output) => {
            for filename in ["transcript.txt", "transcript.srt", "result.json"] {
                let form = multipart::Form::new()
                    .text("chat_id", chat.clone())
                    .file("document", output.directory.join(filename))?;
                let value: Value = client
                    .post(format!("https://api.telegram.org/bot{token}/sendDocument"))
                    .multipart(form)
                    .send()
                    .map_err(|_| anyhow::anyhow!("Telegram 文件发送失败"))?
                    .json()
                    .map_err(|_| anyhow::anyhow!("Telegram 文件发送响应异常"))?;
                if value["ok"] != true {
                    bail!("Telegram 拒绝文件；本次文字稿已生成，请查看任务状态");
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
        Err(error) => {
            let _ = message(
                &client,
                &token,
                &chat,
                &format!("转文字失败：{error}。可在 GitHub Actions 查看本次任务。"),
            );
            Err(error)
        }
    }
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
