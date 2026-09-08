'use strict';
let diagnosticReport=null;
$('open-diagnostics').onclick=async()=>{
  $('settings-dialog').close();$('diagnostics-dialog').showModal();
  $('diagnostics-list').replaceChildren(node('p','正在检查……','muted'));
  visible('diagnostics-error',false);$('copy-diagnostics').disabled=true;diagnosticReport=null;
  try{
    diagnosticReport=await api('/diagnostics');$('diagnostics-list').replaceChildren();
    for(const check of diagnosticReport.checks){
      const row=node('section',undefined,'diagnostic-row');
      row.append(node('strong',({ok:'✓ ',warning:'提示 · ',error:'需处理 · '}[check.status]||'')+check.name));
      row.append(node('p',check.detail));
      if(check.action)row.append(node('p',check.action,'muted'));
      $('diagnostics-list').append(row);
    }
    $('copy-diagnostics').disabled=false;
  }catch(e){$('diagnostics-list').replaceChildren();$('diagnostics-error').textContent=e.message;visible('diagnostics-error',true);}
};
$('copy-diagnostics').onclick=async()=>{
  if(!diagnosticReport)return;
  if(await clipboard(JSON.stringify(diagnosticReport,null,2)))toast('检查报告已复制，不含密钥和视频内容。');
  else toast('浏览器禁止复制；可双击 check_environment.bat 查看检查结果。');
};
