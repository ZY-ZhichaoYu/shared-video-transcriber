export default {
  async fetch(request, env) {
    if (new URL(request.url).pathname !== '/telegram' || request.method !== 'POST') {
      return new Response('Not found', { status: 404 });
    }
    if (!env.TELEGRAM_WEBHOOK_SECRET || request.headers.get('X-Telegram-Bot-Api-Secret-Token') !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response('Forbidden', { status: 403 });
    }
    let update;
    try { update = await request.json(); } catch { return new Response('Bad request', { status: 400 }); }
    const message = update.message;
    const allowed = (env.TELEGRAM_ALLOWED_USER_IDS || '').split(',').map(id => id.trim());
    if (!Number.isSafeInteger(update.update_id) || !message || message.chat?.type !== 'private'
        || !allowed.includes(String(message.from?.id)) || message.chat.id !== message.from.id) {
      return new Response('ok');
    }
    const text = typeof message.text === 'string' ? message.text : '';
    if (text === '/start' || text === '/help') {
      await notify(env, message.chat.id, '把抖音视频的分享链接发给我，GitHub Actions 会转成文字，并把 TXT、SRT 和时间戳 JSON 发回来。');
      return new Response('ok');
    }
    const url = douyinUrl(text);
    if (!url) {
      await notify(env, message.chat.id, '请发送抖音视频分享链接，也可以直接粘贴整段分享文字。');
      return new Response('ok');
    }
    const response = await fetch(`https://api.github.com/repos/${env.GITHUB_REPOSITORY}/actions/workflows/${env.GITHUB_WORKFLOW}/dispatches`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json', 'User-Agent': 'douyin-transcriber-webhook' },
      body: JSON.stringify({ ref: env.GITHUB_REF, inputs: { url, chat_id: String(message.chat.id), request_id: String(update.update_id) } }),
    });
    if (!response.ok) {
      await notify(env, message.chat.id, 'CI 暂时无法启动，请稍后重发。');
      return new Response('Dispatch failed', { status: 502 });
    }
    await notify(env, message.chat.id, '已交给远端 CI，完成后会在这里发回文字稿。');
    return new Response('ok');
  },
};

export function douyinUrl(text) {
  const match = text.match(/(?:https?:\/\/)?(?:(?:www\.|v\.)?douyin\.com|(?:www\.)?iesdouyin\.com)\/[^\s<>"“”\u4e00-\u9fff]+/i);
  if (!match || (match.index > 0 && /[a-z0-9./@_-]/i.test(text[match.index - 1]))) return null;
  const raw = match[0].replace(/[。，！？；）)】\]》]+$/, '');
  const url = new URL(/^https?:/i.test(raw) ? raw : `https://${raw}`);
  const hosts = ['douyin.com', 'www.douyin.com', 'v.douyin.com', 'iesdouyin.com', 'www.iesdouyin.com'];
  if (!hosts.includes(url.hostname) || url.username || url.password || url.port) return null;
  url.hash = '';
  return url.href;
}

async function notify(env, chat, text) {
  try {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chat_id: chat, text }),
  });
  return response.ok;
  } catch { return false; }
}
