"""全局羁绊机制的定向验证。

羁绊按 **(阵营, 流派)** 分组统计场上棋子数量，2 / 4 / 6 张逐级激活：
  档位 1 → 同流派棋子攻击 +6%
  档位 2 → 再加生命 +8%
  档位 3 → 再加承伤 -6%

分三层验证：
  1. 纯函数层：`bond_tier` 的档位边界、`bond_status` 的字段与语义
  2. 结算层：`_apply_spawn_passives` 落到单位上的真实数值
  3. 真实战斗层：`_simulate_battle` 整局里羁绊确实被结算

关键语义：羁绊只统计**自己场上**的棋子，双方同流派各自成组、互不叠加。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as s

checks = []


def ok(cond, label):
    assert cond, label
    checks.append(label)


# ===========================================================================
# 一、纯函数层
# ===========================================================================
ok(tuple(s.BOND_TIERS) == (2, 4, 6), 'bond thresholds are 2 / 4 / 6')
ok([s.bond_tier(n) for n in range(8)] == [0, 0, 1, 1, 2, 2, 3, 3],
   'bond_tier boundary values: 1->0, 2->1, 4->2, 6->3')
ok(len(s.BOND_EFFECTS) == 3, 'exactly three bond effects are defined')
ok(s.BOND_ATK_STEP > 0 and s.BOND_HP_STEP > 0 and s.BOND_GUARD_STEP > 0,
   'bond effects are all positive steps')

# bond_status 语义：只给已激活的效果，并报出下一档还差几张
cards = [s.CARD_BY_ID[x] for x in ('greedy', 'sort', 'two_pointers')]
st = s.bond_status(cards)
ok(len(st) == 1, 'one trait across three cards yields one bond row')
ok(st[0]['count'] == 3 and st[0]['tier'] == 1 and st[0]['next'] == 4,
   'bond_status exposes count / tier / next threshold')
ok(st[0]['effects'] == [s.BOND_EFFECTS[0]],
   'bond_status exposes only the effects already active')
ok(s.bond_status([]) == [], 'empty board has no bonds')
ok(s.bond_status([s.CARD_BY_ID['greedy'], s.CARD_BY_ID['diff']])[0]['tier'] == 0,
   'different traits never stack into a bond')
ok(all('bondTier' not in s.CARD_BY_ID[x] for x in ('greedy', 'diff')),
   'card definitions carry no baked-in bond tier')


# ===========================================================================
# 二、结算层
# ===========================================================================
r = s.Room('bond-test', 'A')
STATS = {'A': {'out': 1, 'in': 1}, 'B': {'out': 1, 'in': 1}}


def unit(cid, owner='A', x=3, y=4, hp=6000):
    u = r._unit_from(owner, '3,0',
                     {'card': cid, 'hp': s.effective_max_hp(s.CARD_BY_ID[cid])},
                     'a' if owner == 'A' else 'b', STATS, 3)
    u.update(uid=f'{owner}:{x},{y}:{cid}', x=x, y=y,
             hp=float(hp), maxHp=float(hp), atk=120., baseAtk=120., range=5)
    return u


base_atk = 120.
six = [unit('greedy', x=i, y=1) for i in range(6)]
r._apply_spawn_passives(six)
ok(all(abs(u['atk'] - base_atk * (1 + s.BOND_ATK_STEP)) < 1e-8 for u in six),
   'tier 1 grants BOND_ATK_STEP attack to every same-trait unit')
ok(all(abs(u['maxHp'] - int(6000 * (1 + s.BOND_HP_STEP))) < 1e-8 for u in six),
   'tier 2 grants BOND_HP_STEP max HP')
ok(all(u['maxHp'] == int(u['maxHp']) for u in six),
   'bond max HP stays integral (no fractional hp that would serialize as 0)')
ok(all(abs(u['inMult'] - (1 - s.BOND_GUARD_STEP)) < 1e-8 for u in six),
   'tier 3 grants BOND_GUARD_STEP damage reduction')

pair = [unit('greedy'), unit('sort', x=2, y=4)]   # 同为 greedy 流派
r._apply_spawn_passives(pair)
ok(all(abs(u['atk'] - base_atk * (1 + s.BOND_ATK_STEP)) < 1e-8 for u in pair),
   'two same-trait allies both activate tier 1')
ok(all(u.get('bondTier') == 1 for u in pair),
   'both same-trait allies record tier 1')
ok(s.CARD_BY_ID['greedy']['trait'] == s.CARD_BY_ID['sort']['trait'],
   'greedy and sort really do share the greedy trait')

mixed = [unit('greedy'), unit('diff', x=2, y=4)]
r._apply_spawn_passives(mixed)
ok(all(abs(u['atk'] - base_atk) < 1e-8 for u in mixed),
   'different traits do not stack into a bond')

# 羁绊按 (阵营, 流派) 分组：双方同流派互不叠加
ally = unit('greedy', owner='A', x=1, y=1)
foe = unit('greedy', owner='B', x=1, y=2)
r._apply_spawn_passives([ally, foe])
ok(abs(ally['atk'] - base_atk) < 1e-8 and abs(foe['atk'] - base_atk) < 1e-8,
   'one ally and one enemy of the same trait form no bond')
ok('bondTier' not in ally and 'bondTier' not in foe,
   'enemy units never count toward your bond')


# ===========================================================================
# 三、真实战斗层
# ===========================================================================
def team(pid, roster, cells):
    return dict(id=pid, mind=100, energy=40,
                board={f'{x},{y}': dict(card=cid, hp=s.effective_max_hp(s.CARD_BY_ID[cid]))
                       for cid, (x, y) in zip(roster, cells)})


# 5 张同流派 vs 5 张互不同流派
diff_trait = []
seen_trait = set()
for c in s.CARDS:
    if c['trait'] not in seen_trait:
        seen_trait.add(c['trait'])
        diff_trait.append(c['id'])
    if len(diff_trait) == 5:
        break
ok(len(diff_trait) == 5, 'five cards with five distinct traits are available')

cells = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]
a = team('A', ['greedy'] * 5, cells)
b = team('B', diff_trait, cells)

captured = []
orig = s.Room._apply_spawn_passives


def spy(self, units):
    pre = [{'owner': u['owner'], 'card': u['card'], 'trait': u['trait'],
            'atk0': u['atk'], 'hp0': u['maxHp']} for u in units]
    orig(self, units)
    captured.append([dict(pre[i], tier=u.get('bondTier', 0), atk=u['atk'],
                          maxHp=u['maxHp'])
                     for i, u in enumerate(units)])


s.Room._apply_spawn_passives = spy
try:
    s.Room('bond-battle', 'A')._simulate_battle(a, b, 3, record=False)
finally:
    s.Room._apply_spawn_passives = orig

ok(len(captured) == 1, 'the battle applies spawn passives exactly once')
rows = captured[0]
ok(len(rows) == 10, 'all ten units entered the passive pass')

ally_rows = [x for x in rows if x['owner'] == 'A']
foe_rows = [x for x in rows if x['owner'] == 'B']
ok(all(x['trait'] == 'greedy' for x in ally_rows),
   'the allied roster is a single trait')
ok(all(x['tier'] == 2 for x in ally_rows),
   'five same-trait allies reach tier 2 in a real battle')
ok(all(abs(x['atk'] - x['atk0'] * (1 + s.BOND_ATK_STEP)) < 1e-8 for x in ally_rows),
   'the real battle applies the tier 1 attack bonus')
ok(all(abs(x['maxHp'] - int(x['hp0'] * (1 + s.BOND_HP_STEP))) < 1e-8 for x in ally_rows),
   'the real battle applies the tier 2 max HP bonus')
ok(all(x['maxHp'] == int(x['maxHp']) for x in ally_rows),
   'the real battle keeps bonded HP integral')
ok(all(x['tier'] == 0 for x in foe_rows),
   'a roster of five distinct traits activates no bond')
ok(all(abs(x['atk'] - x['atk0']) < 1e-8 for x in foe_rows),
   'units without a bond keep their base attack')

# 双方同流派：各自成组，都停在 tier 2，不会因为对手也是同流派而叠加
a2 = team('A', ['greedy'] * 5, cells)
b2 = team('B', ['greedy'] * 5, cells)
captured.clear()
s.Room._apply_spawn_passives = spy
try:
    s.Room('bond-battle-2', 'A')._simulate_battle(a2, b2, 3, record=False)
finally:
    s.Room._apply_spawn_passives = orig
rows2 = captured[0]
ok(all(x['tier'] == 2 for x in rows2),
   'both sides of a mirror match reach tier 2 independently')
ok(len({x['tier'] for x in rows2}) == 1,
   'enemy rosters never push a bond past its own tier')

print('PASS bonds:', len(checks), 'checks,',
      'tiers 2/4/6 / owner-scoped / applied in real battles')
