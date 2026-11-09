"""8 人整局压力测试：随机买/卖/刷/收回/布阵/聊天，跑到对局结束，全程校验数值与配对不变量。

建议把服务器的准备/战斗时间调短后再跑（否则一局要 10 分钟）：
    # 临时改成 PREP_TIME = 2.0, BATTLE_TIME = 12.0, PORT = 8096 再启动
    OI_BASE=http://127.0.0.1:8096 python tests/stress_game.py

校验项：
  hp>=0 / 心态·精力·理智∈[0,100] / 金币>=0 / 场上<=15 / 备战席<=10 / 商店<=5
  战斗期每名存活玩家恰好一个对手或轮空，配对对称且无重复
"""
import json
import os
import random
import time
import urllib.request as u

BASE = os.environ.get('OI_BASE', 'http://127.0.0.1:8080').rstrip('/')
LIMIT = float(os.environ.get('OI_SECONDS', '160'))


def req(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = u.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        with u.urlopen(r) as f:
            return f.status, json.loads(f.read())
    except u.HTTPError as e:
        return e.code, {'raw': e.read()[:160]}
    except Exception as e:
        return 'DROP', {'raw': str(e)[:160]}


def check(pid, m, viol):
    for k, (lo, hi) in {'hp': (0, None), 'mind': (0, 100), 'energy': (0, 100),
                        'reason': (0, 100), 'gold': (0, None)}.items():
        v = m.get(k)
        if v is None:
            continue
        if v < lo or (hi is not None and v > hi):
            viol.append((pid, k, v))
    if len(m.get('board', {})) > 15:
        viol.append((pid, 'board', len(m['board'])))
    if len(m.get('bench', [])) > 10:
        viol.append((pid, 'bench', len(m['bench'])))
    if len(m.get('shop', [])) > 5:
        viol.append((pid, 'shop', len(m['shop'])))


def main():
    ids = ['stress%d' % i for i in range(8)]
    s, r = req('/api/rooms', {'clientId': ids[0], 'name': 'S0'})
    assert s == 200, (s, r)
    rid = r['roomId']
    for i in ids[1:]:
        req('/api/join', {'clientId': i, 'name': i, 'roomId': rid})
    req('/api/action', {'playerId': ids[0], 'action': 'start'})

    viol, pair_bad, acted, seen = [], [], 0, set()
    t0 = time.time()
    while time.time() - t0 < LIMIT:
        st, d = req('/api/state?playerId=' + ids[0])
        if st != 200:
            print('状态接口异常', st, d)
            break
        for pid, p in d['players'].items():
            if not p['dead'] and (pid == ids[0] or random.random() < 0.35):
                check(pid, p, viol)

        if d['state'] == 'battle' and d['round'] not in seen:
            seen.add(d['round'])
            opp, bye, alive = {}, [], set()
            for pid in ids:
                _, dd = req('/api/state?playerId=' + pid)
                if dd['players'][pid]['dead']:
                    continue
                alive.add(pid)
                if dd.get('viewerBye'):
                    bye.append(pid)
                elif dd.get('opponentId'):
                    opp[pid] = dd['opponentId']
                check(pid, dd['players'][pid], viol)
            sym = all(opp.get(v) == k for k, v in opp.items())
            ok = sym and len(set(opp.values())) == len(opp) and (set(opp) | set(bye)) == alive
            print(f"  R{d['round']}: 存活 {len(alive)} 场配对 {len(opp)//2} 轮空 {bye} "
                  + ('OK' if ok else '!! 配对异常'))
            if not ok:
                pair_bad.append(d['round'])

        if d['state'] == 'prep':
            for pid in ids:
                _, dd = req('/api/state?playerId=' + pid)
                m = dd['players'][pid]
                if m['dead']:
                    continue
                for _ in range(6):
                    roll = random.random()
                    if roll < 0.45:
                        req('/api/action', {'playerId': pid, 'action': 'buy', 'index': 0})
                    elif roll < 0.55:
                        req('/api/action', {'playerId': pid, 'action': 'refresh'})
                    elif roll < 0.65 and m['bench']:
                        req('/api/action', {'playerId': pid, 'action': 'sell',
                                            'source': 'bench', 'index': 0})
                    elif roll < 0.72 and m['board']:
                        x, y = map(int, random.choice(list(m['board'])).split(','))
                        req('/api/action', {'playerId': pid, 'action': 'retrieve', 'x': x, 'y': y})
                    acted += 1
                    _, dd = req('/api/state?playerId=' + pid)
                    m = dd['players'][pid]
                occ = set(m['board'])
                for bi in range(len(m['bench']) - 1, -1, -1):
                    if len(m['board']) >= 15:
                        break
                    for _t in range(30):
                        x, y = random.randint(0, 7), random.randint(0, 3)
                        if f'{x},{y}' in occ:
                            continue
                        if req('/api/action', {'playerId': pid, 'action': 'place',
                                               'benchIndex': bi, 'x': x, 'y': y})[0] == 200:
                            occ.add(f'{x},{y}')
                            break
                if random.random() < 0.15:
                    req('/api/chat', {'playerId': pid, 'text': random.choice(
                        ['gg', '<b>x</b>', '中文测试', 'a' * 180])})

        if d['state'] == 'ended':
            print('对局结束，winner =', d['winner'])
            print('最终:', {k: (v['hp'], v['gold'], v['mind'], v['dead'])
                          for k, v in d['players'].items()})
            break
        time.sleep(0.15)

    print(f'共 {acted} 次操作；数值越界 {len(viol)} 条；配对小轮 {pair_bad}')
    for x in viol[:10]:
        print('  !!', x)
    return 0 if not viol and not pair_bad else 1


if __name__ == '__main__':
    raise SystemExit(main())
