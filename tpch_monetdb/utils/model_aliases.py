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