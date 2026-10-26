import sys
d = sys.stdin.buffer.read().split()
n, t = int(d[0]), int(d[1])
seen = {}
for j in range(n):
    x = int(d[2 + j])
    if t - x in seen:
        print(seen[t - x], j)
        break
    seen.setdefault(x, j)
