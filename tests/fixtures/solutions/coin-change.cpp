#include <bits/stdc++.h>
using namespace std;
int main() {
    int n, amount; cin >> n >> amount;
    vector<int> coins(n); for (auto &c : coins) cin >> c;
    vector<int> dp(amount + 1, INT_MAX); dp[0] = 0;
    for (int v = 1; v <= amount; ++v) for (int c : coins) if (c <= v && dp[v - c] != INT_MAX) dp[v] = min(dp[v], dp[v - c] + 1);
    cout << (dp[amount] == INT_MAX ? -1 : dp[amount]) << '\n';
}
