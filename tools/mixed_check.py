"""混编验证：在「4 张参考卡 + 1 张被测卡」的队伍里，看每张卡的真实贡献。

镜像测（5 张同卡）会放大树状数组、归并排序这类需要队友配合的技能，
所以这里换一个独立口径交叉验证：被测卡当替补上场，看它把胜率抬高了多少。

用法：python tools/mixed_check.py [--trials 40]
"""
import argparse
import contextlib
import io
import os
import random
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = 'mod_op'          # 参考卡：2 费、技能简单，用来撑住队伍框架
TRIALS = 40


def load_server():
    src = open(os.path.join(ROOT, 'server.py'), encoding='utf-8').read()
    src = src.replace("if __name__ == '__main__':", "if False:")
    srv = types.ModuleType('srv')
    srv.__dict__['__file__'] = os.path.join(ROOT, 'server.py')
    exec(compile(src, 'server.py', 'exec'), srv.__dict__)
    return srv


SRV = load_server()


def team(pid, cards, cells):
    return {'id': pid, 'mind': 100, 'energy': 40,
            'board': {f'{x},{y}': {'card': c,
                                   'hp': SRV.effective_max_hp(SRV.CARD_BY_ID[c])}
                      for c, (x, y) in zip(cards, cells)}}


def one(rng, x, swap):
    cells = rng.sample([(a, b) for a in range(SRV.HALF_W) for b in range(SRV.HALF_H)], 5)
    roster = [REF] * 4 + [x]
    rng.shuffle(roster)
    a_cards = roster
    b_cards = [REF] * 5
    if swap:
        a, b = team('A', b_cards, cells), team('B', a_cards, cells)
        frames, events, ah, bh = SRV.Room('m', 'A')._simulate_battle(a, b, rng.randint(2, 9), record=False)
        return (sum(max(0, v) for v in bh.values()) / sum(
            SRV.effective_max_hp(SRV.CARD_BY_ID[i['card']]) for i in b['board'].values())
            - sum(max(0, v) for v in ah.values()) / sum(
                SRV.effective_max_hp(SRV.CARD_BY_ID[i['card']]) for i in a['board'].values()))
    a, b = team('A', a_cards, cells), team('B', b_cards, cells)
    frames, events, ah, bh = SRV.Room('m', 'A')._simulate_battle(a, b, rng.randint(2, 9), record=False)
    return (sum(max(0, v) for v in ah.values()) / sum(
        SRV.effective_max_hp(SRV.CARD_BY_ID[i['card']]) for i in a['board'].values())
        - sum(max(0, v) for v in bh.values()) / sum(
            SRV.effective_max_hp(SRV.CARD_BY_ID[i['card']]) for i in b['board'].values()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--trials', type=int, default=TRIALS)
    args = ap.parse_args()
    rng = random.Random(20261108)

    rows = []
    for card in SRV.CARDS:
        acc = 0.0
        for t in range(args.trials):
            acc += one(rng, card['id'], swap=(t % 2 == 1))
        rows.append({'id': card['id'], 'name': card['name'], 'cost': card['cost'],
                     'attack': card['attack'], 'hp': card['hp'],
                     'value': acc / args.trials})

    print(f"参考卡 = {SRV.CARD_BY_ID[REF]['name']}（{REF}），每张卡 {args.trials} 场")
    print('「替补价值」= 上场后比纯参考队伍多出的净胜血量\n')
    by_cost = {}
    for r in rows:
        by_cost.setdefault(r['cost'], []).append(r)
    for cost in sorted(by_cost):
        tier = by_cost[cost]
        mean = sum(r['value'] for r in tier) / len(tier)
        print(f'—— {cost} 费（均值 {mean:+.3f}）')
        for r in sorted(tier, key=lambda r: -r['value']):
            print(f"   {r['name']:12}{r['attack']:>4}/{r['hp']:<6} 替补价值 {r['value']:+.3f}"
                  f"   相对 {r['value'] - mean:+.3f}")
    return rows


if __name__ == '__main__':
    main()
