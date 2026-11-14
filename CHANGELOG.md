# 3.0.0

- 抖音分享链接转文字的核心迁移到 Rust，移除全部 Python 脚本、启动器和依赖。
- Docker 中交互登录，验证后正常关闭 Chromium，将完整 ini 和用户目录认证加密保存到私有 R2。
- Telegram webhook 触发 GitHub Actions，使用 Tailscale 大陆出口与 whisper.cpp，回传 TXT、SRT、JSON。
- 本版本专注抖音转文字，移除旧网页、MCP、其他平台和原任务库入口。原 `.data` 不迁移也不删除。
