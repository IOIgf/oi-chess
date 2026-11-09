"""15v15 随机战斗，覆盖各心态、精力、成长和回合的回放不变量。"""
import sys,random,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from balance_lab import load_server
s=load_server();rng=random.Random(20261118);ids=[c['id'] for c in s.CARDS];frames_n=events_n=0
for case in range(120):
    def team(pid):
        board={}
        for x,y in rng.sample([(x,y) for x in range(8) for y in range(4)],15):
            cid=rng.choice(ids);board[f'{x},{y}']={'card':cid,'hp':rng.randint(1,s.effective_max_hp(s.CARD_BY_ID[cid]))}
            if cid=='genetic':board[f'{x},{y}']['kills']=rng.randint(0,3)
        return dict(id=pid,mind=rng.choice([0,29,30,69,70,100]),energy=rng.choice([0,1,40]),board=board)
    a,b=team('A'),team('B');random.seed(20261118+case)
    frames,events,ah,bh=s.Room('invariant','A')._simulate_battle(a,b,rng.randint(1,10))
    assert all(x['t']<y['t'] for x,y in zip(frames,frames[1:])),case
    assert frames[-1]['t']<=30+1e-6
    for f in frames:
        coords=set();uids=set()
        for u in f['units']:
            assert u['uid'] not in uids;uids.add(u['uid'])
            assert (u['x'],u['y']) not in coords,(case,u)
            coords.add((u['x'],u['y']))
            assert 0<=u['x']<8 and 0<=u['y']<8
            assert 0<u['hp']<=u['maxHp'],(case,u)
            assert 0<=u['shield']<=int(u['maxHp']*.5)
            assert 0<=u['attackProgress']<=1
            assert u['atk']>=0
            assert u['haste'] in [1,2]
    assert all(x['t']<=y['t'] for x,y in zip(events,events[1:]))
    assert all(0<=e['t']<30+1e-6 for e in events)
    assert all(v>0 for v in list(ah.values())+list(bh.values()))
    assert 0<=a['energy']<=40 and 0<=b['energy']<=40
    frames_n+=len(frames);events_n+=len(events)
result={'battles':120,'units_per_side':15,'frames':frames_n,'events':events_n,'errors':0}
(Path(__file__).resolve().parents[1]/'audit/invariants.json').write_text(json.dumps(result,indent=2))
print('PASS battle invariants',result)
