"""瘦状态响应：版本与聊天均未变时省去全量快照，但心跳与倒计时仍准确。"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as s

r = s.Room('delta-probe', 'p0')
for i in range(8):
    ok, _ = r.add_player(f'p{i}', f'P{i}')
    assert ok, f'add_player p{i}'
viewer = 'p0'

full = r.get_state(viewer, -1, -1)
assert 'players' in full and len(full['players']) == 8
assert 'minimal' not in full
assert 'serverNow' in full and 'prepEndsAt' in full

thin = r.get_state(viewer, full['chatVersion'], full['version'])
assert thin.get('minimal') is True
assert 'players' not in thin
for k in ('version', 'chatVersion', 'serverNow', 'state', 'round', 'battleKey',
          'prepEndsAt', 'battleEndsAt', 'battleStartedAt'):
    assert k in thin, k
# 计时与状态字段必须与完整响应一致（房间未推进）
for k in ('prepEndsAt', 'battleEndsAt', 'battleStartedAt', 'battleKey', 'state', 'round'):
    assert thin[k] == full[k], k

# 瘦响应仍必须刷新心跳，否则玩家会被判掉线
before = r.players[viewer]['last_seen']
r.players[viewer]['last_seen'] = before - 10
r.get_state(viewer, full['chatVersion'], full['version'])
assert r.players[viewer]['last_seen'] > before

# 版本变化 -> 回退到完整响应
r.version += 1
again = r.get_state(viewer, full['chatVersion'], full['version'])
assert 'players' in again and 'minimal' not in again

# 聊天变化（只 bump chat_version）-> 完整响应且带 chat
r.version = full['version']
r._sys_chat('delta probe')
assert r.chat_version != full['chatVersion']
with_chat = r.get_state(viewer, full['chatVersion'], full['version'])
assert 'players' in with_chat and 'chat' in with_chat
assert with_chat['chatVersion'] == r.chat_version

full_bytes = len(json.dumps(full, ensure_ascii=False).encode('utf-8'))
thin_bytes = len(json.dumps(thin, ensure_ascii=False).encode('utf-8'))
assert thin_bytes < full_bytes * 0.35, (thin_bytes, full_bytes)
print(f'PASS state delta: 8-player full={full_bytes}B thin={thin_bytes}B '
      f'({thin_bytes / full_bytes:.1%}), heartbeat kept, version/chat fallbacks OK')
