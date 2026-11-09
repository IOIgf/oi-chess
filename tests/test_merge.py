"""合成 / 升星机制合同：3 张同名同星自动合成，最高 3 星。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from balance_lab import load_server

s = load_server()
checks = []


def ok(cond, label):
    assert cond, label
    checks.append(label)


def room():
    r = s.Room('merge', 'A')
    r.state = 'prep'
    p = s.new_player('A', 'A')
    p['gold'] = 100
    p['energy'] = 100
    p['reason'] = 100
    r.players = {'A': p}
    return r, p


def unit(cid, star=1, hp=None, kills=None):
    card = s.CARD_BY_ID[cid]
    info = {'card': cid, 'star': star,
            'hp': s.star_max_hp(card, star) if hp is None else hp}
    if kills is not None:
        info['kills'] = kills
    return info


def stats(cid, star):
    card = s.CARD_BY_ID[cid]
    return s.Room._unit_from(
        s.Room('stats', 'A'), 'A', '3,0',
        {'card': cid, 'star': star, 'hp': s.star_max_hp(card, star)},
        'a', {'A': {'out': 1, 'in': 1}}, 3)


# ---- 基础倍率与返还 --------------------------------------------------------
dfs = s.CARD_BY_ID['dfs']
ok(s.star_max_hp(dfs, 1) == 438, 'star1 max hp')
ok(s.star_max_hp(dfs, 2) == 788, 'star2 max hp')
ok(s.star_max_hp(dfs, 3) == 1419, 'star3 max hp')
ok(abs(s.star_attack(dfs, 2) - 79.2) < 1e-9, 'star2 attack')
ok(abs(s.star_attack(dfs, 3) - 142.56) < 1e-9, 'star3 attack')
ok(s.sell_value(dfs, 1) == 1, 'star1 sell value')
ok(s.sell_value(dfs, 2) == 2, 'star2 sell value')
ok(s.sell_value(dfs, 3) == 8, 'star3 sell value')

# ---- 3 张 1 星 -> 2 星 -----------------------------------------------------
r, p = room()
p['shop'] = ['dfs'] * 3
for _ in range(3):
    ok(r.buy('A', 0)[0], 'buy dfs')
ok(len(p['bench']) == 1, 'three copies become one unit')
u = p['bench'][0]
ok(u['card'] == 'dfs' and u['star'] == 2, 'merged to star 2')
ok(u['hp'] == s.star_max_hp(dfs, 2), 'merged unit full hp')
ok(p['mergeNotice']['card'] == 'dfs' and p['mergeNotice']['star'] == 2,
   'merge notice emitted')
ok(p['gold'] == 97 and p['energy'] == 88 and p['reason'] == 88,
   'buy costs are unchanged by merge')

# ---- 9 张 1 星 -> 3 星级联 -------------------------------------------------
r, p = room()
p['shop'] = ['dfs'] * 9
for _ in range(9):
    ok(r.buy('A', 0)[0], 'buy dfs cascade')
ok(len(p['bench']) == 1 and p['bench'][0]['star'] == 3, 'nine copies become star 3')
ok(p['bench'][0]['hp'] == s.star_max_hp(dfs, 3), 'star3 full hp')
ok(p['mergeNotice']['star'] == 3, 'cascade notice is highest star')

# ---- 场上优先，锚点对象不换 ------------------------------------------------
r, p = room()
p['shop'] = ['dfs'] * 3
r.buy('A', 0)
r.buy('A', 0)
r.place('A', 0, 1, 1)
anchor = p['board']['1,1']
r.buy('A', 0)
ok(list(p['board']) == ['1,1'], 'board position wins')
ok(p['board']['1,1'] is anchor, 'anchor object is upgraded in place')
ok(anchor['star'] == 2 and not p['bench'], 'bench copies consumed')

# ---- 备战席满：可合成时允许购买，否则拒绝 ----------------------------------
filler = ['gcd', 'greedy', 'sort', 'diff', 'xor', 'bfs', 'pigeonhole', 'prime_sieve']
r, p = room()
p['bench'] = [unit(cid) for cid in filler] + [unit('dfs'), unit('dfs')]
p['shop'] = ['dfs']
ok(len(p['bench']) == 10, 'bench starts full')
ok(r.buy('A', 0)[0], 'buy allowed when it completes a merge')
ok(len(p['bench']) == 9, 'merge frees a bench slot')
ok(any(u['card'] == 'dfs' and u['star'] == 2 for u in p['bench']), 'dfs merged')

r, p = room()
p['bench'] = [unit(cid) for cid in filler] + [unit('gcd'), unit('greedy')]
p['shop'] = ['dfs']
ok(not r.buy('A', 0)[0], 'buy rejected when bench is full and no merge')
ok(len(p['bench']) == 10, 'bench unchanged after rejected buy')

# ---- 不合成的情况 ----------------------------------------------------------
r, p = room()
p['bench'] = [unit('dfs'), unit('dfs'), unit('gcd')]
ok(r._try_merge(p) is None and len(p['bench']) == 3, 'different cards do not merge')

r, p = room()
p['bench'] = [unit('dfs', 1), unit('dfs', 1), unit('dfs', 2)]
ok(r._try_merge(p) is None and len(p['bench']) == 3, 'different stars do not merge')

r, p = room()
p['bench'] = [unit('dfs', 3) for _ in range(3)]
ok(r._try_merge(p) is None and len(p['bench']) == 3, 'star 3 is the cap')

# ---- 合成满血 / 遗传算法击杀层数 -------------------------------------------
r, p = room()
p['bench'] = [unit('dfs', 1, hp=1) for _ in range(3)]
r._try_merge(p)
ok(p['bench'][0]['hp'] == s.star_max_hp(dfs, 2), 'merge heals to full hp')

r, p = room()
p['bench'] = [unit('genetic', kills=k) for k in (1, 2, 3)]
r._try_merge(p)
ok(p['bench'][0]['star'] == 2 and p['bench'][0]['kills'] == 3,
   'genetic keeps max kills')

r, p = room()
p['bench'] = [unit('genetic', kills=3) for _ in range(3)]
r._try_merge(p)
ok(p['bench'][0]['kills'] == s.GENETIC_CAP, 'genetic kills capped')

# ---- 卖出返还 --------------------------------------------------------------
r, p = room()
p['bench'] = [unit('dfs', 2)]
p['gold'] = 0
p['energy'] = 50
p['reason'] = 50
ok(r.sell('A', 'bench', 0)[0], 'sell star2')
ok(p['gold'] == 2 and p['energy'] == 56 and p['reason'] == 56, 'star2 refund')

r, p = room()
p['bench'] = [unit('dfs', 3)]
p['gold'] = 0
p['energy'] = 50
p['reason'] = 50
ok(r.sell('A', 'bench', 0)[0], 'sell star3')
ok(p['gold'] == 8 and p['energy'] == 68 and p['reason'] == 68, 'star3 refund')

# ---- 战斗数值 --------------------------------------------------------------
u = stats('dfs', 2)
ok(u['star'] == 2 and u['maxHp'] == 788.0, 'battle star2 max hp')
ok(abs(u['atk'] - 79.2) < 1e-9, 'battle star2 attack')
u = stats('dfs', 3)
ok(u['maxHp'] == 1419.0 and abs(u['atk'] - 142.56) < 1e-9, 'battle star3 stats')

u = stats('shift', 2)
ok(u['maxHp'] == 678.0 and abs(u['atk'] - 273.6) < 1e-9, 'shift star2 stats')
u = stats('matrix_pow', 2)
ok(u['maxHp'] == 2502.0 and abs(u['atk'] - 418.5) < 1e-9, 'matrix star2 stats')
u = stats('o2', 2)
ok(u['maxHp'] == 504.0 and u['atk'] == 0.0, 'o2 star2 only gains hp')

# ---- 准备期回血 / 轮空帧 / 状态序列化 --------------------------------------
r, p = room()
p['board'] = {'0,0': unit('dfs', 2, hp=1)}
r._start_prep(first=False)
ok(p['board']['0,0']['hp'] == 551, 'prep heal uses star max hp')

r, p = room()
p['board'] = {'0,0': unit('dfs', 2, hp=100)}
frames = r._make_bye_frames('A')
ok(frames[0]['units'][0]['maxHp'] == 788, 'bye frame star max hp')
ok(frames[0]['units'][0]['star'] == 2, 'bye frame star field')

r, p = room()
p['bench'] = [unit('dfs', 2)]
p['mergeNotice'] = {'id': 'm1', 'card': 'dfs', 'star': 2}
state = r.get_state('A')
ok(state['players']['A']['mergeNotice']['id'] == 'm1', 'merge notice serialized')
json.dumps(state, ensure_ascii=False)

print(f'PASS merge audit: {len(checks)} checks')
