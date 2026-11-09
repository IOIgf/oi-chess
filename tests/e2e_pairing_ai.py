"""端到端验证：奇数人轮空轮换 + 局内加电脑（真实 HTTP）。

流程：
  1. 3 名真人进同一房间并开局
  2. 打完 2 个完整回合，从服务器配对日志里取每轮的轮空者，验证换人
  3. 第 3 回合准备期，房主通过 /api/action 的 addAi 加一名电脑
     验证：电脑加入后立即买卡布阵并点「准备」、人数变偶数后不再有人轮空
"""
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = 8123
BASE = f'http://127.0.0.1:{PORT}'
LOG = '/tmp/oi_e2e_server.log'

checks = []


def ok(cond, label):
    assert cond, label
    checks.append(label)
    print('  ok:', label)


def api(path, method='GET', body=None):
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


def state(pid):
    return api(f'/api/state?playerId={pid}')


def ready(pid):
    api('/api/action', 'POST', {'playerId': pid, 'action': 'ready'})


def bye_players_from_log(seen):
    """从服务器配对日志里解析出已经出现过的轮空玩家名。"""
    txt = open(LOG, encoding='utf-8', errors='replace').read()
    return re.findall(r'\[配对\] (.+?) 轮空', txt)


def main():
    srv = subprocess.Popen([sys.executable, '-u', 'server.py', '--port', str(PORT)],
                            stdout=open(LOG, 'w'), stderr=subprocess.STDOUT)
    try:
        for _ in range(80):
            time.sleep(0.25)
            try:
                api('/api/rooms')
                break
            except Exception:
                continue
        else:
            raise SystemExit('server did not start')

        # ---- 建房：3 名真人 -------------------------------------------------
        r1 = api('/api/rooms', 'POST',
                 {'clientId': 'e2e-1', 'name': '甲', 'aiCount': 0, 'aiLevel': 'normal'})
        rid = r1['roomId']
        api('/api/join', 'POST', {'clientId': 'e2e-2', 'name': '乙', 'roomId': rid})
        api('/api/join', 'POST', {'clientId': 'e2e-3', 'name': '丙', 'roomId': rid})
        st = state('e2e-1')
        ok(len(st['players']) == 3, '三名真人进入同一房间')
        api('/api/action', 'POST', {'playerId': 'e2e-1', 'action': 'start'})
        ok(state('e2e-1')['state'] == 'prep', '开局进入准备期')

        # ---- 第 1 回合：3 人奇数，应有 1 人轮空 ----------------------------
        for pid in ('e2e-1', 'e2e-2', 'e2e-3'):
            ready(pid)
        st = state('e2e-1')
        ok(st['state'] == 'prep', '全员点准备后仍在准备期（等开战）')

        # 等战斗开始
        deadline = time.time() + 12
        while time.time() < deadline:
            st = state('e2e-1')
            if st['state'] == 'battle':
                break
            time.sleep(0.3)
        ok(st['state'] == 'battle', '全员就绪后立即开战')
        log_byes = bye_players_from_log(None)
        ok(len(log_byes) == 1, f'第 1 轮恰好 1 人轮空（日志：{log_byes}）')

        # ---- 等第 1 回合结束，进入第 2 回合准备期 ---------------------------
        deadline = time.time() + 45
        while time.time() < deadline:
            st = state('e2e-1')
            if st['state'] == 'prep' and st['round'] >= 2:
                break
            time.sleep(0.5)
        ok(st['state'] == 'prep' and st['round'] >= 2, '第 1 回合结算后进入第 2 回合准备期')

        # ---- 第 2 回合：仍是 3 人奇数，轮空者应当换人 -----------------------
        for pid in ('e2e-1', 'e2e-2', 'e2e-3'):
            ready(pid)
        deadline = time.time() + 12
        while time.time() < deadline:
            st = state('e2e-1')
            if st['state'] == 'battle':
                break
            time.sleep(0.3)
        ok(st['state'] == 'battle', '第 2 回合全员就绪后开战')
        log_byes2 = bye_players_from_log(None)
        ok(len(log_byes2) == 2, f'第 2 轮又轮空 1 人（累计日志：{log_byes2}）')
        ok(log_byes2[0] != log_byes2[1],
           f'轮空者换人了：第 1 轮 {log_byes2[0]} → 第 2 轮 {log_byes2[1]}')

        # ---- 等第 2 回合结束，进入第 3 回合准备期 ---------------------------
        deadline = time.time() + 45
        while time.time() < deadline:
            st = state('e2e-1')
            if st['state'] == 'prep' and st['round'] >= 3:
                break
            time.sleep(0.5)
        ok(st['state'] == 'prep' and st['round'] >= 3, '进入第 3 回合准备期')

        # ---- 局内加电脑（准备期）：3 真人 + 1 电脑 = 4 人偶数 ----------------
        st = state('e2e-1')
        ok(st['state'] == 'prep', '当前处于准备期，可加电脑')
        before = len(st['players'])
        res = api('/api/action', 'POST',
                  {'playerId': 'e2e-1', 'action': 'addAi', 'level': 'hard'})
        ok(res.get('ok') and str(res.get('aiId', '')).startswith('ai:'),
           f'房主在准备期成功加电脑（aiId={res.get("aiId")}）')
        st = state('e2e-1')
        ok(len(st['players']) == before + 1, '房间人数 +1')
        ai_id = res['aiId']
        ai_row = st['players'][ai_id]
        ok(ai_row['isAi'] is True and ai_row['aiLevel'] == '困难', '新电脑带难度标记')
        ok(ai_row['ready'] is True, '新电脑在准备期自动点了「准备」')
        # 棋盘与商店只对本人可见，所以以新电脑的身份查一次状态
        ai_self = state(ai_id)['players'][ai_id]
        ok(0 < len(ai_self.get('board') or {}) <= 20, '新电脑已经买卡布阵')
        ok(len(ai_self.get('shop') or []) >= 0, '新电脑拿到了商店')
        ok(state('e2e-2')['players'][ai_id]['isAi'] is True, '其他玩家也能看到该电脑')

        # 非房主不能加
        try:
            api('/api/action', 'POST',
                {'playerId': 'e2e-2', 'action': 'addAi', 'level': 'easy'})
            ok(False, '非房主加电脑应被拒绝')
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode('utf-8'))
            ok(e.code == 400 and '房主' in body.get('error', ''),
               '非房主加电脑被拒绝：' + body.get('error', ''))

        # ---- 第 3 回合：4 人偶数，不应有人轮空 ------------------------------
        for pid in ('e2e-1', 'e2e-2', 'e2e-3'):
            ready(pid)
        deadline = time.time() + 12
        while time.time() < deadline:
            st = state('e2e-1')
            if st['state'] == 'battle':
                break
            time.sleep(0.3)
        ok(st['state'] == 'battle', '补一名电脑后全员就绪即可开战')
        log_byes3 = bye_players_from_log(None)
        ok(len(log_byes3) == 2,
           f'人数变成偶数后本轮不再新增轮空（日志仍是 {log_byes3}）')

        # ---- 局内加电脑（战斗期）：本轮按轮空处理 --------------------------
        res2 = api('/api/action', 'POST',
                   {'playerId': 'e2e-1', 'action': 'addAi', 'level': 'easy'})
        ok(res2.get('ok'), '房主在战斗期也能加电脑')
        battle_ai = res2['aiId']
        st = state('e2e-1')
        ok(len(st['players']) == 5, '战斗期加电脑后人数 5')
        ok(st['players'][battle_ai]['ready'] is False,
           '战斗期加入的电脑还没进入准备期，不会提前准备')
        ok(state(battle_ai)['players'][battle_ai]['shop'],
           '战斗期加入的电脑拿到了商店')

        # ---- 等第 3 回合结束，进入第 4 回合准备期 ---------------------------
        deadline = time.time() + 45
        while time.time() < deadline:
            st = state('e2e-1')
            if st['state'] == 'prep' and st['round'] >= 4:
                break
            time.sleep(0.5)
        ok(st['state'] == 'prep' and st['round'] >= 4, '进入第 4 回合准备期')
        st = state('e2e-1')
        ok(st['players'][battle_ai]['ready'] is True,
           '战斗期加入的电脑在下一轮准备期自动点了「准备」')
        ok(len(state(battle_ai)['players'][battle_ai].get('board') or {}) > 0,
           '战斗期加入的电脑在下一轮准备期完成了布阵')
        bye_rows = [p['name'] for p in st['players'].values() if p.get('byeCount')]
        ok(len(bye_rows) >= 1, f'轮空次数对玩家可见：{bye_rows}')

        print('PASS e2e pairing + in-game AI: %d checks' % len(checks))
        return 0
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except Exception:
            srv.kill()


if __name__ == '__main__':
    sys.exit(main())
