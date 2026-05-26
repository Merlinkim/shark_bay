from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

ALLOWED_STRATEGY_TYPES = {"signal_strategy"}
RESERVED_FUTURE_STRATEGY_TYPES = {"event_strategy", "pair_strategy", "portfolio_strategy"}
REQUIRED_FUNCTIONS = ("required_features", "prepare_features", "generate_signals")
FORBIDDEN_IMPORT_SNIPPETS = ("import psycopg", "import requests", "urllib", "socket", "open(", "Path(")


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_id: str
    meta: dict[str, Any]
    module: ModuleType


class StrategyLoader:
    def __init__(self, roots: list[Path] | None = None):
        self.roots = roots or [Path("strategies/builtin"), Path("strategies/gawain")]
        self._definitions: dict[str, StrategyDefinition] = {}

    def discover(self) -> dict[str, StrategyDefinition]:
        discovered: dict[str, StrategyDefinition] = {}
        for root in self.roots:
            if not root.exists():
                continue
            for py_file in sorted(root.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                definition = self._load_module(py_file)
                sid = definition.strategy_id
                if sid in discovered:
                    raise ValueError(f"Duplicate strategy_id detected: {sid}")
                discovered[sid] = definition
        self._definitions = discovered
        return discovered

    def list_metadata(self) -> dict[str, dict[str, Any]]:
        if not self._definitions:
            self.discover()
        out = {}
        for sid, definition in self._definitions.items():
            meta = dict(definition.meta)
            meta.setdefault("metadata_only", False)
            out[sid] = meta
        return out

    def get(self, strategy_id: str) -> StrategyDefinition:
        if not self._definitions:
            self.discover()
        if strategy_id not in self._definitions:
            raise ValueError("Unknown strategy_name")
        return self._definitions[strategy_id]

    def _load_module(self, py_file: Path) -> StrategyDefinition:
        source = py_file.read_text(encoding="utf-8")
        for token in FORBIDDEN_IMPORT_SNIPPETS:
            if token in source:
                raise ValueError(f"Strategy sandbox violation in {py_file}: {token}")
        module_name = f"strategy_{py_file.stem}_{abs(hash(str(py_file)))}"
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None or spec.loader is None:
            raise ValueError(f"Unable to load strategy module: {py_file}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        meta = getattr(module, "STRATEGY_META", None)
        if not isinstance(meta, dict):
            raise ValueError(f"Missing STRATEGY_META in {py_file}")
        strategy_id = meta.get("strategy_id")
        if not strategy_id:
            raise ValueError(f"Missing strategy_id in STRATEGY_META for {py_file}")
        strategy_type = meta.get("strategy_type")
        if strategy_type not in ALLOWED_STRATEGY_TYPES and strategy_type not in RESERVED_FUTURE_STRATEGY_TYPES:
            raise ValueError(f"Invalid strategy_type for {strategy_id}: {strategy_type}")
        if meta.get("research_only") is not True:
            raise ValueError(f"strategy {strategy_id} must set research_only=True")
        for fn_name in REQUIRED_FUNCTIONS:
            if not callable(getattr(module, fn_name, None)):
                raise ValueError(f"Missing required function {fn_name} in {strategy_id}")
        return StrategyDefinition(strategy_id=strategy_id, meta=meta, module=module)


strategy_loader = StrategyLoader()
