"""Windows 非中文代码页下启动期中文输出的回归闸门。

复现现场：stdout 为 cp1252 + errors='strict' 且 reconfigure 失效时，
直接 print 中文会抛 UnicodeEncodeError，导致 check_update.py 非零退出、
server.py 根本起不来（v1.7.5 在部分 Windows 机器上的启动崩溃）。
修复后输出层必须自兜底，绝不中断启动，也不得丢失可读信息。
"""
import sys, io
from pathlib import Path
from unittest.mock import patch

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
import check_update as u
import server as s

checks = []


def ok(cond, label):
    assert cond, label
    checks.append(label)


class StrictConsole(io.TextIOBase):
    """模拟英文 Windows 控制台：ANSI=cp1252、strict、reconfigure 不可用。"""
    def __init__(self):
        self.parts = []

    def reconfigure(self, *a, **k):
        raise AttributeError('reconfigure unsupported on this host')

    def write(self, text):
        text.encode('cp1252')  # strict：中文必然 UnicodeEncodeError
        self.parts.append(text)
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return True


ok(hasattr(u, '_safe_print'), 'check_update defines _safe_print')
ok(hasattr(s, '_safe_print'), 'server defines _safe_print')

real_out = sys.stdout

# 1) 正常编码不得降级，中文保持可读
buf = io.StringIO()
sys.stdout = buf
try:
    u._safe_print('检查更新：已是最新版本 v1.7.6')
finally:
    sys.stdout = real_out
ok('检查更新：已是最新版本' in buf.getvalue(), 'normal encoding keeps readable Chinese')

# 2) 严格编码下 check_update.main() 必须返回 0 且不抛异常
fake = StrictConsole()
sys.stdout = fake
try:
    with patch.object(u, 'check', return_value={
            'status': 'offline', 'local': 'v1.7.6',
            'proxy': 'http://127.0.0.1:7890'}):
        rc = u.main([])
finally:
    sys.stdout = real_out
out = ''.join(fake.parts)
ok(rc == 0, 'check_update.main returns 0 under strict console encoding')
ok('http://127.0.0.1:7890' in out, 'proxy hint survives ASCII fallback')
ok(all(ord(c) < 128 for c in out), 'check_update fallback output is pure ASCII')

# 3) 严格编码下 server 启动期中文输出不抛异常
fake2 = StrictConsole()
sys.stdout = fake2
try:
    s._safe_print('已加载 3 名玩家档案')
    s._safe_print('!! 缺少静态文件:', ['index.html'])
finally:
    sys.stdout = real_out
out2 = ''.join(fake2.parts)
ok(all(ord(c) < 128 for c in out2), 'server fallback output is pure ASCII')
ok('\\u5df2\\u52a0\\u8f7d' in out2, 'server Chinese is escaped, not dropped')
ok("['index.html']" in out2, 'server multi-arg output is preserved')

# 4) 启动器：ASCII-only + 钉住子进程编码
bat = (R / 'start.bat').read_bytes()
ok(bat.isascii(), 'start.bat stays ASCII-only')
ok(b'PYTHONIOENCODING=utf-8:replace' in bat, 'start.bat pins UTF-8 for child processes')
ok(b'chcp 65001' not in bat, 'start.bat no longer forces code page 65001')
ok(hasattr(u, '_flush_quietly') and hasattr(s, '_flush_quietly'),
   'both modules define _flush_quietly')

# 6) 解释器退出期 flush：stdout 句柄提前关闭时不得出现 'Exception ignored in'
import subprocess
_bare = 'import sys, os\nprint("\u4e2d\u6587")\nos.close(1)\n'
_p0 = subprocess.run([sys.executable, '-c', _bare], capture_output=True)
ok(b'Exception ignored in' in _p0.stderr,
   'control: bare print does reproduce the exit-time flush warning')
_guarded = (
    'import sys, os\n'
    'sys.path.insert(0, %r)\n'
    'import check_update as u\n'
    'u._safe_print("\u5df2\u52a0\u8f7d 3 \u540d\u73a9\u5bb6\u6863\u6848")\n'
    'os.close(1)\n'
) % str(R)
_p1 = subprocess.run([sys.executable, '-c', _guarded], capture_output=True)
ok(b'Exception ignored in' not in _p1.stderr,
   'guarded output produces no exit-time flush warning')
ok(_p1.returncode == 0, 'guarded process still exits 0')

# 5) 标准流 reconfigure 的兜底必须捕获全部异常（源码级）
src_u = (R / 'check_update.py').read_text('utf-8')
src_s = (R / 'server.py').read_text('utf-8')
ok('except Exception:' in src_u and '_stream.reconfigure' in src_u,
   'check_update reconfigure is fully guarded')
ok('except Exception:' in src_s and 'stream.reconfigure' in src_s,
   'server reconfigure is fully guarded')

print('PASS console encoding: %d checks, strict cp1252 fallback / no startup crash / ASCII-only launcher'
      % len(checks))
