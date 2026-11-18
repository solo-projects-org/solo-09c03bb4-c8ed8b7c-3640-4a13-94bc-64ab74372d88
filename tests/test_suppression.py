"""隐藏规则（suppression）单元测试。"""

from app.suppression import (
    _cell_value_range,
    _rows_cols_covered,
    find_suppression,
    primary_cells,
)


def assert_valid_solution(counts, hidden):
    """通用校验：方案满足全部发布规则。"""
    n_r, n_c = len(counts), len(counts[0])
    assert hidden is not None
    # 一次隐藏格必须全部被隐藏
    assert primary_cells(counts) <= hidden
    # 每行每列至少一个公开格
    assert _rows_cols_covered(n_r, n_c, hidden)
    # 每个隐藏格至少两种非负整数可行取值
    for cell in hidden:
        lo, hi = _cell_value_range(counts, hidden, cell)
        assert hi > lo, f"格 {cell} 被唯一确定为 {lo}"


def test_no_small_cells_publish_all():
    counts = [[0, 3, 5], [4, 0, 6], [7, 8, 9]]
    hidden, reasons = find_suppression(counts)
    assert hidden == set()
    assert reasons == []


def test_3x3_complementary_block():
    """经典情形：一个小格 -> 连带隐藏成 2x2 块。"""
    counts = [[1, 4, 5], [3, 4, 5], [6, 7, 8]]
    hidden, _ = find_suppression(counts)
    assert hidden == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert_valid_solution(counts, hidden)


def test_3x3_zero_column_case():
    """含零列时，零列中的格被强制为 0，算法须绕开并找到可行方案。"""
    counts = [[1, 0, 5], [0, 0, 3], [4, 0, 6]]
    hidden, _ = find_suppression(counts)
    assert_valid_solution(counts, hidden)


def test_2x2_unpublishable():
    counts = [[1, 5], [5, 5]]
    hidden, reasons = find_suppression(counts)
    assert hidden is None
    assert reasons  # 有说明


def test_2x3_unpublishable():
    """2 行表：任何隐藏格都会被列合计与同行公开格唯一确定。"""
    counts = [[1, 5, 5], [5, 5, 5]]
    hidden, reasons = find_suppression(counts)
    assert hidden is None
    assert reasons


def test_3x2_unpublishable():
    counts = [[1, 5], [5, 5], [5, 5]]
    hidden, _ = find_suppression(counts)
    assert hidden is None


def test_3x3_all_small_unpublishable():
    """所有格都是小格：无法做到每行每列仍有公开格。"""
    counts = [[1, 1, 1], [1, 2, 1], [1, 1, 1]]
    hidden, reasons = find_suppression(counts)
    assert hidden is None
    assert reasons


def test_multiple_small_cells():
    counts = [[1, 2, 8], [6, 7, 8], [9, 10, 11]]
    hidden, _ = find_suppression(counts)
    assert_valid_solution(counts, hidden)
    assert {(0, 0), (0, 1)} <= hidden


def test_count_2_also_hidden():
    counts = [[2, 4, 5], [3, 4, 5], [6, 7, 8]]
    hidden, _ = find_suppression(counts)
    assert_valid_solution(counts, hidden)
    assert (0, 0) in hidden


def test_zero_and_three_not_primary():
    """0 和 >=3 不属于必须隐藏的小格。"""
    assert primary_cells([[0, 3], [2, 1]]) == {(1, 0), (1, 1)}
