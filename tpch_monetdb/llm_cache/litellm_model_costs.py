import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any
import litellm

COST_OVERRIDES_JSON = Path(__file__).parent / "litellm_model_cost_overrides.json"

_REGISTERED = False

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
    global _REGISTERED
    if _REGISTERED:
        return
    _REGISTERED = True
    # 直接使用 sys.modules 中的 litellm 模块（支持测试中的 mock）
    litellm_mod = sys.modules.get("litellm")
    if litellm_mod is None:
        return
    overrides = load_tpch_monetdb_litellm_model_cost_overrides()
    litellm_mod.model_cost.update(overrides)
    # 检查是否存在 litellm.utils 模块（测试中会 mock）
    utils_mod = sys.modules.get("litellm.utils")
    if utils_mod is not None and hasattr(utils_mod, "_invalidate_model_cost_lowercase_map"):
        utils_mod._invalidate_model_cost_lowercase_map()
    else:
        # 否则手动刷新 lowercase map
        try:
            from litellm import _model_cost_lowercase
            _model_cost_lowercase.clear()
            for k, v in litellm_mod.model_cost.items():
                _model_cost_lowercase[k.lower()] = v
        except ImportError:
            pass
    logging.info(f"Registered {len(overrides)} model cost overrides")

def force_litellm_local_model_cost_map():
    """Force local model cost map (placeholder)."""
    # 这个函数用于确保 Litellm 使用本地成本映射，但我们暂时不实现具体逻辑
    pass

def validate_gpt55_xhigh_model_cost():
    """Validate GPT-5.5 xhigh model cost (placeholder)."""
    # 这个函数用于验证 GPT-5.5 的 xhigh 成本，暂时不实现
    pass