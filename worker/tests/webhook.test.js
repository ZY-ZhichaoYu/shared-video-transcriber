import test from 'node:test';
import assert from 'node:assert/strict';
import worker, { douyinUrl } from '../index.js';
const env = { TELEGRAM_WEBHOOK_SECRET: 'test-secret', TELEGRAM_ALLOWED_USER_IDS: '42', GITHUB_REPOSITORY: 'owner/repo', GITHUB_REF: 'feature/test', GITHUB_WORKFLOW: 'transcribe.yml', GITHUB_DISPATCH_TOKEN: 'fake', TELEGRAM_BOT_TOKEN: 'fake' };
function request(body, secret = 'test-secret') {
  return new Request('https://example.test/telegram', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Telegram-Bot-Api-Secret-Token': secret }, body: JSON.stringify(body) });
}
const update = { update_id: 123, message: { from: { id: 42 }, chat: { id: 42, type: 'private' }, text: '复制 https://v.douyin.com/abc/ 打开抖音' } };
test('accepts only independent Douyin links', () => {
  assert.equal(douyinUrl(update.message.text), 'https://v.douyin.com/abc/');
  for (const value of ['https://bilibili.com/video/1', 'https://evildouyin.com/video/1', 'https://evil.test/v.douyin.com/x/']) assert.equal(douyinUrl(value), null);
});
test('rejects invalid webhook secret', async () => { assert.equal((await worker.fetch(request(update, 'wrong'), env)).status, 403); });
test('ignores unauthorized users and groups before making requests', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = () => { throw Error('must not call network'); };
  try {
    const denied = structuredClone(update); denied.message.from.id = 7;
    assert.equal((await worker.fetch(request(denied), env)).status, 200);
    const group = structuredClone(update); group.message.chat.type = 'group';
    assert.equal((await worker.fetch(request(group), env)).status, 200);
  } finally { globalThis.fetch = original; }
});
test('dispatches a workflow with data inputs and reports acceptance', async () => {
  const calls = []; const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => { calls.push({ url, options }); return new Response(null, { status: 204 }); };
  try {
    assert.equal((await worker.fetch(request(update), env)).status, 200);
    assert.equal(calls.length, 2);
    assert.match(calls[0].url, /workflows\/transcribe.yml\/dispatches$/);
    assert.deepEqual(JSON.parse(calls[0].options.body), { ref: 'feature/test', inputs: { url: 'https://v.douyin.com/abc/', chat_id: '42', request_id: '123' } });
  } finally { globalThis.fetch = original; }
});
test('dispatch failure produces an actionable retry response', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async url => new Response(null, { status: url.includes('api.github.com') ? 403 : 200 });
  try { assert.equal((await worker.fetch(request(update), env)).status, 502); } finally { globalThis.fetch = original; }
});
