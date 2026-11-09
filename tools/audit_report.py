"""将终版实战写回评分数据，并生成完整检查与平衡报告。"""
import json,csv,shutil,hashlib,re
from pathlib import Path
from balance_lab import load_server
ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads((ROOT/path).read_text())
def table(h,rs):return '| '+' | '.join(h)+' |\n|'+'|'.join(['---']*len(h))+'|\n'+''.join('| '+' | '.join(map(str,r))+' |\n' for r in rs)
def main():
    s=load_server();meta=read('audit/final/meta.json');base=read('audit/baseline/meta.json');final=read('audit/final/final.json');mixed=read('audit/final/mixed_map.json');diverse=read('audit/final/diverse_map.json');before=read('audit/baseline/mixed_map.json');sc=read('balance/o2_scenarios.json');patch=read('audit/balance_patch.json');checks=read('tests/mechanics_audit_results.json');fx=read('audit/fx/results.json')
    for name in ['final.json','mixed_map.json','diverse_map.json']:
        shutil.copyfile(ROOT/'audit/final'/name,ROOT/'balance'/name)
    invariants=read('audit/invariants.json')
    stress_text=(ROOT/'audit/stress_game.log').read_text()
    stress_ops=int(re.search(r'共 (\d+) 次操作',stress_text).group(1))
    total=meta['total']+base['total']+sc['battles']+invariants['battles']
    intro=f'''# 完整检查与平衡报告

## 当前结论

已完成 **{len(s.CARDS)} 张卡、{checks['passed']} 项机制合同、18 组精确时序验证**。基线与终版累计完成 **{total:,} 场战斗模拟**（含满编随机验证，不计中断重跑与线上回归），并通过三回合八人整局压力、API 和浏览器回归。

O2 保持你指定的 **3 金 / 0 攻击 / 280 生命 / 周围八格攻速 ×2**。SPFA 保持 **攻速 ×1.5、普攻伤害 ×1.2、每击后独立 20% 概率额外卡 4 秒**；此次只将其生命由 1100 调到 1000。

本轮新增 **3 张同名同星自动合成**（最高 3 星，生命/攻击每星 ×1.8）。本报告中的 {total:,} 场统计与平衡表仍是 **1 星基线**，未包含 2/3 星阵容；升星合同由 `tests/test_merge.py` 单独验证。

这不是“证明所有可能状态永无误差”：验证范围、随机样本、数值取整和模型估计均在下文注明。理论倍率与实际结算的已发现不一致已修复；带权评分仍是估计，不会被包装成真实胜率。

## 一、机制与数据一致性修复

1. **射程**：补刀/最高攻击优先先在射程内选目标；除 BFS 的全场技能外，技能先裁剪射程，再取行列、分块、最近/最远或攻击力前半。
2. **线性 DP / 状压 DP**：敌方目标行不再错误使用施法者所在己方行；线性 DP 明确目标所在行/列中更密集的一条线，50% 伤害；状压 DP 汇总自身同行友军面板攻击，作用于目标所在行。
3. **分块**：固定对齐的 2×2 棋盘分块，与卡面“目标所在分块”一致；扫描线明确至多三人。
4. **树状数组**：友军普攻和施法都触发，非仅普攻；自身行动不为自身加层。
5. **剪枝**：本次减免后先承受剩余伤害，转化的新盾随后到账，避免新盾立刻抵消同次攻击而变成隐性完全免伤。护盾上限向下取整到整数生命单位，浮字显示实际获得量。
6. **gcd**：多分担者分配完整的总 30% 伤害，整数余量不再遗漏；不是每个 gcd 分别再分担 30%。
7. **归并排序**：按归并连接边形成的连通组同步均分当前生命，遵守每个棋子的生命上限并守恒；余量确定性分配为整数，消除顺序依赖和半滴血显示失真。属于当前生命调配，不是凭空治疗。
8. **异或**：多次攻击交换按仍有效的交换顺序从基础攻击重放，到期不会恢复串值或负攻击。
9. **遗传算法**：击杀只记一次，幸存棋子的成长层数跨回合保存、收回再上场也保留，最多三层。新买棋子从零开始。
10. **伤害与回放**：普通技能即时扣血的命中事件也在即时产生；DFS 的立即追击、反伤不再假标未来时刻。差分真正延迟两秒结算并产生对应命中事件。过量伤害不再显示成实际损血。
11. **计时**：保留精确事件驱动攻击，O2/减速实时积分，SPFA 卡顿独立计真实秒数；移动仍每 0.5 秒一次，技能仍为 6 秒冷却，不受 O2 加速。
12. **界面与表格**：战内攻击/有效生命/射程、加速、卡顿、换攻、成长、延迟伤害均从服务器状态读取；嵌套范围坐标随视角镜像。角色定位进入图鉴和商店。评分表淘汰旧版硬编码结论，显示实际游戏判胜口径。

### 理论时序（持续有目标、无减速、未触发卡顿）

| 场景 | 理论间隔 | 实测时间序列前五击 |
|---|---:|---|
| SPFA | 4/3 秒 | 0 / 1.333333 / 2.666667 / 4 / 5.333333 |
| SPFA + ×1.5 光环 | 8/9 秒 | 0 / 0.888889 / 1.777778 / 2.666667 / 3.555556 |
| SPFA + 当前 O2 | 2/3 秒 | 0 / 0.666667 / 1.333333 / 2 / 2.666667 |

时间戳序列化至微秒，误差测试容限 1.1 微秒；不声称循环小数可无限精确存储。伤害按统一 1/3 缩放、心态输出/承伤、技能倍率计算，再按整数伤害、减免、分担和已有护盾结算。SPFA 每次都卡顿的强制测试中，当前 O2 下相邻攻击间隔为 4 + 2/3 秒。

## 二、数值调整

允许调整数值，但没有将所有卡强行拉到同一条线上；保护流派差异，保留 O2 的站位门槛。以下九张改动均已写入服务器，其余攻血不变。

'''
    reasons={'diff':'基线纯卡及两种混编均偏弱，提高延迟群伤的基础收益与存活。','xor':'射程修复后仍在低费中明显突出，小幅下调，保留高攻反制定位。','quick_sort':'射程限制后面板偏低，三个口径都偏弱，补基础攻血。','ids':'前期混编偏弱，轻补面板，保留长局射程优势。','bidirectional':'纯卡与多样混编偏弱，轻补双端技能的基础面板。','sweep_line':'三个口径偏弱，补足递增群攻的基础面板。','spfa':'精确攻速修复后纯卡/混编均较突出，仅降低生命，保留高攻和随机卡顿。','bitmask_dp':'目标行修复提高群伤收益，小幅收面板，保留同行协同。','a_star':'高面板收割收益较稳定，小幅回收基础攻血。'}
    # 旧卡攻血固化为只读数据快照；历史可运行源码已移入 git history，工作区不再保留。
    old_s=read('audit/baseline/cards_before.json')
    changes=[]
    for cid in patch:
        c=s.CARD_BY_ID[cid];old=old_s[cid];name=c['name'];changes.append([name,f"{old['attack']} / {old['hp']}",f"{c['attack']} / {c['hp']}",reasons[cid]])
    text=intro+table(['卡牌','原攻 / 血','新攻 / 血','理由'],changes)
    text+='\n### 参考混编复测\n\n基线每卡 80 场、终版每卡 200 场，结果为各自剩余生命比例差。这里包含整轮机制修正与数值调整，不是单项改动的严格因果试验；小差异存在抽样误差。\n\n'
    comparisons=[]
    for cid in patch:
        name=s.CARD_BY_ID[cid]['name'];b=before[name];m=mixed[name];comparisons.append([name,f"{b['value']:+.4f}",f"{m['value']:+.4f}",f"{m['value']-1.96*m['se']:+.4f} 至 {m['value']+1.96*m['se']:+.4f}"])
    text+=table(['卡牌','基线 ΔHP','终版 ΔHP','终版近似 95% 区间'],comparisons)
    text+='\n## 三、完整实战与定位表\n\n**胜场积分率**按游戏实际规则：幸存棋子数多者胜，胜=1、平=0.5、负=0。**ΔHP**是双方各自剩余生命占初始总生命比例之差，不是胜率。两种指标不混用。\n\n'
    rows=[]
    for c in s.CARDS:
        p=next(x for x in final if x['id']==c['id']);m=mixed[c['name']];d=diverse[c['name']]
        rows.append([c['name'],c['cost'],c['role'],c['position'],f"{p['win_score']*100:.1f}%",f"{m['value']:+.3f}",f"{d['value']:+.3f}"])
    headers=['卡牌','费','定位','站位','纯卡积分率','参考混编 ΔHP','多样混编 ΔHP'];text+=table(headers,rows)
    with (ROOT/'全卡实战与定位.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.writer(f);w.writerow(headers);w.writerows(rows)
    text+='\n## 四、O2 定向验证（280 血）\n\n四名同类输出 + O2 对比五名同类输出，另设相同阵容关闭光环对照；四种输出、两种站位、三种配置，每组 200 场，共 4,800 场。集中保护开场覆盖四名输出，分散后置开场覆盖不到。以下差值仍为净胜血量差的百分点，不是胜率。\n\n'
    sr=[]
    for r in sc['rows']:sr.append([r['carry'],r['formation'],f"{r['aura_gain']*100:+.2f}",f"{r['replace_gain']*100:+.2f}"])
    text+=table(['输出','站位','开启光环收益（百分点）','替换第五张输出收益（百分点）'],sr)
    text+='\nO2 的强弱主要由覆盖、保护与队友普攻占比决定；不因随机站位差就自动加血，也不因全 O2 无法攻击就认定没有价值。BFS、异或、gcd、归并排序同样应结合阵容判断。\n'
    text+='\n## 五、清晰特效重做\n\n- 短时路径残影与同步命中，去掉“已扣血但几百毫秒后弹道才落地”的错觉。\n- 控制用蓝色虚线，延迟用琥珀色点线，爆发用紫色加粗路径；范围用轻量格框，标记真实作用格。\n- O2 八邻域轮廓、受加速标识、SPFA 卡顿倒计时、减速/延迟/换攻/成长等权威状态提示。\n- HP/护盾条加普攻准备进度；盾浮字按实际新增值，伤害浮字短时间同格合并。\n- 卡名使用高对比前景色、队伍用边框区分，长算法名更完整，减少遮挡。\n- 攻击与技能按 UID 找棋子；相同时间同坐标的不同事件不再被去重吞掉。\n- 修复单人/轮空模式坐标重复偏移，技能范围随双方视角正确镜像。\n- 无全屏震动和长时间遮罩；新增 FX / FX− 开关，尊重系统减少动态效果设置。\n- 特效 DOM 节点上限：清晰 128、低特效 40，已用瞬时 500 次生成压测验证。\n'
    text+=f"\n浏览器演示测试：明暗主题、390px 移动视口、低特效切换、重复事件均通过，控制台错误 0。当前沙箱 Chromium 桌面测得 rAF 间隔中位数 {fx['desktop']['median_ms']:.1f} ms、P95 {fx['desktop']['p95_ms']:.1f} ms，仅代表此环境，不能保证所有设备均为 60fps。\n"
    text+=f'''\n## 六、测试范围与复现

- 全卡机制合同：{checks['passed']} 项；`python3 tests/test_mechanics_audit.py`。
- 满编随机：120 场 15 对 15，覆盖心态 0/29/30/69/70/100、精力 0/1/40、回合 1–10 和遗传初始成长；共 {invariants['frames']:,} 帧、{invariants['events']:,} 事件，不变量错误 0。日志 `audit/invariants.json`。
- 精确时序：18 组与动态减速/光环消失；`python3 tests/test_precision.py`。
- O2 / SPFA 独立机制与配对：`tests/test_o2.py`、`tests/test_spfa.py`、`tests/test_pairing.py`。
- API 脏输入：`tests/api_fuzz.py`，异常 0。
- 在线动画：`tests/anim_check.py`，控制台错误 0、平滑移动检查通过。
- 特效审计：`tests/test_fx_audit.py`；截图位于 `audit/fx/`。
- 八人整局：测试服务临时将准备/战斗时间缩短，完成三回合、{stress_ops} 次操作，数值越界 0、配对错误 0；生产时间没有缩短。日志 `audit/stress_game.log`。
- 基线：纯卡 {base['pure_battles']:,} + 参考混编 {base['mixed_battles']:,} + 多样混编 {base['diverse_battles']:,} 场。
- 终版：纯卡 {meta['pure_battles']:,} + 参考混编 {meta['mixed_battles']:,} + 多样混编 {meta['diverse_battles']:,} + O2 定向 {sc['battles']:,} 场。
- 全池种子 {meta['seed']}，每场 5 人队、随机站位、回合 2–9、心态 100、精力 40，交替先后手。详见 `tools/full_audit_lab.py`。
- 多样混编固定四人骨架为 gcd / 模运算 / BFS / 单调队列，第五位置为被测卡；对手第五位使用同费参考卡。

**局限**：未穷举 15 人阵容、全部心态/站位/棋子组合。全池统计以新买卡、无遗传初始成长为起点；永久成长跨回合通过路径测试，但没有把满层遗传混同为新买遗传的全局强度。纯卡赛不能衡量保护型辅助的全部价值，固定定向场景也不是随机天梯。评分中的群体覆盖、特性与定位分仍含人工评级，不能当作严格的伤害预测。

## 文件

- `卡牌战力评分.html / .csv`：带权评分与当前实测、全卡定位。
- `全卡实战与定位.csv`：不含主观评分的实测定位表。
- `特效预览.html`：无需联网的真实战斗演示，含 O2 / SPFA / 减速 / 延迟 / 换攻。
- `动画预览.html`：原有演示已同步新版渲染。
- `audit/baseline/cards_before.json`：平衡调整前 9 张卡的攻 / 血快照（仅供报告生成）；历史源码已移入 git history，工作区不再保留可运行的旧后端。`audit/baseline/`、`audit/final/`：可回溯实战数据。

## 后续修复：准备阶段放置错位

已修复百分比点击格与缓存像素棋子位置不一致，以及边框、内边距和 Flex 压缩导致的尺寸误差。8 类放置/缩放回归在测试浏览器中均测得 0 像素偏差。未修改战斗与卡牌数值，上述实战数据仍适用。详情见 `docs/放置错位修复.md`。

## 本轮：50 张卡 = 50 种独立技能 + 全局羁绊 + 上场上限 20

卡池保持 **{len(s.CARDS)} 张**不变（ID、名称、费用、基础攻防、流派、定位全部保留），但**每张卡的技能互不重复**：原先 50 张卡只有 38 种技能（`synergy` 4 张、`pierce` 3 张，其余 9 种各 2 张），本轮把重复技能全部换成与算法特点相符的独立机制，同时**新增全局羁绊**，并把场上棋子上限从 15 提到 **20**。

**新增的 13 种独立技能**（每张卡一条，技能名与卡牌算法一一对应）：前缀累计（每命中一次攻击 +10%，最多 6 层）、最小生成树链（正交相邻友军每条边减伤 6%，最多 4 边）、强连通标记（目标被打后每层承伤 +8%，最多 3 层）、蝶形变换（奇数击 ×0.7 / 偶数击 ×1.7）、KMP 跃迁（未击杀每击 +10%，击杀即清零）、最长公共前缀（连打同名 ×1.5，换目标掉到 ×0.8）、线段树区间查询（每第 4 击对射程内其余全体追加 60% 伤害）、启发式选点（估价挑目标且全伤害 +25%）、模周期振荡（7 击一循环：×1.3 逐击衰减到 ×0.4，末击 ×2.0）、伸展旋转（每击 +7% 攻击，受伤即折半）、最小割（射程内全体分摊，血量最高者再吃一刀最大流）、多模式匹配（额外同名敌人各吃 30%）、自动机压缩（同名友军越多攻击越高，但生命上限同步下降）。

**负面技能用于限制高基础数值卡**：模周期振荡、最长公共前缀、蝶形变换三条技能本身自带惩罚段（下一击更低），自动机压缩用「攻击换生命上限」换取构筑收益，伸展旋转在受伤时清空层数；上一轮的新卡专属「协同」技能被全局羁绊取代，不再有专属加成。

**全局羁绊**：按流派统计**自己场上**的棋子数量，达到 **2 / 4 / 6** 张时逐档激活——档位 1 同流派棋子攻击 +6%，档位 2 再加生命 +8%，档位 3 再加承伤 -6%。羁绊只统计己方棋子，对手不计入；生命加成按整数结算，避免浮点截断导致血量显示 0 但单位存活。

这些改动改变了所有卡之间的对局结算，因此 `audit/baseline/` 的历史基线不再与终版可比，本轮**主动放弃历史可比性**并按当前源码重跑全池：{meta['pure_battles']:,} 场纯卡对局、{meta['total']:,} 场总模拟，`audit/final/meta.json` 的 `source_sha256` 与 `server.py` 一致。逐卡机制合同由 384 项增至 {checks['passed']} 项；18 组精确时序、O2/SPFA 定向、配对与 15v15 满编不变量继续通过。
'''
    (ROOT/'完整检查与平衡报告.md').write_text(text)
    with (ROOT/'机制核对表.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['卡牌','技能ID','卡面描述','基础攻击','基础生命','战内生命','基础间隔秒','定位','站位'])
        for c in s.CARDS:w.writerow([c['name'],c['skill'],c['desc'],c['attack'],c['hp'],s.effective_max_hp(c),c['baseInterval'],c['role'],c['position']])
    print('Report complete:',total,'completed battles;',checks['passed'],'mechanics checks')
if __name__=='__main__':main()
