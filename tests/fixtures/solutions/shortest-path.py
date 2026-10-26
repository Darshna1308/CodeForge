import heapq
import sys
d = sys.stdin.buffer.read().split()
n, m, s = int(d[0]), int(d[1]), int(d[2])
adj = [[] for _ in range(n + 1)]
for k in range(m):
    u, v, w = int(d[3 + 3 * k]), int(d[4 + 3 * k]), int(d[5 + 3 * k])
    adj[u].append((v, w))
INF = 1 << 62
dist = [INF] * (n + 1)
dist[s] = 0
pq = [(0, s)]
while pq:
    du, u = heapq.heappop(pq)
    if du != dist[u]:
        continue
    for v, w in adj[u]:
        nd = du + w
        if nd < dist[v]:
            dist[v] = nd
            heapq.heappush(pq, (nd, v))
sys.stdout.write(" ".join(str(x) if x != INF else "-1" for x in dist[1:]) + "\n")
