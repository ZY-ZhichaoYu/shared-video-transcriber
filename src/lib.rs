pub mod browser;
pub mod config;
pub mod media;
pub mod network;
pub mod profile;
pub mod portal;

pub mod telegram;

use anyhow::{bail, Context, Result};
use std::process::{Command, Stdio};

pub fn run(command: &mut Command, stage: &str) -> Result<()> {
    let status = command.stdout(Stdio::null()).stderr(Stdio::null()).status()
        .with_context(|| format!("无法启动 {stage}，请检查依赖是否安装"))?;
    if !status.success() {
        bail!("{stage}失败（退出码 {:?}），请检查网络、登录状态和配置", status.code());
    }
    Ok(())
}
