# 实现依据

本次目标是抖音分享链接转文字，Telegram 收链接，GitHub Actions 执行，Docker 用来初始化登录态。仓库内不保留 Python 脚本。原网页、其他平台和 MCP 入口不再作为本版本接口。

GitHub 检索后比较：

| 项目 | 维护和许可证 | 采用的思路与依赖 | 已知限制 |
|---|---|---|---|
| [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) | 约 5.5 万 stars，2026-11-13 有提交，MIT；[#4155](https://github.com/ggml-org/whisper.cpp/issues/4155) 有讨论并关闭 | 固定 v1.9.5，在远端 Docker 构建 CLI；依赖 C++ 和 ggml，Rust 通过进程调用 | 需要单独下载模型；JSON offsets 为毫秒，转统一结果时只换算一次 |
| [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) | 约 20.8 万 stars，近期提交，Unlicense；[#18042](https://github.com/yt-dlp/yt-dlp/issues/18042) 有讨论并关闭 | 比较过其平台解析和 FFmpeg 组合，没有采用 | 用户明确只做抖音和不保留 Python，避免引入通用下载器 |
| [tailscale/tailscale](https://github.com/tailscale/tailscale) | 约 3.9 万 stars，2026-11-14 UTC 有提交，BSD-3-Clause | 官方 Action 接入临时 Runner 和已有 exit node | 在线不代表有出口权限，必须核对真实 IP 和地区；中国大陆出口可能无法连接 Telegram |
| [C0verSnow/TGMusic](https://github.com/C0verSnow/TGMusic/tree/main/scripts) | 当前组织维护的 MIT 项目 | 借鉴先人工登录、验证、正常停浏览器，再归档完整 ini 和用户目录的顺序；本项目自行用 Rust 实现 | Chrome 版本、Linux 密钥环和设备环境影响恢复；不能只备份 ini 或只看 Cookie |
| [noVNC/noVNC](https://github.com/novnc/noVNC) | 固定 v1.6.0，MPL-2.0 | 使用浏览器内的 VNC 客户端，Rust/axum 转接 x11vnc 字节流 | 只在宿主回环地址开放；不使用 Python websockify |
| [str4d/rage](https://github.com/str4d/rage) | MIT OR Apache-2.0 | 使用 age crate 的 X25519 和流式认证加密，不自行设计密码协议 | 必须读完并验证密文尾部；解密失败不把部分档案切换成正式目录 |

完整 Chrome 用户目录是明确需求，所以选择 Chromium，而不是只持久化 Cookie 和 localStorage 的 Obscura；不引入 DrissionPage，避免 Python 依赖。browser.ini 记录本工具实际使用的相对路径和启动配置；恢复后统一由 Rust 映射到当前数据目录。

Telegram 个人账号的机器人创建与管理使用现有 gotd/cli 会话；业务 webhook 和机器人发送文件使用 Telegram 官方 Bot API。二者不是同一份会话，个人账号会话不会交给 CI 或 Worker。

R2 每次上传唯一版本对象，成功后更新 latest.json。下载、认证解密和完整目录检查通过后才恢复。CI 只读恢复后的账号档案，不在每次转文字后回写账号，避免失败任务污染已验证登录。

真实分享链接验收发现，首次 Tailscale up 还没有节点列表时不能按主机名选择出口。已检索并核对 [Tailscale 官方实现](https://github.com/tailscale/tailscale/blob/0d822c9d3ab06465e95868fe63c6a26fff55e170/ipn/prefs.go)：先用官方 Action 加入网络，再用 tailscale set 选择 armbian；转录入口继续核对实际出口、地区和抖音连通性。使用同一条用户链接复验，远端获取视频、转文字、Telegram 三种文件交付全部通过，见 [真实视频验收 CI](https://github.com/C0verSnow/shared-video-transcriber/actions/runs/43560354503)。
