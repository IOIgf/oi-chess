"""多视口布局回归：控件不压内容、面板不溢出、棋盘完整可见（准备期 + 战斗期）。

用法： python3 tests/test_layout.py        # 需要 8080 上的服务器
覆盖：全屏 / 半宽 / 半屏 / 矮半屏 / 窄屏 / 手机尺寸。
"""
import json, os, sys, time, urllib.request as u

BASE = os.environ.get('OI_BASE', 'http://127.0.0.1:8080')
VIEWPORTS = [
    (1440, 900), (1280, 720), (960, 1080), (960, 540),
    (800, 600), (1280, 450), (700, 900), (560, 720),
]


def req(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = u.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    with u.urlopen(r, timeout=8) as f:
        return json.loads(f.read())


def state(pid):
    return req('/api/state?playerId=' + pid)


PROBE = r"""() => {
  const bad = [];
  const R = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect() : null; };
  const hit = (a, b) => {
    if (!a || !b) return false;
    return Math.min(a.right,b.right) - Math.max(a.left,b.left) > 1 &&
           Math.min(a.bottom,b.bottom) - Math.max(a.top,b.top) > 1;
  };
  const vw = innerWidth, vh = innerHeight;

  // 1. 顶栏控件不得压住任何面板或面板内的交互内容
  const gc = R('.game-controls');
  for (const s of ['.panel-status','.panel-board','.panel-shop','.panel-chat',
                   '.shop-header','#refreshBtn','.meta','#timerVal','.stat-group',
                   '.ready-btn','.chat-input-bar','#boardWrap']) {
    if (hit(gc, R(s))) bad.push('控件遮挡 ' + s);
  }

  // 2. 面板之间不得互相重叠，且完整落在视口内
  const panels = ['.panel-status','.panel-board','.panel-shop','.panel-chat'];
  for (const s of panels) {
    const r = R(s);
    if (!r) { bad.push('缺少面板 ' + s); continue; }
    if (r.bottom > vh + 1 || r.right > vw + 1 || r.left < -1 || r.top < -1)
      bad.push('面板超出视口 ' + s + ' ' + JSON.stringify({x:Math.round(r.x),y:Math.round(r.y),
                r:Math.round(r.right),b:Math.round(r.bottom)}));
  }
  for (let i = 0; i < panels.length; i++)
    for (let j = i+1; j < panels.length; j++)
      if (hit(R(panels[i]), R(panels[j]))) bad.push('面板重叠 ' + panels[i] + ' / ' + panels[j]);

  // 3. 布局容器不得产生溢出（内容被裁）
  const gl = document.querySelector('.game-layout');
  if (gl.scrollHeight > gl.clientHeight + 2) bad.push('布局纵向溢出 ' + gl.scrollHeight + '>' + gl.clientHeight);
  if (gl.scrollWidth > gl.clientWidth + 2) bad.push('布局横向溢出 ' + gl.scrollWidth + '>' + gl.clientWidth);

  // 4. 棋盘必须完整落在 board-wrap 内（准备期 / 战斗期分别检查）
  const wrap = R('#boardWrap');
  const boards = [...document.querySelectorAll('#prepBoard, #battleBoard')]
    .filter(e => !e.classList.contains('hidden'));
  for (const e of boards) {
    const r = e.getBoundingClientRect();
    const s = e.id;
    if (r.left < wrap.left - 1 || r.right > wrap.right + 1 ||
        r.top < wrap.top - 1 || r.bottom > wrap.bottom + 1)
      bad.push('棋盘被裁 ' + s + ' 溢出X=' + Math.round(r.right-wrap.right) +
               ' Y=' + Math.round(r.bottom-wrap.bottom));
  }
  // 战斗期两块半场各自也要在 wrap 内
  for (const h of document.querySelectorAll('#battleBoard:not(.hidden) .half-board')) {
    const r = h.getBoundingClientRect();
    if (r.left < wrap.left - 1 || r.right > wrap.right + 1 ||
        r.top < wrap.top - 1 || r.bottom > wrap.bottom + 1)
      bad.push('半场被裁 ' + h.id);
  }
  // 分离间距会撑出容器且让 FX 弹道与棋子错位，战斗期必须恒为 0
  const bb0 = document.querySelector('#battleBoard');
  if (bb0 && !bb0.classList.contains('hidden')) {
    const g = parseFloat(getComputedStyle(bb0).rowGap) || 0;
    if (g > 1) bad.push('战斗棋盘存在分离间距 ' + g + 'px（会撑出容器被裁）');
  }

  // 5. 商店卡片：宽屏应全部可见；更窄时允许横向滚动，但必须能滑到最后一张
  const sl = document.querySelector('#shopList');
  if (sl) {
    const cards = [...sl.querySelectorAll('.shop-card')];
    const sr = sl.getBoundingClientRect();
    const full = cards.filter(c => c.getBoundingClientRect().right <= sr.right + 1).length;
    if (vw >= 800 && cards.length && full < cards.length)
      bad.push('宽屏商店卡未全部可见 ' + full + '/' + cards.length);
    if (sl.scrollWidth > sl.clientWidth + 2) {
      const ovX = getComputedStyle(sl).overflowX;
      if (ovX !== 'auto' && ovX !== 'scroll') bad.push('商店列表溢出但不可滚动');
      if (getComputedStyle(sl).scrollbarWidth === 'none')
        bad.push('商店列表溢出但无滚动条提示');
    }
    if (cards.length) {
      const before = sl.scrollLeft;
      sl.scrollLeft = sl.scrollWidth;
      const last = cards[cards.length-1].getBoundingClientRect();
      if (last.right > sr.right + 2 || last.left < sr.left - 2)
        bad.push('商店卡无法滚动到完整可见');
      sl.scrollLeft = before;
    }
    const clipped = cards.filter(c => c.scrollHeight > c.clientHeight + 1).length;
    if (clipped) bad.push('商店卡文字被裁 ' + clipped);
  }
  const bench = R('.bench');
  if (bench && (bench.right > vw + 1 || bench.bottom > vh + 1)) bad.push('备战席超出视口');

  // 6. 关键按钮必须可见且中心点命中的是它自己（没有被浮层挡住）
  const clickable = ['#refreshBtn','#readyBtn','#fxMode','.game-controls .ctrl-btn:nth-child(2)',
                     '.game-controls .ctrl-btn.danger'];
  for (const s of clickable) {
    const e = document.querySelector(s);
    if (!e) { bad.push('缺少按钮 ' + s); continue; }
    const r = e.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) { bad.push('按钮不可见 ' + s); continue; }
    const top = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
    if (!top || !(e === top || e.contains(top))) bad.push('按钮被遮挡 ' + s + ' 命中=' +
      (top ? (top.id || top.className || top.tagName) : 'null'));
  }
  return {vw, vh, bad,
    wrap: [Math.round(wrap.width), Math.round(wrap.height)],
    board: boards.map(e => [e.id, Math.round(e.getBoundingClientRect().width),
                                 Math.round(e.getBoundingClientRect().height)])};
}"""


def main():
    from playwright.sync_api import sync_playwright
    tag = str(int(time.time()))[-6:]
    failures = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={'width': 1440, 'height': 900})
        pg.goto(BASE, wait_until='domcontentloaded')
        cid = pg.evaluate("localStorage.getItem('oi_client_id')")
        room = req('/api/rooms', {'clientId': cid, 'name': '甲' + tag})
        rid = room['roomId']
        req('/api/join', {'clientId': 'layout-bot-' + tag, 'name': '乙', 'roomId': rid})
        pg.evaluate("rid => localStorage.setItem('oi_room_id', rid)", rid)
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_timeout(600)
        req('/api/action', {'playerId': cid, 'action': 'start'})
        pg.wait_for_timeout(800)
        assert pg.evaluate("document.getElementById('game').classList.contains('active')"), '未进入游戏界面'

        def sweep(label):
            print('--- ' + label + ' ---')
            for w, h in VIEWPORTS:
                pg.set_viewport_size({'width': w, 'height': h})
                pg.wait_for_timeout(320)
                d = pg.evaluate(PROBE)
                ok = not d['bad']
                print('  %4dx%-4d %s  wrap=%s board=%s%s' % (
                    w, h, 'PASS' if ok else 'FAIL', d['wrap'], d['board'],
                    '' if ok else '  -> ' + '; '.join(d['bad'][:5])))
                if not ok:
                    failures.append('%s %dx%d: %s' % (label, w, h, '; '.join(d['bad'])))

        sweep('准备期')
        # 双方准备，进入战斗（首帧与稳定态各测一轮）
        for pid in (cid, 'layout-bot-' + tag):
            req('/api/action', {'playerId': pid, 'action': 'ready'})
        in_battle = False
        for _ in range(40):
            if state(cid).get('state') == 'battle':
                in_battle = True
                break
            time.sleep(0.25)
        assert in_battle, '未进入战斗阶段'
        pg.wait_for_timeout(250)
        sweep('战斗期(展开)')
        pg.wait_for_timeout(1700)
        sweep('战斗期(合并)')
        br.close()

    if failures:
        print('\n布局回归失败 %d 项:' % len(failures))
        for f in failures:
            print('  ' + f)
        sys.exit(1)
    print('\n布局回归 PASS：%d 视口 x 3 阶段，控件无遮挡、面板无溢出、棋盘完整可见' % len(VIEWPORTS))


if __name__ == '__main__':
    main()
