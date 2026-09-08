import asyncio
import json
import ssl
import io
import wave
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import server
import recognition
from library import Library, stamp
from webapp import app, transport_errors
import summaries


class UrlTests(unittest.TestCase):
    def test_tracking_removed_part_preserved(self):
        self.assertEqual(server._extract_url('朋友分享：https://www.bilibili.com/video/BV1orhK6tE5q/?p=2&spm_id=abc。复制打开'),
                         'https://www.bilibili.com/video/BV1orhK6tE5q/?p=2')

    def test_spoofed_domains_rejected(self):
        for url in ['https://bilibili.com.evil.test/video/BV123', 'https://evildouyin.com/video/1',
                    'https://b23.tv@127.0.0.1/a', 'http://localhost:8000', 'https://evilb23.tv/a', 'file:///etc/passwd']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                server._extract_url(url)

    def test_tls_enabled(self):
        self.assertTrue(server._SSL_CTX.check_hostname)
        self.assertEqual(server._SSL_CTX.verify_mode, ssl.CERT_REQUIRED)

    def test_part_selects_correct_cid(self):
        view = {'title': 'video', 'cid': 100, 'pages': [{'cid': 100}, {'cid': 200, 'part': 'second', 'duration': 20}]}
        with patch.object(server, '_bilibili_view_sync', return_value=view), patch.object(server, '_bilibili_api_json_sync', return_value={}) as api:
            metadata, _, _ = server._bilibili_view_and_playurl_sync('https://www.bilibili.com/video/BV123?p=2')
        self.assertIn('cid=200', api.call_args.args[0])
        self.assertEqual(metadata['duration'], 20)

    def test_bare_link(self):
        self.assertEqual(server._extract_url('b23.tv/AbCd！'), 'https://b23.tv/AbCd')


async def fake_download(url, directory, on_progress=None):
    path = Path(directory) / 'audio.wav'
    with wave.open(str(path),'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\0'*32000)
    if on_progress:
        on_progress(7, 7)
    return str(path), 'bilibili'


def fake_transcribe(path, model, language, hotwords, on_segment, on_status, cancelled):
    cancelled()
    on_status('识别语音')
    segments = [{'start': 0.0, 'end': 2.5, 'text': '这是测试内容。'}]
    on_segment(segments[0], 3.0, segments)
    return {'transcript': segments[0]['text'], 'segments': segments, 'duration': 3.0, 'language': 'zh', 'model': model}


def wait_done(library, jid):
    for _ in range(100):
        job = library.get(jid)
        if job['status'] in {'done', 'error', 'cancelled'}:
            return job
        time.sleep(.02)
    raise AssertionError('task did not finish')


class LifecycleTests(unittest.TestCase):
    def test_second_instance_cannot_rewrite_running_jobs(self):
        with tempfile.TemporaryDirectory() as root:
            first = Library(root)
            try:
                with self.assertRaises(RuntimeError):
                    Library(root)
            finally:
                first.close()

    def test_durable_result_exports_dedup_and_asset_boundary(self):
        with tempfile.TemporaryDirectory() as root, patch.object(server, '_download_transcription_media', fake_download), patch('library.transcribe', fake_transcribe):
            lib = Library(root)
            first = lib.submit('https://www.bilibili.com/video/BV123')
            job = wait_done(lib, first['id'])
            self.assertEqual(job['status'], 'done', job.get('error'))
            self.assertIn('00:00:00,000 --> 00:00:02,500', lib.asset(job['id'], 'transcript.srt').read_text(encoding='utf-8'))
            self.assertTrue(lib.submit('https://www.bilibili.com/video/BV123')['reused'])
            with self.assertRaises(KeyError):
                lib.asset(job['id'], '../library.sqlite3')
            lib.close()
            reopened = Library(root)
            self.assertEqual(reopened.get(job['id'])['transcript'], '这是测试内容。')
            reopened.close()

    def test_cancel_bypasses_fallback(self):
        entered = threading.Event()
        async def download(url, directory, on_progress):
            entered.set()
            for i in range(100):
                await asyncio.sleep(.01)
                on_progress(i, 100)
        with tempfile.TemporaryDirectory() as root, patch.object(server, '_download_transcription_media', download):
            lib = Library(root)
            job = lib.submit('https://b23.tv/test')
            self.assertTrue(entered.wait(1))
            lib.cancel(job['id'])
            self.assertEqual(wait_done(lib, job['id'])['status'], 'cancelled')
            lib.close()

    def test_restart_marks_running_interrupted(self):
        with tempfile.TemporaryDirectory() as root:
            lib = Library(root)
            lib.jobs['x'] = {'id': 'x', 'status': 'running', 'stage': '识别', 'created': time.time()}
            lib._save(lib.jobs['x'])
            lib.close()
            lib = Library(root)
            self.assertEqual(lib.get('x')['status'], 'interrupted')
            lib.close()

    def test_asr_model_reused(self):
        class FakeModel:
            def transcribe(self, *args, **kwargs):
                return iter([SimpleNamespace(start=0, end=1, text='你好')]), SimpleNamespace(duration=1, language='zh')
        with patch('faster_whisper.WhisperModel', return_value=FakeModel()) as factory, patch.object(recognition, '_MODEL', None), patch.object(recognition, '_KEY', None):
            recognition.transcribe('fake.wav', 'base')
            recognition.transcribe('fake.wav', 'base')
            self.assertEqual(factory.call_count, 1)


class ApiTests(unittest.TestCase):
    def test_only_known_windows_disconnect_is_filtered(self):
        loop = unittest.mock.Mock()
        error = ConnectionResetError()
        error.winerror = 10054
        transport_errors(loop, {'exception':error, 'message':'Exception in callback _ProactorBasePipeTransport._call_connection_lost()'})
        loop.default_exception_handler.assert_not_called()
        transport_errors(loop, {'exception':error, 'message':'Unexpected failure in video download'})
        loop.default_exception_handler.assert_called_once()

    def test_security_and_validation(self):
        with tempfile.TemporaryDirectory() as root, patch.dict('os.environ', {'VIDEO_DATA_DIR': root}), TestClient(app) as client:
            self.assertEqual(client.get('/').status_code, 200)
            self.assertEqual(client.get('/api/health', headers={'Origin': 'https://evil.test'}).status_code, 403)
            self.assertEqual(client.get('/api/health', headers={'Host': 'evil.test'}).status_code, 400)
            self.assertEqual(client.post('/api/jobs', json={'url': 'b23.tv/test'}).status_code, 403)
            token = client.get('/api/health').json()['token']
            headers = {'X-Video-Token': token}
            self.assertEqual(client.post('/api/jobs', headers=headers, json={'url':'https://bilibili.com.evil.test'}).status_code, 400)
            self.assertEqual(client.post('/api/jobs', headers=headers, json={'url':'b23.tv/test','profile':'invalid'}).status_code, 422)
            self.assertEqual(client.get('/api/jobs/missing/assets/library.sqlite3').status_code, 404)
            self.assertEqual(client.get('/api/jobs').json(), [])

    def test_timestamp_rounding(self):
        self.assertEqual(stamp(59.9999, True), '00:01:00,000')


class DownloadTests(unittest.TestCase):
    def test_truncated_response_fails(self):
        response = io.BytesIO(b'1234')
        response.headers = {'Content-Length': '10'}
        with tempfile.TemporaryDirectory() as root, patch('urllib.request.urlopen', return_value=response):
            with self.assertRaisesRegex(RuntimeError, '不完整'):
                server._download_sync('https://example.com/media', str(Path(root) / 'media.bin'))

    def test_unknown_length_has_byte_progress(self):
        response = io.BytesIO(b'1234')
        response.headers = {}
        seen = []
        with tempfile.TemporaryDirectory() as root, patch('urllib.request.urlopen', return_value=response):
            server._download_sync('https://example.com/media', str(Path(root) / 'media.bin'), progress_cb=lambda n,t:seen.append((n,t)))
        self.assertEqual(seen[-1], (4, None))


class SummaryTests(unittest.TestCase):
    def test_no_implicit_cloud_configuration(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ValueError):
            summaries.configuration()

    def test_vision_budget_and_truncation_disclosed(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            (path / 'one.jpg').write_bytes(b'fixture')
            frames = [{'time': i, 'file': 'one.jpg'} for i in range(24)]
            job = {'title': '测试', 'url': 'https://b23.tv/example', 'segments': [{'start':0, 'text':'字' * 46000}], 'frames':frames}
            response = io.BytesIO(json.dumps({'choices':[{'message':{'content':'摘要内容'}}]}).encode())
            opener = unittest.mock.Mock()
            opener.open.return_value = response
            with patch.dict('os.environ', {'VIDEO_AI_BASE_URL':'http://127.0.0.1:1234/v1', 'VIDEO_AI_MODEL':'test'}), patch('urllib.request.build_opener', return_value=opener):
                result = summaries.generate(job, path, True)
            payload = json.loads(opener.open.call_args.args[0].data)
            images = [c for c in payload['messages'][1]['content'] if c['type'] == 'image_url']
            self.assertEqual(len(images), 8)
            self.assertIn('45,000', result)
            self.assertEqual(len(job['segments'][0]['text']), 46000)


if __name__ == '__main__':
    unittest.main()
