"""启动前检查更新：版本比较、跳过开关、异常降级、启动顺序与版本一致性。

不访问外网：所有网络结果通过 check(fetch=...) 注入。
"""
import sys, json, io, os, subprocess
from pathlib import Path
from unittest.mock import patch

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
import check_update as u

checks = []


def ok(cond, label):
    assert cond, label
    checks.append(label)


# ---- 版本号解析与比较 ----
ok(u.version_key('v1.6.1-update-check') == (1, 6, 1), 'version_key parses semver prefix')
ok(u.version_key('v2.0.0') == (2, 0, 0), 'version_key plain tag')
ok(u.version_key('garbage') == (0, 0, 0), 'version_key tolerates garbage')
ok(u.has_update('v1.6.0-cards-50-1', 'v1.6.1-update-check'), 'newer remote is an update')
ok(not u.has_update('v1.6.1-update-check', 'v1.6.0-cards-50-1'), 'older remote is not an update')
ok(not u.has_update('v1.6.1-a', 'v1.6.1-b'), 'same version different build is not an update')
ok(not u.has_update('v1.6.1', 'v1.6.1'), 'equal tags are not an update')
ok(u.has_update('', 'v0.0.1'), 'empty local tag still detects an update')

# ---- 本地版本单一真相源 ----
html = (R / 'static' / 'index.html').read_text('utf-8')
m = u.META_RE.search(html)
ok(m is not None, 'index.html carries oi-chess-release meta')
tag = m.group(1)
ok(u.local_tag(R) == tag, 'local_tag reads index.html meta')
ok(u.FALLBACK_TAG == tag, 'fallback constant matches index.html meta')
ok(u.local_tag(R / 'nonexistent') == u.FALLBACK_TAG, 'missing index.html falls back safely')

# ---- 正常路径 ----
def newer(timeout):
    return {'tag_name': 'v9.9.9', 'html_url': 'https://example/release',
            'assets': [{'browser_download_url': 'https://example/pkg.zip'}],
            'name': 'v9.9.9 big'}

r = u.check(root=R, timeout=1, fetch=newer)
ok(r['status'] == 'update' and r['remote'] == 'v9.9.9', 'update status for newer release')
ok(r['download'] == 'https://example/pkg.zip' and r['url'] == 'https://example/release',
   'update carries release page and asset link')
ok(r['local'] == tag, 'update reports local tag')

r = u.check(root=R, timeout=1, fetch=lambda t: {'tag_name': tag, 'html_url': 'x'})
ok(r['status'] == 'latest', 'matching tag reports latest')
r = u.check(root=R, timeout=1, fetch=lambda t: {'tag_name': 'v1.0.0', 'html_url': 'x'})
ok(r['status'] == 'latest', 'local dev build ahead of remote reports latest')
r = u.check(root=R, timeout=1, fetch=lambda t: {'tag_name': 'v9.9.9'})
ok(r['status'] == 'update' and r['url'] == u.RELEASE_PAGE,
   'missing html_url falls back to releases/latest')

# ---- 异常一律静默降级，绝不抛错 ----
for exc in [OSError('offline'), TimeoutError('slow'), ValueError('bad json'),
            KeyError('tag_name'), RuntimeError('whatever')]:
    def boom(t, e=exc):
        raise e
    ok(u.check(root=R, timeout=1, fetch=boom)['status'] == 'offline',
       'network/parse error degrades to offline: %s' % type(exc).__name__)
for bad in [{}, {'tag_name': ''}, {'tag_name': 123}, {'tag_name': None}]:
    ok(u.check(root=R, timeout=1, fetch=lambda t, b=bad: b)['status'] == 'offline',
       'malformed payload degrades to offline: %r' % bad)

# ---- 跳过开关 ----
with patch.dict(os.environ, {u.SKIP_ENV: '1'}):
    def forbidden(t):
        raise AssertionError('fetch must not be called when skipped')
    ok(u.check(root=R, timeout=1, fetch=forbidden)['status'] == 'skipped',
       'OI_CHESS_SKIP_UPDATE=1 skips without network')

# ---- 超时取值：显式参数 / 环境变量 / 非法值兜底 ----
seen = []
def capture(t):
    seen.append(t)
    return {'tag_name': tag, 'html_url': 'x'}

u.check(root=R, timeout=7, fetch=capture)
ok(seen == [7], 'explicit timeout is passed through')
with patch.dict(os.environ, {u.TIMEOUT_ENV: '3.5'}):
    seen.clear()
    u.check(root=R, fetch=capture)
    ok(seen == [3.5], 'timeout env is honoured')
with patch.dict(os.environ, {u.TIMEOUT_ENV: 'not-a-number'}):
    seen.clear()
    u.check(root=R, fetch=capture)
    ok(seen == [u.DEFAULT_TIMEOUT], 'invalid timeout env falls back to default')

# ---- CLI --json：合法 JSON、退出码 0、不联网 ----
env = dict(os.environ, **{u.SKIP_ENV: '1'})
out = subprocess.run([sys.executable, str(R / 'check_update.py'), '--json'],
                     cwd=R, capture_output=True, text=True, timeout=30, env=env)
ok(out.returncode == 0, '--json exits 0')
doc = json.loads(out.stdout.strip().splitlines()[-1])
ok(doc['status'] == 'skipped', '--json reports skipped status')

# 人类可读输出：有更新时给出下载链接，且 main 恒返回 0
fake = {'status': 'update', 'local': 'v1.0.0', 'remote': 'v2.0.0',
        'url': 'https://example/r', 'download': 'https://example/z.zip', 'name': 'v2'}
with patch.object(u, 'check', return_value=fake):
    buf = io.StringIO()
    with patch('sys.stdout', buf):
        rc = u.main([])
    text = buf.getvalue()
ok(rc == 0 and '发现新版本' in text and 'https://example/z.zip' in text,
   'human-readable output shows version and download link')

# ---- 启动器：先检查再起服务，且保持 ASCII-only ----
bat = (R / 'start.bat').read_bytes()
ok(bat.isascii(), 'start.bat stays ASCII-only')
s = bat.decode('ascii')
ok(s.index('check_update.py') < s.index('server.py'),
   'update check runs before the server starts')
ok(s.count('check_update.py') == 2, 'both py and python branches check for updates')
ok((R / 'check_update.py').is_file(), 'check_update.py ships with the project')

# ---- 发布闸门与清单同步 ----
manifest = json.loads((R / '版本清单.json').read_text('utf-8'))
ok(manifest.get('release_tag') == tag, 'manifest release_tag matches index.html meta')
src = (R / 'check_update.py').read_text('utf-8')
ok('import requests' not in src and 'urllib.request' in src,
   'check_update.py uses only the standard library')

print('PASS update check:', len(checks), 'checks,',
      'version compare / skip / offline fallback / launcher order / single source')
