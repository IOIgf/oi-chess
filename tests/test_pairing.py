"""离线单测：校验 Room._compute_pairings 的配对不变量与轮空公平性。

用法（在项目根目录）：python tests/test_pairing.py

不变量：
  1. 同一玩家不会出现在两场配对里（曾经的 bug：用了循环残留变量 b 而不是 best）
  2. 每名存活玩家要么有对手，要么在 _bye_players 里
  3. 配对对称：a 的对手是 b，则 b 的对手是 a
  4. 奇数人数时轮空会轮换：同一个人不会连续两轮轮空
  5. 轮空次数分布均匀：多轮之后各人轮空次数相差不超过 1
  6. 轮空不再被血量最高的人锁定（旧实现按 HP 排序后把最高的剩下来，
     而轮空不扣血，于是同一个人会一直轮空）
"""
import contextlib
import io
import os
import random
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, 'server.py'), encoding='utf-8').read()
src = src.replace("if __name__ == '__main__':", "if False:")
srv = types.ModuleType('srv')
srv.__dict__['__file__'] = os.path.join(ROOT, 'server.py')
exec(compile(src, 'server.py', 'exec'), srv.__dict__)


def make_players(n, seed=0, hp=None):
    """构造 n 名玩家；hp 可显式指定血量，用于制造「血量最高者」的极端场景。"""
    random.seed(seed)
    out = {}
    for i in range(n):
        cid = f'p{i}'
        out[cid] = {'id': cid, 'name': cid,
                    'hp': hp[i] if hp else random.randint(20, 100),
                    'dead': False, 'mind': 100, 'gold': 10, 'level': 1,
                    'energy': 100, 'reason': 100, 'board': {}, 'bench': [],
                    'ready': False, 'lastResult': '', 'roundWins': 0,
                    'roundLosses': 0, 'crashed': False}
    return out


def trial(n, seed):
    r = srv.Room('r', 'h')
    r.players = make_players(n, seed)
    r._compute_pairings()
    return r


def check(n, seed):
    r = trial(n, seed)
    slots = [x for p in r.pairings for x in (p['a'], p['b'])]
    covered = set(slots) | set(r._bye_players)
    dup = len(slots) != len(set(slots))
    pair_map = {}
    for p in r.pairings:
        pair_map.setdefault(p['a'], set()).add(p['b'])
        pair_map.setdefault(p['b'], set()).add(p['a'])
    asym = any(len(v) != 1 for v in pair_map.values())
    return not (dup or asym or covered != set(r.players))


def legacy_bye_ids(n, hp):
    """复现旧实现：按 HP 排序后贪心配对，最后剩下的人轮空。

    贪心时对手总是选血量最低的，于是血量最高者最后无人配对，
    轮空又不扣血，于是同一个人被永久锁定在轮空位。
    """
    ids = [f'p{i}' for i in range(n)]
    hps = {f'p{i}': hp[i] for i in range(n)}
    ids.sort(key=lambda cid: hps[cid])
    used = set()
    for a in ids:
        if a in used:
            continue
        best = None
        for b in ids:
            if b == a or b in used:
                continue
            if best is None or hps[b] < hps[best]:
                best = b
        if best:
            used.add(a)
            used.add(best)
    return [cid for cid in ids if cid not in used]


def fair_run(n, rounds, seed=0, hp=None):
    """连续模拟 rounds 轮配对。

    返回 (每名玩家的轮空次数, 每轮的轮空玩家集合列表)。
    """
    r = srv.Room('r', 'h')
    r.players = make_players(n, seed, hp=hp)
    counts = {cid: 0 for cid in r.players}
    bye_sets = []
    for rnd in range(1, rounds + 1):
        r.round = rnd
        r._compute_pairings()
        bye = set(r._bye_players)
        bye_sets.append(bye)
        for cid in bye:
            counts[cid] += 1
    return counts, bye_sets


def main():
    fails = 0
    notes = []

    def ok(cond, label):
        nonlocal fails
        if not cond:
            fails += 1
            notes.append('FAIL: ' + label)
        else:
            notes.append('ok: ' + label)

    # ---- 原有不变量 --------------------------------------------------------
    for n in range(2, 9):
        with contextlib.redirect_stdout(io.StringIO()):
            bad = sum(1 for seed in range(500) if not check(n, seed))
        ok(bad == 0, f'n={n} 配对三不变量（500 组随机样本）')
        if bad:
            notes.append(f'  n={n}: {bad}/500 次异常')

    # ---- 轮空公平性 --------------------------------------------------------
    for n in (3, 5, 7, 9):
        with contextlib.redirect_stdout(io.StringIO()):
            counts, bye_sets = fair_run(n, n * 4, seed=n)

        # 每一轮恰好 1 人轮空
        ok(all(len(b) == 1 for b in bye_sets), f'n={n} 每轮恰好 1 人轮空')
        # 不会连续两轮轮空
        ok(all(not (a & b) for a, b in zip(bye_sets, bye_sets[1:])),
           f'n={n} 同一个人不会连续两轮轮空')
        # 轮空次数分布均匀（相差不超过 1）
        spread = max(counts.values()) - min(counts.values())
        ok(spread <= 1, f'n={n} 轮空次数分布均匀（极差 {spread} <= 1）')
        # 每个玩家都轮空过
        ok(all(v >= 1 for v in counts.values()),
           f'n={n} 每个玩家都轮到过轮空')

    # ---- 旧 bug：血量最高者被永久锁定轮空 ----------------------------------
    for n in (3, 5, 7):
        hp = [100] + [30] * (n - 1)          # p0 血量最高
        with contextlib.redirect_stdout(io.StringIO()):
            counts, bye_sets = fair_run(n, n * 3, seed=n, hp=hp)
        spread = max(counts.values()) - min(counts.values())
        ok(spread <= 1,
           f'n={n} 血量最高的 p0 未独占轮空'
           f'（全场轮空 {min(counts.values())}~{max(counts.values())} 次）')
        # 对照：旧实现（按 HP 排序后把血量最高的剩下来）会让 p0 每轮都轮空
        legacy = [legacy_bye_ids(n, hp) for _ in range(n * 3)]
        ok(all(b == ['p0'] for b in legacy),
           f'n={n} 对照：旧实现确实让血量最高者每轮轮空')
        ok(not all(b == ['p0'] for b in bye_sets),
           f'n={n} 新实现打破了「血量最高者每轮轮空」')

    # ---- 轮空不依赖血量：血量全部相同时轮空依然轮换 ------------------------
    for n in (3, 5):
        hp = [50] * n
        with contextlib.redirect_stdout(io.StringIO()):
            counts, bye_sets = fair_run(n, n * 3, seed=n + 100, hp=hp)
        ok(all(not (a & b) for a, b in zip(bye_sets, bye_sets[1:])),
           f'n={n} 同血量时轮空依然轮换，不会固定给同一个人')

    # ---- 偶数人数：完全不轮空 ------------------------------------------------
    for n in (2, 4, 6, 8):
        with contextlib.redirect_stdout(io.StringIO()):
            counts, bye_sets = fair_run(n, 3, seed=n)
        ok(all(not b for b in bye_sets), f'n={n} 偶数人数没有人轮空')

    for line in notes:
        print('  ' + line)
    print('配对单测:', 'PASS' if fails == 0 else f'FAIL ({fails} 项)')
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
