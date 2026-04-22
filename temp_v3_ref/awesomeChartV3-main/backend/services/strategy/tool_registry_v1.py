from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple


def _stable_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return json.dumps(str(obj), ensure_ascii=False)


def _hash_obj(obj: Any) -> str:
    return hashlib.sha256(_stable_json(obj).encode("utf-8")).hexdigest()[:16]


ToolFunc = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass
class ToolSpec:
    name: str
    version: str
    func: ToolFunc
    cacheable: bool = True


class ToolRegistryV1:
    """
    极简 Tool Registry：
    - tool 以 name@version 唯一标识
    - 支持 in-memory 缓存（以 inputs/params hash 作为 key）
    - 返回 telemetry（耗时、cache_hit、cache_key）
    """

    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}
        self._cache: Dict[str, Dict[str, Any]] = {}

    def register(self, spec: ToolSpec):
        key = f"{spec.name}@{spec.version}"
        self._tools[key] = spec

    def get(self, name: str, version: Optional[str] = None) -> ToolSpec:
        if version:
            key = f"{name}@{version}"
            if key not in self._tools:
                raise KeyError(f"tool not found: {key}")
            return self._tools[key]
        # pick latest-ish: lexical max (simple)
        candidates = [s for k, s in self._tools.items() if k.startswith(f"{name}@")]
        if not candidates:
            raise KeyError(f"tool not found: {name}")
        candidates = sorted(candidates, key=lambda x: x.version)
        return candidates[-1]

    def run(self, name: str, payload: Dict[str, Any], *, version: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        spec = self.get(name, version=version)
        cache_key = f"{spec.name}@{spec.version}:{_hash_obj(payload)}"
        t0 = time.time()
        if spec.cacheable and cache_key in self._cache:
            out = self._cache[cache_key]
            telem = {"tool": spec.name, "version": spec.version, "cache_hit": True, "cache_key": cache_key, "elapsed_ms": int((time.time() - t0) * 1000)}
            return out, telem
        out = spec.func(payload)
        if spec.cacheable:
            self._cache[cache_key] = out
        telem = {"tool": spec.name, "version": spec.version, "cache_hit": False, "cache_key": cache_key, "elapsed_ms": int((time.time() - t0) * 1000)}
        return out, telem


# singleton
tool_registry_v1 = ToolRegistryV1()

