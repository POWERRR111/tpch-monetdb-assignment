import os
import logging
from typing import Optional,Any
from dataclasses import dataclass

@dataclass
class ModelConfig:
    model_name: str
    accounting_model_name: str
    provider: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    use_litellm: bool = True
    openai_client: Optional[Any] = None

def setup_model_config(model_identifier: str) -> ModelConfig:
    from .model_aliases import normalize_accounting_model_name, get_model_provider

    # 去除 litellm/ 前缀（如果有）
    raw = model_identifier
    if raw.startswith("litellm/"):
        raw = raw[len("litellm/"):]

    provider = get_model_provider(raw)
    if provider == "deepseek":
        accounting = normalize_accounting_model_name(raw)
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
            use_litellm=True,
        )
    if provider == "openai" and "deepseek" in raw:
        logging.warning(f"Deprecated: Using legacy openai/deepseek path: {model_identifier}")
        base_url = os.getenv("LITELLM_BASE_URL") or "https://api.deepseek.com"
        accounting = normalize_accounting_model_name(raw)
        return ModelConfig(
            model_name=model_identifier,
            accounting_model_name=accounting,
            provider="openai",
            base_url=base_url,
            api_key=os.getenv("LITELLM_API_KEY"),
            use_litellm=True,
        )
    if provider == "anthropic" and "deepseek" in raw:
        raise RuntimeError(f"Anthropic provider does not support DeepSeek models: {model_identifier}")
    # Default fallback
    return ModelConfig(
        model_name=model_identifier,
        accounting_model_name=normalize_accounting_model_name(raw),
        provider=provider,
        base_url=os.getenv("LITELLM_BASE_URL"),
        api_key=os.getenv("LITELLM_API_KEY"),
        use_litellm=True,
    )