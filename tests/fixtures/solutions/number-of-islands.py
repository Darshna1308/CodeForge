import sys
data = sys.stdin.read().split()
r, c = int(data[0]), int(data[1])
g = [list(row) for row in data[2:2 + r]]
count = 0
for i in range(r):
    for j in range(c):
        if g[i][j] == '1':
            count += 1
            g[i][j] = '0'
            stack = [(i, j)]
            while stack:
                x, y = stack.pop()
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < r and 0 <= ny < c and g[nx][ny] == '1':
                        g[nx][ny] = '0'
                        stack.append((nx, ny))
print(count)
