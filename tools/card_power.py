# -*- coding: utf-8 -*-
"""卡牌战力评分：六维带权 → 0~1000；再结合金币/精力/理智花费 → 性价比 0~10。

评分维度与权重（合计 100%）：
    血量        22%   有效生命上限（含移位的 ×0.5、矩阵快速幂的 ×0.9）
    单体攻击    26%   单次有效攻击力（含入场的 ×2 / ×1.5 倍率）
    群体攻击    13%   能同时覆盖多少目标（技能多目标 / 穿透 / 全场）
    攻速        10%   6 秒内的有效出手次数（基础 2 秒一次，只有追加攻击类会更高）
    特性/技能   21%   控制、减伤、成长、补刀、换攻、团队光环等非直接伤害价值
    定位        8%    射程 + 血量决定的阵型适配度（前排能不能站住、后排安不安全）

运行： python3 tools/card_power.py
输出： 卡牌战力评分.html / 卡牌战力评分.csv
"""
import csv, json, os, types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV_PATH = os.path.join(ROOT, 'server.py')

# 方案 A = 初版权重；方案 B = 按实测偏差（模型高估机制、低估数值）下调特性、上调数值
W_A = {'hp': 0.22, 'st': 0.26, 'aoe': 0.13, 'spd': 0.10, 'skill': 0.21, 'role': 0.08}
W_B = {'hp': 0.25, 'st': 0.29, 'aoe': 0.13, 'spd': 0.10, 'skill': 0.15, 'role': 0.08}
W = W_B          # 默认方案
W_NAME = {'hp': '血量', 'st': '单体', 'aoe': '群体', 'spd': '攻速', 'skill': '特性', 'role': '定位'}

# ---- 每张卡的机制评分（0~1，人工判定 + 实测校验）----------------------------
# aoe：多目标覆盖度；spd：6 秒内额外出手；skill：非伤害类机制价值
JUDGE = {
    # 1 费
    'dfs':            dict(aoe=0.05, spd=0.55, skill=0.50, why='击杀后追加攻击，能滚雪球，但要先抢到人头'),
    'diff':           dict(aoe=0.65, spd=0.40, skill=0.35, why='整行 150% 延迟伤害，覆盖广但基础攻击低、2 秒后才结算'),
    'gcd':            dict(aoe=0.10, spd=0.30, skill=0.55, why='相邻友军受伤时替其分担 30%，团队减伤但自己掉血'),
    'greedy':         dict(aoe=0.05, spd=0.30, skill=0.45, why='优先攻击射程内生命最低者，只补刀不增伤'),
    'linear_dp':      dict(aoe=0.55, spd=0.40, skill=0.40, why='同行/同列一条线全打，站位好时白赚'),
    'monotonic_stack':dict(aoe=0.05, spd=0.30, skill=0.50, why='每第 4 次普攻 ×3，平均 +50% 但前三次很软'),
    'sort':           dict(aoe=0.45, spd=0.40, skill=0.50, why='打乱整行敌人站位，能破坏对面阵型（控场类）'),
    'tree_array':     dict(aoe=0.05, spd=0.30, skill=0.70, why='每名友军行动 +8% 攻击、上限 6 层，全家桶光环'),
    'xor':            dict(aoe=0.05, spd=0.30, skill=0.65, why='与射程内攻击最高的敌人交换攻击 6 秒，专治大哥'),
    # 2 费
    'bfs':            dict(aoe=0.75, spd=0.40, skill=0.62, why='全场 35% + 减速 3 秒，等于让对面全体少打一次'),
    'divide':         dict(aoe=0.85, spd=0.40, skill=0.45, why='射程内全体 50%，无人阵亡再补 100%，合计最高 150%'),
    'ids':            dict(aoe=0.05, spd=0.30, skill=0.55, why='每回合射程 +1，长局后排站桩越打越远'),
    'inverse':        dict(aoe=0.15, spd=0.30, skill=0.60, why='受普攻反弹 35%，对面打得越猛越亏'),
    'merge_sort':     dict(aoe=0.05, spd=0.30, skill=0.70, why='入场与相邻友军均分生命总和，能把两个残血拉成两个健康'),
    'mod_op':         dict(aoe=0.05, spd=0.30, skill=0.55, why='每第 3 次普攻 ×2.5，比单调栈来得更快'),
    'pigeonhole':     dict(aoe=0.30, spd=0.30, skill=0.50, why='目标周围 3×3 有 ≥3 敌人时伤害翻倍，看对面站位'),
    'prime_sieve':    dict(aoe=0.05, spd=0.30, skill=0.50, why='质数回合 ×1.8，10 回合里有 4 个质数，期望 +32%'),
    'pruning':        dict(aoe=0.05, spd=0.30, skill=0.65, why='单次伤害低于自身攻击 50% 时减半并转盾，天然克制小碎伤'),
    'quick_sort':     dict(aoe=0.60, spd=0.40, skill=0.50, why='对射程内攻击最高的一半敌人造成 100%，专打对面输出'),
    'range_dp':       dict(aoe=0.58, spd=0.40, skill=0.45, why='目标及左右相邻格 80%，密集阵型好使'),
    'segment_tree':   dict(aoe=0.05, spd=0.30, skill=0.50, why='每第 4 次普攻 ×3，与单调栈同机制但基础数值更高'),
    'shift':          dict(aoe=0.05, spd=0.35, skill=0.45, why='入场攻击 ×2、生命 ×0.5，纯换血的高攻脆皮'),
    'sqrt_block':     dict(aoe=0.55, spd=0.40, skill=0.45, why='目标所在 2×2 区域 70%，贴脸团战收益最大'),
    # 3 费
    'a_star':         dict(aoe=0.05, spd=0.30, skill=0.50, why='优先攻击射程内生命最低者，高攻补刀极快'),
    'bidirectional':  dict(aoe=0.35, spd=0.40, skill=0.60, why='最近与最远各 120%，跨排点杀，无视阵型'),
    'bitmask_dp':     dict(aoe=0.70, spd=0.40, skill=0.70, why='整行友军攻击力之和化作一击，堆一行就是斩首炮'),
    'cdq':            dict(aoe=0.05, spd=0.30, skill=0.55, why='前 10 秒 ×0.6、之后 ×1.8，30 秒战斗里后半程是主力'),
    'expectation':    dict(aoe=0.05, spd=0.30, skill=0.10, why='伤害恒定 ×1.25，无随机、无前置条件'),
    'fermat':         dict(aoe=0.05, spd=0.30, skill=0.50, why='质数回合 ×1.8，与质数筛同机制但基础数值高一档'),
    'monotonic_queue':dict(aoe=0.05, spd=0.30, skill=0.58, why='优先攻击射程内攻击力最高者，直接废掉对面 C 位'),
    'sweep_line':     dict(aoe=0.65, spd=0.40, skill=0.55, why='同一行由近到远 60%/90%/120%，越打越疼'),
    'o2':             dict(aoe=0.0, spd=0.0, skill=0.85, why='无法攻击、280 生命；周围八格友军攻速 ×2，不叠加，依赖站位与队友，模型对纯辅助仅作参考'),
    'spfa':           dict(aoe=0.05, spd=0.30, skill=0.10, why='攻速 ×1.5、普攻伤害 ×1.2；每击后独立 20% 概率额外停攻 4 秒，无其他效果'),
    # 4 / 5 费
    'genetic':        dict(aoe=0.05, spd=0.35, skill=0.65, why='每次击杀永久 +15% 攻击（3 层），滚起来无解'),
    'matrix_pow':     dict(aoe=0.05, spd=0.35, skill=0.62, why='每 6 秒攻击 ×1.2（3 层）+ 射程 8，站最远也能打到全场'),
}

TEAM_CARDS = {'gcd', 'tree_array', 'merge_sort', 'o2'}
HP_CAP = 1510.0     # 全池最高有效生命（遗传算法）
ATK_CAP = 232.0     # 全池最高有效攻击（矩阵快速幂 155×1.5）
GOLD_PER_ROUND, ENERGY_PER_ROUND, REASON_PER_ROUND = 20.0, 25.0, 16.0


def load_server():
    src = open(SRV_PATH, encoding='utf-8-sig').read().replace("if __name__ == '__main__':", 'if False:')
    srv = types.ModuleType('srv')
    srv.__file__ = SRV_PATH
    exec(compile(src, 'server.py', 'exec'), srv.__dict__)
    return srv


def role_rating(card, eff_hp):
    r, h = card['range'], min(1.0, eff_hp / HP_CAP)
    if r <= 4:
        base = 0.30 + 0.45 * h          # 射程 4：必须贴着中线站，血越厚越站得住
    elif r == 5:
        base = 0.62 + 0.30 * h          # 射程 5：能站中排打到对面第二排
    elif r == 6:
        base = 0.78 + 0.18 * h
    else:
        base = 0.86 + 0.12 * h          # 射程 8：站最后一排也能覆盖全场
    if card['id'] in TEAM_CARDS:
        base += 0.12                     # 光环类，站位本身就是团队收益
    return min(1.0, base)


def score_all(weights=None):
    Wt = weights or W
    srv = load_server()
    cards = srv.CARDS
    hp_cap = max(srv.effective_max_hp(c) for c in cards)
    atk_cap = max(c['attack'] * (2 if c['skill'] == 'shift_stats' else 1.5 if c['skill'] == 'matrix_pow' else 1) for c in cards)
    rows = []
    for c in cards:
        cid = c['id']
        eff_hp = float(srv.effective_max_hp(c))
        mult = 2.0 if c['skill'] == 'shift_stats' else 1.5 if c['skill'] == 'matrix_pow' else 1.0
        if c['skill'] == 'spfa_stall': mult *= srv.SPFA_DAMAGE_MULT
        elif c['skill'] == 'expectation': mult *= srv.EXPECT_MULT
        eff_atk = c['attack'] * mult
        interval = c['baseInterval']
        long_interval = interval + (srv.SPFA_STALL_CHANCE * srv.SPFA_STALL_EXTRA if cid == 'spfa' else 0)
        speed_rating = min(1.0, 1 / long_interval) if long_interval else 0
        j = JUDGE[cid]
        r = {
            'hp': min(1.0, eff_hp / hp_cap),
            'st': min(1.0, eff_atk / atk_cap),
            'aoe': j['aoe'],
            'spd': speed_rating,
            'skill': j['skill'],
            'role': role_rating(c, eff_hp),
        }
        # 花费：按「每回合恢复多少」折算成占用了几个回合的产出
        cost = (c['cost'] / GOLD_PER_ROUND + c['energy'] / ENERGY_PER_ROUND
                + c['reason'] / REASON_PER_ROUND)
        rows.append({
            'id': cid, 'name': c['name'], 'cost': c['cost'], 'difficulty': c['difficulty'],
            'attack': c['attack'], 'hp': c['hp'], 'eff_atk': round(eff_atk, 3), 'eff_hp': int(eff_hp),
            'range': c['range'], 'active': c['active'], 'energy': c['energy'], 'reason': c['reason'],
            'skill': c['skill'], 'desc': c['desc'], 'why': j['why'],
            'role_name': c['role'], 'position': c['position'], 'tip': c['tip'], 'base_interval': interval, 'long_interval': long_interval,
            'r': r, 'raw': sum(Wt[k] * r[k] for k in Wt), 'cost_units': cost,
        })

    raw_max = max(x['raw'] for x in rows)
    for x in rows:
        x['power'] = 1000.0 * (x['raw'] / raw_max)
        x['contrib'] = {k: 1000.0 * Wt[k] * x['r'][k] / raw_max for k in Wt}
        x['eff'] = x['power'] / x['cost_units']

    effs = [x['eff'] for x in rows]
    mean_eff = sum(effs) / len(effs)
    for x in rows:
        x['value'] = max(0.0, min(10.0, 6.0 * x['eff'] / mean_eff))

    # 同费相对性价比（这一档里比平均划算多少）
    for cost in sorted({x['cost'] for x in rows}):
        tier = [x for x in rows if x['cost'] == cost]
        m = sum(x['eff'] for x in tier) / len(tier)
        for x in tier:
            x['value_vs_tier'] = x['eff'] / m - 1.0

    rows.sort(key=lambda x: -x['power'])
    for i, x in enumerate(rows, 1):
        x['rank'] = i

    # 实测校验
    measured = {}
    fp = os.path.join(ROOT, 'balance', 'final.json')
    if os.path.exists(fp):
        for it in json.load(open(fp, encoding='utf-8')):
            card = next((c for c in srv.CARDS if c['id'] == it['id']), None)
            if card and it.get('attack') == card['attack'] and it.get('hp') == card['hp']:
                measured[it['id']] = it
    return rows, measured


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


# ============================================================
# 输出
# ============================================================
def load_mixed():
    fp = os.path.join(ROOT, 'balance', 'mixed_map.json')
    data = json.load(open(fp, encoding='utf-8')) if os.path.exists(fp) else {}
    cards = {c['name']: c for c in load_server().CARDS}
    return {name: r for name, r in data.items() if name in cards and r.get('atk') == cards[name]['attack'] and r.get('hp') == cards[name]['hp']}


def write_csv(rows, path):
    _, measured = score_all(W_B)
    mixed = load_mixed()
    diverse_path = os.path.join(ROOT, 'balance', 'diverse_map.json')
    diverse = json.load(open(diverse_path, encoding='utf-8')) if os.path.exists(diverse_path) else {}
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['排名', '卡牌', 'ID', '费用', '攻击', '生命', '有效攻击', '有效生命', '射程',
                    '主动', '精力', '理智', '技能', '战力分',
                    '血量分', '单体分', '群体分', '攻速分', '特性分', '定位分',
                    '综合花费', '性价比', '同费相对', '实测纯卡净胜血量', '实测纯卡同费差(百分点)', '实测混编净胜血量', '实测混编同费差(百分点)', '定位', '推荐站位', '基础普攻间隔秒', '长期期望普攻间隔秒', '纯卡胜场积分率', '参考混编胜场积分率', '多样混编净胜血量', '多样混编胜场积分率'])
        for x in rows:
            c = x['contrib']
            w.writerow([x['rank'], x['name'], x['id'], x['cost'], x['attack'], x['hp'],
                        x['eff_atk'], x['eff_hp'], x['range'], '是' if x['active'] else '否',
                        x['energy'], x['reason'], x['skill'], round(x['power']),
                        round(c['hp']), round(c['st']), round(c['aoe']), round(c['spd']),
                        round(c['skill']), round(c['role']),
                        round(x['cost_units'], 3), round(x['value'], 2),
                        round(x['value_vs_tier'] * 100, 1),
                        measured.get(x['id'], {}).get('margin', ''),
                        round(measured[x['id']]['rel'] * 100, 2) if x['id'] in measured else '',
                        mixed.get(x['name'], {}).get('value', ''),
                        round(mixed[x['name']]['rel'] * 100, 2) if x['name'] in mixed else '',
                        x['role_name'], x['position'], round(x['base_interval'],6), round(x['long_interval'],6),
                        measured.get(x['id'],{}).get('win_score',''), mixed.get(x['name'],{}).get('win_score',''),
                        diverse.get(x['name'],{}).get('value',''), diverse.get(x['name'],{}).get('win_score','')])


HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OI-chess 卡牌战力评分</title>
<style>
:root{--bg:#fff;--fg:#000;--muted:#7a7a7a;--soft:#ececec;--line:#000;
 --hot:#c0392b;--good:#2e7d4f;--warn:#b8781f;--panel:#fafafa;}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'SF Mono',Menlo,Consolas,'Microsoft YaHei',monospace;background:var(--bg);color:var(--fg);
 font-size:13px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:30px;font-weight:200;letter-spacing:6px}
h2{font-size:15px;font-weight:700;letter-spacing:3px;margin:44px 0 14px;padding-bottom:8px;
 border-bottom:1px solid var(--line)}
h3{font-size:13px;font-weight:700;letter-spacing:1px;margin:18px 0 8px}
.sub{color:var(--muted);font-size:12px;letter-spacing:2px;margin-top:8px}
p{color:#333;margin-bottom:8px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:24px}
.kpi{border:1px solid var(--line);padding:14px 16px}
.kpi .k{font-size:10px;letter-spacing:2px;color:var(--muted)}
.kpi .v{font-size:24px;font-weight:200;letter-spacing:1px;margin-top:4px;font-variant-numeric:tabular-nums}
.kpi .n{font-size:10px;color:var(--muted);margin-top:2px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th{font-size:10px;letter-spacing:1px;color:var(--muted);font-weight:400;text-align:right;
 padding:6px 6px;border-bottom:1px solid var(--line);white-space:nowrap;cursor:pointer;user-select:none}
th:hover{color:var(--fg)}
th.l,td.l{text-align:left}
td{padding:7px 6px;border-bottom:1px solid var(--soft);text-align:right;white-space:nowrap}
tr:hover td{background:var(--panel)}
.name{font-weight:700;letter-spacing:.5px}
.cost{display:inline-block;min-width:16px;padding:0 4px;border:1px solid var(--line);font-size:10px;
 text-align:center;margin-right:6px}
.bar{position:relative;height:6px;background:var(--soft);width:100%;min-width:54px}
.bar i{position:absolute;left:0;top:0;bottom:0;background:var(--fg);display:block}
.bar.g i{background:var(--good)}
.bar.w i{background:var(--warn)}
.bar.r i{background:var(--hot)}
.cellbar{display:flex;align-items:center;gap:6px;justify-content:flex-end}
.cellbar .bar{width:52px;min-width:52px}
.dimhead{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:10px}
.dimhead div{border:1px solid var(--line);padding:10px 12px}
.dimhead .t{font-weight:700;letter-spacing:1px}
.dimhead .w{color:var(--muted);font-size:10px;letter-spacing:1px;margin-top:2px}
.dimhead .d{font-size:10.5px;color:#555;margin-top:6px;line-height:1.5}
.pos{color:var(--good)}.neg{color:var(--hot)}
.note{border-left:2px solid var(--line);padding:2px 0 2px 14px;color:#444;font-size:12px;margin:10px 0}
.tools{display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
.tools input{border:1px solid var(--line);padding:6px 10px;font-family:inherit;font-size:12px;outline:none;width:160px}
.tools input:focus{background:var(--panel)}
.chip{border:1px solid var(--line);padding:5px 10px;font-size:11px;letter-spacing:1px;cursor:pointer;background:var(--bg)}
.chip.on{background:var(--fg);color:var(--bg)}
.tablewrap{overflow-x:auto;border-top:2px solid var(--line)}
.foot{margin-top:50px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:11px;line-height:1.8}
code{background:var(--soft);padding:1px 5px;font-size:11px}
.wtoggle{display:inline-flex;border:1px solid var(--line);margin-left:8px;vertical-align:middle}
.wtoggle button{border:0;background:var(--bg);color:var(--fg);font-family:inherit;font-size:11px;
 letter-spacing:1px;padding:4px 12px;cursor:pointer}
.wtoggle button.on{background:var(--fg);color:var(--bg)}
@media(max-width:760px){.wrap{padding:24px 12px 60px}h1{font-size:22px;letter-spacing:3px}
 .dimhead{grid-template-columns:1fr 1fr}.hide-s{display:none}}
</style></head><body><div class="wrap">
"""


def _cls(v):
    return 'pos' if v > 3 else ('neg' if v < -3 else '')


def build_data(rows, measured, mixed):
    n_by_cost = {}
    for x in rows:
        n_by_cost[x['cost']] = n_by_cost.get(x['cost'], 0) + 1
    out = []
    for x in rows:
        c = x['contrib']
        m = measured.get(x['id'])
        mx = mixed.get(x['name'])
        out.append({
            'rank': x['rank'], 'name': x['name'], 'id': x['id'], 'cost': x['cost'],
            'atkraw': x['attack'], 'hpraw': x['hp'], 'effatk': x['eff_atk'], 'effhp': x['eff_hp'],
            'power': round(x['power'], 1),
            'hp': round(c['hp']), 'st': round(c['st']), 'aoe': round(c['aoe']),
            'spd': round(c['spd']), 'skill': round(c['skill']), 'role': round(c['role']),
            'costu': round(x['cost_units'], 2), 'value': round(x['value'], 1),
            'tier': round(x['value_vs_tier'] * 100, 1) if n_by_cost[x['cost']] > 1 else None,
            'mir': round(m['rel'] * 100, 1) if m else None,
            'mix': round(mx['rel'] * 100, 1) if mx else None,
            'desc': x['desc'], 'why': x['why'],
        })
    return out


def write_html(rows, rows_a, measured, mixed, path):
    import html
    def read_json(name, default):
        fp = os.path.join(ROOT, name)
        return json.load(open(fp, encoding='utf-8')) if os.path.exists(fp) else default
    diverse = read_json('balance/diverse_map.json', {})
    meta = read_json('audit/final/meta.json', {})
    out_data = []
    for r in rows:
        x = dict(r)
        x['pure'] = measured.get(r['id'])
        x['mixed'] = mixed.get(r['name'])
        x['diverse'] = diverse.get(r['name'])
        x['power_a'] = next(a['power'] for a in rows_a if a['id'] == r['id'])
        out_data.append(x)
    data = json.dumps(out_data, ensure_ascii=False).replace('</', '<' + chr(92) + '/')
    weights = ' / '.join(W_NAME[k]+' '+str(round(W_B[k]*100))+'%' for k in W_B)
    total = meta.get('total', 0)
    nchecks = read_json('tests/mechanics_audit_results.json', {}).get('passed', 165)
    page = HTML_HEAD + f"""
<h1>OI-chess · 实战与定位</h1>
<div class="sub">35 张卡 · 精确事件计时 · 战力 /1000 · 性价比 /10 · 终版实战 {total:,} 场</div>
<div class="kpis"><div class="kpi"><div class="k">机制合同</div><div class="v">{nchecks} 项</div><div class="n">覆盖全部 35 张卡</div></div><div class="kpi"><div class="k">理论时序</div><div class="v">18 组</div><div class="n">攻击时间与次数逐次校验</div></div><div class="kpi"><div class="k">O2 当前值</div><div class="v">280 HP</div><div class="n">3 金 / 周围八格攻速 ×2</div></div></div>
<h2>口径与权重</h2><p>{weights}</p>
<div class="note">战力与性价比是带权模型估计，不是战斗伤害或胜率的保证。普攻攻速维度改为实际理论频率；SPFA 长期期望间隔为 2/1.5 + 20%×4 ≈ 2.133333 秒，不卡时仍为 1.333333 秒。O2 的站位价值不能由纯卡赛代表。</div>
<p>统一伤害：基础攻击 × 入场倍率 × 技能倍率 × 1/3 × 心态输出倍率 × 承伤倍率，向下取整（最小 1）；随后处理减免、分担与护盾。无法攻击的 O2 不触发最小伤害。生命有各自上限，过量伤害不计为实际损血。</p>
<p>综合花费 = 金币/20 + 精力/25 + 理智/16；性价比同时包含金币与理智，不直接按金币除分。模型特性与群体覆盖为规则评级，实际收益以对应阵容实测为准。</p>
<h2>全卡强度与定位</h2><div class="tools"><input id="q" placeholder="搜索名称 / 定位" oninput="draw()" aria-label="搜索卡牌"><select id="tier" onchange="draw()" style="padding:6px"><option value="0">全部费用</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select><select id="order" onchange="draw()" style="padding:6px"><option value="power">模型战力</option><option value="mix">参考混编</option><option value="div">多样混编</option><option value="value">性价比</option></select></div>
<div class="tablewrap"><table><thead><tr><th class="l">卡牌 / 定位</th><th>费</th><th>攻 / 战内血</th><th>战力</th><th>性价比</th><th>纯卡积分率</th><th>参考混编 ΔHP</th><th>多样混编 ΔHP</th></tr></thead><tbody id="cardRows"></tbody></table></div>
<div class="note">点击卡牌可展开机制、六维贡献、站位建议及三个场景的实际胜场积分率。ΔHP 是各自剩余生命比例之差，不是胜率。胜场积分率按游戏规则「幸存棋子数量更多者胜」，胜=1、平=0.5、负=0。</div>
<h2>实战方法</h2><p>纯卡：5 张同卡对战其余 34 种卡，每种对手 {meta.get('trials',32)} 场，交替先后手。参考混编：4 张模运算 + 被测卡，对 5 张模运算，每卡 {meta.get('mixed_trials',200)} 场。多样混编：gcd / 模运算 / BFS / 单调队列 + 被测卡，对相同四张 + 同费参考卡。参考卡为 1费贪心、2费模运算、3费期望、4费遗传、5费矩阵快速幂。</p>
<p>随机站位、回合 2–9、心态 100、每队精力 40；随机种子 {meta.get('seed',20261117)}。阵容不同意味着这不是全局天梯胜率，也不代表所有站位。单次混编均值的不确定性约为 ±1.96×标准误；小差距不做强弱定论。</p>
<h2>辅助与特殊场景</h2><p>O2 保留 280 血，必须比较覆盖与占位代价；BFS 的全场减速、异或的高攻反制、归并排序的生命调配也不能靠全同卡赛定论。参见《完整检查与平衡报告.md》中的 O2 定向对照与永久成长说明。</p>
<div class="foot">来源：server.py（当前规则与卡面） / audit/final（终版实战） / tests/test_mechanics_audit.py（机制合同）。旧版历史结果已归档，不作为本表当前结果。模型不声称精确预测多目标技能与站位辅助的实战伤害。</div>
<script>const DATA=__DATA__;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const pct=x=>x==null?'—':(x*100).toFixed(1)+'%';
const num=x=>x==null?'—':(x>=0?'+':'')+x.toFixed(3);
function draw(){{const q=document.getElementById('q').value.trim(),tier=+document.getElementById('tier').value,k=document.getElementById('order').value;
const rs=DATA.filter(x=>(!tier||x.cost===tier)&&(!q||(x.name+x.role_name+x.position).includes(q))).sort((a,b)=>k==='mix'?(b.mixed?.value??-9)-(a.mixed?.value??-9):k==='div'?(b.diverse?.value??-9)-(a.diverse?.value??-9):b[k]-a[k]);
document.getElementById('cardRows').innerHTML=rs.map(x=>`<tr><td class="l"><details><summary><b>${{esc(x.name)}}</b><br><small>${{esc(x.role_name)}} · ${{esc(x.position)}}</small></summary><div style="white-space:normal;max-width:350px;padding:10px 0"><p>${{esc(x.desc)}}</p><p>${{esc(x.tip)}}</p><p>基础间隔：${{x.base_interval?x.base_interval.toFixed(6)+' 秒':'不攻击'}}；精力 ${{x.energy}} / 理智 ${{x.reason}}</p><p>六维贡献：${{Object.entries(x.contrib).map(([k,v])=>({{hp:'血',st:'单',aoe:'群',spd:'速',skill:'特',role:'位'}}[k])+Math.round(v)).join(' / ')}}</p><p>实际胜场积分率：纯卡 ${{pct(x.pure?.win_score)}} / 参考混编 ${{pct(x.mixed?.win_score)}} / 多样混编 ${{pct(x.diverse?.win_score)}}</p><p>混编近似95%区间：${{x.mixed?num(x.mixed.value-1.96*x.mixed.se)+' 至 '+num(x.mixed.value+1.96*x.mixed.se):'未测试'}}</p></div></details></td><td>${{x.cost}}</td><td>${{x.attack}} / ${{x.eff_hp}}</td><td><b>${{Math.round(x.power)}}</b><div class="bar"><i style="width:${{x.power/10}}%"></i></div></td><td>${{x.value.toFixed(1)}}</td><td>${{pct(x.pure?.win_score)}}</td><td>${{num(x.mixed?.value)}}</td><td>${{num(x.diverse?.value)}}</td></tr>`).join('');}}
draw();</script></div></body></html>
"""
    page = page.replace('__DATA__', data)
    open(path, 'w', encoding='utf-8').write(page)
    xs = [x for x in rows if x['id'] in measured]
    rho = spearman([x['power'] for x in xs], [measured[x['id']]['margin'] for x in xs])
    def corr(rs):
        ys = [x for x in rs if x['id'] in measured]
        return spearman([x['power'] for x in ys], [measured[x['id']]['margin'] for x in ys])
    def tier_corr(rs):
        ys = [x for x in rs if x['id'] in measured]
        return spearman([x['value_vs_tier'] for x in ys], [measured[x['id']]['rel'] for x in ys])
    return rho, tier_corr(rows), corr(rows_a), tier_corr(rows_a)


def main():
    rows, measured = score_all(W_B)
    rows_a, _ = score_all(W_A)
    mixed = load_mixed()
    h = os.path.join(ROOT, '卡牌战力评分.html')
    c = os.path.join(ROOT, '卡牌战力评分.csv')
    write_csv(rows, c)
    r1, r2, r1a, r2a = write_html(rows, rows_a, measured, mixed, h)

    ra = {x['id']: x['rank'] for x in rows_a}
    print(f"{'#':>3} {'卡牌':12}{'费':>2} {'战力':>5} {'A排名':>5}{'变化':>5} "
          f"{'血':>4}{'单':>4}{'群':>4}{'速':>4}{'技':>4}{'位':>4} {'花费':>5} {'性价比':>5}")
    for x in rows:
        c6 = x['contrib']
        d = x['rank'] - ra[x['id']]
        print(f"{x['rank']:>3} {x['name']:12}{x['cost']:>2} {x['power']:>5.0f} {ra[x['id']]:>5}"
              f"{(('%+d' % d) if d else '·'):>5} "
              f"{c6['hp']:>4.0f}{c6['st']:>4.0f}{c6['aoe']:>4.0f}"
              f"{c6['spd']:>4.0f}{c6['skill']:>4.0f}{c6['role']:>4.0f} "
              f"{x['cost_units']:>5.2f} {x['value']:>5.1f}")
    print(f"\n方案A 全池 {r1a:.3f} / 同费 {r2a:.3f}")
    print(f"方案B 全池 {r1:.3f} / 同费 {r2:.3f}")
    print('写出', os.path.basename(h), '与', os.path.basename(c))


if __name__ == '__main__':
    main()
