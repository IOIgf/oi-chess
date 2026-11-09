"""O2：八邻域、同队、存活、不可叠加、无法攻击与实际加速。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from balance_lab import SRV as s
room=s.Room('o2-test','A')
u=dict(owner='A',x=3,y=5,hp=100,skill='expectation')
def aura(x,y,owner='A',hp=300):
    return dict(owner=owner,x=x,y=y,hp=hp,skill='o2_aura')
for dx in [-1,0,1]:
    for dy in [-1,0,1]:
        if dx==dy==0: continue
        assert room._attack_speed_aura(u,[u,aura(3+dx,5+dy)])==2.0
assert room._attack_speed_aura(u,[u,aura(5,5)])==1
assert room._attack_speed_aura(u,[u,aura(4,5,'B')])==1
assert room._attack_speed_aura(u,[u,aura(4,5,hp=0)])==1
assert room._attack_speed_aura(u,[u,aura(4,5),aura(2,5)])==2.0
# 双方对称站位，保证全程留在射程与光环范围内。
s.CARD_BY_ID['expectation']['hp']=100000
s.CARD_BY_ID['o2']['hp']=100000

def player(pid, with_o2):
    cards={'3,0':dict(card='expectation',hp=100000)}
    if with_o2: cards['4,0']=dict(card='o2',hp=100000)
    return dict(id=pid,mind=100,energy=40,board=cards)

def run(with_o2):
    a=player('A',with_o2);b=player('B',with_o2)
    _,events,*_=room._simulate_battle(a,b,3)
    atk=[e for e in events if e['type']=='attack' and e['owner']=='A']
    assert all(e['fromX']==3 for e in atk) # O2 从未出手
    ts=[e['t'] for e in atk]
    return {round(y-x,3) for x,y in zip(ts,ts[1:])}
assert run(False)=={2.0}
assert run(True)=={1.0} # ×2 光环，间隔正好为 1 秒
# 直接调用攻击也不产生事件，避免被追加攻击逻辑绕过。
events=[]
room._do_attack(dict(skill='o2_aura'),{},[],events,0,{},3)
assert not events
assert s.CARD_BY_ID['o2']['attack']==0
assert s.CARD_BY_ID['o2']['hp']==100000 # 上文测试临时覆盖了生命
assert s.O2_SPEED_MULT==2.0
print('PASS O2: eight cells, ally only, living only, non-stacking, no attacks, actual haste')
