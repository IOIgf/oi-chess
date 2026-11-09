"""就绪门控的定向验证：准备期无倒计时，全员点「准备」才开战。

覆盖五条规则：
  1. 准备期不会因超时自动开战（prep_end 恒为 0，直到全员触达）
  2. 部分玩家准备不开战；全员准备后立刻触发
  3. 全员触达后如果有人取消准备，触发被撤回
  4. 已出局（dead）玩家不计入「全员」
  5. prepEndsAt 在等待期间对外保持 0（前端据此显示准备人数）
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as s

checks = []


def ok(cond, label):
    assert cond, label
    checks.append(label)


def make_room():
    r = s.Room('ready-%d' % time.time_ns(), 'A')
    ok(r.add_player('A', 'A')[0], 'host joins')
    ok(r.add_player('B', 'B')[0], 'second player joins')
    r.state = 'prep'
    r.prep_end = 0.0
    return r


# 1. 无倒计时：即使时间流逝，也不会自动开战
r = make_room()
time.sleep(0.2)
r._tick()
ok(r.state == 'prep' and r.prep_end == 0.0,
   'prep phase never auto-starts without every player ready')

# 2. 部分准备不开战
r.toggle_ready('A')
r._tick()
ok(r.state == 'prep' and r.prep_end == 0.0,
   'one ready player does not start the battle')

# 3. 全员准备立刻触发
r.toggle_ready('B')
ok(r.prep_end > 0, 'every player ready arms the immediate start')
r._tick()
ok(r.state == 'battle', 'tick after full readiness enters battle')

# 4. 取消准备撤回触发
r2 = make_room()
r2.toggle_ready('A')
r2.toggle_ready('B')
ok(r2.prep_end > 0, 'both ready arms the start')
r2.toggle_ready('B')          # 取消准备
ok(r2.prep_end == 0.0, 'un-readying one player disarms the start')
r2._tick()
ok(r2.state == 'prep', 'battle does not start after disarm')

# 5. 出局玩家不计入「全员」
r3 = make_room()
r3.players['B']['dead'] = True
r3.toggle_ready('A')
ok(r3.prep_end > 0, 'dead players do not count toward the ready gate')

# 6. 等待期间对外 prepEndsAt 为 0
st = r2._view_full(r2.players['A']['id']) if hasattr(r2, '_view_full') else None
if st is not None:
    ok(st.get('prepEndsAt') == 0, 'prepEndsAt stays 0 while waiting for ready')

print('PASS ready gate: %d checks' % len(checks))
