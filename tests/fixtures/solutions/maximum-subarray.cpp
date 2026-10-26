#include <bits/stdc++.h>
int main() {
    int n; scanf("%d", &n);
    long long best = LLONG_MIN, cur = 0;
    for (int i = 0; i < n; ++i) { long long x; scanf("%lld", &x); cur = std::max(x, cur + x); best = std::max(best, cur); }
    printf("%lld\n", best);
}
