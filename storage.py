"""Scoped, previewed file deletion with durable audit records and busy-job guards."""
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from local_media import original_path

AUDIO_VIDEO = {'.mp4','.webm','.mkv','.mov','.m4a','.m4s','.mp3','.wav','.flac','.ogg','.aac','.ts'}
IMAGES = {'.jpg','.jpeg','.png','.webp'}
KNOWN = {'speech.flac','speech.partial.flac','bilibili_media.m4a','bilibili_video.mp4',
         'bilibili_video.m4s','bilibili_audio.m4s','douyin_media.mp4','douyin_video.mp4','storyboard.png'}
TERMINAL = {'done','error','cancelled','interrupted'}


class StorageMixin:
    def job_dir(self, jid):
        if not re.fullmatch(r'[a-f0-9]{32}', jid):
            raise ValueError('无效的任务目录')
        raw = self.root / jid
        path = raw.resolve()
        if raw.is_symlink() or path.parent != self.root or path != raw:
            raise ValueError('任务目录超出允许范围')
        return path

    def busy(self, jid):
        job = self.jobs[jid]
        return (job['status'] not in TERMINAL or job.get('summary_status') == 'running'
                or any(j.get('source_job') == jid and j['status'] not in TERMINAL for j in self.jobs.values()))

    def source_path(self, jid):
        job = self.jobs[jid]
        directory = self.job_dir(jid)
        candidates = ['speech.flac',job.get('media_file'),job.get('video_file'),
                      'bilibili_media.m4a','douyin_media.mp4','douyin_video.mp4','bilibili_video.mp4']
        for name in candidates:
            if not name or Path(name).name != name:
                continue
            path = directory / name
            if not path.is_symlink() and path.resolve().parent == directory and path.is_file():
                return path
        return original_path(job)

    def storage_stats(self):
        with self.lock:
            items = []
            for jid, job in self.jobs.items():
                if not re.fullmatch(r'[a-f0-9]{32}', jid):
                    continue
                try:
                    directory = self.job_dir(jid)
                    files = [p for p in directory.iterdir() if p.is_file() and not p.is_symlink() and p.resolve().parent == directory] if directory.exists() else []
                    size = sum(p.stat().st_size for p in files)
                    media = sum(p.stat().st_size for p in files if p.suffix.lower() in AUDIO_VIDEO)
                except (OSError, ValueError):
                    continue
                items.append({'id':jid,'title':job['title'],'bytes':size,'media_bytes':media,
                              'external_source':bool(job.get('local_source')),
                              'busy':self.busy(jid),'status':job['status'],'created':job['created']})
            return {'total_bytes':sum(j['bytes'] for j in items), 'media_bytes':sum(j['media_bytes'] for j in items),
                    'free_bytes':shutil.disk_usage(self.root).free,
                    'jobs':sorted(items,key=lambda j:j['bytes'],reverse=True)}

    def cleanup_preview(self, ids, scope='media'):
        if scope not in {'intermediates','media','all_media'}:
            raise ValueError('未知的清理范围')
        with self.lock:
            files, skipped = [], []
            for jid in dict.fromkeys(ids):
                if jid not in self.jobs:
                    raise KeyError(jid)
                if self.busy(jid):
                    skipped.append({'id':jid,'reason':'任务、摘要或关联重识别正在使用文件'})
                    continue
                job = self.jobs[jid]
                directory = self.job_dir(jid)
                owned = set(job.get('managed_files', [])) | set(job.get('assets', [])) | KNOWN
                if job.get('media_file'):
                    owned.add(job['media_file'])
                source = self.source_path(jid)
                protected = {job.get('video_file'), source.name if source else None}
                for name in sorted(owned):
                    if not name or Path(name).name != name:
                        continue
                    path = directory / name
                    if path.is_symlink() or path.resolve().parent != directory or not path.is_file():
                        continue
                    suffix = path.suffix.lower()
                    allowed = AUDIO_VIDEO | (IMAGES if scope == 'all_media' else set())
                    if suffix not in allowed or (scope == 'intermediates' and name in protected):
                        continue
                    stat = path.stat()
                    files.append({'id':jid,'name':name,'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns})
            plan = {'token':uuid.uuid4().hex,'created':time.time(),'scope':scope,'files':files,
                    'bytes':sum(f['bytes'] for f in files),'skipped':skipped}
            self.cleanup_plans = {k:v for k,v in getattr(self,'cleanup_plans',{}).items() if time.time()-v['created'] < 180}
            if len(self.cleanup_plans) >= 20:
                self.cleanup_plans.pop(next(iter(self.cleanup_plans)))
            self.cleanup_plans[plan['token']] = plan
            return json.loads(json.dumps(plan))

    def cleanup_commit(self, token):
        with self.lock:
            plan = getattr(self,'cleanup_plans',{}).pop(token,None)
            if not plan or time.time()-plan['created'] > 180:
                raise ValueError('清理预览已过期，请重新预览')
            # Validate every target before removing any file.
            for item in plan['files']:
                if self.busy(item['id']):
                    raise ValueError('任务正在使用文件，请稍后重新预览')
                directory = self.job_dir(item['id'])
                path = directory / item['name']
                if path.is_symlink() or path.resolve().parent != directory or not path.is_file():
                    raise ValueError('文件状态已改变，请重新预览')
                stat = path.stat()
                if (stat.st_size,stat.st_mtime_ns) != (item['bytes'],item['mtime_ns']):
                    raise ValueError('文件已更新，请重新预览')
            audit = dict(plan, status='started', removed=[], errors=[])
            self.db.execute('CREATE TABLE IF NOT EXISTS maintenance (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            self.db.execute('INSERT INTO maintenance VALUES (?,?)',(token,json.dumps(audit,ensure_ascii=False)))
            self.db.commit()
            for item in plan['files']:
                try:
                    (self.job_dir(item['id']) / item['name']).unlink()
                    audit['removed'].append(item)
                except OSError as exc:
                    audit['errors'].append({'id':item['id'],'name':item['name'],'error':type(exc).__name__})
            removed = {(i['id'],i['name']) for i in audit['removed']}
            for jid in {i['id'] for i in audit['removed']}:
                job = self.jobs[jid]
                job['assets'] = [n for n in job['assets'] if (jid,n) not in removed]
                job['frames'] = [f for f in job['frames'] if (jid,f['file']) not in removed]
                for field in ('media_file','video_file'):
                    if (jid,job.get(field)) in removed:
                        job[field] = None
                job['cleanup_at'] = time.time()
                job['media_cleaned'] = self.source_path(jid) is None
                if job.get('local_source'):
                    job['cache_cleaned'] = True
                self._save(job)
                # Text exports remain useful; regenerate frame references only when needed.
                if job['status'] == 'done':
                    try:
                        self._exports(jid,self.job_dir(jid))
                    except OSError as exc:
                        audit['errors'].append({'id':jid,'name':'exports','error':type(exc).__name__})
            audit.update(status='completed', reclaimed_bytes=sum(i['bytes'] for i in audit['removed']))
            self.db.execute('UPDATE maintenance SET payload=? WHERE id=?',(json.dumps(audit,ensure_ascii=False),token))
            self.db.commit()
            return audit
