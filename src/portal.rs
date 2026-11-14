use axum::{extract::{ws::{Message, WebSocket}, WebSocketUpgrade}, response::Response, routing::get, Router};
use futures_util::{SinkExt, StreamExt};
use std::thread::JoinHandle;
use tokio::{io::{AsyncReadExt, AsyncWriteExt}, net::{TcpListener, TcpStream}, sync::oneshot};
use tower_http::services::ServeDir;

pub struct Portal { stop: Option<oneshot::Sender<()>>, thread: Option<JoinHandle<()>> }

impl Portal {
    pub fn start() -> Self {
        let (stop, receiver) = oneshot::channel();
        let thread = std::thread::spawn(move || {
            let runtime = tokio::runtime::Runtime::new().expect("portal runtime");
            runtime.block_on(async move {
                let app = Router::new().route("/websockify", get(upgrade))
                    .fallback_service(ServeDir::new("/usr/share/novnc"));
                let listener = match TcpListener::bind("0.0.0.0:6080").await {
                    Ok(listener) => listener,
                    Err(_) => { eprintln!("登录网页端口 6080 被占用"); return; }
                };
                let task = tokio::spawn(async move { let _ = axum::serve(listener, app).await; }); let _ = receiver.await; task.abort();
            });
        });
        Self { stop: Some(stop), thread: Some(thread) }
    }
}

impl Drop for Portal {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() { let _ = stop.send(()); }
        if let Some(thread) = self.thread.take() { let _ = thread.join(); }
    }
}

async fn upgrade(ws: WebSocketUpgrade) -> Response { ws.on_upgrade(relay) }

async fn relay(socket: WebSocket) {
    let Ok(stream) = TcpStream::connect("127.0.0.1:5900").await else { return; };
    let (mut reader, mut writer) = stream.into_split();
    let (mut sender, mut receiver) = socket.split();
    let to_vnc = async {
        while let Some(Ok(message)) = receiver.next().await {
            match message {
                Message::Binary(data) => if writer.write_all(&data).await.is_err() { break; },
                Message::Close(_) => break,
                _ => {},
            }
        }
    };
    let to_web = async {
        let mut buffer = vec![0; 65536];
        while let Ok(size) = reader.read(&mut buffer).await {
            if size == 0 || sender.send(Message::Binary(buffer[..size].to_vec().into())).await.is_err() { break; }
        }
    };
    tokio::select! { _ = to_vnc => {}, _ = to_web => {} }
}
