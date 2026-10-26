s = input().strip()
match = {')': '(', ']': '[', '}': '{'}
st = []
ok = True
for c in s:
    if c in '([{':
        st.append(c)
    elif not st or st.pop() != match[c]:
        ok = False
        break
print("true" if ok and not st else "false")
