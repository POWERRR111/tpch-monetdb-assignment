import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional


class CpuInfoTool:
    def __init__(self, workspace_root: str, cache_dir: Optional[Path] = None, max_output_tokens: Optional[int] = None):
        self.workspace_root = workspace_root
        self.cache_dir = cache_dir
        self.max_output_tokens = max_output_tokens

    def _truncate(self, text: str, max_len: Optional[int] = None) -> str:
        """截断过长的文本，保留 head/tail 并添加截断标记。"""
        if max_len is None:
            max_len = self.max_output_tokens or 2000
        if len(text) <= max_len:
            return text
        half = max_len // 2
        return text[:half] + "\n... (truncated) ...\n" + text[-half:]

    def _parse_cpuinfo_flags(self, text: str) -> List[str]:
        flags = []
        for line in text.splitlines():
            if line.startswith("flags") or line.startswith("Features"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    flags = parts[1].strip().split()
                    break
        return flags

    def _parse_lscpu_summary(self, text: str) -> Dict[str, Any]:
        summary = {}
        for line in text.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                summary[key.strip()] = val.strip()
        return summary

    def _build_response(self, probes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        cpuinfo_text = probes.get("cpuinfo", {}).get("stdout", "")
        lscpu_text = probes.get("lscpu", {}).get("stdout", "")
        flags = self._parse_cpuinfo_flags(cpuinfo_text)
        summary = self._parse_lscpu_summary(lscpu_text)
        isa_flags = []
        for flag in flags:
            if flag in ("avx512f", "avx2", "avx", "sse4_2", "sse4_1", "neon", "asimd"):
                isa_flags.append(flag)
        has_evidence = bool(flags) or bool(summary)
        target_cpu_hint = None if not has_evidence else ("native" if any(f in isa_flags for f in ("avx512f", "avx2")) else "generic")
        vectorization_recommendation = "vectorization_support_unclear" if not has_evidence else ("vectorization_available" if isa_flags else "vectorization_not_detected")
        cpuinfo_raw = " ".join(flags)
        lscpu_raw = json.dumps(summary, indent=2)
        max_len = self.max_output_tokens or 2000
        # 构建 cache_summary
        cache_summary = {}
        for key, value in summary.items():
            if "cache" in key.lower():
                # 提取缓存大小，例如 "L3 cache: 32 MiB" -> "L3": "32 MiB"
                # 移除 "cache" 字样，保留数字和单位
                cache_key = key.replace("cache", "").strip()
                # 简化键名，如 "L3" 或 "L1d"
                cache_summary[cache_key] = value
        # 如果 summary 中有 "L3 cache"，直接映射
        if "L3 cache" in summary:
            cache_summary["L3"] = summary["L3 cache"]
        if "L2 cache" in summary:
            cache_summary["L2"] = summary["L2 cache"]
        if "L1d cache" in summary:
            cache_summary["L1d"] = summary["L1d cache"]
        if "L1i cache" in summary:
            cache_summary["L1i"] = summary["L1i cache"]
        return {
            "arch": summary.get("Architecture", "unknown"),
            "model_name": summary.get("Model name", ""),
            "cpu_info": {
                "flags": flags,
                "isa_flags": isa_flags,
                "raw": self._truncate(cpuinfo_raw, max_len),
            },
            "lscpu_summary": summary,
            "lscpu_raw": self._truncate(lscpu_raw, max_len),
            "target_cpu_hint": target_cpu_hint,
            "vectorization_recommendation": vectorization_recommendation,
            "vectorization_flags": [f for f in ["avx2", "avx", "sse4_2"] if f in isa_flags],
            "cache_summary": cache_summary,
        }

    def run(self) -> Dict[str, Any]:
        flags = []
        try:
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo_text = f.read()
            flags = self._parse_cpuinfo_flags(cpuinfo_text)
        except FileNotFoundError:
            pass
        summary = {}
        try:
            result = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                summary = self._parse_lscpu_summary(result.stdout)
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
        isa_flags = []
        for flag in flags:
            if flag in ("avx512f", "avx2", "avx", "sse4_2", "sse4_1", "neon", "asimd"):
                isa_flags.append(flag)
        has_evidence = bool(flags) or bool(summary)
        target_cpu_hint = None if not has_evidence else ("native" if any(f in isa_flags for f in ("avx512f", "avx2")) else "generic")
        vectorization_recommendation = "vectorization_support_unclear" if not has_evidence else ("vectorization_available" if isa_flags else "vectorization_not_detected")
        cpuinfo_raw = " ".join(flags)
        lscpu_raw = json.dumps(summary, indent=2)
        max_len = self.max_output_tokens or 2000
        cache_summary = {}
        if "L3 cache" in summary:
            cache_summary["L3"] = summary["L3 cache"]
        if "L2 cache" in summary:
            cache_summary["L2"] = summary["L2 cache"]
        if "L1d cache" in summary:
            cache_summary["L1d"] = summary["L1d cache"]
        if "L1i cache" in summary:
            cache_summary["L1i"] = summary["L1i cache"]
        return {
            "arch": summary.get("Architecture", "unknown"),
            "model_name": summary.get("Model name", ""),
            "cpu_info": {
                "flags": flags,
                "isa_flags": isa_flags,
                "raw": self._truncate(cpuinfo_raw, max_len),
            },
            "lscpu_summary": summary,
            "lscpu_raw": self._truncate(lscpu_raw, max_len),
            "target_cpu_hint": target_cpu_hint,
            "vectorization_recommendation": vectorization_recommendation,
            "vectorization_flags": [f for f in ["avx2", "avx", "sse4_2"] if f in isa_flags],
            "cache_summary": cache_summary,
        }

    async def on_invoke_tool(self, ctx, args_json: str) -> str:
        try:
            import json as jsonlib
            try:
                args = jsonlib.loads(args_json)
                if "max_output_tokens" in args:
                    self.max_output_tokens = args["max_output_tokens"]
            except jsonlib.JSONDecodeError:
                return f"Invalid JSON: {args_json}"
            result = self.run()
            return jsonlib.dumps(result, indent=2)
        except Exception as exc:
            return f"Error: {exc}"


def make_cpu_info_tool(workspace_root: str, cache_dir: Optional[Path] = None) -> CpuInfoTool:
    return CpuInfoTool(workspace_root, cache_dir)