"""Standard-library launcher shared by Windows, macOS and Linux."""
import argparse
import contextlib
import hashlib
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
IMPORT_PROBE='import fastapi,uvicorn,faster_whisper,playwright,yt_dlp,mcp,PIL,av,ctranslate2,dotenv'


def requirements_hash(root=ROOT):
    return hashlib.sha256(b'\0'.join((root/name).read_bytes() for name in ('requirements.txt','constraints.txt'))).hexdigest()


@contextlib.contextmanager
def setup_lock(root=ROOT):
    with (root/'.setup.lock').open('a+b') as handle:
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('另一个启动器正在准备环境，请等待那个窗口完成。') from exc
        yield


def run_checked(command,log):
    result=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                            text=True,encoding='utf-8',errors='replace')
    for line in result.stdout:
        print(line,end='',flush=True);log.write(line);log.flush()
    if result.wait()!=0:
        raise RuntimeError('准备环境失败；请查看上面的错误以及本地 .setup-logs 日志，然后重试。')


def main(argv=None):
    args=argparse.ArgumentParser(description='准备并启动视频收件箱')
    args.add_argument('--check',action='store_true',help='只检查环境，不安装或启动')
    args.add_argument('--install-only',action='store_true',help='只准备依赖，不启动服务')
    args.add_argument('--skip-browser',action='store_true',help='跳过 Chromium 安装；只处理本地文件时可用')
    options=args.parse_args(argv)
    if not (3,10)<=sys.version_info[:2]<(3,15) or struct.calcsize('P')!=8:
        raise RuntimeError('需要 64 位 Python 3.10–3.14，推荐 Python 3.12。请从 python.org 安装。')
    os.environ['PYTHONUTF8']='1'
    executable=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if options.check:
        if not executable.is_file():
            print('项目环境尚未安装，请先正常运行启动器。')
            return 1
        return subprocess.call([str(executable),str(ROOT/'diagnostics.py')],cwd=ROOT)
    logs=ROOT/'.setup-logs';logs.mkdir(exist_ok=True)
    with setup_lock(),(logs/f'setup-{time.strftime("%Y%m%d-%H%M%S")}-{os.getpid()}.log').open('x',encoding='utf-8') as log:
        if not executable.is_file():
            print('[1/3] 创建独立 Python 环境……',flush=True)
            run_checked([sys.executable,'-m','venv',str(ROOT/'.venv')],log)
        version_probe=subprocess.run([str(executable),'-c','import sys,struct;sys.exit(0 if (3,10)<=sys.version_info[:2]<(3,15) and struct.calcsize("P")==8 else 1)'],capture_output=True)
        if version_probe.returncode:
            raise RuntimeError('已有 .venv 环境损坏或版本不兼容。请关闭服务，将 .venv 改名备份后再启动；不要删除 .data。')
        marker=ROOT/'.venv/inbox-requirements.sha256'
        wanted=requirements_hash()
        installed=marker.read_text(encoding='utf-8').strip() if marker.exists() else ''
        probe=subprocess.run([str(executable),'-c',IMPORT_PROBE],capture_output=True)
        if installed!=wanted or probe.returncode:
            print('[2/3] 检查并安装依赖；首次需要联网……',flush=True)
            run_checked([str(executable),'-m','pip','--disable-pip-version-check','install','-r',str(ROOT/'requirements.txt')],log)
            run_checked([str(executable),'-c',IMPORT_PROBE],log)
            temporary=marker.with_suffix('.tmp');temporary.write_text(wanted,encoding='utf-8');temporary.replace(marker)
        if not options.skip_browser:
            probe=subprocess.run([str(executable),'-c','from playwright.sync_api import sync_playwright;from pathlib import Path;p=sync_playwright().start();ok=Path(p.chromium.executable_path).is_file();p.stop();raise SystemExit(0 if ok else 1)'],capture_output=True)
            if probe.returncode:
                print('[3/3] 安装网页解析内核 Chromium……',flush=True)
                run_checked([str(executable),'-m','playwright','install','chromium'],log)
        if not shutil_available('ffmpeg'):
            print('提示：未找到 ffmpeg；本地视频和仅转录仍可用。完整 B 站视频合并需要另行安装。')
        print('环境已就绪。首次使用某个识别档位仍需下载语音模型。',flush=True)
    if options.install_only:return 0
    print('正在打开网页；使用期间请保持此窗口运行。',flush=True)
    return subprocess.call([str(executable),str(ROOT/'app.py')],cwd=ROOT)


def shutil_available(name):
    import shutil
    return bool(shutil.which(name))


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,RuntimeError) as exc:
        print('\n启动未完成：'+str(exc),file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
