"""放置回归：点击坐标、棋子边界、缩放与无需轮询的布局变化。"""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1]
errors=[];results=[]
with sync_playwright() as p:
    br=p.chromium.launch();pg=br.new_page(viewport={'width':1440,'height':960})
    pg.on('pageerror',lambda e:errors.append(str(e)))
    pg.goto((R/'特效预览.html').as_uri(),wait_until='load')
    pg.evaluate("""()=>{
        stopBattlePlayback();const d=window.__DEMO_DATA__.state;d.state='prep';d.version=10000;d.prepEndsAt=Date.now()/1000+3600;
        const me=d.players[d.viewerId];me.board={};me.bench=Array.from({length:10},()=>({card:'expectation',hp:970}));
        state.lastVersion=-1;window.__placed=[];
        doAction=async function(action,args){if(action==='place'){window.__placed.push(args);me.board[`${args.x},${args.y}`]=me.bench.splice(args.benchIndex,1)[0];d.version++;render(d);return true}return true};render(d);
    }""")
    pg.wait_for_timeout(150)
    for x,y in [(0,0),(7,0),(0,3),(7,3),(3,1)]:
        pg.locator('#benchList .bench-card').first.click()
        pg.locator(f'#cellLayerPrep .cell[data-x="{x}"][data-y="{y}"]').click()
        pg.wait_for_timeout(30)
        args=pg.evaluate('window.__placed.at(-1)');assert (args['x'],args['y'])==(x,y),args
    def measure(label):
        data=pg.evaluate("""()=>Array.from(state.prepUnitMap.entries()).map(([key,el])=>{
            const [x,y]=key.split(',');const cell=document.querySelector(`#cellLayerPrep .cell[data-x="${x}"][data-y="${y}"]`);
            const a=el.getBoundingClientRect(),b=cell.getBoundingClientRect();
            const g=document.querySelector('#gridLayerPrep').children[Number(y)*state.halfW+Number(x)].getBoundingClientRect();
            const v=el.querySelector('.unit-inner').getBoundingClientRect();
            return {key,dx:a.x-b.x,dy:a.y-b.y,dw:a.width-b.width,dh:a.height-b.height,background_dx:a.x-g.x,background_dy:a.y-g.y,background_dw:a.width-g.width,background_dh:a.height-g.height,visible_dx:v.x-g.x,visible_dy:v.y-g.y,visible_dw:v.width-g.width,visible_dh:v.height-g.height};})""")
        worst=max(abs(v) for d in data for k,v in d.items() if k!='key')
        results.append({'case':label,'worst_error_px':worst})
        assert worst<.15,(label,data)
    measure('initial placement')
    for width,height in [(1000,700),(390,844),(844,390),(1440,960)]:
        pg.set_viewport_size({'width':width,'height':height});pg.wait_for_timeout(150);measure(f'resize {width}x{height}')
    # 浏览器缩放会触发布局变化；不重新render数据，也不触发window resize。
    pg.evaluate("document.body.style.zoom='1.25';fitBoard()")
    pg.wait_for_timeout(100);measure('125 percent zoom')
    pg.evaluate("document.body.style.zoom='1';document.querySelector('#prepBoard').style.width='603px';document.querySelector('#prepBoard').style.height='301px'")
    pg.wait_for_timeout(50);measure('layout changes without data update')
    # 验证缩放后继续放置不会落到邻格。
    pg.locator('#benchList .bench-card').first.click()
    pg.locator('#cellLayerPrep .cell[data-x="6"][data-y="2"]').click();pg.wait_for_timeout(50)
    args=pg.evaluate('window.__placed.at(-1)');assert (args['x'],args['y'])==(6,2)
    measure('place after layout change')
    (R/'audit/placement').mkdir(parents=True,exist_ok=True)
    pg.screenshot(path=str(R/'audit/placement/fixed.png'))
    br.close()
assert not errors,errors
(R/'audit/placement/results.json').write_text(json.dumps({'cases':results,'errors':errors},ensure_ascii=False,indent=2))
print('PASS placement regression:',json.dumps(results,ensure_ascii=False))
