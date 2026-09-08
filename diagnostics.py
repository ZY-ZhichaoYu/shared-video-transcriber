"""Shareable, offline environment checks. Never report credentials, paths or job data."""
import importlib.metadata
import json
import os
import platform
import shutil
import struct
import sys
from pathlib import Path
from version import __version__

PACKAGES=('fastapi','uvicorn','faster-whisper','ctranslate2','av','playwright','yt-dlp','mcp','pillow','python-dotenv')


def collect():
    checks=[]
    def add(name,status,detail,action=''):
        checks.append({'name':name,'status':status,'detail':detail,'action':action})
    supported=(3,10)<=sys.version_info[:2]<(3,15)
    add('Python','ok' if supported else 'error',platform.python_version(),'推荐安装 64 位 Python 3.12，再重新启动。' if not supported else '')
    bits=struct.calcsize('P')*8
    add('位数','ok' if bits==64 else 'error',str(bits)+' bit','请安装 64 位 Python。' if bits!=64 else '')
    versions={}
    for package in PACKAGES:
        try:versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:versions[package]=None
    missing=[p for p,v in versions.items() if v is None]
    add('Python 依赖','error' if missing else 'ok','缺少：'+', '.join(missing) if missing else '所需软件包均已安装',
        '重新运行启动器，让它补齐依赖；仍失败时查看 .setup-logs。' if missing else '')
    ffmpeg=bool(shutil.which('ffmpeg'))
    add('ffmpeg','ok' if ffmpeg else 'warning','已找到视频合并程序' if ffmpeg else '未找到外部 ffmpeg',
        '本地视频和仅转录仍可用；下载 B 站完整视频前请安装 ffmpeg。' if not ffmpeg else '')
    browser=False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:browser=Path(p.chromium.executable_path).is_file()
    except Exception:
        pass
    add('Chromium','ok' if browser else 'warning','网页解析内核已安装' if browser else '网页解析内核未就绪',
        '重新运行启动器安装 Chromium；本地视频不依赖它。' if not browser else '')
    root=Path(os.environ.get('VIDEO_DATA_DIR',str(Path(__file__).resolve().parent/'.data')))
    while not root.exists() and root.parent!=root:root=root.parent
    try:
        free=shutil.disk_usage(root).free/1073741824
        add('磁盘空间','ok' if free>=2 else 'warning',f'可用 {free:.1f} GB','建议至少保留 2 GB，并按视频大小额外预留。' if free<2 else '')
    except OSError:
        add('磁盘空间','warning','无法读取空间信息','检查结果目录是否存在及是否有读写权限。')
    cached=[]
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
        for model in ('tiny','base','small','medium','large-v3'):
            folder=Path(HF_HUB_CACHE)/('models--Systran--faster-whisper-'+model)/'snapshots'
            if any(p.is_file() for p in folder.glob('*/model.bin')):cached.append(model)
    except (ImportError,OSError):
        pass
    add('语音模型缓存','ok' if cached else 'warning',', '.join(cached) if cached else '尚未发现标准 Whisper 模型缓存',
        '首次使用某个识别档位需要联网下载模型；这个过程不是转录卡死。' if not cached else '')
    ai=bool(os.environ.get('VIDEO_AI_BASE_URL') and os.environ.get('VIDEO_AI_MODEL'))
    add('可选 AI 摘要','ok' if ai else 'warning','已配置（连通性未测试）' if ai else '未配置；转录、截图和复制不受影响',
        '需要应用内 AI 摘要时，按 .env.example 创建 .env 并重启。' if not ai else '')
    return {'app_version':__version__,'system':platform.system(),'architecture':platform.machine(),
            'checks':checks,'packages':versions,
            'privacy':'不包含 API key、完整路径、分享链接、转录内容或个人文件名；未联网测试。'}


def main():
    from configuration import load_settings
    load_settings()
    result=collect()
    if '--json' in sys.argv:
        print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        print('视频收件箱 '+result['app_version']+' / 环境检查（离线）')
        for item in result['checks']:
            print(f"[{item['status']}] {item['name']}: {item['detail']}")
            if item['action']:print('  '+item['action'])
        print(result['privacy'])
    return int(any(c['status']=='error' for c in result['checks']))


if __name__=='__main__':
    raise SystemExit(main())
