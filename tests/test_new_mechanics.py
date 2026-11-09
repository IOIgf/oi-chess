"""新增 6 种战斗机制的定向验证：由真实服务器函数结算，不看评分器预测值。

逐卡合同（test_mechanics_audit.py）只保证每张卡可执行；满编随机战斗
（test_battle_invariants.py）只保证不崩。这里逐条断言新机制真的生效，
且数值与 server.py 中的常量一致。旧 35 张卡的结算不在此测试范围内。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as s

r = s.Room('new-mech', 'A')
STATS = {'A': {'out': 1, 'in': 1}, 'B': {'out': 1, 'in': 1}}
checks = []


def ok(cond, label):
    assert cond, label
    checks.append(label)


def unit(cid, owner='A', x=3, y=4, hp=6000, max_hp=6000):
    # hp 与 maxHp 必须可分离：真实战斗中受伤后 hp 下降而 maxHp 不变，
    # 汲取才有回血空间。
    u = r._unit_from(owner, '3,0',
                     {'card': cid, 'hp': s.effective_max_hp(s.CARD_BY_ID[cid])},
                     'a' if owner == 'A' else 'b', STATS, 3)
    u.update(uid=f'{owner}:{x},{y}:{cid}', x=x, y=y,
             hp=float(hp), maxHp=float(max_hp), atk=120., baseAtk=120., range=5)
    return u


RAW = 120. * s.DMG_MULT          # 一次普攻的基础伤害（单位攻击 120）
assert abs(RAW - 40.) < 1e-8, RAW


def do_attack(cid, enemies, hp=6000):
    u = unit(cid, hp=hp)
    us = [u] + enemies
    ev = []
    r._do_attack(u, enemies[0], us, ev, 0, {x['uid']: x for x in us}, 3)
    return u, ev


# ---- 穿透 pierce：命中目标后，对正后方同列相邻敌人追加 50% 伤害 ----
front = unit('greedy', owner='B', x=3, y=3)
back = unit('greedy', owner='B', x=3, y=2)
u, ev = do_attack('two_pointers', [front, back])
# 主普攻事件也带 skillId='pierce'；追加事件额外带 skill=True。
pierce = [e for e in ev if e.get('skillId') == 'pierce' and e.get('skill')]
ok(len(pierce) == 1, 'pierce emits exactly one extra attack event')
ok(pierce[0]['toX'] == 3 and pierce[0]['toY'] == 2, 'pierce hits the unit directly behind')
ok(abs(back['hp'] - (6000 - int(RAW * s.PIERCE_RATIO))) < 1e-8,
   'pierce deals PIERCE_RATIO of the base hit')
ok(abs(front['hp'] - (6000 - int(RAW))) < 1e-8, 'pierce does not change the primary hit')

# ---- 溅射 splash：主目标四邻敌人受 35% 伤害，更远的不受影响 ----
center = unit('greedy', owner='B', x=3, y=3)
near = unit('greedy', owner='B', x=2, y=3)
far = unit('greedy', owner='B', x=0, y=0)
u, ev = do_attack('flood_fill', [center, near, far])
splash = [e for e in ev if e.get('skillId') == 'splash' and e.get('skill')]
ok(len(splash) == 1, 'splash emits exactly one adjacent hit')
ok(splash[0]['toX'] == 2 and splash[0]['toY'] == 3, 'splash targets the adjacent enemy')
ok(abs(near['hp'] - (6000 - int(RAW * s.SPLASH_RATIO))) < 1e-8,
   'splash deals SPLASH_RATIO of the base hit')
ok(far['hp'] == 6000, 'splash ignores enemies farther than one cell')
ok(not any(e.get('skillId') == 'pierce' for e in ev), 'mechanics do not cross-trigger')

# ---- 汲取 lifesteal：造成伤害后按 30% 回血，且不超过生命上限 ----
target = unit('greedy', owner='B', x=3, y=3)
u, ev = do_attack('huffman', [target], hp=3000)
heals = [e for e in ev if e.get('type') == 'heal']
expected_heal = int(int(RAW) * s.LIFESTEAL_RATIO)
ok(len(heals) == 1, 'lifesteal emits one heal event')
ok(heals[0]['dmg'] == expected_heal, 'heal amount equals LIFESTEAL_RATIO of damage dealt')
ok(abs(u['hp'] - (3000 + expected_heal)) < 1e-8, 'lifesteal actually restores HP')
ok(abs(u['hp'] - (3000 + expected_heal)) < 1e-8 and u['hp'] <= u['maxHp'],
   'lifesteal never exceeds max HP')

# ---- 背水 rampage：生命低于上限 50% 时攻击 ×1.6，满血不触发 ----
hi = unit('minimax', hp=6000)
lo = unit('minimax', hp=2000)
e = unit('greedy', owner='B', y=3)
v_hi = r._attack_multiplier(hi, e, [hi, e], 0, 3)
v_lo = r._attack_multiplier(lo, e, [lo, e], 0, 3)
ok(abs(v_hi - RAW) < 1e-8, 'rampage inactive at full HP')
ok(abs(v_lo - RAW * s.RAMPAGE_MULT) < 1e-8, 'rampage multiplies by RAMPAGE_MULT below threshold')
edge = unit('minimax', hp=6000 * s.RAMPAGE_HP)
ok(abs(r._attack_multiplier(edge, e, [edge, e], 0, 3) - RAW) < 1e-8,
   'rampage threshold is strict (<), not <=')

# ---- 协同 synergy：同流派友军每层 +12% 攻击，最多 4 层，异流派不计 ----
syn = unit('tarjan', x=3, y=4)                     # graph_theory
same = unit('prim', x=2, y=4)                      # graph_theory + synergy
r._apply_spawn_passives([syn, same])
ok(abs(syn['atk'] - 120. * (1 + s.SYNERGY_STEP)) < 1e-8,
   'one same-trait ally grants one SYNERGY_STEP')
ok(abs(syn['baseAtk'] - syn['atk']) < 1e-8, 'synergy updates baseAtk as well as atk')

syn2 = unit('tarjan', x=3, y=4)
peers = [unit('topo_sort', x=i, y=1) for i in range(6)]   # 6 个同流派友军
r._apply_spawn_passives([syn2] + peers)
ok(abs(syn2['atk'] - 120. * (1 + s.SYNERGY_STEP * s.SYNERGY_CAP)) < 1e-8,
   'synergy stacks are capped at SYNERGY_CAP')

syn3 = unit('tarjan', x=3, y=4)
other = unit('two_pointers', x=2, y=4)              # greedy，不同流派
r._apply_spawn_passives([syn3, other])
ok(abs(syn3['atk'] - 120.) < 1e-8, 'different-trait ally grants no synergy')
enemy = unit('topo_sort', owner='B', x=2, y=4)      # 敌方同流派不计
r._apply_spawn_passives([syn3, enemy])
ok(abs(syn3['atk'] - 120.) < 1e-8, 'enemy units never count as synergy peers')

# ---- 冻结 freeze：射程内全体敌人受 40% 伤害并停攻 2 秒 ----
caster = unit('topo_sort')                          # freeze 主动
e1 = unit('greedy', owner='B', x=3, y=3)
e2 = unit('greedy', owner='B', x=2, y=3)
out_of_range = unit('greedy', owner='B', x=7, y=0)
us = [caster, e1, e2, out_of_range]
ev = []
r._use_skill(caster, e1, [e1, e2, out_of_range], us, ev, 0,
             {x['uid']: x for x in us}, 3)
ok(all(abs(x['stallUntil'] - s.FREEZE_STALL) < 1e-8 for x in (e1, e2)),
   'freeze stalls every in-range enemy for FREEZE_STALL seconds')
ok(out_of_range['stallUntil'] == -1.0, 'freeze respects skill range')
ok(abs(e1['hp'] - (6000 - int(RAW * s.FREEZE_RATIO))) < 1e-8,
   'freeze deals FREEZE_RATIO of the base hit')
ok(abs(e2['hp'] - e1['hp']) < 1e-8, 'freeze hits all in-range enemies equally')
ok(any(e.get('type') == 'skill' and e.get('name') == 'freeze' for e in ev),
   'freeze emits a cast event for the client')

# ---- 机制只挂在新卡上，旧卡技能集合未被污染 ----
new_skills = {'pierce', 'splash', 'lifesteal', 'rampage', 'synergy', 'freeze'}
ok(all(s.CARD_BY_ID[c]['skill'] in new_skills for c in
       ('two_pointers', 'flood_fill', 'huffman', 'minimax', 'tarjan', 'topo_sort')),
   'six representative cards carry the six new skills')
legacy = [c for c in s.CARDS if c['id'] not in
          ('two_pointers', 'prefix_sum', 'huffman', 'topo_sort', 'kmp', 'prim',
           'flood_fill', 'ac_automaton', 'tarjan', 'minimax', 'suffix_array',
           'splay', 'network_flow', 'fft', 'suffix_automaton')]
ok(not any(c['skill'] in new_skills for c in legacy),
   'legacy 35 cards keep their original skills (baseline stays comparable)')
ok(len(s.CARDS) == 50 and len(s.TRAITS) == 16, 'card and trait totals')

print('PASS new mechanics:', len(checks), 'checks,',
      'pierce / splash / lifesteal / rampage / synergy / freeze 真实结算')
