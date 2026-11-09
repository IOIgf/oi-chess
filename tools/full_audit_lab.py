"""全卡真实战斗：净胜血量 + 按游戏幸存棋子数判胜 + 两种混编场景。"""
import argparse,random,json,statistics,hashlib
from pathlib import Path
from balance_lab import load_server
ROOT=Path(__file__).resolve().parents[1]
SEED=20261117

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--trials',type=int,default=24);ap.add_argument('--mixed',type=int,default=120);args=ap.parse_args()
    source_hash=hashlib.sha256((ROOT/'server.py').read_bytes()).hexdigest()
    s=load_server();out=ROOT/args.out;out.mkdir(parents=True,exist_ok=True)
    def team(pid,roster,cells):
        return dict(id=pid,mind=100,energy=40,board={f'{x},{y}':dict(card=cid,hp=s.effective_max_hp(s.CARD_BY_ID[cid])) for cid,(x,y) in zip(roster,cells)})
    def game(aa,bb,i,seed,mirror=False):
        rng=random.Random(seed+i);cells=rng.sample([(x,y) for x in range(8) for y in range(4)],5);a=team('A',aa,cells);b=team('B',bb,cells);random.seed(seed+i);rnd=rng.randint(2,9)
        if i%2:_,ev,bh,ah=s.Room('audit','B')._simulate_battle(b,a,rnd,record=False)
        else:_,ev,ah,bh=s.Room('audit','A')._simulate_battle(a,b,rnd,record=False)
        ah={k:v for k,v in ah.items() if v>0};bh={k:v for k,v in bh.items() if v>0}
        at=sum(s.effective_max_hp(s.CARD_BY_ID[c]) for c in aa);bt=sum(s.effective_max_hp(s.CARD_BY_ID[c]) for c in bb)
        margin=sum(ah.values())/at-sum(bh.values())/bt
        wr=1 if len(ah)>len(bh) else 0 if len(ah)<len(bh) else .5
        return margin,wr
    ids=[c['id'] for c in s.CARDS];values={cid:[] for cid in ids};wr={cid:[] for cid in ids};pairs=[]
    n=0
    for i,x in enumerate(ids):
        for y in ids[i+1:]:
            seed=SEED+int(hashlib.sha256((x+':'+y).encode()).hexdigest()[:6],16)
            v=[game([x]*5,[y]*5,t,seed) for t in range(args.trials)]
            for m,w in v:values[x].append(m);values[y].append(-m);wr[x].append(w);wr[y].append(1-w)
            pairs.append(dict(a=x,b=y,margin=statistics.mean(m for m,w in v),win_score=statistics.mean(w for m,w in v)))
            n+=len(v)
        print('pure',x,n,flush=True)
    measured=[];mixed={};diverse={}
    for c in s.CARDS:
        cid=c['id'];mean=statistics.mean(statistics.mean(values[z['id']]) for z in s.CARDS if z['cost']==c['cost'])
        measured.append(dict(id=cid,name=c['name'],cost=c['cost'],attack=c['attack'],hp=c['hp'],margin=statistics.mean(values[cid]),rel=statistics.mean(values[cid])-mean,win_score=statistics.mean(wr[cid]),battles=len(values[cid]),trials_per_opponent=args.trials))
        for kind,dst in [('reference',mixed),('diverse',diverse)]:
            vals=[]
            for t in range(args.mixed):
                if kind=='reference':aa=['mod_op']*4+[cid];bb=['mod_op']*5
                else:
                    refs=['gcd','mod_op','bfs','monotonic_queue'];aa=refs+[cid]
                    anchor={1:'greedy',2:'mod_op',3:'expectation',4:'genetic',5:'matrix_pow'}[c['cost']]
                    bb=refs+[anchor]
                # 每张卡同场景使用同站位、回合、先后手种子。
                vals.append(game(aa,bb,t,SEED+500000+(kind=='diverse')*100000))
            margins=[m for m,w in vals];dst[c['name']]=dict(id=cid,cost=c['cost'],atk=c['attack'],hp=c['hp'],value=statistics.mean(margins),se=statistics.stdev(margins)/len(margins)**.5,win_score=statistics.mean(w for m,w in vals),trials=args.mixed)
        print('mixed',cid,flush=True)
    for data in [mixed,diverse]:
        for name,r in data.items():r['rel']=r['value']-statistics.mean(v['value'] for v in data.values() if v['cost']==r['cost'])
    for name,data in [('final.json',measured),('mixed_map.json',mixed),('diverse_map.json',diverse),('pairs.json',pairs)]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
    (out/'meta.json').write_text(json.dumps(dict(seed=SEED,pure_battles=n,mixed_battles=len(ids)*args.mixed,diverse_battles=len(ids)*args.mixed,total=n+2*len(ids)*args.mixed,trials=args.trials,mixed_trials=args.mixed,source_sha256=source_hash),indent=2))
    print('DONE',out,flush=True)
if __name__=='__main__':main()
