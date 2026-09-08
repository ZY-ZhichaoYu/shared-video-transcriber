"""Read-only references to explicitly selected local media. Sources are never owned."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

EXTENSIONS={'.mp4','.mkv','.mov','.webm','.avi','.m4v','.mp3','.m4a','.wav','.flac','.ogg','.aac'}
_PICKER_LOCK=threading.Lock()


def inspect_media(value):
    path=Path(value.strip().strip('"'))
    if not path.is_absolute() or str(path).startswith(('\\\\','//')):
        raise ValueError('请选择这台电脑上的绝对文件路径，不支持网络共享地址')
    if path.suffix.lower() not in EXTENSIONS:
        raise ValueError('请选择常见视频或音频文件，例如 MP4、MKV、MOV、WAV')
    try:
        path=path.resolve(strict=True)
        if not path.is_file():
            raise ValueError('这个路径不是文件')
        before=path.stat()
        import av
        with av.open(str(path)) as container:
            audio=bool(container.streams.audio)
            video=bool(container.streams.video)
            if not audio and not video:
                raise ValueError('文件没有可读取的音轨或画面')
            duration=float(container.duration or 0)/av.time_base
        after=path.stat()
    except (OSError,RuntimeError) as exc:
        raise ValueError('本地媒体不存在、无法读取或格式损坏，请检查文件') from exc
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('文件仍在变化，请等录制或复制完成后导入')
    return {'path':str(path),'name':path.name,'bytes':after.st_size,'mtime_ns':after.st_mtime_ns,
            'duration':duration,'has_audio':audio,'has_video':video}


def original_path(job):
    source=job.get('local_source')
    if not source:
        return None
    try:
        path=Path(source['path'])
        stat=path.stat()
        if path.is_file() and (stat.st_size,stat.st_mtime_ns)==(source['bytes'],source['mtime_ns']):
            return path
    except OSError:
        pass
    return None


def pick_file():
    # The fixed script has no user-supplied code. Only an explicit UI click invokes it.
    if not _PICKER_LOCK.acquire(blocking=False):
        raise ValueError('文件选择窗口已经打开，请先完成选择')
    script="""import json,tkinter as tk
from tkinter import filedialog
root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
path=filedialog.askopenfilename(title='选择本地视频或音频',filetypes=[('Video / audio','*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.mp3 *.m4a *.wav *.flac *.ogg *.aac')])
root.destroy();print(json.dumps({'path':path},ensure_ascii=True))
"""
    try:
        result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,timeout=180,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
        if result.returncode:
            raise ValueError('无法打开系统选择窗口，请复制文件的完整路径粘贴到输入框')
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('文件选择超时，请重试或直接粘贴完整路径') from exc
    finally:
        _PICKER_LOCK.release()
