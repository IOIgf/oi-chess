"""战斗静止格与弹道中心直接对照真实背景 DOM；不以点击区代替背景。"""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1];results=[]
with sync_playwright() as p:
    b=p.chromium.launch();pg=b.new_page(viewport={'width':1440,'height':960});errors=[]
    pg.on('pageerror',lambda e:errors.append(str(e)))
    pg.goto((R/'特效预览.html').as_uri());pg.wait_for_timeout(100)
    pg.evaluate("""()=>{stopBattlePlayback();const f=state.currentFrames[0];state.currentFrames=[f,{...f,t:30}];state.lastFrameIdx=-1;state.battleEpoch=Date.now()+state.serverOffset;paintBattle()}""")
    def check(label):
        data=pg.evaluate("""()=>{const f=state.currentFrames[0],me=getMe(),fx=document.querySelector('#fxLayer').getBoundingClientRect();return f.units.map(u=>{
            const self=u.owner===me.id;const y=self?u.y-state.halfH:u.y;
            const bg=document.querySelector(self?'#gridLayerSelf':'#gridLayerOpp').children[y*state.halfW+u.x].getBoundingClientRect();
            const a=state.unitMap.get(u.uid).getBoundingClientRect();const q=FX.pt(u.x,u.y);
            return {uid:u.uid,dx:a.x-bg.x,dy:a.y-bg.y,dw:a.width-bg.width,dh:a.height-bg.height,fxX:fx.x+q.x-(bg.x+bg.width/2),fxY:fx.y+q.y-(bg.y+bg.height/2)};
        })}""")
        err=max(abs(v) for d in data for k,v in d.items() if k!='uid');assert err<.1,(label,data)
        results.append({'case':label,'max_error_px':err})
    check('initial battle')
    for w,h in [(1000,700),(390,844),(844,390),(1440,960)]:
        pg.set_viewport_size({'width':w,'height':h});pg.wait_for_timeout(150);check(f'battle {w}x{h}')
    assert not errors,errors;b.close()
(R/'audit/placement/battle-background.json').write_text(json.dumps(results,indent=2))
print('PASS real background + battle units + FX centers:',results)
