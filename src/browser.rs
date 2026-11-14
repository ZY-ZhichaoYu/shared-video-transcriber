use crate::config::{private_dir, Config};
use anyhow::{bail, Context, Result};
use reqwest::blocking::Client;
use serde_json::{json, Value};
use std::{collections::VecDeque, fs, net::TcpStream, process::{Child, Command, Stdio}, thread, time::{Duration, Instant}};
use tungstenite::{stream::MaybeTlsStream, Message, WebSocket};

pub struct Browser {
    chrome: Child,
    helpers: Vec<Child>,
    pub cdp: Cdp,
    portal: Option<crate::portal::Portal>,

    closed: bool,
}

impl Browser {
    pub fn open(config: &Config, gui: bool) -> Result<Self> {
        private_dir(&config.profile())?;
        fs::write(config.profile().join("browser.ini"), include_str!("../config/browser.ini"))?;
        let mut helpers = Helpers(Vec::new());
        let display = std::env::var("DISPLAY").unwrap_or_else(|_| ":99".into());
        if std::env::var("DISPLAY").is_err() {
            helpers.0.push(spawn(Command::new("Xvfb").args([&display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"]))?);
            thread::sleep(Duration::from_secs(1));
        }
        if gui {
            helpers.0.push(spawn(Command::new("x11vnc").args(["-display", &display, "-localhost", "-nopw", "-forever", "-shared", "-rfbport", "5900"]))?);
        }
        let mut command = Command::new(&config.chromium);
        command.env("DISPLAY", display).args([
            "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=9222",
            "--no-first-run", "--no-default-browser-check", "--password-store=basic",
            "--disable-dev-shm-usage", "--window-size=1280,800",
        ]).arg(format!("--user-data-dir={}", config.profile().join("user-data").display())).arg("about:blank");
        let mut chrome = spawn(&mut command)?;
        let connection = connect_page();
        if connection.is_err() { let _ = chrome.kill(); let _ = chrome.wait(); }
        Ok(Self { chrome, helpers: std::mem::take(&mut helpers.0), cdp: connection?, portal: gui.then(crate::portal::Portal::start), closed: false })
    }

    pub fn navigate(&mut self, url: &str) -> Result<()> {
        self.cdp.call("Page.navigate", json!({"url":url}))?;
        Ok(())
    }

    pub fn login_state(&mut self) -> Result<AuthState> {
        let result = self.cdp.call("Runtime.evaluate", json!({
            "expression": "(async()=>{try{const r=await fetch('/aweme/v1/web/user/profile/self/?device_platform=webapp&aid=6383',{credentials:'include',signal:AbortSignal.timeout(8000)});return await r.json()}catch(e){return null}})()",
            "awaitPromise":true,"returnByValue":true
        }))?;
        Ok(auth_state(&result["result"]["value"]))
    }

    pub fn close(&mut self) -> Result<()> {
        // Browser.close flushes all profile databases before the archive is created.
        let _ = self.cdp.socket.send(Message::Text(json!({"id":999999,"method":"Browser.close"}).to_string().into()));
        let deadline = Instant::now() + Duration::from_secs(20);
        while Instant::now() < deadline {
            if let Some(status) = self.chrome.try_wait()? {
                if !status.success() { bail!("Chromium 未正常退出，停止归档"); }
                self.closed = true;
                return Ok(());
            }
            thread::sleep(Duration::from_millis(200));
        }
        bail!("Chromium 关闭超时，停止归档")
    }
}

impl Drop for Browser {
    fn drop(&mut self) {
        self.portal.take();

        if !self.closed { let _ = self.chrome.kill(); let _ = self.chrome.wait(); }
        for child in &mut self.helpers { let _ = child.kill(); let _ = child.wait(); }
    }
}

struct Helpers(Vec<Child>);
impl Drop for Helpers {
    fn drop(&mut self) {
        for child in &mut self.0 { let _ = child.kill(); let _ = child.wait(); }
    }
}

fn spawn(command: &mut Command) -> Result<Child> {
    command.stdout(Stdio::null()).stderr(Stdio::null()).spawn().context("浏览器组件启动失败，请使用项目 Docker 镜像")
}

fn connect_page() -> Result<Cdp> {
    let client = Client::builder().no_proxy().timeout(Duration::from_secs(2)).build()?;
    for _ in 0..60 {
        if let Ok(response) = client.get("http://127.0.0.1:9222/json/list").send() {
            if let Ok(pages) = response.json::<Vec<Value>>() {
                if let Some(url) = pages.iter().filter(|p| p["type"] == "page").find_map(|p| p["webSocketDebuggerUrl"].as_str()) {
                    return Cdp::connect(url);
                }
            }
        }
        thread::sleep(Duration::from_millis(500));
    }
    bail!("Chromium 调试接口未启动；请确认容器支持 Chromium 沙箱")
}

#[derive(Debug, PartialEq, Eq)]
pub enum AuthState { Valid, Expired, Unknown }

pub fn auth_state(value: &Value) -> AuthState {
    if value["status_code"] == 0 && value["user"]["uid"].as_str().is_some_and(|uid| !uid.is_empty() && uid != "0") {
        AuthState::Valid
    } else if value["status_code"].as_i64().is_some_and(|code| code != 0) {
        AuthState::Expired
    } else { AuthState::Unknown }
}

pub struct Cdp {
    socket: WebSocket<MaybeTlsStream<TcpStream>>,
    next_id: u64,
    events: VecDeque<Value>,
}

impl Cdp {
    fn connect(url: &str) -> Result<Self> {
        let (mut socket, _) = tungstenite::connect(url).context("无法连接 Chromium CDP")?;
        if let MaybeTlsStream::Plain(stream) = socket.get_mut() {
            stream.set_read_timeout(Some(Duration::from_secs(2)))?;
            stream.set_write_timeout(Some(Duration::from_secs(5)))?;
        }
        Ok(Self { socket, next_id: 0, events: VecDeque::new() })
    }

    pub fn call(&mut self, method: &str, params: Value) -> Result<Value> {
        self.next_id += 1;
        let id = self.next_id;
        self.socket.send(Message::Text(json!({"id":id,"method":method,"params":params}).to_string().into()))?;
        let deadline = Instant::now() + Duration::from_secs(20);
        while Instant::now() < deadline {
            let Some(message) = self.read()? else { continue; };
            if message["id"] == id {
                if message.get("error").is_some() { bail!("浏览器未能完成 {method}"); }
                return Ok(message["result"].clone());
            }
            if message.get("method").is_some() { self.events.push_back(message); }
        }
        bail!("浏览器操作超时：{method}")
    }

    pub fn event(&mut self) -> Result<Option<Value>> {
        if let Some(event) = self.events.pop_front() { return Ok(Some(event)); }
        self.read()
    }

    fn read(&mut self) -> Result<Option<Value>> {
        match self.socket.read() {
            Ok(Message::Text(message)) => Ok(Some(serde_json::from_str(&message)?)),
            Ok(_) => Ok(None),
            Err(tungstenite::Error::Io(error)) if matches!(error.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => Ok(None),
            Err(_) => bail!("浏览器连接已中断"),
        }
    }
}
