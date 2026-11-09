"""局内「+ 添加电脑」控件的界面复核（需要本地已启动的服务器）。

验证：
  1. 房主在游戏界面能看到「+ 添加电脑」与难度下拉
  2. 非房主看不到
  3. 控件在窄屏 / 半屏下不遮挡状态栏其它内容、不溢出面板
  4. 点击后确实加进一名电脑（状态里能查到）

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
        req('/api/join', {'clientId': 'ui-bot-1', 'name': '路人甲', 'roomId': rid})

        # 第二个真人（用独立浏览器上下文，稍后验证他看不到加电脑控件）
        ctx2 = browser.new_context(viewport={'width': 1280, 'height': 800})
        pg2 = ctx2.new_page()
        pg2.goto(BASE, wait_until='domcontentloaded')
        cid2 = pg2.evaluate("localStorage.getItem('oi_client_id')")
        req('/api/join', {'clientId': cid2, 'name': '路人乙', 'roomId': rid})
        pg2.evaluate("rid => localStorage.setItem('oi_room_id', rid)", rid)
        pg2.reload(wait_until='domcontentloaded')

        pg.evaluate("rid => localStorage.setItem('oi_room_id', rid)", rid)
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_timeout(1200)

        # 房主开局，进入游戏界面
        req('/api/action', {'playerId': cid, 'action': 'start'})
        pg.wait_for_timeout(1500)
        ok(pg.evaluate("document.getElementById('game') && "
                       "!document.getElementById('game').classList.contains('hidden')"),
           '已进入游戏界面')

        ok(visible(pg, '#gameAiControls'), '房主在局内能看到「+ 添加电脑」控件')
        ok(visible(pg, '#gameAiLevel'), '难度下拉可见')
        ok(pg.evaluate("document.getElementById('gameAiLevel').value") in
           ('easy', 'normal', 'hard'), '难度下拉有可选项')

        # 不遮挡状态栏其它内容
        box = pg.evaluate("""() => {
          const c = document.getElementById('gameAiControls').getBoundingClientRect();
          const o = document.getElementById('opponents').getBoundingClientRect();
          const s = document.getElementById('roundVal').getBoundingClientRect();
          const panel = document.querySelector('.panel-status').getBoundingClientRect();
          return {c: {t: c.top, b: c.bottom, l: c.left, r: c.right},
                  o: {b: o.bottom}, s: {b: s.bottom},
                  panel: {l: panel.left, r: panel.right, b: panel.bottom}};
        }""")
        ok(box['c']['t'] >= box['o']['b'] - 1,
           f'控件不压住对手列表（控件顶 {box["c"]["t"]:.0f} ≥ 列表底 {box["o"]["b"]:.0f}）')
        ok(box['c']['l'] >= box['panel']['l'] and box['c']['r'] <= box['panel']['r'],
           '控件横向不出状态栏面板')
        ok(box['c']['b'] <= box['panel']['b'], '控件纵向不出状态栏面板')
        pg.screenshot(path=OUT + '/host_game_1280.png')

        # 窄屏 / 半屏
        for w, h, tag in ((390, 844, 'phone'), (844, 390, 'half')):
            pg.set_viewport_size({'width': w, 'height': h})
            pg.wait_for_timeout(700)
            over = pg.evaluate("""() => {
              const c = document.getElementById('gameAiControls').getBoundingClientRect();
              const p = document.querySelector('.panel-status').getBoundingClientRect();
              return {cl: c.left, cr: c.right, ct: c.top, cb: c.bottom,
                      pl: p.left, pr: p.right, pt: p.top, pb: p.bottom,
                      vw: innerWidth, vh: innerHeight};
            }""")
            ok(over['cl'] >= over['pl'] - 1 and over['cr'] <= over['pr'] + 1,
               f'{tag} {w}x{h}：控件横向不溢出状态栏')
            ok(over['ct'] >= over['pt'] - 1 and over['cb'] <= over['pb'] + 1,
               f'{tag} {w}x{h}：控件纵向不溢出状态栏')
            pg.screenshot(path=f'{OUT}/host_game_{tag}.png')

        # 点击真的加进一名电脑
        pg.set_viewport_size({'width': 1280, 'height': 800})
        pg.wait_for_timeout(400)
        before = len(get(f'/api/state?playerId={cid}')['players'])
        pg.click('#gameAiControls button')
        pg.wait_for_timeout(1500)
        after_state = get(f'/api/state?playerId={cid}')
        ok(len(after_state['players']) == before + 1,
           f'点击后房间人数 {before} → {len(after_state["players"])}')
        ok(any(p.get('isAi') for p in after_state['players'].values()),
           '新成员被标记为电脑')
        pg.screenshot(path=OUT + '/host_game_after_add.png')

        # 非房主看不到控件
        pg2.wait_for_timeout(1200)
        ok(not visible(pg2, '#gameAiControls'), '非房主看不到「+ 添加电脑」控件')
        pg2.screenshot(path=OUT + '/guest_game.png')

        browser.close()
    print('PASS ui ai control: %d checks（截图目录 %s）' % (len(checks), OUT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
