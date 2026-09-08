"""Create an isolated UI test library. Never point this at a user library."""
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from library import Library
from test_product import fixture

root=Path(sys.argv[1]).resolve()
if root.exists():
    raise SystemExit('Refusing to overwrite an existing fixture directory')
source=Path(sys.argv[2]).resolve()
lib=Library(root)
try:
    jid,directory=fixture(lib,'这是光离级打击，当量分级是作者自造的梗。')
    shutil.copy2(source/'bilibili_video.mp4',directory/'bilibili_video.mp4')
    shutil.copy2(source/'frame-01.jpg',directory/'frame-01.jpg')
    # Reuse the valid video as the audio source; discard only our fake audio fixture.
    (directory/'speech.flac').unlink()
    lib.update(jid,title='验收样本（复制的媒体，可清理）',mode='visual',language='zh',
               hotwords='',model='small',recognition_version='2.1',review_count=1,media_file=None)
    lib._exports(jid,directory)
    print(json.dumps({'id':jid,'root':str(root)},ensure_ascii=False))
finally:
    lib.close()
