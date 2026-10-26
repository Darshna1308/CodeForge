import sys
d = sys.stdin.buffer.read().split()
n, q = int(d[0]), int(d[1])
a = list(map(int, d[2:2 + n]))
out = []
for x in map(int, d[2 + n:2 + n + q]):
    lo, hi = 0, n - 1
    ans = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if a[mid] == x:
            ans = mid
            break
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid - 1
    out.append(ans)
sys.stdout.write("\n".join(map(str, out)) + "\n")
