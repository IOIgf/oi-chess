"""整理当前项目为唯一最新版下载包；不打包玩家存档、缓存、旧包和截图。"""
from pathlib import Path
import json,hashlib,zipfile,tempfile,types,re
R=Path(__file__).resolve().parents[1]
DEST=R.parent/'OI-chess_最新版.zip'
# Reproducibility gate: the shipped source must be the exact source that produced
# audit/final/*.json. Rerun full_audit_lab.py whenever server.py changes.
_meta=json.loads((R/'audit/final/meta.json').read_text('utf-8'))
_src=hashlib.sha256((R/'server.py').read_bytes()).hexdigest()
assert _meta['source_sha256']==_src,(
    'server.py changed since the last full audit; rerun: '
    'python3 tools/full_audit_lab.py --out audit/final --trials 32 --mixed 200')
def _contracts(f):
    m=re.search(r'(\d+) 项机制合同',(R/f).read_text('utf-8'))
    return m.group(1) if m else None
_rm,_rp=_contracts('README.md'),_contracts('完整检查与平衡报告.md')
assert _rm and _rp and _rm==_rp,(
    'mechanics contract count disagrees between README.md and 完整检查与平衡报告.md')
# Local release version is single-sourced in index.html; the launcher, browser
# check and this manifest all read the same value.
_tagm=re.search(r'<meta\s+name="oi-chess-release"\s+content="([^"]+)"',
                (R/'static'/'index.html').read_text('utf-8'))
assert _tagm,'static/index.html missing oi-chess-release meta'
RELEASE_TAG=_tagm.group(1)
files=[]
for p in R.rglob('*'):
    if not p.is_file():continue
    rel=p.relative_to(R)
    # rglob('*') descends into hidden dirs; skip VCS metadata so a .git/
    # never leaks into 版本清单.json or the release archive.
    if any(x in rel.parts for x in ['__pycache__','data','shots','stress_data','.git']):continue
    if p.suffix in ['.pyc','.zip'] or rel.as_posix()=='版本清单.json':continue
    if rel.parts[:2]==('audit','fx') and p.suffix=='.png':continue
    if rel.parts[:2]==('audit','placement') and p.suffix=='.png':continue
    files.append(p)
manifest={'release':'最新版（50 张卡 = 50 种独立技能 + 全局羁绊机制 + 场上上限 20 + 负面技能平衡 + 启动前检查更新（代理可选） + 准备期无倒计时（全员点准备才开战） + 商店升星保底 + 按等级解锁卡池 + 状态轮询瘦响应 + 半屏布局遮挡修复 + 可复现性校验 + Windows 编码修复 + 启动期控制台编码兜底（非中文代码页不崩） + 退出期标准流 flush 兜底（无 Exception ignored） + 整体视觉精修与信息可读性 + 项目治理（MIT LICENSE / GitHub Actions CI / UTF-8 可读源码 / 端口可配置 / 巨型函数拆分 / 历史后端清理））','build':'ui-polish-1','release_tag':RELEASE_TAG,'entrypoint':'start.bat（启动前检查更新）/ py -3 server.py','server_utf8':bool((R/'server.py').read_bytes().decode('utf-8')),'current_cards':{'o2':{'attack':0,'hp':280,'cost':3,'aura_speed_multiplier':2},'spfa':{'attack':120,'hp':1000,'cost':3}},'files':{p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}}
(R/'版本清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));files.append(R/'版本清单.json')
with zipfile.ZipFile(DEST,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('oi-chess/data/','')
    for p in sorted(files):z.write(p,Path('oi-chess')/p.relative_to(R))
with tempfile.TemporaryDirectory() as tmp:
    with zipfile.ZipFile(DEST) as z:
        assert z.testzip() is None;z.extractall(tmp)
    root=Path(tmp)/'oi-chess';m=json.loads((root/'版本清单.json').read_text())
    for name,digest in m['files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
    b=(root/'server.py').read_bytes();b.decode('utf-8');compile(b,'server.py','exec')
    mod=types.ModuleType('release_check');mod.__file__=str(root/'server.py');exec(compile(b,'server.py','exec'),mod.__dict__)
    assert len(mod.CARDS)==50 and mod.CARD_BY_ID['o2']['hp']==280 and mod.CARD_BY_ID['spfa']['hp']==1000
    # 50 张卡必须 50 种互不重复的技能，羁绊与上场上限也要与文档一致
    assert len({c['skill'] for c in mod.CARDS})==50,('cards must carry 50 distinct skills')
    assert mod.MAX_BOARD==20 and mod.MAX_BENCH==10,('board cap must be 20, bench cap 10')
    assert tuple(mod.BOND_TIERS)==(2,4,6) and len(mod.BOND_EFFECTS)==3,('bond tiers must be 2/4/6')
    assert not any(c['skill']=='synergy' for c in mod.CARDS),('card-only synergy must be gone')
    assert (root/'static/script.js').exists() and (root/'start.bat').read_bytes().isascii()
    _cu=root/'check_update.py';assert _cu.exists(),'check_update.py missing from release'
    _cus=_cu.read_text('utf-8');assert 'urllib.request' in _cus and 'import requests' not in _cus
    _sb=(root/'start.bat').read_bytes().decode('ascii')
    assert _sb.index('check_update.py')<_sb.index('server.py'),'start.bat must check updates before launching'
    _im=re.search(r'<meta\s+name="oi-chess-release"\s+content="([^"]+)"',(root/'static'/'index.html').read_text('utf-8'))
    assert _im and m['release_tag']==_im.group(1),'release_tag disagrees with index.html'
    assert not list((root/'data').iterdir())
print('PASS release checks:',DEST,len(files),'files',round(DEST.stat().st_size/1024),'KiB')
