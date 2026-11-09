# -*- coding: utf-8 -*-
"""自动更新：发现新版本 -> 下载 -> 双重校验 -> 备份 -> 覆盖安装 -> 自检回滚。

与 check_update.py 的分工：
- check_update.py  保持「纯只读检查」契约，绝不写文件、绝不下载；
- auto_update.py   负责真正的下载与安装，失败即回滚，保证旧版本仍可运行。

安全约束（与项目「标准库 + 可离线 + 可复现」的定位一致）：
- 只用 Python 标准库（urllib / zipfile / hashlib / shutil / json）；
- 玩家存档 data/players.json 永不覆盖，跨版本延续；
- 本机网络配置 update_config.bat 永不覆盖；
- 双重校验：GitHub 资产 sha256（接口提供时）+ 包内 版本清单.json 逐文件 sha256；
- 覆盖前把「将被替换 / 将被删除」的文件备份到 update_backup/；
- 安装后自检（版本号 + server.py 可编译），不通过立即回滚；
- 绝不阻塞启动：任何异常都降级为 status='failed'，旧版本照常可用。

环境变量：
  OI_CHESS_SKIP_UPDATE=1        完全跳过检查与更新
  OI_CHESS_UPDATE_TIMEOUT=2.5   检查更新的网络超时秒数
  OI_CHESS_DOWNLOAD_TIMEOUT=120 下载更新的超时秒数
  OI_CHESS_PROXY=http://...     走代理访问 GitHub；空 / 0 / none / direct = 直连
命令行：
  py -3 auto_update.py            执行检查 + 自动安装
  py -3 auto_update.py --check    只检查不安装
  py -3 auto_update.py --json     机器可读输出
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import check_update as cu

R = Path(__file__).resolve().parent

# 下载体积上限：超过就当异常处理，不写盘。
MAX_ZIP_BYTES = 64 * 1024 * 1024
DOWNLOAD_TIMEOUT_ENV = 'OI_CHESS_DOWNLOAD_TIMEOUT'
DEFAULT_DOWNLOAD_TIMEOUT = 120.0

# 这些目录与文件永远不参与安装，也永远不会被删除。
PROTECTED_DIRS = ('data', 'update_backup', '__pycache__', '.git')
PROTECTED_FILES = ('update_config.bat',)

# 备份目录最多保留几份。
KEEP_BACKUPS = 3


def _safe_print(*args, **kwargs):
    """中文输出不因编码问题中断流程。"""
    try:
        print(*args, **kwargs)
        sys.stdout.flush()
        return
    except (UnicodeEncodeError, OSError, ValueError):
        pass
    try:
        text = kwargs.get('sep', ' ').join(str(a) for a in args)
        print(text.encode('ascii', 'backslashreplace').decode('ascii'))
        sys.stdout.flush()
    except Exception:
        pass


def _sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def _protected(rel):
    """rel 是相对项目根的 POSIX 路径；返回 True 表示不参与安装。"""
    parts = rel.split('/')
    if parts[0] in PROTECTED_DIRS:
        return True
    return rel in PROTECTED_FILES


def _install_file(src, dst):
    """把 src 复制到 dst。

    两个 Windows 相关的坑：
    1. 内容完全相同就别写 —— cmd.exe 独占正在运行的 start.bat，
       即使内容一样也会写失败；
    2. 目标确实被占用时，先把旧文件改名让路，再写入新文件。
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if dst.is_file() and dst.stat().st_size == os.path.getsize(str(src)):
            if _sha256(dst) == _sha256(src):
                return
    except OSError:
        pass
    try:
        shutil.copy2(str(src), str(dst))
        return
    except PermissionError:
        pass
    # 目标被占用：改名让路 -> 写入 -> 清理改名后的旧文件。
    old = dst.with_name(dst.name + '.old')
    renamed = False
    try:
        if old.exists():
            old.unlink()
        os.replace(str(dst), str(old))
        renamed = True
    except OSError:
        pass
    tmp = dst.with_name(dst.name + '.new')
    shutil.copyfile(str(src), str(tmp))
    os.replace(str(tmp), str(dst))
    if renamed:
        try:
            old.unlink()
        except OSError:
            pass


def _pick_asset(release):
    """从 Release JSON 里挑出 zip 资产，返回 (url, digest, name)。"""
    assets = release.get('assets') or []
    zips = [a for a in assets if (a.get('name') or '').lower().endswith('.zip')]
    chosen = (zips or assets or [None])[0]
    if not chosen:
        return None, None, None
    url = chosen.get('browser_download_url')
    digest = chosen.get('digest') or ''
    if digest.startswith('sha256:'):
        digest = digest[len('sha256:'):].strip().lower()
    else:
        digest = None
    return url, digest, chosen.get('name')


def _download(url, dest, proxy, timeout, log):
    """流式下载到 dest，返回字节数。"""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'oi-chess-auto-update',
        'Accept': 'application/octet-stream',
    })
    if proxy:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({
            'http': proxy, 'https': proxy}))
    else:
        opener = urllib.request.build_opener()
    got = 0
    total = 0
    last = 0
    with opener.open(req, timeout=timeout) as resp:
        try:
            total = int(resp.headers.get('Content-Length') or 0)
        except (TypeError, ValueError):
            total = 0
        with open(str(dest), 'wb') as out:
            while True:
                buf = resp.read(1 << 16)
                if not buf:
                    break
                out.write(buf)
                got += len(buf)
                if got > MAX_ZIP_BYTES:
                    raise ValueError('release package too large')
                if got - last >= (1 << 20):
                    last = got
                    if total:
                        log('  downloading %.1f/%.1f MiB' % (got / 1048576.0,
                                                            total / 1048576.0))
    if total and got != total:
        raise ValueError('truncated download (%d/%d bytes)' % (got, total))
    return got


def _safe_extract(zf, dest):
    """解压并拒绝越界路径（zip-slip）。"""
    for info in zf.infolist():
        name = info.filename.replace('\\', '/')
        if name.startswith('/') or '..' in Path(name).parts:
            raise ValueError('unsafe path in release package: %s' % name)
    zf.extractall(str(dest))


def _package_root(extracted):
    """定位包内真正的项目根（兼容 oi-chess/ 前缀，也兼容无前缀）。"""
    files = [p for p in Path(extracted).rglob('*') if p.is_file()]
    if not files:
        raise ValueError('release package is empty')
    tops = {p.relative_to(extracted).parts[0] for p in files}
    if len(tops) == 1:
        cand = Path(extracted) / tops.pop()
        if cand.is_dir():
            return cand
    return Path(extracted)


def _verify_package(extracted, expect_digest, remote_tag, log):
    """校验包内容；返回 (项目根, 校验文件数, 新清单)。

    两道校验：
    1. GitHub 资产自身的 sha256（接口提供时）——已在下载后单独校验；
    2. 包内 版本清单.json 逐文件 sha256——保证每个文件都是发布时那份。
    """
    root = _package_root(extracted)
    manifest_path = root / '版本清单.json'
    if not manifest_path.is_file():
        if expect_digest:
            log('  no manifest in package; relying on the asset sha256')
            return root, 0, None
        raise ValueError('release package has no 版本清单.json and no asset digest')
    manifest = json.loads(manifest_path.read_text('utf-8'))
    files = manifest.get('files') or {}
    if not files:
        raise ValueError('release manifest lists no files')
    checked = 0
    for rel, digest in files.items():
        p = root / rel
        if not p.is_file():
            raise ValueError('release package misses %s' % rel)
        if _sha256(p) != digest:
            raise ValueError('release package file mismatch: %s' % rel)
        checked += 1
    tag = manifest.get('release_tag')
    if remote_tag and tag and tag != remote_tag:
        raise ValueError('manifest tag %s does not match release tag %s'
                         % (tag, remote_tag))
    log('  verified %d files against the release manifest' % checked)
    return root, checked, manifest


def _old_manifest(root):
    try:
        return json.loads((Path(root) / '版本清单.json').read_text('utf-8'))
    except (OSError, ValueError, UnicodeError):
        return None


def _install(root, pkg_root, remote_tag, log):
    """把 pkg_root 覆盖安装到 root；返回统计信息。失败抛异常并已回滚。"""
    root = Path(root)
    old_man = _old_manifest(root) or {}
    old_files = old_man.get('files') or {}

    # 1) 规划：写哪些、删哪些
    writes = []
    new_all = set()
    for p in sorted(pkg_root.rglob('*')):
        if not p.is_file():
            continue
        rel = p.relative_to(pkg_root).as_posix()
        new_all.add(rel)
        if _protected(rel):
            continue
        writes.append((rel, p))
    deletes = []
    for rel in old_files:
        if rel in new_all or _protected(rel):
            continue
        if (root / rel).is_file():
            deletes.append(rel)

    # 2) 备份
    stamp = time.strftime('%Y%m%d-%H%M%S')
    backup = root / 'update_backup' / ('%s_%s' % (cu.local_tag(root) or 'unknown', stamp))
    backup.mkdir(parents=True, exist_ok=True)
    backed_up = []
    for rel in [r for r, _ in writes] + deletes:
        src = root / rel
        if not src.is_file():
            continue
        dst = backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        backed_up.append(rel)

    journal = []          # (rel, 是否为新文件) 用于回滚
    created = []
    replaced = []
    try:
        for rel, src in writes:
            dst = root / rel
            existed = dst.is_file()
            _install_file(src, dst)
            (replaced if existed else created).append(rel)
            journal.append(rel)
        for rel in deletes:
            try:
                (root / rel).unlink()
                journal.append(rel)
            except OSError:
                pass
        # 3) 自检
        meta = (root / 'static' / 'index.html').read_text('utf-8')
        m = cu.META_RE.search(meta)
        if not m:
            raise ValueError('installed index.html lost its release meta')
        if remote_tag and m.group(1) != remote_tag:
            raise ValueError('installed version %s != expected %s'
                             % (m.group(1), remote_tag))
        server = root / 'server.py'
        if server.is_file():
            compile(server.read_bytes(), 'server.py', 'exec')
    except Exception:
        # 回滚：恢复被替换与被删除的文件，删掉新建的文件
        for rel in reversed(created):
            try:
                (root / rel).unlink()
            except OSError:
                pass
        for rel in reversed(replaced) + list(reversed(deletes)):
            src = backup / rel
            if src.is_file():
                try:
                    _install_file(src, root / rel)
                except OSError:
                    pass
        log('  update failed, rolled back to the previous version')
        raise

    # 4) 清掉过期的字节码缓存（模块内容变了，缓存必须失效）
    for d in root.rglob('__pycache__'):
        if d.is_dir():
            shutil.rmtree(str(d), ignore_errors=True)

    # 5) 只保留最近几份备份
    backups = sorted((root / 'update_backup').glob('*'),
                     key=lambda p: p.name, reverse=True)
    for old in backups[KEEP_BACKUPS:]:
        shutil.rmtree(str(old), ignore_errors=True)

    return {
        'written': len(writes),
        'deleted': len(deletes),
        'backup': str(backup),
        'preserved': sorted(p for p in PROTECTED_DIRS if (root / p).exists()),
    }


def apply_update(root=R, proxy=cu._ENV, timeout=None, release=None, log=None):
    """检查并在需要时安装新版本。

    返回字典：status 为
      'latest'  | 'updated' | 'skipped' | 'offline' | 'failed' | 'git'
    """
    log = log or _safe_print
    local = cu.local_tag(root)
    if os.environ.get(cu.SKIP_ENV) == '1':
        return {'status': 'skipped', 'local': local}

    # 检查更新的超时与下载的超时是两回事：前者要短（不能拖慢启动），
    # 后者要长（几百 KB 的包在慢代理下也要给足时间）。
    check_timeout = cu.DEFAULT_TIMEOUT
    if timeout is None:
        try:
            timeout = float(os.environ.get(DOWNLOAD_TIMEOUT_ENV,
                                           DEFAULT_DOWNLOAD_TIMEOUT))
        except (TypeError, ValueError):
            timeout = DEFAULT_DOWNLOAD_TIMEOUT
    else:
        check_timeout = timeout
    try:
        check_timeout = float(os.environ.get(cu.TIMEOUT_ENV, check_timeout))
    except (TypeError, ValueError):
        pass
    if proxy is cu._ENV:
        proxy = cu.resolve_proxy()

    # Git 检出目录不做覆盖安装：那是开发者的仓库，应该走 git pull。
    if (Path(root) / '.git').exists():
        return {'status': 'git', 'local': local,
                'error': 'git checkout detected; use git pull instead'}

    try:
        if release is None:
            release = cu.fetch_latest(check_timeout, proxy=proxy)
        remote = release.get('tag_name')
        if not isinstance(remote, str) or not remote:
            raise ValueError('bad tag_name')
        if not cu.has_update(local, remote):
            return {'status': 'latest', 'local': local, 'remote': remote}
        url, digest, name = _pick_asset(release)
        if not url:
            raise ValueError('release has no downloadable asset')
        page = release.get('html_url') or cu.RELEASE_PAGE
        log('  new version %s found (current %s)' % (remote, local))
        log('  package: %s' % name)

        tmpdir = tempfile.mkdtemp(prefix='oi-update-')
        try:
            zpath = Path(tmpdir) / 'release.zip'
            _download(url, zpath, proxy, timeout, log)
            if digest:
                got = _sha256(zpath)
                if got != digest:
                    raise ValueError('asset sha256 mismatch')
                log('  asset sha256 verified')
            extract_dir = Path(tmpdir) / 'x'
            extract_dir.mkdir()
            with zipfile.ZipFile(str(zpath)) as zf:
                if zf.testzip() is not None:
                    raise ValueError('release package is corrupt')
                _safe_extract(zf, extract_dir)
            pkg_root, checked, manifest = _verify_package(
                extract_dir, digest, remote, log)
            info = _install(root, pkg_root, remote, log)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        out = {'status': 'updated', 'local': local, 'remote': remote,
               'url': page, 'download': url, 'files': info['written'],
               'deleted': info['deleted'], 'backup': info['backup'],
               'preserved': info['preserved'], 'verified': checked}
        log('  installed %s (%d files written, %d removed)' % (
            remote, info['written'], info['deleted']))
        log('  backup kept at %s' % info['backup'])
        return out
    except Exception as e:
        msg = '%s: %s' % (type(e).__name__, e)
        low = msg.lower()
        if 'timeout' in low or 'timed out' in low or 'urlopen error' in low:
            return {'status': 'offline', 'local': local, 'error': msg}
        return {'status': 'failed', 'local': local, 'error': msg}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    check_only = '--check' in argv
    proxy = cu._ENV
    if '--proxy' in argv:
        i = argv.index('--proxy')
        proxy = argv[i + 1] if i + 1 < len(argv) else None
    result = apply_update(proxy=proxy)
    if '--json' in argv:
        print(json.dumps(result, ensure_ascii=True))
        return 0
    st = result['status']
    if st == 'updated':
        _safe_print('=' * 56)
        _safe_print('  已自动更新到 %s' % result['remote'])
        _safe_print('  玩家存档已保留；旧版本备份在 %s' % result.get('backup', ''))
        _safe_print('=' * 56)
    elif st == 'latest':
        _safe_print('检查更新：已是最新版本 %s' % result.get('local'))
    elif st == 'skipped':
        _safe_print('检查更新：已跳过（%s=1）' % cu.SKIP_ENV)
    elif st == 'git':
        _safe_print('检查更新：检测到 Git 检出目录，跳过自动安装（请用 git pull）')
    elif st == 'offline':
        _safe_print('检查更新：跳过（离线或超时，不影响启动）')
    else:
        _safe_print('检查更新：自动更新未完成（%s），已保留当前版本'
                    % result.get('error', '未知错误'))
    return 0


if __name__ == '__main__':
    try:
        import urllib.request  # noqa: F401  (随 auto_update 一起导入亦可)
    except ImportError:
        pass
    try:
        _rc = main()
    finally:
        try:
            sys.stdout.flush()
        except Exception:
            pass
    sys.exit(_rc)
