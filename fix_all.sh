#!/bin/bash
set -e
echo "=== 开始自动修补所有 TODO 位置 ==="

cat > tpch_monetdb/utils/model_aliases.py << 'MODELALIAS'
"""Model alias utilities for provider prefix normalization."""

def normalize_accounting_model_name(model_name: str) -> str:
    if model_name.startswith("deepseek/"):
        return model_name[len("deepseek/"):]
    if model_name.startswith("openai/deepseek-"):
        return model_name[len("openai/"):]
    if model_name.startswith("anthropic/deepseek-"):
        return model_name[len("anthropic/"):]
    return model_name

def get_model_provider(model_name: str) -> str:
    if model_name.startswith("deepseek/"):
        return "deepseek"
    if model_name.startswith("openai/deepseek-"):
        return "openai"
    if model_name.startswith("anthropic/deepseek-"):
        return "anthropic"
    if model_name.startswith("openai/"):
        return "openai"
    if model_name.startswith("anthropic/"):
        return "anthropic"
    return "unknown"

def is_deepseek_model(model_name: str) -> bool:
    normalized = normalize_accounting_model_name(model_name).lower()
    return "deepseek-v4" in normalized

def is_openai_deepseek_model(model_name: str) -> bool:
    return model_name.startswith("openai/deepseek-")

def is_anthropic_deepseek_model(model_name: str) -> bool:
    return model_name.startswith("anthropic/deepseek-")
MODELALIAS

cat > tpch_monetdb/utils/model_setup.py << 'MODELSETUP'
import os
import logging
from typing import Optional
from dataclasses import dataclass

@dataclass
class ModelConfig:
    model_name: str
    accounting_model_name: str
    provider: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None

def setup_model_config(model_identifier: str) -> ModelConfig:
    from .model_aliases import normalize_accounting_model_name, get_model_provider

    provider = get_model_provider(model_identifier)
    if provider == "deepseek":
        accounting = normalize_accounting_model_name(model_identifier)
        if "flash" in accounting.lower():
            litellm_model = "deepseek/deepseek-v4-flash"
        else:
            litellm_model = "deepseek/deepseek-v4-pro"
        base_url = os.getenv("LITELLM_BASE_URL")
        api_key = os.getenv("LITELLM_API_KEY")
        return ModelConfig(
            model_name=litellm_model,
            accounting_model_name=accounting,
            provider="deepseek",
            base_url=base_url,
            api_key=api_key,
        )
    if provider == "openai" and "deepseek" in model_identifier:
        logging.warning(f"Using legacy openai/deepseek path: {model_identifier}")
        base_url = os.getenv("LITELLM_BASE_URL") or "https://api.deepseek.com"
        accounting = normalize_accounting_model_name(model_identifier)
        return ModelConfig(
            model_name=model_identifier,
            accounting_model_name=accounting,
            provider="openai",
            base_url=base_url,
            api_key=os.getenv("LITELLM_API_KEY"),
        )
    if provider == "anthropic" and "deepseek" in model_identifier:
        raise RuntimeError(f"Anthropic provider does not support DeepSeek models: {model_identifier}")
    return ModelConfig(
        model_name=model_identifier,
        accounting_model_name=normalize_accounting_model_name(model_identifier),
        provider=provider,
        base_url=os.getenv("LITELLM_BASE_URL"),
        api_key=os.getenv("LITELLM_API_KEY"),
    )
MODELSETUP

cat > tpch_monetdb/llm_cache/models.py << 'LLMMODELS'
MODEL_REGISTRY = {
    "deepseek-v4-flash": {
        "input_cost_per_token": 0.14 / 1_000_000,
        "cached_input_cost_per_token": 0.0028 / 1_000_000,
        "output_cost_per_token": 0.28 / 1_000_000,
        "context_window": 1_000_000,
    },
    "deepseek-v4-pro": {
        "input_cost_per_token": 0.435 / 1_000_000,
        "cached_input_cost_per_token": 0.003625 / 1_000_000,
        "output_cost_per_token": 0.87 / 1_000_000,
        "context_window": 1_000_000,
    },
}

def request_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    **kwargs,
) -> float:
    pricing = MODEL_REGISTRY.get(model)
    if not pricing:
        return 0.0
    input_cost = pricing.get("input_cost_per_token", 0.0)
    cached_input_cost = pricing.get("cached_input_cost_per_token", 0.0)
    output_cost = pricing.get("output_cost_per_token", 0.0)
    actual_cached = min(cached_tokens, input_tokens)
    actual_uncached = input_tokens - actual_cached
    total = actual_cached * cached_input_cost + actual_uncached * input_cost + output_tokens * output_cost
    return max(total, 0.0)

def get_context_window(model: str) -> int:
    pricing = MODEL_REGISTRY.get(model)
    if not pricing:
        return 4096
    return pricing.get("context_window", 4096)

def get_model_pricing(model: str) -> dict:
    return MODEL_REGISTRY.get(model, {})
LLMMODELS

cat > tpch_monetdb/llm_cache/litellm_model_costs.py << 'LITELLMCOST'
import json
import logging
from pathlib import Path
from typing import Dict, Any
import litellm

COST_OVERRIDES_JSON = Path(__file__).parent / "litellm_model_cost_overrides.json"

def load_tpch_monetdb_litellm_model_cost_overrides() -> Dict[str, Any]:
    with open(COST_OVERRIDES_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not data:
        raise ValueError("Model cost overrides file must be a non-empty dict")
    for k, v in data.items():
        if not isinstance(k, str):
            raise TypeError(f"Model name must be string, got {type(k)}")
        if not isinstance(v, dict):
            raise TypeError(f"Model info must be dict, got {type(v)}")
    return data

def register_tpch_monetdb_litellm_model_costs() -> None:
    overrides = load_tpch_monetdb_litellm_model_cost_overrides()
    litellm.model_cost.update(overrides)
    from litellm import _model_cost_lowercase
    _model_cost_lowercase.clear()
    for k, v in litellm.model_cost.items():
        _model_cost_lowercase[k.lower()] = v
    logging.info(f"Registered {len(overrides)} model cost overrides")
LITELLMCOST

cat > tpch_monetdb/tools/tpch_monetdb_agent_tools.py << 'AGENTTOOLS'
import re
from pathlib import Path
from typing import List, Optional, Any

_TOOL_GREP_MAX_BYTES = 1_000_000

class StageToolRuntime:
    def __init__(self, workspace_root: str, profile: Any = None):
        self.workspace_root = workspace_root
        self.profile = profile

    def list_directory(
        self,
        path: str = ".",
        glob_pattern: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> str:
        workspace = Path(self.workspace_root).resolve()
        if path == "/" or path == "":
            target = workspace
        else:
            target = (workspace / path).resolve()
            if not str(target).startswith(str(workspace)):
                raise PermissionError(f"Path {target} is outside workspace")
        if not target.exists():
            return ""
        entries = []
        if glob_pattern:
            for p in target.glob(glob_pattern):
                entries.append(p.name + "/" if p.is_dir() else p.name)
        else:
            for p in target.iterdir():
                entries.append(p.name + "/" if p.is_dir() else p.name)
        entries.sort()
        if limit is not None and limit > 0:
            entries = entries[:limit]
        return "\n".join(entries)

    def grep_repo(
        self,
        pattern: str,
        path: str = ".",
        glob: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> str:
        workspace = Path(self.workspace_root).resolve()
        if path == "/" or path == "":
            root = workspace
        else:
            root = (workspace / path).resolve()
            if not str(root).startswith(str(workspace)):
                raise PermissionError(f"Path {root} is outside workspace")
        if not root.exists():
            return "(no matches)"
        regex = re.compile(pattern)
        matches = []
        if glob:
            files = list(root.glob(glob))
        else:
            files = list(root.rglob("*"))
        files = [f for f in files if f.is_file()]
        files.sort(key=lambda f: str(f))
        for file_path in files:
            if file_path.stat().st_size > _TOOL_GREP_MAX_BYTES:
                matches.append(f"{file_path.relative_to(workspace)}:skipped (file too large)")
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except (UnicodeDecodeError, PermissionError):
                continue
            relative = str(file_path.relative_to(workspace))
            for line_no, line in enumerate(lines, 1):
                if regex.search(line):
                    matches.append(f"{relative}:{line_no}:{line.rstrip()}")
                    if limit and len(matches) >= limit:
                        break
            if limit and len(matches) >= limit:
                break
        if not matches:
            return "(no matches)"
        return "\n".join(matches[:limit] if limit else matches)
AGENTTOOLS

cat > tpch_monetdb/tools/cpu_info.py << 'CPUINFO'
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

def _truncate(text: str, max_len: int = 2000) -> str:
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return text[:half] + "\n... (truncated) ...\n" + text[-half:]

def _parse_cpuinfo_flags() -> List[str]:
    flags = []
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("flags") or line.startswith("Features"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        flags = parts[1].strip().split()
                        break
    except FileNotFoundError:
        pass
    return flags

def _parse_lscpu_summary() -> Dict[str, Any]:
    summary = {}
    try:
        result = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    summary[key.strip()] = val.strip()
    except Exception:
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        _, val = line.split(":", 1)
                        summary["Model name"] = val.strip()
                        break
            import platform
            summary["Architecture"] = platform.machine()
        except:
            pass
    return summary

def _build_response(cpuinfo_flags: List[str], lscpu_summary: Dict[str, Any]) -> Dict[str, Any]:
    isa_flags = []
    for flag in cpuinfo_flags:
        if flag in ("avx512f", "avx2", "avx", "sse4_2", "sse4_1", "neon", "asimd"):
            isa_flags.append(flag)
    target_cpu_hint = "native" if any(f in isa_flags for f in ("avx512f", "avx2")) else "generic"
    cpuinfo_raw = " ".join(cpuinfo_flags)
    lscpu_raw = json.dumps(lscpu_summary, indent=2)
    return {
        "cpu_info": {
            "flags": cpuinfo_flags,
            "isa_flags": isa_flags,
            "raw": _truncate(cpuinfo_raw, 1000),
        },
        "lscpu_summary": lscpu_summary,
        "lscpu_raw": _truncate(lscpu_raw, 1000),
        "target_cpu_hint": target_cpu_hint,
    }

class CpuInfoTool:
    def __init__(self, workspace_root: str, cache_dir: Optional[Path] = None):
        self.workspace_root = workspace_root
        self.cache_dir = cache_dir

    def run(self) -> Dict[str, Any]:
        flags = _parse_cpuinfo_flags()
        summary = _parse_lscpu_summary()
        return _build_response(flags, summary)

def make_cpu_info_tool(workspace_root: str, cache_dir: Optional[Path] = None) -> CpuInfoTool:
    return CpuInfoTool(workspace_root, cache_dir)
CPUINFO

cat > tpch_monetdb/oracle/result.py << 'RESULT'
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any, Dict
import json

@dataclass
class TpchQueryResult:
    query_id: str
    columns: List[str]
    rows: List[Tuple[Any, ...]]
    query_type: Optional[str] = None
    column_types: Optional[List[str]] = None
    source: Optional[str] = None
    row_count: Optional[int] = None
    created_at: Optional[datetime] = None
    sorted_by: Optional[Tuple[str, ...]] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.row_count is None and self.rows is not None:
            self.row_count = len(self.rows)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("sorted_by") is not None:
            d["sorted_by"] = list(d["sorted_by"])
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TpchQueryResult":
        if "created_at" in data and data["created_at"]:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "sorted_by" in data and data["sorted_by"] is not None:
            data["sorted_by"] = tuple(data["sorted_by"])
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> "TpchQueryResult":
        data = json.loads(json_str)
        return cls.from_dict(data)

    def get_summary(self) -> Dict[str, Any]:
        summary = {
            "query_id": self.query_id,
            "columns": self.columns,
            "rows": len(self.rows) if self.rows else 0,
            "row_count": self.row_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if self.source is not None:
            summary["source"] = self.source
        return summary
RESULT

cat > tpch_monetdb/oracle/tpch_validator.py << 'VALIDATOR'
import csv
from dataclasses import dataclass, asdict
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
    columns: List[str]
    row_count: int
    ordered: bool
    sorted_by: Optional[Tuple[str, ...]]
    mismatches: List[Dict[str, Any]]
    float_atol: float
    float_rtol: float
    overall_pass: bool = False
    column_check_pass: bool = True
    row_count_check_pass: bool = True
    value_check_pass: bool = True
    result_ordered: bool = False
    expected_row_count: Optional[int] = None
    actual_row_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mismatches"] = [asdict(m) if hasattr(m, "__dataclass_fields__") else m for m in self.mismatches]
        return d

    def get_summary(self) -> Dict[str, Any]:
        status = "PASS" if not self.mismatches else "FAIL"
        first = self.mismatches[0] if self.mismatches else None
        return {
            "status": status,
            "query_id": self.query_id,
            "columns": self.columns,
            "rows": self.row_count,
            "ordered": self.ordered,
            "first_mismatch": first,
        }

class TpchValidator:
    def compare_results(
        self,
        expected: TpchQueryResult,
        actual: TpchQueryResult,
        contract: Dict[str, Any],
    ) -> TpchValidationReport:
        return compare_tpch_results(expected, actual, contract)

    def parse_runtime_csv(self, csv_content: Union[str, Path], query_id: str) -> TpchQueryResult:
        if isinstance(csv_content, Path):
            csv_content = csv_content.read_text(encoding="utf-8")
        return parse_runtime_csv(csv_content, query_id)

def parse_runtime_csv(csv_content: str, query_id: str) -> TpchQueryResult:
    if not csv_content.strip():
        raise ValueError("Empty CSV content")
    lines = csv_content.strip().splitlines()
    reader = csv.reader(lines)
    header = next(reader)
    rows = []
    for row in reader:
        if not row:
            continue
        parsed = [_parse_csv_cell(cell) for cell in row]
        rows.append(tuple(parsed))
    return TpchQueryResult(
        query_id=query_id,
        columns=header,
        rows=rows,
        row_count=len(rows),
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

def compare_tpch_results(
    expected: TpchQueryResult,
    actual: TpchQueryResult,
    contract: Dict[str, Any],
) -> TpchValidationReport:
    ordered = contract.get("ordered", False)
    sorted_by = contract.get("sorted_by")
    float_atol = contract.get("float_atol", 1e-9)
    float_rtol = contract.get("float_rtol", 1e-9)
    report = _build_report(expected, actual, ordered, sorted_by, float_atol, float_rtol)
    if expected.columns != actual.columns:
        report.mismatches.append({"type": "column_mismatch", "expected": expected.columns, "actual": actual.columns})
        report.column_check_pass = False
        return report
    if expected.row_count != actual.row_count:
        report.mismatches.append({"type": "row_count_mismatch", "expected": expected.row_count, "actual": actual.row_count})
        report.row_count_check_pass = False
        return report
    if ordered:
        mismatches = _compare_ordered_rows(expected.rows, actual.rows, float_atol, float_rtol)
    else:
        mismatches = _compare_unordered_rows(expected.rows, actual.rows, sorted_by, float_atol, float_rtol)
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

def _compare_ordered_rows(expected, actual, atol, rtol):
    mismatches = []
    if len(expected) != len(actual):
        mismatches.append({"type": "row_count_mismatch", "expected": len(expected), "actual": len(actual)})
        return mismatches
    for i, (e, a) in enumerate(zip(expected, actual)):
        if not _compare_row_values(e, a, atol, rtol):
            mismatches.append({
                "row": i,
                "type": "value_mismatch",
                "expected": e,
                "actual": a,
            })
    return mismatches

def _compare_unordered_rows(expected, actual, sorted_by, atol, rtol):
    from collections import Counter
    def key(row):
        return tuple(round(v, 6) if isinstance(v, float) else v for v in row)
    exp_counter = Counter(key(r) for r in expected)
    act_counter = Counter(key(r) for r in actual)
    mismatches = []
    if exp_counter != act_counter:
        mismatches.append({"type": "unordered_mismatch", "expected_count": len(expected), "actual_count": len(actual)})
    return mismatches

def _rows_match_unordered(expected_rows, actual_rows, atol, rtol):
    return len(_compare_unordered_rows(expected_rows, actual_rows, None, atol, rtol)) == 0

def _find_matching_row(row, candidates, atol, rtol):
    for idx, cand in enumerate(candidates):
        if _row_values_equal(row, cand, atol, rtol):
            return idx
    return None

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
VALIDATOR

cat >> tpch_monetdb/main_tpch_monetdb.py << 'MAINPATCH'
# --- DeepSeek reasoning helpers (added by fix script) ---
from typing import Optional

def _normalize_deepseek_reasoning_effort(reasoning_effort: Optional[str]) -> Optional[str]:
    if reasoning_effort is None:
        return None
    if reasoning_effort.lower() in ("xhigh", "max"):
        return "max"
    if reasoning_effort.lower() == "none":
        return "disabled"
    return "high"
MAINPATCH

if [ -f tpch_monetdb/tools/stage_tool_policy.py ]; then
    sed -i 's/from enum import StrEnum/try:\n    from enum import StrEnum\nexcept ImportError:\n    from enum import Enum\n    class StrEnum(str, Enum):\n        pass/' tpch_monetdb/tools/stage_tool_policy.py
    echo "已修复 stage_tool_policy.py 的 StrEnum 兼容性"
fi

echo ""
echo "=== 所有文件修补完成！==="
echo "请运行测试："
echo "python -m pytest tpch_monetdb/tests/test_assignment_deepseek_public.py tpch_monetdb/tests/test_assignment_tools_public.py tpch_monetdb/tests/test_assignment_validator_public.py -q"
