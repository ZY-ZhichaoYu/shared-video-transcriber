"""MCP bridge to the running local inbox, so AI and browser share durable jobs."""
import json
import os
import urllib.request
from urllib.parse import urlparse


def request(path, body=None):
    configured = os.environ.get('VIDEO_INBOX_URL')
    candidates = [configured.rstrip('/')] if configured else [f'http://127.0.0.1:{port}' for port in range(7860, 7880)]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for base in candidates:
        parsed = urlparse(base)
        if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.username or parsed.password:
            raise ValueError('VIDEO_INBOX_URL 必须是本机 HTTP 地址')
        try:
            with opener.open(base + '/api/health', timeout=.4) as response:
                health = json.loads(response.read())
            if health.get('service') != 'video-inbox':
                continue
        except Exception:
            continue
        headers = {'X-Video-Token': health['token'], 'Content-Type': 'application/json'}
        payload = None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(base + path, data=payload, headers=headers)
        try:
            with opener.open(req, timeout=10) as response:
                result = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = json.loads(exc.read()).get('detail', '请求失败')
            raise ValueError(str(detail)) from exc
        if isinstance(result, dict) and result.get('id'):
            result['inbox_url'] = base
            result['asset_urls'] = {name: f"{base}/api/jobs/{result['id']}/assets/{urllib.parse.quote(name)}" for name in result.get('assets', [])}
            if result.get('frames'):
                result['visual_note'] = 'frames 是带时间戳的抽样图片，最多 24 张。需要读取图片才能理解画面，文字稿不包含全部视觉信息。'
        return result
    raise RuntimeError('视频收件箱尚未启动，请先运行 run_web.bat / python app.py。旧版纯转录工具仍可独立使用。')
