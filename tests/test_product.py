import copy
import json
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from handoff import build_handoff
from library import Library
from webapp import app


def fixture(lib, text='这是光粒级打击。'):
    jid=uuid.uuid4().hex
    directory=lib.root/jid
    directory.mkdir()
    segments=[{'start':116.02,'end':119.5,'text':text,'needs_review':True,'review_reasons':['测试']}]
    job={'id':jid,'title':'测试视频','url':'https://b23.tv/test','signature':jid,'platform':'bilibili',
         'created':time.time(),'finished':time.time(),'status':'done','stage':'已完成','duration':120,
         'segments':segments,'transcript':text,'summary':None,'summary_status':'idle','revision':0,
         'assets':['bilibili_video.mp4','speech.flac','frame-01.jpg'],'frames':[{'time':117,'file':'frame-01.jpg'}],
         'video_file':'bilibili_video.mp4','media_file':'speech.flac','profile':'balanced','warnings':[]}
    for name in ['bilibili_video.mp4','speech.flac','bilibili_video.m4s','bilibili_audio.m4s','frame-01.jpg']:
        (directory/name).write_bytes(b'x'*1024)
    # An unrelated file in the directory must not be considered app-owned media.
    (directory/'personal.mp4').write_bytes(b'personal')
    lib.jobs[jid]=job;lib._save(job);lib._exports(jid,directory)
    return jid,directory


class CleanupTests(unittest.TestCase):
    def test_preview_does_not_delete_and_commit_preserves_text(self):
        with tempfile.TemporaryDirectory() as root:
            lib=Library(root)
            try:
                jid,d=fixture(lib)
                before=(d/'transcript.txt').read_bytes()
                p=lib.cleanup_preview([jid],'media')
                self.assertEqual(p['bytes'],4096)
                self.assertTrue((d/'bilibili_video.mp4').exists())
                r=lib.cleanup_commit(p['token'])
                self.assertEqual(r['reclaimed_bytes'],4096)
                self.assertEqual((d/'transcript.txt').read_bytes(),before)
                self.assertTrue((d/'personal.mp4').exists())
                self.assertTrue((d/'frame-01.jpg').exists())
                self.assertFalse(lib.get(jid)['media_available'])
                self.assertIsNone(lib.get(jid)['video_file'])
                self.assertIn('光粒级',lib.handoff(jid)['text'])
                with self.assertRaises(ValueError):lib.cleanup_commit(p['token'])
            finally:lib.close()

    def test_intermediates_keep_replay_and_source_video(self):
        with tempfile.TemporaryDirectory() as root:
            lib=Library(root)
            try:
                jid,d=fixture(lib);p=lib.cleanup_preview([jid],'intermediates')
                self.assertEqual({x['name'] for x in p['files']},{'bilibili_audio.m4s','bilibili_video.m4s'})
                lib.cleanup_commit(p['token']);self.assertTrue(lib.source_path(jid).exists())
            finally:lib.close()

    def test_file_changed_after_preview_aborts_all(self):
        with tempfile.TemporaryDirectory() as root:
            lib=Library(root)
            try:
                jid,d=fixture(lib);p=lib.cleanup_preview([jid])
                (d/'speech.flac').write_bytes(b'changed')
                with self.assertRaises(ValueError):lib.cleanup_commit(p['token'])
                self.assertTrue((d/'bilibili_video.mp4').exists())
            finally:lib.close()

    def test_running_and_dependent_jobs_protected(self):
        with tempfile.TemporaryDirectory() as root:
            lib=Library(root)
            try:
                jid,d=fixture(lib)
                child=uuid.uuid4().hex
                lib.jobs[child]=dict(lib.jobs[jid],id=child,source_job=jid,status='running')
                p=lib.cleanup_preview([jid])
                self.assertFalse(p['files']);self.assertEqual(len(p['skipped']),1)
                lib.jobs[child]['status']='done'
                p=lib.cleanup_preview([jid])
                lib.jobs[jid]['summary_status']='running'
                with self.assertRaises(ValueError):lib.cleanup_commit(p['token'])
            finally:lib.close()

    def test_images_removed_only_with_explicit_scope(self):
        with tempfile.TemporaryDirectory() as root:
            lib=Library(root)
            try:
                jid,d=fixture(lib);p=lib.cleanup_preview([jid],'all_media')
                lib.cleanup_commit(p['token'])
                self.assertEqual(lib.get(jid)['frames'],[])
                self.assertNotIn('frame-01.jpg',(d/'notes.md').read_text(encoding='utf-8'))
            finally:lib.close()

    def test_external_symlink_excluded(self):
        with tempfile.TemporaryDirectory() as root,tempfile.TemporaryDirectory() as external:
            lib=Library(root)
            try:
                jid,d=fixture(lib)
                target=Path(external)/'video.mp4';target.write_bytes(b'private')
                link=d/'douyin_media.mp4'
                try:link.symlink_to(target)
                except OSError:self.skipTest('Symlink creation is unavailable')
                p=lib.cleanup_preview([jid])
                self.assertNotIn('douyin_media.mp4',[x['name'] for x in p['files']])
                lib.cleanup_commit(p['token']);self.assertEqual(target.read_bytes(),b'private')
            finally:lib.close()


class EditingTests(unittest.TestCase):
    def test_revision_preserves_original_and_invalidates_summary(self):
        with tempfile.TemporaryDirectory() as root:
            lib=Library(root)
            try:
                jid,d=fixture(lib,'光弊及打击')
                lib.jobs[jid]['summary']='旧摘要'
                j=lib.edit_segments(jid,0,[{'index':0,'text':'光粒级打击'}])
                self.assertEqual(j['revision'],1)
                self.assertTrue(j['summary_stale'])
                self.assertEqual(j['segments'][0]['start'],116.02)
                self.assertFalse(j['segments'][0]['needs_review'])
                self.assertEqual((d/'original-transcript.txt').read_text(encoding='utf-8'),'光弊及打击')
                self.assertEqual(len(list((d/'revisions').glob('*.json'))),1)
                self.assertNotIn('旧摘要',lib.handoff(jid)['text'])
                with self.assertRaises(ValueError):lib.edit_segments(jid,0,[{'index':0,'text':'stale'}])
            finally:lib.close()

    def test_blank_out_of_range_and_busy_edits_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            lib=Library(root)
            try:
                jid,d=fixture(lib)
                for change in [{'index':3,'text':'x'},{'index':0,'text':' '}]:
                    with self.assertRaises(ValueError):lib.edit_segments(jid,0,[change])
                lib.jobs[jid]['summary_status']='running'
                with self.assertRaises(ValueError):lib.edit_segments(jid,0,[{'index':0,'text':'x'}])
            finally:lib.close()


class AutomaticCleanupTests(unittest.TestCase):
    def test_cleanup_failure_does_not_lose_finished_transcript(self):
        from test_inbox import fake_download, fake_transcribe
        import server
        with tempfile.TemporaryDirectory() as root, patch.object(server,'_download_transcription_media',fake_download), patch('library.transcribe',fake_transcribe):
            lib=Library(root)
            try:
                with patch.object(lib,'cleanup_commit',side_effect=OSError('file busy')):
                    job=lib.submit('https://b23.tv/test',cleanup_after=True)
                    lib.pool.shutdown(wait=True)
                result=lib.get(job['id'])
                self.assertEqual(result['status'],'done')
                self.assertIn('这是测试内容',result['transcript'])
                self.assertTrue(any('自动清理失败' in w for w in result['warnings']))
            finally:lib.close()

    def test_auto_cleanup_removes_download_and_keeps_notes(self):
        from test_inbox import fake_download, fake_transcribe
        import server
        with tempfile.TemporaryDirectory() as root, patch.object(server,'_download_transcription_media',fake_download), patch('library.transcribe',fake_transcribe):
            lib=Library(root)
            try:
                job=lib.submit('https://b23.tv/test',cleanup_after=True)
                lib.pool.shutdown(wait=True)
                result=lib.get(job['id'])
                self.assertEqual(result['status'],'done')
                self.assertFalse(result['media_available'])
                self.assertFalse((lib.root/job['id']/'audio.wav').exists())
                self.assertTrue((lib.root/job['id']/'transcript.txt').exists())
            finally:lib.close()


class HandoffTests(unittest.TestCase):
    def test_long_content_is_lossless_and_each_part_bounded(self):
        job={'title':'标题','url':'https://b23.tv/test','status':'done','duration':100,
             'segments':[{'start':i,'text':'当量分级：自造梗。'*200} for i in range(20)],'frames':[]}
        packet=build_handoff(job,max_chars=2000)
        self.assertEqual(''.join(packet['chunks']),packet['text'])
        self.assertTrue(all(len(p)<=2000 for p in packet['parts']))
        self.assertIn('全部资料已发送',packet['parts'][-1])
        self.assertEqual(packet['text'].count('当量分级'),4000)

    def test_frame_note_does_not_claim_to_attach_pictures(self):
        job={'title':'标题','url':'https://b23.tv/test','status':'running','segments':[], 'frames':[{'file':'f.jpg'}]}
        p=build_handoff(job)
        self.assertIn('图片没有包含',p['text']);self.assertTrue(p['partial'])


class NewApiTests(unittest.TestCase):
    def test_write_authorization_and_full_cleanup_flow(self):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'VIDEO_DATA_DIR':root}),TestClient(app) as client:
            jid,d=fixture(app.state.library)
            token=client.get('/api/health').json()['token'];headers={'X-Video-Token':token}
            self.assertEqual(client.post('/api/storage/cleanup',json={'token':'a'*32}).status_code,403)
            packet=client.get(f'/api/jobs/{jid}/handoff').json()
            self.assertIn('光粒级',packet['text'])
            preview=client.post('/api/storage/preview',headers=headers,json={'ids':[jid],'scope':'media'}).json()
            result=client.post('/api/storage/cleanup',headers=headers,json={'token':preview['token']})
            self.assertEqual(result.status_code,200)
            self.assertEqual(client.get(f'/api/jobs/{jid}/source').status_code,404)
            self.assertEqual(client.get(f'/api/jobs/{jid}/assets/transcript.txt').status_code,200)
            self.assertEqual(client.get(f'/api/jobs/{jid}/handoff?max_chars=1').status_code,422)


if __name__=='__main__':unittest.main()
