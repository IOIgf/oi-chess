"""浏览器端动画/渲染回归：真开一局，逐帧截图并收集控制台错误。

用法： python3 tests/anim_check.py            # 需要 8080 上的服务器
"""
import json, os, random, re, sys, time, urllib.request as u

BASE = os.environ.get('OI_BASE', 'http://127.0.0.1:8080')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots')
os.makedirs(OUT, exist_ok=True)


def req(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = u.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        with u.urlopen(r) as f:
            return json.loads(f.read())
    except u.HTTPError as e:
        print('HTTP', e.code, e.read()[:200])
        raise


def state(pid):
    return req('/api/state?playerId=' + pid)


def setup_bot(pid, n=8):
    """给某个玩家买满并铺开棋子（不需要经过 UI）"""
    d = state(pid)
    me = d['players'][pid]
    for _ in range(10):
        try:
            req('/api/action', {'playerId': pid, 'action': 'buy', 'index': 0})
        except Exception:
            break
    me = state(pid)['players'][pid]
    occ = set(me['board'])
    cells = [(x, y) for y in range(4) for x in range(8) if f'{x},{y}' not in occ]
    random.shuffle(cells)
    for bi in range(len(me['bench']) - 1, -1, -1):
        if not cells:
            break
        x, y = cells.pop()
        try:
            req('/api/action', {'playerId': pid, 'action': 'place',
                                'benchIndex': bi, 'x': x, 'y': y})
        except Exception:
            break


def main():
    from playwright.sync_api import sync_playwright

    tag = str(random.randint(10 ** 5, 10 ** 6))
    errors, warns = [], []
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={'width': 1440, 'height': 900})
        pg.on('console', lambda m: (errors if m.type == 'error' else warns).append(m.text))
        pg.on('pageerror', lambda e: errors.append('PAGEERROR ' + str(e)))
        pg.goto(BASE, wait_until='domcontentloaded')
        cid = pg.evaluate("localStorage.getItem('oi_client_id')")
        assert cid, '客户端 id 未生成'

        room = req('/api/rooms', {'clientId': cid, 'name': '甲' + tag})
        rid = room['roomId']
        print('房间', rid)
        # 让页面以同一身份进入房间
        pg.evaluate("rid => localStorage.setItem('oi_room_id', rid)", rid)
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_timeout(600)

        bot = 'bot' + tag
        req('/api/join', {'clientId': bot, 'name': '乙' + tag, 'roomId': rid})
        req('/api/action', {'playerId': cid, 'action': 'start'})
        pg.wait_for_timeout(500)
        pg.screenshot(path=os.path.join(OUT, '01_lobby.png'))

        # 甲（浏览器玩家）由脚本代买，保证有棋可看
        setup_bot(cid)
        setup_bot(bot)
        pg.wait_for_timeout(400)
        pg.screenshot(path=os.path.join(OUT, '02_prep.png'))

        # 再用真实点击验证一下放置交互没被渲染改动破坏
        st = state(cid)
        me = st['players'][cid]
        if me['bench']:
            pg.evaluate("document.querySelector('#benchList .bench-card')?.click()")
            pg.wait_for_timeout(120)
            occ = set(me['board'])
            free = [(x, y) for y in range(4) for x in range(8) if f'{x},{y}' not in occ]
            if free:
                x, y = free[0]
                pg.evaluate("([x,y]) => document.querySelector(`#cellLayerPrep .cell[data-x='${x}'][data-y='${y}']`)?.click()", [x, y])
                pg.wait_for_timeout(350)
        pg.screenshot(path=os.path.join(OUT, '03_placed.png'))

        for pid in (cid, bot):
            req('/api/action', {'playerId': pid, 'action': 'ready'})

        # 战斗：每 400ms 一帧，抓关键瞬间
        pg.wait_for_timeout(300)
        idx_a = pg.evaluate('state.lastFrameIdx')
        # 边截图边采样：统计每枚棋子在回放中出现过多少个不同的 transform
        seen = {}
        shots = 0
        t0 = time.time()
        while time.time() - t0 < 12:
            st = state(cid)
            if st.get('state') != 'battle':
                break
            for uid, tf in pg.evaluate(
                    "() => [...document.querySelectorAll('.unit')].map(e => [e.dataset.uid, e.style.transform])"):
                seen.setdefault(uid, set()).add(tf)
            if shots < 10 and int((time.time() - t0) / 0.9) + 1 > shots:
                pg.screenshot(path=os.path.join(OUT, f'battle_{shots:02d}.png'))
                shots += 1
            pg.wait_for_timeout(150)
        idx_b = pg.evaluate('state.lastFrameIdx')
        raf = pg.evaluate('state.rafId !== null')
        moved = sum(1 for v in seen.values() if len(v) >= 4)   # 至少滑过 4 个中间位置
        print(f'回放帧 {idx_a}→{idx_b}  rAF {raf}  平滑位移的棋子 {moved}  截图 {shots} 张')

        # 数值自检：棋子位置是否都在棋盘内、血条宽度是否与血量一致
        info = pg.evaluate("""() => {
          const out = {units: [], bars: 0, bad: []};
          document.querySelectorAll('.unit').forEach(el => {
            if (!el.offsetParent) return;      // 隐藏棋盘上的棋子跳过
            const r = el.getBoundingClientRect();
            const layer = el.parentElement.getBoundingClientRect();
            out.units.push([el.dataset.uid, Math.round(r.x - layer.x), Math.round(r.y - layer.y),
                            Math.round(r.width), Math.round(r.height)]);
            if (r.width < 4 || r.height < 4) out.bad.push('尺寸异常 ' + el.dataset.uid);
            if (r.left < layer.left - 2 || r.right > layer.right + 2) out.bad.push('越界 x ' + el.dataset.uid);
            if (r.top < layer.top - 2 || r.bottom > layer.bottom + 2) out.bad.push('越界 y ' + el.dataset.uid);
            const fill = el.querySelector('.hp-fill');
            const stat = el.querySelector('.unit-stat');
            if (fill && stat) {
              out.bars++;
              const m = /^(\\d+)\\/(\\d+)/.exec(stat.textContent || '');
              if (m) {
                const want = Math.round(+m[1] / +m[2] * 100);
                const tr = getComputedStyle(fill).transform;
                let got = 100;
                if (tr && tr.startsWith('matrix')) got = Math.round(parseFloat(tr.split('(')[1]) * 100);
                if (Math.abs(got - want) > 3) out.bad.push(`血条不符 ${el.dataset.uid} ${got}!=${want}`);
              }
            }
          });
          return out;
        }""")
        print('棋子', len(info['units']), '血条', info['bars'], '异常', info['bad'][:6])
        pg.screenshot(path=os.path.join(OUT, '99_final.png'))
        toast_el = pg.evaluate("""() => {
          const el = document.getElementById('toast');
          return {text: (el.textContent || '').trim(), visible: el.classList.contains('show')};
        }""")
        # #toast is a general notification channel (star-up merges, join notices,
        # 'not enough gold', ...). Its textContent is never cleared; only the
        # 'show' class is removed after 1800ms. Treating any non-empty text as an
        # error therefore produces false failures. Only a *visible* message that
        # reports a real transport/server fault should fail this render check.
        FAULT_TOAST = re.compile(r'(无法连接|服务器返回异常|请求失败|服务器内部错误|房间已结束)', re.I)
        toast_error = toast_el['visible'] and bool(FAULT_TOAST.search(toast_el['text']))
        if toast_error:
            print('页面弹出错误提示:', toast_el['text'])
        elif toast_el['text']:
            print('页面提示(非错误):', toast_el['text'])
        br.close()

    print('控制台错误', len(errors), '| 位移棋子', moved)
    for e in errors[:8]:
        print('  !', e[:300])
    for w in warns[:5]:
        print('  ~', w[:200])
    ok = (not errors and not info['bad'] and shots >= 3 and raf
          and idx_b > idx_a and not toast_error)
    print('动画回归:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
