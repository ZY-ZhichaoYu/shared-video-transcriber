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

## 问题及解决模板：Tailscale 启动时还不能按主机名找出口

- [1794633110] 遇到的问题：真实转录 CI 在 Tailscale up 阶段返回 cannot resolve exit node by hostname while Tailscale is starting up；通用解决步骤：先由官方 Action 加入网络，等节点信息可用后再用 tailscale set 选择出口，随后核对实际出口；不要把主机名出口参数塞进首次 up。之前新 Runner 的恢复检查已通过这套顺序。

## 问题及解决模板：容器模型能用但宿主缓存读不到

- [1794651596] 遇到的问题：本次文字稿成功发送后，actions/cache 因模型文件权限不能保存缓存，后续新 Runner 可能要重新下载模型；通用解决步骤：先区分业务失败和缓存警告，再核对容器写出的文件权限与宿主运行用户。当前未改这项缓存优化，不影响本次已经交付的文字稿。

## 想做：

- [1794651596] 等用户 review PR #2；合入默认分支后，再验收直接给 Telegram 发链接触发生产 workflow_dispatch。本次没有自动合并。

## 做完：

- [1794651596] 用户给的 https://v.douyin.com/4IanPT1B4wI/ 已在远端真实转写成功，代码 d44d0c6，CI 五项任务全部通过：https://github.com/C0verSnow/shared-video-transcriber/actions/runs/43560354503 。同一份生产转录 workflow 通过 workflow_call 在 feature 分支运行，没有另抄转录逻辑。
- [1794651596] 首轮真实测试在加入 Tailscale 时失败；检索官方源码确认启动时节点列表尚未可用，改成先加入网络再选择出口，使用同一条链接复验成功。首次 Docker 扫码登录未强制中国出口，本次 CI 登录态检查和取视频使用已经核对为中国大陆的 armbian 出口，发 Telegram 前退出该出口。
- [1794651596] 已从机器人实际收到并取回 transcript.txt、transcript.srt、result.json；视频标题对应“认知和财富的转化”，TXT 为 4924 字节、1756 个字符（含换行），JSON 有 143 段，最后时间为 263.8 秒，TXT 与 JSON 正文一致。保留原始识别稿，发现“俞敏洪”等人名及部分同音词有错字，没有冒充人工校对稿。
- [1794651596] 本地交付文件保留在忽略目录 .runtime/acceptance，未提交聊天和文字稿；已删除临时仓库变量 DOUYIN_TEST_URL，后续 push 不会重复发送这条测试视频。最终文档提交前重新按四象限整理过程。
- [1794632806] 完成 issue #1 的实现，在 feature/issue-1-rust-docker 提交 PR #2：https://github.com/C0verSnow/shared-video-transcriber/pull/2 。按 issue 要求关闭 issue，不自动合并 PR。本次最终提交前重新按四象限整理记录。
- [1794632806] 用户最终要求是抖音转文字、远端 CI 执行、Telegram 收链接和文字稿；已移除全部 Python 源码、启动器、依赖、yt-dlp、其他平台、旧网页和 MCP 入口，Rust 负责下载转录与档案管理，FFmpeg 和 whisper.cpp 作为镜像内工具。
- [1794632806] Docker 登录功能已实际使用：用户亲自登录抖音，Rust 确认身份有效，正常关闭 Chromium，将完整 browser.ini 和 user-data 认证加密上传私有 R2，然后自动清理本地明文目录。只排除 Singleton 进程锁，不删减缓存、Cookie、Local Storage 或 IndexedDB。
- [1794632806] 已创建独立机器人 @C0verSnow_DouyinText_bot；用 browser-persistent-runner 技能和 gotd/cli 的现有个人会话向 BotFather 创建机器人，个人 Telegram 会话没有交给 CI。Worker https://douyin-transcriber-webhook.f1515xcn.workers.dev 已上传，Telegram webhook 已注册，限定当前用户私聊。
- [1794632806] 已建私有 bucket douyin-transcriber-private，Infisical 共用 Project 的 dev 下独立建 /douyin-transcriber 和 /douyin-transcriber/webhook，保存独立 age 密钥和本应用配置。按用户授权使用 agent-browser 接入已登录 Chrome，创建只允许这个 bucket 的 Object Read & Write 凭证，写入 Infisical 并回读一致；临时页面和明文密钥已删除。
- [1794632806] GitHub 复用组织共享读取身份，仓库 Secret 指向本应用目录。本地 .env 为 0600，只保留已有读取身份和路径，不复制业务密钥。官方 Cloudflare Secret Sync 已成功，Worker 只接收四项 webhook 所需密钥，没有获得 R2 或档案解密密钥。
- [1794632806] 已使用当前 dev 的有效 Tailscale OAuth 和真实获准标签，旧 prod 身份已替换。大陆出口负责抖音取流；该阶段明确结束后，Runner 默认网络负责 Telegram 交付。不会在抖音取流失败时偷偷直连重试。
- [1794632806] 前一轮代码 98e6553 的远端 CI 43559244387 全部通过：https://github.com/C0verSnow/shared-video-transcriber/actions/runs/43559244387 。包含 Rust 回归、格式、Clippy、五项 webhook 测试、真实 Compose 命令、headed Chromium/CDP/正常退出、完整档案加密往返与损坏拒绝、镜像内 whisper.cpp 样例音频转文字、真实大陆出口和线上 webhook 检查，以及新 Runner 下载解密本次真实 R2 档案并成功确认抖音仍已登录。
- [1794632806] 登录脚本从成功的远端 CI 下载镜像，不在本地构建。用户现有 OrbStack 已启动，首次登录使用已通过 CI 的同功能镜像；CI 和本机操作不会把文字稿、会话或视频作为 GitHub Artifacts，也不打印文字稿正文。
- [1794632806] 已在 GitHub 检索和比较 whisper.cpp、yt-dlp、Tailscale、抖音实现和官方工具；采用和排除的理由、许可证、链接和限制见 docs/DESIGN.md。已清理任务中的临时凭证快照，不改其他仓库配置或日常浏览器档案。

## 没做：

- [1794632806] 没有本地 Rust/Docker 编译、构建或业务冒烟；曾误执行一次包含 JavaScript 本地打包的 Wrangler dry-run，已向用户说明并记录问题模板，不能宣称完全没有本地打包。后续 Worker 上传使用 --no-bundle，编译和测试放远端。
- [1794651596] 没有合并 PR；新增转录 workflow 尚未进入默认分支，因此还没验收“发 Telegram 链接自动派发生产任务”这一入口。真实视频从远端获取到文字稿返回 Telegram 已经通过可复用 workflow 实测。
- [1794651596] 本轮没有执行本地编译、构建或业务测试，只读取代码、核对差异、从 Telegram 下载并阅读远端结果。GitHub 已检索 Tailscale 官方源码，确认启动阶段不能按主机名找出口的原因；依据链接已写入 docs/DESIGN.md。
- [1794632806] 不迁移或删除旧 .data；不读取日常浏览器账号作为抖音档案，不代用户输入密码、短信或验证码。

## 在做：

- [1794651596] 本轮真实链接测试已完成，没有继续运行的登录或转写任务；等待用户 review PR。
