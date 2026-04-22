from __future__ import annotations

from backend.services.strategy.tool_registry_v1 import ToolSpec, tool_registry_v1
from backend.services.strategy.tools_data_v1 import tool_data_load_bars
from backend.services.strategy.tools_indicators_v1 import tool_indicator_compute_batch
from backend.services.strategy.tools_structures_v1 import tool_structure_level_generator
from backend.services.strategy.tools_patterns_v1 import tool_pattern_detect_batch


def bootstrap_tool_registry_v1():
    # data
    tool_registry_v1.register(ToolSpec(name="data.load_bars", version="1.0.0", func=tool_data_load_bars, cacheable=False))
    # indicators
    tool_registry_v1.register(ToolSpec(name="indicator.compute_batch", version="1.0.0", func=tool_indicator_compute_batch, cacheable=True))
    # structures
    tool_registry_v1.register(ToolSpec(name="structure.level_generator", version="1.0.0", func=tool_structure_level_generator, cacheable=False))
    # patterns
    tool_registry_v1.register(ToolSpec(name="pattern.detect_batch", version="1.0.0", func=tool_pattern_detect_batch, cacheable=False))


# eager bootstrap on import
bootstrap_tool_registry_v1()
