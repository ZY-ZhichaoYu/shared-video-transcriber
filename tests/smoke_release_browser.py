"""Check onboarding diagnostics against an empty, disposable demo instance."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

url=sys.argv[1].rstrip('/')
output=Path(sys.argv[2]).resolve()
output.mkdir(parents=True,exist_ok=False)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context=browser.new_context(viewport={'width':1440,'height':960},
                                permissions=['clipboard-read','clipboard-write'])
    health=context.request.get(url+'/api/health').json()
    assert Path(health['data_dir']).name=='demo','Use only the disposable demo library'
    assert health['version']=='2.3.0'
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(url,wait_until='networkidle')
    page.locator('#settings-button').click()
    page.locator('#open-diagnostics').click()
    expect(page.locator('#copy-diagnostics')).to_be_enabled(timeout=15000)
    expect(page.locator('.diagnostic-row')).not_to_have_count(0)
    page.locator('#copy-diagnostics').click()
    report=json.loads(page.evaluate('()=>navigator.clipboard.readText()'))
    serialized=json.dumps(report)
    assert 'checks' in report
    assert health['data_dir'] not in serialized and health['token'] not in serialized
    assert all(item['status'] in ('ok','warning','error') for item in report['checks'])
    page.screenshot(path=str(output/'diagnostics-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('()=>document.documentElement.scrollWidth <= innerWidth')
    bounds=page.locator('#diagnostics-dialog').bounding_box()
    assert bounds and bounds['x']>=0 and bounds['x']+bounds['width']<=391
    page.screenshot(path=str(output/'diagnostics-mobile.png'),full_page=True)
    page.locator('#diagnostics-dialog .close-dialog').click()
    expect(page.locator('#diagnostics-dialog')).not_to_be_visible()
    assert not errors,errors
    print(json.dumps({'diagnostics':True,'clipboard':True,'mobile_no_overflow':True,
                      'page_errors':errors}))
    browser.close()
