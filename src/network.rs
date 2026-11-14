use anyhow::{bail, Context, Result};
use reqwest::blocking::Client;
use serde_json::Value;
use std::{env, net::IpAddr, process::Command, time::Duration};

pub fn check() -> Result<()> {
    match env::var("NETWORK_MODE")
        .unwrap_or_else(|_| "direct".into())
        .as_str()
    {
        "direct" => Ok(()),
        "tailscale" => check_tailscale(),
        _ => bail!("NETWORK_MODE 只支持 direct 或 tailscale"),
    }
}

fn check_tailscale() -> Result<()> {
    let expected = crate::config::required("TAILSCALE_EXIT_NODE")?;
    let output = Command::new("tailscale")
        .args(["status", "--json"])
        .output()
        .context("无法读取 Tailscale 状态，请先连接出口节点")?;
    if !output.status.success() {
        bail!("Tailscale 状态读取失败");
    }
    let status: Value = serde_json::from_slice(&output.stdout)?;
    if status["BackendState"] != "Running" || status["ExitNodeStatus"]["Online"] != true {
        bail!("Tailscale 没有选中在线的 exit node，停止任务");
    }
    let selected = &status["ExitNodeStatus"]["ID"];
    if !status["Peer"].as_object().is_some_and(|peers| {
        peers
            .values()
            .any(|peer| peer["ID"] == *selected && peer["HostName"] == expected)
    }) {
        bail!("Tailscale 选中的出口不符合 TAILSCALE_EXIT_NODE，停止任务");
    }
    let client = Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(20))
        .build()?;
    let trace = client
        .get("https://www.cloudflare.com/cdn-cgi/trace")
        .send()
        .context("无法检查实际出口")?
        .error_for_status()?
        .text()?;
    let _address = trace
        .lines()
        .find_map(|line| line.strip_prefix("ip="))
        .context("出口检查没有返回 IP")?
        .parse::<IpAddr>()?;
    if !trace.lines().any(|line| line == "loc=CN") {
        bail!("实际出口不是中国大陆，停止任务");
    }
    client
        .get("https://www.douyin.com/")
        .send()
        .context("当前出口无法访问抖音")?
        .error_for_status()?;
    eprintln!("Tailscale 出口、地区和抖音连通检查通过");
    Ok(())
}
