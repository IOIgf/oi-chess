"""O2 配对阵容测试：同站位同种子对照，隔离光环收益。"""
import random,json,statistics,contextlib,io
from pathlib import Path
from unittest.mock import patch
import mixed_check as M
s=M.SRV
ROOT=Path(__file__).resolve().parents[1]
N=200
SEED=20261111

def frac(hp,p):
    return sum(max(0,v) for v in hp.values())/sum(s.effective_max_hp(s.CARD_BY_ID[u['card']]) for u in p['board'].values())

def trial(carry,mode,formation,i):
    rng=random.Random(SEED+i)
    # 半场 y=0 在交战前沿，y=3 在后沿；O2 固定最后一个位置。
    if formation=='集中保护':
        cells=[(2,1),(3,1),(4,1),(2,2),(3,2)]
    else:
        cells=[(0,0),(2,0),(5,0),(7,0),(3,3)]
    if i%2: cells=[(7-x,y) for x,y in cells]
    support={'O2':'o2','关闭光环':'o2','再上一张输出':carry}[mode]
    a=M.team('A',[carry]*4+[support],cells)
    b=M.team('B',[carry]*5,cells)
    rnd=rng.randint(2,9)
    random.seed(SEED+i)
    with contextlib.redirect_stdout(io.StringIO()):
        if mode=='关闭光环':
            with patch.object(s.Room,'_attack_speed_aura',staticmethod(lambda u,units:1.0)):
                _,events,ah,bh=s.Room('s','A')._simulate_battle(a,b,rnd,record=False) if not i%2 else s.Room('s','B')._simulate_battle(b,a,rnd,record=False)
        else:
            _,events,ah,bh=s.Room('s','A')._simulate_battle(a,b,rnd,record=False) if not i%2 else s.Room('s','B')._simulate_battle(b,a,rnd,record=False)
    if i%2: ah,bh=bh,ah
    frames=None
    return frac(ah,a)-frac(bh,b)

def main():
    rows=[]
    for carry in ['expectation','spfa','monotonic_queue','bitmask_dp']:
        for formation in ['集中保护','分散后置']:
            vals={mode:[trial(carry,mode,formation,i) for i in range(N)] for mode in ['O2','关闭光环','再上一张输出']}
            delta=[a-b for a,b in zip(vals['O2'],vals['关闭光环'])]
            replace=[a-b for a,b in zip(vals['O2'],vals['再上一张输出'])]
            rows.append(dict(carry=s.CARD_BY_ID[carry]['name'],formation=formation,trials=N,o2=statistics.mean(vals['O2']),disabled=statistics.mean(vals['关闭光环']),extra_carry=statistics.mean(vals['再上一张输出']),aura_gain=statistics.mean(delta),aura_se=statistics.stdev(delta)/N**.5,replace_gain=statistics.mean(replace),replace_se=statistics.stdev(replace)/N**.5))
    (ROOT/'balance/o2_scenarios.json').write_text(json.dumps(dict(seed=SEED,battles=len(rows)*N*3,rows=rows),ensure_ascii=False,indent=2))
    print(json.dumps(rows,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
