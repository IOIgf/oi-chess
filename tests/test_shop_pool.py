"""按等级解锁的商店卡池：等级 1 与旧版一致，高等级只新增高费卡。"""
import sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as s

r = s.Room('shop-probe', 'A')

# 等级 1 必须与旧版「只出最低费棋子」行为完全一致
ids, w = r._shop_pool(1)
assert ids and all(s.CARD_BY_ID[i]['cost'] == s.SHOP_MIN_COST for i in ids)
assert len(set(ids)) == len(ids)
assert all(x == 1 for x in w)
assert set(r._roll_shop(1, 200)) <= set(ids)

# 每个等级解锁的费用上限正确，且卡池随等级单调扩张
prev = set()
for lv in range(1, s.SHOP_MAX_COST + 1):
    ids, w = r._shop_pool(lv)
    costs = {s.CARD_BY_ID[i]['cost'] for i in ids}
    assert max(costs) == lv, (lv, costs)
    assert set(ids) >= prev
    prev = set(ids)

# 低费权重严格高于高费
ids, w = r._shop_pool(5)
by_cost = {}
for i, weight in zip(ids, w):
    by_cost.setdefault(s.CARD_BY_ID[i]['cost'], set()).add(weight)
for c in range(1, s.SHOP_MAX_COST):
    assert min(by_cost[c]) > max(by_cost[c + 1])

# 抽样：等级 1 全 1 费；等级 3 出现 2/3 费且低费仍占多数
d1 = collections.Counter(s.CARD_BY_ID[i]['cost'] for i in r._roll_shop(1, 4000))
assert set(d1) == {1}
d3 = collections.Counter(s.CARD_BY_ID[i]['cost'] for i in r._roll_shop(3, 20000))
assert set(d3) == {1, 2, 3}
assert d3[1] > d3[2] > d3[3]

# 每轮赠送卡也走等级卡池，等级 1 不会白送 5 费核心
gifts = [r._roll_shop(1, 1)[0] for _ in range(500)]
assert all(s.CARD_BY_ID[i]['cost'] == 1 for i in gifts)

# 卡池改动不得触碰卡牌数值或战斗常量
assert len(s.CARDS) == 50
assert s.CARD_BY_ID['o2']['hp'] == 280 and s.CARD_BY_ID['spfa']['hp'] == 1000

# 升星保底：差一张即可合成的卡在商店里权重 ×4，缓解 50 张卡池的稀释。
two = {'board': {'0,0': s.make_card_obj('greedy'),
                 '1,0': s.make_card_obj('greedy')},
       'bench': []}
one = {'board': {'0,0': s.make_card_obj('greedy')}, 'bench': []}
assert r._near_merge_ids(two) == {'greedy'}
assert r._near_merge_ids(one) == set()
base = collections.Counter(r._roll_shop(1, 20000))
pity = collections.Counter(r._roll_shop(1, 20000, owner=two))
assert pity['greedy'] > base['greedy'] * 2, (base['greedy'], pity['greedy'])
# 无 owner 时行为必须与旧版完全一致（保底不改变默认卡池分布）。
assert set(r._roll_shop(1, 200)) <= set(r._shop_pool(1)[0])

print('PASS shop pool: level 1 == legacy 1-cost-only, unlocks 1..L, '
      'weights ordered, gift uses level pool, merge pity, card data unchanged')
