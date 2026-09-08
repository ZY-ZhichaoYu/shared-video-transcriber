"""Manual end-to-end acceptance against setup_browser_fixture's isolated service."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

url=sys.argv[1].rstrip('/')
output=Path(sys.argv[2]);output.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1000},
                               permissions=['clipboard-read','clipboard-write'])
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(url,wait_until='domcontentloaded')
    page.locator('.history-item').first.click()
    expect(page.locator('#result-title')).to_contain_text('验收样本')
    original_revision=page.evaluate("state.job.revision||0")
    page.locator('#tab-transcript').click()
    page.locator('.edit-segment').first.click()
    expect(page.locator('#edit-dialog')).to_be_visible()
    page.locator('#edit-text').fill('这是光粒级打击，当量分级是作者自造的梗。')
    page.locator('#save-edit').click()
    expect(page.locator('#edit-dialog')).not_to_be_visible()
    expect(page.locator('#segments')).to_contain_text('光粒级打击')
    expect(page.locator('#review-status')).to_contain_text(f'已修订 {original_revision+1} 次')
    page.screenshot(path=str(output/'desktop.png'),full_page=True)
    page.locator('#copy-options').click()
    expect(page.locator('#copy-dialog')).to_be_visible()
    page.locator('#copy-full').click()
    copied=page.evaluate('navigator.clipboard.readText()')
    assert '光粒级打击' in copied and '来源：' in copied
    page.locator('#copy-picture').click()
    expect(page.locator('#picture-download')).to_be_visible(timeout=15000)
    picture=page.locator('#picture-download').get_attribute('href')
    assert context.request.get(url+picture).status==200
    page.screenshot(path=str(output/'copy.png'),full_page=True)
    page.locator('#copy-dialog .close-dialog').click()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow'
    page.screenshot(path=str(output/'mobile.png'),full_page=True)
    page.locator('#clean-job').click()
    page.locator('#preview-cleanup').click()
    expect(page.locator('#cleanup-preview')).to_be_visible()
    description=page.locator('#cleanup-description').inner_text()
    page.screenshot(path=str(output/'cleanup-preview.png'),full_page=True)
    # Only this specially named fixture library is allowed to be mutated by this script.
    health=context.request.get(url+'/api/health').json()
    assert Path(health['data_dir']).name=='browser-library', 'Refusing cleanup outside test library'
    page.locator('#confirm-cleanup').click()
    expect(page.locator('#storage-message')).to_contain_text('已释放',timeout=15000)
    cleanup_message=page.locator('#storage-message').inner_text()
    page.locator('#storage-dialog .close-dialog').click()
    expect(page.locator('#review-status')).to_contain_text('音视频已清理')
    expect(page.locator('#segments')).to_contain_text('当量分级')
    assert not errors,errors
    result={'clipboard_text':True,'storyboard':True,'edit_revision':1,'mobile_no_overflow':True,
            'cleanup_preview':description,'cleanup_result':cleanup_message,'page_errors':errors}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    browser.close()
