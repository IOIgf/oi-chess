"""离线单测：校验 Room._compute_pairings 的配对不变量。

用法（在项目根目录）：python tests/test_pairing.py

不变量：
  1. 同一玩家不会出现在两场配对里（曾经的 bug：用了循环残留变量 b 而不是 best）
  2. 每名存活玩家要么有对手，要么在 _bye_players 里
  3. 配对对称：a 的对手是 b，则 b 的对手是 a
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


def trial(n, seed):
    random.seed(seed)
    r = srv.Room('r', 'h')
    r.players = {
        f'p{i}': {'id': f'p{i}', 'name': f'p{i}', 'hp': random.randint(20, 100),
                  'dead': False, 'mind': 100, 'gold': 10, 'level': 1,
                  'energy': 100, 'reason': 100, 'board': {}, 'bench': [],
                  'ready': False, 'lastResult': '', 'roundWins': 0,
                  'roundLosses': 0, 'crashed': False}
        for i in range(n)
    }
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


def main():
    fails = 0
    for n in range(2, 9):
        with contextlib.redirect_stdout(io.StringIO()):   # 静音服务器自己的配对日志
            bad = sum(1 for seed in range(500) if not check(n, seed))
        print(f'  n={n}: ' + ('OK' if bad == 0 else f'{bad}/500 次异常'))
        fails += bad
    print('配对单测:', 'PASS' if fails == 0 else f'FAIL ({fails} 次异常)')
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
