import json

from langchain_core.tools import tool


@tool
def draw_objects(objects: list[dict]) -> str:
    """通用绘图入口。支持画线(hline, trendline)、标记(marker)和图形(box, arrow)。
    objects: 一组绘图对象的列表，例如 [{"type": "hline", "price": 1.10, "color": "#ef4444", "lineWidth": 2, "lineStyle": "dashed"}, {"type": "marker", "time": 1612131, "position": "belowBar", "text": "Buy", "color": "#22c55e"}]
    你可以指定 color 属性（如 "#ef4444" 表示红色, "#22c55e" 表示绿色, "#3b82f6" 表示蓝色），lineWidth（线宽），lineStyle（线型：solid/dashed/dotted）。
    """
    return "Successfully sent UI command to draw objects"


@tool
def draw_clear_all() -> str:
    """移除图表上的所有手动或 AI 绘制的线条和标记。"""
    return "Successfully sent UI command to clear all drawings"


@tool
def draw_clear_ai() -> str:
    """仅移除 AI 绘制的线条/标记，不影响用户手动绘图。"""
    return "Successfully sent UI command to clear AI drawings"


@tool
def draw_remove_object(id: str) -> str:
    """移除特定的绘图对象。"""
    return f"Successfully sent UI command to remove drawing {id}"


@tool
def execute_ui_action(
    action: str = None,
    type: str = None,
    price: float = None,
    time: int = None,
    color: str = None,
    text: str = None,
    position: str = None,
    shape: str = None,
    t1: int = None,
    t2: int = None,
    p1: float = None,
    p2: float = None,
    objects: list = None,
) -> str:
    """Emit a JSON action to the frontend to draw lines, markers or update the chart."""
    cmd = {k: v for k, v in locals().items() if v is not None and k != "cmd"}
    if "type" in cmd and "action" not in cmd:
        cmd["action"] = cmd["type"]
    return f"Successfully sent UI command: {json.dumps(cmd)}"
