"""生成离线动画预览 动画预览.html：真实渲染代码 + 真实战斗数据，可直接双击打开。

    python3 tools/make_demo.py [输出路径]
"""
import json, os, sys, types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV_PATH = os.path.join(ROOT, 'server.py')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, '动画预览.html')


def load_server():
    src = open(SRV_PATH, encoding='utf-8-sig').read().replace("if __name__ == '__main__':", 'if False:')
    srv = types.ModuleType('srv')
    srv.__file__ = SRV_PATH
    exec(compile(src, 'server.py', 'exec'), srv.__dict__)
    return srv


SRV = load_server()
CARD = {c['id']: c for c in SRV.CARDS}
A_ID, B_ID = 'demo-a', 'demo-b'

# 双方阵容：尽量覆盖护盾 / 生命调配 / 减速 / 群伤 / 反伤 / 处决 等不同表现
A_BOARD = [('pruning', 3, 0), ('divide', 5, 1), ('quick_sort', 1, 2),
           ('inverse', 6, 2), ('xor', 3, 3)]
B_BOARD = [('bfs', 2, 0), ('sqrt_block', 5, 1), ('range_dp', 1, 2),
           ('monotonic_stack', 6, 1), ('dfs', 4, 3)]


def make_player(pid, name, color, board):
    b = {f'{x},{y}': {'card': cid, 'hp': SRV.effective_max_hp(CARD[cid])}
         for cid, x, y in board}
    return {
        'id': pid, 'name': name, 'color': color, 'dead': False, 'ready': False,
        'mind': 100, 'reason': 100, 'energy': 100, 'gold': 20, 'hp': 100,
        'crashed': False, 'level': 3, 'board': b, 'bench': [], 'shop': [],
        'lastResult': '', 'roundWins': 0, 'roundLosses': 0,
    }


def mark_star(board, key, star):
    if key not in board:
        return
    info = board[key]
    info['star'] = star
    info['hp'] = SRV.star_max_hp(CARD[info['card']], star)


def main():
    a = make_player(A_ID, '你', 0, A_BOARD)
    b = make_player(B_ID, '对手', 5, B_BOARD)
    # 展示升星：场上 2 星 / 3 星，备战席 2 星
    mark_star(a['board'], '3,0', 2)
    mark_star(a['board'], '5,1', 3)
    mark_star(b['board'], next(iter(b['board'])), 2)
    room = SRV.Room('DEMO', A_ID)
    frames, events, _, _ = room._simulate_battle(a, b, 3)
    kinds = sorted({e['type'] for e in events})
    print('帧', len(frames), '事件', len(events), '类型', kinds)
    assert 'skill' in kinds or len(events) > 40, '战斗太单调，换一套阵容'

    # 演示用商店/备战席：从卡池里挑几张
    a['shop'] = ['bfs', 'fermat', 'merge_sort', 'greedy', 'cdq']
    a['bench'] = [{'card': 'sort', 'hp': SRV.star_max_hp(CARD['sort'], 2), 'star': 2}]
    b['shop'] = ['xor', 'diff', 'shift', 'a_star', 'gcd']

    state = {
        'version': 1, 'roomId': 'DEMO', 'host': A_ID, 'state': 'battle', 'round': 3,
        'winner': None, 'viewerId': A_ID, 'viewerSide': 'a', 'viewerBye': False,
        'players': {A_ID: a, B_ID: b}, 'opponentId': B_ID, 'battleKey': 'demo-0',
        'prepEndsAt': 0, 'battleEndsAt': 0, 'battleStartedAt': 0, 'serverNow': 0,
        'chatVersion': 0, 'halfW': 8, 'halfH': 4, 'battleW': 8, 'battleH': 8,
        'maxRounds': 10, 'maxPlayers': 8,
        'chat': [{'type': 'system', 'text': '动画预览 · 循环播放'}],
    }
    battle = {'battleKey': 'demo-0', 'battleStartedAt': 0, 'frames': frames,
              'events': events, 'viewerBye': False, 'opponentId': B_ID}
    data = {'state': state, 'battle': battle,
            'cards': SRV.CARDS, 'traits': SRV.TRAITS if hasattr(SRV, 'TRAITS') else {}}

    html_src = open(os.path.join(ROOT, 'static', 'index.html'), encoding='utf-8').read()
    css = open(os.path.join(ROOT, 'static', 'style.css'), encoding='utf-8-sig').read()
    js = open(os.path.join(ROOT, 'static', 'script.js'), encoding='utf-8-sig').read()

    body = html_src.split('<body>', 1)[1].split('<script src=')[0]
    shim = '''
<script>
/* 沙箱预览里 localStorage 会抛 SecurityError，这里换一份内存实现 */
(function () {
  try { localStorage.setItem('__t', '1'); localStorage.removeItem('__t'); return; } catch (e) {}
  var mem = {};
  var shim = {
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(mem, k) ? mem[k] : null; },
    setItem: function (k, v) { mem[k] = String(v); },
    removeItem: function (k) { delete mem[k]; },
    clear: function () { mem = {}; }
  };
  try { Object.defineProperty(window, 'localStorage', { configurable: true, get: function () { return shim; } }); }
  catch (e) { window.localStorage = shim; }
})();
</script>
'''
    boot = '''
<script>
(function () {
  var D = window.__DEMO_DATA__;
  /* 1. 注入卡牌数据（离线跑不到 /api/cards） */
  state.cards = {};
  D.cards.forEach(function (c) { state.cards[c.id] = c; });
  state.traits = D.traits;
  state.cardsLoaded = true;
  state.playerId = D.state.viewerId;
  state.roomId = 'DEMO';

  /* 2. 关掉开场横幅的重复播放（第一轮保留） */
  var intro = window.triggerBattleIntro;
  var firstRound = true;
  window.triggerBattleIntro = function () {
    if (!firstRound) return;
    firstRound = false;
    return intro.apply(null, arguments);
  };

  /* 3. 挂载真实战斗数据并开始回放 */
  var d = D.state, bt = D.battle;
  function arm() {
    d.version += 1;
    var now = Date.now();
    bt.battleKey = 'demo-' + now;
    bt.battleStartedAt = now / 1000;
    d.battleKey = bt.battleKey;
    d.battleStartedAt = now / 1000;
    d.battleEndsAt = (now + 30000) / 1000;
    state.battleData = bt;
    state.activeBattleKey = '';
    state.lastVersion = -1;
    render(d);
  }
  arm();

  /* 4. 播完自动重来 */
  setInterval(function () {
    var f = state.currentFrames;
    if (!f.length) return;
    if (state.lastFrameIdx >= f.length - 1) { stopBattlePlayback(); arm(); }
  }, 700);
})();
</script>
'''

    out = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OI-chess · 动画预览</title>
<style>
{css}
</style>
<style>
  /* 预览页专用：隐藏会退出对局的控件，加一条提示 */
  .game-controls .danger {{ display: none; }}
  #demoTag {{
    position: fixed; left: 50%; bottom: 6px; transform: translateX(-50%);
    font-size: 10px; letter-spacing: 3px; color: var(--muted);
    pointer-events: none; z-index: 50; white-space: nowrap;
  }}
</style>
</head>
<body>
<div id="demoTag">动画预览 · 循环播放</div>
{body}
{shim}
<script>
window.__DEMO_DATA__ = {json.dumps(data, ensure_ascii=False)};
</script>
<script>
{js}
</script>
{boot}
</body>
</html>
'''
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(out)
    print('写出', OUT, round(len(out) / 1024), 'KB')


if __name__ == '__main__':
    main()
