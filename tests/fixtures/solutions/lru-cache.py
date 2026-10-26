import sys
from collections import OrderedDict
lines = sys.stdin.read().split("\n")
cap, q = map(int, lines[0].split())
cache = OrderedDict()
out = []
for line in lines[1:1 + q]:
    p = line.split()
    if p[0] == "get":
        k = int(p[1])
        if k in cache:
            cache.move_to_end(k)
            out.append(str(cache[k]))
        else:
            out.append("-1")
    else:
        k, v = int(p[1]), int(p[2])
        cache[k] = v
        cache.move_to_end(k)
        if len(cache) > cap:
            cache.popitem(last=False)
sys.stdout.write("\n".join(out) + "\n")
