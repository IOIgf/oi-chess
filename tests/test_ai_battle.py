"""AI 对战定向回归（仅标准库，不需要运行中的服务器）。

覆盖：
  1. AI 玩家模型：cid 前缀、isAi / aiLevel 标记、三档难度
  2. add_ai 约束：需有真人、受 MAX_PLAYERS 限制；等待期与对局中都能加入
  3. 对外状态：_public_player / get_state 暴露「电脑」标记
  4. 准备期自动化：AI 自动买卡布阵并点准备，真人仍需自己点准备
  5. 难度梯度：多轮后 简单 <= 普通 <= 困难 的上阵人数
  6. 可复现性：AI 决策用独立随机流，绝不推进全局 random
  7. 档案隔离：AI 不写 PROFILES、不参与 Rating
  8. 清理豁免：AI 不受心跳超时淘汰；没有真人时房间被回收
  9. 全员准备门控与多轮推进不卡死
 10. 局内加入电脑：按当前回合初始化、立即决策并准备、战斗期加入视为本轮轮空
 11. HTTP API：/api/rooms 带 aiCount / aiLevel、addAi 动作与房主校验
"""
import random
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as s

# 把玩家档案重定向到临时目录，测试不污染工作区 data/
_TMP = tempfile.TemporaryDirectory()
s.DATA_DIR = Path(_TMP.name)
s.DATA_FILE = s.DATA_DIR / 'players.json'
s.PROFILES = {}

checks = []


def ok(cond, label):
    assert cond, label
    checks.append(label)


def fresh_room(n_ai=0, level='normal'):
    r = s.Room('ai-test-%d' % time.time_ns(), 'H')
    ok(r.add_player('H', '真人')[0], 'host joins')
    for _ in range(n_ai):
        ok(r.add_ai(level)[0], 'add ai')
    return r


def ai_players(r):
    return [p for p in r.players.values() if p.get('isAi')]


# ---- 1. AI 玩家模型 --------------------------------------------------------
ok(s.AI_CID_PREFIX == 'ai:', 'AI cid prefix is ai:')
p = s.new_player('ai:x', '电脑', is_ai=True, ai_level='hard')
ok(p['isAi'] is True and p['aiLevel'] == 'hard', 'new_player AI flags')
ok('isAi' not in s.new_player('H', '真人'), 'human player has no AI flags')
ok(tuple(s.AI_LEVELS) == ('easy', 'normal', 'hard'), 'three difficulty tiers')
ok(s.AI_LEVEL_LABELS['hard'] == '困难', 'difficulty labels are Chinese')

# ---- 2. add_ai 约束 -------------------------------------------------------
r = fresh_room()
added, cid = r.add_ai('bogus')
ok(added and cid.startswith(s.AI_CID_PREFIX), 'add_ai returns an ai: cid')
ok(r.players[cid]['aiLevel'] == 'normal', 'unknown difficulty falls back to normal')
ok(cid in r.colors, 'AI gets a player color')
r.state = 'prep'
ok(r.add_ai('hard')[0], 'add_ai allowed during the prep phase')
r.state = 'ended'
ok(not r.add_ai('hard')[0], 'add_ai rejected once the game ended')

r2 = fresh_room()
for _ in range(s.MAX_PLAYERS - 1):
    r2.add_ai('easy')
ok(len(r2.players) == s.MAX_PLAYERS, 'room filled to MAX_PLAYERS')
ok(not r2.add_ai('easy')[0], 'add_ai rejected when the room is full')

r3 = s.Room('empty-room', 'nobody')
ok(not r3.add_ai('normal')[0], 'add_ai rejected without any human player')

# ---- 3. 对外状态 ----------------------------------------------------------
r = fresh_room(1, 'hard')
cid = [c for c in r.players if c.startswith(s.AI_CID_PREFIX)][0]
row = r._public_player(cid, r.players[cid], r.colors[cid])
ok(row['isAi'] is True and row['aiLevel'] == '困难', 'public player exposes AI flags')
ok(r.get_state('H')['players'][cid]['isAi'] is True, 'state exposes AI flags')
ok(r.get_state('H')['players']['H']['isAi'] is False, 'human flagged as non-AI')

# ---- 4. 准备期自动化 ------------------------------------------------------
r = fresh_room(2, 'normal')
ok(r.start('H')[0], 'start with 1 human + 2 AI')
ok(r.state == 'prep', 'prep phase entered')
ok(not r.players['H']['ready'], 'human is not auto-readied')
ok(all(p['ready'] for p in ai_players(r)), 'AI auto-readies every prep phase')
ok(all(0 < len(p['board']) <= s.MAX_BOARD for p in ai_players(r)),
   'AI buys and places a legal board')
ok(r.prep_end == 0.0, 'battle still waits for the human to ready up')

# ---- 5. 难度梯度 ----------------------------------------------------------
r = fresh_room()
for lv in s.AI_LEVELS:
    r.add_ai(lv)
ok(r.start('H')[0], 'start with all three difficulties')
for _ in range(4):
    if r.state != 'prep':
        break
    r.toggle_ready('H')
    r._tick()
    if r.state != 'battle':
        break
    r._enter_settle()
counts = {p['aiLevel']: len(p['board']) for p in ai_players(r)}
ok(counts['easy'] <= counts['normal'] <= counts['hard'],
   'difficulty board-size gradient after 4 rounds')
ok(all(counts[lv] <= s.AI_TUNING[lv]['board_target'] for lv in s.AI_LEVELS),
   'each AI stays within its difficulty board target')

# ---- 6. 可复现性：AI 不推进全局随机流 -------------------------------------
r = fresh_room(2, 'hard')
r.start('H')
before = random.getstate()
r._ai_prep()
after = random.getstate()
ok(before == after, 'AI decisions never advance the global random stream')

# ---- 7. 档案隔离 ----------------------------------------------------------
ai_cid = 'ai:profile-test'
before_keys = set(s.PROFILES)
ok(s.update_rating(ai_cid, 10, 'win', name='电脑') == {}, 'update_rating skips AI')
ok(s.get_profile(ai_cid, '电脑')['rating'] == s.DEFAULT_RATING,
   'get_profile returns a virtual AI profile')
ok(set(s.PROFILES) == before_keys and ai_cid not in s.PROFILES,
   'AI is never persisted into PROFILES')

# ---- 8. 清理豁免 ----------------------------------------------------------
r = fresh_room(1, 'normal')
r.state = 'prep'
now = time.time()
for pl in r.players.values():
    pl['last_seen'] = now - s.PLAYER_TIMEOUT - 100.0
to_remove = []
s._cleanup_room_locked(r, now, to_remove)
ais = ai_players(r)
ok(len(ais) == 1 and not ais[0].get('abandoned') and not ais[0].get('dead'),
   'AI is exempt from the heartbeat timeout')
ok(r.id in to_remove, 'room with no live human is recycled')

# ---- 9. 门控与多轮推进 ----------------------------------------------------
r = fresh_room(1, 'normal')
r.start('H')
ok(r.prep_end == 0.0, 'battle waits while human is not ready')
r.toggle_ready('H')
ok(r.prep_end > 0, 'human ready arms the immediate battle')
r._tick()
ok(r.state == 'battle', 'tick after full readiness enters battle')

r = fresh_room(3, 'hard')
r.start('H')
rounds = 0
for _ in range(s.MAX_ROUNDS + 2):
    if r.state != 'prep':
        break
    r.toggle_ready('H')
    r._tick()
    if r.state != 'battle':
        break
    r._enter_settle()
    rounds += 1
ok(rounds >= 3, 'AI game advances through multiple rounds without stalling')
ok(r.state in ('prep', 'ended'), 'game stays in a reachable state')

# ---- 10. 局内加入电脑（真人房间补位，消除奇数轮空） -----------------------
r = fresh_room(1, 'normal')
ok(r.start('H')[0], 'start a human + AI game')
ok(r.state == 'prep', 'the game is in the prep phase')
r.players['H']['hp'] = 64
before_state = random.getstate()
ok_ai, new_cid = r.add_ai('hard')
ok(ok_ai and new_cid.startswith(s.AI_CID_PREFIX), 'AI can join an ongoing game')
np = r.players[new_cid]
ok(np['hp'] == 64, 'the late AI starts at the humans\' HP level')
ok(0 <= np['gold'] <= 18, 'the late AI starts with the standard round gold and may spend it')
ok(np['level'] == s.level_for_round(r.round), 'the late AI uses the current round level')
ok(0 <= len(np['shop']) <= 5, 'the late AI gets a shop immediately')
ok(np['ready'] is True, 'the late AI readies itself in the prep phase')
ok(0 < len(np['board']) <= s.MAX_BOARD, 'the late AI buys and places a board')
ok(random.getstate() == before_state,
   'a late AI never advances the global random stream')
ok(r.pairs_computed is False, 'the pairing is recomputed after the late AI joins')
r.toggle_ready('H')
ok(r.prep_end > 0, 'the battle arms once every living player is ready')

r2 = fresh_room(1, 'normal')
ok(r2.start('H')[0], 'start another game')
r2.toggle_ready('H')
r2._tick()
ok(r2.state == 'battle', 'the game entered the battle phase')
ok_ai2, battle_cid = r2.add_ai('easy')
ok(ok_ai2, 'AI can join during the battle phase')
ok(battle_cid in r2._bye_players, 'a battle-phase AI is a bye for the current round')
ok(r2.players[battle_cid]['shop'], 'a battle-phase AI still receives a shop')

# ---- 11. HTTP API（伪 Handler，无需起服务） -------------------------------
class FakeHandler:
    def __init__(self, data):
        self.data = data
        self.result = None
        self.status = None

    def _read_json(self):
        return self.data

    def _json(self, obj, status=200):
        self.result = obj
        self.status = status
        return obj


h = FakeHandler({'clientId': 'api-human', 'name': '真人',
                 'aiCount': 2, 'aiLevel': 'hard'})
s.Handler._api_rooms(h, h.data)
ok(h.status == 200 and h.result.get('aiCount') == 2,
   '/api/rooms creates the requested AI opponents')
rid = h.result['roomId']
room = s.ROOMS[rid]
ok(sum(1 for pl in room.players.values() if pl.get('isAi')) == 2,
   'AI players really joined the created room')
ok(all(pl['aiLevel'] == 'hard' for pl in ai_players(room)),
   'aiLevel is propagated to every AI')

h2 = FakeHandler({'playerId': 'api-human', 'action': 'addAi', 'level': 'easy'})
s.Handler._api_action(h2, h2.data)
ok(h2.status == 200, 'addAi action succeeds for the host')
ok(sum(1 for pl in room.players.values() if pl.get('isAi')) == 3,
   'addAi appends one more AI')
ok(str(h2.result.get('aiId', '')).startswith(s.AI_CID_PREFIX),
   'addAi returns the new AI id')

ok(room.add_player('api-guest', '客人')[0], 'a second human joins the room')
h3 = FakeHandler({'playerId': 'api-guest', 'action': 'addAi', 'level': 'easy'})
s.Handler._api_action(h3, h3.data)
ok(h3.status == 400, 'addAi rejected for a non-host')

h4 = FakeHandler({'clientId': 'api-human-2', 'name': '真人2', 'aiCount': 99})
s.Handler._api_rooms(h4, h4.data)
ok(h4.status == 200 and h4.result.get('aiCount') <= s.MAX_PLAYERS - 1,
   'aiCount is clamped to MAX_PLAYERS - 1')
with s.ROOMS_LOCK:
    s.ROOMS.pop(h4.result['roomId'], None)
    s.ROOMS.pop(rid, None)

print('PASS ai battle: %d checks' % len(checks))
