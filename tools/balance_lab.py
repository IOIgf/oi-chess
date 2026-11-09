"""卡片强度实验室：用服务器自带的战斗模拟，跑当前卡池的完整循环赛，算出每张卡的战力指数。

原理
----
* 每张卡组一支「5 个同卡」的队伍，两两对战（含先后手交换），用 Bradley-Terry 模型
  把胜负矩阵拟合成一个可比的战力倍率；
* 站位随机、回合数随机（2~9）、精力统一 40，保证不同卡之间条件一致；
* 战力指数按费用层各自归一化（1.0 = 该费用层的平均水平），用来发现同费之间的强弱差。

用法
----
    python tools/balance_lab.py                        # 测当前数值
    python tools/balance_lab.py --apply balance/x.json # 先套用 json 里的数值再测
    python tools/balance_lab.py --trials 20 --json out.json
"""
import argparse
import contextlib
import io
import itertools
import json
import os
import random
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_server(path=None):
    src = open(path or os.path.join(ROOT, 'server.py'), encoding='utf-8-sig').read()
    src = src.replace("if __name__ == '__main__':", "if False:")
    srv = types.ModuleType('srv')
    srv.__dict__['__file__'] = os.path.join(ROOT, 'server.py')
    exec(compile(src, 'server.py', 'exec'), srv.__dict__)
    return srv


SRV = load_server(os.environ.get('OI_SERVER', ''))
TEAM_SIZE = 5
ENERGY = 40.0


def apply_overrides(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for cid, patch in data.items():
        card = SRV.CARD_BY_ID[cid]
        for k, v in patch.items():
            card[k] = v
    return data


def make_player(pid, card_id, cells):
    return {
        'id': pid, 'mind': 100, 'energy': ENERGY,
        'board': {f'{x},{y}': {'card': card_id,
                               'hp': SRV.effective_max_hp(SRV.CARD_BY_ID[card_id])}
                  for (x, y) in cells},
    }


def battle(rng, card_a, card_b):
    """返回 A 方的净优势：剩余血量占比之差（+ 表示 A 强）。"""
    cells = rng.sample([(x, y) for x in range(SRV.HALF_W) for y in range(SRV.HALF_H)],
                       TEAM_SIZE)
    a = make_player('A', card_a, cells)
    b = make_player('B', card_b, cells)
    rnd = rng.randint(2, 9)
    room = SRV.Room('lab', 'A')
    frames, events, a_hp, b_hp = room._simulate_battle(a, b, rnd, record=False)

    def frac(hp_map, board):
        total = sum(SRV.effective_max_hp(SRV.CARD_BY_ID[i['card']]) for i in board.values())
        return sum(max(0, v) for v in hp_map.values()) / max(1, total)

    return frac(a_hp, a['board']), frac(b_hp, b['board'])


def run_round_robin(ids, trials, seed=20261107):
    """返回 {(x,y): [x 的平均剩余血量占比, y 的 ...]}, x 始终是字典序较小的那个。"""
    rng = random.Random(seed)
    results = {}
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            mx = my = 0.0
            for t in range(trials):
                # 交替先后手，抵消「单位列表里先手方每个 tick 先行动」的微小优势
                if t % 2 == 0:
                    ax, by = battle(rng, x, y)
                else:
                    by, ax = battle(rng, y, x)
                mx += ax
                my += by
            results[(x, y)] = (mx / trials, my / trials)
    return results


def bradley_terry(ids, results, iters=200):
    """极大似然拟合战力倍率；平局按 0.5 胜计。"""
    gamma = {c: 1.0 for c in ids}
    for _ in range(iters):
        new = {}
        for c in ids:
            wins = 0.0
            denom = 0.0
            for (x, y), (mx, my) in results.items():
                if c not in (x, y):
                    continue
                if x == c:
                    s, o = mx, my
                else:
                    s, o = my, mx
                n = 1.0
                p = 0.5 if abs(s - o) < 0.02 else (1.0 if s > o else 0.0)
                wins += n * p
                denom += n / (gamma[x] + gamma[y])
            new[c] = wins / denom if denom else gamma[c]
        tot = sum(new.values()) / len(new)
        gamma = {c: max(0.05, v / tot) for c, v in new.items()}
    return gamma


def intra_tier_bt(rows_gamma, results):
    """在每个费用层内部单独拟合一次，剥离「跨费用强弱」的干扰，只看同费之间的技能差异。"""
    tiers = {}
    for c in rows_gamma:
        tiers.setdefault(SRV.CARD_BY_ID[c]['cost'], []).append(c)
    rel = {}
    for cost, ids in tiers.items():
        if len(ids) < 2:
            for c in ids:
                rel[c] = 1.0
            continue
        sub = {k: v for k, v in results.items()
               if k[0] in ids and k[1] in ids}
        g = bradley_terry(ids, sub)
        mean = sum(g.values()) / len(g)
        for c, v in g.items():
            rel[c] = v / mean
    return rel


def margin_scores(ids, results):
    """每张卡对所有对手的平均净剩余血量差（-1~+1）。
    每张卡面对的是同一批对手，所以这个值可以直接横向比较；比胜负计数稳健得多。"""
    score = {c: [] for c in ids}
    for (x, y), (mx, my) in results.items():
        score[x].append(mx - my)
        score[y].append(my - mx)
    return {c: sum(v) / len(v) for c, v in score.items()}


def summarize(gamma, results):
    rows = []
    cards = SRV.CARD_BY_ID
    margins = margin_scores(list(gamma), results)
    for c in gamma:
        card = cards[c]
        wins = draws = losses = 0
        for (x, y), (mx, my) in results.items():
            if c not in (x, y):
                continue
            s, o = (mx, my) if x == c else (my, mx)
            if abs(s - o) < 0.02:
                draws += 1
            elif s > o:
                wins += 1
            else:
                losses += 1
        rows.append({
            'id': c, 'name': card['name'], 'cost': card['cost'],
            'difficulty': card['difficulty'], 'energy': card['energy'],
            'reason': card['reason'], 'attack': card['attack'], 'hp': card['hp'],
            'power': round(gamma[c], 4),
            'margin': round(margins[c], 4),
            'wins': wins, 'draws': draws, 'losses': losses,
            'wr': round((wins + 0.5 * draws) / max(1, wins + draws + losses), 3),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--trials', type=int, default=14, help='每对卡的对战次数')
    ap.add_argument('--apply', help='套用数值改动 json')
    ap.add_argument('--json', help='把结果写到 json')
    ap.add_argument('--ids', help='只测这些卡（逗号分隔），默认全部')
    ap.add_argument('--server', help='测另一份 server.py（例如历史版本）')
    args = ap.parse_args()

    global SRV
    if args.server:
        SRV = load_server(args.server)
    if args.apply:
        apply_overrides(args.apply)

    ids = args.ids.split(',') if args.ids else [c['id'] for c in SRV.CARDS]
    with contextlib.redirect_stdout(io.StringIO()):
        results = run_round_robin(ids, args.trials)
    gamma = bradley_terry(ids, results)
    rows = summarize(gamma, results)
    intra = intra_tier_bt(ids, results)
    for r in rows:
        r['intra'] = round(intra[r['id']], 3)

    # 同费单独归一化：以该费用层平均净胜血量为基准
    by_cost = {}
    for r in rows:
        by_cost.setdefault(r['cost'], []).append(r)
    print(f"{'费':>2} {'卡牌':14}{'难度':>4}{'精/理':>7}{'攻':>5}{'血':>6}{'净胜血量':>8}{'同费相对':>9}  胜-平-负")
    for cost in sorted(by_cost):
        tier = by_cost[cost]
        mean = sum(r['margin'] for r in tier) / len(tier)
        for r in sorted(tier, key=lambda r: -r['margin']):
            r['rel'] = round(r['margin'] - mean, 3)
            print(f"{cost:>2} {r['name']:14}{r['difficulty']:>4}"
                  f"{str(r['energy'])+'/'+str(r['reason']):>7}"
                  f"{r['attack']:>5}{r['hp']:>6}{r['margin']:>+8.3f}{r['rel']:>+9.3f}"
                  f"  {r['wins']}-{r['draws']}-{r['losses']}")
        print(f"   —— {cost} 费均值 {mean:+.3f}，同费极差 "
              f"{max(r['rel'] for r in tier):+.3f} ~ {min(r['rel'] for r in tier):+.3f}"
              + ('' if len(tier) > 1 else '（该费用只有 1 张卡）'))
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print('已写入', args.json)


if __name__ == '__main__':
    main()
