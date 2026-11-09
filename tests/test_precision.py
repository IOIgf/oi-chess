"""真实事件时间：攻速、减速、动态光环与卡顿均不得向上量化。"""
import sys,math
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from balance_lab import SRV as s
s.CARD_BY_ID['spfa']['hp']=10**8
s.CARD_BY_ID['expectation']['hp']=10**8
s.CARD_BY_ID['o2']['hp']=10**8
room=s.Room('precision','A')

def simulate(card='spfa',aura=1,slow_until=-1,stall=False,death=None):
    def player(pid):
        board={'3,0':dict(card=card,hp=10**8)}
        if aura!=1:board['4,0']=dict(card='o2',hp=10**8)
        return dict(id=pid,mind=100,energy=40,board=board)
    spawn=room._apply_spawn_passives
    def setup(units):
        spawn(units)
        for u in units:
            if u['skill']!='o2_aura':u['slowUntil']=slow_until
            elif death is not None:u['delayed']=[(death,10**10,None)]
    with patch.object(s,'O2_SPEED_MULT',aura),patch.object(s.random,'random',return_value=0 if stall else 1),patch.object(room,'_apply_spawn_passives',side_effect=setup):
        frames,events,*_=room._simulate_battle(player('A'),player('B'),3)
    times=[e['t'] for e in events if e['type']=='attack' and e['owner']=='A' and e['fromX']==3]
    assert all(a['t']<b['t'] for a,b in zip(frames,frames[1:]))
    return times

rows=[]
for card in ['expectation','spfa']:
    for aura in [1,1.5,2]:
        for slowed in [False,True]:
            for stall in ([False,True] if card=='spfa' else [False]):
                interval=(3 if slowed else 2)/(1.5 if card=='spfa' else 1)/aura+(4 if stall else 0)
                ts=simulate(card,aura,100 if slowed else -1,stall)
                assert len(ts)==math.ceil((30-1e-9)/interval),(card,aura,interval,len(ts))
                assert all(abs(t-i*interval)<1.1e-6 for i,t in enumerate(ts)),(card,aura,interval,ts)
                rows.append((card,aura,slowed,stall,interval,ts[:5]))
# 减速在 1 秒结束：先完成 2/3 工作量，剩余 2/3，用时 2/3 秒。
ts=simulate(slow_until=1)
assert abs(ts[1]-5/3)<1e-6,ts
# 光环在第 0.8 秒死亡，已完成 1.6 工作量；剩余工作量按无光环速率消耗。
ts=simulate(aura=2,death=.8)
assert abs(ts[1]-2/3)<1e-6
assert abs(ts[2]-(.8+(4/3-(.8-2/3)*2)))<1e-6,ts
for row in rows:print(row)
print('PASS: 18 constant-rate cases, exact cadence/counts, slow expiry, aura death, non-grid stall')
