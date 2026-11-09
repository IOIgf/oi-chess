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
  OI_CHESS_PROXY=http://...     走代理访问 GitHub；空 / 0 / none / direct = 直连
命令行：
  py -3 check_update.py          人类可读输出
  py -3 check_update.py --json   机器可读输出（供自动化/前端复用）
  py -3 check_update.py --proxy URL   本次检查强制走指定代理
代理选择：start.bat 首次启动会询问一次并保存到 update_config.bat，
之后每次启动自动读取；重新选择请运行 start.bat setup 或直接删除该文件。
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
PROXY_ENV = 'OI_CHESS_PROXY'
DEFAULT_TIMEOUT = 2.5
# index.html 缺失时的兜底值；发布新版本时必须与 index.html 的 meta 一起更新。
FALLBACK_TAG = 'v1.7.7-stdout-flush'
# 这些取值（忽略大小写）表示「直连，不走代理」。
PROXY_OFF = ('', '0', 'no', 'none', 'direct', 'off')
# check(proxy=...) 的哨兵：None 表示显式直连，_ENV 表示读环境变量。
_ENV = object()

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
    """v1.7.0-bonds-skills -> (1, 7, 0)；只比较前三段数字，忽略构建后缀。"""
    m = re.match(r'v?(\d+)\.(\d+)\.(\d+)', tag or '')
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def has_update(local, remote):
    """远程版本号严格大于本地才算更新。

    同版本号不同构建（例如 v1.6.1-a / v1.6.1-b）不反复提示；本地是开发版
    （比远程还新）也不提示。
    """
    return version_key(remote) > version_key(local)


def resolve_proxy(raw=None):
    """OI_CHESS_PROXY 取值 -> 代理 URL 或 None（直连）。

    None 参数表示读环境变量；空 / 0 / no / none / direct / off 一律直连。
    """
    if raw is None:
        raw = os.environ.get(PROXY_ENV, '')
    raw = (raw or '').strip()
    if raw.lower() in PROXY_OFF:
        return None
    return raw or None


def fetch_latest(timeout=DEFAULT_TIMEOUT, proxy=None):
    req = urllib.request.Request(API, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'oi-chess-update-check',
    })
    if proxy:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({
            'http': proxy, 'https': proxy}))
        resp = opener.open(req, timeout=timeout)
    else:
        resp = urllib.request.urlopen(req, timeout=timeout)
    with resp:
        return json.load(resp)


def check(root=R, timeout=None, fetch=None, proxy=_ENV):
    """返回状态字典，永不抛异常。

    status: 'update' | 'latest' | 'skipped' | 'offline'
    fetch 参数用于测试注入，避免单测依赖外网。
    proxy 为 None 表示显式直连；不传则读 OI_CHESS_PROXY。
    """
    local = local_tag(root)
    if os.environ.get(SKIP_ENV) == '1':
        return {'status': 'skipped', 'local': local}
    if timeout is None:
        try:
            timeout = float(os.environ.get(TIMEOUT_ENV, DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT
    if proxy is _ENV:
        proxy = resolve_proxy()
    try:
        if fetch is None:
            def fetch(t, _proxy=proxy):
                return fetch_latest(t, proxy=_proxy)
        data = fetch(timeout)
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
                    'name': data.get('name') or remote, 'proxy': proxy}
        return {'status': 'latest', 'local': local, 'remote': remote,
                'proxy': proxy}
    except Exception:
        # 离线、DNS 失败、超时、限流、JSON 损坏、字段缺失：一律静默跳过。
        return {'status': 'offline', 'local': local, 'proxy': proxy}


def _flush_quietly():
    """清空标准流缓冲并吞掉异常。

    解释器退出时会自动 flush stdout/stderr；若缓冲区里还有中文输出而底层
    句柄已被宿主 / 管道提前关闭，会打印
    'Exception ignored in: <_io.TextIOWrapper ...>'，窗口看起来像卡住。
    提前把缓冲清空，退出期的自动 flush 就无事可做。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass


def _safe_print(*args, **kwargs):
    """中文输出绝不中断启动：编码失败降级成 ASCII 转义文本，且立即 flush。

    非中文代码页的 Windows 控制台（cp1252 / cp437）可能无法编码中文；
    若输出只留在缓冲区，解释器退出时的自动 flush 还会在 stdout 句柄被
    宿主关闭时抛 'Exception ignored in: <_io.TextIOWrapper ...>'。
    本脚本契约是「退出码恒为 0，绝不阻塞启动」，两层都必须兜住。
    """
    try:
        print(*args, **kwargs)
        _flush_quietly()
        return
    except (UnicodeEncodeError, OSError, ValueError):
        pass
    try:
        text = kwargs.get('sep', ' ').join(str(a) for a in args)
        print(text.encode('ascii', 'backslashreplace').decode('ascii'))
        _flush_quietly()
    except Exception:
        pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    proxy = _ENV
    if '--proxy' in argv:
        i = argv.index('--proxy')
        # --proxy 后面没有值时视为显式直连，避免误用环境变量。
        proxy = argv[i + 1] if i + 1 < len(argv) else None
    result = check(proxy=proxy)
    if '--json' in argv:
        _safe_print(json.dumps(result, ensure_ascii=True))
        return 0
    for _stream in (sys.stdout, sys.stderr):
        try:
            # 非中文代码页的 Windows 控制台默认编码无法表示中文，统一切 UTF-8；
            # 某些宿主会替换标准流导致 reconfigure 抛各类异常，一律忽略。
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    st = result['status']
    if st == 'update':
        _safe_print('=' * 56)
        _safe_print('  发现新版本：%s（当前 %s）' % (result['remote'], result['local']))
        _safe_print('  发布页：%s' % result['url'])
        _safe_print('  下载：  %s' % result['download'])
        _safe_print('  不会自动更新，请手动下载替换（玩家存档会保留）。')
        _safe_print('=' * 56)
    elif st == 'latest':
        _safe_print('检查更新：已是最新版本 %s' % result['local'])
    elif st == 'skipped':
        _safe_print('检查更新：已跳过（%s=1）' % SKIP_ENV)
    else:
        if result.get('proxy'):
            _safe_print('检查更新：跳过（代理 %s 连接失败或超时，不影响启动）'
                  % result['proxy'])
        else:
            _safe_print('检查更新：跳过（离线或超时，不影响启动）')
            _safe_print('提示：GitHub 连不上时可运行 start.bat setup 选择代理，'
                  '或 set %s=http://127.0.0.1:7890' % PROXY_ENV)
    return 0


if __name__ == '__main__':
    try:
        _rc = main()
    finally:
        _flush_quietly()
    sys.exit(_rc)
