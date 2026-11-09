# -*- coding: utf-8 -*-
"""自动更新：下载校验、覆盖安装、存档保留、失败回滚。

不访问外网：所有网络结果通过参数注入（release=... / _download 替换）。
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
import check_update as cu
import auto_update as au

checks = []


def ok(cond, label):
    assert cond, label
    checks.append(label)


def make_pkg(root, tag, extra=None):
    """构造一个模拟的发布包目录，返回 (root, manifest)。"""
    root = Path(root)
    (root / 'static').mkdir(parents=True, exist_ok=True)
    (root / 'server.py').write_text(
        '# -*- coding: utf-8 -*-\nTAG = %r\n' % tag, 'utf-8')
    (root / 'static' / 'index.html').write_text(
        '<meta name="oi-chess-release" content="%s">\n' % tag, 'utf-8')
    (root / 'static' / 'style.css').write_text('body{}\n', 'utf-8')
    files = {}
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name != '版本清单.json':
            files[p.relative_to(root).as_posix()] = hashlib.sha256(
                p.read_bytes()).hexdigest()
    manifest = {'release_tag': tag, 'files': files}
    (root / '版本清单.json').write_text(
        json.dumps(manifest, ensure_ascii=False), 'utf-8')
    return root, manifest


def zip_pkg(pkg_root, dest):
    with zipfile.ZipFile(str(dest), 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(Path(pkg_root).rglob('*')):
            if p.is_file():
                z.write(str(p), Path('oi-chess') / p.relative_to(pkg_root))
    return dest


# ---- 受保护的路径 ----
ok(au._protected('data/players.json'), 'player save is protected')
ok(au._protected('data'), 'the data dir is protected')
ok(au._protected('update_config.bat'), 'the local proxy config is protected')
ok(au._protected('__pycache__/x.pyc'), 'bytecode cache is protected')
ok(not au._protected('server.py'), 'server.py is installable')
ok(not au._protected('static/index.html'), 'static files are installable')

# ---- 资产挑选：优先 zip，并解析 digest ----
rel = {'tag_name': 'v9.9.9', 'html_url': 'https://example/r',
       'assets': [
           {'name': 'notes.txt', 'browser_download_url': 'https://example/n'},
           {'name': 'pkg.zip', 'browser_download_url': 'https://example/z.zip',
            'digest': 'sha256:ABCDEF'},
       ]}
url, digest, name = au._pick_asset(rel)
ok(url == 'https://example/z.zip' and name == 'pkg.zip',
   'the zip asset is preferred over other assets')
ok(digest == 'abcdef', 'the sha256 digest is parsed and lower-cased')
ok(au._pick_asset({'assets': []})[0] is None, 'no assets yields no url')

# ---- 空包必须报错，不能当成合法包 ----
try:
    au._package_root(Path(tempfile.mkdtemp()))
    ok(False, 'an empty package must be rejected')
except ValueError:
    ok(True, 'an empty package is rejected')

with tempfile.TemporaryDirectory() as td:
    bad = Path(td) / 'bad.zip'
    with zipfile.ZipFile(str(bad), 'w') as z:
        z.writestr('../escape.txt', 'x')
    try:
        with zipfile.ZipFile(str(bad)) as zf:
            au._safe_extract(zf, Path(td) / 'out')
        ok(False, 'zip-slip must be rejected')
    except ValueError:
        ok(True, 'zip-slip path traversal is rejected')

# ---- 主流程：安装新版本，存档保留 ----
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / 'app'
    old, old_man = make_pkg(root, 'v1.0.0')
    (root / 'data').mkdir()
    (root / 'data' / 'players.json').write_text('{"p":1}', 'utf-8')
    (root / 'update_config.bat').write_text('set "OI_CHESS_PROXY=x"', 'utf-8')
    (root / 'stale.py').write_text('# old\n', 'utf-8')
    old_man['files']['stale.py'] = hashlib.sha256(b'# old\n').hexdigest()
    (root / '版本清单.json').write_text(json.dumps(old_man), 'utf-8')

    pkg, man = make_pkg(Path(td) / 'pkg', 'v2.0.0')
    zpath = zip_pkg(pkg, Path(td) / 'rel.zip')
    sha = hashlib.sha256(Path(zpath).read_bytes()).hexdigest()

    release = {'tag_name': 'v2.0.0', 'html_url': 'https://example/r',
               'assets': [{'name': 'pkg.zip',
                           'browser_download_url': 'file://' + str(zpath),
                           'digest': 'sha256:' + sha}]}

    def fake_download(url, dest, proxy, timeout, log):
        shutil.copyfile(str(zpath), str(dest))
        return dest.stat().st_size

    orig_dl = au._download
    au._download = fake_download
    try:
        res = au.apply_update(root=root, proxy=None, release=release,
                              log=lambda *a: None)
    finally:
        au._download = orig_dl

    ok(res['status'] == 'updated', 'a newer release is installed: %r' % res)
    ok(cu.local_tag(root) == 'v2.0.0', 'the installed version is the new tag')
    ok((root / 'server.py').read_text('utf-8').find('v2.0.0') >= 0,
       'server.py was replaced by the new one')
    ok((root / 'data' / 'players.json').read_text('utf-8') == '{"p":1}',
       'the player save survives the update')
    ok((root / 'update_config.bat').read_text('utf-8').find('OI_CHESS_PROXY') >= 0,
       'the local proxy config survives the update')
    ok(not (root / 'stale.py').exists(),
       'files dropped by the new release are removed')
    ok((root / 'update_backup').is_dir(), 'a backup of the old version is kept')
    ok(res['verified'] >= 3, 'every package file was verified against the manifest')

# ---- 已是最新：不下载不改动 ----
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / 'app'
    make_pkg(root, 'v1.0.0')
    marker = root / 'server.py'
    before = marker.stat().st_mtime_ns

    def must_not_download(*a, **kw):
        raise AssertionError('must not download when already up to date')

    orig = au._download
    au._download = must_not_download
    try:
        res = au.apply_update(root=root, proxy=None,
                              release={'tag_name': 'v1.0.0', 'assets': []},
                              log=lambda *a: None)
    finally:
        au._download = orig
    ok(res['status'] == 'latest', 'the same version reports latest')
    ok(marker.stat().st_mtime_ns == before, 'nothing was touched when up to date')

# ---- 校验失败：拒绝安装并保留旧版本 ----
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / 'app'
    make_pkg(root, 'v1.0.0')
    (root / 'data').mkdir()
    (root / 'data' / 'players.json').write_text('{"p":1}', 'utf-8')
    pkg, _ = make_pkg(Path(td) / 'pkg', 'v2.0.0')
    zpath = zip_pkg(pkg, Path(td) / 'rel.zip')

    # 篡改包内一个文件：清单里的 sha256 就不再匹配
    tampered = Path(td) / 'tampered.zip'
    with zipfile.ZipFile(str(zpath)) as src, \
            zipfile.ZipFile(str(tampered), 'w', zipfile.ZIP_DEFLATED) as out:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith('static/style.css'):
                data = b'body{evil}\n'
            out.writestr(info, data)
    zpath = tampered

    release = {'tag_name': 'v2.0.0', 'assets': [{
        'name': 'pkg.zip', 'browser_download_url': 'file://' + str(zpath)}]}

    orig = au._download
    au._download = lambda url, dest, proxy, timeout, log: shutil.copyfile(
        str(zpath), str(dest))
    try:
        res = au.apply_update(root=root, proxy=None, release=release,
                              log=lambda *a: None)
    finally:
        au._download = orig
    ok(res['status'] == 'failed', 'a tampered package is rejected')
    ok(cu.local_tag(root) == 'v1.0.0', 'the old version stays installed')
    ok((root / 'data' / 'players.json').is_file(), 'the save is untouched')
    ok('mismatch' in res['error'], 'the mismatch is reported: %s' % res['error'])

# ---- 安装中途失败：回滚到旧版本 ----
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / 'app'
    make_pkg(root, 'v1.0.0')
    (root / 'data').mkdir()
    (root / 'data' / 'players.json').write_text('{"p":1}', 'utf-8')
    pkg, _ = make_pkg(Path(td) / 'pkg', 'v2.0.0')
    zpath = zip_pkg(pkg, Path(td) / 'rel.zip')
    release = {'tag_name': 'v2.0.0', 'assets': [{
        'name': 'pkg.zip', 'browser_download_url': 'file://' + str(zpath)}]}

    orig_install = au._install_file
    state = {'n': 0}

    def flaky(src, dst):
        state['n'] += 1
        if state['n'] == 2:
            raise OSError('disk full (simulated)')
        return orig_install(src, dst)

    orig_dl = au._download
    au._download = lambda url, dest, proxy, timeout, log: shutil.copyfile(
        str(zpath), str(dest))
    au._install_file = flaky
    try:
        res = au.apply_update(root=root, proxy=None, release=release,
                              log=lambda *a: None)
    finally:
        au._install_file = orig_install
        au._download = orig_dl
    ok(res['status'] == 'failed', 'a failed install reports failure')
    ok(cu.local_tag(root) == 'v1.0.0', 'the old version is restored')
    ok('TAG = ' in (root / 'server.py').read_text('utf-8'),
       'the old server.py is restored')

# ---- Git 检出目录：拒绝覆盖安装 ----
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / 'app'
    make_pkg(root, 'v1.0.0')
    (root / '.git').mkdir()
    res = au.apply_update(root=root, proxy=None,
                          release={'tag_name': 'v9.9.9', 'assets': []},
                          log=lambda *a: None)
    ok(res['status'] == 'git', 'a git checkout is never overwritten')
    ok(cu.local_tag(root) == 'v1.0.0', 'the git checkout stays untouched')

# ---- 跳过开关 ----
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / 'app'
    make_pkg(root, 'v1.0.0')
    env = dict(os.environ)
    env[cu.SKIP_ENV] = '1'
    old_env = os.environ.get(cu.SKIP_ENV)
    os.environ[cu.SKIP_ENV] = '1'
    try:
        res = au.apply_update(root=root, proxy=None,
                              release={'tag_name': 'v9.9.9', 'assets': []},
                              log=lambda *a: None)
    finally:
        if old_env is None:
            os.environ.pop(cu.SKIP_ENV, None)
        else:
            os.environ[cu.SKIP_ENV] = old_env
    ok(res['status'] == 'skipped', 'OI_CHESS_SKIP_UPDATE=1 skips everything')

# ---- 启动器：每次都问代理 + 先更新后起服务 ----
bat = (R / 'start.bat').read_bytes()
ok(bat.isascii(), 'start.bat stays ASCII-only')
s = bat.decode('ascii')
ok(s.index('auto_update.py') < s.index('server.py'),
   'the auto update runs before the server starts')
ok(s.count('auto_update.py') == 2, 'both py and python branches auto update')
ok('askproxy' in s, 'the proxy question has its own label')
ok('OI_CHESS_PROXY_MODE' in s, 'the saved choice records direct vs proxy')
ok(s.count('choice /c') >= 2, 'the proxy menu is offered')
ok('reuse last choice' in s, 'the menu offers reusing the last choice')
# 关键回归：不能因为 update_config.bat 存在就跳过询问。
guard = 'if exist update_config.bat (\n  call update_config.bat\n  goto runcheck\n)'
ok(guard not in s, 'an existing config no longer skips the proxy question')
ok(s.index('update_config.bat') < s.index(':askproxy'),
   'the saved config is only read to show the default')

# ---- 服务端 /api/update 端点（伪 Handler，无需起服务） ----
sys.path.insert(0, str(R))
import server as srv


class FakeHandler:
    def __init__(self, data):
        self.data = data
        self.result = None
        self.status = None

    def _read_json(self):
        return self.data

    def _json(self, obj, status=200):
        self.result = obj
        self.status = status
        return obj


with srv.UPDATE_LOCK:
    srv.UPDATE_STATE.update({'busy': False, 'status': 'idle', 'message': '',
                             'error': '', 'remote': '', 'backup': ''})

h = FakeHandler({'action': 'status'})
srv.Handler._api_update(h, h.data)
ok(h.status == 200 and h.result.get('status') == 'idle',
   '/api/update status reports idle when untouched')

h = FakeHandler({'action': 'bogus'})
srv.Handler._api_update(h, h.data)
ok(h.status == 400, 'unknown update action is rejected')

# apply：Git 检出目录（本仓库就是）→ 后台任务立即结束并记录 git 状态
h = FakeHandler({'action': 'apply'})
srv.Handler._api_update(h, h.data)
ok(h.status == 200 and h.result.get('status') == 'running',
   'apply starts a background update task')
h2 = FakeHandler({'action': 'apply'})
srv.Handler._api_update(h2, h2.data)
# 任务线程刚启动还没结束：并发 apply 必须被 409 挡住（若恰好跑完则重新开始也合法）
ok(h2.status in (200, 409), 'a concurrent apply is rate-limited or restarted')
for _ in range(50):
    with srv.UPDATE_LOCK:
        if not srv.UPDATE_STATE.get('busy'):
            break
    time.sleep(0.1)
with srv.UPDATE_LOCK:
    st = srv.UPDATE_STATE['status']
ok(st in ('git', 'latest', 'updated', 'failed', 'offline'),
   'the background task finished with a terminal status: %s' % st)

# busy 标志必须复位，否则后续更新永远 409
with srv.UPDATE_LOCK:
    ok(srv.UPDATE_STATE.get('busy') is False, 'the busy flag is reset afterwards')

# ---- 只用标准库 ----
src = (R / 'auto_update.py').read_text('utf-8')
ok('import requests' not in src and 'urllib.request' in src,
   'auto_update.py uses only the standard library')
ok('import check_update' in src, 'auto_update.py reuses the single source of truth')

print('PASS auto update:', len(checks), 'checks,',
      'verify / install / save preserved / rollback / git guard / launcher order')
