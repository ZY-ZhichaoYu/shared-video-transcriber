"""Isolated UI test for local import, context notes and original-file safety."""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from test_local_media import create_audio

url=sys.argv[1].rstrip('/')
output=Path(sys.argv[2]).resolve();output.mkdir(parents=True,exist_ok=True)
source=output/'我的会议.wav'
if source.exists():
    raise SystemExit('Refusing to overwrite existing local test source')
source=create_audio(output)
before=hashlib.sha256(source.read_bytes()).hexdigest()
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1000})
    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(url,wait_until='domcontentloaded')
    health=context.request.get(url+'/api/health').json()
    assert Path(health['data_dir']).name=='browser-library','Only run against the disposable test library'
    page.locator('#source-local').click()
    page.locator('#local-path').fill(str(source))
    page.locator('.local-reference summary').click()
    page.locator('#local-context').fill('测试参考摘要：应单独保留，不冒充录像原话。')
    page.locator('#local-reference-url').fill('https://www.bilibili.com/video/BVexample/')
    page.screenshot(path=str(output/'local-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(output/'local-mobile.png'),full_page=True)
    page.locator('#submit').click()
    expect(page.locator('#result-title')).to_contain_text('我的会议',timeout=15000)
    expect(page.locator('#stage')).to_have_text('已完成',timeout=90000)
    expect(page.locator('#result-meta')).to_contain_text('本地文件')
    page.locator('#reference-note-panel summary').click()
    expect(page.locator('#reference-note-text')).to_contain_text('测试参考摘要')
    jid=page.evaluate('state.job.id')
    response=context.request.get(url+'/api/jobs/'+jid+'/original',headers={'Range':'bytes=0-15'})
    assert response.status==206
    page.locator('#clean-job').click()
    page.locator('#preview-cleanup').click()
    expect(page.locator('#cleanup-preview')).to_be_visible()
    page.locator('#confirm-cleanup').click()
    expect(page.locator('#storage-message')).to_contain_text('已释放')
    assert source.exists() and hashlib.sha256(source.read_bytes()).hexdigest()==before
    assert not errors,errors
    result={'local_import':True,'reference_notes':True,'range_playback':True,
            'source_unchanged_after_cleanup':True,'mobile_no_overflow':True,'page_errors':errors}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    browser.close()
