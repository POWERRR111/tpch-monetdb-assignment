from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any, Dict
import json

@dataclass
class TpchQueryResult:
    query_id: str
    columns: Optional[List[str]] = None
    rows: Optional[List[Tuple[Any, ...]]] = None
    query_type: Optional[str] = None
    column_types: Optional[List[str]] = None
    source: Optional[str] = None
    source_protocol: Optional[str] = None   # 新增
    row_count: Optional[int] = None
    created_at: Optional[str] = None
    sorted_by: Optional[Tuple[str, ...]] = None

    def __post_init__(self):
        if self.created_at is None:
            # 生成 UTC ISO 格式，并将 +00:00 替换为 Z
            self.created_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        if self.row_count is None and self.rows is not None:
            self.row_count = len(self.rows)
        if self.columns is None:
            self.columns = []
        if self.rows is None:
            self.rows = []

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("sorted_by") is not None:
            d["sorted_by"] = list(d["sorted_by"])
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TpchQueryResult":
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
            "created_at": self.created_at,
        }
        if self.source is not None:
            summary["source"] = self.source
        return summary