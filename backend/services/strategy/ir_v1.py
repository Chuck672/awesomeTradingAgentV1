from __future__ import annotations

"""
Executable IR v1（最小可用版）

目标：
- 把 StrategySchema v2 编译成“可执行 DAG”的中间表示（IR）
- IR 只表达：步骤、依赖、输入/输出契约、参数
- Executor/ToolRegistry 在后续阶段实现；本阶段先保证 IR/DSL 输出稳定
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic.v1 import BaseModel, Field


class IRPort(BaseModel):
    name: str
    jsonschema: Dict[str, Any] = Field(default_factory=dict, alias="schema")

    class Config:
        allow_population_by_field_name = True


class IRStep(BaseModel):
    id: str
    kind: str  # tool name / compiler step name
    depends_on: List[str] = Field(default_factory=list)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    params: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class IRGraph(BaseModel):
    version: Literal["1.0"] = "1.0"
    steps: List[IRStep] = Field(default_factory=list)

    def step_ids(self) -> List[str]:
        return [s.id for s in self.steps]


class CompilationReport(BaseModel):
    compiler: str = "ir_compiler_v1"
    compiler_version: str = "0.1.0"
    spec_version: str = "2.0"
    status: Literal["ok", "warning", "error"] = "ok"
    summary: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    unsupported_features: List[Dict[str, Any]] = Field(default_factory=list)
    capabilities_required: List[Dict[str, Any]] = Field(default_factory=list)
    normalization_fixes: List[Dict[str, Any]] = Field(default_factory=list)


def render_text_dsl(ir: IRGraph) -> str:
    """
    Text DSL v1（由 IR 渲染，便于调试/审计）
    """
    lines: List[str] = []
    lines.append(f"# IRGraph v{ir.version}")
    for s in ir.steps:
        dep = ", ".join(s.depends_on) if s.depends_on else "-"
        lines.append("")
        lines.append(f"step {s.id} kind={s.kind} depends=[{dep}]")
        if s.params:
            for k, v in s.params.items():
                lines.append(f"  param {k} = {v}")
        if s.inputs:
            for k, v in s.inputs.items():
                lines.append(f"  input {k} <- {v}")
        if s.outputs:
            for k, v in s.outputs.items():
                lines.append(f"  output {k} -> {v}")
        if s.notes:
            lines.append(f"  note {s.notes}")
    lines.append("")
    return "\n".join(lines)
