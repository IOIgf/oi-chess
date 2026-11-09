# -*- coding: utf-8 -*-
import http.server, socketserver, json, threading, uuid, random, socket, sys, time, math, os, argparse
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

HOST = '0.0.0.0'
PORT = 8080
STATIC_DIR = (Path(__file__).parent / 'static').resolve()
DATA_DIR = (Path(__file__).parent / 'data').resolve()
DATA_FILE = DATA_DIR / 'players.json'

MAX_PLAYERS = 8
MAX_BENCH = 10             # 备战席上限
MAX_BOARD = 20             # 场上棋子上限
HALF_W, HALF_H = 8, 4
BATTLE_W, BATTLE_H = 8, 8
BATTLE_TIME = 30.0
MAX_ROUNDS = 10
TICK_SEC = 0.5

# ---- 掉线 / 回收参数 -------------------------------------------------------
PLAYER_TIMEOUT = 120.0     # 超过该时长无心跳视为掉线
ROOM_TTL_ENDED = 60.0    # 已结束房间保留时长（秒）
CLEANUP_INTERVAL = 5.0    # 心跳清理周期（秒）

ATK_CD = 2.0
ATK_CD_SLOWED = 3.0
SLOW_DURATION = 3.0        # 减速持续时间（旧版是整场永久，等价于永久削弱敌方 33% 输出）
SKILL_CD = 6.0
DMG_MULT = 0.5 * 2.0 / 3.0

# ---- 心态：决定伤害输出与承伤 ----------------------------------------------
MIND_HIGH = 70
MIND_LOW = 30
MIND_DMG_UP = 1.10
MIND_DMG_DOWN = 0.50
MIND_DMG_TAKEN = 1.10
MIND_MAX = 100

REASON_CRASH_MIND = 8

SHIELD_CAP_RATIO = 0.5
AOE_DEBUFF_RATIO = 0.35     # BFS：全场伤害倍率（减速效果见 _use_skill）
SHIELD_ON_LOW_ATK = 0.5    # 剪枝：单次伤害低于自身攻击力的这个比例才触发
SHIELD_ON_LOW_CONVERT = 0.5  # 触发时把伤害的这个比例转化为护盾（其余仍然承受）
THORNS_RATIO = 0.35
LINK_SHARE = 0.30
CHARGE_STEPS = 4
CHARGE_MULT = 3.0
EVERY_N_STEPS = 3
EVERY_N_MULT = 2.5
STACK_ALLY_STEP = 0.08
STACK_ALLY_CAP = 6
GENETIC_STEP = 0.15
GENETIC_CAP = 3
MATRIX_STEP = 1.1
MATRIX_CAP = 2
CDQ_SWITCH = 10.0
CDQ_EARLY = 0.6
CDQ_LATE = 1.8
PRIME_MULT = 1.8
EXPECT_MULT = 1.25
SWAP_DURATION = 6.0
# SPFA：攻速、伤害倍率；每次普攻后独立判定卡顿。
SPFA_SPEED_MULT = 1.5
SPFA_DAMAGE_MULT = 1.2
SPFA_STALL_CHANCE = 0.20
SPFA_STALL_EXTRA = 4.0
O2_SPEED_MULT = 2.0

# ---- New mechanics: pierce / splash / lifesteal / rampage / synergy / freeze ----
PIERCE_RATIO = 0.50        # Extra damage to the enemy directly behind the target.
SPLASH_RATIO = 0.35        # Extra damage to each orthogonally adjacent enemy.
LIFESTEAL_RATIO = 0.30     # Fraction of dealt damage returned as HP.
RAMPAGE_MULT = 1.6         # Attack multiplier while below the HP threshold.
RAMPAGE_HP = 0.5           # Trigger when current HP / max HP is below this.
SYNERGY_STEP = 0.12        # Attack gained per same-trait ally at spawn.
SYNERGY_CAP = 4            # Maximum synergy stacks.
FREEZE_RATIO = 0.40        # Damage ratio of the freeze active skill.
FREEZE_STALL = 2.0         # Seconds of attack stall applied by freeze.
SHOP_PITY_MULT = 4         # Shop weight multiplier for cards one copy from merging.

# ---- Global bonds: 2/4/6 units of one trait unlock one tier each -----------
BOND_TIERS = (2, 4, 6)
BOND_ATK_STEP = 0.06       # tier 1: +6% attack for units of that trait
BOND_HP_STEP = 0.08        # tier 2: +8% max HP
BOND_GUARD_STEP = 0.06     # tier 3: -6% damage taken
BOND_EFFECTS = ['攻击 +6%', '生命 +8%', '承伤 -6%']  # exposed to the client

# ---- Unique skills: one distinct skill id per card -------------------------
PREFIX_GROWTH_STEP = 0.10
PREFIX_GROWTH_CAP = 6
MST_GUARD_STEP = 0.06
MST_GUARD_CAP = 4
SCC_MARK_STEP = 0.08
SCC_MARK_CAP = 3
FFT_ODD_MULT = 0.75
FFT_EVEN_MULT = 1.70
KMP_NEXT_STEP = 0.10
KMP_NEXT_CAP = 5
LCP_SAME_MULT = 1.50
LCP_OTHER_MULT = 0.80
SEG_QUERY_STEPS = 4
SEG_QUERY_RATIO = 0.60
HEURISTIC_MULT = 1.25
MOD_CYCLE = 7
MOD_CYCLE_START = 1.30
MOD_CYCLE_STEP = 0.10
MOD_CYCLE_BURST = 2.00
SPLAY_STEP = 0.07
SPLAY_CAP = 6
MIN_CUT_RATIO = 0.35
MIN_CUT_BOSS_RATIO = 0.60
MIN_CUT_SPREAD = 0.15
MIN_CUT_BOSS_SPREAD = 0.18
MULTI_MATCH_RATIO = 0.30
SAM_ATK_STEP = 0.15
SAM_HP_STEP = 0.08
SAM_CAP = 5

EMPTY_PENALTY_INTERVAL = 2.0
ENERGY_PER_ROUND = 25
SKILL_ENERGY_COST = 1
REASON_PER_ROUND = 16
MIND_WIN = 5
MIND_LOSE = 8

CARDS_RAW = [
    ('linear_dp', '线性 DP', 1, '普及', 0.75, 'dynamic_programming', 41, 401, 4, 4, 'line',
     '沿行/列直线攻击',
     '技能：对射程内目标所在行或列中敌人更多的一条线造成 50% 伤害'),
    ('tree_array', '树状数组', 1, '普及', 0.75, 'data_structure', 37, 364, 4, 4, 'stack_ally',
     '友军行动叠层',
     '被动：每次友军普攻或施法 +1 层，每层 +8% 普攻伤害（上限 6 层）'),
    ('monotonic_stack', '单调栈', 1, '普及', 0.75, 'data_structure', 38, 371, 4, 4, 'charge_burst',
     '积累后爆发',
     '被动：每第 4 次普攻造成 3 倍伤害'),
    ('greedy', '贪心', 1, '普及', 0.75, 'greedy', 46, 456, 4, 4, 'finish_weak',
     '打最易击杀目标',
     '被动：优先攻击射程内生命最低的敌人'),
    ('sort', '排序', 1, '普及', 0.75, 'greedy', 40, 404, 4, 4, 'sort_line',
     '重排一行或一列',
     '技能：打乱射程内同一行敌人的站位，并造成 30% 伤害'),
    ('dfs', 'DFS', 1, '普及', 0.75, 'search', 44, 438, 4, 4, 'chain_kill',
     '一路深入，击杀续行',
     '被动：击杀后立刻追加一次攻击，本场最多追加 3 次'),
    ('diff', '差分', 1, '普及', 0.75, 'diff', 35, 335, 4, 4, 'delayed_line',
     '延迟整行伤害',
     '技能：给射程内整行敌人挂延迟伤害，2 秒后结算 150%'),
    ('xor', '异或', 1, '普及', 0.75, 'bitwise', 28, 280, 4, 4, 'swap_stats',
     '交换敌人属性',
     '技能：与射程内攻击最高的敌人交换攻击力，持续 6 秒'),
    ('gcd', 'gcd', 1, '普及', 0.75, 'number_theory', 44, 437, 4, 4, 'link_ally',
     '链接相邻友军',
     '被动：相邻友军受伤时，自身分担 30%'),
    ('bfs', 'BFS', 2, '普及', 0.75, 'search', 50, 500, 6, 9, 'aoe_debuff',
     '全场扩散，限时减速',
     '技能：全场敌人受 35% 伤害并减速 3 秒（普攻准备速度降为 2/3）'),
    ('pigeonhole', '鸽巢原理', 2, '普及', 0.75, 'combinatorics', 75, 727, 6, 9, 'crowd_crit',
     '密集必暴击',
     '被动：目标周围 3\xd73 内除目标外敌人 ≥3 时，本次伤害翻倍'),
    ('prime_sieve', '质数筛', 2, '普及', 0.75, 'math', 64, 636, 6, 9, 'prime_round',
     '质数回合爆发',
     '被动：质数回合伤害 \xd71.8'),
    ('mod_op', '模运算', 2, '普及', 0.75, 'math', 62, 619, 6, 9, 'every_n',
     '每第N次攻击触发',
     '被动：每第 3 次普攻造成 2.5 倍伤害'),
    ('shift', '移位', 2, '普及', 0.75, 'bitwise', 76, 754, 6, 9, 'shift_stats',
     '攻击翻倍生命减半',
     '被动：入场攻击 \xd72、生命上限 \xd70.5'),
    ('range_dp', '区间 DP', 2, '提高', 1.05, 'dynamic_programming', 66, 647, 6, 9, 'range_aoe',
     '连续区间伤害',
     '技能：对目标及其左右相邻格造成 80% 伤害'),
    ('segment_tree', '线段树', 2, '提高', 1.05, 'data_structure', 64, 632, 6, 9, 'seg_query',
     '区间查询，懒标记下放',
     '被动：每第 4 次普攻额外对射程内全体敌人造成 60% 伤害'),
    ('sqrt_block', '分块', 2, '提高', 1.05, 'data_structure', 67, 655, 6, 9, 'block_aoe',
     '2\xd72 块控制',
     '技能：对射程内目标所在的固定 2\xd72 棋盘分块造成 70% 伤害'),
    ('pruning', '剪枝', 2, '提高', 1.05, 'search', 55, 539, 6, 9, 'shield_on_low',
     '弱攻击转护盾',
     '被动：单次伤害低于自身攻击力 50% 时，减免 50% 并转化为护盾'),
    ('ids', '迭代加深', 2, '提高', 1.05, 'search', 76, 750, 6, 9, 'grow_range',
     '范围逐回合+1',
     '被动：第 1 回合使用基础射程，此后每回合射程 +1'),
    ('merge_sort', '归并排序', 2, '提高', 1.05, 'divide_conquer', 74, 739, 6, 9, 'merge_ally',
     '合并相邻属性',
     '被动：入场时与上下左右相邻友军连成的分组均分当前生命，不超各自上限'),
    ('quick_sort', '快速排序', 2, '提高', 1.05, 'divide_conquer', 60, 590, 6, 9, 'partition',
     '按攻击分区',
     '技能：对射程内攻击力最高的一半敌人造成 100% 伤害'),
    ('divide', '分治', 2, '提高', 1.05, 'divide_conquer', 57, 558, 6, 9, 'divide_conquer',
     '分段处理再合并',
     '技能：射程内全体受 50% 伤害，若无人阵亡再补一次 100%'),
    ('inverse', '逆元', 2, '提高', 1.05, 'number_theory', 63, 626, 6, 9, 'thorns',
     '受击反伤',
     '被动：受到普攻时反弹 35% 伤害'),
    ('bitmask_dp', '状压 DP', 3, '提高', 1.05, 'dynamic_programming', 79, 800, 9, 16, 'compress_line',
     '压缩整行友军',
     '技能：汇总自身与同行友军攻击力，对射程内目标所在行敌人造成等值伤害'),
    ('monotonic_queue', '单调队列', 3, '提高', 1.05, 'data_structure', 111, 1115, 9, 16, 'sliding_max',
     '滑窗攻击最强者',
     '被动：优先攻击射程内攻击力最高的敌人'),
    ('a_star', 'A*', 3, '提高', 1.05, 'search', 110, 1100, 9, 16, 'heuristic',
     '启发式估价 f=g+h',
     '被动：按「距离 + 剩余生命/攻击」选估价最低的目标，对其伤害 ×1.25'),
    ('bidirectional', '双向搜索', 3, '提高', 1.05, 'search', 86, 840, 9, 16, 'pincer',
     '两端夹击',
     '技能：对射程内最近与最远的敌人各造成 120% 伤害'),
    ('fermat', '费马小定理', 3, '提高', 1.05, 'number_theory', 96, 954, 9, 16, 'mod_cycle',
     '模幂周期，归零爆发',
     '被动：7 击为一个模周期，倍率由 1.3 逐击降到 0.8，第 7 击 ×2.0'),
    ('expectation', '期望', 3, '提高', 1.05, 'probability', 98, 970, 9, 16, 'expectation',
     '随机转固定',
     '被动：普攻伤害恒定 \xd71.25'),
    ('sweep_line', '扫描线', 3, '提高', 1.05, 'geometry', 94, 920, 9, 16, 'sweep',
     '线上递增伤害',
     '技能：射程内目标同行至多 3 名敌人按距离由近到远，受 60%/90%/120% 伤害'),
    ('cdq', 'CDQ 分治', 3, '省选', 1.25, 'divide_conquer', 96, 961, 9, 16, 'cdq',
     '前弱后爆',
     '被动：战斗前 10 秒伤害 \xd70.6，之后 \xd71.8'),
    ('spfa', 'SPFA', 3, '提高', 1.05, 'search', 120, 1000, 9, 16, 'spfa_stall',
     '平时跑得飞快，遇到数据就卡了',
     '被动：攻速 \xd71.5，普攻伤害 \xd71.2；每次普攻后有 20% 概率「卡了」，下一次普攻额外延迟 4 秒'),
    ('o2', 'O2 优化', 3, '提高', 1.05, 'optimization', 0, 280, 9, 16, 'o2_aura',
     '自己不跑，让队友跑得更快',
     '被动：无法攻击，原地为周围八格友军提供攻速 \xd72；同名光环不叠加，离开范围或自身阵亡后失效'),
    ('genetic', '遗传算法', 4, '省选', 1.25, 'search', 152, 1510, 13, 25, 'genetic',
     '继承并变异',
     '被动：每次击杀永久 +15% 攻击（最多 3 层）'),
    ('matrix_pow', '矩阵快速幂', 5, '省选', 1.25, 'math', 155, 1545, 15, 31, 'matrix_pow',
     '攻击\xd71.5，生命-10%',
     '被动：入场攻击 \xd71.5、生命上限 \xd70.9；每 6 秒攻击 \xd71.2（最多 3 层）'),
    ('two_pointers', '双指针', 1, '普通', 0.75, 'greedy', 42, 410, 4, 4, 'pierce',
     '贯穿一线',
     '被动：普攻命中后，对目标正后方同列相邻的敌人追加 50% 伤害'),
    ('prefix_sum', '前缀和', 1, '普通', 0.75, 'diff', 39, 392, 4, 4, 'prefix_growth',
     '前缀累加，越战越强',
     '被动：每次普攻使伤害 +10%（最多 6 层），同一场战斗持续累积'),
    ('huffman', '哈夫曼编码', 1, '普通', 0.75, 'greedy', 40, 400, 4, 4, 'lifesteal',
     '带权路径回血',
     '被动：普攻造成伤害后，回复该次实际伤害 30% 的生命（不超过上限）'),
    ('topo_sort', '拓扑排序', 2, '普通', 0.75, 'graph_theory', 58, 575, 6, 9, 'freeze',
     '冻结依赖环',
     '技能：射程内全体敌人受 40% 伤害并停攻 2 秒'),
    ('kmp', 'KMP', 2, '提高', 1.05, 'string', 66, 650, 6, 9, 'kmp_next',
     '失配不回退，next 表跳转',
     '被动：未击杀目标时下次伤害 +10%（最多 5 层），击杀后清零重来'),
    ('prim', '最小生成树', 2, '提高', 1.05, 'graph_theory', 63, 628, 6, 9, 'mst_link',
     '连边成网，共担冲击',
     '被动：入场时每有一名正交相邻友军，减伤 6%（最多 4 边 / 24%）'),
    ('flood_fill', '泛洪填充', 2, '提高', 1.05, 'search', 62, 615, 6, 9, 'splash',
     '四邻扩散',
     '被动：普攻时，对目标上下左右相邻的敌人各造成 35% 伤害'),
    ('ac_automaton', 'AC 自动机', 3, '提高', 1.05, 'string', 92, 905, 9, 16, 'multi_match',
     'fail 链，一次扫描多命中',
     '被动：普攻后对射程内所有同名敌人各追加 30% 伤害'),
    ('tarjan', '强连通分量', 3, '提高', 1.05, 'graph_theory', 95, 940, 9, 16, 'scc_mark',
     '环内互相标记',
     '被动：普攻给目标叠加 1 层标记，每层使其承受伤害 +8%（最多 3 层）'),
    ('minimax', '极小化极大', 3, '提高', 1.05, 'game_theory', 105, 1030, 9, 16, 'rampage',
     '劣势时搏到底',
     '被动：自身生命低于上限 50% 时，攻击 \xd71.6'),
    ('suffix_array', '后缀数组', 3, '提高', 1.05, 'string', 99, 980, 9, 16, 'lcp_chain',
     '最长公共前缀',
     '被动：连续攻击同名敌人时伤害 ×1.5，切换目标时 ×0.8'),
    ('splay', '伸展树', 4, '省选', 1.25, 'data_structure', 148, 1480, 13, 25, 'splay_rotate',
     '访问即旋根，摊还代价',
     '被动：每次普攻 +7% 伤害（最多 6 层），但每次受伤损失一半层数'),
    ('network_flow', '网络流', 4, '省选', 1.25, 'graph_theory', 150, 1495, 13, 25, 'min_cut',
     '最小割，容量瓶颈',
     '技能：射程内全体受 35% 伤害（敌人越多单体越低），血量最高者额外 60%'),
    ('fft', '快速傅里叶变换', 5, '省选', 1.25, 'math', 153, 1530, 15, 31, 'fft_butterfly',
     '蝶形运算，奇偶相抵',
     '被动：奇数次普攻 ×0.75、偶数次 ×1.7；高面板的代价是输出极不稳定'),
    ('suffix_automaton', '后缀自动机', 5, '省选', 1.25, 'string', 156, 1550, 15, 31, 'sam_compress',
     '状态压缩，以血换攻',
     '被动：每名同名友军使攻击 +15%（含自己）；合并状态会挤占生命上限 -8%（独苗不扣，最多 5 层）'),
]

RANGE_BY_COST = {1: 4, 2: 4, 3: 5, 4: 6, 5: 8}

ACTIVE_SKILLS = frozenset({
    'line', 'multi', 'aoe', 'aoe_debuff', 'block_aoe', 'range_aoe',
    'delayed_line', 'swap_stats', 'sort_line', 'compress_line',
    'pincer', 'partition', 'divide_conquer', 'sweep', 'freeze', 'min_cut',
})

# 商店刷新：每轮第一次免费，第二次起按基础价格递增。
SHOP_FREE_REFRESHES = 1
SHOP_REFRESH_BASE = 2
SHOP_REFRESH_STEP = 1

CARDS = [{
    'id': c[0], 'name': c[1], 'cost': c[2], 'difficulty': c[3], 'coef': c[4],
    'trait': c[5], 'attack': c[6], 'hp': c[7], 'energy': c[8], 'reason': c[9],
    'skill': c[10], 'flavor': c[11], 'desc': c[12],
    'range': RANGE_BY_COST.get(c[2], 4),
    'active': c[10] in ACTIVE_SKILLS,
    'skillCost': SKILL_ENERGY_COST if c[10] in ACTIVE_SKILLS else 0,
} for c in CARDS_RAW]
CARD_ROLES = {'linear_dp': ('线性群攻', '中排', '让目标行或列聚集，技能按射程筛选。'), 'tree_array': ('团队成长', '中后排', '友军每次普攻或施法加层，适合行动密集的阵容。'), 'monotonic_stack': ('周期爆发', '中排', '每四击爆发，避免输出位过早阵亡。'), 'greedy': ('低费收割', '中排', '优先射程内残血，不会为远处残血放弃当前目标。'), 'sort': ('重排控场', '中排', '扰乱射程内同行站位，伤害不是主要价值。'), 'dfs': ('连锁收割', '中排', '击杀后立即续攻，本场最多追加三次。'), 'diff': ('延时群攻', '后排', '伤害在标记两秒后结算，保护施法者争取多次标记。'), 'xor': ('高攻反制', '保护位', '交换射程内最高攻击，适合针对高费核心。'), 'gcd': ('分担坦辅', '前中排', '上下左右接住队友的伤害，分担总量为30%，非每个gcd各30%。'), 'bfs': ('全场减速', '保护位', '全场伤害并限时降低普攻准备速度，不降低技能频率。'), 'pigeonhole': ('密集克制', '中排', '敌方围绕目标密集时触发翻倍，分散敌人收益低。'), 'prime_sieve': ('回合爆发', '中排', '第2、3、5、7回合普攻增强，非质数回合保持基础输出。'), 'mod_op': ('稳定周期输出', '中排', '每三击2.5倍，适合稳定站场。'), 'shift': ('玻璃大炮', '后排', '战内攻击翻倍、生命减半，避免直接承伤。'), 'range_dp': ('局部群攻', '中后排', '打目标及左右相邻格，克制横向密集阵。'), 'segment_tree': ('蓄力爆发', '中排', '线段树把区间修改攒成懒标记再一次性下放，每四拍清一次全场。'), 'sqrt_block': ('分块群攻', '中后排', '固定棋盘2\xd72分块，不是以目标为左上角任意取块。'), 'pruning': ('碎伤防御', '前排', '只针对低于自身攻击50%的单次伤害，重击仍危险。'), 'ids': ('长局远程', '后排', '第一回合基础射程，随回合逐步增加。'), 'merge_sort': ('生命调配', '邻接保护位', '开战时为连通组均分当前生命；不是凭空治疗。'), 'quick_sort': ('高攻点群伤', '中后排', '射程内按当前攻击排序，优先打输出位。'), 'divide': ('条件群爆', '中后排', '第一段未击杀任何目标才有补刀段。'), 'inverse': ('普攻反制', '前排', '按实际损失生命反弹，不反弹被护盾吸收的部分。'), 'bitmask_dp': ('同行协同炮', '同行保护位', '同行高攻击队友增强技能，需兼顾射程与站位。'), 'monotonic_queue': ('高攻压制', '中排', '优先攻击射程内最高攻击者，可能放过残血。'), 'a_star': ('高费收割', '中后排', 'A* 用 f=g+h 挑最有希望的节点，优先打近且快死的目标，并自带 25% 增伤。'), 'bidirectional': ('双端打击', '中后排', '射程内最近与最远各一击，只有一名敌人时不重复。'), 'fermat': ('回合爆发', '中后排', '模幂按周期回绕，前半周期占优、后半周期疲软，最后一击归零时爆发。'), 'expectation': ('稳定单体', '中后排', '恒定普攻倍率，适合需要稳定输出的阵容。'), 'sweep_line': ('同行递增群攻', '中后排', '目标同行至多三人，由近到远递增。'), 'cdq': ('后程核心', '保护后排', '前10秒偏弱，此后爆发，必须保护到后半场。'), 'spfa': ('随机停顿输出', '保护中后排', '攻速快、攻击高，但每次普攻后20%概率额外卡4秒。'), 'o2': ('站位攻速核心', '邻接保护位', '0攻击、280血；覆盖多人再投入，分散或主动技能阵容不宜盲带。'), 'genetic': ('永久成长核心', '保护中后排', '击杀叠层最多三层，幸存棋子的层数跨回合保留。'), 'matrix_pow': ('高费时间核心', '后排', '入场攻高血减，6/12秒逐步成长。')}
CARD_ROLES.update({
    'two_pointers': ('穿透补刀', '中排', '沿敌人纵列站位，普攻能顺带打到目标身后的敌人。'),
    'prefix_sum': ('同流派成长', '中后排', '前缀和把历史累加成表，越打到后面单次伤害越高，适合持久战而非速攻。'),
    'huffman': ('续航输出', '中排', '普攻按实际伤害回血，适合持久战而非爆发。'),
    'topo_sort': ('全场停滞', '后排', '射程内全体停攻 2 秒，为友军争取出手窗口。'),
    'kmp': ('穿透点杀', '中排', 'KMP 失配时不回退主串而是查 next 表，连续啃同一个目标越啃越快。'),
    'prim': ('连边协同', '中后排', '最小生成树用最少的边连通全场，贴着队友站能把伤害分摊出去。'),
    'flood_fill': ('四邻溅射', '中排', '敌方密集站位时，一次普攻能溅到多个相邻目标。'),
    'ac_automaton': ('多点溅射', '中后排', 'AC 自动机沿 fail 链一次扫描命中所有模式，对面同类越多收益越高。'),
    'tarjan': ('同环共振', '中后排', '强连通分量靠 lowlink 标记互相可达的节点，被标记的目标会越来越脆。'),
    'minimax': ('残血翻盘', '前中排', '生命跌破一半后攻击 \xd71.6，适合顶在前排换血。'),
    'suffix_array': ('纵列穿透', '中后排', '后缀数组靠 LCP 衡量相邻后缀的相似度，只打同一类目标才有高收益。'),
    'splay': ('高续航前排', '前排', '伸展树每次访问都把节点旋到根，越打越顺；一旦被集火，旋转层数立刻折半。'),
    'network_flow': ('全场阻塞', '后排', '最大流受限于最小割，流量被多条边分摊，优先割断容量最大的那一路。'),
    'fft': ('同频协同', '后排', '蝶形运算把时域拆成奇偶两路再合并，第一拍弱、第二拍强，均值略高于普通卡。'),
    'suffix_automaton': ('绝境收割', '前中排', '后缀自动机用最少状态存下所有子串，代价是极低的有效生命：堆同名越多越脆。'),
})

for _card in CARDS:
    _card['role'], _card['position'], _card['tip'] = CARD_ROLES[_card['id']]
    _card['baseInterval'] = 0 if _card['id'] == 'o2' else ATK_CD / (SPFA_SPEED_MULT if _card['id'] == 'spfa' else 1.0)

CARD_BY_ID = {c['id']: c for c in CARDS}
SHOP_MIN_COST = min(c['cost'] for c in CARDS)
SHOP_MAX_COST = max(c['cost'] for c in CARDS)
SHOP_WEIGHT_BASE = 2       # lower cost cards stay more common at every level


def _fill_card_max_hp():
    """把有效生命上限（移位 \xd70.5 / 矩阵快速幂 \xd70.9）写进卡表，供前端显示。"""
    for c in CARDS:
        c['maxHp'] = effective_max_hp(c)

TRAITS = {
    'dynamic_programming': '动态规划', 'data_structure': '数据结构',
    'greedy': '贪心/排序', 'search': '搜索', 'divide_conquer': '分治',
    'diff': '差分', 'bitwise': '位运算', 'number_theory': '数论',
    'combinatorics': '组合数学', 'probability': '概率期望',
    'geometry': '计算几何', 'math': '数学', 'optimization': '优化',
    'graph_theory': '图论', 'string': '字符串', 'game_theory': '博弈',
}



def bond_tier(count):
    tier = 0
    for need in BOND_TIERS:
        if count >= need:
            tier += 1
    return tier


def bond_status(cards):
    # Trait counts for one player's board, with active tiers.
    counts = {}
    for c in cards:
        t = c['trait']
        counts[t] = counts.get(t, 0) + 1
    rows = []
    for trait, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        tier = bond_tier(count)
        rows.append({
            'trait': trait, 'name': TRAITS.get(trait, trait),
            'count': count, 'tier': tier,
            'next': BOND_TIERS[tier] if tier < len(BOND_TIERS) else None,
            'effects': list(BOND_EFFECTS[:tier]),
        })
    return rows

DATA_LOCK = threading.RLock()
PROFILES = {}
DEFAULT_RATING = 1000
RATING_LOSE = -20
RATING_QUIT = -30

# ---- AI 对战 ---------------------------------------------------------------
# AI 玩家的 clientId 一律以 'ai:' 开头：真人不会生成这种 id，因而档案写入、
# 心跳清理和房间回收都能用同一个前缀判断，无需在玩家 dict 之外再维护索引。
AI_CID_PREFIX = 'ai:'
AI_LEVELS = ('easy', 'normal', 'hard')
AI_LEVEL_LABELS = {'easy': '简单', 'normal': '普通', 'hard': '困难'}
AI_NAMES = ('电脑·贪心', '电脑·动态规划', '电脑·最短路', '电脑·并查集',
            '电脑·二分', '电脑·搜索', '电脑·图论', '电脑·数论')
# 难度只影响「准备期怎么花钱、铺多少人」，不触碰战斗数值与随机数顺序：
#   refreshes   每回合最多主动刷新商店的次数
#   board_target 期望上阵棋子数（不超过 MAX_BOARD）
#   max_cost    愿意购买的最高费用卡
#   trait_bias  同流派羁绊在选卡评分里的权重
AI_TUNING = {
    'easy':   {'refreshes': 0, 'board_target': 10, 'max_cost': 2, 'trait_bias': 0.0},
    'normal': {'refreshes': 1, 'board_target': 16, 'max_cost': 4, 'trait_bias': 6.0},
    'hard':   {'refreshes': 3, 'board_target': 20, 'max_cost': 5, 'trait_bias': 14.0},
}


def _as_str(v, limit=None, default=''):
    """只接受字符串，防止 {'text': {}} 这类脏输入把处理线程打崩。"""
    if not isinstance(v, str):
        return default
    v = v.strip()
    return v[:limit] if limit is not None else v


def _as_int(v, default=None):
    """只接受整数（bool 不算），非法返回 default。"""
    if isinstance(v, bool) or not isinstance(v, int):
        return default
    return v


def is_prime(n):
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True


def level_for_round(rnd):
    return max(1, min(10, 1 + (max(1, rnd) - 1) // 2))


def shop_refresh_cost(refreshes):
    """本轮第 n 次刷新的金币价格：首次免费，之后从基础价逐次 +1。"""
    n = max(0, int(refreshes or 0))
    if n < SHOP_FREE_REFRESHES:
        return 0
    return SHOP_REFRESH_BASE + (n - SHOP_FREE_REFRESHES) * SHOP_REFRESH_STEP


def board_power(board):
    """存活棋子的等级格子之和：每个存活棋子占 1 格，等级即星级。"""
    total = 0
    for info in board.values():
        try:
            hp = float(info.get('hp', 0) or 0)
        except (TypeError, ValueError):
            hp = 0.0
        if hp > 0:
            total += unit_star(info)
    return total


def effective_max_hp(card):
    m = float(card['hp'])
    if card['skill'] == 'shift_stats':
        m *= 0.5
    elif card['skill'] == 'matrix_pow':
        m *= 0.9
    return int(m)


# ---- star-up / merge -------------------------------------------------------
STAR_SCALE = 1.8
MAX_STAR = 3
MERGE_COPIES = 3


def clamp_star(star):
    try:
        star = int(star)
    except (TypeError, ValueError):
        return 1
    return max(1, min(MAX_STAR, star))


def unit_star(info):
    """Star level of a stored unit; legacy/tool-built units default to 1."""
    return clamp_star(info.get('star', 1))


def star_max_hp(card, star):
    return int(effective_max_hp(card) * (STAR_SCALE ** (clamp_star(star) - 1)))


def star_attack(card, star):
    return float(card['attack']) * (STAR_SCALE ** (clamp_star(star) - 1))


def sell_value(card, star):
    """TFT-style refund: 1-star cost, 2-star 3*cost-1, 3-star 9*cost-1."""
    star = clamp_star(star)
    return max(1, card['cost'] * (3 ** (star - 1)) - (0 if star == 1 else 1))


_fill_card_max_hp()


# ============================================================
# 档案与 Rating
# ============================================================
def load_profiles():
    global PROFILES
    DATA_DIR.mkdir(exist_ok=True)
    if DATA_FILE.exists():
        try:
            PROFILES = json.loads(DATA_FILE.read_text('utf-8'))
        except Exception:
            PROFILES = {}
    else:
        PROFILES = {}


def save_profiles():
    with DATA_LOCK:
        try:
            DATA_DIR.mkdir(exist_ok=True)
            tmp = DATA_FILE.with_name(DATA_FILE.name + '.tmp')
            tmp.write_text(json.dumps(PROFILES, ensure_ascii=False, indent=2), 'utf-8')
            tmp.replace(DATA_FILE)
        except Exception:
            pass


def get_profile(cid, name=None):
    # AI 是房间内的一次性虚拟玩家，不落盘、不占玩家档案。
    if str(cid).startswith(AI_CID_PREFIX):
        return {'clientId': cid, 'name': name or '电脑', 'rating': DEFAULT_RATING,
                'wins': 0, 'losses': 0, 'games': 0}
    with DATA_LOCK:
        if cid not in PROFILES:
            PROFILES[cid] = {'clientId': cid, 'name': name or '选手',
                             'rating': DEFAULT_RATING, 'wins': 0, 'losses': 0, 'games': 0}
            save_profiles()
        elif name and PROFILES[cid].get('name') != name:
            PROFILES[cid]['name'] = name
            save_profiles()
        return dict(PROFILES[cid])


def update_rating(cid, delta, result=None, name=None):
    # 淘汰 / 结算 / 中途退出都会走到这里；AI 不参与 Rating 统计。
    if str(cid).startswith(AI_CID_PREFIX):
        return {}
    with DATA_LOCK:
        if cid not in PROFILES:
            PROFILES[cid] = {'clientId': cid, 'name': name or '选手',
                             'rating': DEFAULT_RATING, 'wins': 0, 'losses': 0, 'games': 0}
        if name:
            PROFILES[cid]['name'] = name
        PROFILES[cid]['rating'] = max(0, PROFILES[cid]['rating'] + delta)
        PROFILES[cid]['games'] = PROFILES[cid].get('games', 0) + 1
        if result == 'win':
            PROFILES[cid]['wins'] = PROFILES[cid].get('wins', 0) + 1
        elif result == 'lose':
            PROFILES[cid]['losses'] = PROFILES[cid].get('losses', 0) + 1
        save_profiles()
        return dict(PROFILES[cid])


ROOMS = {}
ROOMS_LOCK = threading.RLock()


def make_card_obj(card_id):
    card = CARD_BY_ID[card_id]
    return {'card': card_id, 'hp': effective_max_hp(card), 'star': 1}


def new_player(pid, name, is_ai=False, ai_level='normal'):
    p = {
        'id': pid, 'name': name,
        'hp': 100, 'gold': 10, 'level': 1,
        'mind': 100, 'reason': 100, 'energy': 100,
        'board': {}, 'bench': [], 'shop': [], 'shopRefreshes': 0,
        'ready': False, 'lastResult': '', 'opponent': None,
        'dead': False, 'abandoned': False, 'rated': False, 'crashed': False,
        'roundWins': 0, 'roundLosses': 0,
        'last_seen': time.time(),
    }
    if is_ai:
        p['isAi'] = True
        p['aiLevel'] = ai_level if ai_level in AI_LEVELS else 'normal'
    return p


def is_ai_cid(cid):
    """统一判断：AI 前缀优先，同时兼容直接传入的玩家 dict 标记。"""
    return str(cid).startswith(AI_CID_PREFIX)


class Room:
    def __init__(self, rid, host_id):
        self.id = rid
        self.host = host_id
        self.players = {}
        self.colors = {}
        self.state = 'waiting'
        self.round = 0
        self.version = 0
        self.lock = threading.RLock()
        self.chat = []
        self.chat_version = 0
        self.pairings = []
        self.last_pair_ids = []
        self.prep_end = 0
        self.battle_end = 0
        self.battle_started_at = 0
        self.pairs_computed = False
        self.winner = None
        self._last_empty_check = 0
        self._bye_players = []
        self._bye_frames = {}
        self._tick_lock = threading.Lock()
        self._ended_at = None

    # ---- 颜色 --------------------------------------------------------------
    def _assign_color(self, cid):
        used = set(self.colors.values())
        for i in range(MAX_PLAYERS):
            if i not in used:
                self.colors[cid] = i
                return i
        self.colors[cid] = 0
        return 0

    # ---- 心跳 --------------------------------------------------------------
    def _touch(self, cid):
        p = self.players.get(cid)
        if p is not None:
            p['last_seen'] = time.time()

    # ---- 进出房间 ----------------------------------------------------------
    def add_player(self, cid, name):
        with self.lock:
            if cid in self.players:
                self._touch(cid)
                return True, 'rejoined'
            if len(self.players) >= MAX_PLAYERS:
                return False, '房间已满'
            if self.state != 'waiting':
                return False, '游戏已开始'
            self.players[cid] = new_player(cid, name)
            self._assign_color(cid)
            self.version += 1
            self._sys_chat(f'{name} 加入了房间')
            return True, 'joined'

    # ---- AI 对手 -----------------------------------------------------------
    def add_ai(self, ai_level='normal'):
        """往等待中的房间加入一名电脑对手，返回 (ok, cid | 错误)。"""
        with self.lock:
            if self.state != 'waiting':
                return False, '游戏已开始'
            if len(self.players) >= MAX_PLAYERS:
                return False, '房间已满'
            if not [p for p in self.players.values() if not p.get('isAi')]:
                return False, '至少要有 1 名真人玩家'
            level = ai_level if ai_level in AI_LEVELS else 'normal'
            n_ai = sum(1 for p in self.players.values() if p.get('isAi'))
            name = '%s·%s' % (AI_NAMES[n_ai % len(AI_NAMES)],
                              AI_LEVEL_LABELS[level])
            cid = AI_CID_PREFIX + uuid.uuid4().hex[:10]
            self.players[cid] = new_player(cid, name, is_ai=True, ai_level=level)
            self._assign_color(cid)
            self.version += 1
            self._sys_chat(f'{name} 加入房间（AI 对手）')
            return True, cid

    @staticmethod
    def _ai_traits(p):
        counts = {}
        for info in list(p['board'].values()) + list(p['bench']):
            c = CARD_BY_ID.get(info['card'])
            if c:
                counts[c['trait']] = counts.get(c['trait'], 0) + 1
        return counts

    @staticmethod
    def _ai_card_score(card, traits, tuning, rng):
        score = (card['cost'] * 9 + card['attack'] * 0.35
                 + card['hp'] * 0.04)
        score += tuning['trait_bias'] * traits.get(card['trait'], 0)
        return score + rng.random() * 8.0

    def _ai_rng(self, cid):
        """每位 AI 每回合一条独立确定性随机流，绝不推进全局 random。"""
        return random.Random(f'{cid}|{self.round}')

    def _ai_fill_board(self, cid, p, target):
        """把备战席上最肉的棋子依次摆到最靠前的空格。"""
        while p['bench'] and len(p['board']) < target:
            free = [(x, y) for x in range(HALF_W) for y in range(HALF_H)
                    if f'{x},{y}' not in p['board']]
            if not free:
                return
            idx = max(range(len(p['bench'])),
                      key=lambda i: CARD_BY_ID[p['bench'][i]['card']]['hp'])
            x, y = free[0]
            ok, _err = self.place(cid, idx, x, y)
            if not ok:
                return

    def _ai_buy_round(self, cid, p, tuning, rng, target, max_cost):
        """从当前商店按评分买若干张卡并立刻上阵，返回是否买到过。"""
        bought_any = False
        for _ in range(MAX_BOARD + MAX_BENCH):
            if len(p['board']) >= target or not p['shop']:
                break
            traits = self._ai_traits(p)
            choices = []
            for idx, card_id in enumerate(p['shop']):
                card = CARD_BY_ID.get(card_id)
                if not card or card['cost'] > max_cost or card['cost'] > p['gold']:
                    continue
                choices.append((self._ai_card_score(card, traits, tuning, rng), idx))
            if not choices:
                break
            choices.sort(reverse=True)
            bought = False
            for _score, idx in choices[:3]:
                ok, _err = self.buy(cid, idx)
                if ok:
                    bought = bought_any = True
                    break
            if not bought:
                break
            self._ai_fill_board(cid, p, target)
        return bought_any

    def _ai_prep(self):
        """每个准备期为所有 AI 自动买卡、布阵并点「准备」。

        只调用 buy / place / refresh_shop / toggle_ready 这些现成接口，
        不改 _simulate_battle；随机决策用独立 Random，不污染全局随机流。
        """
        ais = [(cid, p) for cid, p in self.players.items()
               if p.get('isAi') and not p.get('dead')]
        for cid, p in ais:
            tuning = AI_TUNING.get(p.get('aiLevel'), AI_TUNING['normal'])
            rng = self._ai_rng(cid)
            target = min(MAX_BOARD, int(tuning['board_target']))
            max_cost = min(int(tuning['max_cost']), SHOP_MAX_COST)

            self._ai_fill_board(cid, p, target)
            self._ai_buy_round(cid, p, tuning, rng, target, max_cost)
            for _ in range(int(tuning['refreshes'])):
                if len(p['board']) >= target:
                    break
                ok, _err = self.refresh_shop(cid, rng=rng)
                if not ok:
                    break
                self._ai_buy_round(cid, p, tuning, rng, target, max_cost)
            self.toggle_ready(cid)

    # ---- 聊天 --------------------------------------------------------------
    def _push_chat(self, msg):
        self.chat.append(msg)
        if len(self.chat) > 100:
            self.chat = self.chat[-100:]
        self.chat_version += 1

    def _sys_chat(self, text):
        self._push_chat({'id': uuid.uuid4().hex, 'sender': '', 'senderId': '',
                         'text': text, 'time': int(time.time() * 1000), 'system': True})

    def send_chat(self, pid, text):
        with self.lock:
            p = self.players.get(pid)
            if not p:
                return False, '玩家不存在'
            self._touch(pid)
            if not isinstance(text, str):
                return False, '消息格式错误'
            text = text.strip()[:200]
            if not text:
                return False, '消息为空'
            self._push_chat({'id': uuid.uuid4().hex, 'sender': p['name'], 'senderId': pid,
                             'text': text, 'time': int(time.time() * 1000), 'system': False})
            self.version += 1
            return True, None

    # ---- 商店 --------------------------------------------------------------
    def _shop_pool(self, level):
        """Unlock costs up to min(SHOP_MAX_COST, level); lower costs weigh more."""
        top = max(SHOP_MIN_COST, min(int(level or 1), SHOP_MAX_COST))
        ids, weights = [], []
        for c in CARDS:
            if c['cost'] <= top:
                ids.append(c['id'])
                weights.append(SHOP_WEIGHT_BASE ** (top - c['cost']))
        return ids, weights

    def _roll_shop(self, level, count=5, owner=None, rng=None):
        # Level drives the pool; a card one copy short of a merge is weighted
        # up so a larger card pool does not make 3-star upgrades unreachable.
        # rng 仅由 AI 决策传入（独立随机流）；默认仍走全局 random，
        # 真人商店与全池审计的随机顺序保持完全不变。
        ids, weights = self._shop_pool(level)
        if owner is not None:
            near = self._near_merge_ids(owner)
            if near:
                weights = [w * (SHOP_PITY_MULT if cid in near else 1)
                           for cid, w in zip(ids, weights)]
        return (rng or random).choices(ids, weights=weights, k=count)

    @staticmethod
    def _near_merge_ids(p):
        counts = {}
        for info in list(p['board'].values()) + list(p['bench']):
            key = (info['card'], unit_star(info))
            counts[key] = counts.get(key, 0) + 1
        return {cid for (cid, _), n in counts.items()
                if n >= MERGE_COPIES - 1}

    def _roll_all_shops(self):
        for p in self.players.values():
            if p.get('dead') or p.get('abandoned'):
                continue
            p['shop'] = self._roll_shop(p['level'], owner=p)

    # ---- 开局 --------------------------------------------------------------
    def start(self, pid):
        with self.lock:
            if pid != self.host:
                return False, '只有房主可以开始'
            if self.state != 'waiting':
                return False, '游戏已经开始'
            self._touch(pid)
            n = len([p for p in self.players.values() if not p.get('dead')])
            if n < 2:
                return False, '至少需要 2 名玩家'
            self.round = 1
            for p in self.players.values():
                p['level'] = level_for_round(self.round)
            self._roll_all_shops()
            self._start_prep(first=True)
            self._sys_chat(f'游戏开始，共 {n} 名玩家')
            self.version += 1
            return True, None

    def _purge_abandoned(self):
        gone = [cid for cid, p in self.players.items() if p.get('abandoned')]
        if not gone:
            return False
        for cid in gone:
            self.players.pop(cid, None)
            self.colors.pop(cid, None)
        self.pairings = [pr for pr in self.pairings
                         if pr['a'] in self.players and pr['b'] in self.players]
        self._bye_players = [cid for cid in self._bye_players if cid in self.players]
        return True

    def _start_prep(self, first=False):
        self._purge_abandoned()
        self.state = 'prep'
        # Prep has no countdown: the battle starts only after EVERY living
        # player toggles ready (see toggle_ready).
        self.prep_end = 0.0
        self.pairs_computed = False
        for p in self.players.values():
            if p.get('dead'):
                continue
            p['ready'] = False
            p['shopRefreshes'] = 0
            if not first:
                for store in (p['board'], p['bench']):
                    items = store.values() if isinstance(store, dict) else store
                    for info in items:
                        card = CARD_BY_ID[info['card']]
                        max_hp = star_max_hp(card, unit_star(info))
                        cur_hp = int(info.get('hp', max_hp))
                        info['hp'] = int(min(max_hp, cur_hp + (max_hp - cur_hp) * 0.7))
        # AI 在准备期一开始就完成布阵并点准备，真人仍需自己点「准备」。
        self._ai_prep()

    # ---- 准备期操作 --------------------------------------------------------
    def _prep_player(self, pid):
        p = self.players.get(pid)
        if not p:
            return None, '玩家不存在'
        if p.get('dead'):
            return None, '你已出局'
        if self.state != 'prep':
            return None, '当前不可操作'
        p['last_seen'] = time.time()
        return p, None

    def refresh_shop(self, pid, rng=None):
        with self.lock:
            p, err = self._prep_player(pid)
            if err:
                return False, err
            cost = shop_refresh_cost(p.get('shopRefreshes', 0))
            if p['gold'] < cost:
                return False, '金币不足'
            p['gold'] -= cost
            p['shopRefreshes'] = int(p.get('shopRefreshes', 0) or 0) + 1
            p['shop'] = self._roll_shop(p['level'], owner=p, rng=rng)
            self.version += 1
            return True, None

    # ---- star-up merge -----------------------------------------------------
    @staticmethod
    def _would_merge(p, cid, star):
        """True if one more copy of (cid, star) would form a triple."""
        n = 0
        for info in p['board'].values():
            if info['card'] == cid and unit_star(info) == star:
                n += 1
        for info in p['bench']:
            if info['card'] == cid and unit_star(info) == star:
                n += 1
        return n >= MERGE_COPIES - 1

    @staticmethod
    def _merge_groups(p):
        """Group owned units by (card, star); board order first, then bench order."""
        groups = {}
        for key, info in p['board'].items():
            groups.setdefault((info['card'], unit_star(info)), []).append(
                ('board', key, info))
        for idx, info in enumerate(p['bench']):
            groups.setdefault((info['card'], unit_star(info)), []).append(
                ('bench', idx, info))
        return groups

    def _try_merge(self, p):
        """Cascade every possible 3-of-a-kind merge. Caller bumps version."""
        notice = None
        while True:
            target = None
            for (cid, star), items in self._merge_groups(p).items():
                if star < MAX_STAR and len(items) >= MERGE_COPIES:
                    target = (cid, star, items[:MERGE_COPIES])
                    break
            if target is None:
                break

            cid, star, chosen = target
            # Keep a board copy if possible, otherwise the first bench copy.
            anchor = chosen[0]
            for item in chosen:
                if item[0] == 'board':
                    anchor = item
                    break

            # Remove the other two by object identity; bench indices may shift.
            for loc, key, info in chosen:
                if info is anchor[2]:
                    continue
                if loc == 'board':
                    if p['board'].get(key) is info:
                        p['board'].pop(key, None)
                else:
                    p['bench'][:] = [u for u in p['bench'] if u is not info]

            card = CARD_BY_ID[cid]
            new_star = star + 1
            anchor[2]['star'] = new_star
            anchor[2]['hp'] = star_max_hp(card, new_star)
            if card['skill'] == 'genetic':
                anchor[2]['kills'] = min(
                    GENETIC_CAP,
                    max(int(i[2].get('kills', 0) or 0) for i in chosen),
                )
            notice = {'id': uuid.uuid4().hex, 'card': cid, 'star': new_star}

        if notice is not None:
            p['mergeNotice'] = notice
        return notice

    def buy(self, pid, shop_index):
        with self.lock:
            p, err = self._prep_player(pid)
            if err:
                return False, err
            if not (0 <= shop_index < len(p['shop'])):
                return False, '无效位置'
            card = CARD_BY_ID[p['shop'][shop_index]]
            if p['gold'] < card['cost']:
                return False, '金币不足'
            if p['energy'] < card['energy']:
                return False, '精力不足'
            if p['reason'] < card['reason']:
                return False, '理智不足'
            if len(p['bench']) >= MAX_BENCH \
                    and not self._would_merge(p, card['id'], 1):
                return False, '备战席已满'
            p['gold'] -= card['cost']
            p['energy'] -= card['energy']
            p['reason'] -= card['reason']
            p['bench'].append(make_card_obj(card['id']))
            p['shop'].pop(shop_index)
            self._try_merge(p)
            if p['reason'] <= 0 and not p.get('crashed'):
                p['crashed'] = True
                self._sys_chat(f'{p["name"]} 理智耗尽，陷入崩溃：每回合额外 -{REASON_CRASH_MIND} 心态')
            self.version += 1
            return True, None

    def sell(self, pid, source, key_or_idx):
        with self.lock:
            p, err = self._prep_player(pid)
            if err:
                return False, err
            if source == 'bench':
                idx = key_or_idx
                if not isinstance(idx, int) or not (0 <= idx < len(p['bench'])):
                    return False, '无效位置'
                item = p['bench'].pop(idx)
            else:
                key = key_or_idx
                if key not in p['board']:
                    return False, '无效位置'
                item = p['board'].pop(key)
            card = CARD_BY_ID[item['card']]
            star = unit_star(item)
            copies = 3 ** (star - 1)
            p['gold'] += sell_value(card, star)
            p['energy'] = min(100, p['energy'] + card['energy'] * copies // 2)
            p['reason'] = min(100, p['reason'] + card['reason'] * copies // 2)
            if p['reason'] > 0:
                p['crashed'] = False
            self.version += 1
            return True, None

    def place(self, pid, bench_index, x, y):
        with self.lock:
            p, err = self._prep_player(pid)
            if err:
                return False, err
            if not isinstance(bench_index, int) or not (0 <= bench_index < len(p['bench'])):
                return False, '无效位置'
            if not isinstance(x, int) or not isinstance(y, int) \
                    or not (0 <= x < HALF_W and 0 <= y < HALF_H):
                return False, '超出你的半场'
            if len(p['board']) >= MAX_BOARD:
                return False, f'场上最多 {MAX_BOARD} 个棋子'
            key = f'{x},{y}'
            if key in p['board']:
                return False, '该位置已有单位'
            p['board'][key] = p['bench'].pop(bench_index)
            self.version += 1
            return True, None

    def retrieve(self, pid, x, y):
        with self.lock:
            p, err = self._prep_player(pid)
            if err:
                return False, err
            key = f'{x},{y}'
            if key not in p['board']:
                return False, '空位'
            if len(p['bench']) >= MAX_BENCH:
                return False, '备战席已满'
            p['bench'].append(p['board'].pop(key))
            self.version += 1
            return True, None

    def toggle_ready(self, pid):
        with self.lock:
            p, err = self._prep_player(pid)
            if err:
                return False, err
            p['ready'] = not p['ready']
            active = [pl for pl in self.players.values() if not pl.get('dead')]
            if active and all(pl['ready'] for pl in active):
                self.prep_end = time.time()
            else:
                self.prep_end = 0.0
            self.version += 1
            return True, None

    # ---- 配对 --------------------------------------------------------------
    def _compute_pairings(self):
        ids = [cid for cid, p in self.players.items() if not p.get('dead')]
        n = len(ids)
        if n < 2:
            self.pairings = []
            self._bye_players = list(ids)
            return

        ids.sort(key=lambda cid: self.players[cid]['hp'])
        last_pairs = set(frozenset(p) for p in self.last_pair_ids)
        pairs = []
        used = set()

        for a in ids:
            if a in used:
                continue
            best, best_score = None, None
            for b in ids:
                if b == a or b in used:
                    continue
                score = 0
                if frozenset((a, b)) not in last_pairs:
                    score += 10000
                score -= abs(self.players[a]['hp'] - self.players[b]['hp'])
                if best_score is None or score > best_score:
                    best_score, best = score, b
            if best:
                pairs.append({'a': a, 'b': best})
                used.add(a)
                used.add(best)

        self._bye_players = [cid for cid in ids if cid not in used]
        self.pairings = pairs
        self.last_pair_ids = [(p['a'], p['b']) for p in pairs]
        for pr in pairs:
            print(f'[配对] {self.players[pr["a"]]["name"]} vs {self.players[pr["b"]]["name"]}')
        for cid in self._bye_players:
            print(f'[配对] {self.players[cid]["name"]} 轮空')

    # ---- 淘汰 / 结算 -------------------------------------------------------
    def _mark_dead(self, cid, note='被淘汰'):
        p = self.players.get(cid)
        if not p or p.get('dead'):
            return
        p['dead'] = True
        if not p.get('rated'):
            p['rated'] = True
            update_rating(cid, RATING_LOSE, 'lose', name=p.get('name'))
            self._sys_chat(f'{p["name"]} {note}，-20 Rating')
        else:
            self._sys_chat(f'{p["name"]} {note}')

    def _apply_empty_penalty(self):
        pending = [cid for cid, p in self.players.items()
                   if not p.get('dead') and not p['board']]
        for cid in pending:
            self.players[cid]['hp'] = max(0, self.players[cid]['hp'] - 1)
        dead = [cid for cid in pending if self.players[cid]['hp'] <= 0]
        for cid in dead:
            self._mark_dead(cid, '空场挂机被淘汰')
        if pending:
            self.version += 1

    def _tick(self):
        now = time.time()
        if self.state == 'prep':
            if self.prep_end and now >= self.prep_end:
                self._enter_battle()
        elif self.state == 'battle':
            if now - self._last_empty_check >= EMPTY_PENALTY_INTERVAL:
                self._last_empty_check = now
                self._apply_empty_penalty()
                if self._check_game_over():
                    return
            if now >= self.battle_end:
                self._enter_settle()

    def _enter_battle(self):
        purged = self._purge_abandoned()
        if purged or not self.pairs_computed:
            self._compute_pairings()

        for pair in self.pairings:
            pair.pop('frames_view', None)
            pair.pop('events_view', None)
            pair.pop('events', None)

        self.state = 'battle'
        now = time.time()
        self.battle_started_at = now
        self.battle_end = now + BATTLE_TIME
        self._last_empty_check = now
        self.version += 1

        for p in self.players.values():
            p['opponent'] = None

        self._bye_frames = {cid: self._make_bye_frames(cid) for cid in self._bye_players}

        for pair in self.pairings:
            a = self.players.get(pair['a'])
            b = self.players.get(pair['b'])
            if not a or not b or a.get('dead') or b.get('dead'):
                continue
            a['opponent'] = pair['b']
            b['opponent'] = pair['a']
            frames, events, a_hp_map, b_hp_map = self._simulate_battle(a, b, self.round)
            pair['frames_view'] = {
                'a': frames,
                'b': self._transform_frames_for_viewer(frames, 'b'),
            }
            pair['events_view'] = {
                'a': events,
                'b': self._transform_event_for_viewer(events, 'b'),
            }
            pair['events'] = events

            # 阵亡棋子不再从棋盘上删除，保留 0 血到下一轮。
            for key, info in a['board'].items():
                info['hp'] = max(0, int(a_hp_map.get(key, 0)))
            for key, info in b['board'].items():
                info['hp'] = max(0, int(b_hp_map.get(key, 0)))

        for p in self.players.values():
            if not p.get('dead'):
                p['ready'] = False

    def _enter_settle(self):
        for pair in self.pairings:
            a = self.players.get(pair['a'])
            b = self.players.get(pair['b'])
            if not a or not b:
                continue

            if a.get('dead') or b.get('dead'):
                for p in (a, b):
                    if not p.get('dead'):
                        p['lastResult'] = 'win'
                        p['roundWins'] += 1
                        p['mind'] = min(MIND_MAX, p['mind'] + MIND_WIN)
                        p['gold'] = 18
                continue

            a_power = board_power(a['board'])
            b_power = board_power(b['board'])
            events = pair.get('events', [])
            a_dmg = sum(e.get('dmg', 0) for e in events
                        if e.get('owner') == a['id'] and not e.get('shared'))
            b_dmg = sum(e.get('dmg', 0) for e in events
                        if e.get('owner') == b['id'] and not e.get('shared'))

            def _alive_count(p):
                return sum(1 for info in p['board'].values()
                           if float(info.get('hp', 0) or 0) > 0)

            def _gold_for(p, my_dmg, opp):
                perf = math.sqrt(max(0.0, my_dmg) / 50.0) + math.sqrt(_alive_count(opp)) * 1.5
                bonus = min(10, int(perf))
                return min(24, max(18, int((10 + bonus) * 1.2)))

            if a_power == b_power:
                for p, my_dmg, opp in ((a, a_dmg, b), (b, b_dmg, a)):
                    p['lastResult'] = 'draw'
                    p['gold'] = _gold_for(p, my_dmg, opp)
            else:
                a_win = a_power > b_power
                b_win = b_power > a_power
                hp_loss = abs(a_power - b_power)
                for p, win, opp, my_dmg in ((a, a_win, b, a_dmg), (b, b_win, a, b_dmg)):
                    if win:
                        p['lastResult'] = 'win'
                        p['roundWins'] += 1
                        p['mind'] = min(MIND_MAX, p['mind'] + MIND_WIN)
                    else:
                        p['lastResult'] = 'lose'
                        p['roundLosses'] += 1
                        p['hp'] = max(0, p['hp'] - hp_loss)
                        p['mind'] = max(0, p['mind'] - MIND_LOSE)
                    p['gold'] = _gold_for(p, my_dmg, opp)

        for cid in self._bye_players:
            p = self.players.get(cid)
            if p and not p.get('dead'):
                p['lastResult'] = 'bye'
                p['gold'] = 18

        for p in self.players.values():
            if p.get('dead'):
                continue
            if p['reason'] <= 0 and not p.get('crashed'):
                p['crashed'] = True
                self._sys_chat(f'{p["name"]} 理智耗尽，陷入崩溃')
            if p.get('crashed'):
                p['mind'] = max(0, p['mind'] - REASON_CRASH_MIND)

        dead = [cid for cid, p in self.players.items()
                if not p.get('dead') and (p['hp'] <= 0 or p['mind'] <= 0)]
        for cid in dead:
            p = self.players[cid]
            note = '心态崩溃退赛' if p['mind'] <= 0 and p['hp'] > 0 else 'AC 归零被淘汰'
            self._mark_dead(cid, note)

        if self._check_game_over():
            return

        self.round += 1
        if self.round > MAX_ROUNDS:
            self._end_by_gold()
            return

        for p in self.players.values():
            if p.get('dead'):
                continue
            p['energy'] = min(100, p['energy'] + ENERGY_PER_ROUND)
            p['reason'] = min(100, p['reason'] + REASON_PER_ROUND)
            if p['reason'] > 0:
                p['crashed'] = False
            p['level'] = level_for_round(self.round)
            cid = self._roll_shop(p['level'], 1, owner=p)[0]
            if len(p['bench']) < MAX_BENCH or self._would_merge(p, cid, 1):
                p['bench'].append(make_card_obj(cid))
                self._try_merge(p)

        self._roll_all_shops()
        self._start_prep()
        self.version += 1

    def _finish_game(self, winner_id, note=''):
        if self.state == 'ended':
            return False
        self.state = 'ended'
        self._ended_at = time.time()
        self.winner = winner_id
        for cid, p in list(self.players.items()):
            if p.get('rated'):
                continue
            p['rated'] = True
            if cid == winner_id:
                gain = max(1, int(p['gold'] / 3))
                update_rating(cid, gain, 'win', name=p.get('name'))
                p['lastResult'] = 'win'
                self._sys_chat(f'{p["name"]} 获胜！金币 {p["gold"]}，Rating +{gain}')
            else:
                update_rating(cid, 0, 'lose', name=p.get('name'))
        self._purge_abandoned()
        if note:
            self._sys_chat(note)
        self.version += 1
        return True

    def _check_game_over(self):
        if self.state == 'ended':
            return True
        if self.state == 'waiting':
            return False
        alive = [cid for cid, p in self.players.items() if not p.get('dead')]
        if len(alive) <= 1:
            self._finish_game(alive[0] if alive else None)
            return True
        return False

    def _end_by_gold(self):
        alive = [cid for cid, p in self.players.items() if not p.get('dead')]
        if not alive:
            self._finish_game(None)
            return
        winner_id = max(alive, key=lambda cid: (
            self.players[cid]['gold'],
            self.players[cid]['roundWins'],
            self.players[cid]['hp'],
        ))
        self._finish_game(winner_id, f'回合上限，{self.players[winner_id]["name"]} 金币最多获胜！')

    # ========================================================
    # 战斗模拟
    # ========================================================
    def _unit_from(self, owner, key, info, side, stats, round_no):
        x, y = map(int, key.split(','))
        card = CARD_BY_ID[info['card']]
        star = unit_star(info)
        max_hp = float(star_max_hp(card, star))
        hp = int(info.get('hp', max_hp))
        if hp <= 0:
            return None
        atk = star_attack(card, star)
        rng = float(card['range'])
        skill = card['skill']
        if skill == 'shift_stats':
            atk *= 2.0
            hp = min(hp, max_hp)
        elif skill == 'matrix_pow':
            atk *= 1.5
            hp = min(hp, max_hp)
        if skill == 'grow_range':
            rng += max(0, round_no - 1)
        by = y + HALF_H if side == 'a' else (HALF_H - 1 - y)
        return {
            'uid': f'{owner}:{key}', 'owner': owner, 'origKey': key, 'side': side,
            'card': card['id'], 'star': star, 'x': x, 'y': by,
            'hp': float(hp), 'maxHp': max_hp,
            'atk': atk, 'baseAtk': atk, 'range': rng, 'skill': skill,
            'trait': card['trait'],
            'active': skill in ACTIVE_SKILLS,
            'atkCd': 0.0, 'skillCd': 0.0, 'slowUntil': -1.0,
            'stallUntil': -1.0, 'actionUntil': -1.0,
            'shield': 0.0, 'stacks': 0, 'hits': 0, 'charge': 0, 'kills': min(GENETIC_CAP, int(info.get('kills', 0))) if skill == 'genetic' else 0,
            'outMult': stats[owner]['out'], 'inMult': stats[owner]['in'],
            'swap': [], 'delayed': [],
            'lastCard': '', 'mark': 0, 'mstGuard': 0.0,
        }

    @staticmethod
    def _dist(a, b):
        return abs(a['x'] - b['x']) + abs(a['y'] - b['y'])

    @staticmethod
    def _attack_speed_aura(u, units):
        # 八邻域（含斜角），仅活着的同队 O2；多个来源取同一个倍率。
        return O2_SPEED_MULT if any(
            o is not u and o['hp'] > 0 and o['owner'] == u['owner']
            and o['skill'] == 'o2_aura'
            and max(abs(o['x'] - u['x']), abs(o['y'] - u['y'])) == 1
            for o in units) else 1.0

    def _attack_rate(self, u, units, t):
        slow = ATK_CD / ATK_CD_SLOWED if u['slowUntil'] > t else 1.0
        return self._attack_speed_aura(u, units) * slow

    def _apply_spawn_passives(self, units):
        # ---- Global bonds: every (owner, trait) group of 2/4/6 units ----
        # unlocks one tier. Effects are deliberately small so the whole pool
        # stays balanced; all units of both sides are treated identically.
        group = {}
        for u in units:
            k = (u['owner'], u['trait'])
            group[k] = group.get(k, 0) + 1
        for u in units:
            tier = bond_tier(group[(u['owner'], u['trait'])])
            if tier <= 0:
                continue
            u['bondTier'] = tier
            u['atk'] = u['baseAtk'] = u['baseAtk'] * (1.0 + BOND_ATK_STEP)
            if tier >= 3:
                u['inMult'] = u['inMult'] * (1.0 - BOND_GUARD_STEP)
            if tier >= 2:
                # Keep HP integral: a fractional maxHp would make a living
                # 0.x-HP unit serialize as hp=0 in the replay frames.
                u['maxHp'] = float(int(u['maxHp'] * (1.0 + BOND_HP_STEP)))
                u['hp'] = min(u['maxHp'], float(int(u['hp'] * (1.0 + BOND_HP_STEP))))
        # ---- SAM state compression: same-card allies trade HP for attack ----
        same = {}
        for u in units:
            k = (u['owner'], u['card'])
            same[k] = same.get(k, 0) + 1
        for u in units:
            if u['skill'] != 'sam_compress':
                continue
            n = min(SAM_CAP, max(0, same[(u['owner'], u['card'])] - 1))
            # A lone state still compresses its own suffix, so it gains the
            # attack bonus without paying the space cost; the HP penalty
            # only applies once there are states to merge with.
            u['atk'] = u['baseAtk'] = u['baseAtk'] * (1.0 + SAM_ATK_STEP * (n + 1))
            if n > 0:
                u['maxHp'] = float(max(1, int(u['maxHp'] * (1.0 - SAM_HP_STEP * n))))
                u['hp'] = min(u['maxHp'], float(int(u['hp'])))
        # ---- MST links: each orthogonal ally is one edge of damage share ---
        for u in units:
            if u['skill'] != 'mst_link':
                continue
            links = sum(1 for o in units
                        if o is not u and o['hp'] > 0
                        and o['owner'] == u['owner'] and self._dist(u, o) == 1)
            u['mstGuard'] = min(MST_GUARD_CAP, links) * MST_GUARD_STEP
        # 合并边只由归并排序连接自己与正交邻居；连通组同步均分，消除遍历顺序差异。
        unseen = {u['uid']: u for u in units}
        edges = {u['uid']: set() for u in units}
        for u in units:
            if u['skill'] == 'merge_ally':
                for o in units:
                    if o is not u and o['owner'] == u['owner'] and self._dist(u, o) == 1:
                        edges[u['uid']].add(o['uid'])
                        edges[o['uid']].add(u['uid'])
        while unseen:
            key = next(iter(unseen))
            group, todo = [], [key]
            while todo:
                key = todo.pop()
                if key not in unseen:
                    continue
                group.append(unseen.pop(key))
                todo.extend(edges[key])
            if len(group) < 2:
                continue
            remaining = sum(u['hp'] for u in group)
            pending = list(group)
            while pending:
                avg = remaining / len(pending)
                capped = [u for u in pending if u['maxHp'] < avg]
                if not capped:
                    ordered = sorted(pending, key=lambda u: u['uid'])
                    base, extra = divmod(int(round(remaining)), len(ordered))
                    for i, u in enumerate(ordered):
                        u['hp'] = float(base + (i < extra))
                    break
                for u in capped:
                    u['hp'] = u['maxHp']
                    remaining -= u['hp']
                    pending.remove(u)

    def _refresh_swaps(self, units, now):
        # 从基础攻击按仍有效的交换顺序重放；重叠交换到期不会回滚成负攻击。
        tokens = set()
        by_uid = {u['uid']: u for u in units}
        for u in units:
            u['swap'] = [token for token in u['swap'] if token[4] > now + 1e-9]
            tokens.update(u['swap'])
            u['atk'] = u['baseAtk']
        for _, _, left, right, _ in sorted(tokens):
            a, b = by_uid[left], by_uid[right]
            a['atk'], b['atk'] = b['atk'], a['atk']

    def _notify_ally_action(self, u, units):
        for o in units:
            if o is not u and o['hp'] > 0 and o['owner'] == u['owner'] and o['skill'] == 'stack_ally':
                o['stacks'] = min(STACK_ALLY_CAP, o['stacks'] + 1)

    def _pick_target(self, u, enemies):
        sk = u['skill']
        enemies = [e for e in enemies if self._dist(u, e) <= u['range']] or enemies
        if sk == 'finish_weak':
            return min(enemies, key=lambda e: (e['hp'], self._dist(u, e)))
        if sk == 'sliding_max':
            return min(enemies, key=lambda e: (-e['atk'], self._dist(u, e)))
        if sk == 'heuristic':
            return min(enemies, key=lambda e: (self._dist(u, e) + e['hp'] / max(1.0, e['atk']), self._dist(u, e)))
        return min(enemies, key=lambda e: (self._dist(u, e), e['hp']))

    def _deal_damage(self, target, raw, events, t, units, by_uid,
                     source=None, is_attack=False, allow_react=True):
        if target['hp'] <= 0:
            return 0
        raw = raw * (1.0 - target.get('mstGuard', 0.0)) \
              * (1.0 + SCC_MARK_STEP * min(SCC_MARK_CAP, target.get('mark', 0)))
        dmg = max(1, int(raw * target['inMult']))
        pending_shield = 0

        if target['skill'] == 'shield_on_low' and source is not None \
                and dmg < target['atk'] * SHIELD_ON_LOW_ATK:
            # 旧规则是「伤害低于自身攻击力就完全免疫」，在全局伤害 \xd71/3 的设定下
            # 等于对同费及以下的攻击者永久无敌。现在改成按比例减免 + 转护盾。
            conv = int(dmg * SHIELD_ON_LOW_CONVERT)
            if conv > 0:
                pending_shield = conv
                dmg -= conv

        dealt = dmg

        if allow_react:
            links = [o for o in units
                     if o['hp'] > 0 and o is not target and o['owner'] == target['owner']
                     and o['skill'] == 'link_ally' and self._dist(o, target) == 1]
            if links and dmg > 1:
                total_share = min(max(1, int(dmg * LINK_SHARE)), dmg - 1)
                actual = 0
                killed = 0
                for i, o in enumerate(links):
                    take = total_share // len(links) + (1 if i < total_share % len(links) else 0)
                    if take <= 0:
                        break
                    o['hp'] -= take
                    actual += take
                    # Emit a hit event for the shared damage so the client shows
                    # the number on the ally instead of silently dropping HP.
                    events.append({
                        't': round(t, 6), 'type': 'attack',
                        'fromX': int(source['x']) if source else int(target['x']),
                        'fromY': int(source['y']) if source else int(target['y']),
                        'toX': int(o['x']), 'toY': int(o['y']),
                        'dmg': take,
                        'owner': source['owner'] if source else target['owner'],
                        'sourceUid': source['uid'] if source else target['uid'],
                        'targetUid': o['uid'], 'skillId': 'gcd_share',
                        'shared': True,
                    })
                    if o['hp'] <= 0:
                        killed += 1
                dealt = max(0, dmg - actual)
                if killed and source is not None and source.get('skill') == 'genetic':
                    source['kills'] = min(GENETIC_CAP, source['kills'] + killed)

        if target['shield'] > 0 and dealt > 0:
            absorbed = min(target['shield'], dealt)
            target['shield'] -= absorbed
            dealt -= absorbed

        dealt = min(max(0.0, target['hp']), dealt)
        if dealt > 0:
            target['hp'] -= dealt
            if target['hp'] <= 0 and source is not None and source.get('skill') == 'genetic':
                source['kills'] = min(GENETIC_CAP, source['kills'] + 1)
        if dealt > 0 and target.get('skill') == 'splay_rotate':
            target['stacks'] = int(target.get('stacks', 0) // 2)

        if pending_shield > 0 and target['hp'] > 0:
            old_shield = target['shield']
            target['shield'] = min(int(target['maxHp'] * SHIELD_CAP_RATIO), old_shield + pending_shield)
            gained = target['shield'] - old_shield
            if gained > 0:
                events.append({'t': round(t, 6), 'type': 'shield', 'x': int(target['x']), 'y': int(target['y']), 'owner': target['owner'], 'dmg': gained, 'uid': target['uid']})

        if is_attack and allow_react and source is not None and dealt > 0 \
                and target['skill'] == 'thorns' and source['hp'] > 0:
            back = min(source['hp'], max(1, int(dealt * THORNS_RATIO)))
            source['hp'] -= back
            events.append({'t': round(t, 6), 'type': 'attack',
                           'fromX': int(target['x']), 'fromY': int(target['y']),
                           'toX': int(source['x']), 'toY': int(source['y']),
                           'dmg': back, 'owner': target['owner'], 'thorns': True, 'sourceUid': target['uid'], 'targetUid': source['uid'], 'skillId': 'thorns'})
        return dealt

    def _attack_multiplier(self, u, target, units, t, round_no):
        base = u['atk'] * DMG_MULT * u['outMult']
        sk = u['skill']
        u['hits'] = u.get('hits', 0) + 1
        h = u['hits']
        if sk == 'spfa_stall':
            base *= SPFA_DAMAGE_MULT
        elif sk == 'prime_round':
            if is_prime(round_no):
                base *= PRIME_MULT
        elif sk == 'cdq':
            base *= CDQ_EARLY if t < CDQ_SWITCH else CDQ_LATE
        elif sk == 'expectation':
            base *= EXPECT_MULT
        elif sk == 'matrix_pow':
            base *= MATRIX_STEP ** min(MATRIX_CAP, int(t // 6))
        elif sk == 'genetic':
            base *= 1.0 + GENETIC_STEP * min(GENETIC_CAP, u['kills'])
        elif sk == 'every_n':
            if u['hits'] % EVERY_N_STEPS == 0:
                base *= EVERY_N_MULT
        elif sk == 'charge_burst':
            u['charge'] += 1
            if u['charge'] >= CHARGE_STEPS:
                u['charge'] = 0
                base *= CHARGE_MULT
        elif sk == 'stack_ally':
            base *= 1.0 + STACK_ALLY_STEP * min(STACK_ALLY_CAP, u['stacks'])
        elif sk == 'crowd_crit':
            near = sum(1 for e in units
                       if e['hp'] > 0 and e is not target and e['owner'] != u['owner']
                       and abs(e['x'] - target['x']) <= 1 and abs(e['y'] - target['y']) <= 1)
            if near >= 3:
                base *= 2.0
        elif sk == 'prefix_growth':
            base *= 1.0 + PREFIX_GROWTH_STEP * min(PREFIX_GROWTH_CAP, h - 1)
        elif sk == 'fft_butterfly':
            base *= FFT_EVEN_MULT if h % 2 == 0 else FFT_ODD_MULT
        elif sk == 'kmp_next':
            base *= 1.0 + KMP_NEXT_STEP * min(KMP_NEXT_CAP, u.get('charge', 0))
        elif sk == 'lcp_chain':
            base *= LCP_SAME_MULT if u.get('lastCard', '') == target['card'] else LCP_OTHER_MULT
        elif sk == 'heuristic':
            base *= HEURISTIC_MULT
        elif sk == 'mod_cycle':
            phase = (h - 1) % MOD_CYCLE
            base *= MOD_CYCLE_BURST if phase == MOD_CYCLE - 1 \
                else max(0.4, MOD_CYCLE_START - MOD_CYCLE_STEP * phase)
        elif sk == 'splay_rotate':
            base *= 1.0 + SPLAY_STEP * min(SPLAY_CAP, u.get('stacks', 0))
        if sk == 'rampage' and u['hp'] < u['maxHp'] * RAMPAGE_HP:
            base *= RAMPAGE_MULT
        return base

    def _do_attack(self, u, target, units, events, t, by_uid, round_no):
        if u['skill'] == 'o2_aura':
            return
        raw = self._attack_multiplier(u, target, units, t, round_no)
        h = u.get('hits', 0)
        dealt = self._deal_damage(target, raw, events, t, units, by_uid,
                                  source=u, is_attack=True)
        events.append({'t': round(t, 6), 'type': 'attack',
                       'fromX': int(u['x']), 'fromY': int(u['y']),
                       'toX': int(target['x']), 'toY': int(target['y']),
                       'dmg': dealt, 'owner': u['owner'], 'sourceUid': u['uid'], 'targetUid': target['uid'], 'skillId': u['skill']})

        self._notify_ally_action(u, units)

        sk = u['skill']
        # ---- unique-skill post-hit hooks (all produce real damage events) ---
        if sk == 'seg_query' and h % SEG_QUERY_STEPS == 0:
            for e in units:
                if e['hp'] <= 0 or e['owner'] == u['owner'] or e is target \
                        or self._dist(u, e) > u['range']:
                    continue
                dmg = self._deal_damage(e, raw * SEG_QUERY_RATIO, events, t,
                                        units, by_uid, source=u)
                events.append({'t': round(t, 6), 'type': 'attack',
                               'fromX': int(u['x']), 'fromY': int(u['y']),
                               'toX': int(e['x']), 'toY': int(e['y']),
                               'dmg': dmg, 'owner': u['owner'], 'skill': True,
                               'skillId': 'seg_query', 'sourceUid': u['uid'],
                               'targetUid': e['uid']})
        elif sk == 'multi_match':
            for e in units:
                if e['hp'] <= 0 or e['owner'] == u['owner'] or e is target \
                        or e['card'] != target['card'] \
                        or self._dist(u, e) > u['range']:
                    continue
                dmg = self._deal_damage(e, raw * MULTI_MATCH_RATIO, events, t,
                                        units, by_uid, source=u)
                events.append({'t': round(t, 6), 'type': 'attack',
                               'fromX': int(u['x']), 'fromY': int(u['y']),
                               'toX': int(e['x']), 'toY': int(e['y']),
                               'dmg': dmg, 'owner': u['owner'], 'skill': True,
                               'skillId': 'multi_match', 'sourceUid': u['uid'],
                               'targetUid': e['uid']})
        if sk == 'scc_mark':
            target['mark'] = min(SCC_MARK_CAP, target.get('mark', 0) + 1)
        if sk == 'lcp_chain':
            u['lastCard'] = target['card']
        if sk == 'kmp_next':
            u['charge'] = 0 if target['hp'] <= 0 \
                else min(KMP_NEXT_CAP, u.get('charge', 0) + 1)
        if sk == 'splay_rotate':
            u['stacks'] = min(SPLAY_CAP, u.get('stacks', 0) + 1)
        if sk == 'pierce':
            dy = 1 if target['y'] >= u['y'] else -1
            back = [e for e in units
                    if e['hp'] > 0 and e['owner'] != u['owner']
                    and e['x'] == target['x'] and e['y'] == target['y'] + dy]
            for e in back[:1]:
                dmg = self._deal_damage(e, raw * PIERCE_RATIO, events, t, units,
                                        by_uid, source=u)
                events.append({'t': round(t, 6), 'type': 'attack',
                               'fromX': int(u['x']), 'fromY': int(u['y']),
                               'toX': int(e['x']), 'toY': int(e['y']),
                               'dmg': dmg, 'owner': u['owner'], 'skill': True,
                               'skillId': 'pierce', 'sourceUid': u['uid'], 'targetUid': e['uid']})
        elif sk == 'splash':
            for e in units:
                if e['hp'] <= 0 or e['owner'] == u['owner'] or e is target \
                        or self._dist(e, target) != 1:
                    continue
                dmg = self._deal_damage(e, raw * SPLASH_RATIO, events, t, units,
                                        by_uid, source=u)
                events.append({'t': round(t, 6), 'type': 'attack',
                               'fromX': int(u['x']), 'fromY': int(u['y']),
                               'toX': int(e['x']), 'toY': int(e['y']),
                               'dmg': dmg, 'owner': u['owner'], 'skill': True,
                               'skillId': 'splash', 'sourceUid': u['uid'], 'targetUid': e['uid']})
        if sk == 'lifesteal' and dealt > 0 and u['hp'] > 0:
            heal = min(u['maxHp'] - u['hp'], int(dealt * LIFESTEAL_RATIO))
            if heal > 0:
                u['hp'] += heal
                events.append({'t': round(t, 6), 'type': 'heal',
                               'x': int(u['x']), 'y': int(u['y']),
                               'owner': u['owner'], 'dmg': heal, 'uid': u['uid']})

        if target['hp'] > 0 or u['hp'] <= 0:
            return
        if u['skill'] == 'chain_kill' and u['kills'] < 3:
            u['kills'] += 1
            rest = [e for e in units if e['hp'] > 0 and e['owner'] != u['owner']]
            if rest:
                nxt = self._pick_target(u, rest)
                if self._dist(u, nxt) <= u['range']:
                    self._do_attack(u, nxt, units, events, t, by_uid, round_no)

    def _use_skill(self, u, target, enemies, units, events, t, by_uid, round_no):
        sk = u['skill']
        if sk != 'aoe_debuff':
            enemies = [e for e in enemies if e['hp'] > 0 and self._dist(u, e) <= u['range']]
        self._notify_ally_action(u, units)
        cast_event = {'t': round(t, 6), 'type': 'skill',
                       'x': int(u['x']), 'y': int(u['y']),
                       'owner': u['owner'], 'name': sk, 'sourceUid': u['uid'], 'toX': target['x'], 'toY': target['y'], 'targets': []}
        events.append(cast_event)

        def hit(e, mult, extra=None, raw_override=None):
            cast_event['targets'].append({'x': int(e['x']), 'y': int(e['y'])})
            raw = raw_override if raw_override is not None else u['atk'] * DMG_MULT * u['outMult'] * mult
            dealt = self._deal_damage(e, raw, events, t, units, by_uid, source=u)
            ev = {'t': round(t, 6), 'type': 'attack',
                  'fromX': int(u['x']), 'fromY': int(u['y']),
                  'toX': int(e['x']), 'toY': int(e['y']),
                  'dmg': dealt, 'owner': u['owner'], 'skill': True, 'skillId': sk, 'sourceUid': u['uid'], 'targetUid': e['uid']}
            if extra:
                ev.update(extra)
            events.append(ev)

        caster = self._SKILL_CASTERS.get(sk)
        if caster is not None:
            getattr(self, caster)(hit, u, target, enemies, units, events, t, by_uid, cast_event)

    # 技能分派表：sk -> 处理器方法名。每个处理器接收统一上下文，
    # 逻辑与原 _use_skill 的 if/elif 分支逐行等价；hit 闭包由 _use_skill 传入。
    _SKILL_CASTERS = {
        'aoe': '_sk_aoe',
        'aoe_debuff': '_sk_aoe_debuff',
        'multi': '_sk_multi',
        'line': '_sk_line',
        'range_aoe': '_sk_range_aoe',
        'block_aoe': '_sk_block_aoe',
        'delayed_line': '_sk_delayed_line',
        'swap_stats': '_sk_swap_stats',
        'sort_line': '_sk_sort_line',
        'compress_line': '_sk_compress_line',
        'pincer': '_sk_pincer',
        'partition': '_sk_partition',
        'divide_conquer': '_sk_divide_conquer',
        'sweep': '_sk_sweep',
        'freeze': '_sk_freeze',
        'min_cut': '_sk_min_cut',
    }

    def _sk_aoe(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        for e in enemies:
            hit(e, 0.5)

    def _sk_aoe_debuff(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        for e in enemies:
            hit(e, AOE_DEBUFF_RATIO)
            e['slowUntil'] = max(e['slowUntil'], t + SLOW_DURATION)

    def _sk_multi(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        for _ in range(3):
            if target['hp'] <= 0:
                break
            hit(target, 0.5)

    def _sk_line(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        row = [e for e in enemies if e['y'] == target['y']]
        col = [e for e in enemies if e['x'] == target['x']]
        line = row if len(row) >= len(col) else col
        for e in (line or [target]):
            hit(e, 0.5)

    def _sk_range_aoe(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        box = [e for e in enemies if e['y'] == target['y']
               and abs(e['x'] - target['x']) <= 1]
        for e in box:
            hit(e, 0.8)

    def _sk_block_aoe(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        box = [e for e in enemies
               if e['x'] // 2 == target['x'] // 2 and e['y'] // 2 == target['y'] // 2]
        for e in (box or [target]):
            hit(e, 0.7)

    def _sk_delayed_line(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        row = [e for e in enemies if e['y'] == target['y']] or [target]
        for e in row:
            amount = u['atk'] * DMG_MULT * u['outMult'] * 1.5
            e['delayed'].append((t + 2.0, amount, u['uid']))
            cast_event['targets'].append({'x': int(e['x']), 'y': int(e['y'])})

    def _sk_swap_stats(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        # 卡面写的是“攻击最高的敌人”，目标本身也在候选里
        other = max(enemies, key=lambda e: e['atk'])
        ua, oa = u['atk'], other['atk']
        u['atk'], other['atk'] = oa, ua
        token = (t, len(events), u['uid'], other['uid'], t + SWAP_DURATION)
        u['swap'].append(token)
        other['swap'].append(token)
        self._refresh_swaps(units, t)
        cast_event['targets'].append({'x': int(other['x']), 'y': int(other['y'])})

    def _sk_sort_line(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        row = sorted([e for e in enemies if e['y'] == target['y']], key=lambda e: e['x'])
        for i in range(0, len(row) - 1, 2):
            row[i]['x'], row[i + 1]['x'] = row[i + 1]['x'], row[i]['x']
        for e in row:
            hit(e, 0.3)

    def _sk_compress_line(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        allies = [o for o in units
                  if o is not u and o['hp'] > 0 and o['owner'] == u['owner']
                  and o['y'] == u['y']]
        total_atk = u['atk'] + sum(o['atk'] for o in allies)
        row = [e for e in enemies if e['y'] == target['y']] or [target]
        for e in row:
            hit(e, 1.0, raw_override=total_atk * DMG_MULT * u['outMult'])

    def _sk_pincer(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        near = min(enemies, key=lambda e: self._dist(u, e))
        far = max(enemies, key=lambda e: self._dist(u, e))
        hit(near, 1.2)
        if far is not near:
            hit(far, 1.2)

    def _sk_partition(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        ranked = sorted(enemies, key=lambda e: -e['atk'])
        half = ranked[:max(1, (len(ranked) + 1) // 2)]
        for e in half:
            hit(e, 1.0)

    def _sk_divide_conquer(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        pool = [e for e in enemies if self._dist(u, e) <= u['range']] or [target]
        for e in pool:
            hit(e, 0.5)
        if all(e['hp'] > 0 for e in pool):
            for e in pool:
                hit(e, 1.0)

    def _sk_sweep(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        row = sorted([e for e in enemies if e['y'] == target['y']] or [target],
                     key=lambda e: abs(e['x'] - u['x']))
        for i, e in enumerate(row[:3]):
            hit(e, 0.6 + 0.3 * i)

    def _sk_freeze(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        for e in enemies:
            hit(e, FREEZE_RATIO)
            e['stallUntil'] = max(e['stallUntil'], t + FREEZE_STALL)

    def _sk_min_cut(self, hit, u, target, enemies, units, events, t, by_uid, cast_event):
        n = max(1, len(enemies))
        ratio = MIN_CUT_RATIO / (1.0 + MIN_CUT_SPREAD * (n - 1))
        boss = max(enemies, key=lambda e: e['hp']) if enemies else None
        for e in enemies:
            hit(e, ratio)
        if boss is not None and boss['hp'] > 0:
            hit(boss, MIN_CUT_BOSS_RATIO / (1.0 + MIN_CUT_BOSS_SPREAD * (n - 1)))

    def _alive_side(self, units, owner):
        return [u for u in units if u['hp'] > 0 and u['owner'] == owner]

    def _frame_snapshot(self, units, now, record, frames):
        if not record:
            return
        frames.append({
            't': round(now, 6),
            'units': [{
                'uid': u['uid'], 'owner': u['owner'],
                'x': int(u['x']), 'y': int(u['y']),
                'hp': max(0, int(u['hp'])), 'maxHp': int(u['maxHp']),
                'shield': max(0, int(u['shield'])),
                'card': u['card'], 'star': u['star'], 'slowed': u['slowUntil'] > now,
                'haste': self._attack_speed_aura(u, units),
                'stalled': u['stallUntil'] > now,
                'stallLeft': round(max(0.0, u['stallUntil'] - now), 3),
                'atk': round(u['atk'], 2), 'range': u['range'],
                'attackProgress': max(0.0, min(1.0, 1.0 - u['atkCd'] / (ATK_CD / (SPFA_SPEED_MULT if u['skill'] == 'spfa_stall' else 1.0)))),
                'skillLeft': round(max(0.0, u['skillCd']), 3),
                'delayedDamage': round(sum(d[1] for d in u['delayed']), 2),
                'charge': u['charge'], 'stacks': u['stacks'], 'kills': u['kills'],
                'swapped': bool(u['swap']),
                'phase': '爆发' if u['skill'] == 'cdq' and now >= CDQ_SWITCH else '',
            } for u in units if u['hp'] > 0],
        })

    def _settle_delayed(self, u, units, events, t, by_uid, eps):
        if not u['delayed']:
            return
        due = [d for d in u['delayed'] if d[0] <= t + eps]
        u['delayed'] = [d for d in u['delayed'] if d[0] > t + eps]
        for _, amount, src_uid in due:
            src = by_uid.get(src_uid)
            dealt = self._deal_damage(u, amount, events, t, units, by_uid, source=src)
            events.append({'t': round(t, 6), 'type': 'attack', 'fromX': src['x'] if src else u['x'], 'fromY': src['y'] if src else u['y'], 'toX': u['x'], 'toY': u['y'], 'dmg': dealt, 'owner': src['owner'] if src else u['owner'], 'sourceUid': src_uid, 'targetUid': u['uid'], 'skill': True, 'skillId': 'delayed_line'})

    def _act_in_range(self, u, target, enemies, units, events, t, by_uid, round_no, pools, eps):
        acted = False
        if t >= u['actionUntil'] - eps:
            if u['active'] and u['skillCd'] <= eps:
                cost = float(CARD_BY_ID[u['card']]['skillCost'])
                if pools.get(u['owner'], 0.0) >= cost:
                    pools[u['owner']] -= cost
                    u['skillCd'] = SKILL_CD
                    self._use_skill(u, target, enemies, units, events, t, by_uid, round_no)
                    # 保留原有施法占用一次行动的规则。
                    u['actionUntil'] = t + TICK_SEC
                    acted = True
            if not acted and u['atkCd'] <= eps and t >= u['stallUntil'] - eps:
                self._do_attack(u, target, units, events, t, by_uid, round_no)
                u['atkCd'] = ATK_CD / (SPFA_SPEED_MULT if u['skill'] == 'spfa_stall' else 1.0)
                if u['skill'] == 'spfa_stall' and random.random() < SPFA_STALL_CHANCE:
                    u['stallUntil'] = t + SPFA_STALL_EXTRA

    def _step_move(self, u, target, units):
        dx = target['x'] - u['x']
        dy = target['y'] - u['y']
        sx = 0 if dx == 0 else (1 if dx > 0 else -1)
        sy = 0 if dy == 0 else (1 if dy > 0 else -1)
        order = ([(sx, 0), (0, sy)] if abs(dx) >= abs(dy)
                 else [(0, sy), (sx, 0)])
        occupied = {(o['x'], o['y']) for o in units if o is not u and o['hp'] > 0}
        for mx, my in order:
            if mx == 0 and my == 0:
                continue
            nx, ny = u['x'] + mx, u['y'] + my
            if not (0 <= nx < BATTLE_W):
                continue
            lo, hi = ((HALF_H, BATTLE_H - 1) if u['side'] == 'a'
                      else (0, HALF_H - 1))
            if not (lo <= ny <= hi):
                continue
            # 单位不能进入已被其他存活单位占据的格子，避免战斗帧出现棋子重叠。
            if (nx, ny) in occupied:
                continue
            u['x'], u['y'] = nx, ny
            break

    def _next_event_time(self, units, t, next_move, pools, eps):
        next_t = min(BATTLE_TIME, next_move)
        for u in units:
            for due, _, _ in u['delayed']:
                if due > t + eps:
                    next_t = min(next_t, due)
            if u['hp'] <= 0:
                continue
            for expiry in (u['slowUntil'], u['stallUntil'], u['actionUntil']):
                if expiry > t + eps:
                    next_t = min(next_t, expiry)
            for _, _, _, _, expiry in u['swap']:
                if expiry > t + eps:
                    next_t = min(next_t, expiry)
            if u['skill'] == 'o2_aura':
                continue
            enemies = [e for e in units if e['owner'] != u['owner'] and e['hp'] > 0]
            if not enemies or self._dist(u, self._pick_target(u, enemies)) > u['range']:
                continue
            ready = max(t, u['stallUntil']) + max(0.0, u['atkCd']) / self._attack_rate(u, units, t)
            ready = max(ready, u['actionUntil'])
            if ready > t + eps:
                next_t = min(next_t, ready)
            if u['active'] and pools.get(u['owner'], 0.0) >= float(CARD_BY_ID[u['card']]['skillCost']):
                ready = max(t + max(0.0, u['skillCd']), u['actionUntil'])
                if ready > t + eps:
                    next_t = min(next_t, ready)
        return next_t

    def _integrate_cooldowns(self, units, t, next_t):
        dt = next_t - t
        for u in units:
            if u['hp'] <= 0:
                continue
            work_dt = max(0.0, next_t - max(t, u['stallUntil']))
            u['atkCd'] = max(0.0, u['atkCd'] - work_dt * self._attack_rate(u, units, t))
            u['skillCd'] = max(0.0, u['skillCd'] - dt)

    def _simulate_battle(self, a, b, round_no, record=True):
        stats = {}
        for p in (a, b):
            mind = p['mind']
            if mind >= MIND_HIGH:
                out, inc = MIND_DMG_UP, 1.0
            elif mind < MIND_LOW:
                out, inc = MIND_DMG_DOWN, MIND_DMG_TAKEN
            else:
                out, inc = 1.0, 1.0
            stats[p['id']] = {'out': out, 'in': inc}
        pools = {a['id']: float(a['energy']), b['id']: float(b['energy'])}

        units = []
        for key, info in a['board'].items():
            u = self._unit_from(a['id'], key, info, 'a', stats, round_no)
            if u:
                units.append(u)
        for key, info in b['board'].items():
            u = self._unit_from(b['id'], key, info, 'b', stats, round_no)
            if u:
                units.append(u)
        by_uid = {u['uid']: u for u in units}
        self._apply_spawn_passives(units)

        frames = []
        events = []
        t = 0.0


        # 攻击/技能/状态到期使用事件时间；移动仍每 TICK_SEC 一次。
        # 不缩小全局 tick，也不把冷却余量向上取整。
        eps = 1e-9
        next_move = 0.0
        self._frame_snapshot(units, 0.0, record, frames)
        while t < BATTLE_TIME - eps:
            move_now = t >= next_move - eps
            if move_now:
                next_move += TICK_SEC
            self._refresh_swaps(units, t)
            for u in units:
                self._settle_delayed(u, units, events, t, by_uid, eps)
                if u['hp'] <= 0:
                    continue
                enemies = [e for e in units if e['owner'] != u['owner'] and e['hp'] > 0]
                if not enemies:
                    break
                if u['skill'] == 'o2_aura':
                    continue
                target = self._pick_target(u, enemies)
                if self._dist(u, target) <= u['range']:
                    self._act_in_range(u, target, enemies, units, events, t, by_uid, round_no, pools, eps)
                elif move_now:
                    self._step_move(u, target, units)


            # 存储真实事件时刻的状态；重复时间戳替换初始快照。
            if frames and abs(frames[-1]['t'] - t) < eps:
                frames.pop()
            self._frame_snapshot(units, t, record, frames)
            if not self._alive_side(units, a['id']) or not self._alive_side(units, b['id']):
                break

            next_t = self._next_event_time(units, t, next_move, pools, eps)

            # 区间内光环、减速和卡顿状态不变；积分准备进度。
            self._integrate_cooldowns(units, t, next_t)
            t = next_t
        if frames and frames[-1]['t'] < round(t, 6):
            self._frame_snapshot(units, t, record, frames)

        a_hp, b_hp = {}, {}
        for u in units:
            if u['hp'] > 0:
                (a_hp if u['side'] == 'a' else b_hp)[u['origKey']] = max(1, int(u['hp']))
                if u['skill'] == 'genetic':
                    player = a if u['side'] == 'a' else b
                    player['board'][u['origKey']]['kills'] = u['kills']

        a['energy'] = int(max(0.0, pools[a['id']]))
        b['energy'] = int(max(0.0, pools[b['id']]))
        events.sort(key=lambda event: event['t'])
        return frames, events, a_hp, b_hp

    # ---- 视角变换 ----------------------------------------------------------
    def _mirror_y(self, y):
        return BATTLE_H - 1 - y

    def _transform_frames_for_viewer(self, frames, viewer_side):
        if viewer_side != 'b':
            return frames
        out = []
        for frame in frames:
            f2 = {'t': frame['t'], 'units': []}
            for u in frame['units']:
                u2 = dict(u)
                u2['y'] = self._mirror_y(u2['y'])
                f2['units'].append(u2)
            out.append(f2)
        return out

    def _transform_event_for_viewer(self, events, viewer_side):
        if viewer_side != 'b':
            return events
        out = []
        for e in events:
            e2 = dict(e)
            for k in ('fromY', 'toY', 'y'):
                if k in e2 and e2[k] is not None:
                    e2[k] = self._mirror_y(e2[k])
            if 'targets' in e2:
                e2['targets'] = [dict(p, y=self._mirror_y(p['y'])) for p in e2['targets']]
            out.append(e2)
        return out

    def _make_bye_frames(self, viewer_id):
        p = self.players.get(viewer_id)
        if not p or p.get('dead'):
            return []
        units = []
        for key, info in p['board'].items():
            x, y = map(int, key.split(','))
            card = CARD_BY_ID[info['card']]
            star = unit_star(info)
            mx = star_max_hp(card, star)
            hp = int(info.get('hp', mx))
            if hp <= 0:
                continue
            units.append({'uid': f'{viewer_id}:{key}', 'owner': viewer_id,
                          'x': x, 'y': y + HALF_H, 'hp': hp, 'maxHp': mx,
                          'shield': 0, 'card': info['card'], 'star': star,
                          'slowed': False})
        return [{'t': 0.0, 'units': units}]

    # ---- 对外状态 ----------------------------------------------------------
    def _battle_key(self):
        return f'{self.round}:{self.battle_started_at:.3f}'

    def _viewer_battle(self, viewer_id):
        side, frames, events, opp, bye = None, [], [], None, False
        if not viewer_id:
            return side, frames, events, opp, bye
        if viewer_id in self._bye_players:
            bye = True
        for pair in self.pairings:
            if pair['a'] == viewer_id:
                side, opp = 'a', pair['b']
            elif pair['b'] == viewer_id:
                side, opp = 'b', pair['a']
            else:
                continue
            if self.state == 'battle':
                frames = pair.get('frames_view', {}).get(side, [])
                events = pair.get('events_view', {}).get(side, [])
            break
        if self.state == 'battle' and bye:
            frames = self._bye_frames.get(viewer_id, [])
            events = []
        return side, frames, events, opp, bye

    @staticmethod
    def _public_player(cid, p, color):
        return {'id': cid, 'name': p['name'], 'color': color,
                'hp': p['hp'], 'gold': p['gold'], 'level': p['level'],
                'mind': p['mind'], 'reason': p['reason'], 'energy': p['energy'],
                'dead': p['dead'], 'crashed': p.get('crashed', False),
                'ready': bool(p.get('ready', False)),
                'isAi': bool(p.get('isAi', False)),
                'aiLevel': AI_LEVEL_LABELS.get(p.get('aiLevel'), '') if p.get('isAi') else '',
                'lastResult': p['lastResult'],
                'roundWins': p['roundWins'], 'roundLosses': p['roundLosses']}

    def _bond_view(self, viewer_id):
        if not viewer_id or viewer_id not in self.players:
            return []
        cards = []
        for info in self.players[viewer_id]['board'].values():
            c = CARD_BY_ID.get(info['card'])
            if c:
                cards.append(c)
        return bond_status(cards)

    def get_state(self, viewer_id=None, have_chat=-1, since=-1):
        with self.lock:
            if viewer_id:
                self._touch(viewer_id)
            now = time.time()
            # Thin response when the client is already up to date. The heartbeat
            # above still runs and all timer fields stay exact, so the 300ms poll
            # costs a few hundred bytes instead of the whole player/board/shop
            # snapshot. Any version or chat change falls through to the full path.
            if since == self.version and have_chat == self.chat_version:
                return {
                    'minimal': True,
                    'version': self.version,
                    'chatVersion': self.chat_version,
                    'serverNow': now,
                    'state': self.state,
                    'round': self.round,
                    'battleKey': self._battle_key() if self.state == 'battle' else None,
                    'prepEndsAt': self.prep_end if self.state == 'prep' else 0,
                    'battleEndsAt': self.battle_end if self.state == 'battle' else 0,
                    'battleStartedAt': self.battle_started_at if self.state == 'battle' else 0,
                }
            players_out = {}
            for cid, p in self.players.items():
                row = self._public_player(cid, p, self.colors.get(cid, 0))
                if cid == viewer_id:
                    row.update({'board': p['board'], 'bench': p['bench'],
                                'shop': p['shop'], 'ready': p['ready'],
                                'shopRefreshCost': shop_refresh_cost(p.get('shopRefreshes', 0)),
                                'mergeNotice': p.get('mergeNotice')})
                players_out[cid] = row

            side, _frames, _events, opp, bye = self._viewer_battle(viewer_id)
            out = {
                'version': self.version,
                'roomId': self.id,
                'host': self.host,
                'state': self.state,
                'round': self.round,
                'winner': self.winner,
                'viewerId': viewer_id,
                'viewerSide': side,
                'viewerBye': bye,
                'players': players_out,
                'opponentId': opp,
                'battleKey': self._battle_key() if self.state == 'battle' else None,
                'prepEndsAt': self.prep_end if self.state == 'prep' else 0,
                'battleEndsAt': self.battle_end if self.state == 'battle' else 0,
                'battleStartedAt': self.battle_started_at if self.state == 'battle' else 0,
                'serverNow': now,
                'chatVersion': self.chat_version,
                'halfW': HALF_W, 'halfH': HALF_H,
                'battleW': BATTLE_W, 'battleH': BATTLE_H,
                'maxRounds': MAX_ROUNDS, 'maxPlayers': MAX_PLAYERS,
                'maxBoard': MAX_BOARD, 'maxBench': MAX_BENCH,
                'bonds': self._bond_view(viewer_id),
                'bondTiers': list(BOND_TIERS), 'bondEffects': list(BOND_EFFECTS),
            }
            if have_chat != self.chat_version:
                out['chat'] = self.chat
            return out

    def get_battle(self, viewer_id):
        with self.lock:
            if viewer_id:
                self._touch(viewer_id)
            if self.state != 'battle':
                return {'battleKey': None, 'frames': [], 'events': [],
                        'viewerBye': False, 'opponentId': None, 'viewerSide': None}
            side, frames, events, opp, bye = self._viewer_battle(viewer_id)
            return {'battleKey': self._battle_key(), 'frames': frames, 'events': events,
                    'viewerSide': side, 'viewerBye': bye, 'opponentId': opp,
                    'battleStartedAt': self.battle_started_at,
                    'battleEndsAt': self.battle_end}


def find_room_by_client(cid):
    with ROOMS_LOCK:
        for r in ROOMS.values():
            if cid in r.players:
                return r
    return None


def leave_room(cid, rid, penalize=True):
    with ROOMS_LOCK:
        r = ROOMS.get(rid)
        if not r:
            return
    with r.lock:
        in_game = r.state in ('prep', 'battle')
        p = r.players.get(cid)
        was_alive = bool(p) and not p.get('dead')

        if p and penalize and in_game and was_alive:
            update_rating(cid, RATING_QUIT, 'lose', name=p.get('name'))
            p['rated'] = True
            r._sys_chat(f'{p["name"]} 中途退出，-30 Rating')

        if p:
            name = p['name']
            if in_game:
                p['dead'] = True
                p['abandoned'] = True
                p['ready'] = False
                r._sys_chat(f'{name} 离开了对局')
            else:
                del r.players[cid]
                r.colors.pop(cid, None)
                r._sys_chat(f'{name} 离开了房间')

        if not in_game:
            for aid in [c for c, pl in r.players.items() if pl.get('abandoned')]:
                del r.players[aid]
                r.colors.pop(aid, None)

        if r.host == cid:
            cand = [c for c, pl in r.players.items()
                    if not pl.get('abandoned') and not pl.get('isAi')]
            if cand:
                r.host = cand[0]
                r._sys_chat(f'{r.players[r.host]["name"]} 成为新房主')

        r.version += 1
        if in_game:
            r._check_game_over()

        with ROOMS_LOCK:
            humans = [pl for pl in r.players.values()
                      if not pl.get('abandoned') and not pl.get('isAi')]
            if not humans:
                ROOMS.pop(rid, None)


# ============================================================
# 掉线清理 & 房间回收
# ============================================================
def _cleanup_room_locked(r, now, to_remove):
    """在持有 r.lock 的前提下：踢掉线玩家、重选房主、回收空房。"""
    # 1. 心跳超时
    for cid, p in list(r.players.items()):
        if p.get('abandoned'):
            continue
        # AI 是房间内的虚拟玩家，不会发 /api/state 心跳，不能被超时清理。
        if p.get('isAi'):
            continue
        last = p.get('last_seen', now)
        if now - last <= PLAYER_TIMEOUT:
            continue
        in_game = r.state in ('prep', 'battle')
        name = p['name']
        if in_game:
            if not p.get('dead') and not p.get('rated'):
                p['rated'] = True
                update_rating(cid, RATING_QUIT, 'lose', name=name)
            p['dead'] = True
            p['abandoned'] = True
            p['ready'] = False
            r._sys_chat(f'{name} 长时间无响应，已掉线')
        else:
            r.players.pop(cid, None)
            r.colors.pop(cid, None)
            r._sys_chat(f'{name} 长时间无响应，已离开')
        r.version += 1

    # 2. 房主离线 / 不在房间 → 重选
    if r.host not in r.players or r.players[r.host].get('abandoned'):
        cand = [c for c, pl in r.players.items()
                if not pl.get('abandoned') and not pl.get('isAi')]
        if cand:
            r.host = cand[0]
            r._sys_chat(f'{r.players[r.host]["name"]} 成为新房主')
            r.version += 1

    # 3. 对局中掉线后重新判定对局是否结束
    if r.state in ('prep', 'battle'):
        r._check_game_over()

    # 4. 房间回收：没有真人（只剩 AI 的房间没有存在的意义，直接回收）
    humans = [pl for pl in r.players.values()
              if not pl.get('abandoned') and not pl.get('isAi')]
    if not humans:
        to_remove.append(r.id)
        return

    # 5. 已结束房间超时回收
    if r.state == 'ended' and r._ended_at and now - r._ended_at > ROOM_TTL_ENDED:
        to_remove.append(r.id)


def cleanup_rooms():
    now = time.time()
    to_remove = []
    with ROOMS_LOCK:
        rooms = list(ROOMS.values())
    for r in rooms:
        try:
            with r.lock:
                _cleanup_room_locked(r, now, to_remove)
        except Exception as e:
            print(f'!! cleanup error: {e}')
    if to_remove:
        with ROOMS_LOCK:
            for rid in to_remove:
                if ROOMS.pop(rid, None):
                    print(f'[房间回收] {rid}')


# 每房间独立 tick 并发执行，避免一个房间的战斗模拟阻塞其他房间的倒计时
_tick_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='tick')


def _tick_room(r):
    try:
        with r.lock:
            if r.state in ('prep', 'battle'):
                r._tick()
    except Exception as e:
        print(f'!! tick error: {e}')
    finally:
        r._tick_lock.release()


_last_cleanup_at = 0.0


def tick_loop():
    global _last_cleanup_at
    while True:
        time.sleep(0.15)
        now = time.time()
        with ROOMS_LOCK:
            rooms = list(ROOMS.values())
        for r in rooms:
            if not r._tick_lock.acquire(blocking=False):
                continue
            try:
                _tick_pool.submit(_tick_room, r)
            except Exception:
                r._tick_lock.release()
                raise
        if now - _last_cleanup_at >= CLEANUP_INTERVAL:
            _last_cleanup_at = now
            try:
                cleanup_rooms()
            except Exception as e:
                print(f'!! cleanup loop error: {e}')


class QuietThreadingTCPServer(socketserver.ThreadingTCPServer):
    """客户端提前断开（浏览器 abort 轮询 / 关闭标签页）会产生
    ConnectionAbortedError / ConnectionResetError / BrokenPipeError，
    这些属于正常网络噪声，静默忽略；其他异常照常打印便于排查真实 bug。"""
    allow_reuse_address = True
    daemon_threads = True      # Ctrl+C 退出时不再 join 所有请求线程，避免卡住

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            pass

    def _read_json(self):
        try:
            n = int(self.headers.get('Content-Length', 0) or 0)
        except (TypeError, ValueError):
            return {}
        if n <= 0 or n > 65536:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except Exception:
            return {}

    def _serve_file(self, fname, mime):
        if not fname or '\x00' in fname:
            return self._json({'error': 'invalid path'}, 400)
        try:
            fp = (STATIC_DIR / fname).resolve()
        except (OSError, ValueError):
            return self._json({'error': 'invalid path'}, 400)
        if fp != STATIC_DIR and STATIC_DIR not in fp.parents:
            return self._json({'error': 'forbidden'}, 403)
        if not fp.is_file():
            return self._json({'error': f'{fname} not found'}, 404)
        body = fp.read_bytes()
        try:
            self.send_response(200)
            self.send_header('Content-Type', f'{mime}; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            pass

    def do_OPTIONS(self):
        try:
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.end_headers()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            pass

    def do_GET(self):
        try:
            self._handle_get()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:                      # 兜底：不让处理线程静默崩溃
            print(f'!! GET {self.path} 处理异常: {e!r}')
            self._json({'error': '服务器内部错误'}, 500)

    def _handle_get(self):
        p = urlparse(self.path)
        path = p.path
        if path in ('/', '/index.html'):
            return self._serve_file('index.html', 'text/html')
        if path.startswith('/static/'):
            fname = path[len('/static/'):]
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            mime = {'css': 'text/css', 'js': 'application/javascript', 'html': 'text/html',
                    'svg': 'image/svg+xml', 'json': 'application/json'}.get(ext, 'text/plain')
            return self._serve_file(fname, mime)
        if path == '/api/rooms':
            with ROOMS_LOCK:
                rooms = [{'id': r.id, 'host': r.players.get(r.host, {}).get('name', '?'),
                          'players': len(r.players), 'state': r.state,
                          'max': MAX_PLAYERS,
                          'aiCount': sum(1 for p in r.players.values()
                                         if p.get('isAi'))} for r in ROOMS.values()]
            return self._json({'rooms': rooms})
        if path == '/api/state':
            qs = parse_qs(p.query)
            pid = _as_str(qs.get('playerId', [''])[0], 64)
            if not pid:
                return self._json({'error': 'missing playerId'}, 400)
            room = find_room_by_client(pid)
            if not room:
                return self._json({'error': 'not in room'}, 404)
            try:
                have_chat = int(qs.get('haveChat', ['-1'])[0])
            except (ValueError, TypeError, IndexError):
                have_chat = -1
            try:
                since = int(qs.get('since', ['-1'])[0])
            except (ValueError, TypeError, IndexError):
                since = -1
            return self._json(room.get_state(pid, have_chat, since))
        if path == '/api/battle':
            qs = parse_qs(p.query)
            pid = _as_str(qs.get('playerId', [''])[0], 64)
            if not pid:
                return self._json({'error': 'missing playerId'}, 400)
            room = find_room_by_client(pid)
            if not room:
                return self._json({'error': 'not in room'}, 404)
            return self._json(room.get_battle(pid))
        if path == '/api/profile':
            qs = parse_qs(p.query)
            cid = _as_str(qs.get('clientId', [''])[0], 64)
            if not cid:
                return self._json({'error': 'missing clientId'}, 400)
            return self._json(get_profile(cid))
        if path == '/api/cards':
            return self._json({'cards': CARDS, 'traits': TRAITS,
                               'starScale': STAR_SCALE, 'maxStar': MAX_STAR,
                               'bondTiers': list(BOND_TIERS),
                               'bondEffects': list(BOND_EFFECTS),
                               'maxBoard': MAX_BOARD, 'maxBench': MAX_BENCH})
        return self._json({'error': f'not found: {path}'}, 404)

    def do_POST(self):
        try:
            self._handle_post()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:                      # 兜底：不让处理线程静默崩溃
            print(f'!! POST {self.path} 处理异常: {e!r}')
            self._json({'error': '服务器内部错误'}, 500)

    _POST_ROUTES = {
        '/api/rooms': '_api_rooms',
        '/api/join': '_api_join',
        '/api/rejoin': '_api_rejoin',
        '/api/chat': '_api_chat',
        '/api/action': '_api_action',
    }

    def _handle_post(self):
        p = urlparse(self.path)
        path = p.path
        data = self._read_json()
        handler = self._POST_ROUTES.get(path)
        if handler is not None:
            return getattr(self, handler)(data)
        return self._json({'error': f'not found: {path}'}, 404)

    def _api_rooms(self, data):
        cid = _as_str(data.get('clientId'), 64)
        if not cid:
            return self._json({'error': 'missing clientId'}, 400)
        name = _as_str(data.get('name'), 12) or '选手'
        get_profile(cid, name)
        existing = find_room_by_client(cid)
        if existing:
            return self._json({'roomId': existing.id, 'playerId': cid, 'rejoined': True})
        ai_count = _as_int(data.get('aiCount'), 0)
        ai_count = max(0, min(MAX_PLAYERS - 1, ai_count if isinstance(ai_count, int) else 0))
        ai_level = _as_str(data.get('aiLevel'), 16)
        if ai_level not in AI_LEVELS:
            ai_level = 'normal'
        rid = uuid.uuid4().hex[:6]
        room = Room(rid, cid)
        with ROOMS_LOCK:
            ROOMS[rid] = room
        ok, err = room.add_player(cid, name)
        if not ok:
            with ROOMS_LOCK:
                ROOMS.pop(rid, None)
            return self._json({'error': err}, 400)
        added = 0
        for _ in range(ai_count):
            ok_ai, _ai_id = room.add_ai(ai_level)
            if not ok_ai:
                break
            added += 1
        return self._json({'roomId': rid, 'playerId': cid, 'aiCount': added})

    def _api_join(self, data):
        cid = _as_str(data.get('clientId'), 64)
        rid = _as_str(data.get('roomId'), 32)
        name = _as_str(data.get('name'), 12) or '选手'
        if not cid or not rid:
            return self._json({'error': '参数缺失'}, 400)
        get_profile(cid, name)
        with ROOMS_LOCK:
            room = ROOMS.get(rid)
            if not room:
                return self._json({'error': '房间不存在'}, 404)
        if cid in room.players:
            room._touch(cid)
            return self._json({'roomId': rid, 'playerId': cid, 'rejoined': True})
        old = find_room_by_client(cid)
        if old and old.id != rid:
            leave_room(cid, old.id, penalize=True)
        ok, err = room.add_player(cid, name)
        if not ok:
            return self._json({'error': err}, 400)
        return self._json({'roomId': rid, 'playerId': cid})

    def _api_rejoin(self, data):
        cid = _as_str(data.get('clientId'), 64)
        if not cid:
            return self._json({'error': 'missing clientId'}, 400)
        room = find_room_by_client(cid)
        if not room:
            return self._json({'error': '无可用房间'}, 404)
        room._touch(cid)
        return self._json({'roomId': room.id, 'playerId': cid})

    def _api_chat(self, data):
        pid = _as_str(data.get('playerId'), 64)
        text = data.get('text', '')
        if not pid:
            return self._json({'error': 'missing playerId'}, 400)
        room = find_room_by_client(pid)
        if not room:
            return self._json({'error': '不在房间'}, 404)
        ok, err = room.send_chat(pid, text)
        if not ok:
            return self._json({'error': err}, 400)
        return self._json({'ok': True})

    def _api_action(self, data):
        pid = _as_str(data.get('playerId'), 64)
        action = _as_str(data.get('action'), 32)
        if not pid:
            return self._json({'error': 'missing playerId'}, 400)
        room = find_room_by_client(pid)
        if not room:
            return self._json({'error': '不在房间'}, 404)
        if action == 'start':
            ok, err = room.start(pid)
        elif action == 'buy':
            ok, err = room.buy(pid, _as_int(data.get('index'), -1))
        elif action == 'sell':
            src = _as_str(data.get('source'), 16)
            if src == 'bench':
                ok, err = room.sell(pid, src, _as_int(data.get('index'), -1))
            else:
                ok, err = room.sell(pid, src, _as_str(data.get('index'), 16))
        elif action == 'place':
            ok, err = room.place(pid, _as_int(data.get('benchIndex'), -1),
                                 _as_int(data.get('x'), -1), _as_int(data.get('y'), -1))
        elif action == 'retrieve':
            ok, err = room.retrieve(pid, _as_int(data.get('x'), -1),
                                    _as_int(data.get('y'), -1))
        elif action == 'ready':
            ok, err = room.toggle_ready(pid)
        elif action == 'refresh':
            ok, err = room.refresh_shop(pid)
        elif action == 'addAi':
            if pid != room.host:
                ok, err = False, '只有房主可以添加电脑'
            else:
                ok, res = room.add_ai(_as_str(data.get('level'), 16))
                err = None if ok else res
        elif action == 'leave':
            leave_room(pid, room.id, penalize=True)
            return self._json({'ok': True})
        else:
            ok, err = False, f'未知操作 {action}'
        if not ok:
            return self._json({'error': err}, 400)
        return self._json({'ok': True})


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def _flush_quietly():
    """清空标准流缓冲并吞掉异常。

    解释器退出时会自动 flush stdout/stderr；若缓冲区里还有中文输出而底层
    句柄已被宿主 / 管道提前关闭，会打印
    'Exception ignored in: <_io.TextIOWrapper ...>'，窗口看起来像卡住。
    提前把缓冲清空，退出期的自动 flush 就无事可做。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass


def _safe_print(*args, **kwargs):
    """启动期输出：编码失败降级成 ASCII 转义文本，且立即 flush。

    Windows 非中文代码页或标准流被宿主替换时，直接 print 中文会抛
    UnicodeEncodeError；若输出只留在缓冲区，解释器退出时还会在 stdout
    句柄失效后抛 'Exception ignored in' 并让窗口看起来卡住。两层都兜住。
    """
    try:
        print(*args, **kwargs)
        _flush_quietly()
        return
    except (UnicodeEncodeError, OSError, ValueError):
        pass
    try:
        text = kwargs.get('sep', ' ').join(str(a) for a in args)
        print(text.encode('ascii', 'backslashreplace').decode('ascii'))
        _flush_quietly()
    except Exception:
        pass


def _setup_utf8_console():
    """仅统一标准流编码，不改控制台代码页。

    Python 3.6+ 在 Windows 控制台通过 WriteConsoleW 直接写 Unicode，
    与代码页无关，中文无需 chcp 65001 即可显示；强切 65001 反而会带来
    控制台 IO 异常与退出期 flush 挂起。重定向到文件/管道时，
    reconfigure 保证中文以 UTF-8 写出。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def resolve_bind(argv=None):
    """绑定优先级：CLI > 环境变量 OI_CHESS_HOST / OI_CHESS_PORT > 内置默认值。"""
    parser = argparse.ArgumentParser(description='OI-chess LAN server')
    parser.add_argument('--host', default=None, help='bind address (default 0.0.0.0)')
    parser.add_argument('--port', type=int, default=None, help='listen port (default 8080)')
    args, _ = parser.parse_known_args(argv)
    host = args.host or os.environ.get('OI_CHESS_HOST', '').strip() or HOST
    env_port = os.environ.get('OI_CHESS_PORT', '').strip()
    raw = args.port if args.port is not None else (env_port or PORT)
    try:
        port = int(raw)
    except (TypeError, ValueError):
        raise SystemExit('port must be an integer, got: %r' % (raw,))
    if not (1 <= port <= 65535):
        raise SystemExit('port out of range: %s' % port)
    return host, port


def main():
    _setup_utf8_console()
    host, port = resolve_bind()
    STATIC_DIR.mkdir(exist_ok=True)
    load_profiles()
    missing = [f for f in ['index.html', 'style.css', 'script.js']
               if not (STATIC_DIR / f).exists()]
    if missing:
        _safe_print('!! 缺少静态文件:', missing)
        if sys.stdin.isatty():
            _safe_print('按回车退出...')
            input()
        return 1
    _safe_print(f'已加载 {len(PROFILES)} 名玩家档案')
    threading.Thread(target=tick_loop, daemon=True).start()
    try:
        with QuietThreadingTCPServer((host, port), Handler) as httpd:
            ip = get_local_ip()
            _safe_print('=' * 50)
            _safe_print('  OI chess · 局域网服务器')
            _safe_print(f'  本机:   http://127.0.0.1:{port}')
            _safe_print(f'  局域网: http://{ip}:{port}')
            _safe_print('=' * 50)
            httpd.serve_forever()
    except OSError as e:
        _safe_print(f'!! 端口 {port} 被占用或无法绑定: {e}')
        _safe_print('   换端口重试: python3 server.py --port 8123')
        _safe_print('   或设置环境变量 OI_CHESS_PORT=8123')
        return 1
    except KeyboardInterrupt:
        _safe_print('\n已停止')
    return 0


if __name__ == '__main__':
    try:
        _rc = main()
    finally:
        _flush_quietly()
    sys.exit(_rc)
