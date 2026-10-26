#include <bits/stdc++.h>
using namespace std;
int main() {
    int r, c; cin >> r >> c;
    vector<string> g(r);
    for (auto &row : g) cin >> row;
    int count = 0;
    vector<pair<int,int>> st;
    for (int i = 0; i < r; ++i) for (int j = 0; j < c; ++j) if (g[i][j] == '1') {
        ++count; g[i][j] = '0'; st.push_back({i, j});
        while (!st.empty()) {
            auto [x, y] = st.back(); st.pop_back();
            const int dx[] = {1, -1, 0, 0}, dy[] = {0, 0, 1, -1};
            for (int k = 0; k < 4; ++k) {
                int nx = x + dx[k], ny = y + dy[k];
                if (nx >= 0 && nx < r && ny >= 0 && ny < c && g[nx][ny] == '1') { g[nx][ny] = '0'; st.push_back({nx, ny}); }
            }
        }
    }
    cout << count << '\n';
}
