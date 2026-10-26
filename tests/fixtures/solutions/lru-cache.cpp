#include <bits/stdc++.h>
using namespace std;
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int cap, q; cin >> cap >> q;
    list<pair<int,long long>> order;
    unordered_map<int, list<pair<int,long long>>::iterator> pos;
    string op;
    while (q--) {
        cin >> op;
        if (op == "get") {
            int k; cin >> k;
            auto it = pos.find(k);
            if (it == pos.end()) { cout << -1 << '\n'; continue; }
            order.splice(order.begin(), order, it->second);
            cout << it->second->second << '\n';
        } else {
            int k; long long v; cin >> k >> v;
            auto it = pos.find(k);
            if (it != pos.end()) { it->second->second = v; order.splice(order.begin(), order, it->second); continue; }
            order.push_front({k, v}); pos[k] = order.begin();
            if ((int)order.size() > cap) { pos.erase(order.back().first); order.pop_back(); }
        }
    }
}
