"""新版特效回归：真实演示、明暗/移动、低特效、节点预算与重复事件。"""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1];OUT=R/'audit/fx';OUT.mkdir(parents=True,exist_ok=True)
errors=[];results={}
with sync_playwright() as p:
    br=p.chromium.launch()
    pg=br.new_page(viewport={'width':1440,'height':960},device_scale_factor=1)
    pg.on('pageerror',lambda e:errors.append(str(e)))
    pg.goto((R/'特效预览.html').as_uri(),wait_until='load')
    pg.wait_for_timeout(3500)
    assert pg.locator('.unit').count()>0
    assert pg.locator('.unit.aura-source').count()==1
    assert pg.locator('.unit.hasted').count()>0
    assert pg.locator('.unit-tags').count()>0
    pg.screenshot(path=str(OUT/'clear-light.png'))
    pg.evaluate("document.documentElement.dataset.theme='dark'")
    pg.wait_for_timeout(350)
    pg.screenshot(path=str(OUT/'clear-dark.png'))
    perf=pg.evaluate("""async()=>{const dt=[];let last=performance.now();await new Promise(done=>{let n=0;function f(t){dt.push(t-last);last=t;if(++n<90)requestAnimationFrame(f);else done()}requestAnimationFrame(f)});dt.sort((a,b)=>a-b);return {median_ms:dt[45],p95_ms:dt[85],nodes:document.querySelector('#fxLayer').childElementCount}}""")
    results['desktop']=perf
    pg.evaluate("for(let i=0;i<500;i++)FX.impact(3,3,0,false)")
    assert pg.locator('#fxLayer > *').count()<=128
    pg.click('#fxMode');assert pg.evaluate("document.documentElement.dataset.fx")=='low'
    pg.evaluate("for(let i=0;i<500;i++)FX.impact(3,3,0,false)")
    assert pg.locator('#fxLayer > *').count()<=40
    results['budgets']={'clear':128,'low':40}
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(OUT/'low-dark.png'))
    pg.set_viewport_size({'width':390,'height':844})
    pg.wait_for_timeout(250)
    pg.screenshot(path=str(OUT/'mobile.png'))
    assert pg.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    # 同一时刻同坐标的两次攻击不再被去重吞掉。
    pg.evaluate("""()=>{stopBattlePlayback();state.playedEventKeys.clear();const e={t:0,type:'attack',fromX:3,fromY:4,toX:3,toY:3,dmg:1,owner:state.playerId};state.currentEvents=[e,{...e}];playEventsUpTo(state.currentD,0)}""")
    assert pg.evaluate('state.playedEventKeys.size')==2
    results['duplicate_events']=2
    br.close()
assert not errors,errors
results['errors']=errors
(OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print('PASS FX audit',json.dumps(results,ensure_ascii=False))
