"""交叉表保密隐藏（cell suppression）核心逻辑。

发布规则：
1. 计数为 1~2 的格必须隐藏（一次隐藏 / primary suppression）。
2. 可连带隐藏其他格（二次隐藏 / complementary suppression），但结果必须满足：
   a. 每行、每列至少保留一个公开格；
   b. 在“公开格取值 + 行合计 + 列合计”已知的前提下，每个隐藏格
      （尤其是计数 1~2 的小格）至少有两种非负整数可行取值，
      即不能被行列合计唯一倒推。
3. 若不存在满足条件的隐藏方案，则判定为“无法发布”。

可行性模型：隐藏格为取值 >=0 的整数变量，公开格固定为真实计数，
行合计与列合计公开。二维列联表在给定边际合计下的可行性是运输问题，
用最大流精确判定（整数容量 => 存在整数解）。单个隐藏格的可行取值
构成连续区间 [vmin, vmax]，通过对上/下界分别二分求得；
vmax > vmin 即表示该格至少有两种可行取值。
"""

from __future__ import annotations

from collections import deque
from itertools import combinations
from typing import Optional


# ---------------------------------------------------------------- 最大流


class _MaxFlow:
    """Dinic 最大流。节点数 <= 11（3 行 + 3 列 + 源汇），规模极小。"""

    __slots__ = ("n", "g", "level", "it")

    def __init__(self, n: int):
        self.n = n
        self.g: list[list[list[int]]] = [[] for _ in range(n)]

    def add(self, fr: int, to: int, cap: int) -> None:
        self.g[fr].append([to, cap, len(self.g[to])])
        self.g[to].append([fr, 0, len(self.g[fr]) - 1])

    def _bfs(self, s: int, t: int) -> bool:
        self.level = [-1] * self.n
        self.level[s] = 0
        q = deque([s])
        while q:
            v = q.popleft()
            for to, cap, _ in self.g[v]:
                if cap > 0 and self.level[to] < 0:
                    self.level[to] = self.level[v] + 1
                    q.append(to)
        return self.level[t] >= 0

    def _dfs(self, v: int, t: int, f: int) -> int:
        if v == t:
            return f
        while self.it[v] < len(self.g[v]):
            e = self.g[v][self.it[v]]
            if e[1] > 0 and self.level[v] < self.level[e[0]]:
                d = self._dfs(e[0], t, min(f, e[1]))
                if d > 0:
                    e[1] -= d
                    self.g[e[0]][e[2]][1] += d
                    return d
            self.it[v] += 1
        return 0

    def max_flow(self, s: int, t: int) -> int:
        flow = 0
        while self._bfs(s, t):
            self.it = [0] * self.n
            while True:
                f = self._dfs(s, t, 1 << 62)
                if f == 0:
                    break
                flow += f
        return flow


# ---------------------------------------------------------------- 可行性


def _feasible(row_sums: list[int], col_sums: list[int],
              lo: list[list[int]], hi: list[list[int]]) -> bool:
    """是否存在非负整数矩阵 x，lo<=x<=hi，且行列合计等于给定值。"""
    n_r, n_c = len(row_sums), len(col_sums)
    rs = [row_sums[i] - sum(lo[i][j] for j in range(n_c)) for i in range(n_r)]
    cs = [col_sums[j] - sum(lo[i][j] for i in range(n_r)) for j in range(n_c)]
    if any(v < 0 for v in rs) or any(v < 0 for v in cs):
        return False
    total = sum(rs)
    if total != sum(cs):
        return False
    s, t = 0, n_r + n_c + 1
    mf = _MaxFlow(n_r + n_c + 2)
    for i in range(n_r):
        mf.add(s, 1 + i, rs[i])
    for j in range(n_c):
        mf.add(1 + n_r + j, t, cs[j])
    for i in range(n_r):
        for j in range(n_c):
            cap = hi[i][j] - lo[i][j]
            if cap < 0:
                return False
            if cap > 0:
                mf.add(1 + i, 1 + n_r + j, cap)
    return mf.max_flow(s, t) == total


def _cell_value_range(counts, hidden, target) -> Optional[tuple[int, int]]:
    """隐藏格 target 在公开信息下的可行取值区间 [vmin, vmax]。

    counts: 真实计数矩阵；hidden: (i,j) 集合；target: (i,j)。
    整体不可行时返回 None（正常流程不会发生）。
    """
    n_r, n_c = len(counts), len(counts[0])
    row_sums = [sum(row) for row in counts]
    col_sums = [sum(counts[i][j] for i in range(n_r)) for j in range(n_c)]
    total = sum(row_sums)

    lo = [[0] * n_c for _ in range(n_r)]
    hi = [[0] * n_c for _ in range(n_r)]
    for i in range(n_r):
        for j in range(n_c):
            if (i, j) in hidden:
                lo[i][j], hi[i][j] = 0, total
            else:
                lo[i][j] = hi[i][j] = counts[i][j]

    if not _feasible(row_sums, col_sums, lo, hi):
        return None

    ti, tj = target
    bound = min(row_sums[ti], col_sums[tj])

    # 最小可行值：对 hi[target] 二分（可行性关于上界单调）
    a, b = 0, bound
    while a < b:
        mid = (a + b) // 2
        hi[ti][tj] = mid
        if _feasible(row_sums, col_sums, lo, hi):
            b = mid
        else:
            a = mid + 1
    vmin = a

    # 最大可行值：对 lo[target] 二分（可行性关于下界单调递减）
    hi[ti][tj] = total
    vmax = vmin
    a, b = vmin, bound
    while a <= b:
        mid = (a + b) // 2
        lo[ti][tj] = mid
        if _feasible(row_sums, col_sums, lo, hi):
            vmax = mid
            a = mid + 1
        else:
            b = mid - 1
    lo[ti][tj] = 0
    return vmin, vmax


# ---------------------------------------------------------------- 隐藏方案


def _rows_cols_covered(n_r: int, n_c: int, hidden: set[tuple[int, int]]) -> bool:
    """每行每列是否都至少保留一个公开格。"""
    for i in range(n_r):
        if all((i, j) in hidden for j in range(n_c)):
            return False
    for j in range(n_c):
        if all((i, j) in hidden for i in range(n_r)):
            return False
    return True


def _all_ambiguous(counts, hidden) -> bool:
    """所有隐藏格都至少有两种非负整数可行取值。"""
    for cell in hidden:
        rng = _cell_value_range(counts, hidden, cell)
        if rng is None or rng[0] == rng[1]:
            return False
    return True


def primary_cells(counts: list[list[int]]) -> set[tuple[int, int]]:
    """计数为 1~2 的格（必须隐藏）。"""
    return {(i, j)
            for i, row in enumerate(counts)
            for j, v in enumerate(row)
            if 1 <= v <= 2}


def find_suppression(counts: list[list[int]]) -> tuple[Optional[set[tuple[int, int]]], list[str]]:
    """求满足发布规则的隐藏方案。

    返回 (hidden, reasons)：
    - hidden 为 (i,j) 集合（含一次隐藏与连带隐藏），None 表示无法发布；
    - reasons 为无法发布时的说明（面向数据员，不含任何计数）。
    方案按连带隐藏格数最少优先（BFS）。
    """
    n_r, n_c = len(counts), len(counts[0])
    primary = primary_cells(counts)
    if not primary:
        return set(), []

    candidates = [(i, j) for i in range(n_r) for j in range(n_c)
                  if (i, j) not in primary]
    for extra_size in range(0, len(candidates) + 1):
        for extra in combinations(candidates, extra_size):
            hidden = primary | set(extra)
            if not _rows_cols_covered(n_r, n_c, hidden):
                continue
            if _all_ambiguous(counts, hidden):
                return hidden, []

    reasons = [
        "存在计数为 1～2 的格，必须隐藏；但在满足“每行每列至少保留一个公开格”"
        "的前提下，任何连带隐藏组合都无法使每个隐藏格具有至少两种非负整数可行取值"
        "（即无法避免被行列合计唯一倒推），因此本表无法发布。"
    ]
    if n_r < 3 or n_c < 3:
        reasons.append(
            "提示：本表不足 3 行或不足 3 列，任何隐藏格都会被其所在行/列的"
            "合计与其余公开格唯一确定，且无法再连带隐藏（否则某行/列将没有公开格）。"
        )
    return None, reasons
