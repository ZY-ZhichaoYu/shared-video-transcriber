import { spawnSync } from 'node:child_process';
import { appendFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
const env = { ...process.env, INFISICAL_UNIVERSAL_AUTH_CLIENT_ID: process.env.INFISICAL_CLIENT_ID, INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET: process.env.INFISICAL_CLIENT_SECRET };
const domain = env.INFISICAL_API_URL || 'https://app.infisical.com';
function call(args) {
  const result = spawnSync('infisical', [...args, `--domain=${domain}`, '--silent'], { env, encoding: 'utf8' });
  if (result.status || result.error) throw Error('Infisical 读取失败；任务已停止，敏感响应未打印');
  return result.stdout;
}
try {
  env.INFISICAL_TOKEN = call(['login', '--method=universal-auth', '--plain']).trim();
  console.log(`::add-mask::${env.INFISICAL_TOKEN}`);
  const rows = JSON.parse(call(['secrets-manager', 'secrets', 'get', `--projectId=${env.INFISICAL_PROJECT_ID}`, `--env=${env.INFISICAL_ENVIRONMENT || 'dev'}`, `--path=${env.INFISICAL_SECRET_PATH}`, '--output=json', '--expand=false']));
  const names = ['R2_ENDPOINT','R2_BUCKET','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY','PROFILE_ENCRYPTION_KEY','R2_PROFILE_PREFIX','TELEGRAM_BOT_TOKEN','TELEGRAM_ALLOWED_USER_IDS','TS_OAUTH_CLIENT_ID','TS_OAUTH_SECRET','TAILSCALE_TAGS','TAILSCALE_EXIT_NODE','TAILSCALE_EXPECTED_IP'];
  for (const row of rows) {
    if (!names.includes(row.secretKey)) continue;
    console.log(`::add-mask::${row.secretValue}`);
    const delimiter = randomUUID();
    appendFileSync(env.GITHUB_ENV, `${row.secretKey}<<${delimiter}\n${row.secretValue}\n${delimiter}\n`);
  }
} catch (error) { console.error(error.message); process.exitCode = 1; }
