"""Read-only verification of a completed real local-video job."""
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

base,jid=sys.argv[1].rstrip('/'),sys.argv[2]
output=Path(sys.argv[3]);output.mkdir(parents=True,exist_ok=True)
with urllib.request.urlopen(base+'/api/jobs/'+jid) as response:job=json.load(response)
assert job['status']=='done',job['status']
source=Path(job['local_source']['path']);stat=source.stat()
assert (stat.st_size,stat.st_mtime_ns)==(job['local_source']['bytes'],job['local_source']['mtime_ns'])
assert job['segments'] and job['frames'] and job['context_notes']
with urllib.request.urlopen(base+'/api/jobs/'+jid+'/bundle') as response:bundle=response.read()
with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
    names=archive.namelist()
    assert 'reference-notes.txt' in names and 'ai-context.txt' in names
    assert not any(Path(n).suffix in {'.mp4','.flac','.m4a'} for n in names)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/?job='+jid,wait_until='domcontentloaded')
    expect(page.locator('#result-title')).to_have_text(job['title'])
    page.locator('#tab-visual').click()
    page.wait_for_function("()=>document.getElementById('player').videoWidth>0",timeout=20000)
    dimensions=page.locator('#player').evaluate('(v)=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration})')
    page.locator('#player').evaluate('(v)=>{v.currentTime=300;}')
    page.wait_for_function("()=>Math.abs(document.getElementById('player').currentTime-300)<1 && !document.getElementById('player').seeking",timeout=20000)
    page.locator('#player').evaluate('(v)=>{v.muted=true;return v.play();}')
    page.wait_for_function("()=>document.getElementById('player').currentTime>301",timeout=20000)
    page.locator('#player').evaluate('(v)=>v.pause()')
    page.locator('#result').scroll_into_view_if_needed()
    page.screenshot(path=str(output/'real-report-visual.png'),full_page=False)
    page.locator('#tab-transcript').click()
    page.locator('#transcript-search').fill('CIEM')
    expect(page.locator('.segment').first).to_be_visible()
    page.locator('#result-title').scroll_into_view_if_needed()
    page.screenshot(path=str(output/'real-report-transcript.png'),full_page=False)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#result-title').scroll_into_view_if_needed()
    page.screenshot(path=str(output/'real-report-mobile.png'),full_page=False)
    assert not errors,errors
    browser.close()
result={'status':job['status'],'duration':job['duration'],'elapsed':job['elapsed'],
        'segments':len(job['segments']),'frames':len(job['frames']),'characters':len(job['transcript']),
        'source_bytes':stat.st_size,'source_unchanged':True,'bundle_bytes':len(bundle),
        'video':dimensions,'seek_seconds':300,'playback_advanced':True,'page_errors':errors}
(output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False),flush=True)
