import sys
d = list(map(int, sys.stdin.buffer.read().split()))
n = d[0]
iv = sorted(zip(d[1:2 * n + 1:2], d[2:2 * n + 2:2]))
res = []
for l, r in iv:
    if res and l <= res[-1][1]:
        if r > res[-1][1]:
            res[-1][1] = r
    else:
        res.append([l, r])
sys.stdout.write(f"{len(res)}\n" + "".join(f"{l} {r}\n" for l, r in res))
