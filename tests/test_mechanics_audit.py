"""逐卡机制合同：由真实服务器函数验证，不使用评分器预测值。"""
import sys,math,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from balance_lab import load_server
s=load_server();r=s.Room('contract','A');checks=[]
def ok(cond,label):
    assert cond,label
    checks.append(label)
def unit(cid='expectation',owner='A',x=3,y=4,hp=6000):
    u=r._unit_from(owner,'3,0',{'card':cid,'hp':s.effective_max_hp(s.CARD_BY_ID[cid])},'a' if owner=='A' else 'b',{'A':{'out':1,'in':1},'B':{'out':1,'in':1}},3)
    u.update(uid=f'{owner}:{x},{y}:{cid}',x=x,y=y,hp=float(hp),maxHp=float(hp),atk=120.,baseAtk=120.,range=5)
    return u
def skill(cid,coords):
    u=unit(cid);es=[unit(owner='B',x=x,y=y) for x,y in coords];us=[u]+es;ev=[]
    r._use_skill(u,es[0],es,us,ev,0,{a['uid']:a for a in us},3)
    return u,es,ev
# 数值与元数据（全部 35 张）。
for c in s.CARDS:
    ok(c['active']==(c['skill'] in s.ACTIVE_SKILLS),c['id']+' active flag')
    ok(c['desc'].startswith('技能：' if c['active'] else '被动：'),c['id']+' description kind')
    u=unit(c['id']);e=unit(owner='B',y=3);ev=[]
    if c['active']:r._use_skill(u,e,[e],[u,e],ev,0,{u['uid']:u,e['uid']:e},3)
    else:r._do_attack(u,e,[u,e],ev,0,{u['uid']:u,e['uid']:e},3)
    ok(bool(ev) or c['id']=='o2',c['id']+' executable')
ok(s.CARD_BY_ID['o2']['hp']==280,'O2 current 280 HP')
# 射程优先，不能为了远处残血/高攻放弃射程内目标。
for cid in ['greedy','a_star','monotonic_queue','xor']:
    u=unit(cid);near=unit(owner='B',y=3);far=unit(owner='B',x=7,y=0,hp=1);far['atk']=999
    ok(r._pick_target(u,[far,near]) is near,cid+' range-priority target')
# 被动倍率与叠层节奏。
for cid,expected in [('spfa',1.2),('expectation',1.25),('prime_sieve',1.8),('fermat',1.8),('cdq',.6),('matrix_pow',1),('genetic',1)]:
    u=unit(cid);e=unit(owner='B');v=r._attack_multiplier(u,e,[u,e],0,3)
    ok(abs(v-40*expected)<1e-8,cid+' damage multiplier')
for cid,n,mult in [('monotonic_stack',4,3),('segment_tree',4,3),('mod_op',3,2.5)]:
    u=unit(cid);e=unit(owner='B');v=[r._attack_multiplier(u,e,[u,e],0,3)/40 for _ in range(n)]
    ok(v==[1]*(n-1)+[mult],cid+' burst cadence')
u=unit('cdq');e=unit(owner='B');ok(r._attack_multiplier(u,e,[u,e],10,3)==72,'CDQ exact 10s threshold')
u=unit('matrix_pow');ok(abs(r._attack_multiplier(u,e,[u,e],18,3)-40*1.2**3)<1e-8,'matrix max growth')
u=unit('genetic');u['kills']=3;ok(r._attack_multiplier(u,e,[u,e],0,3)==58,'genetic max growth')
# 射程裁剪：全场 BFS 是唯一例外。
for cid in ['xor','quick_sort','bidirectional','sweep_line','diff','linear_dp','range_dp','sqrt_block','divide','bitmask_dp','sort']:
    _,es,_=skill(cid,[(3,3),(7,0)])
    ok(es[1]['hp']==6000 and not es[1]['delayed'] and not es[1]['swap'],cid+' excludes out-of-range enemy')
_,es,ev=skill('bfs',[(3,3),(7,0)]);ok(all(e['slowUntil']==3 for e in es),'BFS global slow 3s');ok(all(e['hp']==5986 for e in es),'BFS 35% damage')
_,es,_=skill('linear_dp',[(2,3),(3,3),(4,3)]);ok(all(e['hp']==5980 for e in es),'linear DP target row 50%')
_,es,_=skill('range_dp',[(3,3),(2,3),(4,3),(5,3)]);ok([e['hp'] for e in es]==[5968,5968,5968,6000],'range DP target +/-1')
_,es,_=skill('sqrt_block',[(3,3),(2,3),(3,2),(2,2),(4,3)]);ok([e['hp'] for e in es]==[5972]*4+[6000],'sqrt fixed aligned 2x2')
_,es,_=skill('sweep_line',[(3,3),(2,3),(4,3),(1,3)]);ok(sorted(6000-e['hp'] for e in es)==[0,24,36,48],'sweep three distance-ordered hits')
_,es,_=skill('bidirectional',[(3,3),(1,2)]);ok(all(e['hp']==5952 for e in es),'pincer near and far 120%')
_,es,_=skill('divide',[(3,3),(2,3)]);ok(all(e['hp']==5940 for e in es),'divide 50%+100%')
_,es,ev=skill('diff',[(3,3),(2,3)]);ok(all(e['hp']==6000 and e['delayed'][0][0]==2 and e['delayed'][0][1]==60 for e in es),'diff exact delayed payload')
# 树状数组应响应友军普攻和施法。
u=unit('linear_dp');a=unit('tree_array',x=4);e=unit(owner='B',y=3);ev=[];units=[u,a,e]
r._use_skill(u,e,[e],units,ev,0,{x['uid']:x for x in units},3);ok(a['stacks']==1,'tree array counts skills')
r._do_attack(u,e,units,ev,1,{x['uid']:x for x in units},3);ok(a['stacks']==2,'tree array counts attacks')
# 遗传击杀不重复计数；成长能在幸存棋子跨回合保留。
u=unit('genetic');e=unit(owner='B',y=3,hp=1);ev=[];us=[u,e]
r._do_attack(u,e,us,ev,0,{x['uid']:x for x in us},3);ok(u['kills']==1,'genetic one kill once')
r._deal_damage(e,100,ev,0,us,{},source=u);ok(u['kills']==1,'dead target no repeated kill')
u=r._unit_from('A','3,0',{'card':'genetic','hp':1510,'kills':2},'a',{'A':{'out':1,'in':1}},4);ok(u['kills']==2,'genetic persistent stacks load')
# 多重攻击交换到期后从基础值重放，不能负攻击或永久串值。
a,b,c=unit('xor'),unit(owner='B',x=2),unit(owner='B',x=4)
a['baseAtk']=a['atk']=100;b['baseAtk']=b['atk']=200;c['baseAtk']=c['atk']=1
us=[a,b,c];t1=(0,0,a['uid'],b['uid'],6);t2=(3,1,a['uid'],c['uid'],9)
a['swap']=[t1,t2];b['swap']=[t1];c['swap']=[t2]
r._refresh_swaps(us,3);ok([x['atk'] for x in us]==[1,100,200],'overlap swaps active order')
r._refresh_swaps(us,6);ok([x['atk'] for x in us]==[1,200,100],'overlap swaps first expiry nonnegative')
r._refresh_swaps(us,9);ok([x['atk'] for x in us]==[100,200,1],'overlap swaps full restoration')
# 合并同时结算，保留总血量与上限，不受输入遍历顺序影响。
a=unit('merge_sort',x=3,y=4,hp=900);b=unit(x=4,y=4,hp=100);c=unit('o2',x=3,y=5,hp=50);c['maxHp']=280
a['maxHp']=b['maxHp']=1000;us=[a,b,c];r._apply_spawn_passives(us);ok(abs(sum(x['hp'] for x in us)-1050)<1e-8,'merge conserves total HP');ok(c['hp']==280 and a['hp']==b['hp']==385,'merge capped equalization')
# 技能命中和扣血同一时刻；不是先扣血后播放未来命中。
for cid in ['linear_dp','bidirectional','sweep_line','divide']:
    _,_,ev=skill(cid,[(3,3),(2,3)])
    ok(all(e['t']==0 for e in ev),cid+' event time equals damage time')
# record=False 不影响任何结算，只省略回放序列化。
def player(pid,cid):return {'id':pid,'mind':100,'energy':40,'board':{'3,0':{'card':cid,'hp':s.effective_max_hp(s.CARD_BY_ID[cid])}}}
with patch.object(s.random,'random',return_value=1):
    a=r._simulate_battle(player('A','spfa'),player('B','expectation'),3)
    b=r._simulate_battle(player('A','spfa'),player('B','expectation'),3,record=False)
ok(a[1:]==b[1:] and b[0]==[],'record=False same authoritative battle')
# 每张卡的技能分支必须由上述测试及压力对战至少一次执行。
print('PASS mechanics audit:',len(checks),'checks,',len(s.CARDS),'cards')
Path(__file__).with_name('mechanics_audit_results.json').write_text(json.dumps({'passed':len(checks),'cards':len(s.CARDS),'checks':checks},ensure_ascii=False,indent=2))
# 护盾转化应在本次受伤后到账，不能让新盾立刻吃掉剩余伤害。
a=unit('pruning');a['atk']=a['baseAtk']=120;b=unit(owner='B',y=3);ev=[]
r._deal_damage(a,40,ev,0,[a,b],{a['uid']:a,b['uid']:b},source=b)
ok(a['hp']==5980 and a['shield']==20,'pruning damage before new shield')
ok(ev[-1]['dmg']==20,'shield event actual gained value')
# 固定上限，不能把截断的盾值也显示为获得。
a['shield']=a['maxHp']*.5;r._deal_damage(a,40,ev,1,[a,b],{},source=b)
ok(a['shield']==a['maxHp']*.5,'pruning refill only after old shield absorbs')
# 新伤害到达时已有盾先吸收，后续转化再到账。
ok(a['hp']==5980,'old shield absorbs subsequent damage')
# 成长真实跨战斗持久化，而非仅测试加载字段。
a={'id':'A','mind':100,'energy':40,'board':{'3,0':{'card':'genetic','hp':1510}}}
b={'id':'B','mind':100,'energy':40,'board':{'3,0':{'card':'greedy','hp':1}}}
r._simulate_battle(a,b,3,record=False);ok(a['board']['3,0']['kills']==1,'genetic stores surviving growth between rounds')
# 区域元数据在对手视角也必须镜像。
ev=[{'t':0,'type':'skill','y':4,'toY':3,'targets':[{'x':2,'y':3}]}]
mir=r._transform_event_for_viewer(ev,'b')[0];ok(mir['targets'][0]['y']==4 and mir['y']==3,'mirror nested skill targets')
# 归并余量采用确定性整数分配，避免活棋子显示为0血。
a=unit('merge_sort',x=3,y=4,hp=100);b=unit(x=4,y=4,hp=101);a['maxHp']=b['maxHp']=1000
r._apply_spawn_passives([a,b]);ok(sorted([a['hp'],b['hp']])==[100,101],'merge integer HP remainder')
print('PASS full mechanics audit:',len(checks),'checks')
Path(__file__).with_name('mechanics_audit_results.json').write_text(json.dumps({'passed':len(checks),'cards':len(s.CARDS),'checks':checks},ensure_ascii=False,indent=2))
# 全部 35 张卡逐项验证战内攻击/有效生命/回合射程，而非只验证可执行。
for c in s.CARDS:
    for rnd in [1,5]:
        stats={'A':{'out':1,'in':1}}
        u=r._unit_from('A','3,0',{'card':c['id'],'hp':s.effective_max_hp(c)},'a',stats,rnd)
        expected_atk=c['attack']*(2 if c['skill']=='shift_stats' else 1.5 if c['skill']=='matrix_pow' else 1)
        ok(u['atk']==expected_atk,c['id']+f' round{rnd} exact battle attack')
        ok(u['maxHp']==s.effective_max_hp(c),c['id']+f' round{rnd} exact max HP')
        ok(u['range']==c['range']+(rnd-1 if c['id']=='ids' else 0),c['id']+f' round{rnd} exact range')
# 分担有整数余量时必须分配完整总量，而非静默丢失。
a=unit(x=3,y=4);links=[unit('gcd',x=x,y=y) for x,y in [(2,4),(4,4),(3,5)]];b=unit(owner='B',y=3);us=[a,b]+links;ev=[]
r._deal_damage(a,45,ev,0,us,{u['uid']:u for u in us},source=b)
ok(sum(6000-u['hp'] for u in [a]+links)==45,'link total damage conservation')
ok(sum(6000-u['hp'] for u in links)==13,'link all integer remainder distributed')
ok(len([e for e in ev if e.get('skillId')=='gcd_share'])==3,'link share emits hit events')
# DFS 本场最多追击三次，且伤害与回放事件时刻一致。
a=unit('dfs');es=[unit(owner='B',x=x,y=3,hp=1) for x in range(1,6)];us=[a]+es;ev=[]
r._do_attack(a,es[0],us,ev,0,{u['uid']:u for u in us},3)
ok(sum(e['hp']<=0 for e in es)==4 and a['kills']==3,'DFS max three immediate followups')
ok(all(e['t']==0 for e in ev),'DFS immediate damage and event time agree')
# 不同心态的统一缩放与整数伤害。
for raw,inc in [(40,1),(40,1.1),(40.9,1),(1.1,.5)]:
    a=unit();a['inMult']=inc;ev=[];d=r._deal_damage(a,raw,ev,0,[a],{},allow_react=False)
    ok(d==max(1,int(raw*inc)),'global damage floor '+str((raw,inc)))
print('PASS complete mechanics audit:',len(checks),'checks')
Path(__file__).with_name('mechanics_audit_results.json').write_text(json.dumps({'passed':len(checks),'cards':len(s.CARDS),'checks':checks},ensure_ascii=False,indent=2))
