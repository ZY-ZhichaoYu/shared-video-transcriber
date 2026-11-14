import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
process.chdir(new URL('..', import.meta.url).pathname);
try { process.loadEnvFile('.env'); } catch { console.error('请先复制 .env.example 为 .env，并填写 Infisical 配置'); process.exit(1); }
function command(name, args, capture = false, env = process.env) {
  const result = spawnSync(name, args, { env, encoding: 'utf8', stdio: capture ? 'pipe' : 'inherit' });
  if (result.status || result.error) throw Error(`${name} 操作失败`);
  return result.stdout?.trim();
}
try {
  const env = { ...process.env };
  if (env.INFISICAL_PROJECT_ID) {
    env.INFISICAL_UNIVERSAL_AUTH_CLIENT_ID = env.INFISICAL_CLIENT_ID;
    env.INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET = env.INFISICAL_CLIENT_SECRET;
    env.INFISICAL_TOKEN = command('infisical', ['login', '--method=universal-auth', '--plain', '--silent'], true, env);
    const rows = JSON.parse(command('infisical', ['secrets-manager', 'secrets', 'get', '--projectId='+env.INFISICAL_PROJECT_ID, '--env=dev', '--path='+env.INFISICAL_SECRET_PATH, '--output=json', '--expand=false', '--silent'], true, env));
    for (const row of rows) if (!env[row.secretKey]) env[row.secretKey] = row.secretValue;
  }
  for (const key of ['R2_ENDPOINT','R2_BUCKET','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY','PROFILE_ENCRYPTION_KEY']) {
    if (!env[key]) throw Error(`缺少 ${key}，请在 Infisical 本应用目录填写`);
  }
  const branch = command('git', ['branch', '--show-current'], true);
  const run = command('gh', ['run','list','--repo','C0verSnow/shared-video-transcriber','--workflow','tests.yml','--branch',branch,'--event','push','--status','success','--limit','1','--json','databaseId','--jq','.[0].databaseId'], true);
  if (!run || run === 'null') throw Error('当前分支还没有构建成功的远端镜像');
  const directory = resolve('.runtime/image/'+run);
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  if (!existsSync(directory+'/login-image.tar.gz')) command('gh', ['run','download',run,'--repo','C0verSnow/shared-video-transcriber','--name','docker-login-image','--dir',directory]);
  command('docker', ['load','--input',directory+'/login-image.tar.gz']);
  mkdirSync('.runtime/docker', { recursive: true, mode: 0o700 });
  command('docker', ['compose','run','--rm','--no-build','--pull','never','--service-ports','login', ...process.argv.slice(2)], false, env);
} catch (error) { console.error(error.message); process.exitCode = 1; }
