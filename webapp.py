import asyncio
import io
import logging
import os
import secrets
import shutil
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from library import Library
from local_media import pick_file, original_path
from version import __version__

BASE = Path(__file__).resolve().parent


def transport_errors(loop, context):
    # Windows reports a normal browser disconnect again during socket shutdown.
    error = context.get('exception')
    if (isinstance(error, ConnectionResetError) and getattr(error, 'winerror', None) == 10054
            and '_ProactorBasePipeTransport._call_connection_lost' in context.get('message', '')):
        logging.getLogger(__name__).debug('Browser connection closed during Windows transport shutdown')
        return
    loop.default_exception_handler(context)


@asynccontextmanager
async def lifespan(app):
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(transport_errors)
    app.state.token = secrets.token_urlsafe(32)
    app.state.library = Library(os.environ.get('VIDEO_DATA_DIR', str(BASE / '.data')))
    try:
        yield
    finally:
        app.state.library.close()
        loop.set_exception_handler(previous_handler)


app = FastAPI(title='视频收件箱 API', version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])


@app.middleware('http')
async def local_guard(request: Request, call_next):
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        return JSONResponse({'detail': '不允许跨站访问本地视频资料'}, status_code=403)
    if request.headers.get('sec-fetch-site') == 'cross-site':
        return JSONResponse({'detail': '不允许跨站访问'}, status_code=403)
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        if request.headers.get('x-video-token') != getattr(request.app.state, 'token', None):
            return JSONResponse({'detail': '页面连接已更新，请刷新后重试'}, status_code=403)
        if int(request.headers.get('content-length', '0')) > 32768:
            return JSONResponse({'detail': '请求太大'}, status_code=413)
        body = await request.body()
        if len(body) > 32768:
            return JSONResponse({'detail': '请求太大'}, status_code=413)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    elif request.url.path == '/' or request.url.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-cache'
    return response


class JobInput(BaseModel):
    url: str = Field(min_length=1, max_length=8000)
    profile: Literal['fast', 'balanced', 'accurate'] = 'balanced'
    mode: Literal['transcript', 'visual', 'download'] = 'transcript'
    language: Literal['zh', 'en', 'ja', 'ko'] | None = None
    hotwords: str = Field(default='', max_length=500)
    force: bool = False
    cleanup_after: bool = False


class RerecognizeInput(BaseModel):
    profile: Literal['fast','balanced','accurate'] = 'balanced'
    language: Literal['zh','en','ja','ko'] | None = None
    hotwords: str = Field(default='',max_length=500)


class LocalJobInput(BaseModel):
    path: str = Field(min_length=1,max_length=4096)
    profile: Literal['fast','balanced','accurate'] = 'balanced'
    mode: Literal['transcript','visual'] = 'visual'
    language: Literal['zh','en','ja','ko'] | None = None
    hotwords: str = Field(default='',max_length=500)
    force: bool = False
    cleanup_after: bool = False
    reference_url: str = Field(default='',max_length=2000)
    context_notes: str = Field(default='',max_length=8000)


class SegmentChange(BaseModel):
    index: int = Field(ge=0)
    text: str = Field(min_length=1,max_length=4000)


class EditInput(BaseModel):
    revision: int = Field(ge=0)
    changes: list[SegmentChange] = Field(min_length=1,max_length=200)


class CleanupInput(BaseModel):
    ids: list[str] = Field(min_length=1,max_length=200)
    scope: Literal['intermediates','media','all_media'] = 'media'


class CleanupCommit(BaseModel):
    token: str = Field(pattern=r'^[a-f0-9]{32}$')


class SummaryInput(BaseModel):
    vision: bool = False


@app.exception_handler(KeyError)
async def missing(request, exc):
    return JSONResponse({'detail': '任务或文件不存在'}, status_code=404)


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


@app.get('/api/health')
def health(request: Request):
    configured = bool(os.environ.get('VIDEO_AI_BASE_URL') and os.environ.get('VIDEO_AI_MODEL'))
    return {'status': 'ok', 'service': 'video-inbox', 'version': __version__, 'token': request.app.state.token,
            'ffmpeg': bool(shutil.which('ffmpeg')), 'ai_configured': configured,
            'ai_host': urlparse(os.environ.get('VIDEO_AI_BASE_URL', '')).hostname if configured else None,
            'device': os.environ.get('VIDEO_WHISPER_DEVICE', 'cpu'),
            'data_dir': str(request.app.state.library.root)}


@app.get('/api/jobs')
def jobs(request: Request):
    return request.app.state.library.list()


@app.get('/api/diagnostics')
def environment_report():
    from diagnostics import collect
    return collect()


@app.post('/api/jobs', status_code=202)
def create_job(body: JobInput, request: Request):
    return request.app.state.library.submit(**body.model_dump())


@app.get('/api/jobs/{jid}')
def get_job(jid: str, request: Request):
    return request.app.state.library.get(jid)


@app.post('/api/local/pick')
def choose_local_file():
    return pick_file()


@app.post('/api/local/jobs',status_code=202)
def create_local_job(body: LocalJobInput, request: Request):
    return request.app.state.library.submit_local(**body.model_dump())


@app.get('/api/jobs/{jid}/original')
def original_video(jid: str, request: Request):
    library=request.app.state.library
    job=library.get(jid)
    path=original_path(job)
    if not path:
        raise HTTPException(404,'本地原文件已移动、删除或修改，请重新选择文件')
    return FileResponse(path)


@app.post('/api/jobs/{jid}/cancel')
def cancel_job(jid: str, request: Request):
    return request.app.state.library.cancel(jid)


@app.post('/api/jobs/{jid}/summary', status_code=202)
def summarize(jid: str, body: SummaryInput, request: Request):
    return request.app.state.library.summarize(jid, body.vision)


@app.get('/api/jobs/{jid}/assets/{name}')
def asset(jid: str, name: str, request: Request):
    path = request.app.state.library.asset(jid, name)
    inline = path.suffix.lower() in {'.jpg', '.png', '.mp4', '.webm', '.flac', '.m4a', '.wav'}
    return FileResponse(path, filename=None if inline else name)


@app.get('/api/jobs/{jid}/source')
def source_audio(jid: str, request: Request):
    library = request.app.state.library
    library.get(jid)
    path = library.source_path(jid)
    if not path:
        raise HTTPException(404,'原音视频已清理，请重新下载后复听')
    return FileResponse(path)


@app.get('/api/jobs/{jid}/handoff')
def handoff(jid: str, request: Request, format: Literal['ai','plain','timestamps','summary']='ai',
            max_chars: int=Query(default=8000,ge=2000,le=20000)):
    return request.app.state.library.handoff(jid,format,max_chars)


@app.post('/api/jobs/{jid}/storyboard')
def storyboard(jid: str, request: Request):
    name = request.app.state.library.storyboard(jid)
    return {'name':name,'url':f'/api/jobs/{jid}/assets/{name}'}


@app.post('/api/jobs/{jid}/recognize',status_code=202)
def rerecognize(jid: str, body: RerecognizeInput, request: Request):
    return request.app.state.library.rerecognize(jid,**body.model_dump())


@app.post('/api/jobs/{jid}/edit')
def edit(jid: str, body: EditInput, request: Request):
    return request.app.state.library.edit_segments(jid,body.revision,[s.model_dump() for s in body.changes])


@app.get('/api/storage')
def storage(request: Request):
    return request.app.state.library.storage_stats()


@app.post('/api/storage/preview')
def preview(body: CleanupInput, request: Request):
    return request.app.state.library.cleanup_preview(body.ids,body.scope)


@app.post('/api/storage/cleanup')
def cleanup(body: CleanupCommit, request: Request):
    return request.app.state.library.cleanup_commit(body.token)


@app.get('/api/jobs/{jid}/bundle')
def bundle(jid: str, request: Request):
    library = request.app.state.library
    job = library.get(jid)
    if job['status'] != 'done':
        raise HTTPException(409, '请等任务完成后再导出')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in job['assets']:
            if Path(name).suffix.lower() in {'.mp4','.webm','.mkv','.m4a','.mp3','.wav','.flac','.ogg'}:
                continue
            archive.write(library.asset(jid, name), name)
    return Response(stream.getvalue(), media_type='application/zip',
                    headers={'Content-Disposition': f'attachment; filename="video-notes-{jid[:8]}.zip"'})


@app.get('/')
def index():
    return FileResponse(BASE / 'static' / 'index.html')


@app.get('/docs')
def api_docs():
    return FileResponse(BASE / 'static' / 'api.html')


app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')
