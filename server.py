# -*- coding: utf-8 -*-
import http.server, socketserver, json, threading, uuid, random, socket, sys, time, math
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

HOST = '0.0.0.0'
PORT = 8080
STATIC_DIR = (Path(__file__).parent / 'static').resolve()
DATA_DIR = (Path(__file__).parent / 'data').resolve()
DATA_FILE = DATA_DIR / 'players.json'

MAX_PLAYERS = 8
MAX_BENCH = 10             # \u5907\u6218\u5e2d\u4e0a\u9650
MAX_BOARD = 20             # \u573a\u4e0a\u68cb\u5b50\u4e0a\u9650
HALF_W, HALF_H = 8, 4
BATTLE_W, BATTLE_H = 8, 8
PREP_TIME = 30.0
BATTLE_TIME = 30.0
PAIR_LEAD_TIME = 3.0
MAX_ROUNDS = 10
TICK_SEC = 0.5

# ---- \u6389\u7ebf / \u56de\u6536\u53c2\u6570 -------------------------------------------------------
PLAYER_TIMEOUT = 120.0     # \u8d85\u8fc7\u8be5\u65f6\u957f\u65e0\u5fc3\u8df3\u89c6\u4e3a\u6389\u7ebf
ROOM_TTL_ENDED = 60.0    # \u5df2\u7ed3\u675f\u623f\u95f4\u4fdd\u7559\u65f6\u957f\uff08\u79d2\uff09
CLEANUP_INTERVAL = 5.0    # \u5fc3\u8df3\u6e05\u7406\u5468\u671f\uff08\u79d2\uff09

ATK_CD = 2.0
ATK_CD_SLOWED = 3.0
SLOW_DURATION = 3.0        # \u51cf\u901f\u6301\u7eed\u65f6\u95f4\uff08\u65e7\u7248\u662f\u6574\u573a\u6c38\u4e45\uff0c\u7b49\u4ef7\u4e8e\u6c38\u4e45\u524a\u5f31\u654c\u65b9 33% \u8f93\u51fa\uff09
SKILL_CD = 6.0
DMG_MULT = 0.5 * 2.0 / 3.0

# ---- \u5fc3\u6001\uff1a\u51b3\u5b9a\u4f24\u5bb3\u8f93\u51fa\u4e0e\u627f\u4f24 ----------------------------------------------
MIND_HIGH = 70
MIND_LOW = 30
MIND_DMG_UP = 1.10
MIND_DMG_DOWN = 0.50
MIND_DMG_TAKEN = 1.10
MIND_MAX = 100

REASON_CRASH_MIND = 8

SHIELD_CAP_RATIO = 0.5
AOE_DEBUFF_RATIO = 0.35     # BFS\uff1a\u5168\u573a\u4f24\u5bb3\u500d\u7387\uff08\u51cf\u901f\u6548\u679c\u89c1 _use_skill\uff09
SHIELD_ON_LOW_ATK = 0.5    # \u526a\u679d\uff1a\u5355\u6b21\u4f24\u5bb3\u4f4e\u4e8e\u81ea\u8eab\u653b\u51fb\u529b\u7684\u8fd9\u4e2a\u6bd4\u4f8b\u624d\u89e6\u53d1
SHIELD_ON_LOW_CONVERT = 0.5  # \u89e6\u53d1\u65f6\u628a\u4f24\u5bb3\u7684\u8fd9\u4e2a\u6bd4\u4f8b\u8f6c\u5316\u4e3a\u62a4\u76fe\uff08\u5176\u4f59\u4ecd\u7136\u627f\u53d7\uff09
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
# SPFA\uff1a\u653b\u901f\u3001\u4f24\u5bb3\u500d\u7387\uff1b\u6bcf\u6b21\u666e\u653b\u540e\u72ec\u7acb\u5224\u5b9a\u5361\u987f\u3002
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
BOND_EFFECTS = ['\u653b\u51fb +6%', '\u751f\u547d +8%', '\u627f\u4f24 -6%']  # exposed to the client

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
    ('linear_dp', '\u7ebf\u6027 DP', 1, '\u666e\u53ca', 0.75, 'dynamic_programming', 41, 401, 4, 4, 'line',
     '\u6cbf\u884c/\u5217\u76f4\u7ebf\u653b\u51fb',
     '\u6280\u80fd\uff1a\u5bf9\u5c04\u7a0b\u5185\u76ee\u6807\u6240\u5728\u884c\u6216\u5217\u4e2d\u654c\u4eba\u66f4\u591a\u7684\u4e00\u6761\u7ebf\u9020\u6210 50% \u4f24\u5bb3'),
    ('tree_array', '\u6811\u72b6\u6570\u7ec4', 1, '\u666e\u53ca', 0.75, 'data_structure', 37, 364, 4, 4, 'stack_ally',
     '\u53cb\u519b\u884c\u52a8\u53e0\u5c42',
     '\u88ab\u52a8\uff1a\u6bcf\u6b21\u53cb\u519b\u666e\u653b\u6216\u65bd\u6cd5 +1 \u5c42\uff0c\u6bcf\u5c42 +8% \u666e\u653b\u4f24\u5bb3\uff08\u4e0a\u9650 6 \u5c42\uff09'),
    ('monotonic_stack', '\u5355\u8c03\u6808', 1, '\u666e\u53ca', 0.75, 'data_structure', 38, 371, 4, 4, 'charge_burst',
     '\u79ef\u7d2f\u540e\u7206\u53d1',
     '\u88ab\u52a8\uff1a\u6bcf\u7b2c 4 \u6b21\u666e\u653b\u9020\u6210 3 \u500d\u4f24\u5bb3'),
    ('greedy', '\u8d2a\u5fc3', 1, '\u666e\u53ca', 0.75, 'greedy', 46, 456, 4, 4, 'finish_weak',
     '\u6253\u6700\u6613\u51fb\u6740\u76ee\u6807',
     '\u88ab\u52a8\uff1a\u4f18\u5148\u653b\u51fb\u5c04\u7a0b\u5185\u751f\u547d\u6700\u4f4e\u7684\u654c\u4eba'),
    ('sort', '\u6392\u5e8f', 1, '\u666e\u53ca', 0.75, 'greedy', 40, 404, 4, 4, 'sort_line',
     '\u91cd\u6392\u4e00\u884c\u6216\u4e00\u5217',
     '\u6280\u80fd\uff1a\u6253\u4e71\u5c04\u7a0b\u5185\u540c\u4e00\u884c\u654c\u4eba\u7684\u7ad9\u4f4d\uff0c\u5e76\u9020\u6210 30% \u4f24\u5bb3'),
    ('dfs', 'DFS', 1, '\u666e\u53ca', 0.75, 'search', 44, 438, 4, 4, 'chain_kill',
     '\u4e00\u8def\u6df1\u5165\uff0c\u51fb\u6740\u7eed\u884c',
     '\u88ab\u52a8\uff1a\u51fb\u6740\u540e\u7acb\u523b\u8ffd\u52a0\u4e00\u6b21\u653b\u51fb\uff0c\u672c\u573a\u6700\u591a\u8ffd\u52a0 3 \u6b21'),
    ('diff', '\u5dee\u5206', 1, '\u666e\u53ca', 0.75, 'diff', 35, 335, 4, 4, 'delayed_line',
     '\u5ef6\u8fdf\u6574\u884c\u4f24\u5bb3',
     '\u6280\u80fd\uff1a\u7ed9\u5c04\u7a0b\u5185\u6574\u884c\u654c\u4eba\u6302\u5ef6\u8fdf\u4f24\u5bb3\uff0c2 \u79d2\u540e\u7ed3\u7b97 150%'),
    ('xor', '\u5f02\u6216', 1, '\u666e\u53ca', 0.75, 'bitwise', 28, 280, 4, 4, 'swap_stats',
     '\u4ea4\u6362\u654c\u4eba\u5c5e\u6027',
     '\u6280\u80fd\uff1a\u4e0e\u5c04\u7a0b\u5185\u653b\u51fb\u6700\u9ad8\u7684\u654c\u4eba\u4ea4\u6362\u653b\u51fb\u529b\uff0c\u6301\u7eed 6 \u79d2'),
    ('gcd', 'gcd', 1, '\u666e\u53ca', 0.75, 'number_theory', 44, 437, 4, 4, 'link_ally',
     '\u94fe\u63a5\u76f8\u90bb\u53cb\u519b',
     '\u88ab\u52a8\uff1a\u76f8\u90bb\u53cb\u519b\u53d7\u4f24\u65f6\uff0c\u81ea\u8eab\u5206\u62c5 30%'),
    ('bfs', 'BFS', 2, '\u666e\u53ca', 0.75, 'search', 50, 500, 6, 9, 'aoe_debuff',
     '\u5168\u573a\u6269\u6563\uff0c\u9650\u65f6\u51cf\u901f',
     '\u6280\u80fd\uff1a\u5168\u573a\u654c\u4eba\u53d7 35% \u4f24\u5bb3\u5e76\u51cf\u901f 3 \u79d2\uff08\u666e\u653b\u51c6\u5907\u901f\u5ea6\u964d\u4e3a 2/3\uff09'),
    ('pigeonhole', '\u9e3d\u5de2\u539f\u7406', 2, '\u666e\u53ca', 0.75, 'combinatorics', 75, 727, 6, 9, 'crowd_crit',
     '\u5bc6\u96c6\u5fc5\u66b4\u51fb',
     '\u88ab\u52a8\uff1a\u76ee\u6807\u5468\u56f4 3\xd73 \u5185\u9664\u76ee\u6807\u5916\u654c\u4eba \u22653 \u65f6\uff0c\u672c\u6b21\u4f24\u5bb3\u7ffb\u500d'),
    ('prime_sieve', '\u8d28\u6570\u7b5b', 2, '\u666e\u53ca', 0.75, 'math', 64, 636, 6, 9, 'prime_round',
     '\u8d28\u6570\u56de\u5408\u7206\u53d1',
     '\u88ab\u52a8\uff1a\u8d28\u6570\u56de\u5408\u4f24\u5bb3 \xd71.8'),
    ('mod_op', '\u6a21\u8fd0\u7b97', 2, '\u666e\u53ca', 0.75, 'math', 62, 619, 6, 9, 'every_n',
     '\u6bcf\u7b2cN\u6b21\u653b\u51fb\u89e6\u53d1',
     '\u88ab\u52a8\uff1a\u6bcf\u7b2c 3 \u6b21\u666e\u653b\u9020\u6210 2.5 \u500d\u4f24\u5bb3'),
    ('shift', '\u79fb\u4f4d', 2, '\u666e\u53ca', 0.75, 'bitwise', 76, 754, 6, 9, 'shift_stats',
     '\u653b\u51fb\u7ffb\u500d\u751f\u547d\u51cf\u534a',
     '\u88ab\u52a8\uff1a\u5165\u573a\u653b\u51fb \xd72\u3001\u751f\u547d\u4e0a\u9650 \xd70.5'),
    ('range_dp', '\u533a\u95f4 DP', 2, '\u63d0\u9ad8', 1.05, 'dynamic_programming', 66, 647, 6, 9, 'range_aoe',
     '\u8fde\u7eed\u533a\u95f4\u4f24\u5bb3',
     '\u6280\u80fd\uff1a\u5bf9\u76ee\u6807\u53ca\u5176\u5de6\u53f3\u76f8\u90bb\u683c\u9020\u6210 80% \u4f24\u5bb3'),
    ('segment_tree', '\u7ebf\u6bb5\u6811', 2, '\u63d0\u9ad8', 1.05, 'data_structure', 64, 632, 6, 9, 'seg_query',
     '\u533a\u95f4\u67e5\u8be2\uff0c\u61d2\u6807\u8bb0\u4e0b\u653e',
     '\u88ab\u52a8\uff1a\u6bcf\u7b2c 4 \u6b21\u666e\u653b\u989d\u5916\u5bf9\u5c04\u7a0b\u5185\u5168\u4f53\u654c\u4eba\u9020\u6210 60% \u4f24\u5bb3'),
    ('sqrt_block', '\u5206\u5757', 2, '\u63d0\u9ad8', 1.05, 'data_structure', 67, 655, 6, 9, 'block_aoe',
     '2\xd72 \u5757\u63a7\u5236',
     '\u6280\u80fd\uff1a\u5bf9\u5c04\u7a0b\u5185\u76ee\u6807\u6240\u5728\u7684\u56fa\u5b9a 2\xd72 \u68cb\u76d8\u5206\u5757\u9020\u6210 70% \u4f24\u5bb3'),
    ('pruning', '\u526a\u679d', 2, '\u63d0\u9ad8', 1.05, 'search', 55, 539, 6, 9, 'shield_on_low',
     '\u5f31\u653b\u51fb\u8f6c\u62a4\u76fe',
     '\u88ab\u52a8\uff1a\u5355\u6b21\u4f24\u5bb3\u4f4e\u4e8e\u81ea\u8eab\u653b\u51fb\u529b 50% \u65f6\uff0c\u51cf\u514d 50% \u5e76\u8f6c\u5316\u4e3a\u62a4\u76fe'),
    ('ids', '\u8fed\u4ee3\u52a0\u6df1', 2, '\u63d0\u9ad8', 1.05, 'search', 76, 750, 6, 9, 'grow_range',
     '\u8303\u56f4\u9010\u56de\u5408+1',
     '\u88ab\u52a8\uff1a\u7b2c 1 \u56de\u5408\u4f7f\u7528\u57fa\u7840\u5c04\u7a0b\uff0c\u6b64\u540e\u6bcf\u56de\u5408\u5c04\u7a0b +1'),
    ('merge_sort', '\u5f52\u5e76\u6392\u5e8f', 2, '\u63d0\u9ad8', 1.05, 'divide_conquer', 74, 739, 6, 9, 'merge_ally',
     '\u5408\u5e76\u76f8\u90bb\u5c5e\u6027',
     '\u88ab\u52a8\uff1a\u5165\u573a\u65f6\u4e0e\u4e0a\u4e0b\u5de6\u53f3\u76f8\u90bb\u53cb\u519b\u8fde\u6210\u7684\u5206\u7ec4\u5747\u5206\u5f53\u524d\u751f\u547d\uff0c\u4e0d\u8d85\u5404\u81ea\u4e0a\u9650'),
    ('quick_sort', '\u5feb\u901f\u6392\u5e8f', 2, '\u63d0\u9ad8', 1.05, 'divide_conquer', 60, 590, 6, 9, 'partition',
     '\u6309\u653b\u51fb\u5206\u533a',
     '\u6280\u80fd\uff1a\u5bf9\u5c04\u7a0b\u5185\u653b\u51fb\u529b\u6700\u9ad8\u7684\u4e00\u534a\u654c\u4eba\u9020\u6210 100% \u4f24\u5bb3'),
    ('divide', '\u5206\u6cbb', 2, '\u63d0\u9ad8', 1.05, 'divide_conquer', 57, 558, 6, 9, 'divide_conquer',
     '\u5206\u6bb5\u5904\u7406\u518d\u5408\u5e76',
     '\u6280\u80fd\uff1a\u5c04\u7a0b\u5185\u5168\u4f53\u53d7 50% \u4f24\u5bb3\uff0c\u82e5\u65e0\u4eba\u9635\u4ea1\u518d\u8865\u4e00\u6b21 100%'),
    ('inverse', '\u9006\u5143', 2, '\u63d0\u9ad8', 1.05, 'number_theory', 63, 626, 6, 9, 'thorns',
     '\u53d7\u51fb\u53cd\u4f24',
     '\u88ab\u52a8\uff1a\u53d7\u5230\u666e\u653b\u65f6\u53cd\u5f39 35% \u4f24\u5bb3'),
    ('bitmask_dp', '\u72b6\u538b DP', 3, '\u63d0\u9ad8', 1.05, 'dynamic_programming', 79, 800, 9, 16, 'compress_line',
     '\u538b\u7f29\u6574\u884c\u53cb\u519b',
     '\u6280\u80fd\uff1a\u6c47\u603b\u81ea\u8eab\u4e0e\u540c\u884c\u53cb\u519b\u653b\u51fb\u529b\uff0c\u5bf9\u5c04\u7a0b\u5185\u76ee\u6807\u6240\u5728\u884c\u654c\u4eba\u9020\u6210\u7b49\u503c\u4f24\u5bb3'),
    ('monotonic_queue', '\u5355\u8c03\u961f\u5217', 3, '\u63d0\u9ad8', 1.05, 'data_structure', 111, 1115, 9, 16, 'sliding_max',
     '\u6ed1\u7a97\u653b\u51fb\u6700\u5f3a\u8005',
     '\u88ab\u52a8\uff1a\u4f18\u5148\u653b\u51fb\u5c04\u7a0b\u5185\u653b\u51fb\u529b\u6700\u9ad8\u7684\u654c\u4eba'),
    ('a_star', 'A*', 3, '\u63d0\u9ad8', 1.05, 'search', 110, 1100, 9, 16, 'heuristic',
     '\u542f\u53d1\u5f0f\u4f30\u4ef7 f=g+h',
     '\u88ab\u52a8\uff1a\u6309\u300c\u8ddd\u79bb + \u5269\u4f59\u751f\u547d/\u653b\u51fb\u300d\u9009\u4f30\u4ef7\u6700\u4f4e\u7684\u76ee\u6807\uff0c\u5bf9\u5176\u4f24\u5bb3 \u00d71.25'),
    ('bidirectional', '\u53cc\u5411\u641c\u7d22', 3, '\u63d0\u9ad8', 1.05, 'search', 86, 840, 9, 16, 'pincer',
     '\u4e24\u7aef\u5939\u51fb',
     '\u6280\u80fd\uff1a\u5bf9\u5c04\u7a0b\u5185\u6700\u8fd1\u4e0e\u6700\u8fdc\u7684\u654c\u4eba\u5404\u9020\u6210 120% \u4f24\u5bb3'),
    ('fermat', '\u8d39\u9a6c\u5c0f\u5b9a\u7406', 3, '\u63d0\u9ad8', 1.05, 'number_theory', 96, 954, 9, 16, 'mod_cycle',
     '\u6a21\u5e42\u5468\u671f\uff0c\u5f52\u96f6\u7206\u53d1',
     '\u88ab\u52a8\uff1a7 \u51fb\u4e3a\u4e00\u4e2a\u6a21\u5468\u671f\uff0c\u500d\u7387\u7531 1.3 \u9010\u51fb\u964d\u5230 0.8\uff0c\u7b2c 7 \u51fb \u00d72.0'),
    ('expectation', '\u671f\u671b', 3, '\u63d0\u9ad8', 1.05, 'probability', 98, 970, 9, 16, 'expectation',
     '\u968f\u673a\u8f6c\u56fa\u5b9a',
     '\u88ab\u52a8\uff1a\u666e\u653b\u4f24\u5bb3\u6052\u5b9a \xd71.25'),
    ('sweep_line', '\u626b\u63cf\u7ebf', 3, '\u63d0\u9ad8', 1.05, 'geometry', 94, 920, 9, 16, 'sweep',
     '\u7ebf\u4e0a\u9012\u589e\u4f24\u5bb3',
     '\u6280\u80fd\uff1a\u5c04\u7a0b\u5185\u76ee\u6807\u540c\u884c\u81f3\u591a 3 \u540d\u654c\u4eba\u6309\u8ddd\u79bb\u7531\u8fd1\u5230\u8fdc\uff0c\u53d7 60%/90%/120% \u4f24\u5bb3'),
    ('cdq', 'CDQ \u5206\u6cbb', 3, '\u7701\u9009', 1.25, 'divide_conquer', 96, 961, 9, 16, 'cdq',
     '\u524d\u5f31\u540e\u7206',
     '\u88ab\u52a8\uff1a\u6218\u6597\u524d 10 \u79d2\u4f24\u5bb3 \xd70.6\uff0c\u4e4b\u540e \xd71.8'),
    ('spfa', 'SPFA', 3, '\u63d0\u9ad8', 1.05, 'search', 120, 1000, 9, 16, 'spfa_stall',
     '\u5e73\u65f6\u8dd1\u5f97\u98de\u5feb\uff0c\u9047\u5230\u6570\u636e\u5c31\u5361\u4e86',
     '\u88ab\u52a8\uff1a\u653b\u901f \xd71.5\uff0c\u666e\u653b\u4f24\u5bb3 \xd71.2\uff1b\u6bcf\u6b21\u666e\u653b\u540e\u6709 20% \u6982\u7387\u300c\u5361\u4e86\u300d\uff0c\u4e0b\u4e00\u6b21\u666e\u653b\u989d\u5916\u5ef6\u8fdf 4 \u79d2'),
    ('o2', 'O2 \u4f18\u5316', 3, '\u63d0\u9ad8', 1.05, 'optimization', 0, 280, 9, 16, 'o2_aura',
     '\u81ea\u5df1\u4e0d\u8dd1\uff0c\u8ba9\u961f\u53cb\u8dd1\u5f97\u66f4\u5feb',
     '\u88ab\u52a8\uff1a\u65e0\u6cd5\u653b\u51fb\uff0c\u539f\u5730\u4e3a\u5468\u56f4\u516b\u683c\u53cb\u519b\u63d0\u4f9b\u653b\u901f \xd72\uff1b\u540c\u540d\u5149\u73af\u4e0d\u53e0\u52a0\uff0c\u79bb\u5f00\u8303\u56f4\u6216\u81ea\u8eab\u9635\u4ea1\u540e\u5931\u6548'),
    ('genetic', '\u9057\u4f20\u7b97\u6cd5', 4, '\u7701\u9009', 1.25, 'search', 152, 1510, 13, 25, 'genetic',
     '\u7ee7\u627f\u5e76\u53d8\u5f02',
     '\u88ab\u52a8\uff1a\u6bcf\u6b21\u51fb\u6740\u6c38\u4e45 +15% \u653b\u51fb\uff08\u6700\u591a 3 \u5c42\uff09'),
    ('matrix_pow', '\u77e9\u9635\u5feb\u901f\u5e42', 5, '\u7701\u9009', 1.25, 'math', 155, 1545, 15, 31, 'matrix_pow',
     '\u653b\u51fb\xd71.5\uff0c\u751f\u547d-10%',
     '\u88ab\u52a8\uff1a\u5165\u573a\u653b\u51fb \xd71.5\u3001\u751f\u547d\u4e0a\u9650 \xd70.9\uff1b\u6bcf 6 \u79d2\u653b\u51fb \xd71.2\uff08\u6700\u591a 3 \u5c42\uff09'),
    ('two_pointers', '\u53cc\u6307\u9488', 1, '\u666e\u901a', 0.75, 'greedy', 42, 410, 4, 4, 'pierce',
     '\u8d2f\u7a7f\u4e00\u7ebf',
     '\u88ab\u52a8\uff1a\u666e\u653b\u547d\u4e2d\u540e\uff0c\u5bf9\u76ee\u6807\u6b63\u540e\u65b9\u540c\u5217\u76f8\u90bb\u7684\u654c\u4eba\u8ffd\u52a0 50% \u4f24\u5bb3'),
    ('prefix_sum', '\u524d\u7f00\u548c', 1, '\u666e\u901a', 0.75, 'diff', 39, 392, 4, 4, 'prefix_growth',
     '\u524d\u7f00\u7d2f\u52a0\uff0c\u8d8a\u6218\u8d8a\u5f3a',
     '\u88ab\u52a8\uff1a\u6bcf\u6b21\u666e\u653b\u4f7f\u4f24\u5bb3 +10%\uff08\u6700\u591a 6 \u5c42\uff09\uff0c\u540c\u4e00\u573a\u6218\u6597\u6301\u7eed\u7d2f\u79ef'),
    ('huffman', '\u54c8\u592b\u66fc\u7f16\u7801', 1, '\u666e\u901a', 0.75, 'greedy', 40, 400, 4, 4, 'lifesteal',
     '\u5e26\u6743\u8def\u5f84\u56de\u8840',
     '\u88ab\u52a8\uff1a\u666e\u653b\u9020\u6210\u4f24\u5bb3\u540e\uff0c\u56de\u590d\u8be5\u6b21\u5b9e\u9645\u4f24\u5bb3 30% \u7684\u751f\u547d\uff08\u4e0d\u8d85\u8fc7\u4e0a\u9650\uff09'),
    ('topo_sort', '\u62d3\u6251\u6392\u5e8f', 2, '\u666e\u901a', 0.75, 'graph_theory', 58, 575, 6, 9, 'freeze',
     '\u51bb\u7ed3\u4f9d\u8d56\u73af',
     '\u6280\u80fd\uff1a\u5c04\u7a0b\u5185\u5168\u4f53\u654c\u4eba\u53d7 40% \u4f24\u5bb3\u5e76\u505c\u653b 2 \u79d2'),
    ('kmp', 'KMP', 2, '\u63d0\u9ad8', 1.05, 'string', 66, 650, 6, 9, 'kmp_next',
     '\u5931\u914d\u4e0d\u56de\u9000\uff0cnext \u8868\u8df3\u8f6c',
     '\u88ab\u52a8\uff1a\u672a\u51fb\u6740\u76ee\u6807\u65f6\u4e0b\u6b21\u4f24\u5bb3 +10%\uff08\u6700\u591a 5 \u5c42\uff09\uff0c\u51fb\u6740\u540e\u6e05\u96f6\u91cd\u6765'),
    ('prim', '\u6700\u5c0f\u751f\u6210\u6811', 2, '\u63d0\u9ad8', 1.05, 'graph_theory', 63, 628, 6, 9, 'mst_link',
     '\u8fde\u8fb9\u6210\u7f51\uff0c\u5171\u62c5\u51b2\u51fb',
     '\u88ab\u52a8\uff1a\u5165\u573a\u65f6\u6bcf\u6709\u4e00\u540d\u6b63\u4ea4\u76f8\u90bb\u53cb\u519b\uff0c\u51cf\u4f24 6%\uff08\u6700\u591a 4 \u8fb9 / 24%\uff09'),
    ('flood_fill', '\u6cdb\u6d2a\u586b\u5145', 2, '\u63d0\u9ad8', 1.05, 'search', 62, 615, 6, 9, 'splash',
     '\u56db\u90bb\u6269\u6563',
     '\u88ab\u52a8\uff1a\u666e\u653b\u65f6\uff0c\u5bf9\u76ee\u6807\u4e0a\u4e0b\u5de6\u53f3\u76f8\u90bb\u7684\u654c\u4eba\u5404\u9020\u6210 35% \u4f24\u5bb3'),
    ('ac_automaton', 'AC \u81ea\u52a8\u673a', 3, '\u63d0\u9ad8', 1.05, 'string', 92, 905, 9, 16, 'multi_match',
     'fail \u94fe\uff0c\u4e00\u6b21\u626b\u63cf\u591a\u547d\u4e2d',
     '\u88ab\u52a8\uff1a\u666e\u653b\u540e\u5bf9\u5c04\u7a0b\u5185\u6240\u6709\u540c\u540d\u654c\u4eba\u5404\u8ffd\u52a0 30% \u4f24\u5bb3'),
    ('tarjan', '\u5f3a\u8fde\u901a\u5206\u91cf', 3, '\u63d0\u9ad8', 1.05, 'graph_theory', 95, 940, 9, 16, 'scc_mark',
     '\u73af\u5185\u4e92\u76f8\u6807\u8bb0',
     '\u88ab\u52a8\uff1a\u666e\u653b\u7ed9\u76ee\u6807\u53e0\u52a0 1 \u5c42\u6807\u8bb0\uff0c\u6bcf\u5c42\u4f7f\u5176\u627f\u53d7\u4f24\u5bb3 +8%\uff08\u6700\u591a 3 \u5c42\uff09'),
    ('minimax', '\u6781\u5c0f\u5316\u6781\u5927', 3, '\u63d0\u9ad8', 1.05, 'game_theory', 105, 1030, 9, 16, 'rampage',
     '\u52a3\u52bf\u65f6\u640f\u5230\u5e95',
     '\u88ab\u52a8\uff1a\u81ea\u8eab\u751f\u547d\u4f4e\u4e8e\u4e0a\u9650 50% \u65f6\uff0c\u653b\u51fb \xd71.6'),
    ('suffix_array', '\u540e\u7f00\u6570\u7ec4', 3, '\u63d0\u9ad8', 1.05, 'string', 99, 980, 9, 16, 'lcp_chain',
     '\u6700\u957f\u516c\u5171\u524d\u7f00',
     '\u88ab\u52a8\uff1a\u8fde\u7eed\u653b\u51fb\u540c\u540d\u654c\u4eba\u65f6\u4f24\u5bb3 \u00d71.5\uff0c\u5207\u6362\u76ee\u6807\u65f6 \u00d70.8'),
    ('splay', '\u4f38\u5c55\u6811', 4, '\u7701\u9009', 1.25, 'data_structure', 148, 1480, 13, 25, 'splay_rotate',
     '\u8bbf\u95ee\u5373\u65cb\u6839\uff0c\u644a\u8fd8\u4ee3\u4ef7',
     '\u88ab\u52a8\uff1a\u6bcf\u6b21\u666e\u653b +7% \u4f24\u5bb3\uff08\u6700\u591a 6 \u5c42\uff09\uff0c\u4f46\u6bcf\u6b21\u53d7\u4f24\u635f\u5931\u4e00\u534a\u5c42\u6570'),
    ('network_flow', '\u7f51\u7edc\u6d41', 4, '\u7701\u9009', 1.25, 'graph_theory', 150, 1495, 13, 25, 'min_cut',
     '\u6700\u5c0f\u5272\uff0c\u5bb9\u91cf\u74f6\u9888',
     '\u6280\u80fd\uff1a\u5c04\u7a0b\u5185\u5168\u4f53\u53d7 35% \u4f24\u5bb3\uff08\u654c\u4eba\u8d8a\u591a\u5355\u4f53\u8d8a\u4f4e\uff09\uff0c\u8840\u91cf\u6700\u9ad8\u8005\u989d\u5916 60%'),
    ('fft', '\u5feb\u901f\u5085\u91cc\u53f6\u53d8\u6362', 5, '\u7701\u9009', 1.25, 'math', 153, 1530, 15, 31, 'fft_butterfly',
     '\u8776\u5f62\u8fd0\u7b97\uff0c\u5947\u5076\u76f8\u62b5',
     '\u88ab\u52a8\uff1a\u5947\u6570\u6b21\u666e\u653b \u00d70.75\u3001\u5076\u6570\u6b21 \u00d71.7\uff1b\u9ad8\u9762\u677f\u7684\u4ee3\u4ef7\u662f\u8f93\u51fa\u6781\u4e0d\u7a33\u5b9a'),
    ('suffix_automaton', '\u540e\u7f00\u81ea\u52a8\u673a', 5, '\u7701\u9009', 1.25, 'string', 156, 1550, 15, 31, 'sam_compress',
     '\u72b6\u6001\u538b\u7f29\uff0c\u4ee5\u8840\u6362\u653b',
     '\u88ab\u52a8\uff1a\u6bcf\u540d\u540c\u540d\u53cb\u519b\u4f7f\u653b\u51fb +15%\uff08\u542b\u81ea\u5df1\uff09\uff1b\u5408\u5e76\u72b6\u6001\u4f1a\u6324\u5360\u751f\u547d\u4e0a\u9650 -8%\uff08\u72ec\u82d7\u4e0d\u6263\uff0c\u6700\u591a 5 \u5c42\uff09'),
]

RANGE_BY_COST = {1: 4, 2: 4, 3: 5, 4: 6, 5: 8}

ACTIVE_SKILLS = frozenset({
    'line', 'multi', 'aoe', 'aoe_debuff', 'block_aoe', 'range_aoe',
    'delayed_line', 'swap_stats', 'sort_line', 'compress_line',
    'pincer', 'partition', 'divide_conquer', 'sweep', 'freeze', 'min_cut',
})

# \u5546\u5e97\u5237\u65b0\uff1a\u6bcf\u8f6e\u7b2c\u4e00\u6b21\u514d\u8d39\uff0c\u7b2c\u4e8c\u6b21\u8d77\u6309\u57fa\u7840\u4ef7\u683c\u9012\u589e\u3002
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
CARD_ROLES = {'linear_dp': ('\u7ebf\u6027\u7fa4\u653b', '\u4e2d\u6392', '\u8ba9\u76ee\u6807\u884c\u6216\u5217\u805a\u96c6\uff0c\u6280\u80fd\u6309\u5c04\u7a0b\u7b5b\u9009\u3002'), 'tree_array': ('\u56e2\u961f\u6210\u957f', '\u4e2d\u540e\u6392', '\u53cb\u519b\u6bcf\u6b21\u666e\u653b\u6216\u65bd\u6cd5\u52a0\u5c42\uff0c\u9002\u5408\u884c\u52a8\u5bc6\u96c6\u7684\u9635\u5bb9\u3002'), 'monotonic_stack': ('\u5468\u671f\u7206\u53d1', '\u4e2d\u6392', '\u6bcf\u56db\u51fb\u7206\u53d1\uff0c\u907f\u514d\u8f93\u51fa\u4f4d\u8fc7\u65e9\u9635\u4ea1\u3002'), 'greedy': ('\u4f4e\u8d39\u6536\u5272', '\u4e2d\u6392', '\u4f18\u5148\u5c04\u7a0b\u5185\u6b8b\u8840\uff0c\u4e0d\u4f1a\u4e3a\u8fdc\u5904\u6b8b\u8840\u653e\u5f03\u5f53\u524d\u76ee\u6807\u3002'), 'sort': ('\u91cd\u6392\u63a7\u573a', '\u4e2d\u6392', '\u6270\u4e71\u5c04\u7a0b\u5185\u540c\u884c\u7ad9\u4f4d\uff0c\u4f24\u5bb3\u4e0d\u662f\u4e3b\u8981\u4ef7\u503c\u3002'), 'dfs': ('\u8fde\u9501\u6536\u5272', '\u4e2d\u6392', '\u51fb\u6740\u540e\u7acb\u5373\u7eed\u653b\uff0c\u672c\u573a\u6700\u591a\u8ffd\u52a0\u4e09\u6b21\u3002'), 'diff': ('\u5ef6\u65f6\u7fa4\u653b', '\u540e\u6392', '\u4f24\u5bb3\u5728\u6807\u8bb0\u4e24\u79d2\u540e\u7ed3\u7b97\uff0c\u4fdd\u62a4\u65bd\u6cd5\u8005\u4e89\u53d6\u591a\u6b21\u6807\u8bb0\u3002'), 'xor': ('\u9ad8\u653b\u53cd\u5236', '\u4fdd\u62a4\u4f4d', '\u4ea4\u6362\u5c04\u7a0b\u5185\u6700\u9ad8\u653b\u51fb\uff0c\u9002\u5408\u9488\u5bf9\u9ad8\u8d39\u6838\u5fc3\u3002'), 'gcd': ('\u5206\u62c5\u5766\u8f85', '\u524d\u4e2d\u6392', '\u4e0a\u4e0b\u5de6\u53f3\u63a5\u4f4f\u961f\u53cb\u7684\u4f24\u5bb3\uff0c\u5206\u62c5\u603b\u91cf\u4e3a30%\uff0c\u975e\u6bcf\u4e2agcd\u540430%\u3002'), 'bfs': ('\u5168\u573a\u51cf\u901f', '\u4fdd\u62a4\u4f4d', '\u5168\u573a\u4f24\u5bb3\u5e76\u9650\u65f6\u964d\u4f4e\u666e\u653b\u51c6\u5907\u901f\u5ea6\uff0c\u4e0d\u964d\u4f4e\u6280\u80fd\u9891\u7387\u3002'), 'pigeonhole': ('\u5bc6\u96c6\u514b\u5236', '\u4e2d\u6392', '\u654c\u65b9\u56f4\u7ed5\u76ee\u6807\u5bc6\u96c6\u65f6\u89e6\u53d1\u7ffb\u500d\uff0c\u5206\u6563\u654c\u4eba\u6536\u76ca\u4f4e\u3002'), 'prime_sieve': ('\u56de\u5408\u7206\u53d1', '\u4e2d\u6392', '\u7b2c2\u30013\u30015\u30017\u56de\u5408\u666e\u653b\u589e\u5f3a\uff0c\u975e\u8d28\u6570\u56de\u5408\u4fdd\u6301\u57fa\u7840\u8f93\u51fa\u3002'), 'mod_op': ('\u7a33\u5b9a\u5468\u671f\u8f93\u51fa', '\u4e2d\u6392', '\u6bcf\u4e09\u51fb2.5\u500d\uff0c\u9002\u5408\u7a33\u5b9a\u7ad9\u573a\u3002'), 'shift': ('\u73bb\u7483\u5927\u70ae', '\u540e\u6392', '\u6218\u5185\u653b\u51fb\u7ffb\u500d\u3001\u751f\u547d\u51cf\u534a\uff0c\u907f\u514d\u76f4\u63a5\u627f\u4f24\u3002'), 'range_dp': ('\u5c40\u90e8\u7fa4\u653b', '\u4e2d\u540e\u6392', '\u6253\u76ee\u6807\u53ca\u5de6\u53f3\u76f8\u90bb\u683c\uff0c\u514b\u5236\u6a2a\u5411\u5bc6\u96c6\u9635\u3002'), 'segment_tree': ('\u84c4\u529b\u7206\u53d1', '\u4e2d\u6392', '\u7ebf\u6bb5\u6811\u628a\u533a\u95f4\u4fee\u6539\u6512\u6210\u61d2\u6807\u8bb0\u518d\u4e00\u6b21\u6027\u4e0b\u653e\uff0c\u6bcf\u56db\u62cd\u6e05\u4e00\u6b21\u5168\u573a\u3002'), 'sqrt_block': ('\u5206\u5757\u7fa4\u653b', '\u4e2d\u540e\u6392', '\u56fa\u5b9a\u68cb\u76d82\xd72\u5206\u5757\uff0c\u4e0d\u662f\u4ee5\u76ee\u6807\u4e3a\u5de6\u4e0a\u89d2\u4efb\u610f\u53d6\u5757\u3002'), 'pruning': ('\u788e\u4f24\u9632\u5fa1', '\u524d\u6392', '\u53ea\u9488\u5bf9\u4f4e\u4e8e\u81ea\u8eab\u653b\u51fb50%\u7684\u5355\u6b21\u4f24\u5bb3\uff0c\u91cd\u51fb\u4ecd\u5371\u9669\u3002'), 'ids': ('\u957f\u5c40\u8fdc\u7a0b', '\u540e\u6392', '\u7b2c\u4e00\u56de\u5408\u57fa\u7840\u5c04\u7a0b\uff0c\u968f\u56de\u5408\u9010\u6b65\u589e\u52a0\u3002'), 'merge_sort': ('\u751f\u547d\u8c03\u914d', '\u90bb\u63a5\u4fdd\u62a4\u4f4d', '\u5f00\u6218\u65f6\u4e3a\u8fde\u901a\u7ec4\u5747\u5206\u5f53\u524d\u751f\u547d\uff1b\u4e0d\u662f\u51ed\u7a7a\u6cbb\u7597\u3002'), 'quick_sort': ('\u9ad8\u653b\u70b9\u7fa4\u4f24', '\u4e2d\u540e\u6392', '\u5c04\u7a0b\u5185\u6309\u5f53\u524d\u653b\u51fb\u6392\u5e8f\uff0c\u4f18\u5148\u6253\u8f93\u51fa\u4f4d\u3002'), 'divide': ('\u6761\u4ef6\u7fa4\u7206', '\u4e2d\u540e\u6392', '\u7b2c\u4e00\u6bb5\u672a\u51fb\u6740\u4efb\u4f55\u76ee\u6807\u624d\u6709\u8865\u5200\u6bb5\u3002'), 'inverse': ('\u666e\u653b\u53cd\u5236', '\u524d\u6392', '\u6309\u5b9e\u9645\u635f\u5931\u751f\u547d\u53cd\u5f39\uff0c\u4e0d\u53cd\u5f39\u88ab\u62a4\u76fe\u5438\u6536\u7684\u90e8\u5206\u3002'), 'bitmask_dp': ('\u540c\u884c\u534f\u540c\u70ae', '\u540c\u884c\u4fdd\u62a4\u4f4d', '\u540c\u884c\u9ad8\u653b\u51fb\u961f\u53cb\u589e\u5f3a\u6280\u80fd\uff0c\u9700\u517c\u987e\u5c04\u7a0b\u4e0e\u7ad9\u4f4d\u3002'), 'monotonic_queue': ('\u9ad8\u653b\u538b\u5236', '\u4e2d\u6392', '\u4f18\u5148\u653b\u51fb\u5c04\u7a0b\u5185\u6700\u9ad8\u653b\u51fb\u8005\uff0c\u53ef\u80fd\u653e\u8fc7\u6b8b\u8840\u3002'), 'a_star': ('\u9ad8\u8d39\u6536\u5272', '\u4e2d\u540e\u6392', 'A* \u7528 f=g+h \u6311\u6700\u6709\u5e0c\u671b\u7684\u8282\u70b9\uff0c\u4f18\u5148\u6253\u8fd1\u4e14\u5feb\u6b7b\u7684\u76ee\u6807\uff0c\u5e76\u81ea\u5e26 25% \u589e\u4f24\u3002'), 'bidirectional': ('\u53cc\u7aef\u6253\u51fb', '\u4e2d\u540e\u6392', '\u5c04\u7a0b\u5185\u6700\u8fd1\u4e0e\u6700\u8fdc\u5404\u4e00\u51fb\uff0c\u53ea\u6709\u4e00\u540d\u654c\u4eba\u65f6\u4e0d\u91cd\u590d\u3002'), 'fermat': ('\u56de\u5408\u7206\u53d1', '\u4e2d\u540e\u6392', '\u6a21\u5e42\u6309\u5468\u671f\u56de\u7ed5\uff0c\u524d\u534a\u5468\u671f\u5360\u4f18\u3001\u540e\u534a\u5468\u671f\u75b2\u8f6f\uff0c\u6700\u540e\u4e00\u51fb\u5f52\u96f6\u65f6\u7206\u53d1\u3002'), 'expectation': ('\u7a33\u5b9a\u5355\u4f53', '\u4e2d\u540e\u6392', '\u6052\u5b9a\u666e\u653b\u500d\u7387\uff0c\u9002\u5408\u9700\u8981\u7a33\u5b9a\u8f93\u51fa\u7684\u9635\u5bb9\u3002'), 'sweep_line': ('\u540c\u884c\u9012\u589e\u7fa4\u653b', '\u4e2d\u540e\u6392', '\u76ee\u6807\u540c\u884c\u81f3\u591a\u4e09\u4eba\uff0c\u7531\u8fd1\u5230\u8fdc\u9012\u589e\u3002'), 'cdq': ('\u540e\u7a0b\u6838\u5fc3', '\u4fdd\u62a4\u540e\u6392', '\u524d10\u79d2\u504f\u5f31\uff0c\u6b64\u540e\u7206\u53d1\uff0c\u5fc5\u987b\u4fdd\u62a4\u5230\u540e\u534a\u573a\u3002'), 'spfa': ('\u968f\u673a\u505c\u987f\u8f93\u51fa', '\u4fdd\u62a4\u4e2d\u540e\u6392', '\u653b\u901f\u5feb\u3001\u653b\u51fb\u9ad8\uff0c\u4f46\u6bcf\u6b21\u666e\u653b\u540e20%\u6982\u7387\u989d\u5916\u53614\u79d2\u3002'), 'o2': ('\u7ad9\u4f4d\u653b\u901f\u6838\u5fc3', '\u90bb\u63a5\u4fdd\u62a4\u4f4d', '0\u653b\u51fb\u3001280\u8840\uff1b\u8986\u76d6\u591a\u4eba\u518d\u6295\u5165\uff0c\u5206\u6563\u6216\u4e3b\u52a8\u6280\u80fd\u9635\u5bb9\u4e0d\u5b9c\u76f2\u5e26\u3002'), 'genetic': ('\u6c38\u4e45\u6210\u957f\u6838\u5fc3', '\u4fdd\u62a4\u4e2d\u540e\u6392', '\u51fb\u6740\u53e0\u5c42\u6700\u591a\u4e09\u5c42\uff0c\u5e78\u5b58\u68cb\u5b50\u7684\u5c42\u6570\u8de8\u56de\u5408\u4fdd\u7559\u3002'), 'matrix_pow': ('\u9ad8\u8d39\u65f6\u95f4\u6838\u5fc3', '\u540e\u6392', '\u5165\u573a\u653b\u9ad8\u8840\u51cf\uff0c6/12\u79d2\u9010\u6b65\u6210\u957f\u3002')}
CARD_ROLES.update({
    'two_pointers': ('\u7a7f\u900f\u8865\u5200', '\u4e2d\u6392', '\u6cbf\u654c\u4eba\u7eb5\u5217\u7ad9\u4f4d\uff0c\u666e\u653b\u80fd\u987a\u5e26\u6253\u5230\u76ee\u6807\u8eab\u540e\u7684\u654c\u4eba\u3002'),
    'prefix_sum': ('\u540c\u6d41\u6d3e\u6210\u957f', '\u4e2d\u540e\u6392', '\u524d\u7f00\u548c\u628a\u5386\u53f2\u7d2f\u52a0\u6210\u8868\uff0c\u8d8a\u6253\u5230\u540e\u9762\u5355\u6b21\u4f24\u5bb3\u8d8a\u9ad8\uff0c\u9002\u5408\u6301\u4e45\u6218\u800c\u975e\u901f\u653b\u3002'),
    'huffman': ('\u7eed\u822a\u8f93\u51fa', '\u4e2d\u6392', '\u666e\u653b\u6309\u5b9e\u9645\u4f24\u5bb3\u56de\u8840\uff0c\u9002\u5408\u6301\u4e45\u6218\u800c\u975e\u7206\u53d1\u3002'),
    'topo_sort': ('\u5168\u573a\u505c\u6ede', '\u540e\u6392', '\u5c04\u7a0b\u5185\u5168\u4f53\u505c\u653b 2 \u79d2\uff0c\u4e3a\u53cb\u519b\u4e89\u53d6\u51fa\u624b\u7a97\u53e3\u3002'),
    'kmp': ('\u7a7f\u900f\u70b9\u6740', '\u4e2d\u6392', 'KMP \u5931\u914d\u65f6\u4e0d\u56de\u9000\u4e3b\u4e32\u800c\u662f\u67e5 next \u8868\uff0c\u8fde\u7eed\u5543\u540c\u4e00\u4e2a\u76ee\u6807\u8d8a\u5543\u8d8a\u5feb\u3002'),
    'prim': ('\u8fde\u8fb9\u534f\u540c', '\u4e2d\u540e\u6392', '\u6700\u5c0f\u751f\u6210\u6811\u7528\u6700\u5c11\u7684\u8fb9\u8fde\u901a\u5168\u573a\uff0c\u8d34\u7740\u961f\u53cb\u7ad9\u80fd\u628a\u4f24\u5bb3\u5206\u644a\u51fa\u53bb\u3002'),
    'flood_fill': ('\u56db\u90bb\u6e85\u5c04', '\u4e2d\u6392', '\u654c\u65b9\u5bc6\u96c6\u7ad9\u4f4d\u65f6\uff0c\u4e00\u6b21\u666e\u653b\u80fd\u6e85\u5230\u591a\u4e2a\u76f8\u90bb\u76ee\u6807\u3002'),
    'ac_automaton': ('\u591a\u70b9\u6e85\u5c04', '\u4e2d\u540e\u6392', 'AC \u81ea\u52a8\u673a\u6cbf fail \u94fe\u4e00\u6b21\u626b\u63cf\u547d\u4e2d\u6240\u6709\u6a21\u5f0f\uff0c\u5bf9\u9762\u540c\u7c7b\u8d8a\u591a\u6536\u76ca\u8d8a\u9ad8\u3002'),
    'tarjan': ('\u540c\u73af\u5171\u632f', '\u4e2d\u540e\u6392', '\u5f3a\u8fde\u901a\u5206\u91cf\u9760 lowlink \u6807\u8bb0\u4e92\u76f8\u53ef\u8fbe\u7684\u8282\u70b9\uff0c\u88ab\u6807\u8bb0\u7684\u76ee\u6807\u4f1a\u8d8a\u6765\u8d8a\u8106\u3002'),
    'minimax': ('\u6b8b\u8840\u7ffb\u76d8', '\u524d\u4e2d\u6392', '\u751f\u547d\u8dcc\u7834\u4e00\u534a\u540e\u653b\u51fb \xd71.6\uff0c\u9002\u5408\u9876\u5728\u524d\u6392\u6362\u8840\u3002'),
    'suffix_array': ('\u7eb5\u5217\u7a7f\u900f', '\u4e2d\u540e\u6392', '\u540e\u7f00\u6570\u7ec4\u9760 LCP \u8861\u91cf\u76f8\u90bb\u540e\u7f00\u7684\u76f8\u4f3c\u5ea6\uff0c\u53ea\u6253\u540c\u4e00\u7c7b\u76ee\u6807\u624d\u6709\u9ad8\u6536\u76ca\u3002'),
    'splay': ('\u9ad8\u7eed\u822a\u524d\u6392', '\u524d\u6392', '\u4f38\u5c55\u6811\u6bcf\u6b21\u8bbf\u95ee\u90fd\u628a\u8282\u70b9\u65cb\u5230\u6839\uff0c\u8d8a\u6253\u8d8a\u987a\uff1b\u4e00\u65e6\u88ab\u96c6\u706b\uff0c\u65cb\u8f6c\u5c42\u6570\u7acb\u523b\u6298\u534a\u3002'),
    'network_flow': ('\u5168\u573a\u963b\u585e', '\u540e\u6392', '\u6700\u5927\u6d41\u53d7\u9650\u4e8e\u6700\u5c0f\u5272\uff0c\u6d41\u91cf\u88ab\u591a\u6761\u8fb9\u5206\u644a\uff0c\u4f18\u5148\u5272\u65ad\u5bb9\u91cf\u6700\u5927\u7684\u90a3\u4e00\u8def\u3002'),
    'fft': ('\u540c\u9891\u534f\u540c', '\u540e\u6392', '\u8776\u5f62\u8fd0\u7b97\u628a\u65f6\u57df\u62c6\u6210\u5947\u5076\u4e24\u8def\u518d\u5408\u5e76\uff0c\u7b2c\u4e00\u62cd\u5f31\u3001\u7b2c\u4e8c\u62cd\u5f3a\uff0c\u5747\u503c\u7565\u9ad8\u4e8e\u666e\u901a\u5361\u3002'),
    'suffix_automaton': ('\u7edd\u5883\u6536\u5272', '\u524d\u4e2d\u6392', '\u540e\u7f00\u81ea\u52a8\u673a\u7528\u6700\u5c11\u72b6\u6001\u5b58\u4e0b\u6240\u6709\u5b50\u4e32\uff0c\u4ee3\u4ef7\u662f\u6781\u4f4e\u7684\u6709\u6548\u751f\u547d\uff1a\u5806\u540c\u540d\u8d8a\u591a\u8d8a\u8106\u3002'),
})

for _card in CARDS:
    _card['role'], _card['position'], _card['tip'] = CARD_ROLES[_card['id']]
    _card['baseInterval'] = 0 if _card['id'] == 'o2' else ATK_CD / (SPFA_SPEED_MULT if _card['id'] == 'spfa' else 1.0)

CARD_BY_ID = {c['id']: c for c in CARDS}
SHOP_MIN_COST = min(c['cost'] for c in CARDS)
SHOP_MAX_COST = max(c['cost'] for c in CARDS)
SHOP_WEIGHT_BASE = 2       # lower cost cards stay more common at every level


def _fill_card_max_hp():
    """\u628a\u6709\u6548\u751f\u547d\u4e0a\u9650\uff08\u79fb\u4f4d \xd70.5 / \u77e9\u9635\u5feb\u901f\u5e42 \xd70.9\uff09\u5199\u8fdb\u5361\u8868\uff0c\u4f9b\u524d\u7aef\u663e\u793a\u3002"""
    for c in CARDS:
        c['maxHp'] = effective_max_hp(c)

TRAITS = {
    'dynamic_programming': '\u52a8\u6001\u89c4\u5212', 'data_structure': '\u6570\u636e\u7ed3\u6784',
    'greedy': '\u8d2a\u5fc3/\u6392\u5e8f', 'search': '\u641c\u7d22', 'divide_conquer': '\u5206\u6cbb',
    'diff': '\u5dee\u5206', 'bitwise': '\u4f4d\u8fd0\u7b97', 'number_theory': '\u6570\u8bba',
    'combinatorics': '\u7ec4\u5408\u6570\u5b66', 'probability': '\u6982\u7387\u671f\u671b',
    'geometry': '\u8ba1\u7b97\u51e0\u4f55', 'math': '\u6570\u5b66', 'optimization': '\u4f18\u5316',
    'graph_theory': '\u56fe\u8bba', 'string': '\u5b57\u7b26\u4e32', 'game_theory': '\u535a\u5f08',
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


def _as_str(v, limit=None, default=''):
    """\u53ea\u63a5\u53d7\u5b57\u7b26\u4e32\uff0c\u9632\u6b62 {'text': {}} \u8fd9\u7c7b\u810f\u8f93\u5165\u628a\u5904\u7406\u7ebf\u7a0b\u6253\u5d29\u3002"""
    if not isinstance(v, str):
        return default
    v = v.strip()
    return v[:limit] if limit is not None else v


def _as_int(v, default=None):
    """\u53ea\u63a5\u53d7\u6574\u6570\uff08bool \u4e0d\u7b97\uff09\uff0c\u975e\u6cd5\u8fd4\u56de default\u3002"""
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
    """\u672c\u8f6e\u7b2c n \u6b21\u5237\u65b0\u7684\u91d1\u5e01\u4ef7\u683c\uff1a\u9996\u6b21\u514d\u8d39\uff0c\u4e4b\u540e\u4ece\u57fa\u7840\u4ef7\u9010\u6b21 +1\u3002"""
    n = max(0, int(refreshes or 0))
    if n < SHOP_FREE_REFRESHES:
        return 0
    return SHOP_REFRESH_BASE + (n - SHOP_FREE_REFRESHES) * SHOP_REFRESH_STEP


def board_power(board):
    """\u5b58\u6d3b\u68cb\u5b50\u7684\u7b49\u7ea7\u683c\u5b50\u4e4b\u548c\uff1a\u6bcf\u4e2a\u5b58\u6d3b\u68cb\u5b50\u5360 1 \u683c\uff0c\u7b49\u7ea7\u5373\u661f\u7ea7\u3002"""
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
# \u6863\u6848\u4e0e Rating
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
    with DATA_LOCK:
        if cid not in PROFILES:
            PROFILES[cid] = {'clientId': cid, 'name': name or '\u9009\u624b',
                             'rating': DEFAULT_RATING, 'wins': 0, 'losses': 0, 'games': 0}
            save_profiles()
        elif name and PROFILES[cid].get('name') != name:
            PROFILES[cid]['name'] = name
            save_profiles()
        return dict(PROFILES[cid])


def update_rating(cid, delta, result=None, name=None):
    with DATA_LOCK:
        if cid not in PROFILES:
            PROFILES[cid] = {'clientId': cid, 'name': name or '\u9009\u624b',
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


def new_player(pid, name):
    return {
        'id': pid, 'name': name,
        'hp': 100, 'gold': 10, 'level': 1,
        'mind': 100, 'reason': 100, 'energy': 100,
        'board': {}, 'bench': [], 'shop': [], 'shopRefreshes': 0,
        'ready': False, 'lastResult': '', 'opponent': None,
        'dead': False, 'abandoned': False, 'rated': False, 'crashed': False,
        'roundWins': 0, 'roundLosses': 0,
        'last_seen': time.time(),
    }


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

    # ---- \u989c\u8272 --------------------------------------------------------------
    def _assign_color(self, cid):
        used = set(self.colors.values())
        for i in range(MAX_PLAYERS):
            if i not in used:
                self.colors[cid] = i
                return i
        self.colors[cid] = 0
        return 0

    # ---- \u5fc3\u8df3 --------------------------------------------------------------
    def _touch(self, cid):
        p = self.players.get(cid)
        if p is not None:
            p['last_seen'] = time.time()

    # ---- \u8fdb\u51fa\u623f\u95f4 ----------------------------------------------------------
    def add_player(self, cid, name):
        with self.lock:
            if cid in self.players:
                self._touch(cid)
                return True, 'rejoined'
            if len(self.players) >= MAX_PLAYERS:
                return False, '\u623f\u95f4\u5df2\u6ee1'
            if self.state != 'waiting':
                return False, '\u6e38\u620f\u5df2\u5f00\u59cb'
            self.players[cid] = new_player(cid, name)
            self._assign_color(cid)
            self.version += 1
            self._sys_chat(f'{name} \u52a0\u5165\u4e86\u623f\u95f4')
            return True, 'joined'

    # ---- \u804a\u5929 --------------------------------------------------------------
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
                return False, '\u73a9\u5bb6\u4e0d\u5b58\u5728'
            self._touch(pid)
            if not isinstance(text, str):
                return False, '\u6d88\u606f\u683c\u5f0f\u9519\u8bef'
            text = text.strip()[:200]
            if not text:
                return False, '\u6d88\u606f\u4e3a\u7a7a'
            self._push_chat({'id': uuid.uuid4().hex, 'sender': p['name'], 'senderId': pid,
                             'text': text, 'time': int(time.time() * 1000), 'system': False})
            self.version += 1
            return True, None

    # ---- \u5546\u5e97 --------------------------------------------------------------
    def _shop_pool(self, level):
        """Unlock costs up to min(SHOP_MAX_COST, level); lower costs weigh more."""
        top = max(SHOP_MIN_COST, min(int(level or 1), SHOP_MAX_COST))
        ids, weights = [], []
        for c in CARDS:
            if c['cost'] <= top:
                ids.append(c['id'])
                weights.append(SHOP_WEIGHT_BASE ** (top - c['cost']))
        return ids, weights

    def _roll_shop(self, level, count=5, owner=None):
        # Level drives the pool; a card one copy short of a merge is weighted
        # up so a larger card pool does not make 3-star upgrades unreachable.
        ids, weights = self._shop_pool(level)
        if owner is not None:
            near = self._near_merge_ids(owner)
            if near:
                weights = [w * (SHOP_PITY_MULT if cid in near else 1)
                           for cid, w in zip(ids, weights)]
        return random.choices(ids, weights=weights, k=count)

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

    # ---- \u5f00\u5c40 --------------------------------------------------------------
    def start(self, pid):
        with self.lock:
            if pid != self.host:
                return False, '\u53ea\u6709\u623f\u4e3b\u53ef\u4ee5\u5f00\u59cb'
            if self.state != 'waiting':
                return False, '\u6e38\u620f\u5df2\u7ecf\u5f00\u59cb'
            self._touch(pid)
            n = len([p for p in self.players.values() if not p.get('dead')])
            if n < 2:
                return False, '\u81f3\u5c11\u9700\u8981 2 \u540d\u73a9\u5bb6'
            self.round = 1
            for p in self.players.values():
                p['level'] = level_for_round(self.round)
            self._roll_all_shops()
            self._start_prep(first=True)
            self._sys_chat(f'\u6e38\u620f\u5f00\u59cb\uff0c\u5171 {n} \u540d\u73a9\u5bb6')
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
        self.prep_end = time.time() + PREP_TIME
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

    # ---- \u51c6\u5907\u671f\u64cd\u4f5c --------------------------------------------------------
    def _prep_player(self, pid):
        p = self.players.get(pid)
        if not p:
            return None, '\u73a9\u5bb6\u4e0d\u5b58\u5728'
        if p.get('dead'):
            return None, '\u4f60\u5df2\u51fa\u5c40'
        if self.state != 'prep':
            return None, '\u5f53\u524d\u4e0d\u53ef\u64cd\u4f5c'
        p['last_seen'] = time.time()
        return p, None

    def refresh_shop(self, pid):
        with self.lock:
            p, err = self._prep_player(pid)
            if err:
                return False, err
            cost = shop_refresh_cost(p.get('shopRefreshes', 0))
            if p['gold'] < cost:
                return False, '\u91d1\u5e01\u4e0d\u8db3'
            p['gold'] -= cost
            p['shopRefreshes'] = int(p.get('shopRefreshes', 0) or 0) + 1
            p['shop'] = self._roll_shop(p['level'], owner=p)
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
                return False, '\u65e0\u6548\u4f4d\u7f6e'
            card = CARD_BY_ID[p['shop'][shop_index]]
            if p['gold'] < card['cost']:
                return False, '\u91d1\u5e01\u4e0d\u8db3'
            if p['energy'] < card['energy']:
                return False, '\u7cbe\u529b\u4e0d\u8db3'
            if p['reason'] < card['reason']:
                return False, '\u7406\u667a\u4e0d\u8db3'
            if len(p['bench']) >= MAX_BENCH \
                    and not self._would_merge(p, card['id'], 1):
                return False, '\u5907\u6218\u5e2d\u5df2\u6ee1'
            p['gold'] -= card['cost']
            p['energy'] -= card['energy']
            p['reason'] -= card['reason']
            p['bench'].append(make_card_obj(card['id']))
            p['shop'].pop(shop_index)
            self._try_merge(p)
            if p['reason'] <= 0 and not p.get('crashed'):
                p['crashed'] = True
                self._sys_chat(f'{p["name"]} \u7406\u667a\u8017\u5c3d\uff0c\u9677\u5165\u5d29\u6e83\uff1a\u6bcf\u56de\u5408\u989d\u5916 -{REASON_CRASH_MIND} \u5fc3\u6001')
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
                    return False, '\u65e0\u6548\u4f4d\u7f6e'
                item = p['bench'].pop(idx)
            else:
                key = key_or_idx
                if key not in p['board']:
                    return False, '\u65e0\u6548\u4f4d\u7f6e'
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
                return False, '\u65e0\u6548\u4f4d\u7f6e'
            if not isinstance(x, int) or not isinstance(y, int) \
                    or not (0 <= x < HALF_W and 0 <= y < HALF_H):
                return False, '\u8d85\u51fa\u4f60\u7684\u534a\u573a'
            if len(p['board']) >= MAX_BOARD:
                return False, f'\u573a\u4e0a\u6700\u591a {MAX_BOARD} \u4e2a\u68cb\u5b50'
            key = f'{x},{y}'
            if key in p['board']:
                return False, '\u8be5\u4f4d\u7f6e\u5df2\u6709\u5355\u4f4d'
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
                return False, '\u7a7a\u4f4d'
            if len(p['bench']) >= MAX_BENCH:
                return False, '\u5907\u6218\u5e2d\u5df2\u6ee1'
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
            self.version += 1
            return True, None

    # ---- \u914d\u5bf9 --------------------------------------------------------------
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
            print(f'[\u914d\u5bf9] {self.players[pr["a"]]["name"]} vs {self.players[pr["b"]]["name"]}')
        for cid in self._bye_players:
            print(f'[\u914d\u5bf9] {self.players[cid]["name"]} \u8f6e\u7a7a')

    # ---- \u6dd8\u6c70 / \u7ed3\u7b97 -------------------------------------------------------
    def _mark_dead(self, cid, note='\u88ab\u6dd8\u6c70'):
        p = self.players.get(cid)
        if not p or p.get('dead'):
            return
        p['dead'] = True
        if not p.get('rated'):
            p['rated'] = True
            update_rating(cid, RATING_LOSE, 'lose', name=p.get('name'))
            self._sys_chat(f'{p["name"]} {note}\uff0c-20 Rating')
        else:
            self._sys_chat(f'{p["name"]} {note}')

    def _apply_empty_penalty(self):
        pending = [cid for cid, p in self.players.items()
                   if not p.get('dead') and not p['board']]
        for cid in pending:
            self.players[cid]['hp'] = max(0, self.players[cid]['hp'] - 1)
        dead = [cid for cid in pending if self.players[cid]['hp'] <= 0]
        for cid in dead:
            self._mark_dead(cid, '\u7a7a\u573a\u6302\u673a\u88ab\u6dd8\u6c70')
        if pending:
            self.version += 1

    def _tick(self):
        now = time.time()
        if self.state == 'prep':
            if not self.pairs_computed and now >= self.prep_end - PAIR_LEAD_TIME:
                self._compute_pairings()
                self.pairs_computed = True
            if now >= self.prep_end:
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

            # \u9635\u4ea1\u68cb\u5b50\u4e0d\u518d\u4ece\u68cb\u76d8\u4e0a\u5220\u9664\uff0c\u4fdd\u7559 0 \u8840\u5230\u4e0b\u4e00\u8f6e\u3002
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
                self._sys_chat(f'{p["name"]} \u7406\u667a\u8017\u5c3d\uff0c\u9677\u5165\u5d29\u6e83')
            if p.get('crashed'):
                p['mind'] = max(0, p['mind'] - REASON_CRASH_MIND)

        dead = [cid for cid, p in self.players.items()
                if not p.get('dead') and (p['hp'] <= 0 or p['mind'] <= 0)]
        for cid in dead:
            p = self.players[cid]
            note = '\u5fc3\u6001\u5d29\u6e83\u9000\u8d5b' if p['mind'] <= 0 and p['hp'] > 0 else 'AC \u5f52\u96f6\u88ab\u6dd8\u6c70'
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
                self._sys_chat(f'{p["name"]} \u83b7\u80dc\uff01\u91d1\u5e01 {p["gold"]}\uff0cRating +{gain}')
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
        self._finish_game(winner_id, f'\u56de\u5408\u4e0a\u9650\uff0c{self.players[winner_id]["name"]} \u91d1\u5e01\u6700\u591a\u83b7\u80dc\uff01')

    # ========================================================
    # \u6218\u6597\u6a21\u62df
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
        # \u516b\u90bb\u57df\uff08\u542b\u659c\u89d2\uff09\uff0c\u4ec5\u6d3b\u7740\u7684\u540c\u961f O2\uff1b\u591a\u4e2a\u6765\u6e90\u53d6\u540c\u4e00\u4e2a\u500d\u7387\u3002
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
        # \u5408\u5e76\u8fb9\u53ea\u7531\u5f52\u5e76\u6392\u5e8f\u8fde\u63a5\u81ea\u5df1\u4e0e\u6b63\u4ea4\u90bb\u5c45\uff1b\u8fde\u901a\u7ec4\u540c\u6b65\u5747\u5206\uff0c\u6d88\u9664\u904d\u5386\u987a\u5e8f\u5dee\u5f02\u3002
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
        # \u4ece\u57fa\u7840\u653b\u51fb\u6309\u4ecd\u6709\u6548\u7684\u4ea4\u6362\u987a\u5e8f\u91cd\u653e\uff1b\u91cd\u53e0\u4ea4\u6362\u5230\u671f\u4e0d\u4f1a\u56de\u6eda\u6210\u8d1f\u653b\u51fb\u3002
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
            # \u65e7\u89c4\u5219\u662f\u300c\u4f24\u5bb3\u4f4e\u4e8e\u81ea\u8eab\u653b\u51fb\u529b\u5c31\u5b8c\u5168\u514d\u75ab\u300d\uff0c\u5728\u5168\u5c40\u4f24\u5bb3 \xd71/3 \u7684\u8bbe\u5b9a\u4e0b
            # \u7b49\u4e8e\u5bf9\u540c\u8d39\u53ca\u4ee5\u4e0b\u7684\u653b\u51fb\u8005\u6c38\u4e45\u65e0\u654c\u3002\u73b0\u5728\u6539\u6210\u6309\u6bd4\u4f8b\u51cf\u514d + \u8f6c\u62a4\u76fe\u3002
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

        if sk == 'aoe':
            for e in enemies:
                hit(e, 0.5)
        elif sk == 'aoe_debuff':
            for e in enemies:
                hit(e, AOE_DEBUFF_RATIO)
                e['slowUntil'] = max(e['slowUntil'], t + SLOW_DURATION)
        elif sk == 'multi':
            for _ in range(3):
                if target['hp'] <= 0:
                    break
                hit(target, 0.5)
        elif sk == 'line':
            row = [e for e in enemies if e['y'] == target['y']]
            col = [e for e in enemies if e['x'] == target['x']]
            line = row if len(row) >= len(col) else col
            for e in (line or [target]):
                hit(e, 0.5)
        elif sk == 'range_aoe':
            box = [e for e in enemies if e['y'] == target['y']
                   and abs(e['x'] - target['x']) <= 1]
            for e in box:
                hit(e, 0.8)
        elif sk == 'block_aoe':
            box = [e for e in enemies
                   if e['x'] // 2 == target['x'] // 2 and e['y'] // 2 == target['y'] // 2]
            for e in (box or [target]):
                hit(e, 0.7)
        elif sk == 'delayed_line':
            row = [e for e in enemies if e['y'] == target['y']] or [target]
            for e in row:
                amount = u['atk'] * DMG_MULT * u['outMult'] * 1.5
                e['delayed'].append((t + 2.0, amount, u['uid']))
                cast_event['targets'].append({'x': int(e['x']), 'y': int(e['y'])})
        elif sk == 'swap_stats':
            # \u5361\u9762\u5199\u7684\u662f\u201c\u653b\u51fb\u6700\u9ad8\u7684\u654c\u4eba\u201d\uff0c\u76ee\u6807\u672c\u8eab\u4e5f\u5728\u5019\u9009\u91cc
            other = max(enemies, key=lambda e: e['atk'])
            ua, oa = u['atk'], other['atk']
            u['atk'], other['atk'] = oa, ua
            token = (t, len(events), u['uid'], other['uid'], t + SWAP_DURATION)
            u['swap'].append(token)
            other['swap'].append(token)
            self._refresh_swaps(units, t)
            cast_event['targets'].append({'x': int(other['x']), 'y': int(other['y'])})
        elif sk == 'sort_line':
            row = sorted([e for e in enemies if e['y'] == target['y']], key=lambda e: e['x'])
            for i in range(0, len(row) - 1, 2):
                row[i]['x'], row[i + 1]['x'] = row[i + 1]['x'], row[i]['x']
            for e in row:
                hit(e, 0.3)
        elif sk == 'compress_line':
            allies = [o for o in units
                      if o is not u and o['hp'] > 0 and o['owner'] == u['owner']
                      and o['y'] == u['y']]
            total_atk = u['atk'] + sum(o['atk'] for o in allies)
            row = [e for e in enemies if e['y'] == target['y']] or [target]
            for e in row:
                hit(e, 1.0, raw_override=total_atk * DMG_MULT * u['outMult'])
        elif sk == 'pincer':
            near = min(enemies, key=lambda e: self._dist(u, e))
            far = max(enemies, key=lambda e: self._dist(u, e))
            hit(near, 1.2)
            if far is not near:
                hit(far, 1.2)
        elif sk == 'partition':
            ranked = sorted(enemies, key=lambda e: -e['atk'])
            half = ranked[:max(1, (len(ranked) + 1) // 2)]
            for e in half:
                hit(e, 1.0)
        elif sk == 'divide_conquer':
            pool = [e for e in enemies if self._dist(u, e) <= u['range']] or [target]
            for e in pool:
                hit(e, 0.5)
            if all(e['hp'] > 0 for e in pool):
                for e in pool:
                    hit(e, 1.0)
        elif sk == 'sweep':
            row = sorted([e for e in enemies if e['y'] == target['y']] or [target],
                         key=lambda e: abs(e['x'] - u['x']))
            for i, e in enumerate(row[:3]):
                hit(e, 0.6 + 0.3 * i)
        elif sk == 'freeze':
            for e in enemies:
                hit(e, FREEZE_RATIO)
                e['stallUntil'] = max(e['stallUntil'], t + FREEZE_STALL)
        elif sk == 'min_cut':
            n = max(1, len(enemies))
            ratio = MIN_CUT_RATIO / (1.0 + MIN_CUT_SPREAD * (n - 1))
            boss = max(enemies, key=lambda e: e['hp']) if enemies else None
            for e in enemies:
                hit(e, ratio)
            if boss is not None and boss['hp'] > 0:
                hit(boss, MIN_CUT_BOSS_RATIO / (1.0 + MIN_CUT_BOSS_SPREAD * (n - 1)))

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

        def alive(owner):
            return [u for u in units if u['hp'] > 0 and u['owner'] == owner]

        def snap(now):
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
                    'phase': '\u7206\u53d1' if u['skill'] == 'cdq' and now >= CDQ_SWITCH else '',
                } for u in units if u['hp'] > 0],
            })

        # \u653b\u51fb/\u6280\u80fd/\u72b6\u6001\u5230\u671f\u4f7f\u7528\u4e8b\u4ef6\u65f6\u95f4\uff1b\u79fb\u52a8\u4ecd\u6bcf TICK_SEC \u4e00\u6b21\u3002
        # \u4e0d\u7f29\u5c0f\u5168\u5c40 tick\uff0c\u4e5f\u4e0d\u628a\u51b7\u5374\u4f59\u91cf\u5411\u4e0a\u53d6\u6574\u3002
        eps = 1e-9
        next_move = 0.0
        snap(0.0)
        while t < BATTLE_TIME - eps:
            move_now = t >= next_move - eps
            if move_now:
                next_move += TICK_SEC
            self._refresh_swaps(units, t)
            for u in units:
                if u['delayed']:
                    due = [d for d in u['delayed'] if d[0] <= t + eps]
                    u['delayed'] = [d for d in u['delayed'] if d[0] > t + eps]
                    for _, amount, src_uid in due:
                        src = by_uid.get(src_uid)
                        dealt = self._deal_damage(u, amount, events, t, units, by_uid, source=src)
                        events.append({'t': round(t, 6), 'type': 'attack', 'fromX': src['x'] if src else u['x'], 'fromY': src['y'] if src else u['y'], 'toX': u['x'], 'toY': u['y'], 'dmg': dealt, 'owner': src['owner'] if src else u['owner'], 'sourceUid': src_uid, 'targetUid': u['uid'], 'skill': True, 'skillId': 'delayed_line'})
                if u['hp'] <= 0:
                    continue
                enemies = [e for e in units if e['owner'] != u['owner'] and e['hp'] > 0]
                if not enemies:
                    break
                if u['skill'] == 'o2_aura':
                    continue
                target = self._pick_target(u, enemies)
                if self._dist(u, target) <= u['range']:
                    acted = False
                    if t >= u['actionUntil'] - eps:
                        if u['active'] and u['skillCd'] <= eps:
                            cost = float(CARD_BY_ID[u['card']]['skillCost'])
                            if pools.get(u['owner'], 0.0) >= cost:
                                pools[u['owner']] -= cost
                                u['skillCd'] = SKILL_CD
                                self._use_skill(u, target, enemies, units, events, t, by_uid, round_no)
                                # \u4fdd\u7559\u539f\u6709\u65bd\u6cd5\u5360\u7528\u4e00\u6b21\u884c\u52a8\u7684\u89c4\u5219\u3002
                                u['actionUntil'] = t + TICK_SEC
                                acted = True
                        if not acted and u['atkCd'] <= eps and t >= u['stallUntil'] - eps:
                            self._do_attack(u, target, units, events, t, by_uid, round_no)
                            u['atkCd'] = ATK_CD / (SPFA_SPEED_MULT if u['skill'] == 'spfa_stall' else 1.0)
                            if u['skill'] == 'spfa_stall' and random.random() < SPFA_STALL_CHANCE:
                                u['stallUntil'] = t + SPFA_STALL_EXTRA
                elif move_now:
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
                        # \u5355\u4f4d\u4e0d\u80fd\u8fdb\u5165\u5df2\u88ab\u5176\u4ed6\u5b58\u6d3b\u5355\u4f4d\u5360\u636e\u7684\u683c\u5b50\uff0c\u907f\u514d\u6218\u6597\u5e27\u51fa\u73b0\u68cb\u5b50\u91cd\u53e0\u3002
                        if (nx, ny) in occupied:
                            continue
                        u['x'], u['y'] = nx, ny
                        break


            # \u5b58\u50a8\u771f\u5b9e\u4e8b\u4ef6\u65f6\u523b\u7684\u72b6\u6001\uff1b\u91cd\u590d\u65f6\u95f4\u6233\u66ff\u6362\u521d\u59cb\u5feb\u7167\u3002
            if frames and abs(frames[-1]['t'] - t) < eps:
                frames.pop()
            snap(t)
            if not alive(a['id']) or not alive(b['id']):
                break

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

            # \u533a\u95f4\u5185\u5149\u73af\u3001\u51cf\u901f\u548c\u5361\u987f\u72b6\u6001\u4e0d\u53d8\uff1b\u79ef\u5206\u51c6\u5907\u8fdb\u5ea6\u3002
            dt = next_t - t
            for u in units:
                if u['hp'] <= 0:
                    continue
                work_dt = max(0.0, next_t - max(t, u['stallUntil']))
                u['atkCd'] = max(0.0, u['atkCd'] - work_dt * self._attack_rate(u, units, t))
                u['skillCd'] = max(0.0, u['skillCd'] - dt)
            t = next_t
        if frames and frames[-1]['t'] < round(t, 6):
            snap(t)

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

    # ---- \u89c6\u89d2\u53d8\u6362 ----------------------------------------------------------
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

    # ---- \u5bf9\u5916\u72b6\u6001 ----------------------------------------------------------
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
            r._sys_chat(f'{p["name"]} \u4e2d\u9014\u9000\u51fa\uff0c-30 Rating')

        if p:
            name = p['name']
            if in_game:
                p['dead'] = True
                p['abandoned'] = True
                p['ready'] = False
                r._sys_chat(f'{name} \u79bb\u5f00\u4e86\u5bf9\u5c40')
            else:
                del r.players[cid]
                r.colors.pop(cid, None)
                r._sys_chat(f'{name} \u79bb\u5f00\u4e86\u623f\u95f4')

        if not in_game:
            for aid in [c for c, pl in r.players.items() if pl.get('abandoned')]:
                del r.players[aid]
                r.colors.pop(aid, None)

        if r.host == cid:
            cand = [c for c, pl in r.players.items() if not pl.get('abandoned')]
            if cand:
                r.host = cand[0]
                r._sys_chat(f'{r.players[r.host]["name"]} \u6210\u4e3a\u65b0\u623f\u4e3b')

        r.version += 1
        if in_game:
            r._check_game_over()

        with ROOMS_LOCK:
            alive = [pl for pl in r.players.values() if not pl.get('abandoned')]
            if not alive:
                ROOMS.pop(rid, None)


# ============================================================
# \u6389\u7ebf\u6e05\u7406 & \u623f\u95f4\u56de\u6536
# ============================================================
def _cleanup_room_locked(r, now, to_remove):
    """\u5728\u6301\u6709 r.lock \u7684\u524d\u63d0\u4e0b\uff1a\u8e22\u6389\u7ebf\u73a9\u5bb6\u3001\u91cd\u9009\u623f\u4e3b\u3001\u56de\u6536\u7a7a\u623f\u3002"""
    # 1. \u5fc3\u8df3\u8d85\u65f6
    for cid, p in list(r.players.items()):
        if p.get('abandoned'):
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
            r._sys_chat(f'{name} \u957f\u65f6\u95f4\u65e0\u54cd\u5e94\uff0c\u5df2\u6389\u7ebf')
        else:
            r.players.pop(cid, None)
            r.colors.pop(cid, None)
            r._sys_chat(f'{name} \u957f\u65f6\u95f4\u65e0\u54cd\u5e94\uff0c\u5df2\u79bb\u5f00')
        r.version += 1

    # 2. \u623f\u4e3b\u79bb\u7ebf / \u4e0d\u5728\u623f\u95f4 \u2192 \u91cd\u9009
    if r.host not in r.players or r.players[r.host].get('abandoned'):
        cand = [c for c, pl in r.players.items() if not pl.get('abandoned')]
        if cand:
            r.host = cand[0]
            r._sys_chat(f'{r.players[r.host]["name"]} \u6210\u4e3a\u65b0\u623f\u4e3b')
            r.version += 1

    # 3. \u5bf9\u5c40\u4e2d\u6389\u7ebf\u540e\u91cd\u65b0\u5224\u5b9a\u5bf9\u5c40\u662f\u5426\u7ed3\u675f
    if r.state in ('prep', 'battle'):
        r._check_game_over()

    # 4. \u623f\u95f4\u56de\u6536\uff1a\u6ca1\u6709\u6d3b\u4eba
    alive = [pl for pl in r.players.values() if not pl.get('abandoned')]
    if not alive:
        to_remove.append(r.id)
        return

    # 5. \u5df2\u7ed3\u675f\u623f\u95f4\u8d85\u65f6\u56de\u6536
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
                    print(f'[\u623f\u95f4\u56de\u6536] {rid}')


# \u6bcf\u623f\u95f4\u72ec\u7acb tick \u5e76\u53d1\u6267\u884c\uff0c\u907f\u514d\u4e00\u4e2a\u623f\u95f4\u7684\u6218\u6597\u6a21\u62df\u963b\u585e\u5176\u4ed6\u623f\u95f4\u7684\u5012\u8ba1\u65f6
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
    """\u5ba2\u6237\u7aef\u63d0\u524d\u65ad\u5f00\uff08\u6d4f\u89c8\u5668 abort \u8f6e\u8be2 / \u5173\u95ed\u6807\u7b7e\u9875\uff09\u4f1a\u4ea7\u751f
    ConnectionAbortedError / ConnectionResetError / BrokenPipeError\uff0c
    \u8fd9\u4e9b\u5c5e\u4e8e\u6b63\u5e38\u7f51\u7edc\u566a\u58f0\uff0c\u9759\u9ed8\u5ffd\u7565\uff1b\u5176\u4ed6\u5f02\u5e38\u7167\u5e38\u6253\u5370\u4fbf\u4e8e\u6392\u67e5\u771f\u5b9e bug\u3002"""
    allow_reuse_address = True
    daemon_threads = True      # Ctrl+C \u9000\u51fa\u65f6\u4e0d\u518d join \u6240\u6709\u8bf7\u6c42\u7ebf\u7a0b\uff0c\u907f\u514d\u5361\u4f4f

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
        except Exception as e:                      # \u515c\u5e95\uff1a\u4e0d\u8ba9\u5904\u7406\u7ebf\u7a0b\u9759\u9ed8\u5d29\u6e83
            print(f'!! GET {self.path} \u5904\u7406\u5f02\u5e38: {e!r}')
            self._json({'error': '\u670d\u52a1\u5668\u5185\u90e8\u9519\u8bef'}, 500)

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
                          'max': MAX_PLAYERS} for r in ROOMS.values()]
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
        except Exception as e:                      # \u515c\u5e95\uff1a\u4e0d\u8ba9\u5904\u7406\u7ebf\u7a0b\u9759\u9ed8\u5d29\u6e83
            print(f'!! POST {self.path} \u5904\u7406\u5f02\u5e38: {e!r}')
            self._json({'error': '\u670d\u52a1\u5668\u5185\u90e8\u9519\u8bef'}, 500)

    def _handle_post(self):
        p = urlparse(self.path)
        path = p.path
        data = self._read_json()
        if path == '/api/rooms':
            cid = _as_str(data.get('clientId'), 64)
            if not cid:
                return self._json({'error': 'missing clientId'}, 400)
            name = _as_str(data.get('name'), 12) or '\u9009\u624b'
            get_profile(cid, name)
            existing = find_room_by_client(cid)
            if existing:
                return self._json({'roomId': existing.id, 'playerId': cid, 'rejoined': True})
            rid = uuid.uuid4().hex[:6]
            room = Room(rid, cid)
            with ROOMS_LOCK:
                ROOMS[rid] = room
            ok, err = room.add_player(cid, name)
            if not ok:
                with ROOMS_LOCK:
                    ROOMS.pop(rid, None)
                return self._json({'error': err}, 400)
            return self._json({'roomId': rid, 'playerId': cid})
        if path == '/api/join':
            cid = _as_str(data.get('clientId'), 64)
            rid = _as_str(data.get('roomId'), 32)
            name = _as_str(data.get('name'), 12) or '\u9009\u624b'
            if not cid or not rid:
                return self._json({'error': '\u53c2\u6570\u7f3a\u5931'}, 400)
            get_profile(cid, name)
            with ROOMS_LOCK:
                room = ROOMS.get(rid)
                if not room:
                    return self._json({'error': '\u623f\u95f4\u4e0d\u5b58\u5728'}, 404)
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
        if path == '/api/rejoin':
            cid = _as_str(data.get('clientId'), 64)
            if not cid:
                return self._json({'error': 'missing clientId'}, 400)
            room = find_room_by_client(cid)
            if not room:
                return self._json({'error': '\u65e0\u53ef\u7528\u623f\u95f4'}, 404)
            room._touch(cid)
            return self._json({'roomId': room.id, 'playerId': cid})
        if path == '/api/chat':
            pid = _as_str(data.get('playerId'), 64)
            text = data.get('text', '')
            if not pid:
                return self._json({'error': 'missing playerId'}, 400)
            room = find_room_by_client(pid)
            if not room:
                return self._json({'error': '\u4e0d\u5728\u623f\u95f4'}, 404)
            ok, err = room.send_chat(pid, text)
            if not ok:
                return self._json({'error': err}, 400)
            return self._json({'ok': True})
        if path == '/api/action':
            pid = _as_str(data.get('playerId'), 64)
            action = _as_str(data.get('action'), 32)
            if not pid:
                return self._json({'error': 'missing playerId'}, 400)
            room = find_room_by_client(pid)
            if not room:
                return self._json({'error': '\u4e0d\u5728\u623f\u95f4'}, 404)
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
            elif action == 'leave':
                leave_room(pid, room.id, penalize=True)
                return self._json({'ok': True})
            else:
                ok, err = False, f'\u672a\u77e5\u64cd\u4f5c {action}'
            if not ok:
                return self._json({'error': err}, 400)
            return self._json({'ok': True})
        return self._json({'error': f'not found: {path}'}, 404)


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def main():
    STATIC_DIR.mkdir(exist_ok=True)
    load_profiles()
    missing = [f for f in ['index.html', 'style.css', 'script.js']
               if not (STATIC_DIR / f).exists()]
    if missing:
        print('!! \u7f3a\u5c11\u9759\u6001\u6587\u4ef6:', missing)
        if sys.stdin.isatty():
            input('\u6309\u56de\u8f66\u9000\u51fa...')
        return
    print(f'\u5df2\u52a0\u8f7d {len(PROFILES)} \u540d\u73a9\u5bb6\u6863\u6848')
    threading.Thread(target=tick_loop, daemon=True).start()
    try:
        with QuietThreadingTCPServer((HOST, PORT), Handler) as httpd:
            ip = get_local_ip()
            print('=' * 50)
            print('  OI chess \xb7 \u5c40\u57df\u7f51\u670d\u52a1\u5668')
            print(f'  \u672c\u673a:   http://127.0.0.1:{PORT}')
            print(f'  \u5c40\u57df\u7f51: http://{ip}:{PORT}')
            print('=' * 50)
            httpd.serve_forever()
    except OSError as e:
        print(f'!! \u7aef\u53e3 {PORT} \u88ab\u5360\u7528: {e}')
    except KeyboardInterrupt:
        print('\n\u5df2\u505c\u6b62')


if __name__ == '__main__':
    main()