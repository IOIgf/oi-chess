"""SPFA：独立概率卡顿、攻速与伤害倍率。"""
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from balance_lab import SRV as s, make_player
room = s.Room('spfa-test', 'A')
s.CARD_BY_ID['spfa']['hp'] = 100000

def run(roll):
    a = make_player('A', 'spfa', [(3,0)])
    b = make_player('B', 'spfa', [(3,0)])
    with patch.object(s.random, 'random', return_value=roll) as rng:
        _, events, *_ = room._simulate_battle(a,b,3)
    attacks = [e for e in events if e['type']=='attack']
    times = [e['t'] for e in attacks if e['owner']=='A']
    assert rng.call_count == len(attacks)
    return [round(y-x,3) for x,y in zip(times,times[1:])]
assert all(abs(x-4/3)<.001 for x in run(0.20))
assert all(abs(x-(4+4/3))<.001 for x in run(0.199))
u = dict(atk=120, outMult=1, skill='spfa_stall')
assert abs(room._attack_multiplier(u, {}, [], 0, 3) - 120*s.DMG_MULT*1.2) < 1e-8
assert s.SPFA_SPEED_MULT == 1.5
assert s.SPFA_STALL_CHANCE == .2
print('PASS: 20% boundary, independent rolls, speed x1.5, damage x1.2')
