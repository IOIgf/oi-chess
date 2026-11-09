"""加电脑入口的界面复核（需要本地已启动的服务器）。

验证：
  1. 等待大厅里房主能看到「+ 添加电脑」与难度下拉，点击后确实加进一名电脑
  2. 非房主在大厅里看不到该控件
  3. 点「开始游戏」进入对局后，界面里不再出现任何加电脑入口
  4. 大厅控件在窄屏 / 半屏下不溢出大厅面板

用法：OI_BASE=http://127.0.0.1:8080 python3 tests/ui_ai_control_check.py
"""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get('OI_BASE', 'http://127.0.0.1:8080')
OUT = os.environ.get('OI_SHOT_DIR', '/tmp/oi_ui_ai')
checks = []


def ok(cond, label):
    assert cond, label
    checks.append(label)
    print('  ok:', label)


def req(path, body):
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode('utf-8'),
                               method='POST', headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(r, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


def visible(pg, sel):
    return pg.eval_on_selector(
        sel, "el => !!el && getComputedStyle(el).display !== 'none' "
             "&& el.getBoundingClientRect().width > 0")


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
        pg = ctx.new_page()
        pg.goto(BASE, wait_until='domcontentloaded')
        cid = pg.evaluate("localStorage.getItem('oi_client_id')")
        room = req('/api/rooms', {'clientId': cid, 'name': '房主', 'aiCount': 0})
        rid = room['roomId']

        # 第二个真人（独立上下文，稍后验证他看不到加电脑控件）
        ctx2 = browser.new_context(viewport={'width': 1280, 'height': 800})
        pg2 = ctx2.new_page()
        pg2.goto(BASE, wait_until='domcontentloaded')
        cid2 = pg2.evaluate("localStorage.getItem('oi_client_id')")
        req('/api/join', {'clientId': cid2, 'name': '路人乙', 'roomId': rid})
        pg2.evaluate("rid => localStorage.setItem('oi_room_id', rid)", rid)
        pg2.reload(wait_until='domcontentloaded')

        pg.evaluate("rid => localStorage.setItem('oi_room_id', rid)", rid)
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_timeout(1500)

        # ---- 1. 等待大厅：房主能看到并使用「+ 添加电脑」 --------------------
        ok(pg.evaluate("document.getElementById('lobby') && "
                       "!document.getElementById('lobby').classList.contains('hidden')"),
           '进入等待大厅')
        ok(visible(pg, '#aiControls'), '房主在大厅能看到「+ 添加电脑」控件')
        ok(visible(pg, '#lobbyAiLevel'), '大厅难度下拉可见')
        pg.screenshot(path=OUT + '/lobby_host_1280.png')

        before = len(get(f'/api/state?playerId={cid}')['players'])
        pg.click('#aiControls button')
        pg.wait_for_timeout(1200)
        after_state = get(f'/api/state?playerId={cid}')
        ok(len(after_state['players']) == before + 1,
           f'点击后房间人数 {before} → {len(after_state["players"])}')
        ok(any(p.get('isAi') for p in after_state['players'].values()),
           '新成员被标记为电脑')
        pg.screenshot(path=OUT + '/lobby_host_after_add.png')

        # ---- 2. 非房主在大厅看不到控件 ------------------------------------
        pg2.wait_for_timeout(1000)
        ok(not visible(pg2, '#aiControls'), '非房主在大厅看不到「+ 添加电脑」')
        pg2.screenshot(path=OUT + '/lobby_guest.png')

        # ---- 3. 大厅控件在窄屏 / 半屏不溢出 --------------------------------
        for w, h, tag in ((390, 844, 'phone'), (844, 390, 'half')):
            pg.set_viewport_size({'width': w, 'height': h})
            pg.wait_for_timeout(700)
            box = pg.evaluate("""() => {
              const c = document.getElementById('aiControls').getBoundingClientRect();
              const panel = document.querySelector('.lobby-content').getBoundingClientRect();
              return {cl: c.left, cr: c.right, ct: c.top, cb: c.bottom,
                      pl: panel.left, pr: panel.right, pt: panel.top, pb: panel.bottom,
                      vw: innerWidth, vh: innerHeight};
            }""")
            ok(box['cl'] >= box['pl'] - 1 and box['cr'] <= box['pr'] + 1,
               f'{tag} {w}x{h}：控件横向不溢出大厅面板')
            ok(box['ct'] >= box['pt'] - 1 and box['cb'] <= box['pb'] + 1,
               f'{tag} {w}x{h}：控件纵向不溢出大厅面板')
            pg.screenshot(path=f'{OUT}/lobby_host_{tag}.png')
        pg.set_viewport_size({'width': 1280, 'height': 800})
        pg.wait_for_timeout(400)

        # ---- 4. 开局后界面里不再有加电脑入口 ------------------------------
        req('/api/action', {'playerId': cid, 'action': 'start'})
        pg.wait_for_timeout(1600)
        ok(pg.evaluate("document.getElementById('game') && "
                       "!document.getElementById('game').classList.contains('hidden')"),
           '已进入游戏界面')
        ok(pg.evaluate("!document.getElementById('gameAiControls')"),
           '游戏界面里没有局内加电脑控件')
        ok(pg.evaluate("!document.getElementById('gameAiLevel')"),
           '游戏界面里没有局内难度下拉')
        ok(not visible(pg, '#aiControls'),
           '游戏界面里也不再显示大厅的加电脑控件')
        pg.screenshot(path=OUT + '/host_game_1280.png')

        browser.close()
    print('PASS ui ai control: %d checks（截图目录 %s）' % (len(checks), OUT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
