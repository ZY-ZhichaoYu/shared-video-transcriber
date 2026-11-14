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

- [1794632890] 用户提供真实抖音链接 https://v.douyin.com/4IanPT1B4wI/，要求在远端 CI 实际转 TXT；首次 Docker 登录没有强制中国出口，之前真实账号恢复检查使用中国出口并通过。本次继续用中国出口测试实际下载、转文字和 Telegram 文件交付。

- [1794632806] 用户 review PR #2；合入默认分支后，Telegram 的生产 workflow_dispatch 才能正式触发转录，再用一条真实分享链接验收文件返回。

## 做完：

- [1794632806] 完成 issue #1 的实现，在 feature/issue-1-rust-docker 提交 PR #2：https://github.com/C0verSnow/shared-video-transcriber/pull/2 。按 issue 要求关闭 issue，不自动合并 PR。本次最终提交前重新按四象限整理记录。
- [1794632806] 用户最终要求是抖音转文字、远端 CI 执行、Telegram 收链接和文字稿；已移除全部 Python 源码、启动器、依赖、yt-dlp、其他平台、旧网页和 MCP 入口，Rust 负责下载转录与档案管理，FFmpeg 和 whisper.cpp 作为镜像内工具。
- [1794632806] Docker 登录功能已实际使用：用户亲自登录抖音，Rust 确认身份有效，正常关闭 Chromium，将完整 browser.ini 和 user-data 认证加密上传私有 R2，然后自动清理本地明文目录。只排除 Singleton 进程锁，不删减缓存、Cookie、Local Storage 或 IndexedDB。
- [1794632806] 已创建独立机器人 @C0verSnow_DouyinText_bot；用 browser-persistent-runner 技能和 gotd/cli 的现有个人会话向 BotFather 创建机器人，个人 Telegram 会话没有交给 CI。Worker https://douyin-transcriber-webhook.f1515xcn.workers.dev 已上传，Telegram webhook 已注册，限定当前用户私聊。
- [1794632806] 已建私有 bucket douyin-transcriber-private，Infisical 共用 Project 的 dev 下独立建 /douyin-transcriber 和 /douyin-transcriber/webhook，保存独立 age 密钥和本应用配置。按用户授权使用 agent-browser 接入已登录 Chrome，创建只允许这个 bucket 的 Object Read & Write 凭证，写入 Infisical 并回读一致；临时页面和明文密钥已删除。
- [1794632806] GitHub 复用组织共享读取身份，仓库 Secret 指向本应用目录。本地 .env 为 0600，只保留已有读取身份和路径，不复制业务密钥。官方 Cloudflare Secret Sync 已成功，Worker 只接收四项 webhook 所需密钥，没有获得 R2 或档案解密密钥。
- [1794632806] 已使用当前 dev 的有效 Tailscale OAuth 和真实获准标签，旧 prod 身份已替换。大陆出口负责抖音取流；该阶段明确结束后，Runner 默认网络负责 Telegram 交付。不会在抖音取流失败时偷偷直连重试。
- [1794632806] 最新代码 98e6553 的远端 CI 43559244387 全部通过：https://github.com/C0verSnow/shared-video-transcriber/actions/runs/43559244387 。包含 Rust 回归、格式、Clippy、五项 webhook 测试、真实 Compose 命令、headed Chromium/CDP/正常退出、完整档案加密往返与损坏拒绝、镜像内 whisper.cpp 样例音频转文字、真实大陆出口和线上 webhook 检查，以及新 Runner 下载解密本次真实 R2 档案并成功确认抖音仍已登录。
- [1794632806] 登录脚本从成功的远端 CI 下载镜像，不在本地构建。用户现有 OrbStack 已启动，首次登录使用已通过 CI 的同功能镜像；CI 和本机操作不会把文字稿、会话或视频作为 GitHub Artifacts，也不打印文字稿正文。
- [1794632806] 已在 GitHub 检索和比较 whisper.cpp、yt-dlp、Tailscale、抖音实现和官方工具；采用和排除的理由、许可证、链接和限制见 docs/DESIGN.md。已清理任务中的临时凭证快照，不改其他仓库配置或日常浏览器档案。

## 没做：

- [1794632806] 没有本地 Rust/Docker 编译、构建或业务冒烟；曾误执行一次包含 JavaScript 本地打包的 Wrangler dry-run，已向用户说明并记录问题模板，不能宣称完全没有本地打包。后续 Worker 上传使用 --no-bundle，编译和测试放远端。
- [1794632806] 没有合并 PR。由于用户要求等 review，新增转录 workflow 还没有进入默认分支，尚未实测 Telegram 生产派发一条真实视频并收到文字稿的整个流程；不把样例语音、真实登录恢复或线上 webhook 检查冒充这项验收。
- [1794632806] 不迁移或删除旧 .data；不读取日常浏览器账号作为抖音档案，不代用户输入密码、短信或验证码。

## 在做：

- [1794632890] 准备把现有转录 workflow 也作为可复用 workflow 从 feature 分支的 CI 调用，既不合并 PR，也不复制一套转录逻辑。

- [1794632806] 实现和本轮检查已收尾，等待用户 review；没有继续运行的登录收集任务。
