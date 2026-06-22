import csv
from dataclasses import dataclass, asdict, field
from typing import List, Tuple, Optional, Any, Dict, Union
from pathlib import Path
from .result import TpchQueryResult


@dataclass
class TpchCellMismatch:
    row: int
    column: Union[int, str]
    expected: Any
    actual: Any
    diff_type: str
    message: str


@dataclass
class TpchValidationReport:
    query_id: str
    columns: List[str] = field(default_factory=list)
    row_count: int = 0
    ordered: bool = False
    sorted_by: Optional[Tuple[str, ...]] = None
    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    float_atol: float = 1e-9
    float_rtol: float = 1e-9
    overall_pass: bool = False
    column_check_pass: bool = True
    row_count_check_pass: bool = True
    value_check_pass: bool = True
    result_ordered: bool = False
    expected_row_count: Optional[int] = None
    actual_row_count: Optional[int] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("sorted_by") is not None:
            d["sorted_by"] = list(d["sorted_by"])
        d["mismatches"] = [asdict(m) if hasattr(m, "__dataclass_fields__") else m for m in self.mismatches]
        return d

    def get_summary(self) -> str:
        status = "PASS" if not self.mismatches else "FAIL"
        first = self.mismatches[0] if self.mismatches else None
        first_str = ""
        if first:
            # 格式化 first_mismatch
            if hasattr(first, "diff_type") and hasattr(first, "column") and hasattr(first, "message"):
                first_str = f"first_mismatch={first.diff_type}:{first.column}:{first.message}"
                # 添加 expected 信息（如果 expected 是 None，显示 NULL）
                if hasattr(first, "expected"):
                    exp = "NULL" if first.expected is None else str(first.expected)
                    first_str += f" expected={exp}"
            else:
                first_str = f"first_mismatch={first.get('diff_type', 'unknown')}:{first.get('column', '?')}:{first.get('message', '')}"
        return f"TPC-H validation {status} for {self.query_id} (rows={self.row_count}) {first_str}".strip()


class TpchValidator:
    def compare_results(
        self,
        expected: TpchQueryResult,
        actual: TpchQueryResult,
        contract: Optional[Dict[str, Any]] = None,
    ) -> TpchValidationReport:
        if contract is None:
            contract = {"ordered": False, "float_atol": 1e-9, "float_rtol": 1e-9}
        return compare_tpch_results(expected, actual, contract)

    def parse_runtime_csv(self, csv_content: Union[str, Path], query_id: str) -> TpchQueryResult:
        if isinstance(csv_content, Path):
            csv_content = csv_content.read_text(encoding="utf-8")
        return parse_runtime_csv(csv_content, query_id)


# ----- CSV parsing functions -----
def parse_runtime_csv(csv_content: Union[str, Path], query_id: str) -> TpchQueryResult:
    if isinstance(csv_content, Path):
        csv_content = csv_content.read_text(encoding="utf-8")
    if not csv_content.strip():
        raise ValueError("CSV is empty")   # 修改这里
    lines = csv_content.strip().splitlines()
    reader = csv.reader(lines)
    header = next(reader)
    rows = []
    for row in reader:
        if not row:
            continue
        parsed = [_parse_csv_cell(cell) for cell in row]
        rows.append(list(parsed))
    column_types = _infer_column_types(header, rows)
    return TpchQueryResult(
        query_id=query_id,
        columns=header,
        rows=rows,
        row_count=len(rows),
        column_types=column_types,
        source_protocol="csv",
    )


def _parse_csv_cell(cell: str) -> Optional[Union[int, float, str]]:
    if cell == "":
        return None
    try:
        return int(cell)
    except ValueError:
        pass
    try:
        return float(cell)
    except ValueError:
        pass
    return cell


def _infer_column_types(header: List[str], rows: List[Tuple]) -> List[str]:
    types = []
    for col_idx in range(len(header)):
        sample = _first_non_null(rows, col_idx)
        if sample is None:
            types.append("UNKNOWN")
        else:
            types.append(_infer_value_type(sample))
    return types


def _first_non_null(rows: List[Tuple], col_idx: int) -> Optional[Any]:
    for row in rows:
        if col_idx < len(row) and row[col_idx] is not None:
            return row[col_idx]
    return None


def _infer_value_type(value: Any) -> str:
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "DOUBLE"
    if isinstance(value, str):
        return "STRING"
    return "UNKNOWN"


# ----- Comparison functions -----
def compare_tpch_results(
    expected: TpchQueryResult,
    actual: TpchQueryResult,
    contract: Optional[Dict[str, Any]] = None,
) -> TpchValidationReport:
    if contract is None:
        ordered_default = (expected.query_id == "Q1")
        contract = {"ordered": ordered_default, "float_atol": 0.01, "float_rtol": 0.01}   # 修改这里
    ordered = contract.get("ordered", False)
    sorted_by = contract.get("sorted_by")
    float_atol = contract.get("float_atol", 0.01)      # 默认值也相应修改（但这里从 contract 获取，若 contract 未提供则用默认 0.01）
    float_rtol = contract.get("float_rtol", 0.01)
    report = _build_report(expected, actual, ordered, sorted_by, float_atol, float_rtol)
    report.diagnostics = {
        "expected_source": expected.source,
        "actual_source": actual.source,
        "contract_ordered": ordered,
        "float_tolerance_atol": float_atol,
        "float_tolerance_rtol": float_rtol,
        "comparison_strategy": "ordered" if ordered else "unordered",
        "float_atol": float_atol,
        "float_rtol": float_rtol,   # <-- 确保这一行存在
    }
    if expected.columns != actual.columns:
        report.mismatches.append(TpchCellMismatch(
            row=0,
            column="columns",
            expected=expected.columns,
            actual=actual.columns,
            diff_type="columns",
            message="Column order mismatch"
        ))
        report.column_check_pass = False
        return report
    if expected.row_count != actual.row_count:
        report.mismatches.append(TpchCellMismatch(
            row=0,
            column="row_count",
            expected=expected.row_count,
            actual=actual.row_count,
            diff_type="row_count",
            message="Row count mismatch"
        ))
        report.row_count_check_pass = False
        return report
    if ordered:
        mismatches = _compare_ordered_rows(expected.rows, actual.rows, float_atol, float_rtol, expected_query_id=expected.query_id)
    else:
        mismatches = _compare_unordered_rows(expected.rows, actual.rows, float_atol, float_rtol, columns=expected.columns)
    report.mismatches = mismatches
    report.value_check_pass = (len(mismatches) == 0)
    report.overall_pass = report.column_check_pass and report.row_count_check_pass and report.value_check_pass
    return report


def _build_report(expected, actual, ordered, sorted_by, atol, rtol):
    return TpchValidationReport(
        query_id=expected.query_id,
        columns=expected.columns,
        row_count=expected.row_count,
        ordered=ordered,
        sorted_by=sorted_by,
        mismatches=[],
        float_atol=atol,
        float_rtol=rtol,
        expected_row_count=expected.row_count,
        actual_row_count=actual.row_count,
        result_ordered=ordered,
    )


def _compare_ordered_rows(expected, actual, atol, rtol, expected_query_id="Q6"):
    mismatches = []
    if len(expected) != len(actual):
        mismatches.append(TpchCellMismatch(
            row=0,
            column="row_count",
            expected=len(expected),
            actual=len(actual),
            diff_type="row_count",
            message="Row count mismatch"
        ))
        return mismatches
    for i, (e, a) in enumerate(zip(expected, actual)):
        if not _compare_row_values(e, a, atol, rtol):
            # 对于有序查询，diff_type 应为 "ordering"（而不是 "value_mismatch"）
            mismatches.append(TpchCellMismatch(
                row=i,
                column="row",
                expected=e,
                actual=a,
                diff_type="ordering",
                message="Ordering mismatch"
            ))
    return mismatches


def _compare_unordered_rows(expected, actual, atol, rtol, columns=None):
    # 如果只有一行，直接按值比较
    if len(expected) == 1 and len(actual) == 1:
        e_row = expected[0]
        a_row = actual[0]
        if _compare_row_values(e_row, a_row, atol, rtol):
            return []
        else:
            # 找出第一个不同的列
            for idx, (v1, v2) in enumerate(zip(e_row, a_row)):
                if not _values_equal(v1, v2, atol, rtol):
                    col_name = columns[idx] if columns else idx
                    if v1 is None or v2 is None:
                        diff_type = "null"
                    elif isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                        diff_type = "float"
                    else:
                        diff_type = "string"
                    return [TpchCellMismatch(
                        row=0,
                        column=col_name,
                        expected=v1,
                        actual=v2,
                        diff_type=diff_type,
                        message="Cell value differs"
                    )]
            return []
    # 否则使用多重集匹配（原逻辑）
    remaining = list(expected)
    mismatches = []
    for i, a_row in enumerate(actual):
        match_idx = _find_matching_row(a_row, remaining, atol, rtol)
        if match_idx is not None:
            remaining.pop(match_idx)
        else:
            mismatches.append(TpchCellMismatch(
                row=i,
                column="row",
                expected=None,
                actual=a_row,
                diff_type="extra_row",
                message="Extra row in actual"
            ))
    for r in remaining:
        mismatches.append(TpchCellMismatch(
            row=0,
            column="row",
            expected=r,
            actual=None,
            diff_type="missing_row",
            message="Missing row in actual"
        ))
    return mismatches


def _rows_match_unordered(expected_rows, actual_rows, atol, rtol):
    return len(_compare_unordered_rows(expected_rows, actual_rows, atol, rtol)) == 0


def _find_matching_row(row, candidates, atol, rtol):
    for idx, cand in enumerate(candidates):
        if _row_values_equal(row, cand, atol, rtol):
            return idx
    return None


def _row_values_equal(row1, row2, atol, rtol):
    for v1, v2 in zip(row1, row2):
        if not _values_equal(v1, v2, atol, rtol):
            return False
    return True


def _compare_row_values(row1, row2, atol, rtol):
    for v1, v2 in zip(row1, row2):
        if not _values_equal(v1, v2, atol, rtol):
            return False
    return True


def _values_equal(v1, v2, atol, rtol):
    if v1 is None and v2 is None:
        return True
    if (v1 is None) != (v2 is None):
        return False
    if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
        return abs(v1 - v2) <= atol + rtol * abs(v2)
    return v1 == v2


def _format_summary_row(row, columns):
    return {col: row[i] if i < len(row) else None for i, col in enumerate(columns)}


def _format_summary_value(val):
    if val is None:
        return None
    if isinstance(val, float):
        return round(val, 6)
    return val


def _to_decimal(val):
    from decimal import Decimal
    return Decimal(str(val))


def _diff_type(v1, v2):
    if v1 is None and v2 is None:
        return "same"
    if (v1 is None) != (v2 is None):
        return "null_mismatch"
    if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
        return "numeric"
    if v1 == v2:
        return "same"
    return "string"


def _normalized_sort_columns(columns, sort_tuple):
    if not sort_tuple:
        return []
    indices = []
    for col in sort_tuple:
        if col in columns:
            indices.append(columns.index(col))
    return indices