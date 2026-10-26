"""Seed problem set: original statements, deterministic test generators, reference solutions.

Expected outputs are *computed* at seed time by the reference solutions below
(trusted code, never user input), so every hidden test is self-consistent.
Independent submitted-style solutions in tests/fixtures/solutions/ are judged
against these outputs by the end-to-end tests, cross-checking both.
"""

import heapq
import random
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Sample:
    input: str
    explanation: str | None = None


@dataclass
class ProblemDef:
    slug: str
    title: str
    difficulty: str
    tags: list[str]
    statement: str
    input_spec: str
    output_spec: str
    constraints: str
    solve: Callable[[str], str]
    samples: list[Sample]
    hidden: Callable[[random.Random], list[str]]
    time_limit_ms: int = 2000
    memory_limit_mb: int = 256
    extra: dict = field(default_factory=dict)


def _ints(s: str) -> list[int]:
    return [int(x) for x in s.split()]


# --------------------------------------------------------------------------- 1
def solve_two_sum(inp: str) -> str:
    data = _ints(inp)
    n, target, a = data[0], data[1], data[2:]
    seen: dict[int, int] = {}
    for j, x in enumerate(a[:n]):
        if target - x in seen:
            return f"{seen[target - x]} {j}\n"
        seen.setdefault(x, j)
    raise ValueError("no pair")


def gen_two_sum(rng: random.Random) -> list[str]:
    def make(n: int, lo: int, hi: int) -> str:
        while True:
            a = [rng.randint(lo, hi) for _ in range(n)]
            i, j = sorted(rng.sample(range(n), 2))
            t = a[i] + a[j]
            counts: dict[int, int] = {}
            pairs = 0
            for x in a:
                pairs += counts.get(t - x, 0)
                counts[x] = counts.get(x, 0) + 1
            if pairs == 1:
                return f"{n} {t}\n{' '.join(map(str, a))}\n"

    return [
        "2 0\n-5 5\n",
        "3 6\n3 2 4\n",
        "4 -8\n-3 -5 10 7\n",
        make(10, -20, 20),
        make(100, -1000, 1000),
        make(1000, -10**9, 10**9),
        make(50000, -10**9, 10**9),
        make(100000, -10**9, 10**9),
    ]


# --------------------------------------------------------------------------- 2
def solve_valid_parentheses(inp: str) -> str:
    s = inp.strip()
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif not stack or stack.pop() != pairs[ch]:
            return "false\n"
    return "true\n" if not stack else "false\n"


def gen_valid_parentheses(rng: random.Random) -> list[str]:
    def balanced(n: int) -> str:
        out, stack = [], []
        opens = "([{"
        close = {"(": ")", "[": "]", "{": "}"}
        while len(out) + len(stack) < n:
            if stack and (rng.random() < 0.45 or len(out) + 2 * len(stack) >= n):
                out.append(close[stack.pop()])
            else:
                c = rng.choice(opens)
                stack.append(c)
                out.append(c)
        while stack:
            out.append(close[stack.pop()])
        return "".join(out)

    def corrupt(s: str) -> str:
        i = rng.randrange(len(s))
        repl = rng.choice([c for c in "()[]{}" if c != s[i]])
        return s[:i] + repl + s[i + 1:]

    cases = ["(", "]", "([)]", "{[]}()", "((((((((((", "(" * 50000 + ")" * 50000]
    for n in (20, 200, 5000, 100000):
        b = balanced(n)
        cases += [b, corrupt(b)]
    return [c + "\n" for c in cases]


# --------------------------------------------------------------------------- 3
def solve_binary_search(inp: str) -> str:
    import bisect

    data = _ints(inp)
    n, q = data[0], data[1]
    a = data[2:2 + n]
    out = []
    for x in data[2 + n:2 + n + q]:
        i = bisect.bisect_left(a, x)
        out.append(str(i if i < n and a[i] == x else -1))
    return "\n".join(out) + "\n"


def gen_binary_search(rng: random.Random) -> list[str]:
    def make(n: int, q: int, span: int) -> str:
        a = sorted(rng.sample(range(-span, span), n))
        qs = [rng.choice(a) if rng.random() < 0.5 else rng.randint(-span - 5, span + 5) for _ in range(q)]
        return f"{n} {q}\n{' '.join(map(str, a))}\n{' '.join(map(str, qs))}\n"

    return [
        "1 2\n7\n7 8\n",
        "5 5\n-10 -3 0 4 9\n-10 9 4 5 -11\n",
        make(10, 10, 20),
        make(1000, 1000, 10**6),
        make(100000, 100000, 10**9),
        make(100000, 100000, 200000),
    ]


# --------------------------------------------------------------------------- 4
def solve_max_subarray(inp: str) -> str:
    data = _ints(inp)
    a = data[1:1 + data[0]]
    best = cur = a[0]
    for x in a[1:]:
        cur = max(x, cur + x)
        best = max(best, cur)
    return f"{best}\n"


def gen_max_subarray(rng: random.Random) -> list[str]:
    def make(n: int, lo: int = -10**4, hi: int = 10**4) -> str:
        return f"{n}\n{' '.join(str(rng.randint(lo, hi)) for _ in range(n))}\n"

    return [
        "1\n-7\n", "3\n-3 -1 -2\n", "5\n1 2 3 4 5\n",
        make(10), make(1000), make(1000, -10**4, -1), make(100000), make(100000, -100, 120),
    ]


# --------------------------------------------------------------------------- 5
def solve_merge_intervals(inp: str) -> str:
    data = _ints(inp)
    n = data[0]
    iv = sorted((data[1 + 2 * i], data[2 + 2 * i]) for i in range(n))
    merged: list[list[int]] = []
    for l, r in iv:
        if merged and l <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], r)
        else:
            merged.append([l, r])
    return f"{len(merged)}\n" + "".join(f"{l} {r}\n" for l, r in merged)


def gen_merge_intervals(rng: random.Random) -> list[str]:
    def make(n: int, span: int, max_len: int) -> str:
        lines = []
        for _ in range(n):
            l = rng.randint(0, span)
            lines.append(f"{l} {l + rng.randint(0, max_len)}")
        return f"{n}\n" + "\n".join(lines) + "\n"

    return [
        "1\n5 5\n", "2\n1 3\n3 5\n", "3\n10 20\n0 1\n2 3\n",
        make(10, 50, 10), make(1000, 10**6, 1000), make(100000, 10**9, 10**4), make(100000, 10**5, 50),
    ]


# --------------------------------------------------------------------------- 6
def solve_longest_unique(inp: str) -> str:
    s = inp.rstrip("\n")
    last: dict[str, int] = {}
    best = start = 0
    for i, ch in enumerate(s):
        if last.get(ch, -1) >= start:
            start = last[ch] + 1
        last[ch] = i
        best = max(best, i - start + 1)
    return f"{best}\n"


def gen_longest_unique(rng: random.Random) -> list[str]:
    alpha = "abcdefghijklmnopqrstuvwxyz"
    printable = "".join(chr(c) for c in range(33, 127))

    def make(n: int, chars: str) -> str:
        return "".join(rng.choice(chars) for _ in range(n)) + "\n"

    return [
        "a\n", "aaaaaaa\n", "abcdefg\n", "abba\n", "dvdf\n",
        make(100, "abc"), make(1000, alpha), make(100000, alpha), make(100000, printable), printable + printable + "\n",
    ]


# --------------------------------------------------------------------------- 7
def solve_islands(inp: str) -> str:
    lines = inp.split()
    r, c = int(lines[0]), int(lines[1])
    grid = [bytearray(row.encode()) for row in lines[2:2 + r]]
    count = 0
    for i in range(r):
        for j in range(c):
            if grid[i][j] == 49:
                count += 1
                grid[i][j] = 48
                dq = deque([(i, j)])
                while dq:
                    x, y = dq.popleft()
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= nx < r and 0 <= ny < c and grid[nx][ny] == 49:
                            grid[nx][ny] = 48
                            dq.append((nx, ny))
    return f"{count}\n"


def gen_islands(rng: random.Random) -> list[str]:
    def make(r: int, c: int, p: float) -> str:
        return f"{r} {c}\n" + "\n".join("".join("1" if rng.random() < p else "0" for _ in range(c)) for _ in range(r)) + "\n"

    snake_r, snake_c = 301, 301
    snake = []
    for i in range(snake_r):
        if i % 2 == 0:
            snake.append("1" * snake_c)
        elif i % 4 == 1:
            snake.append("0" * (snake_c - 1) + "1")
        else:
            snake.append("1" + "0" * (snake_c - 1))
    return [
        "1 1\n0\n", "1 1\n1\n", "3 3\n101\n010\n101\n",
        make(10, 10, 0.4), make(100, 100, 0.5), make(500, 500, 0.45), make(500, 500, 0.7),
        f"{snake_r} {snake_c}\n" + "\n".join(snake) + "\n",  # one long path: defeats naive recursion depth
    ]


# --------------------------------------------------------------------------- 8
def solve_shortest_path(inp: str) -> str:
    data = _ints(inp)
    n, m, s = data[0], data[1], data[2]
    adj: list[list[tuple[int, int]]] = [[] for _ in range(n + 1)]
    for k in range(m):
        u, v, w = data[3 + 3 * k], data[4 + 3 * k], data[5 + 3 * k]
        adj[u].append((v, w))
    INF = float("inf")
    dist = [INF] * (n + 1)
    dist[s] = 0
    pq = [(0, s)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        for v, w in adj[u]:
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(pq, (nd, v))
    return " ".join(str(d) if d != INF else "-1" for d in dist[1:]) + "\n"


def gen_shortest_path(rng: random.Random) -> list[str]:
    def make(n: int, m: int, wmax: int) -> str:
        edges = [(rng.randint(1, n), rng.randint(1, n), rng.randint(0, wmax)) for _ in range(m)]
        return f"{n} {m} {rng.randint(1, n)}\n" + "\n".join(f"{u} {v} {w}" for u, v, w in edges) + "\n"

    chain_n = 100000
    chain = "\n".join(f"{i} {i + 1} 1000000" for i in range(1, chain_n))
    return [
        "1 0 1\n",
        "3 1 1\n2 3 5\n",
        "4 5 1\n1 2 4\n1 3 1\n3 2 2\n2 4 1\n3 4 7\n",
        make(10, 30, 10), make(1000, 5000, 1000), make(100000, 200000, 10**6), make(50000, 200000, 3),
        f"{chain_n} {chain_n - 1} 1\n{chain}\n",  # distances up to ~1e11: needs 64-bit integers
    ]


# --------------------------------------------------------------------------- 9
def solve_coin_change(inp: str) -> str:
    data = _ints(inp)
    n, amount = data[0], data[1]
    coins = data[2:2 + n]
    INF = amount + 1
    dp = [0] + [INF] * amount
    for c in coins:
        for v in range(c, amount + 1):
            if dp[v - c] + 1 < dp[v]:
                dp[v] = dp[v - c] + 1
    return f"{dp[amount] if dp[amount] != INF else -1}\n"


def gen_coin_change(rng: random.Random) -> list[str]:
    def make(n: int, amount: int, cmax: int) -> str:
        coins = sorted(set(rng.randint(1, cmax) for _ in range(n)))
        return f"{len(coins)} {amount}\n{' '.join(map(str, coins))}\n"

    return [
        "1 0\n7\n", "1 3\n2\n", "3 11\n1 2 5\n", "2 7\n2 4\n", "3 6\n1 3 4\n",
        make(5, 100, 30), make(20, 5000, 500), make(50, 10000, 1000), "3 10000\n7 13 9973\n", make(100, 10000, 10000),
    ]


# -------------------------------------------------------------------------- 10
def solve_lru(inp: str) -> str:
    lines = inp.split("\n")
    cap, q = map(int, lines[0].split())
    cache: OrderedDict[int, int] = OrderedDict()
    out = []
    for line in lines[1:1 + q]:
        parts = line.split()
        if parts[0] == "get":
            k = int(parts[1])
            if k in cache:
                cache.move_to_end(k)
                out.append(str(cache[k]))
            else:
                out.append("-1")
        else:
            k, v = int(parts[1]), int(parts[2])
            if k in cache:
                cache.move_to_end(k)
            cache[k] = v
            if len(cache) > cap:
                cache.popitem(last=False)
    return "\n".join(out) + ("\n" if out else "")


def gen_lru(rng: random.Random) -> list[str]:
    def make(cap: int, q: int, keyspace: int) -> str:
        ops = []
        has_get = False
        for i in range(q):
            if rng.random() < 0.5 or (i == q - 1 and not has_get):
                ops.append(f"get {rng.randint(1, keyspace)}")
                has_get = True
            else:
                ops.append(f"put {rng.randint(1, keyspace)} {rng.randint(0, 10**9)}")
        return f"{cap} {q}\n" + "\n".join(ops) + "\n"

    return [
        "1 4\nput 1 1\nput 2 2\nget 1\nget 2\n",
        "2 6\nput 1 10\nput 1 20\nget 1\nput 2 5\nput 3 7\nget 1\n",
        make(3, 30, 6), make(10, 1000, 30), make(1000, 100000, 3000), make(1, 100000, 5), make(100000, 100000, 50000),
    ]


PROBLEMS: list[ProblemDef] = [
    ProblemDef(
        slug="two-sum", title="Two Sum", difficulty="EASY", tags=["array", "hash-table"],
        statement=(
            "You are given an array of `n` integers and a target value. Exactly one pair of **distinct positions** "
            "`i < j` has values that add up to the target.\n\nReport that pair of positions."
        ),
        input_spec="The first line contains `n` and `target`. The second line contains `n` integers `a[0] … a[n-1]`.",
        output_spec="Print the two 0-based indices `i j` with `i < j`, separated by a space.",
        constraints="2 ≤ n ≤ 10^5\n-10^9 ≤ a[i] ≤ 10^9\n-2·10^9 ≤ target ≤ 2·10^9\nExactly one valid pair exists.",
        solve=solve_two_sum, hidden=gen_two_sum,
        samples=[
            Sample("4 9\n2 7 11 15\n", "a[0] + a[1] = 2 + 7 = 9."),
            Sample("3 6\n3 2 4\n", "a[1] + a[2] = 2 + 4 = 6. Index 0 cannot be used twice."),
        ],
    ),
    ProblemDef(
        slug="valid-parentheses", title="Valid Parentheses", difficulty="EASY", tags=["stack", "string"],
        statement=(
            "A bracket string uses only the characters `( ) [ ] { }`. It is **well formed** when every opening bracket "
            "is closed by a bracket of the same type, and brackets close in the reverse order in which they were opened.\n\n"
            "Decide whether the given string is well formed."
        ),
        input_spec="A single line containing the bracket string `s`.",
        output_spec="Print `true` if `s` is well formed, otherwise `false`.",
        constraints="1 ≤ |s| ≤ 10^5\n`s` consists only of `()[]{}`.",
        solve=solve_valid_parentheses, hidden=gen_valid_parentheses,
        samples=[
            Sample("()[]{}\n", "Three independent, correctly closed pairs."),
            Sample("([)]\n", "`[` is opened after `(` but `)` arrives first, so the nesting is wrong."),
            Sample("{[()]}\n", None),
        ],
        time_limit_ms=1000,
    ),
    ProblemDef(
        slug="binary-search", title="Binary Search Queries", difficulty="EASY", tags=["array", "binary-search"],
        statement=(
            "You are given a strictly increasing array of `n` integers and `q` queries. For each query value `x`, "
            "report the index at which `x` occurs in the array, or `-1` if it does not occur.\n\n"
            "A linear scan per query is too slow for the largest inputs."
        ),
        input_spec="Line 1: `n q`. Line 2: the `n` sorted integers. Line 3: the `q` query integers.",
        output_spec="Print `q` lines; line `k` holds the 0-based index of the `k`-th query value, or `-1`.",
        constraints="1 ≤ n, q ≤ 10^5\n|a[i]|, |x| ≤ 10^9\na[i] < a[i+1]",
        solve=solve_binary_search, hidden=gen_binary_search,
        samples=[Sample("5 3\n-1 0 3 5 9\n9 2 -1\n", "9 is at index 4; 2 is absent; -1 is at index 0.")],
        time_limit_ms=1500,
    ),
    ProblemDef(
        slug="maximum-subarray", title="Maximum Subarray", difficulty="MEDIUM",
        tags=["array", "dynamic-programming", "divide-and-conquer"],
        statement=(
            "Find the largest possible sum of a **non-empty contiguous** segment of the given array.\n\n"
            "Note that the array may consist entirely of negative numbers."
        ),
        input_spec="Line 1: `n`. Line 2: `n` integers.",
        output_spec="Print the maximum segment sum.",
        constraints="1 ≤ n ≤ 10^5\n-10^4 ≤ a[i] ≤ 10^4",
        solve=solve_max_subarray, hidden=gen_max_subarray,
        samples=[
            Sample("9\n-2 1 -3 4 -1 2 1 -5 4\n", "The segment 4 -1 2 1 sums to 6."),
            Sample("3\n-3 -1 -2\n", "The best non-empty segment is the single element -1."),
        ],
        time_limit_ms=1500,
    ),
    ProblemDef(
        slug="merge-intervals", title="Merge Intervals", difficulty="MEDIUM", tags=["array", "sorting"],
        statement=(
            "You are given `n` closed intervals `[l, r]`. Two intervals that overlap **or touch** (share an endpoint) "
            "belong to the same merged block.\n\nReplace the collection with the minimal set of disjoint intervals that "
            "cover exactly the same points, listed from left to right."
        ),
        input_spec="Line 1: `n`. Next `n` lines: `l r`.",
        output_spec="Line 1: the number of merged intervals `k`. Next `k` lines: `l r`, sorted by `l`.",
        constraints="1 ≤ n ≤ 10^5\n0 ≤ l ≤ r ≤ 2·10^9",
        solve=solve_merge_intervals, hidden=gen_merge_intervals,
        samples=[
            Sample("4\n1 3\n2 6\n8 10\n15 18\n", "[1,3] and [2,6] overlap and become [1,6]."),
            Sample("2\n1 4\n4 5\n", "The intervals touch at 4, so they merge into [1,5]."),
        ],
    ),
    ProblemDef(
        slug="longest-unique-substring", title="Longest Substring Without Repeats", difficulty="MEDIUM",
        tags=["string", "hash-table", "sliding-window"],
        statement=(
            "Given a string `s`, find the length of the longest contiguous substring in which **no character appears "
            "more than once**."
        ),
        input_spec="A single line containing `s` (printable ASCII, no whitespace).",
        output_spec="Print the length of the longest substring with all distinct characters.",
        constraints="1 ≤ |s| ≤ 10^5",
        solve=solve_longest_unique, hidden=gen_longest_unique,
        samples=[
            Sample("abcabcbb\n", "\"abc\" has length 3; every longer window repeats a character."),
            Sample("pwwkew\n", "\"wke\" has length 3. \"pwke\" is not contiguous."),
        ],
        time_limit_ms=1500,
    ),
    ProblemDef(
        slug="number-of-islands", title="Number of Islands", difficulty="MEDIUM",
        tags=["graph", "bfs", "dfs", "matrix"],
        statement=(
            "A map is an `r × c` grid of `1` (land) and `0` (water). Land cells that share an edge (up, down, left, "
            "right — not diagonals) belong to the same island.\n\nCount the islands.\n\n"
            "Some maps contain a single winding island hundreds of thousands of cells long: recursive flood fill may "
            "exceed the stack."
        ),
        input_spec="Line 1: `r c`. Next `r` lines: a string of `c` characters, each `0` or `1`.",
        output_spec="Print the number of islands.",
        constraints="1 ≤ r, c ≤ 500",
        solve=solve_islands, hidden=gen_islands,
        samples=[
            Sample("4 5\n11000\n11000\n00100\n00011\n", "Three separate groups of land."),
            Sample("3 3\n111\n010\n111\n", "All land cells connect through the middle column."),
        ],
        time_limit_ms=3000,
    ),
    ProblemDef(
        slug="shortest-path", title="Single-Source Shortest Paths", difficulty="HARD",
        tags=["graph", "shortest-path", "heap"],
        statement=(
            "A directed graph has `n` vertices numbered `1…n` and `m` weighted edges with non-negative weights. "
            "Compute the length of the shortest path from vertex `s` to every vertex.\n\n"
            "Path lengths can exceed the range of a 32-bit integer."
        ),
        input_spec="Line 1: `n m s`. Next `m` lines: `u v w` — an edge from `u` to `v` with weight `w`.",
        output_spec="Print `n` space-separated values: the distance from `s` to vertex `i`, or `-1` if unreachable.",
        constraints="1 ≤ n ≤ 10^5\n0 ≤ m ≤ 2·10^5\n0 ≤ w ≤ 10^6\nMultiple edges and self-loops may occur.",
        solve=solve_shortest_path, hidden=gen_shortest_path,
        samples=[
            Sample("4 5 1\n1 2 4\n1 3 1\n3 2 2\n2 4 1\n3 4 7\n", "1→3→2→4 costs 1+2+1 = 4, cheaper than 1→3→4 (8)."),
            Sample("3 1 1\n2 3 5\n", "Vertices 2 and 3 cannot be reached from 1."),
        ],
        time_limit_ms=4000,
    ),
    ProblemDef(
        slug="coin-change", title="Coin Change", difficulty="MEDIUM", tags=["dynamic-programming"],
        statement=(
            "You have an unlimited supply of coins of each of `n` denominations. Find the **fewest** coins that add up "
            "to exactly `amount`, or report that it cannot be done.\n\nGreedy choice of the largest coin is not always optimal."
        ),
        input_spec="Line 1: `n amount`. Line 2: the `n` distinct denominations.",
        output_spec="Print the minimum number of coins, or `-1` if `amount` cannot be formed.",
        constraints="1 ≤ n ≤ 100\n1 ≤ coin ≤ 10^4\n0 ≤ amount ≤ 10^4",
        solve=solve_coin_change, hidden=gen_coin_change,
        samples=[
            Sample("3 11\n1 2 5\n", "11 = 5 + 5 + 1."),
            Sample("3 6\n1 3 4\n", "Greedy takes 4+1+1 (3 coins) but 3+3 uses only 2."),
            Sample("1 3\n2\n", "Odd amounts cannot be built from 2s."),
        ],
        time_limit_ms=3000,
    ),
    ProblemDef(
        slug="lru-cache", title="LRU Cache Simulator", difficulty="HARD", tags=["design", "hash-table", "linked-list"],
        statement=(
            "Simulate a key-value cache with a fixed `capacity` that evicts the **least recently used** key.\n\n"
            "- `get k` returns the value for `k` (or `-1` if absent) and marks `k` as most recently used.\n"
            "- `put k v` inserts or updates `k`, marks it most recently used, and if the cache now holds more than "
            "`capacity` keys, evicts the least recently used one.\n\nEvery operation must run in O(1) average time."
        ),
        input_spec="Line 1: `capacity q`. Next `q` lines: `get k` or `put k v`.",
        output_spec="For every `get`, print its result on its own line.",
        constraints="1 ≤ capacity ≤ 10^5\n1 ≤ q ≤ 10^5\n1 ≤ k ≤ 10^5, 0 ≤ v ≤ 10^9\nAt least one `get` is present.",
        solve=solve_lru, hidden=gen_lru,
        samples=[
            Sample("2 9\nput 1 1\nput 2 2\nget 1\nput 3 3\nget 2\nput 4 4\nget 1\nget 3\nget 4\n",
                   "`get 1` refreshes key 1, so `put 3 3` evicts key 2; `put 4 4` then evicts key 1."),
        ],
    ),
]
