"""移除电脑入口的界面复核（需要本地已启动的服务器）。

验证：
  1. 等待大厅里房主能看到每台电脑旁的「移除」按钮，点一下确实少一名电脑
  2. 非房主在大厅里看不到任何「移除」按钮
  3. 点「开始游戏」进入对局后，界面上不再出现移除入口
  4. 移除按钮在窄屏 / 半屏下不溢出大厅面板

用法：OI_BASE=http://127.0.0.1:8080 python3 tests/ui_remove_ai_check.py
"""
import json
import os
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get('OI_BASE', 'http://127.0.0.1:8080')
OUT = os.environ.get('OI_SHOT_DIR', '/tmp/oi_ui_removeai')
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
    with urllib.request.urlopen(BASE, timeout=10) as resp:
        pass


def state(cid):
    with urllib.request.urlopen(BASE + '/api/state?playerId=' + cid, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
        pg = ctx.new_page()
        pg.goto(BASE, wait_until='domcontentloaded')
        cid = pg.evaluate("localStorage.getItem('oi_client_id')")
        room = req('/api/rooms', {'clientId': cid, 'name': '房主', 'aiCount': 2})
        rid = room['roomId']

        ctx2 = browser.new_context(viewport={'width': 1280, 'height': 800})
        pg2 = ctx2.new_page()
        pg2.goto(BASE, wait_until='domcontentloaded')
        cid2 = pg2.evaluate("localStorage.getItem('oi_client_id')")
        req('/api/join', {'clientId': cid2, 'name': '路人乙', 'roomId': rid})

        pg.evaluate("rid => localStorage.setItem('oi_room_id', rid)", rid)
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_timeout(1500)

        # ---- 1. 房主在大厅能看到并使用「移除」 ----------------------------
        ok(pg.evaluate("document.getElementById('lobby') && "
                       "!document.getElementById('lobby').classList.contains('hidden')"),
           '进入等待大厅')
        n_ai = sum(1 for p in state(cid)['players'].values() if p.get('isAi'))
        ok(n_ai == 2, '房间里有两名电脑')
        ok(pg.evaluate("document.querySelectorAll('.remove-ai').length") == 2,
           '每台电脑旁边都有一个「移除」按钮')
        pg.screenshot(path=OUT + '/lobby_host_1280.png')

        pg.click('.remove-ai')
        pg.wait_for_timeout(1200)
        after = state(cid)
        n_ai2 = sum(1 for q in after['players'].values() if q.get('isAi'))
        ok(n_ai2 == 1, '点击移除后电脑从 2 名变成 1 名')
        ok(pg.evaluate("document.querySelectorAll('.remove-ai').length") == 1,
           '剩下的电脑仍有移除按钮')
        pg.screenshot(path=OUT + '/lobby_host_after_remove.png')

        # ---- 2. 非房主看不到移除按钮 --------------------------------------
        pg2.evaluate("rid => localStorage.setItem('oi_room_id', rid)", rid)
        pg2.reload(wait_until='domcontentloaded')
        pg2.wait_for_timeout(1500)
        ok(pg2.evaluate("document.querySelectorAll('.remove-ai').length") == 0,
           '非房主看不到任何「移除」按钮')
        pg2.screenshot(path=OUT + '/lobby_guest.png')

        # ---- 3. 窄屏 / 半屏不溢出 ------------------------------------------
        for w, h, tag in ((390, 844, 'phone'), (844, 390, 'half')):
            pg.set_viewport_size({'width': w, 'height': h})
            pg.wait_for_timeout(700)
            box = pg.evaluate("""() => {
              const el = document.querySelector('.remove-ai');
              if (!el) return null;
              const c = el.getBoundingClientRect();
              const panel = document.querySelector('.lobby-content').getBoundingClientRect();
              return {cl: c.left, cr: c.right, ct: c.top, cb: c.bottom,
                      pl: panel.left, pr: panel.right, pt: panel.top, pb: panel.bottom};
            }""")
            ok(box is not None, f'{tag} {w}x{h}：移除按钮存在')
            ok(box['cl'] >= box['pl'] - 1 and box['cr'] <= box['pr'] + 1,
               f'{tag} {w}x{h}：移除按钮横向不溢出大厅面板')
            ok(box['ct'] >= box['pt'] - 1 and box['cb'] <= box['pb'] + 1,
               f'{tag} {w}x{h}：移除按钮纵向不溢出大厅面板')
            pg.screenshot(path=f'{OUT}/lobby_host_{tag}.png')
        pg.set_viewport_size({'width': 1280, 'height': 800})
        pg.wait_for_timeout(400)

        # ---- 4. 开局后界面里没有移除入口 ----------------------------------
        req('/api/action', {'playerId': cid, 'action': 'start'})
        pg.wait_for_timeout(1600)
        ok(pg.evaluate("document.getElementById('game') && "
                       "!document.getElementById('game').classList.contains('hidden')"),
           '已进入游戏界面')
        # 大厅面板整体隐藏，移除按钮随之不可见（DOM 里留着无妨）
        ok(pg.evaluate("""() => {
            const b = document.querySelector('.remove-ai');
            if (!b) return true;
            const r = b.getBoundingClientRect();
            const lobby = document.getElementById('lobby');
            return lobby.classList.contains('hidden')
                || r.width === 0 || r.height === 0
                || getComputedStyle(b).display === 'none';
        }"""), '开局后界面上不再显示移除按钮')
        pg.screenshot(path=OUT + '/host_game_1280.png')

        browser.close()
    print('PASS ui remove-ai: %d checks（截图目录 %s）' % (len(checks), OUT))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
