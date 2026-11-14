import { spawnSync } from 'node:child_process';
const status = spawnSync('tailscale', ['status','--json'], { encoding: 'utf8' });
if (status.status) throw Error('Tailscale 状态不可读');
const data = JSON.parse(status.stdout);
const peer = Object.values(data.Peer || {}).find(item => item.HostName === process.env.TAILSCALE_EXIT_NODE);
if (!peer?.Online || !peer.ExitNodeOption) throw Error('指定出口没有在线或未获准提供公网出口');
console.log('已核对指定 exit node 在线且获准使用');
const result = spawnSync('sudo', ['tailscale','set','--exit-node='+process.env.TAILSCALE_EXIT_NODE,'--exit-node-allow-lan-access=false'], { encoding:'utf8' });
if (result.status) throw Error('无法选择指定出口');
try {
  const trace = await fetch('https://www.cloudflare.com/cdn-cgi/trace', { signal: AbortSignal.timeout(20000) }).then(r=>r.text());
  if (!trace.split('\n').includes('loc=CN')) throw Error('实际公网出口不是中国大陆');
  const douyin = await fetch('https://www.douyin.com/', { signal: AbortSignal.timeout(20000) });
  if (!douyin.ok) throw Error('出口无法访问抖音');
  console.log('实际大陆出口和抖音连通检查通过');
} finally {
  const reset = spawnSync('sudo', ['tailscale','set','--exit-node='], { encoding:'utf8' });
  if (reset.status) throw Error('无法结束大陆出口阶段');
}
const bot = await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/getMe`, { signal: AbortSignal.timeout(20000) }).then(r=>r.json());
if (!bot.ok || bot.result.username !== 'C0verSnow_DouyinText_bot') throw Error('机器人身份检查失败');
const url = 'https://douyin-transcriber-webhook.f1515xcn.workers.dev/telegram';
const denied = await fetch(url, { method: 'POST', headers: { 'X-Telegram-Bot-Api-Secret-Token': 'invalid' }, body: '{}' });
if (denied.status !== 403) throw Error('线上 webhook 未拒绝错误的 secret');
const allowed = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json','X-Telegram-Bot-Api-Secret-Token':process.env.TELEGRAM_WEBHOOK_SECRET},body:JSON.stringify({update_id:Date.now(),message:{from:{id:5909140623},chat:{id:5909140623,type:'private'},text:'/start'}}) });
if (!allowed.ok) throw Error('线上 webhook 授权检查失败');
console.log('线上 Worker 授权入口和 Telegram 机器人身份检查通过');
