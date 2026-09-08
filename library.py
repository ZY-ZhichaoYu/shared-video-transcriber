"""Persistent local jobs. UI and HTTP/MCP clients share the same task lifecycle."""
import asyncio
import copy
import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import server as media
from recognition import transcribe
from storage import StorageMixin
from handoff import build_handoff, make_storyboard
from audio_utils import prepare_audio
import shutil
from local_media import inspect_media, original_path

TERMINAL = {'done', 'error', 'cancelled', 'interrupted'}
PROFILES = {'fast': 'base', 'balanced': 'small', 'accurate': 'medium'}


class Cancelled(BaseException):
    """Bypasses media-provider fallback handlers to stop further work."""


def stamp(seconds, srt=False):
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}' if srt else f'{hours:02}:{minutes:02}:{seconds:02}'


def sample_frames(path, directory, check, update):
    """Seek through the original; retain timestamps. Sampling is NOT full visual understanding."""
    import av
    result = []
    with av.open(str(path)) as container:
        if not container.streams.video:
            return []
        stream = container.streams.video[0]
        duration = float(container.duration or 0) / av.time_base
        if duration <= 0 and stream.duration:
            duration = float(stream.duration * stream.time_base)
        count = min(24, max(1, math.ceil(duration / 20)))
        for index in range(count):
            check()
            target = duration * index / count
            container.seek(int(target * av.time_base), backward=True)
            for frame in container.decode(video=0):
                actual = float(frame.time or 0)
                if actual + .1 < target:
                    continue
                name = f'frame-{index + 1:02}.jpg'
                picture = frame.to_image()
                picture.thumbnail((960, 720))
                picture.save(directory / name, quality=84)
                result.append({'time': round(actual, 2), 'file': name})
                break
            update((index + 1) / count)
    return result


class Library(StorageMixin):
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.instance_lock = (self.root / '.instance.lock').open('a+b')
        if self.instance_lock.tell() == 0:
            self.instance_lock.write(b'0')
            self.instance_lock.flush()
        self.instance_lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.instance_lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.instance_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.instance_lock.close()
            raise RuntimeError('这个结果目录已有一个视频收件箱在运行，请使用已打开的页面。') from exc
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / 'library.sqlite3', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        self.jobs = {row[0]: json.loads(row[1]) for row in self.db.execute('SELECT id, payload FROM jobs')}
        self.cancel_events = {}
        self.last_saved = {}
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='video-job')
        self.ai_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='video-summary')
        for job in self.jobs.values():
            if job['status'] not in TERMINAL:
                job.update(status='interrupted', stage='上次退出时任务中断，可重新处理')
            if job.get('summary_status') == 'running':
                job.update(summary_status='error', summary_error='上次退出时摘要中断，可重试')
            self._save(job)

    def _save(self, job):
        self.db.execute('INSERT OR REPLACE INTO jobs VALUES (?, ?)', (job['id'], json.dumps(job, ensure_ascii=False)))
        self.db.commit()
        self.last_saved[job['id']] = time.monotonic()

    def update(self, jid, **fields):
        with self.lock:
            job = self.jobs[jid]
            previous_stage = job['stage']
            job.update(fields, updated=time.time())
            if job['stage'] != previous_stage:
                job['stage_started'] = time.time()
            if job['status'] in TERMINAL or previous_stage != job['stage'] or time.monotonic() - self.last_saved.get(jid, 0) >= .75:
                self._save(job)

    def get(self, jid):
        with self.lock:
            if jid not in self.jobs:
                raise KeyError(jid)
            result = copy.deepcopy(self.jobs[jid])
            if re.fullmatch(r'[a-f0-9]{32}', jid):
                source = self.source_path(jid)
                result['media_available'] = source is not None
                result['revision'] = result.get('revision',0)
                result['local_video_available'] = bool((result.get('local_source') or {}).get('has_video') and original_path(result))
        result['elapsed'] = max(0, (result.get('finished') or time.time()) - result['created'])
        return result

    def list(self):
        with self.lock:
            ordered = sorted(self.jobs.values(), key=lambda item: item['created'], reverse=True)[:200]
            return [{key: job.get(key) for key in ('id', 'title', 'platform', 'status', 'stage', 'created', 'mode', 'duration','profile','model','source_job','revision')} for job in ordered]

    def submit_local(self, path, profile='balanced', mode='visual', language=None, hotwords='', force=False,
                     cleanup_after=False, reference_url='', context_notes=''):
        source=inspect_media(path)
        if Path(source['path']).is_relative_to(self.root):
            raise ValueError('这是应用管理的缓存文件，请从历史记录重新识别；本地导入请选择缓存目录之外的原文件')
        if mode == 'download':
            raise ValueError('本地文件无需下载，请选择文字或文字加画面')
        return self.submit(reference_url,profile,mode,language,hotwords,force,cleanup_after,
                           _local_source=source,context_notes=context_notes)

    def submit(self, url, profile='balanced', mode='transcript', language=None, hotwords='', force=False, cleanup_after=False, source_job=None, _local_source=None, context_notes=''):
        url = media._extract_url(url) if url or not _local_source else ''
        if profile not in PROFILES or mode not in {'transcript', 'visual', 'download'}:
            raise ValueError('未知的处理方式')
        if language not in {None, 'zh', 'en', 'ja', 'ko'}:
            raise ValueError('不支持的语言')
        if cleanup_after and mode == 'download':
            raise ValueError('仅下载模式不能在完成后自动删除视频')
        if shutil.disk_usage(self.root).free < int(os.environ.get('VIDEO_MIN_FREE_MB','512'))*1048576:
            raise ValueError('磁盘剩余空间不足，请先清理一些媒体文件')
        signature = hashlib.sha256(json.dumps([url, profile, mode, language, hotwords,cleanup_after,_local_source,context_notes,'2.2'], ensure_ascii=False).encode()).hexdigest()
        with self.lock:
            if source_job and (source_job not in self.jobs or self.busy(source_job) or not self.source_path(source_job)):
                raise ValueError('原音频已清理或正在使用，请直接粘贴链接重新处理')
            if not force:
                for job in reversed(list(self.jobs.values())):
                    if job['signature'] == signature and job['status'] not in {'error', 'cancelled', 'interrupted'} and not (mode != 'transcript' and not cleanup_after and job.get('media_cleaned')):
                        return dict(self.get(job['id']), reused=True)
            if sum(j['status'] not in TERMINAL for j in self.jobs.values()) >= 20:
                raise ValueError('队列已满，请等部分任务完成后再添加')
            jid = uuid.uuid4().hex
            now = time.time()
            platform='local' if _local_source else media._detect_platform(url)
            title=Path(_local_source['name']).stem if _local_source else media._platform_label(platform) + ' · ' + urlparse(url).path.strip('/').split('/')[-1]
            job = dict(id=jid, url=url, signature=signature, platform=platform,
                       title=title, profile=profile, mode=mode, language=language,
                       hotwords=hotwords, status='queued', stage='排队中', progress=None,
                       created=now, updated=now, stage_started=now, transcript='', segments=[],
                       frames=[], assets=[], warnings=[], summary=None, summary_status='idle',
                       cleanup_after=cleanup_after, source_job=source_job, revision=0,
                       local_source=_local_source,context_notes=context_notes)
            self.jobs[jid] = job
            self.cancel_events[jid] = threading.Event()
            self._save(job)
            self.pool.submit(self._run, jid)
            return self.get(jid)

    def cancel(self, jid):
        with self.lock:
            job = self.jobs[jid]
            if job['status'] not in TERMINAL:
                self.cancel_events[jid].set()
                self.update(jid, status='cancelling', stage='正在停止（等待当前网络请求或语音片段结束）')
            return self.get(jid)

    def _run(self, jid):
        job = self.get(jid)
        directory = self.root / jid
        directory.mkdir(exist_ok=True)
        event = self.cancel_events[jid]
        def check():
            if event.is_set():
                raise Cancelled()
        def stage(label):
            check()
            self.update(jid, stage=label, progress=None, downloaded=0, total_bytes=None, speed=None)
        last = [time.monotonic(), 0]
        def progress(done, total):
            check()
            with self.lock:
                current_stage = self.jobs[jid]['stage']
            if current_stage == '解析链接并获取媒体':
                stage('下载声音' if job['mode'] == 'transcript' else '下载视频')
            now = time.monotonic()
            speed = max(0, done - last[1]) / max(.001, now - last[0])
            last[:] = [now, done]
            self.update(jid, downloaded=done, total_bytes=total, speed=speed,
                        progress=min(done / total, 1) if total else None)
        progress.stage = stage
        try:
            check()
            self.update(jid, status='running')
            stage('解析链接并获取媒体')
            if job.get('source_job'):
                source = self.get(job['source_job'])
                path = str(self.source_path(job['source_job']))
                platform = job['platform']
                self.update(jid, title=source['title'], author=source.get('author'), duration=source.get('duration'))
                fields = {k:source.get(k) for k in ('title','author','duration')}
                stage('复用已下载的音频')
            elif job.get('local_source'):
                local_path=original_path(job)
                if not local_path:
                    raise ValueError('本地原文件已移动、删除或修改，请重新选择文件导入')
                path=str(local_path)
                platform='local'
                fields={'title':job['title'],'duration':job['local_source']['duration']}
                stage('读取本地视频（不复制原文件）')
            else:
                downloader = media._download_transcription_media if job['mode'] == 'transcript' else media._download_video_file
                path, platform = asyncio.run(downloader(job['url'], str(directory), progress))
                metadata = directory / 'metadata.json'
                fields = json.loads(metadata.read_text(encoding='utf-8')) if metadata.exists() else {}
            check()
            self.update(jid, title=fields.get('title') or f'{media._platform_label(platform)} 视频',
                        author=fields.get('author'), duration=fields.get('duration'), media_bytes=Path(path).stat().st_size)
            original_media_path=path
            if job['mode'] != 'transcript' and not job.get('local_source'):
                self.update(jid, video_file=Path(path).name, assets=[Path(path).name])
            if job['mode'] != 'download':
                stage('准备复听音轨')
                audio_path = prepare_audio(path,directory/'speech.flac',check,
                                           on_progress=lambda value:self.update(jid,progress=value))
                if audio_path:
                    path = audio_path
                    self.update(jid, media_file='speech.flac', assets=self.get(jid)['assets']+['speech.flac'])
                def on_segment(segment, duration, items):
                    check()
                    self.update(jid, stage='识别语音', progress=min(segment['end'] / duration, .999) if duration else None,
                                duration=duration, transcribed_seconds=segment['end'],
                                transcript='\n'.join(s['text'] for s in items), segments=list(items))
                # Silent videos still produce the visual index.
                if job['mode'] == 'visual' and not audio_path:
                    self.update(jid, warnings=['视频没有音轨，请查看画面。'])
                else:
                    result = transcribe(path, PROFILES[job['profile']], job['language'], job['hotwords'],
                                        on_segment=on_segment, on_status=stage, cancelled=check)
                    self.update(jid, **result)
                    if not result['transcript']:
                        self.update(jid, warnings=['没有检测到清晰语音；如果内容主要靠画面表达，请使用「文字 + 画面」。'])
            if job['mode'] == 'visual':
                stage('提取画面')
                try:
                    frames = sample_frames(str(original_media_path), directory, check, lambda p: self.update(jid, progress=p))
                    self.update(jid, frames=frames, assets=self.get(jid)['assets'] + [f['file'] for f in frames],
                                warnings=self.get(jid)['warnings'] + ['画面为时间均匀抽样，最多 24 张，可能遗漏短暂字幕、动作或转场；不是完整视觉理解。'])
                except Exception as exc:
                    self.update(jid, warnings=self.get(jid)['warnings'] + [f'截图提取失败，原视频和文字稿仍可用：{type(exc).__name__}'])
            check()
            self._exports(jid, directory)
            self.update(jid, managed_files=[p.name for p in directory.iterdir() if p.is_file() and not p.is_symlink()])
            self.update(jid, status='done', stage='已完成', progress=1, finished=time.time())
            if job.get('cleanup_after'):
                try:
                    plan = self.cleanup_preview([jid],'media')
                    cleaned = self.cleanup_commit(plan['token'])
                    if cleaned.get('errors'):
                        self.update(jid, warnings=self.get(jid)['warnings'] + ['部分媒体未能清理，请在空间管理中重试。'])
                except Exception:
                    self.update(jid, warnings=self.get(jid)['warnings'] + ['文字稿已完成，但媒体自动清理失败；请在空间管理中重试。'])
        except Cancelled:
            self.update(jid, status='cancelled', stage='已取消', progress=None, finished=time.time())
        except Exception as exc:
            message = str(exc)
            if 'CERTIFICATE_VERIFY_FAILED' in message:
                message = 'HTTPS 证书校验失败。请检查代理证书或设置 SSL_CERT_FILE 指向可信 CA 文件。'
            self.update(jid, status='error', stage='处理失败', error=message[-1800:], progress=None, finished=time.time())
        finally:
            with self.lock:
                self.jobs[jid]['managed_files'] = [p.name for p in directory.iterdir() if p.is_file() and not p.is_symlink()]
                self._save(self.jobs[jid])
                self.cancel_events.pop(jid, None)

    def _exports(self, jid, directory):
        job = self.get(jid)
        segments = job['segments']
        srt = '\n\n'.join(f"{i}\n{stamp(s['start'], True)} --> {stamp(s['end'], True)}\n{s['text']}" for i, s in enumerate(segments, 1))
        md = f"# {job['title']}\n\n来源：{job['url']}\n\n"
        if job.get('local_source'):
            md += '本地来源：' + job['local_source']['name'] + '（原文件只读引用，不包含在导出包中）\n\n'
        if job.get('summary'):
            md += '## AI 摘要' + ('（文字修订后已过期）' if job.get('summary_stale') else '') + '\n\n' + job['summary'] + '\n\n'
        md += '## 文字稿（自动识别，可能有误）\n\n' + '\n\n'.join(f"[{stamp(s['start'])}] {s['text']}" for s in segments)
        if job['frames']:
            md += '\n\n## 画面索引（抽样）\n\n' + '\n\n'.join(f"[{stamp(f['time'])}] ![画面]({f['file']})" for f in job['frames'])
        exports = {'transcript.txt': job['transcript'], 'transcript.srt': srt, 'notes.md': md,
                   'ai-context.txt':build_handoff(dict(job,status='done' if job['status']=='running' else job['status']))['text'],
                   'result.json': json.dumps({k: job.get(k) for k in ('id', 'url', 'title', 'author', 'duration', 'language', 'model', 'transcript', 'segments', 'frames', 'warnings', 'summary','summary_stale','revision','review_count','recognition_version','source_job','media_cleaned')}, ensure_ascii=False, indent=2)}
        if job.get('context_notes'):
            exports['reference-notes.txt']='用户提供的参考摘要（不是逐字稿，未经录音核验）：\n\n'+job['context_notes']
        for name, content in exports.items():
            target = directory / name
            temporary = directory / (name + '.tmp')
            temporary.write_text(content, encoding='utf-8')
            temporary.replace(target)
        self.update(jid, assets=list(dict.fromkeys(job['assets'] + list(exports))))

    def handoff(self, jid, format='ai', max_chars=8000):
        return build_handoff(self.get(jid),format,max_chars)

    def storyboard(self, jid):
        with self.lock:
            if self.busy(jid):
                raise ValueError('请先等待任务完成')
            job = self.get(jid)
            name = make_storyboard(job,self.job_dir(jid))
            if not name:
                raise ValueError('这个任务没有保留画面')
            self.update(jid,assets=list(dict.fromkeys(job['assets']+[name])))
            return name

    def rerecognize(self, jid, profile='balanced', language=None, hotwords=''):
        with self.lock:
            job = self.get(jid)
            return self.submit(job['url'],profile,'transcript',language,hotwords,True,source_job=jid,
                               _local_source=job.get('local_source'),context_notes=job.get('context_notes',''))

    def edit_segments(self, jid, revision, changes):
        with self.lock:
            job = self.get(jid)
            if self.busy(jid):
                raise ValueError('请等任务和摘要完成后再修正')
            if revision != job.get('revision',0):
                raise ValueError('文字稿已在其他页面更新，请重新打开后再修正')
            segments = copy.deepcopy(job['segments'])
            seen = set()
            for change in changes:
                index,text = change['index'],change['text'].strip()
                if index in seen or index < 0 or index >= len(segments) or not text:
                    raise ValueError('无效的片段修正')
                seen.add(index)
                segments[index].update(text=text,edited=True,needs_review=False,review_reasons=[],words=[])
            directory = self.job_dir(jid)
            revisions = directory/'revisions'
            revisions.mkdir(exist_ok=True)
            if revisions.resolve() != revisions or revisions.is_symlink():
                raise ValueError('修订目录不安全')
            snapshot = revisions / f"{job.get('revision',0):06}-{uuid.uuid4().hex}.json"
            snapshot.write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8')
            if not job.get('revision',0):
                original = directory/'original-transcript.txt'
                if not original.exists():
                    original.write_text(job['transcript'],encoding='utf-8')
                self.update(jid,assets=list(dict.fromkeys(job['assets']+['original-transcript.txt'])))
            self.update(jid,segments=segments,transcript='\n'.join(s['text'] for s in segments),
                        revision=job.get('revision',0)+1,review_count=sum(bool(s.get('needs_review')) for s in segments),
                        summary_stale=bool(job.get('summary')))
            self._exports(jid,directory)
            return self.get(jid)

    def asset(self, jid, name):
        job = self.get(jid)
        if name not in job['assets'] or Path(name).name != name:
            raise KeyError(name)
        path = (self.root / jid / name).resolve()
        if path.parent != self.root / jid or not path.is_file():
            raise KeyError(name)
        return path

    def summarize(self, jid, vision=False):
        from summaries import configuration
        configuration()
        with self.lock:
            job = self.get(jid)
            if job['status'] != 'done' or (not job['transcript'] and not (vision and job['frames'])):
                raise ValueError('请先完成转录，或生成可以分析的画面')
            if job['summary_status'] == 'running':
                return job
            if sum(j.get('summary_status') == 'running' for j in self.jobs.values()) >= 5:
                raise ValueError('摘要队列已满，请稍后重试')
            self.update(jid, summary_status='running', summary_error=None)
            self.ai_pool.submit(self._summarize, jid, vision)
            return self.get(jid)

    def _summarize(self, jid, vision):
        from summaries import generate
        try:
            result = generate(self.get(jid), self.root / jid, vision)
            self.update(jid, summary=result, summary_status='done',summary_stale=False)
            self._exports(jid, self.root / jid)
        except Exception as exc:
            # Do not expose provider responses or credentials to browser/exports.
            self.update(jid, summary_status='error', summary_error=f'AI 请求失败（{type(exc).__name__}），请检查服务地址、模型和 API key；文字稿不受影响。')

    def close(self):
        for event in list(self.cancel_events.values()):
            event.set()
        self.pool.shutdown(wait=True)
        self.ai_pool.shutdown(wait=True)
        self.db.close()
        self.instance_lock.close()
