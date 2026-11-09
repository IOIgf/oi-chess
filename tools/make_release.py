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
manifest={'release':'最新版（商店卡片自适应与半屏棋盘修复 + 半屏布局遮挡修复 + 状态轮询瘦响应 + 按等级解锁卡池 + 可复现性校验 + Windows 编码修复 + 背景格线对齐 grid-align-2）','build':'layout-2','entrypoint':'start.bat / py -3 server.py','server_ascii_only':(R/'server.py').read_bytes().isascii(),'current_cards':{'o2':{'attack':0,'hp':280,'cost':3,'aura_speed_multiplier':2},'spfa':{'attack':120,'hp':1000,'cost':3}},'files':{p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}}
(R/'版本清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));files.append(R/'版本清单.json')
with zipfile.ZipFile(DEST,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('oi-chess/data/','')
    for p in sorted(files):z.write(p,Path('oi-chess')/p.relative_to(R))
with tempfile.TemporaryDirectory() as tmp:
    with zipfile.ZipFile(DEST) as z:
        assert z.testzip() is None;z.extractall(tmp)
    root=Path(tmp)/'oi-chess';m=json.loads((root/'版本清单.json').read_text())
    for name,digest in m['files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
    b=(root/'server.py').read_bytes();assert b.isascii();compile(b,'server.py','exec')
    mod=types.ModuleType('release_check');mod.__file__=str(root/'server.py');exec(compile(b,'server.py','exec'),mod.__dict__)
    assert len(mod.CARDS)==35 and mod.CARD_BY_ID['o2']['hp']==280 and mod.CARD_BY_ID['spfa']['hp']==1000
    assert (root/'static/script.js').exists() and (root/'start.bat').read_bytes().isascii()
    assert not list((root/'data').iterdir())
print('PASS release checks:',DEST,len(files),'files',round(DEST.stat().st_size/1024),'KiB')
