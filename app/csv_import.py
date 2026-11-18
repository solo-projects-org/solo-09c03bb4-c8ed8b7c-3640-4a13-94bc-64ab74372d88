"""检验 CSV 的解析、校验、去重与冲突检测。

CSV 要求（首行为表头，UTF-8 编码，可带 BOM）：
    检验号,病区,周次,是否阳性
- 同号同内容（病区、周次、是否阳性均相同）只计一次；
- 同号内容冲突 -> 整份文件拒绝；
- 文件须覆盖 2～3 个病区、2～3 个周次（按全部记录计，含阴性）。
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

REQUIRED_COLUMNS = ("检验号", "病区", "周次", "是否阳性")
MAX_BYTES = 2 * 1024 * 1024  # 2 MB，足够约十万行
MAX_ERRORS = 20              # 页面上最多展示的错误条数

_POSITIVE = {"是", "阳性", "1", "true", "t", "y", "yes"}
_NEGATIVE = {"否", "阴性", "0", "false", "f", "n", "no"}


class CsvImportError(Exception):
    """CSV 校验失败（整份拒绝）。errors 为面向用户的错误列表。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors[:3]))


@dataclass(frozen=True)
class TestRecord:
    test_id: str
    ward: str
    week: str
    positive: bool


def _parse_positive(raw: str) -> bool | None:
    v = raw.strip().lower()
    if v in _POSITIVE:
        return True
    if v in _NEGATIVE:
        return False
    return None


def parse_tests(data: bytes) -> list[TestRecord]:
    """解析并校验 CSV，返回按检验号去重后的记录列表。

    任何校验错误（含同号冲突）都抛出 CsvImportError —— 整份拒绝。
    """
    if not data:
        raise CsvImportError(["文件为空"])
    if len(data) > MAX_BYTES:
        raise CsvImportError([f"文件过大（上限 {MAX_BYTES // 1024 // 1024} MB）"])
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvImportError(["文件编码须为 UTF-8"])

    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(c.strip() for c in r)]  # 跳过空行
    if not rows:
        raise CsvImportError(["文件无有效内容"])

    errors: list[str] = []
    header = [h.strip() for h in rows[0]]
    col_idx: dict[str, int] = {}
    for col in REQUIRED_COLUMNS:
        if col in header:
            col_idx[col] = header.index(col)
        else:
            errors.append(f"缺少必需列：{col}")
    if errors:
        raise CsvImportError(errors)

    seen: dict[str, TestRecord] = {}
    conflict = False
    for lineno, row in enumerate(rows[1:], start=2):
        if len(errors) >= MAX_ERRORS:
            errors.append("……错误过多，仅显示前若干条")
            break
        if len(row) < len(header):
            errors.append(f"第 {lineno} 行：列数不足")
            continue
        test_id = row[col_idx["检验号"]].strip()
        ward = row[col_idx["病区"]].strip()
        week = row[col_idx["周次"]].strip()
        pos_raw = row[col_idx["是否阳性"]]
        if not test_id:
            errors.append(f"第 {lineno} 行：检验号为空")
            continue
        if not ward:
            errors.append(f"第 {lineno} 行：病区为空")
            continue
        if not week:
            errors.append(f"第 {lineno} 行：周次为空")
            continue
        positive = _parse_positive(pos_raw)
        if positive is None:
            errors.append(
                f"第 {lineno} 行：是否阳性取值无法识别：{pos_raw.strip()!r}"
                "（可用：是/否、阳性/阴性、1/0、true/false）"
            )
            continue
        rec = TestRecord(test_id, ward, week, positive)
        prev = seen.get(test_id)
        if prev is not None and prev != rec:
            errors.append(
                f"检验号 {test_id!r} 存在内容冲突的记录"
                f"（{prev.ward}/{prev.week}/{'阳性' if prev.positive else '阴性'} 与 "
                f"{ward}/{week}/{'阳性' if positive else '阴性'}），整份拒绝"
            )
            conflict = True
            break
        seen[test_id] = rec  # 同号同内容：只计一次

    if errors:
        raise CsvImportError(errors)
    if conflict:  # 防御性：冲突必然已记录错误
        raise CsvImportError(["存在同号冲突记录，整份拒绝"])
    if not seen:
        raise CsvImportError(["文件无有效数据行"])

    wards = {r.ward for r in seen.values()}
    weeks = {r.week for r in seen.values()}
    if not 2 <= len(wards) <= 3:
        errors.append(f"文件须覆盖 2～3 个病区，实际 {len(wards)} 个")
    if not 2 <= len(weeks) <= 3:
        errors.append(f"文件须覆盖 2～3 个周次，实际 {len(weeks)} 个")
    if errors:
        raise CsvImportError(errors)
    return list(seen.values())


# ---------------------------------------------------------------- 交叉表


def _label_sort_key(labels: list[str]):
    """纯数字标签按数值排序，否则按字典序（保证确定性）。"""
    if all(re.fullmatch(r"\d+", x) for x in labels):
        return lambda x: (0, int(x))
    return lambda x: (1, x)


def build_crosstab(records: list[TestRecord]):
    """按 病区×周次 统计阳性记录数。

    返回 (wards, weeks, counts)；counts[i][j] 为 wards[i]×weeks[j] 的阳性数。
    行列取文件中出现的全部病区/周次（含仅阴性者，对应格计数为 0）。
    """
    wards = sorted({r.ward for r in records},
                   key=_label_sort_key([r.ward for r in records]))
    weeks = sorted({r.week for r in records},
                   key=_label_sort_key([r.week for r in records]))
    wi = {w: i for i, w in enumerate(wards)}
    ki = {k: j for j, k in enumerate(weeks)}
    counts = [[0] * len(weeks) for _ in wards]
    for r in records:
        if r.positive:
            counts[wi[r.ward]][ki[r.week]] += 1
    return wards, weeks, counts
