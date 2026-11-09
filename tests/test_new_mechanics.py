"""战斗机制定向验证：由真实服务器函数结算，不看评分器预测值。

覆盖三类：
  1. 上一轮保留的 5 种机制（穿透 / 溅射 / 汲取 / 背水 / 冻结）；
  2. 本轮的全局羁绊（2/4/6 档）；
  3. 本轮新增的 13 个独立技能（含 4 个自限型负面技能）。

逐卡合同（test_mechanics_audit.py）只保证每张卡可执行；满编随机战斗
（test_battle_invariants.py）只保证不崩。这里逐条断言机制真的生效，且
数值与 server.py 中的常量一致。
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


def mult_series(cid, n, target=None):
    u = unit(cid)
    e = target or unit('greedy', owner='B', y=3)
    return [r._attack_multiplier(u, e, [u, e], 0, 3) / RAW for _ in range(n)]


# ===========================================================================
# 一、上一轮保留的 5 种机制
# ===========================================================================
# ---- 穿透 pierce：命中目标后，对正后方同列相邻敌人追加 50% 伤害 ----
front = unit('greedy', owner='B', x=3, y=3)
back = unit('greedy', owner='B', x=3, y=2)
u, ev = do_attack('two_pointers', [front, back])
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
ok(u['hp'] <= u['maxHp'], 'lifesteal never exceeds max HP')

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

# ---- 冻结 freeze：射程内全体敌人受 40% 伤害并停攻 2 秒 ----
caster = unit('topo_sort')
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

# ===========================================================================
# 二、全局羁绊（替代上一轮的新卡专属 synergy）
# ===========================================================================
ok(tuple(s.BOND_TIERS) == (2, 4, 6), 'bond thresholds are 2 / 4 / 6')
ok([s.bond_tier(n) for n in (0, 1, 2, 3, 4, 5, 6)] == [0, 0, 1, 1, 2, 2, 3],
   'bond_tier boundary values')

grp = [unit('greedy', x=i, y=1) for i in range(6)]
r._apply_spawn_passives(grp)
ok(all(abs(u['atk'] - 120 * (1 + s.BOND_ATK_STEP)) < 1e-8 for u in grp),
   'six same-trait units reach tier 3: +6% attack')
ok(all(abs(u['maxHp'] - int(6000 * (1 + s.BOND_HP_STEP))) < 1e-8 for u in grp),
   'tier 2+ grants +8% max HP as an integer')
ok(all(abs(u['inMult'] - (1 - s.BOND_GUARD_STEP)) < 1e-8 for u in grp),
   'tier 3 grants -6% damage taken')

pair = [unit('greedy'), unit('sort', x=2, y=4)]
enemy = unit('greedy', owner='B', x=3, y=1)
r._apply_spawn_passives(pair + [enemy])
ok(abs(pair[0]['atk'] - 120 * (1 + s.BOND_ATK_STEP)) < 1e-8,
   'two same-trait allies activate tier 1')
ok(pair[0]['bondTier'] == 1 and 'bondTier' not in enemy,
   'enemy units never count toward your bond')
ok(abs(enemy['atk'] - 120) < 1e-8, 'enemy units get no bond buff')

mixed = [unit('greedy'), unit('diff', x=2, y=4)]
r._apply_spawn_passives(mixed)
ok(all(abs(u['atk'] - 120) < 1e-8 for u in mixed),
   'different traits do not stack into a bond')

st = s.bond_status([s.CARD_BY_ID[x] for x in ('greedy', 'sort', 'two_pointers')])
ok(st[0]['count'] == 3 and st[0]['tier'] == 1 and st[0]['next'] == 4,
   'bond_status exposes count / tier / next threshold')
ok(st[0]['effects'] == [s.BOND_EFFECTS[0]], 'bond_status exposes active effects only')
ok(s.bond_status([]) == [], 'empty board has no bonds')

# ===========================================================================
# 三、本轮 13 个独立技能
# ===========================================================================
# 1. prefix_growth（前缀和）：伤害按自身命中数递增，上限 6 层
v = mult_series('prefix_sum', 8)
ok(all(abs(v[i] - (1 + s.PREFIX_GROWTH_STEP * min(s.PREFIX_GROWTH_CAP, i))) < 1e-8
       for i in range(8)), 'prefix_growth ramps by PREFIX_GROWTH_STEP and caps')

# 2. mst_link（最小生成树）：正交相邻友军每边减伤 6%，上限 4 边
prim = unit('prim')
n1 = unit('expectation', x=2, y=4)
n2 = unit('expectation', x=4, y=4)
n3 = unit('expectation', x=3, y=5)
r._apply_spawn_passives([prim, n1, n2, n3])
ok(abs(prim['mstGuard'] - 3 * s.MST_GUARD_STEP) < 1e-8,
   'three orthogonal allies create three MST edges')
ev = []
d = r._deal_damage(prim, RAW, ev, 0, [prim, n1], {}, allow_react=False)
ok(d == int(RAW * (1 - 3 * s.MST_GUARD_STEP)),
   'MST guard reduces incoming damage before integer rounding')
far_ally = unit('expectation', x=0, y=0)
prim2 = unit('prim')
r._apply_spawn_passives([prim2, far_ally])
ok(prim2['mstGuard'] == 0.0, 'non-adjacent ally creates no MST edge')

# 3. scc_mark（强连通分量）：标记最多 3 层，每层承伤 +8%
victim = unit('greedy', owner='B', y=3)
for _ in range(5):
    do_attack('tarjan', [victim])
ok(victim['mark'] == s.SCC_MARK_CAP, 'SCC marks cap at SCC_MARK_CAP')
ev = []
d = r._deal_damage(victim, RAW, ev, 0, [victim], {}, allow_react=False)
ok(d == int(RAW * (1 + s.SCC_MARK_STEP * s.SCC_MARK_CAP)),
   'SCC marks amplify damage taken by SCC_MARK_STEP per layer')

# 4. fft_butterfly（FFT）：奇数击 ×0.7 / 偶数击 ×1.7
v = mult_series('fft', 4)
ok(all(abs(v[i] - (s.FFT_ODD_MULT if i % 2 == 0 else s.FFT_EVEN_MULT)) < 1e-8
       for i in range(4)), 'FFT alternates weak/strong butterfly beats')
ok(s.FFT_ODD_MULT < 1.0 < s.FFT_EVEN_MULT,
   'FFT is a self-limiting skill: the first beat is weaker than a normal hit')

# 5. kmp_next（KMP）：未击杀累积 next 层，击杀清零
k = unit('kmp')
t_alive = unit('greedy', owner='B', y=3)
for _ in range(3):
    r._do_attack(k, t_alive, [k, t_alive], [], 1, {k['uid']: k, t_alive['uid']: t_alive}, 3)
ok(k['charge'] == 3, 'KMP accumulates one next-layer per non-lethal hit')
ok(abs(r._attack_multiplier(k, t_alive, [k, t_alive], 1, 3) / RAW
       - (1 + s.KMP_NEXT_STEP * 3)) < 1e-8, 'KMP next layers amplify damage')
t_dying = unit('greedy', owner='B', y=3, hp=1)
r._do_attack(k, t_dying, [k, t_dying], [], 1, {k['uid']: k, t_dying['uid']: t_dying}, 3)
ok(k['charge'] == 0, 'KMP resets the next table after a kill')

# 6. lcp_chain（后缀数组）：连续同名 ×1.5，切换目标 ×0.8
sa = unit('suffix_array')
same = unit('greedy', owner='B', y=3)
other = unit('diff', owner='B', y=3)
v1 = r._attack_multiplier(sa, same, [sa, same], 0, 3) / RAW
r._do_attack(sa, same, [sa, same], [], 1, {sa['uid']: sa, same['uid']: same}, 3)
v2 = r._attack_multiplier(sa, same, [sa, same], 1, 3) / RAW
v3 = r._attack_multiplier(sa, other, [sa, other], 1, 3) / RAW
ok(abs(v1 - s.LCP_OTHER_MULT) < 1e-8, 'first target of an LCP chain is penalised')
ok(abs(v2 - s.LCP_SAME_MULT) < 1e-8, 'same-card target gains LCP_SAME_MULT')
ok(abs(v3 - s.LCP_OTHER_MULT) < 1e-8, 'switching to a different card breaks the chain')
ok(s.LCP_OTHER_MULT < 1.0, 'LCP chain is a self-limiting skill on mixed boards')

# 7. seg_query（线段树）：每第 4 击对射程内全体追加 60% 伤害
seg = unit('segment_tree')
main = unit('greedy', owner='B', x=3, y=3)
extra = unit('greedy', owner='B', x=4, y=3)
us = [seg, main, extra]
evs = []
for _ in range(3):
    r._do_attack(seg, main, us, evs, 1, {x['uid']: x for x in us}, 3)
ok(not any(e.get('skillId') == 'seg_query' and e.get('skill') for e in evs),
   'seg_query stays quiet for the first three hits')
r._do_attack(seg, main, us, evs, 1, {x['uid']: x for x in us}, 3)
q = [e for e in evs if e.get('skillId') == 'seg_query' and e.get('skill')]
ok(len(q) == 1, 'seg_query emits one extra area hit on the 4th attack')
ok(abs(extra['hp'] - (6000 - int(RAW * s.SEG_QUERY_RATIO))) < 1e-8,
   'seg_query deals SEG_QUERY_RATIO to every other in-range enemy')

# 8. heuristic（A*）：估价选目标 + 25% 增伤
astar = unit('a_star')
close_dead = unit('greedy', owner='B', x=3, y=3, hp=10)
far_tank = unit('greedy', owner='B', x=5, y=4, hp=6000)
ok(r._pick_target(astar, [far_tank, close_dead]) is close_dead,
   'A* heuristic prefers the low f=g+h target')
ok(abs(r._attack_multiplier(astar, close_dead, [astar, close_dead], 0, 3) / RAW
       - s.HEURISTIC_MULT) < 1e-8, 'A* heuristic grants HEURISTIC_MULT')

# 9. mod_cycle（费马）：7 击周期，末击爆发
v = mult_series('fermat', 7)
expect = [max(0.4, s.MOD_CYCLE_START - s.MOD_CYCLE_STEP * i)
          for i in range(s.MOD_CYCLE - 1)] + [s.MOD_CYCLE_BURST]
ok(all(abs(v[i] - expect[i]) < 1e-8 for i in range(7)),
   'mod_cycle decays then bursts on the 7th hit')
ok(expect[5] < 1.0, 'mod_cycle late beat is a self-limiting penalty')

# 10. splay_rotate（伸展树）：普攻 +7%/层，受伤折半
sp = unit('splay')
tg = unit('greedy', owner='B', y=3)
for _ in range(4):
    r._do_attack(sp, tg, [sp, tg], [], 1, {sp['uid']: sp, tg['uid']: tg}, 3)
ok(sp['stacks'] == 4, 'splay rotates one layer per attack')
ev = []
r._deal_damage(sp, RAW, ev, 0, [sp, tg], {}, allow_react=False)
ok(sp['stacks'] == 2, 'taking a hit halves the splay rotation layers')
ok(abs(r._attack_multiplier(sp, tg, [sp, tg], 1, 3) / RAW
       - (1 + s.SPLAY_STEP * 2)) < 1e-8, 'splay damage follows the halved stack count')

# 11. min_cut（网络流）：全体分摊 + 血量最高者额外收割
caster = unit('network_flow')
boss = unit('greedy', owner='B', x=3, y=3, hp=6000)
weak = unit('greedy', owner='B', x=2, y=3, hp=5000)
us = [caster, boss, weak]
ev = []
r._use_skill(caster, boss, [boss, weak], us, ev, 0,
             {x['uid']: x for x in us}, 3)
ratio = s.MIN_CUT_RATIO / (1 + s.MIN_CUT_SPREAD)
boss_ratio = s.MIN_CUT_BOSS_RATIO / (1 + s.MIN_CUT_BOSS_SPREAD)
ok(abs(weak['hp'] - (5000 - int(RAW * ratio))) < 1e-8,
   'min_cut splits flow across all in-range enemies')
ok(abs(boss['hp'] - (6000 - int(RAW * ratio) - int(RAW * boss_ratio))) < 1e-8,
   'min_cut cuts the highest-capacity (highest HP) enemy twice')
ok(any(e.get('type') == 'skill' and e.get('name') == 'min_cut' for e in ev),
   'min_cut emits a cast event for the client')
ok(ratio < s.MIN_CUT_RATIO, 'more enemies means less damage each (capacity limit)')
ok(boss_ratio < s.MIN_CUT_BOSS_RATIO,
   'the extra cut on the biggest target also scales down with the enemy count')

# 12. multi_match（AC 自动机）：fail 链命中所有同名敌人
ac = unit('ac_automaton')
m1 = unit('greedy', owner='B', x=3, y=3)
m2 = unit('greedy', owner='B', x=4, y=3)
m3 = unit('diff', owner='B', x=2, y=3)
us = [ac, m1, m2, m3]
ev = []
r._do_attack(ac, m1, us, ev, 0, {x['uid']: x for x in us}, 3)
mm = [e for e in ev if e.get('skillId') == 'multi_match' and e.get('skill')]
ok(len(mm) == 1, 'multi_match follows the fail link to one same-card enemy')
ok(mm[0]['toX'] == 4 and mm[0]['toY'] == 3, 'multi_match hits the same-card enemy')
ok(abs(m2['hp'] - (6000 - int(RAW * s.MULTI_MATCH_RATIO))) < 1e-8,
   'multi_match deals MULTI_MATCH_RATIO to the extra target')
ok(m3['hp'] == 6000, 'multi_match ignores enemies of a different card')

# 13. sam_compress（后缀自动机）：同名友军以血换攻
sam = [unit('suffix_automaton', x=i, y=1) for i in range(3)]
r._apply_spawn_passives(sam)
n = 2
ok(all(abs(u['atk'] - 120 * (1 + s.BOND_ATK_STEP)
           * (1 + s.SAM_ATK_STEP * (n + 1))) < 1e-8
       for u in sam), 'SAM compression trades HP for attack, on top of the bond')
ok(all(abs(u['maxHp'] - int(6000 * (1 - s.SAM_HP_STEP * n))) < 1e-8 for u in sam),
   'SAM compression lowers max HP by SAM_HP_STEP per same-card ally')
ok(all(u['hp'] == u['maxHp'] for u in sam), 'SAM compression clamps current HP to the new cap')
ok(s.SAM_HP_STEP > 0 and s.SAM_ATK_STEP > 0,
   'SAM compression is an explicit negative-skill limiting a top-panel card')
# 独苗不再白板：自己也是一个状态，只赚攻击不付血代价
solo = [unit('suffix_automaton', x=1, y=1)]
r._apply_spawn_passives(solo)
ok(abs(solo[0]['atk'] - 120 * (1 + s.SAM_ATK_STEP)) < 1e-8,
   'a lone SAM unit still gains attack instead of doing nothing')
ok(solo[0]['maxHp'] == 6000,
   'a lone SAM unit pays no HP cost (no state to merge with)')
# 3 张与公式一致（n = same - 1）
triple = [unit('suffix_automaton', x=i, y=1) for i in range(3)]
r._apply_spawn_passives(triple)
ok(all(abs(u['atk'] - 120 * (1 + s.BOND_ATK_STEP) * (1 + s.SAM_ATK_STEP * 3)) < 1e-8
       for u in triple), 'three same-card allies keep the same compression count')

# ===========================================================================
# 四、总体：50 张卡 50 个唯一技能
# ===========================================================================
ok(len(s.CARDS) == 50 and len({c['skill'] for c in s.CARDS}) == 50,
   'all 50 cards now carry 50 distinct skills')
ok(len(s.ACTIVE_SKILLS) == 16, 'min_cut is the 16th active skill')
ok(s.MAX_BOARD == 20, 'board cap raised to 20 units')
ok(not any(c['skill'] == 'synergy' for c in s.CARDS),
   'card-only synergy is gone, replaced by the global bond')
ok(s.CARD_BY_ID['o2']['hp'] == 280 and s.CARD_BY_ID['spfa']['hp'] == 1000,
   'legacy signature cards keep their tuned stats')

print('PASS new mechanics:', len(checks), 'checks,',
      '5 retained / bonds / 13 unique skills / 50 distinct skills')
