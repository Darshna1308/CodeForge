#include <bits/stdc++.h>
using namespace std;
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n, m, s; cin >> n >> m >> s;
    vector<vector<pair<int,long long>>> adj(n + 1);
    for (int i = 0; i < m; ++i) { int u, v; long long w; cin >> u >> v >> w; adj[u].push_back({v, w}); }
    const long long INF = LLONG_MAX;
    vector<long long> dist(n + 1, INF);
    priority_queue<pair<long long,int>, vector<pair<long long,int>>, greater<>> pq;
    dist[s] = 0; pq.push({0, s});
    while (!pq.empty()) {
        auto [d, u] = pq.top(); pq.pop();
        if (d != dist[u]) continue;
        for (auto [v, w] : adj[u]) if (d + w < dist[v]) { dist[v] = d + w; pq.push({dist[v], v}); }
    }
    for (int i = 1; i <= n; ++i) cout << (dist[i] == INF ? -1 : dist[i]) << (i == n ? '\n' : ' ');
}
