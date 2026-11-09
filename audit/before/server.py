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
MAX_BENCH = 10             # 备战席上限
MAX_BOARD = 15             # 场上棋子上限
HALF_W, HALF_H = 8, 4
BATTLE_W, BATTLE_H = 8, 8
PREP_TIME = 30.0
BATTLE_TIME = 30.0
PAIR_LEAD_TIME = 3.0
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
MATRIX_STEP = 1.2
MATRIX_CAP = 3
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

EMPTY_PENALTY_INTERVAL = 2.0
ENERGY_PER_ROUND = 25
SKILL_ENERGY_COST = 1
REASON_PER_ROUND = 16
MIND_WIN = 5
MIND_LOSE = 8

CARDS_RAW = [
    ('linear_dp', '线性 DP', 1, '普及', 0.75, 'dynamic_programming', 41, 401, 4, 4, 'line',
     '沿行/列直线攻击',
     '技能：攻击同行/同列敌人最多的一条线'),
    ('tree_array', '树状数组', 1, '普及', 0.75, 'data_structure', 37, 364, 4, 4, 'stack_ally',
     '友军行动叠层',
     '被动：每名友军行动 +1 层，每层 +8% 攻击（上限 6 层）'),
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
     '被动：击杀后立刻追加一次攻击，最多连续 3 次'),
    ('diff', '差分', 1, '普及', 0.75, 'diff', 31, 298, 4, 4, 'delayed_line',
     '延迟整行伤害',
     '技能：给射程内整行敌人挂延迟伤害，2 秒后结算 150%'),
    ('xor', '异或', 1, '普及', 0.75, 'bitwise', 30, 295, 4, 4, 'swap_stats',
     '交换敌人属性',
     '技能：与射程内攻击最高的敌人交换攻击力，持续 6 秒'),
    ('gcd', 'gcd', 1, '普及', 0.75, 'number_theory', 44, 437, 4, 4, 'link_ally',
     '链接相邻友军',
     '被动：相邻友军受伤时，自身分担 30%'),
    ('bfs', 'BFS', 2, '普及', 0.75, 'search', 50, 500, 6, 9, 'aoe_debuff',
     '全屏扩散，4-8层减益',
     '技能：全场敌人受 35% 伤害并减速 3 秒（攻击间隔 +1 秒）'),
    ('pigeonhole', '鸽巢原理', 2, '普及', 0.75, 'combinatorics', 75, 727, 6, 9, 'crowd_crit',
     '密集必暴击',
     '被动：目标周围 3×3 内除目标外敌人 ≥3 时，本次伤害翻倍'),
    ('prime_sieve', '质数筛', 2, '普及', 0.75, 'math', 64, 636, 6, 9, 'prime_round',
     '质数回合爆发',
     '被动：质数回合伤害 ×1.8'),
    ('mod_op', '模运算', 2, '普及', 0.75, 'math', 62, 619, 6, 9, 'every_n',
     '每第N次攻击触发',
     '被动：每第 3 次普攻造成 2.5 倍伤害'),
    ('shift', '移位', 2, '普及', 0.75, 'bitwise', 76, 754, 6, 9, 'shift_stats',
     '攻击翻倍生命减半',
     '被动：入场攻击 ×2、生命上限 ×0.5'),
    ('range_dp', '区间 DP', 2, '提高', 1.05, 'dynamic_programming', 66, 647, 6, 9, 'range_aoe',
     '连续区间伤害',
     '技能：对目标及其左右相邻格造成 80% 伤害'),
    ('segment_tree', '线段树', 2, '提高', 1.05, 'data_structure', 64, 632, 6, 9, 'charge_burst',
     '蓄力后爆发',
     '被动：每第 4 次普攻造成 3 倍伤害'),
    ('sqrt_block', '分块', 2, '提高', 1.05, 'data_structure', 67, 655, 6, 9, 'block_aoe',
     '2×2 块控制',
     '技能：对目标所在的 2×2 区域造成 70% 伤害'),
    ('pruning', '剪枝', 2, '提高', 1.05, 'search', 55, 539, 6, 9, 'shield_on_low',
     '弱攻击转护盾',
     '被动：单次伤害低于自身攻击力 50% 时，减免 50% 并转化为护盾'),
    ('ids', '迭代加深', 2, '提高', 1.05, 'search', 72, 711, 6, 9, 'grow_range',
     '范围逐回合+1',
     '被动：每回合射程 +1'),
    ('merge_sort', '归并排序', 2, '提高', 1.05, 'divide_conquer', 74, 739, 6, 9, 'merge_ally',
     '合并相邻属性',
     '被动：入场时与相邻友军均分生命值总和'),
    ('quick_sort', '快速排序', 2, '提高', 1.05, 'divide_conquer', 54, 534, 6, 9, 'partition',
     '按攻击分区',
     '技能：对射程内攻击力最高的一半敌人造成 100% 伤害'),
    ('divide', '分治', 2, '提高', 1.05, 'divide_conquer', 57, 558, 6, 9, 'divide_conquer',
     '分段处理再合并',
     '技能：射程内全体受 50% 伤害，若无人阵亡再补一次 100%'),
    ('inverse', '逆元', 2, '提高', 1.05, 'number_theory', 63, 626, 6, 9, 'thorns',
     '受击反伤',
     '被动：受到普攻时反弹 35% 伤害'),
    ('bitmask_dp', '状压 DP', 3, '提高', 1.05, 'dynamic_programming', 82, 813, 9, 16, 'compress_line',
     '压缩整行友军',
     '技能：同一行友军攻击力之和，对该行敌人打出一击'),
    ('monotonic_queue', '单调队列', 3, '提高', 1.05, 'data_structure', 111, 1115, 9, 16, 'sliding_max',
     '滑窗攻击最强者',
     '被动：优先攻击射程内攻击力最高的敌人'),
    ('a_star', 'A*', 3, '提高', 1.05, 'search', 114, 1141, 9, 16, 'finish_weak',
     '打最可能击杀目标',
     '被动：优先攻击射程内生命最低的敌人'),
    ('bidirectional', '双向搜索', 3, '提高', 1.05, 'search', 81, 797, 9, 16, 'pincer',
     '两端夹击',
     '技能：对射程内最近与最远的敌人各造成 120% 伤害'),
    ('fermat', '费马小定理', 3, '提高', 1.05, 'number_theory', 96, 954, 9, 16, 'prime_round',
     '质数回合爆发',
     '被动：质数回合伤害 ×1.8'),
    ('expectation', '期望', 3, '提高', 1.05, 'probability', 98, 970, 9, 16, 'expectation',
     '随机转固定',
     '被动：伤害无随机浮动，恒定 ×1.25'),
    ('sweep_line', '扫描线', 3, '提高', 1.05, 'geometry', 87, 870, 9, 16, 'sweep',
     '线上递增伤害',
     '技能：同一行敌人按距离由近到远，受 60%/90%/120% 递增伤害'),
    ('cdq', 'CDQ 分治', 3, '省选', 1.25, 'divide_conquer', 96, 961, 9, 16, 'cdq',
     '前弱后爆',
     '被动：战斗前 10 秒伤害 ×0.6，之后 ×1.8'),
    ('spfa', 'SPFA', 3, '提高', 1.05, 'search', 120, 1100, 9, 16, 'spfa_stall',
     '平时跑得飞快，遇到数据就卡了',
     '被动：攻速 ×1.5，普攻伤害 ×1.2；每次普攻后有 20% 概率「卡了」，下一次普攻额外延迟 4 秒'),
    ('o2', 'O2 优化', 3, '提高', 1.05, 'optimization', 0, 280, 9, 16, 'o2_aura',
     '自己不跑，让队友跑得更快',
     '被动：无法攻击，原地为周围八格友军提供攻速 ×2；同名光环不叠加，离开范围或自身阵亡后失效'),
    ('genetic', '遗传算法', 4, '省选', 1.25, 'search', 152, 1510, 13, 25, 'genetic',
     '继承并变异',
     '被动：每次击杀永久 +15% 攻击（最多 3 层）'),
    ('matrix_pow', '矩阵快速幂', 5, '省选', 1.25, 'math', 155, 1545, 15, 31, 'matrix_pow',
     '攻击×1.5，生命-10%',
     '被动：入场攻击 ×1.5、生命上限 ×0.9；每 6 秒攻击 ×1.2（最多 3 层）'),
]

RANGE_BY_COST = {1: 4, 2: 4, 3: 5, 4: 6, 5: 8}

ACTIVE_SKILLS = frozenset({
    'line', 'multi', 'aoe', 'aoe_debuff', 'block_aoe', 'range_aoe',
    'delayed_line', 'swap_stats', 'sort_line', 'compress_line',
    'pincer', 'partition', 'divide_conquer', 'sweep',
})

SHOP_ODDS = {
    1:  {1: 50, 2: 33, 3: 13, 4: 3,  5: 1},
    2:  {1: 45, 2: 34, 3: 15, 4: 5,  5: 1},
    3:  {1: 40, 2: 35, 3: 15, 4: 7,  5: 3},
    4:  {1: 35, 2: 35, 3: 18, 4: 9,  5: 3},
    5:  {1: 30, 2: 34, 3: 21, 4: 11, 5: 4},
    6:  {1: 25, 2: 32, 3: 23, 4: 14, 5: 6},
    7:  {1: 21, 2: 30, 3: 25, 4: 16, 5: 8},
    8:  {1: 17, 2: 27, 3: 27, 4: 19, 5: 10},
    9:  {1: 13, 2: 24, 3: 28, 4: 22, 5: 13},
    10: {1: 10, 2: 21, 3: 28, 4: 24, 5: 17},
}

CARDS = [{
    'id': c[0], 'name': c[1], 'cost': c[2], 'difficulty': c[3], 'coef': c[4],
    'trait': c[5], 'attack': c[6], 'hp': c[7], 'energy': c[8], 'reason': c[9],
    'skill': c[10], 'flavor': c[11], 'desc': c[12],
    'range': RANGE_BY_COST.get(c[2], 4),
    'active': c[10] in ACTIVE_SKILLS,
    'skillCost': SKILL_ENERGY_COST if c[10] in ACTIVE_SKILLS else 0,
} for c in CARDS_RAW]
CARD_BY_ID = {c['id']: c for c in CARDS}


def _fill_card_max_hp():
    """把有效生命上限（移位 ×0.5 / 矩阵快速幂 ×0.9）写进卡表，供前端显示。"""
    for c in CARDS:
        c['maxHp'] = effective_max_hp(c)

TRAITS = {
    'dynamic_programming': '动态规划', 'data_structure': '数据结构',
    'greedy': '贪心/排序', 'search': '搜索', 'divide_conquer': '分治',
    'diff': '差分', 'bitwise': '位运算', 'number_theory': '数论',
    'combinatorics': '组合数学', 'probability': '概率期望',
    'geometry': '计算几何', 'math': '数学', 'optimization': '优化',
}

DATA_LOCK = threading.RLock()
PROFILES = {}
DEFAULT_RATING = 1000
RATING_LOSE = -20
RATING_QUIT = -30


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


def effective_max_hp(card):
    m = float(card['hp'])
    if card['skill'] == 'shift_stats':
        m *= 0.5
    elif card['skill'] == 'matrix_pow':
        m *= 0.9
    return int(m)


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
            DATA_FILE.write_text(json.dumps(PROFILES, ensure_ascii=False, indent=2), 'utf-8')
        except Exception:
            pass


def get_profile(cid, name=None):
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
    return {'card': card_id, 'hp': effective_max_hp(card)}


def new_player(pid, name):
    return {
        'id': pid, 'name': name,
        'hp': 100, 'gold': 10, 'level': 1,
        'mind': 100, 'reason': 100, 'energy': 100,
        'board': {}, 'bench': [], 'shop': [],
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
        self._tick_busy = False
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
    def _roll_shop(self, level):
        odds = SHOP_ODDS.get(max(1, min(10, int(level))), SHOP_ODDS[3])
        pool = []
        for c in CARDS:
            w = odds.get(c['cost'], 0)
            if w:
                pool.extend([c['id']] * w)
        if not pool:
            pool = [c['id'] for c in CARDS]
        return [random.choice(pool) for _ in range(5)]

    def _roll_all_shops(self):
        for p in self.players.values():
            if p.get('dead') or p.get('abandoned'):
                continue
            p['shop'] = self._roll_shop(p['level'])

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
        self.prep_end = time.time() + PREP_TIME
        self.pairs_computed = False
        for p in self.players.values():
            if p.get('dead'):
                continue
            p['ready'] = False
            if not first:
                for store in (p['board'], p['bench']):
                    items = store.values() if isinstance(store, dict) else store
                    for info in items:
                        card = CARD_BY_ID[info['card']]
                        max_hp = effective_max_hp(card)
                        cur_hp = int(info.get('hp', max_hp))
                        info['hp'] = int(min(max_hp, cur_hp + (max_hp - cur_hp) * 0.7))

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

    def refresh_shop(self, pid):
        with self.lock:
            p, err = self._prep_player(pid)
            if err:
                return False, err
            if p['gold'] < 2:
                return False, '金币不足'
            p['gold'] -= 2
            p['shop'] = self._roll_shop(p['level'])
            self.version += 1
            return True, None

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
            if len(p['bench']) >= MAX_BENCH:
                return False, '备战席已满'
            p['gold'] -= card['cost']
            p['energy'] -= card['energy']
            p['reason'] -= card['reason']
            p['bench'].append(make_card_obj(card['id']))
            p['shop'].pop(shop_index)
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
            p['gold'] += card['cost']
            p['energy'] = min(100, p['energy'] + card['energy'] // 2)
            p['reason'] = min(100, p['reason'] + card['reason'] // 2)
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

            a['board'] = {k: info for k, info in a['board'].items() if k in a_hp_map}
            for key in a['board']:
                a['board'][key]['hp'] = int(a_hp_map[key])
            b['board'] = {k: info for k, info in b['board'].items() if k in b_hp_map}
            for key in b['board']:
                b['board'][key]['hp'] = int(b_hp_map[key])

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

            a_alive = len(a['board'])
            b_alive = len(b['board'])
            events = pair.get('events', [])
            a_dmg = sum(e.get('dmg', 0) for e in events if e.get('owner') == a['id'])
            b_dmg = sum(e.get('dmg', 0) for e in events if e.get('owner') == b['id'])

            def _gold_for(p, my_dmg, opp):
                perf = math.sqrt(max(0.0, my_dmg) / 50.0) + math.sqrt(len(opp['board'])) * 1.5
                bonus = min(10, int(perf))
                return min(24, max(18, int((10 + bonus) * 1.2)))

            if a_alive == b_alive:
                for p, my_dmg, opp in ((a, a_dmg, b), (b, b_dmg, a)):
                    p['lastResult'] = 'draw'
                    p['gold'] = _gold_for(p, my_dmg, opp)
            else:
                a_win = a_alive > b_alive
                b_win = b_alive > a_alive
                for p, win, opp, my_dmg in ((a, a_win, b, a_dmg), (b, b_win, a, b_dmg)):
                    if win:
                        p['lastResult'] = 'win'
                        p['roundWins'] += 1
                        p['mind'] = min(MIND_MAX, p['mind'] + MIND_WIN)
                    else:
                        p['lastResult'] = 'lose'
                        p['roundLosses'] += 1
                        p['hp'] = max(0, p['hp'] - 10 - len(opp['board']))
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
            if len(p['bench']) < MAX_BENCH:
                p['bench'].append(make_card_obj(random.choice([c['id'] for c in CARDS])))

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
        hp = int(info.get('hp', effective_max_hp(card)))
        if hp <= 0:
            return None
        max_hp = float(card['hp'])
        atk = float(card['attack'])
        rng = float(card['range'])
        skill = card['skill']
        if skill == 'shift_stats':
            atk *= 2.0
            max_hp *= 0.5
            hp = min(hp, max_hp)
        elif skill == 'matrix_pow':
            atk *= 1.5
            max_hp *= 0.9
            hp = min(hp, max_hp)
        if skill == 'grow_range':
            rng += max(0, round_no - 1)
        by = y + HALF_H if side == 'a' else (HALF_H - 1 - y)
        return {
            'uid': f'{owner}:{key}', 'owner': owner, 'origKey': key, 'side': side,
            'card': card['id'], 'x': x, 'y': by,
            'hp': float(hp), 'maxHp': max_hp,
            'atk': atk, 'range': rng, 'skill': skill,
            'active': skill in ACTIVE_SKILLS,
            'atkCd': 0.0, 'skillCd': 0.0, 'slowUntil': -1.0,
            'stallUntil': -1.0, 'actionUntil': -1.0,
            'shield': 0.0, 'stacks': 0, 'hits': 0, 'charge': 0, 'kills': 0,
            'outMult': stats[owner]['out'], 'inMult': stats[owner]['in'],
            'swap': None, 'delayed': [],
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
        for u in units:
            if u['skill'] != 'merge_ally':
                continue
            group = [u] + [o for o in units
                           if o['owner'] == u['owner'] and o is not u and self._dist(u, o) == 1]
            if len(group) < 2:
                continue
            avg = sum(g['hp'] for g in group) / len(group)
            for g in group:
                g['hp'] = float(min(g['maxHp'], max(1.0, avg)))

    def _pick_target(self, u, enemies):
        sk = u['skill']
        if sk == 'finish_weak':
            return min(enemies, key=lambda e: (e['hp'], self._dist(u, e)))
        if sk == 'sliding_max':
            return min(enemies, key=lambda e: (-e['atk'], self._dist(u, e)))
        return min(enemies, key=lambda e: (self._dist(u, e), e['hp']))

    def _deal_damage(self, target, raw, events, t, units, by_uid,
                     source=None, is_attack=False, allow_react=True):
        dmg = max(1, int(raw * target['inMult']))

        if target['skill'] == 'shield_on_low' and source is not None \
                and dmg < target['atk'] * SHIELD_ON_LOW_ATK:
            # 旧规则是「伤害低于自身攻击力就完全免疫」，在全局伤害 ×1/3 的设定下
            # 等于对同费及以下的攻击者永久无敌。现在改成按比例减免 + 转护盾。
            conv = int(dmg * SHIELD_ON_LOW_CONVERT)
            if conv > 0:
                target['shield'] = min(target['maxHp'] * SHIELD_CAP_RATIO,
                                       target['shield'] + conv)
                dmg -= conv
                events.append({'t': round(t, 6), 'type': 'shield',
                               'x': int(target['x']), 'y': int(target['y']),
                               'owner': target['owner'], 'dmg': 0})
                if dmg <= 0:
                    return 0

        dealt = dmg

        if allow_react:
            links = [o for o in units
                     if o['hp'] > 0 and o is not target and o['owner'] == target['owner']
                     and o['skill'] == 'link_ally' and self._dist(o, target) == 1]
            if links and dmg > 1:
                total_share = min(max(1, int(dmg * LINK_SHARE)), dmg - 1)
                per = max(1, total_share // len(links))
                actual = 0
                killed = 0
                for o in links:
                    take = min(per, total_share - actual)
                    if take <= 0:
                        break
                    o['hp'] -= take
                    actual += take
                    if o['hp'] <= 0:
                        killed += 1
                dealt = max(0, dmg - actual)
                if killed and source is not None and source.get('skill') == 'genetic':
                    source['kills'] = min(GENETIC_CAP, source['kills'] + killed)

        if target['shield'] > 0 and dealt > 0:
            absorbed = min(target['shield'], dealt)
            target['shield'] -= absorbed
            dealt -= absorbed

        if dealt > 0:
            target['hp'] -= dealt

        if is_attack and allow_react and source is not None and dealt > 0 \
                and target['skill'] == 'thorns' and source['hp'] > 0:
            back = max(1, int(dealt * THORNS_RATIO))
            source['hp'] -= back
            events.append({'t': round(t + 0.05, 6), 'type': 'attack',
                           'fromX': int(target['x']), 'fromY': int(target['y']),
                           'toX': int(source['x']), 'toY': int(source['y']),
                           'dmg': back, 'owner': target['owner'], 'thorns': True})
        return dealt

    def _attack_multiplier(self, u, target, units, t, round_no):
        base = u['atk'] * DMG_MULT * u['outMult']
        sk = u['skill']
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
            u['hits'] += 1
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
        return base

    def _do_attack(self, u, target, units, events, t, by_uid, round_no):
        if u['skill'] == 'o2_aura':
            return
        raw = self._attack_multiplier(u, target, units, t, round_no)
        dealt = self._deal_damage(target, raw, events, t, units, by_uid,
                                  source=u, is_attack=True)
        events.append({'t': round(t, 6), 'type': 'attack',
                       'fromX': int(u['x']), 'fromY': int(u['y']),
                       'toX': int(target['x']), 'toY': int(target['y']),
                       'dmg': dealt, 'owner': u['owner']})

        for o in units:
            if o is not u and o['hp'] > 0 and o['owner'] == u['owner'] \
                    and o['skill'] == 'stack_ally':
                o['stacks'] = min(STACK_ALLY_CAP, o['stacks'] + 1)

        if target['hp'] > 0:
            return
        if u['skill'] == 'genetic':
            u['kills'] = min(GENETIC_CAP, u['kills'] + 1)
        elif u['skill'] == 'chain_kill' and u['kills'] < 3:
            u['kills'] += 1
            rest = [e for e in units if e['hp'] > 0 and e['owner'] != u['owner']]
            if rest:
                nxt = self._pick_target(u, rest)
                if self._dist(u, nxt) <= u['range']:
                    self._do_attack(u, nxt, units, events, t + 0.15, by_uid, round_no)

    def _use_skill(self, u, target, enemies, units, events, t, by_uid, round_no):
        sk = u['skill']
        events.append({'t': round(t, 6), 'type': 'skill',
                       'x': int(u['x']), 'y': int(u['y']),
                       'owner': u['owner'], 'name': sk})

        def hit(e, mult, delay=0.1, extra=None):
            raw = u['atk'] * DMG_MULT * u['outMult'] * mult
            dealt = self._deal_damage(e, raw, events, t, units, by_uid, source=u)
            ev = {'t': round(t + delay, 6), 'type': 'attack',
                  'fromX': int(u['x']), 'fromY': int(u['y']),
                  'toX': int(e['x']), 'toY': int(e['y']),
                  'dmg': dealt, 'owner': u['owner'], 'skill': True}
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
            for i in range(3):
                if target['hp'] <= 0:
                    break
                hit(target, 0.5, 0.1 + i * 0.15)
        elif sk == 'line':
            row = [e for e in enemies if e['y'] == u['y']]
            col = [e for e in enemies if e['x'] == u['x']]
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
                   if 0 <= e['x'] - target['x'] <= 1 and 0 <= e['y'] - target['y'] <= 1]
            for e in (box or [target]):
                hit(e, 0.7)
        elif sk == 'delayed_line':
            row = [e for e in enemies if e['y'] == target['y']] or [target]
            for e in row:
                amount = u['atk'] * DMG_MULT * u['outMult'] * 1.5
                e['delayed'].append((t + 2.0, amount, u['uid']))
        elif sk == 'swap_stats':
            # 卡面写的是“攻击最高的敌人”，目标本身也在候选里
            other = max(enemies, key=lambda e: e['atk'])
            ua, oa = u['atk'], other['atk']
            u['atk'], other['atk'] = oa, ua
            u['swap'] = (ua, t + SWAP_DURATION)
            other['swap'] = (oa, t + SWAP_DURATION)
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
            row = [e for e in enemies if e['y'] == u['y']] or [target]
            for e in row:
                hit(e, total_atk / max(1e-6, u['atk']))
        elif sk == 'pincer':
            near = min(enemies, key=lambda e: self._dist(u, e))
            far = max(enemies, key=lambda e: self._dist(u, e))
            hit(near, 1.2)
            if far is not near:
                hit(far, 1.2, 0.2)
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
                    hit(e, 1.0, 0.4)
        elif sk == 'sweep':
            row = sorted([e for e in enemies if e['y'] == target['y']] or [target],
                         key=lambda e: abs(e['x'] - u['x']))
            for i, e in enumerate(row[:3]):
                hit(e, 0.6 + 0.3 * i)

    def _simulate_battle(self, a, b, round_no):
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
            frames.append({
                't': round(now, 6),
                'units': [{
                    'uid': u['uid'], 'owner': u['owner'],
                    'x': int(u['x']), 'y': int(u['y']),
                    'hp': max(0, int(u['hp'])), 'maxHp': int(u['maxHp']),
                    'shield': max(0, int(u['shield'])),
                    'card': u['card'], 'slowed': u['slowUntil'] > t,
                } for u in units if u['hp'] > 0],
            })

        # 攻击/技能/状态到期使用事件时间；移动仍每 TICK_SEC 一次。
        # 不缩小全局 tick，也不把冷却余量向上取整。
        eps = 1e-9
        next_move = 0.0
        snap(0.0)
        while t < BATTLE_TIME - eps:
            move_now = t >= next_move - eps
            if move_now:
                next_move += TICK_SEC
            for u in units:
                if u['delayed']:
                    due = [d for d in u['delayed'] if d[0] <= t + eps]
                    u['delayed'] = [d for d in u['delayed'] if d[0] > t + eps]
                    for _, amount, src_uid in due:
                        src = by_uid.get(src_uid)
                        self._deal_damage(u, amount, events, t, units, by_uid,
                                          source=src if src and src['hp'] > 0 else None)
                if u['hp'] <= 0:
                    continue
                if u['swap'] and t >= u['swap'][1] - eps:
                    u['atk'], u['swap'] = u['swap'][0], None
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
                                # 保留原有施法占用一次行动的规则。
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
                        # 单位不能进入已被其他存活单位占据的格子，避免战斗帧出现棋子重叠。
                        if (nx, ny) in occupied:
                            continue
                        u['x'], u['y'] = nx, ny
                        break


            # 存储真实事件时刻的状态；重复时间戳替换初始快照。
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
                if u['swap'] and u['swap'][1] > t + eps:
                    next_t = min(next_t, u['swap'][1])
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

            # 区间内光环、减速和卡顿状态不变；积分准备进度。
            dt = next_t - t
            for u in units:
                if u['hp'] <= 0:
                    continue
                work_dt = max(0.0, next_t - max(t, u['stallUntil']))
                u['atkCd'] = max(0.0, u['atkCd'] - work_dt * self._attack_rate(u, units, t))
                u['skillCd'] = max(0.0, u['skillCd'] - dt)
            t = next_t
        if frames[-1]['t'] < round(t, 6):
            snap(t)

        a_hp, b_hp = {}, {}
        for u in units:
            if u['hp'] > 0:
                (a_hp if u['side'] == 'a' else b_hp)[u['origKey']] = int(u['hp'])

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
            mx = effective_max_hp(card)
            hp = int(info.get('hp', mx))
            if hp <= 0:
                continue
            units.append({'uid': f'{viewer_id}:{key}', 'owner': viewer_id,
                          'x': x, 'y': y + HALF_H, 'hp': hp, 'maxHp': mx,
                          'shield': 0, 'card': info['card'], 'slowed': False})
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
                'lastResult': p['lastResult'],
                'roundWins': p['roundWins'], 'roundLosses': p['roundLosses']}

    def get_state(self, viewer_id=None, have_chat=-1):
        with self.lock:
            if viewer_id:
                self._touch(viewer_id)
            players_out = {}
            for cid, p in self.players.items():
                row = self._public_player(cid, p, self.colors.get(cid, 0))
                if cid == viewer_id:
                    row.update({'board': p['board'], 'bench': p['bench'],
                                'shop': p['shop'], 'ready': p['ready']})
                players_out[cid] = row

            side, _frames, _events, opp, bye = self._viewer_battle(viewer_id)
            now = time.time()
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
            cand = [c for c, pl in r.players.items() if not pl.get('abandoned')]
            if cand:
                r.host = cand[0]
                r._sys_chat(f'{r.players[r.host]["name"]} 成为新房主')

        r.version += 1
        if in_game:
            r._check_game_over()

        with ROOMS_LOCK:
            alive = [pl for pl in r.players.values() if not pl.get('abandoned')]
            if not alive:
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
        cand = [c for c, pl in r.players.items() if not pl.get('abandoned')]
        if cand:
            r.host = cand[0]
            r._sys_chat(f'{r.players[r.host]["name"]} 成为新房主')
            r.version += 1

    # 3. 对局中掉线后重新判定对局是否结束
    if r.state in ('prep', 'battle'):
        r._check_game_over()

    # 4. 房间回收：没有活人
    alive = [pl for pl in r.players.values() if not pl.get('abandoned')]
    if not alive:
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
        r._tick_busy = False


_last_cleanup_at = 0.0


def tick_loop():
    global _last_cleanup_at
    while True:
        time.sleep(0.15)
        now = time.time()
        with ROOMS_LOCK:
            rooms = list(ROOMS.values())
        for r in rooms:
            if getattr(r, '_tick_busy', False):
                continue
            r._tick_busy = True
            _tick_pool.submit(_tick_room, r)
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
            return self._json(room.get_state(pid, have_chat))
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
            return self._json({'cards': CARDS, 'traits': TRAITS})
        return self._json({'error': f'not found: {path}'}, 404)

    def do_POST(self):
        try:
            self._handle_post()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:                      # 兜底：不让处理线程静默崩溃
            print(f'!! POST {self.path} 处理异常: {e!r}')
            self._json({'error': '服务器内部错误'}, 500)

    def _handle_post(self):
        p = urlparse(self.path)
        path = p.path
        data = self._read_json()
        if path == '/api/rooms':
            cid = _as_str(data.get('clientId'), 64)
            if not cid:
                return self._json({'error': 'missing clientId'}, 400)
            name = _as_str(data.get('name'), 12) or '选手'
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
        if path == '/api/rejoin':
            cid = _as_str(data.get('clientId'), 64)
            if not cid:
                return self._json({'error': 'missing clientId'}, 400)
            room = find_room_by_client(cid)
            if not room:
                return self._json({'error': '无可用房间'}, 404)
            room._touch(cid)
            return self._json({'roomId': room.id, 'playerId': cid})
        if path == '/api/chat':
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
        if path == '/api/action':
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
            elif action == 'leave':
                leave_room(pid, room.id, penalize=True)
                return self._json({'ok': True})
            else:
                ok, err = False, f'未知操作 {action}'
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
        print('!! 缺少静态文件:', missing)
        if sys.stdin.isatty():
            input('按回车退出...')
        return
    print(f'已加载 {len(PROFILES)} 名玩家档案')
    threading.Thread(target=tick_loop, daemon=True).start()
    try:
        with QuietThreadingTCPServer((HOST, PORT), Handler) as httpd:
            ip = get_local_ip()
            print('=' * 50)
            print('  OI chess · 局域网服务器')
            print(f'  本机:   http://127.0.0.1:{PORT}')
            print(f'  局域网: http://{ip}:{PORT}')
            print('=' * 50)
            httpd.serve_forever()
    except OSError as e:
        print(f'!! 端口 {PORT} 被占用: {e}')
    except KeyboardInterrupt:
        print('\n已停止')


if __name__ == '__main__':
    main()