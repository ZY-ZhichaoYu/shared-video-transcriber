var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// index.js
var index_default = {
  async fetch(request, env) {
    if (new URL(request.url).pathname !== "/telegram" || request.method !== "POST") {
      return new Response("Not found", { status: 404 });
    }
    if (!env.TELEGRAM_WEBHOOK_SECRET || request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response("Forbidden", { status: 403 });
    }
    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("Bad request", { status: 400 });
    }
    const message = update.message;
    const allowed = (env.TELEGRAM_ALLOWED_USER_IDS || "").split(",").map((id) => id.trim());
    if (!Number.isSafeInteger(update.update_id) || !message || message.chat?.type !== "private" || !allowed.includes(String(message.from?.id)) || message.chat.id !== message.from.id) {
      return new Response("ok");
    }
    const text = typeof message.text === "string" ? message.text : "";
    if (text === "/start" || text === "/help") {
      await notify(env, message.chat.id, "\u628A\u6296\u97F3\u89C6\u9891\u7684\u5206\u4EAB\u94FE\u63A5\u53D1\u7ED9\u6211\uFF0CGitHub Actions \u4F1A\u8F6C\u6210\u6587\u5B57\uFF0C\u5E76\u628A TXT\u3001SRT \u548C\u65F6\u95F4\u6233 JSON \u53D1\u56DE\u6765\u3002");
      return new Response("ok");
    }
    const url = douyinUrl(text);
    if (!url) {
      await notify(env, message.chat.id, "\u8BF7\u53D1\u9001\u6296\u97F3\u89C6\u9891\u5206\u4EAB\u94FE\u63A5\uFF0C\u4E5F\u53EF\u4EE5\u76F4\u63A5\u7C98\u8D34\u6574\u6BB5\u5206\u4EAB\u6587\u5B57\u3002");
      return new Response("ok");
    }
    const response = await fetch(`https://api.github.com/repos/${env.GITHUB_REPOSITORY}/actions/workflows/${env.GITHUB_WORKFLOW}/dispatches`, {
      method: "POST",
      headers: { Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`, Accept: "application/vnd.github+json", "Content-Type": "application/json", "User-Agent": "douyin-transcriber-webhook" },
      body: JSON.stringify({ ref: env.GITHUB_REF, inputs: { url, chat_id: String(message.chat.id), request_id: String(update.update_id) } })
    });
    if (!response.ok) {
      await notify(env, message.chat.id, "CI \u6682\u65F6\u65E0\u6CD5\u542F\u52A8\uFF0C\u8BF7\u7A0D\u540E\u91CD\u53D1\u3002");
      return new Response("Dispatch failed", { status: 502 });
    }
    await notify(env, message.chat.id, "\u5DF2\u4EA4\u7ED9\u8FDC\u7AEF CI\uFF0C\u5B8C\u6210\u540E\u4F1A\u5728\u8FD9\u91CC\u53D1\u56DE\u6587\u5B57\u7A3F\u3002");
    return new Response("ok");
  }
};
function douyinUrl(text) {
  const match = text.match(/(?:https?:\/\/)?(?:(?:www\.|v\.)?douyin\.com|(?:www\.)?iesdouyin\.com)\/[^\s<>"“”\u4e00-\u9fff]+/i);
  if (!match || match.index > 0 && /[a-z0-9./@_-]/i.test(text[match.index - 1])) return null;
  const raw = match[0].replace(/[。，！？；）)】\]》]+$/, "");
  const url = new URL(/^https?:/i.test(raw) ? raw : `https://${raw}`);
  const hosts = ["douyin.com", "www.douyin.com", "v.douyin.com", "iesdouyin.com", "www.iesdouyin.com"];
  if (!hosts.includes(url.hostname) || url.username || url.password || url.port) return null;
  url.hash = "";
  return url.href;
}
__name(douyinUrl, "douyinUrl");
async function notify(env, chat, text) {
  try {
    const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chat, text })
    });
    return response.ok;
  } catch {
    return false;
  }
}
__name(notify, "notify");
export {
  index_default as default,
  douyinUrl
};
//# sourceMappingURL=index.js.map
