#include <bits/stdc++.h>
using namespace std;
int main() {
    string s; cin >> s;
    vector<char> st;
    for (char c : s) {
        if (c == '(' || c == '[' || c == '{') { st.push_back(c); continue; }
        char want = c == ')' ? '(' : c == ']' ? '[' : '{';
        if (st.empty() || st.back() != want) { puts("false"); return 0; }
        st.pop_back();
    }
    puts(st.empty() ? "true" : "false");
}
