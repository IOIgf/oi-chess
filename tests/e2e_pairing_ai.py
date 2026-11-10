"""端到端验证：奇数人轮空轮换 + 加电脑的时间窗口（真实 HTTP）。

覆盖三条边界：
  1. 轮空公平：奇数人数时每轮 1 人轮空，且轮空者会换人
  2. 开局之前：等待大厅里房主可以随时加减电脑（凑成偶数后不再有人轮空）
  3. 开局之后：准备期与战斗期调用 addAi / removeAi 一律被拒绝，且房间状态不受影响
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


def try_add_ai(pid, level='easy'):
    """调用 addAi，成功返回结果，失败返回 (status, error)。"""
    try:
        res = api('/api/action', 'POST',
                  {'playerId': pid, 'action': 'addAi', 'level': level})
        return 200, res
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode('utf-8'))
        return e.code, body


def try_remove_ai(pid, ai_id):
    """调用 removeAi，成功返回结果，失败返回 (status, error)。"""
    try:
        res = api('/api/action', 'POST',
                  {'playerId': pid, 'action': 'removeAi', 'aiId': ai_id})
        return 200, res
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode('utf-8'))
        return e.code, body


def log_byes():
    txt = open(LOG, encoding='utf-8', errors='replace').read()
    return re.findall(r'\[配对\] (.+?) 轮空', txt)


def wait_state(pid, want, pred=None, timeout=45):
    deadline = time.time() + timeout
    st = state(pid)
    while time.time() < deadline:
        st = state(pid)
        if st['state'] == want and (pred is None or pred(st)):
            return st
        time.sleep(0.4)
    return st


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

        # ================= 第 1 局：3 名真人（不加电脑）====================
        r1 = api('/api/rooms', 'POST',
                 {'clientId': 'e2e-1', 'name': '甲', 'aiCount': 0, 'aiLevel': 'normal'})
        rid = r1['roomId']
        api('/api/join', 'POST', {'clientId': 'e2e-2', 'name': '乙', 'roomId': rid})
        api('/api/join', 'POST', {'clientId': 'e2e-3', 'name': '丙', 'roomId': rid})
        ok(len(state('e2e-1')['players']) == 3, '三名真人进入同一房间')

        # 等待大厅里房主可以加电脑 -> 这一局也顺便验证「开局前可加」
        code, body = try_add_ai('e2e-1', 'hard')
        ok(code == 200 and str(body.get('aiId', '')).startswith('ai:'),
           f'开局之前房主可以加电脑（aiId={body.get("aiId")}）')
        st = state('e2e-1')
        ok(len(st['players']) == 4, '加完电脑后房间 4 人')
        ai_id = body['aiId']
        ok(st['players'][ai_id]['isAi'] is True, '新成员被标记为电脑')
        ok(st['players'][ai_id]['ready'] is False, '等待期的电脑还没准备（等开局）')
        code2, body2 = try_add_ai('e2e-2', 'easy')
        ok(code2 == 400 and '房主' in body2.get('error', ''),
           '非房主加电脑被拒绝：' + body2.get('error', ''))

        # --- 移除电脑：与加电脑同一窗口（只有开局之前） ---
        rc, rb = try_remove_ai('e2e-2', ai_id)
        ok(rc == 400 and '房主' in rb.get('error', ''),
           '非房主移除电脑被拒绝：' + rb.get('error', ''))
        ok(len(state('e2e-1')['players']) == 4,
           '被拒绝的移除没有改变人数')
        rc2, rb2 = try_remove_ai('e2e-1', 'ai:不存在的')
        ok(rc2 == 400 and '不在房间里' in rb2.get('error', ''),
           '移除不存在的电脑被拒绝：' + rb2.get('error', ''))
        ai_color = st['players'][ai_id].get('color')
        rc3, rb3 = try_remove_ai('e2e-1', ai_id)
        ok(rc3 == 200, '等待期房主可以移除电脑')
        st = state('e2e-1')
        ok(len(st['players']) == 3, '移除后房间回到 3 人')
        ok(ai_id not in st['players'], '被移除的电脑不再出现在玩家列表里')
        ok(all(q.get('color') != ai_color for q in st['players'].values()),
           '被移除的电脑释放了颜色槽位（没有别人还占着它的颜色）')
        rc4, rb4 = try_remove_ai('e2e-1', ai_id)
        ok(rc4 == 400, '重复移除同一台电脑被拒绝')

        # 移除后可以再补一台，继续用 4 人偶数开局
        code5, body5 = try_add_ai('e2e-1', 'hard')
        ok(code5 == 200 and str(body5.get('aiId', '')).startswith('ai:'),
           '移除之后还能再加电脑')
        ai_id = body5['aiId']
        ok(len(state('e2e-1')['players']) == 4, '补完电脑后房间 4 人')
        api('/api/action', 'POST', {'playerId': 'e2e-1', 'action': 'start'})
        ok(state('e2e-1')['state'] == 'prep', '开局进入准备期')
        ok(state(ai_id)['players'][ai_id]['ready'] is True,
           '开局后电脑自动点了「准备」')
        ok(len(state(ai_id)['players'][ai_id].get('board') or {}) > 0,
           '开局后电脑完成了买卡布阵')

        # 3. 开局之后不能再加电脑
        code3, body3 = try_add_ai('e2e-1', 'easy')
        ok(code3 == 400 and '游戏已开始' in body3.get('error', ''),
           '准备期加电脑被拒绝：' + body3.get('error', ''))
        ok(len(state('e2e-1')['players']) == 4, '被拒绝的加电脑没有改变人数')

        # 开局之后也不能移除电脑
        code3r, body3r = try_remove_ai('e2e-1', ai_id)
        ok(code3r == 400 and '游戏已开始' in body3r.get('error', ''),
           '准备期移除电脑被拒绝：' + body3r.get('error', ''))
        ok(len(state('e2e-1')['players']) == 4, '被拒绝的移除没有改变人数')

        for pid in ('e2e-1', 'e2e-2', 'e2e-3'):
            ready(pid)
        st = wait_state('e2e-1', 'battle', timeout=15)
        ok(st['state'] == 'battle', '全员就绪后立即开战')
        ok(len(log_byes()) == 0, f'4 人偶数局没人轮空（日志：{log_byes()}）')

        # 战斗期也不能加
        code4, body4 = try_add_ai('e2e-1', 'easy')
        ok(code4 == 400 and '游戏已开始' in body4.get('error', ''),
           '战斗期加电脑被拒绝：' + body4.get('error', ''))
        ok(len(state('e2e-1')['players']) == 4, '战斗期被拒绝的加电脑没有改变人数')

        # ================= 第 2 局：3 名真人奇数局，验证轮空换人 ==========
        r2 = api('/api/rooms', 'POST',
                 {'clientId': 'e2e-4', 'name': '丁', 'aiCount': 0, 'aiLevel': 'normal'})
        rid2 = r2['roomId']
        api('/api/join', 'POST', {'clientId': 'e2e-5', 'name': '戊', 'roomId': rid2})
        api('/api/join', 'POST', {'clientId': 'e2e-6', 'name': '己', 'roomId': rid2})
        api('/api/action', 'POST', {'playerId': 'e2e-4', 'action': 'start'})
        for pid in ('e2e-4', 'e2e-5', 'e2e-6'):
            ready(pid)
        st = wait_state('e2e-4', 'battle', timeout=15)
        ok(st['state'] == 'battle', '奇数局全员就绪后开战')
        byes1 = log_byes()
        ok(len(byes1) == 1, f'3 人奇数局恰好 1 人轮空（日志：{byes1}）')

        st = wait_state('e2e-4', 'prep', lambda s: s['round'] >= 2, timeout=45)
        ok(st['state'] == 'prep' and st['round'] >= 2, '第 1 回合结算后进入第 2 回合')
        for pid in ('e2e-4', 'e2e-5', 'e2e-6'):
            ready(pid)
        st = wait_state('e2e-4', 'battle', timeout=15)
        byes2 = log_byes()
        ok(len(byes2) == 2, f'第 2 轮又轮空 1 人（累计日志：{byes2}）')
        ok(byes2[0] != byes2[1],
           f'轮空者换人了：第 1 轮 {byes2[0]} → 第 2 轮 {byes2[1]}')
        bye_rows = [p['name'] for p in st['players'].values() if p.get('byeCount')]
        ok(len(bye_rows) >= 1, f'轮空次数对玩家可见：{bye_rows}')

        print('PASS e2e pairing + add/remove-ai window: %d checks' % len(checks))
        return 0
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except Exception:
            srv.kill()


if __name__ == '__main__':
    sys.exit(main())
