"""卡池、评分、实战数据、CSV 和 HTML 终版一致性。"""
import sys,json,csv,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import card_power as C
R=Path(__file__).resolve().parents[1];s=C.load_server();rows,measured=C.score_all();mixed=C.load_mixed()
assert len(rows)==len(measured)==len(mixed)==len(s.CARDS)==50
assert max(x['power'] for x in rows)==1000
for x in rows:
    c=s.CARD_BY_ID[x['id']];m=measured[x['id']];mx=mixed[x['name']]
    assert x['attack']==m['attack']==mx['atk']==c['attack']
    assert x['hp']==m['hp']==mx['hp']==c['hp']
    assert x['eff_hp']==s.effective_max_hp(c)
    assert 0<=x['value']<=10
    assert abs(x['cost_units']-(c['cost']/20+c['energy']/25+c['reason']/16))<1e-9
    assert abs(sum(x['contrib'].values())-x['power'])<1e-8
    assert c['role'] and c['position'] and c['tip']
    assert 0<=m['win_score']<=1 and 0<=mx['win_score']<=1
meta=json.loads((R/'audit/final/meta.json').read_text())
assert meta['source_sha256']==hashlib.sha256((R/'server.py').read_bytes()).hexdigest()
cs=list(csv.DictReader((R/'卡牌战力评分.csv').open(encoding='utf-8-sig')))
assert len(cs)==len(s.CARDS)
for x in cs:assert x['实测纯卡净胜血量'] and x['实测混编净胜血量'] and x['多样混编净胜血量']
assert next(x for x in cs if x['ID']=='o2')['生命']=='280'
assert next(x for x in cs if x['ID']=='spfa')['生命']=='1000'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch();pg=b.new_page(viewport={'width':1440,'height':960});errors=[]
    pg.on('pageerror',lambda e:errors.append(str(e)))
    pg.goto((R/'卡牌战力评分.html').as_uri(),wait_until='load')
    assert pg.locator('#cardRows > tr').count()==len(s.CARDS)
    pg.fill('#q','O2');assert pg.locator('#cardRows > tr').count()==1
    pg.locator('#cardRows summary').click();assert pg.locator('details[open]').count()==1
    assert '280' in pg.locator('#cardRows').inner_text()
    n3 = sum(1 for c in s.CARDS if c['cost']==3)
    pg.fill('#q','');pg.select_option('#tier','3');assert pg.locator('#cardRows > tr').count()==n3
    pg.select_option('#order','mix');assert pg.locator('#cardRows > tr').count()==n3
    assert not errors,errors
    pg.select_option('#tier','0');pg.screenshot(path=str(R/'audit/fx/score-table.png'),full_page=True)
    b.close()
print('PASS report audit: %d current cards, all measured columns, exact source hash, cost/weight formulas, HTML controls' % len(s.CARDS))
