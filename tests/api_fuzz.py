"""接口健壮性测试：用各种脏输入打所有接口，要求全部返回 4xx/2xx，绝不能让处理线程崩掉。

用法：
    python server.py          # 另开一个终端把服务器跑起来
    python tests/api_fuzz.py  # 默认打 http://127.0.0.1:8080

失败判据：出现「连接被直接关闭（Remote end closed connection）」或 5xx。
"""
import json
import os
import random
import urllib.request as u

BASE = os.environ.get('OI_BASE', 'http://127.0.0.1:8080').rstrip('/')


def req(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = u.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        with u.urlopen(r) as f:
            return f.status, f.read()[:160]
    except u.HTTPError as e:
        return e.code, e.read()[:160]
    except Exception as e:                       # 连接被服务端掐断 = 处理线程崩了
        return 'DROP', str(e)[:160]


WEIRD = [None, {}, [], 'abc', 123, -1, 10 ** 9, True, False, '', 0, 1,
         '1,2', 'x' * 300, {'a': 1.5}, [1, 2], 3.7]


def main():
    tag = 'fz%d' % random.randint(10 ** 6, 10 ** 7)
    a, b = tag + 'a', tag + 'b'
    s, _ = req('/api/rooms', {'clientId': a, 'name': 'A'})
    assert s == 200, s
    rid = json.loads(_)['roomId']
    req('/api/join', {'clientId': b, 'name': 'B', 'roomId': rid})
    req('/api/action', {'playerId': a, 'action': 'start'})

    bad = []

    def poke(path, body):
        st, resp = req(path, body)
        if st not in (200, 400, 404):
            bad.append((path, json.dumps(body, ensure_ascii=False)[:100], st, resp))
        return st

    for w in WEIRD:
        poke('/api/rooms', {'clientId': w, 'name': w})
        poke('/api/join', {'clientId': w, 'roomId': w, 'name': w})
        poke('/api/chat', {'playerId': a, 'text': w})
        poke('/api/chat', {'playerId': w, 'text': w})
        for act in ('buy', 'sell', 'place', 'retrieve', 'refresh', 'ready', 'zzz'):
            poke('/api/action', {'playerId': a, 'action': act, 'index': w,
                                 'benchIndex': w, 'x': w, 'y': w, 'source': w})
            poke('/api/action', {'playerId': w, 'action': act})
    for q in ('', '?playerId=', '?playerId=%7B%7D', '?playerId=x&haveChat=abc',
              '?playerId=x&haveChat=%7B%7D'):
        poke('/api/state' + q, None)

    # 收尾：清掉测试房间
    req('/api/action', {'playerId': a, 'action': 'leave'})
    req('/api/action', {'playerId': b, 'action': 'leave'})

    print(f'脏输入用例完成，异常 {len(bad)} 条')
    for x in bad[:15]:
        print('  !!', x)
    return 0 if not bad else 1


if __name__ == '__main__':
    raise SystemExit(main())
