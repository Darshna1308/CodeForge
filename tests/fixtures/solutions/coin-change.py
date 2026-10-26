import sys
d = list(map(int, sys.stdin.read().split()))
n, amount = d[0], d[1]
coins = d[2:2 + n]
INF = amount + 1
dp = [0] + [INF] * amount
for c in coins:
    for v in range(c, amount + 1):
        t = dp[v - c] + 1
        if t < dp[v]:
            dp[v] = t
print(dp[amount] if dp[amount] != INF else -1)
