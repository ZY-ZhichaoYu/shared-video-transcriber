"""Optional local comparison; recognition differences are not an accuracy benchmark."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recognition import transcribe

start=time.monotonic()
result=transcribe(sys.argv[1],'small',language='zh',
                  hotwords='光粒级，当量分级，Hopf，Brando，微分几何，复几何，费尔兹奖',
                  on_status=lambda text: print(text,flush=True))
result['elapsed']=time.monotonic()-start
Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'elapsed':result['elapsed'],'segments':len(result['segments']),'review_count':result['review_count']},ensure_ascii=False),flush=True)
