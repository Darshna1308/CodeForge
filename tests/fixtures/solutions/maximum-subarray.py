import sys
d = list(map(int, sys.stdin.buffer.read().split()))
a = d[1:1 + d[0]]
best = cur = a[0]
for x in a[1:]:
    cur = x if cur < 0 else cur + x
    best = max(best, cur)
print(best)
