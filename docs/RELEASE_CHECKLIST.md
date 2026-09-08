# 发布验收

本项目按本机个人应用分发，不对公网服务、多租户隔离或所有平台链接作保证。

发布前运行：

    python -m unittest discover -s tests -v
    python -m pip check
    node --check static/app.js
    node --check static/features.js
    node --check static/local.js
    node --check static/diagnostics.js
    python scripts/package_source.py

打包器只读取 Git 跟踪文件；维护者可用 --include-untracked 预览当前未提交源码。
文件范围检查、私密后缀拒绝、大小上限与 SHA-256 用于防止把本地运行资料混入源码包，
但不能替代人工检查源码是否写入了密钥或用户材料。

额外验证：

- 在新解压目录中运行 bootstrap.py --install-only，再启动服务；不要只测试开发机旧环境。
- 验证最新核心回归及 Windows/Linux/macOS CI 状态，跳过的测试必须注明。
- 用隔离样本验证导入、复制、播放、清理和源文件不变，不能拿用户唯一原件做删除试验。
- 检查 .env、.data、语音模型、日志、会议资料、截图是否排除。
- 发布源码包而非伪装成免安装 EXE；首次仍需 Python、依赖和模型下载。
- 不把模拟 AI 请求测试写成真实付费服务测试；不把单样本转录写成准确率基准。

本地个人分析报告不公开分发。发生无法启动、资料丢失或清理范围异常时停止发布，
保留现场与备份，修复后重跑相关回归。升级和回退步骤见 GETTING_STARTED.md。
