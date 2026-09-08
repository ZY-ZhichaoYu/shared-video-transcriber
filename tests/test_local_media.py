import hashlib
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from library import Library
from local_media import inspect_media, original_path
from test_inbox import fake_transcribe
from webapp import app


def create_audio(root):
    source=Path(root)/'我的会议.wav'
    with wave.open(str(source),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000)
        audio.writeframes(b'\0'*32000)
    return source.resolve()


class LocalMediaTests(unittest.TestCase):
    def test_original_survives_processing_and_all_media_cleanup(self):
        with tempfile.TemporaryDirectory() as root,patch('library.transcribe',fake_transcribe),patch('server._download_transcription_media',side_effect=AssertionError('must not download')):
            source=create_audio(root);before=hashlib.sha256(source.read_bytes()).hexdigest()
            lib=Library(Path(root)/'cache')
            try:
                job=lib.submit_local(str(source),mode='transcript',context_notes='Zoom summary: CIME')
                lib.pool.shutdown(wait=True)
                result=lib.get(job['id'])
                self.assertEqual(result['status'],'done',result.get('error'))
                self.assertEqual(result['platform'],'local')
                self.assertEqual(result['url'],'')
                self.assertIn('Zoom summary',lib.handoff(job['id'])['text'])
                self.assertNotIn(str(source),lib.handoff(job['id'])['text'])
                self.assertNotIn(source.name,result['assets'])
                plan=lib.cleanup_preview([job['id']],'all_media')
                lib.cleanup_commit(plan['token'])
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)
                self.assertTrue(lib.get(job['id'])['media_available'])
                self.assertTrue(lib.get(job['id'])['cache_cleaned'])
                self.assertEqual(lib.source_path(job['id']),source)
                self.assertEqual(lib.storage_stats()['media_bytes'],0)
            finally:lib.close()

    def test_changed_source_is_not_silently_reused(self):
        with tempfile.TemporaryDirectory() as root:
            source=create_audio(root);info=inspect_media(str(source))
            self.assertEqual(original_path({'local_source':info}),source)
            source.write_bytes(b'changed')
            self.assertIsNone(original_path({'local_source':info}))

    def test_non_media_relative_and_network_paths_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            bad=Path(root)/'secret.txt';bad.write_text('private')
            for path in [str(bad),'relative.mp4',r'\\server\share\video.mp4']:
                with self.subTest(path=path),self.assertRaises(ValueError):inspect_media(path)

    def test_local_api_auth_range_playback_and_no_source_in_bundle(self):
        with tempfile.TemporaryDirectory() as root,patch('library.transcribe',fake_transcribe),patch.dict(os.environ,{'VIDEO_DATA_DIR':str(Path(root)/'cache')}),TestClient(app) as client:
            source=create_audio(root)
            body={'path':str(source),'mode':'transcript','reference_url':'https://b23.tv/test'}
            self.assertEqual(client.post('/api/local/jobs',json=body).status_code,403)
            headers={'X-Video-Token':client.get('/api/health').json()['token']}
            response=client.post('/api/local/jobs',json=body,headers=headers)
            self.assertEqual(response.status_code,202,response.text)
            app.state.library.pool.shutdown(wait=True)
            jid=response.json()['id']
            read=client.get(f'/api/jobs/{jid}/original',headers={'Range':'bytes=0-15'})
            self.assertEqual(read.status_code,206)
            self.assertEqual(len(read.content),16)
            import io,zipfile
            with zipfile.ZipFile(io.BytesIO(client.get(f'/api/jobs/{jid}/bundle').content)) as bundle:
                self.assertNotIn(source.name,bundle.namelist())
                self.assertIn('transcript.txt',bundle.namelist())
            with patch('webapp.pick_file',return_value={'path':str(source)}):
                self.assertEqual(client.post('/api/local/pick',headers=headers).json()['path'],str(source))

    def test_app_owned_media_cannot_be_reclassified_as_external_original(self):
        with tempfile.TemporaryDirectory() as root:
            lib=Library(root)
            try:
                source=create_audio(root)
                with self.assertRaises(ValueError):lib.submit_local(str(source))
            finally:lib.close()


if __name__=='__main__':unittest.main()
