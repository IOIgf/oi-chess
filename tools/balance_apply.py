"""把一份数值改动写进 server.py 的 CARDS_RAW 表。

用法：
    python tools/balance_apply.py balance/proposal.json [--dry-run]

json 格式：{"card_id": {"attack": 64, "hp": 630, "energy": 6, "reason": 9}, ...}
只写给出的字段，其它保持不变。
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, 'server.py')

# ('id', '名称', cost, '难度', coef, 'trait', 攻击, 生命, 精力, 理智, 'skill',
PAT = re.compile(
    r"(\(\s*'(?P<id>[a-z_0-9]+)', '[^']*', (?P<cost>\d+), '[^']*', [\d.]+,\s*"
    r"'[^']*', )(?P<attack>\d+), (?P<hp>\d+), (?P<energy>\d+), (?P<reason>\d+)(, ')"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('patch')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    with open(args.patch, encoding='utf-8') as f:
        patch = json.load(f)

    src = open(SERVER, encoding='utf-8').read()
    seen = {}

    def sub(m):
        cid = m.group('id')
        seen[cid] = True
        vals = {'attack': int(m.group('attack')), 'hp': int(m.group('hp')),
                'energy': int(m.group('energy')), 'reason': int(m.group('reason'))}
        for k, v in patch.get(cid, {}).items():
            if k not in vals:
                raise SystemExit(f'未知字段 {cid}.{k}')
            vals[k] = int(v)
        return (m.group(1) + f"{vals['attack']}, {vals['hp']}, "
                f"{vals['energy']}, {vals['reason']}" + m.group(8))

    out = PAT.sub(sub, src)
    n = len(seen)
    expected = len(__import__('balance_lab').load_server().CARDS)
    if n != expected:
        raise SystemExit(f'只匹配到 {n} 张卡，预期 {expected}，已中止')
    missing = [c for c in patch if c not in seen]
    if missing:
        raise SystemExit(f'以下 id 在卡表里不存在: {missing}')

    changed = sum(1 for c in patch
                  if any(True for _ in patch[c]))
    print(f'匹配 {n} 张卡，{args.dry_run and "预演" or "写入"} {changed} 张卡的改动')
    for cid in sorted(patch):
        print('   ', cid, patch[cid])
    if not args.dry_run:
        open(SERVER, 'w', encoding='utf-8').write(out)
        print('已写入 server.py')


if __name__ == '__main__':
    main()
