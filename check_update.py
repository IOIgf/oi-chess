# -*- coding: utf-8 -*-
"""启动前检查 GitHub 是否有新 Release。

设计约束（与项目「标准库 + 可离线 + 可复现」的定位一致）：
- 只用 Python 标准库，不写任何文件、不改项目状态、不下载任何东西；
- 离线 / 超时 / API 异常一律静默跳过，退出码恒为 0，绝不阻塞启动；
- 只提示，不自动更新：覆盖文件会破坏发布包可复现性并可能碰到玩家存档；
- 本地版本取自 static/index.html 的 <meta name="oi-chess-release">，
  与发布闸门、浏览器端共用同一个真相源。

可用环境变量：
  OI_CHESS_SKIP_UPDATE=1        完全跳过检查
  OI_CHESS_UPDATE_TIMEOUT=2.5   网络超时秒数
命令行：
  py -3 check_update.py          人类可读输出
  py -3 check_update.py --json   机器可读输出（供自动化/前端复用）
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

R = Path(__file__).resolve().parent
REPO = 'IOIgf/oi-chess'
API = 'https://api.github.com/repos/%s/releases/latest' % REPO
RELEASE_PAGE = 'https://github.com/%s/releases/latest' % REPO

SKIP_ENV = 'OI_CHESS_SKIP_UPDATE'
TIMEOUT_ENV = 'OI_CHESS_UPDATE_TIMEOUT'
DEFAULT_TIMEOUT = 2.5
# index.html 缺失时的兜底值；发布新版本时必须与 index.html 的 meta 一起更新。
FALLBACK_TAG = 'v1.6.1-update-check'

META_RE = re.compile(r'<meta\s+name="oi-chess-release"\s+content="([^"]+)"')


def local_tag(root=R):
    """从 index.html 读本地 Release 版本；读不到则用兜底常量。"""
    try:
        html = (Path(root) / 'static' / 'index.html').read_text('utf-8')
        m = META_RE.search(html)
        if m:
            return m.group(1)
    except (OSError, UnicodeError):
        pass
    return FALLBACK_TAG


def version_key(tag):
    """v1.6.1-update-check -> (1, 6, 1)；只比较前三段数字，忽略构建后缀。"""
    m = re.match(r'v?(\d+)\.(\d+)\.(\d+)', tag or '')
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def has_update(local, remote):
    """远程版本号严格大于本地才算更新。

    同版本号不同构建（例如 v1.6.1-a / v1.6.1-b）不反复提示；本地是开发版
    （比远程还新）也不提示。
    """
    return version_key(remote) > version_key(local)


def fetch_latest(timeout=DEFAULT_TIMEOUT):
    req = urllib.request.Request(API, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'oi-chess-update-check',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def check(root=R, timeout=None, fetch=None):
    """返回状态字典，永不抛异常。

    status: 'update' | 'latest' | 'skipped' | 'offline'
    fetch 参数用于测试注入，避免单测依赖外网。
    """
    local = local_tag(root)
    if os.environ.get(SKIP_ENV) == '1':
        return {'status': 'skipped', 'local': local}
    if timeout is None:
        try:
            timeout = float(os.environ.get(TIMEOUT_ENV, DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT
    try:
        data = (fetch or fetch_latest)(timeout)
        remote = data['tag_name']
        if not isinstance(remote, str) or not remote:
            raise ValueError('bad tag_name')
        assets = data.get('assets') or []
        download = (assets[0].get('browser_download_url') if assets else None) \
            or data.get('html_url') or RELEASE_PAGE
        url = data.get('html_url') or RELEASE_PAGE
        if has_update(local, remote):
            return {'status': 'update', 'local': local, 'remote': remote,
                    'url': url, 'download': download,
                    'name': data.get('name') or remote}
        return {'status': 'latest', 'local': local, 'remote': remote}
    except Exception:
        # 离线、DNS 失败、超时、限流、JSON 损坏、字段缺失：一律静默跳过。
        return {'status': 'offline', 'local': local}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    result = check()
    if '--json' in argv:
        print(json.dumps(result, ensure_ascii=True))
        return 0
    try:
        # Windows 控制台重定向到文件时避免 UnicodeEncodeError 中断启动。
        sys.stdout.reconfigure(errors='replace')
    except (AttributeError, OSError, ValueError):
        pass
    st = result['status']
    if st == 'update':
        print('=' * 56)
        print('  发现新版本：%s（当前 %s）' % (result['remote'], result['local']))
        print('  发布页：%s' % result['url'])
        print('  下载：  %s' % result['download'])
        print('  不会自动更新，请手动下载替换（玩家存档会保留）。')
        print('=' * 56)
    elif st == 'latest':
        print('检查更新：已是最新版本 %s' % result['local'])
    elif st == 'skipped':
        print('检查更新：已跳过（%s=1）' % SKIP_ENV)
    else:
        print('检查更新：跳过（离线或超时，不影响启动）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
