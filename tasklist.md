# 本文档为4象限的任务清单，全文书写大白话

## 问题及解决模板：上层目录不是目标仓库

- [1794628695] 遇到的问题：工作目录不是 Git 仓库，也没有本次目标仓库；通用解决步骤：先核对目录，再克隆 issue 指向的仓库，在 feature 分支操作，不改旁边项目。

## 问题及解决模板：容器用户名撞上系统组

- [1794630107] 遇到的问题：Debian 已有 video 组，创建同名用户失败；通用解决步骤：使用项目自己的用户名，再通过远端 CI 构建，不占用系统组名。

## 问题及解决模板：密钥工具简写和权限要分别核对

- [1794631282] 遇到的问题：Infisical 的 secrets get 简写不能列目录，读取身份也没有建目录权限；通用解决步骤：固定 CLI 版本并按帮助使用 secrets-manager secrets get，建目录使用已有写入身份，运行任务继续用组织共享读取身份，不打印敏感值。

## 问题及解决模板：Tailscale 标签不能照抄示例

- [1794631282] 遇到的问题：远端接入返回标签无效或未获准；通用解决步骤：核对现有 OAuth 的真实授权标签，再更新应用配置并远端复验，不能把示例 tag:ci 当成现成权限。

## 问题及解决模板：dry-run 也可能触发本地打包

- [1794631282] 遇到的问题：误执行了一次 Wrangler deploy --dry-run，它包含本地 JavaScript 打包，违反本仓库不做本地构建验证的约定；通用解决步骤：验证放远端 CI，无依赖 Worker 上传使用明确跳过构建的 --no-bundle；不要仅凭命令叫 dry-run 就认定是静态检查。已向用户说明，临时产物已从分支移除。

## 问题及解决模板：Compose run 和 up 的参数不同

- [1794632082] 遇到的问题：实际首次登录时，Compose run 拒绝 --no-build；通用解决步骤：按子命令帮助选择参数，登录服务本身不配置 build，再用 --pull never 运行远端镜像；远端 CI 增加实际 Compose 启动入口检查。

## 想做：

- [1794631282] 用户最终目标：Telegram 收抖音分享链接，GitHub Actions 转文字，返回 TXT、SRT 和时间戳 JSON；Docker 只负责人工登录和更新完整登录档案，仓库一个 Python 脚本也不保留。

## 做完：

- [1794631282] 已在 feature/issue-1-rust-docker 实现 Rust 核心、Docker 登录、完整 browser.ini 和 user-data 的 age 认证加密上传恢复；去掉 Python、yt-dlp、其他平台、旧网页和 MCP 入口，不改原数据目录。
- [1794631282] 已提交 PR #2 给用户 review，不自动合并：https://github.com/C0verSnow/shared-video-transcriber/pull/2 。本次在最后一次代码提交前重新按四象限整理记录。
- [1794631282] 已创建 @C0verSnow_DouyinText_bot，并用 gotd/cli 核对个人账号、向 BotFather 创建独立机器人；密钥未写进源码。Worker https://douyin-transcriber-webhook.f1515xcn.workers.dev 已上传，Telegram webhook 注册成功。
- [1794631282] 已创建私有 R2 bucket douyin-transcriber-private；共用 Infisical Project 的 dev 中独立建 /douyin-transcriber 和 /douyin-transcriber/webhook，保存新 age 私钥、机器人、网络配置；组织读取身份对仓库可见，仓库路径 Secret 已配置。本地 .env 为 0600，只保存已有读取身份和应用路径。
- [1794631282] Infisical 官方 Cloudflare Worker Secret Sync 已成功，Worker 只接收四项 webhook 所需密钥；R2 密钥和档案解密密钥没有交给 Worker。
- [1794631282] 远端 Rust 回归、Clippy、五项 webhook 测试、真实 headed Chromium、正常关闭、完整档案加密往返和损坏拒绝、whisper.cpp 样例音频转文字均已通过。通过记录包含 43557024371、43557029546；最新配置检查结果另行补充。
- [1794631282] 已提供 node scripts/login.mjs：从成功的远端 CI 下载镜像并加载，读取 Infisical 后启动登录，不在本地构建。CI 中大陆出口取流和关闭出口后向 Telegram 交付分成两个阶段；正文、会话和视频不上传 Artifacts，也不打印正文。
- [1794631282] 已在 GitHub 检索和比较 whisper.cpp、yt-dlp、Tailscale、抖音实现及官方工具；采用 whisper.cpp 和 Chromium 页面取流，未采用 yt-dlp，名称、链接、许可证和限制见 docs/DESIGN.md。

## 没做：

- [1794631282] 未在本地进行 Rust 或 Docker 编译、构建、业务测试或冒烟；曾误执行一次 Worker 本地 dry-run 打包，已在上方如实记录，不能宣称完全没有本地打包。
- [1794631282] 现有 Cloudflare 授权能部署 Worker、创建 bucket，却不能签发新 bucket 专用的 S3 读写凭证；最初无法配置；现已按用户授权接管浏览器创建并保存，见本次完成记录。没有拿其他应用的 bucket 凭证冒充本应用专用凭证。
- [1794631282] 未替用户完成抖音扫码、短信或验证码；未实测真实抖音账号的登录上传恢复、真实视频转录和 Telegram 文件交付，不能把样例音频测试当作整条业务流程已通过。
- [1794631282] 未合并 PR；新增 workflow 尚未进入默认分支，GitHub 生产 workflow_dispatch 需要 review 合入后启用。首次真实账号验收还在进行，issue 暂不关闭，避免误报完成。

## 在做：

- [1794631282] 正在收尾最新远端网络与线上 webhook 检查、格式检查和 PR 结果说明；R2 凭证已补齐，正在等待首次人工登录。

- [1794632082] 用户明确授权 agent-browser 接管日常 Chrome；用户打开远程调试后，已在登录中的 Cloudflare 创建仅限 douyin-transcriber-private 的 Object Read & Write 账号凭证，写入 Infisical 并回读一致，临时密钥页面快照和明文文件已删除。
- [1794632082] 最新代码提交 bebfbbe 的远端 CI 43557895083 全部成功，包含当前 dev 的有效 Tailscale OAuth、获准标签、实际大陆出口、抖音连通、线上 webhook 和 Telegram 身份检查；旧 prod 网络身份已替换，没有继续使用旧身份。
- [1794632082] 已为用户打开现有 OrbStack，加载功能相同的已通过 CI 镜像并启动 Docker 人工登录。R2 preflight 已通过；浏览器页面已打开，等待用户本人完成登录。这里是用户要求的首次使用操作，没有本地编译。
