'use strict';
let localMode=false;
const onlineSubmit=$('job-form').onsubmit;
const oldRetry=$('retry').onclick;
function selectSource(local){
  localMode=local;visible('local-input',local);visible('online-input',!local);
  $('url').required=!local;$('local-path').required=local;
  document.querySelector('.composer-heading h1').textContent=local?'把本地视频，存成能读的记录。':'链接发来了，先看看讲了什么。';
  document.querySelector('.composer-heading p').textContent=local?'整理会议、报告和录屏；大文件无需上传。':'粘贴抖音、Bilibili 链接，或直接粘贴整段分享文字。';
  document.querySelector('.platforms').textContent=local?'视频 / 音频':'抖音 / Bilibili';
  for(const [id,active] of [['source-online',!local],['source-local',local]]){
    $(id).classList.toggle('source-active',active);$(id).setAttribute('aria-pressed',String(active));
  }
  const download=document.querySelector('[name=mode][value=download]');
  download.disabled=local;download.closest('label').hidden=local;
  if(local){const visual=document.querySelector('[name=mode][value=visual]');visual.checked=true;visual.dispatchEvent(new Event('change',{bubbles:true}));$('local-path').focus();}
  $('mode-hint').textContent=local?'只读原文件，另存音轨、文字与抽样画面；原文件不会被清理。':'优先下载音频，本地识别，不需要 AI 密钥。';
  $('retention-label').textContent=local?'完成后删除应用音轨缓存，保留文字、截图与原文件':'完成后删除音视频，保留文字与截图';
  $('retention-hint').textContent=local?'原视频不受影响，仍可回看':'节省空间；之后复听需要重新下载';
}
$('source-online').onclick=()=>selectSource(false);
$('source-local').onclick=()=>selectSource(true);
$('pick-local').onclick=async()=>{
  $('pick-local').disabled=true;
  try{const result=await api('/local/pick',{});if(result.path)$('local-path').value=result.path;}
  catch(e){toast(e.message);}finally{$('pick-local').disabled=false;}
};
$('local-notes-file').onchange=async()=>{
  const file=$('local-notes-file').files[0];if(!file)return;
  if(file.size>64000){toast('摘要文件太长，请先缩短到 8,000 字符以内。');return;}
  const text=await file.text();
  if(text.length>8000){toast('摘要超过 8,000 字符，请手动选择需要的部分；没有自动截断。');return;}
  $('local-context').value=text;toast('参考摘要已载入，导入时将与逐字稿分开保存。');
};
$('job-form').onsubmit=event=>{
  if(!localMode){onlineSubmit(event);return;}
  event.preventDefault();
  submit({path:$('local-path').value,reference_url:$('local-reference-url').value,context_notes:$('local-context').value,
    profile:$('profile').value,mode:document.querySelector('[name=mode]:checked').value,language:$('language').value||null,
    hotwords:$('hotwords').value,force:$('force').checked,cleanup_after:$('cleanup-after').checked},'/local/jobs');
};
$('retry').onclick=()=>{
  const j=state.job;if(!j.local_source){oldRetry();return;}
  submit({path:j.local_source.path,reference_url:j.url||'',context_notes:j.context_notes||'',
    profile:j.profile,mode:j.mode,language:j.language||null,hotwords:j.hotwords||'',force:true,
    cleanup_after:!!j.cleanup_after},'/local/jobs');
};
document.querySelectorAll('[name=mode]').forEach(input=>input.addEventListener('change',()=>{
  if(localMode)$('mode-hint').textContent='只读原文件，另存音轨和文字；选择画面模式会保留抽样截图。';
}));
const onlineNewTask=$('new-task').onclick;
$('new-task').onclick=()=>{
  if(!localMode){onlineNewTask();return;}
  for(const id of ['local-path','local-context','local-reference-url','local-notes-file'])$(id).value='';
  $('local-path').focus();window.scrollTo({top:0,behavior:'smooth'});
};
