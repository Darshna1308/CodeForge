#include <bits/stdc++.h>
using namespace std;
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n; long long t; cin >> n >> t;
    unordered_map<long long, int> seen; seen.reserve(n * 2);
    for (int j = 0; j < n; ++j) {
        long long x; cin >> x;
        auto it = seen.find(t - x);
        if (it != seen.end()) { cout << it->second << ' ' << j << '\n'; return 0; }
        seen.emplace(x, j);
    }
}
