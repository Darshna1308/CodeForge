s = input()
pos = {}
best = left = 0
for i, c in enumerate(s):
    if c in pos and pos[c] >= left:
        left = pos[c] + 1
    pos[c] = i
    best = max(best, i - left + 1)
print(best)
