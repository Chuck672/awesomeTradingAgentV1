from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Body
from fastapi.responses import StreamingResponse
from fastapi.responses import FileResponse
import asyncio
import os
from typing import List, Dict, Any
from pydantic import BaseModel

from backend.api.dependencies import get_current_broker_deps
from backend.database.app_config import app_config
from backend.services.historical import historical_service
from backend.services.research.job_store import job_store
from backend.services.research.event_study import run_event_study
from backend.services.research.strategy_backtest import run_strategy_backtest
from backend.services.research.optimize import run_optimize
from backend.services.research.strategies import list_strategies, get_strategy_by_id
from backend.services.ai.openai_compat import chat_completions, chat_completions_stream
from backend.services.calendar_service import get_calendar_events
from backend.services.strategy.breakout_mvp import (
    compile_breakout_spec_to_dsl,
    compile_breakout_spec_with_report,
    parse_breakout_prompt_to_protocol,
    scan_breakout_candidates_on_bars,
)
from backend.services.strategy.spec_validation import validate_strategy_spec
from backend.services.strategy.gate_mvp import suggest_gate_decision_mvp, suggest_trade_plan_from_evidence
from backend.services.strategy.schema_validate import validate_schema_v2
from backend.services.strategy.schema_v2 import schema_json as schema_v2_jsonschema
from backend.services.strategy.ai_parse_schema_v2 import ai_parse_to_schema_v2
from backend.services.strategy.capabilities_v2 import load_capabilities_config
from backend.services.strategy.compile_v2_to_ir import compile_schema_v2_to_ir
from backend.services.strategy.executor_v1 import execute_ir_v1
from backend.services.ai.chart_tools import tool_schemas as ai_tool_schemas, system_prompt as ai_system_prompt, parse_tool_calls as ai_parse_tool_calls
from backend.services.watchlist_store import list_watchlist, add_symbol as watchlist_add_symbol, remove_symbol as watchlist_remove_symbol
from backend.services.alerts_store import list_alerts as alerts_list, create_alert as alerts_create, delete_alert as alerts_delete, set_enabled as alerts_set_enabled, list_events as alerts_list_events, list_ai_reports as alerts_list_reports
from backend.domain.market.catalog import get_market_feature_catalog
from backend.data_sources.mt5_source import MT5_AVAILABLE, mt5_source
from backend.services.chart_scene import scene_engine, SceneParams
import json
import re

if MT5_AVAILABLE:
    import MetaTrader5 as mt5

router = APIRouter()


def _extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    尝试从 LLM 文本中提取 JSON。
    允许：
      - 纯 JSON
      - ```json ... ```
    """
    s = (text or "").strip()
    if not s:
        return {}
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    m = re.search(r"```json\\s*([\\s\\S]*?)```", s, re.IGNORECASE)
    if m:
        try:
            obj = json.loads(m.group(1))
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}

# 标记已恢复 runtime_state，避免每次请求都重复 restore（仍然容错：若无则忽略）
_scene_runtime_restored: set[tuple[str, str]] = set()

class BrokerConfig(BaseModel):
    server: str
    login: str = ""
    password: str = ""
    path: str = ""

@router.post("/broker/connect")
async def connect_broker(config: BrokerConfig):
    """
    Connects to an MT5 broker and initializes its sandbox.
    """
    if not MT5_AVAILABLE:
        raise HTTPException(status_code=503, detail="MT5 is not available")
        
    success = mt5_source.connect_broker(
        server=config.server,
        login=config.login,
        password=config.password,
        path=config.path
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to connect to MT5 broker. Check credentials and server.")
        
    broker_id = app_config.add_broker(server=config.server, login=config.login, path=config.path)
    app_config.set_active_broker(broker_id)
    
    return {"message": "Successfully connected to broker", "broker_id": broker_id}

@router.get("/broker/active")
async def get_active_broker():
    broker = app_config.get_active_broker()
    if not broker:
        return {"active": False}
    return {"active": True, "broker": broker}

@router.get("/mt5/symbols")
async def get_mt5_symbols(search: str = Query(None, description="Search term for symbols")):
    """
    Returns the full list of symbols available from the MT5 broker.
    Supports optional search filtering.
    """
    if not MT5_AVAILABLE:
        raise HTTPException(status_code=503, detail="MT5 is not available or initialized")
        
    try:
        # Get all symbols from MT5
        symbols = mt5.symbols_get()
        if symbols is None:
            raise HTTPException(status_code=500, detail="Failed to get symbols from MT5")
            
        result = []
        for s in symbols:
            # If search term is provided, filter by name
            if search and search.upper() not in s.name.upper():
                continue
                
            result.append({
                "name": s.name,
                "description": s.description,
                "path": s.path,
                "category": s.path.split('\\')[0] if '\\' in s.path else "Unknown"
            })
            
        # Return top 100 to avoid overwhelming the frontend if no search is provided
        return result[:100] if not search else result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/symbols/add")
async def add_symbol(symbol: str = Query(..., description="The symbol name to add, e.g. EURUSD")):
    """
    Adds a new symbol to the active list so it starts tracking and fetching data.
    """
    if not MT5_AVAILABLE:
        raise HTTPException(status_code=503, detail="MT5 is not available")
        
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured. Please connect a broker first.")
        
    meta_store = deps['meta_store']
    
    # Check if symbol exists in MT5
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found in MT5 broker")
        
    # Add to config store
    default_tf = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
    meta_store.add_symbol(symbol, default_tf)
    
    # Trigger initial catch-up immediately
    from backend.services.ingestion import ingestion_service
    import asyncio
    
    # 我们恢复成异步模式（“秒回”），让任务在后台静默执行。
    # 这样彻底避免前端的 timeout 报错和 socket hang up 崩溃。
    loop = asyncio.get_event_loop()
    for tf in default_tf:
        loop.create_task(ingestion_service.reconcile_symbol_timeframe(symbol, tf))
        
    return {"message": f"Symbol {symbol} added and historical data sync started"}

@router.delete("/symbols/clear")
async def clear_all_symbols():
    """
    Clears all active symbols from the tracking database.
    """
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")
    deps['meta_store'].clear_all_symbols()
    return {"message": "All symbols cleared from active tracking list"}

@router.post("/upload-symbol")
async def upload_symbol(file: UploadFile = File(...)):
    """
    Mock upload endpoint.
    """
    raise HTTPException(status_code=400, detail="Upload disabled. Please search and add MT5 symbols directly.")

@router.get("/symbols/progress")
async def get_sync_progress():
    from backend.services.ingestion import ingestion_service
    return list(ingestion_service.active_progress.values())

@router.post("/tools/gap-repair")
async def tools_gap_repair(payload: Dict[str, Any] = Body(default={})):
    symbol = str(payload.get("symbol") or "").strip()
    timeframe = str(payload.get("timeframe") or "").strip()
    all_timeframes = bool(payload.get("all_timeframes", True))
    days_lookback = int(payload.get("days_lookback") or 15)

    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    if days_lookback <= 0:
        days_lookback = 15

    from backend.services.ingestion import ingestion_service

    if all_timeframes:
        timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    else:
        if not timeframe:
            raise HTTPException(status_code=400, detail="timeframe is required when all_timeframes=false")
        timeframes = [timeframe]

    results: List[Dict[str, Any]] = []
    for tf in timeframes:
        rep = await ingestion_service.check_and_repair_gaps(symbol, tf, days_lookback=days_lookback)
        results.append({"symbol": symbol, "timeframe": tf, "result": rep})
        await asyncio.sleep(0)

    return {"ok": True, "symbol": symbol, "timeframes": timeframes, "results": results}

@router.get("/symbols")
async def get_symbols():
    """Returns the list of active symbols and their supported timeframes."""
    deps = get_current_broker_deps()
    if not deps:
        return []
        
    symbols = deps['meta_store'].get_active_symbols()
        
    # Format for frontend dropdown
    result = []
    for sym, tfs in symbols.items():
        result.append({
            "name": sym,
            "description": f"{sym} Market Data",
            "type": "forex",
            "timeframes": tfs
        })
    return result

@router.get("/history")
async def get_history(
    symbol: str = Query(..., description="e.g. EURUSD"),
    timeframe: str = Query(..., description="e.g. M1, H1"),
    before_time: int = Query(0, description="Fetch data before this timestamp for lazy loading"),
    limit: int = Query(5000, description="Max number of bars to return")
):
    """
    Returns historical OHLCV data for Lightweight Charts.
    """
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")
        
    try:
        from backend.services.historical import historical_service
        data = historical_service.get_history(symbol, timeframe, before_time=before_time, limit=limit)
        
        # Transform DuckDB rows to Lightweight Charts expected format if needed
        formatted_data = []
        for row in data:
            formatted_data.append({
                "time": row['time'],
                "open": row['open'],
                "high": row['high'],
                "low": row['low'],
                "close": row['close'],
                "volume": row.get('tick_volume', 0),
                "delta_volume": row.get('delta_volume', 0)
            })
            
        return formatted_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/range")
async def get_history_range(
    symbol: str = Query(..., description="e.g. XAUUSDz"),
    timeframe: str = Query(..., description="e.g. M5, H1"),
    from_time: int = Query(..., description="UTC unix seconds (inclusive)"),
    to_time: int = Query(..., description="UTC unix seconds (inclusive)"),
    limit: int = Query(20000, description="Max number of bars to return"),
):
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")
    bars = historical_service.get_history_range(symbol, timeframe, from_time=int(from_time), to_time=int(to_time), limit=int(limit))
    formatted = []
    for row in bars:
        formatted.append(
            {
                "time": row["time"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row.get("tick_volume", 0),
                "delta_volume": row.get("delta_volume", 0),
            }
        )
    return formatted


# -----------------------------
# AI - Chart Assistant (MVP)
# -----------------------------


@router.post("/ai/chat")
async def ai_chat(payload: Dict[str, Any] = Body(default={})):
    """
    MVP：图表自然语言操控
    - 使用 OpenAI-compatible chat/completions + tool calling
    - 后端只做：调用 LLM、解析 tool_calls 为 actions
    - 前端负责执行 actions（更新图表 state / 调用 ChartRef 方法）
    """

    user_input = str(payload.get("input") or "").strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="input is required")

    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise HTTPException(status_code=400, detail="missing settings: base_url/api_key/model")

    chart_state = payload.get("chart_state") if isinstance(payload.get("chart_state"), dict) else {}
    sym = str(chart_state.get("symbol") or "")
    tf = str(chart_state.get("timeframe") or "")
    enabled = chart_state.get("enabled") if isinstance(chart_state.get("enabled"), dict) else {}

    ctx_lines = []
    if sym or tf:
        ctx_lines.append(f"当前图表：{sym} {tf}".strip())
    if enabled:
        ctx_lines.append(
            "当前指标开关："
            + ", ".join(
                [
                    f"svp={'on' if enabled.get('svp') else 'off'}",
                    f"vrvp={'on' if enabled.get('vrvp') else 'off'}",
                    f"bubble={'on' if enabled.get('bubble') else 'off'}",
                ]
            )
        )

    # -----------------------------
    # 低延迟直出（不走 LLM）
    # 目标：不要因为“简单指令”让 AI 回复时间变长
    # -----------------------------
    def _extract_symbol_from_text(text: str) -> str:
        # 提取类似 EURUSD / XAUUSDz / BTCUSD 等 token；若没找到则回退当前图表 symbol
        tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9]{2,15}\b", text or "")
        # 优先包含 USD 的
        for t in tokens:
            if "USD" in t.upper():
                return t
        return tokens[0] if tokens else sym

    def _parse_timeframe(text: str) -> str | None:
        t = (text or "").lower().replace("分钟", "min").replace("分", "min").replace(" ", "")
        # 常见写法：5min/15min/30min/1h/4h/1d
        # 注意：必须先匹配更长的（15min 含有 5min 子串），否则会误判为 M5
        if re.search(r"(^|[^0-9])30min(?![0-9])", t) or "m30" in t:
            return "M30"
        if re.search(r"(^|[^0-9])15min(?![0-9])", t) or "m15" in t:
            return "M15"
        if re.search(r"(^|[^0-9])5min(?![0-9])", t) or "m5" in t:
            return "M5"
        if re.search(r"(^|[^0-9])1min(?![0-9])", t) or "m1" in t:
            return "M1"
        if "1h" in t or "h1" in t:
            return "H1"
        if "4h" in t or "h4" in t:
            return "H4"
        if "1d" in t or "d1" in t or "日线" in t:
            return "D1"
        return None

    def _direct_quote_response(text: str) -> Dict[str, Any]:
        symbol = _extract_symbol_from_text(text)
        result = {}
        # 复用已有查询工具实现（与 stream 接口同逻辑）
        try:
            # 内部调用：market_get_quote
            result = {"ok": True}
            if MT5_AVAILABLE:
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    result = {"ok": False, "error": f"symbol_info_tick returned None for {symbol}"}
                else:
                    bid = float(getattr(tick, "bid", 0.0) or 0.0)
                    ask = float(getattr(tick, "ask", 0.0) or 0.0)
                    last = float(getattr(tick, "last", 0.0) or 0.0) or (bid if bid else 0.0)
                    spread = (ask - bid) if (ask and bid) else None
                    result = {"ok": True, "symbol": symbol, "bid": bid, "ask": ask, "last": last, "spread": spread}
            else:
                data = historical_service.get_history(symbol, tf or "M1", before_time=0, limit=1)
                if not data:
                    result = {"ok": False, "error": "no data for symbol"}
                else:
                    last = float(data[-1]["close"])
                    result = {"ok": True, "symbol": symbol, "bid": None, "ask": None, "last": last, "spread": None}
        except Exception as e:
            result = {"ok": False, "error": str(e)}

        if not result.get("ok"):
            return {"ok": True, "assistant": {"content": f"获取报价失败：{result.get('error')}", "tool_calls": []}, "actions": [], "warnings": ["direct_quote_failed"]}

        bid = result.get("bid")
        ask = result.get("ask")
        last = result.get("last")
        spread = result.get("spread")
        s = result.get("symbol") or symbol

        # 文字回答（用户最关心）
        if bid is not None and ask is not None and bid and ask:
            content = f"{s} 报价：Bid {bid} / Ask {ask}" + (f"（Spread {spread}）" if spread is not None else "")
            price_for_line = float((bid + ask) / 2.0)
        else:
            content = f"{s} 最新价：{last}"
            price_for_line = float(last)

        actions: List[Dict[str, Any]] = []
        if re.search(r"(画线|画出来|落图|标注)", text):
            actions.append({"type": "chart_draw", "objects": [{"type": "hline", "price": price_for_line, "color": "#60a5fa", "text": f"{s}"}]})
        return {"ok": True, "assistant": {"content": content, "tool_calls": []}, "actions": actions, "warnings": ["direct_fast_path"]}

    # 报价/价格类：直出（秒回），避免 2 次 LLM 调用导致变慢
    if re.search(r"(报价|最新价|当前价|bid|ask|点差)", user_input, flags=re.I):
        return _direct_quote_response(user_input)

    # 切周期类：直出（秒回）
    tf2 = _parse_timeframe(user_input)
    if tf2 and re.search(r"(切|切到|切换|改成|周期|min|分钟|m\d+|h\d+|d1)", user_input, flags=re.I):
        return {
            "ok": True,
            "assistant": {"content": f"已切换周期到 {tf2}。", "tool_calls": []},
            "actions": [{"type": "chart_set_timeframe", "timeframe": tf2}],
            "warnings": ["direct_fast_path"],
        }

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": ai_system_prompt()},
        {"role": "user", "content": "\n".join([*ctx_lines, "", f"用户指令：{user_input}"]).strip()},
    ]

    def _is_query_tool(name: str) -> bool:
        return name in ("market_get_quote", "account_get_info", "account_list_positions", "account_list_orders")

    def _execute_query_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行“查询类 tool”，把结果返回给模型（二次推理用）。
        """
        if name == "market_get_quote":
            symbol = str(args.get("symbol") or "").strip() or sym
            if not symbol:
                return {"ok": False, "error": "symbol is required (no current chart symbol)"}
            if not MT5_AVAILABLE:
                # fallback：用最新 bar close 近似
                try:
                    data = historical_service.get_history(symbol, tf or "M1", before_time=0, limit=1)
                    if not data:
                        return {"ok": False, "error": "no data for symbol"}
                    last = float(data[-1]["close"])
                    return {"ok": True, "symbol": symbol, "bid": None, "ask": None, "last": last, "spread": None, "time": int(data[-1]["time"]), "source": "history_close"}
                except Exception as e:
                    return {"ok": False, "error": f"quote fallback failed: {e}"}

            # MT5 实时 tick
            try:
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    return {"ok": False, "error": f"symbol_info_tick returned None for {symbol}"}
                bid = float(getattr(tick, "bid", 0.0) or 0.0)
                ask = float(getattr(tick, "ask", 0.0) or 0.0)
                last = float(getattr(tick, "last", 0.0) or 0.0) or (bid if bid else 0.0)
                spread = (ask - bid) if (ask and bid) else None
                t = int(getattr(tick, "time", 0) or 0)
                return {"ok": True, "symbol": symbol, "bid": bid, "ask": ask, "last": last, "spread": spread, "time": t, "source": "mt5_tick"}
            except Exception as e:
                return {"ok": False, "error": f"mt5 quote failed: {e}"}

        if not MT5_AVAILABLE:
            return {"ok": False, "error": "MT5 is not available"}

        if name == "account_get_info":
            try:
                info = mt5.account_info()
                if info is None:
                    return {"ok": False, "error": "account_info returned None"}
                d = info._asdict() if hasattr(info, "_asdict") else dict(info)
                # 限制字段（避免太大）
                out = {k: d.get(k) for k in ["login", "name", "server", "currency", "balance", "equity", "margin", "margin_free", "margin_level", "profit"]}
                return {"ok": True, "account": out}
            except Exception as e:
                return {"ok": False, "error": f"account_info failed: {e}"}

        if name == "account_list_positions":
            symbol = str(args.get("symbol") or "").strip()
            try:
                poss = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
                if poss is None:
                    poss = []
                items = []
                for p in poss:
                    d = p._asdict() if hasattr(p, "_asdict") else dict(p)
                    items.append(
                        {
                            "ticket": d.get("ticket"),
                            "symbol": d.get("symbol"),
                            "type": d.get("type"),
                            "volume": d.get("volume"),
                            "price_open": d.get("price_open"),
                            "sl": d.get("sl"),
                            "tp": d.get("tp"),
                            "profit": d.get("profit"),
                        }
                    )
                return {"ok": True, "symbol": symbol or None, "positions": items, "count": len(items)}
            except Exception as e:
                return {"ok": False, "error": f"positions_get failed: {e}"}

        if name == "account_list_orders":
            symbol = str(args.get("symbol") or "").strip()
            try:
                ods = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
                if ods is None:
                    ods = []
                items = []
                for o in ods:
                    d = o._asdict() if hasattr(o, "_asdict") else dict(o)
                    items.append(
                        {
                            "ticket": d.get("ticket"),
                            "symbol": d.get("symbol"),
                            "type": d.get("type"),
                            "volume_initial": d.get("volume_initial"),
                            "price_open": d.get("price_open"),
                            "sl": d.get("sl"),
                            "tp": d.get("tp"),
                        }
                    )
                return {"ok": True, "symbol": symbol or None, "orders": items, "count": len(items)}
            except Exception as e:
                return {"ok": False, "error": f"orders_get failed: {e}"}

        return {"ok": False, "error": f"unknown query tool: {name}"}

    # 常规：单轮 LLM（避免“变慢”）
    try:
        raw = await asyncio.to_thread(
            chat_completions,
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=ai_tool_schemas(),
            tool_choice="auto",
            temperature=0.2,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")

    choice = ((raw.get("choices") or [{}])[0]) if isinstance(raw, dict) else {}
    msg = (choice.get("message") or {}) if isinstance(choice, dict) else {}
    tool_calls = msg.get("tool_calls") or []
    content = str(msg.get("content") or "")

    actions, warnings = ai_parse_tool_calls(tool_calls)
    if not content and actions:
        content = f"已解析 {len(actions)} 个图表动作并准备执行。"

    return {"ok": True, "assistant": {"content": content, "tool_calls": tool_calls}, "actions": actions, "warnings": warnings}


@router.post("/ai/chat/stream")
async def ai_chat_stream(payload: Dict[str, Any] = Body(default={})):
    """
    SSE 流式 Chat：
    - event: meta  {"phase": "...", "message": "..."}
    - event: delta {"content": "..."}  # 增量文本
    - event: final {"assistant": {...}, "actions": [...], "warnings": [...]}

    说明：为了保证“查询类工具”（报价/账户/持仓）可用，这里采用：
    - 若用户意图命中查询类关键词：先做一轮非流式拿 tool_calls → 执行查询 tool → 第二轮流式输出最终回答。
    - 否则：直接流式输出（默认不会调用查询类 tool）。
    """

    user_input = str(payload.get("input") or "").strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="input is required")

    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise HTTPException(status_code=400, detail="missing settings: base_url/api_key/model")

    chart_state = payload.get("chart_state") if isinstance(payload.get("chart_state"), dict) else {}
    sym = str(chart_state.get("symbol") or "")
    tf = str(chart_state.get("timeframe") or "")
    enabled = chart_state.get("enabled") if isinstance(chart_state.get("enabled"), dict) else {}

    ctx_lines = []
    if sym or tf:
        ctx_lines.append(f"当前图表：{sym} {tf}".strip())
    if enabled:
        ctx_lines.append(
            "当前指标开关："
            + ", ".join(
                [
                    f"svp={'on' if enabled.get('svp') else 'off'}",
                    f"vrvp={'on' if enabled.get('vrvp') else 'off'}",
                    f"bubble={'on' if enabled.get('bubble') else 'off'}",
                ]
            )
        )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": ai_system_prompt()},
        {"role": "user", "content": "\n".join([*ctx_lines, "", f"用户指令：{user_input}"]).strip()},
    ]

    def sse(event: str, data: Dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _is_query_intent(text: str) -> bool:
        # 简单启发式：这些关键词才允许/需要调用查询类工具
        return bool(re.search(r"(最新价|当前价|报价|点差|bid|ask|持仓|仓位|挂单|订单|账户|权益|保证金|余额)", text, flags=re.I))

    def _is_query_tool(name: str) -> bool:
        return name in ("market_get_quote", "account_get_info", "account_list_positions", "account_list_orders")

    def _execute_query_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        # 与 ai_chat 内同名逻辑保持一致（这里做一个轻量复制，避免导入循环）
        if name == "market_get_quote":
            symbol = str(args.get("symbol") or "").strip() or sym
            if not symbol:
                return {"ok": False, "error": "symbol is required (no current chart symbol)"}
            if not MT5_AVAILABLE:
                try:
                    data = historical_service.get_history(symbol, tf or "M1", before_time=0, limit=1)
                    if not data:
                        return {"ok": False, "error": "no data for symbol"}
                    last = float(data[-1]["close"])
                    return {"ok": True, "symbol": symbol, "bid": None, "ask": None, "last": last, "spread": None, "time": int(data[-1]["time"]), "source": "history_close"}
                except Exception as e:
                    return {"ok": False, "error": f"quote fallback failed: {e}"}
            try:
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    return {"ok": False, "error": f"symbol_info_tick returned None for {symbol}"}
                bid = float(getattr(tick, "bid", 0.0) or 0.0)
                ask = float(getattr(tick, "ask", 0.0) or 0.0)
                last = float(getattr(tick, "last", 0.0) or 0.0) or (bid if bid else 0.0)
                spread = (ask - bid) if (ask and bid) else None
                t = int(getattr(tick, "time", 0) or 0)
                return {"ok": True, "symbol": symbol, "bid": bid, "ask": ask, "last": last, "spread": spread, "time": t, "source": "mt5_tick"}
            except Exception as e:
                return {"ok": False, "error": f"mt5 quote failed: {e}"}

        if not MT5_AVAILABLE:
            return {"ok": False, "error": "MT5 is not available"}

        if name == "account_get_info":
            try:
                info = mt5.account_info()
                if info is None:
                    return {"ok": False, "error": "account_info returned None"}
                d = info._asdict() if hasattr(info, "_asdict") else dict(info)
                out = {k: d.get(k) for k in ["login", "name", "server", "currency", "balance", "equity", "margin", "margin_free", "margin_level", "profit"]}
                return {"ok": True, "account": out}
            except Exception as e:
                return {"ok": False, "error": f"account_info failed: {e}"}

        if name == "account_list_positions":
            symbol = str(args.get("symbol") or "").strip()
            try:
                poss = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
                if poss is None:
                    poss = []
                items = []
                for p in poss:
                    d = p._asdict() if hasattr(p, "_asdict") else dict(p)
                    items.append(
                        {
                            "ticket": d.get("ticket"),
                            "symbol": d.get("symbol"),
                            "type": d.get("type"),
                            "volume": d.get("volume"),
                            "price_open": d.get("price_open"),
                            "sl": d.get("sl"),
                            "tp": d.get("tp"),
                            "profit": d.get("profit"),
                        }
                    )
                return {"ok": True, "symbol": symbol or None, "positions": items, "count": len(items)}
            except Exception as e:
                return {"ok": False, "error": f"positions_get failed: {e}"}

        if name == "account_list_orders":
            symbol = str(args.get("symbol") or "").strip()
            try:
                ods = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
                if ods is None:
                    ods = []
                items = []
                for o in ods:
                    d = o._asdict() if hasattr(o, "_asdict") else dict(o)
                    items.append(
                        {
                            "ticket": d.get("ticket"),
                            "symbol": d.get("symbol"),
                            "type": d.get("type"),
                            "volume_initial": d.get("volume_initial"),
                            "price_open": d.get("price_open"),
                            "sl": d.get("sl"),
                            "tp": d.get("tp"),
                        }
                    )
                return {"ok": True, "symbol": symbol or None, "orders": items, "count": len(items)}
            except Exception as e:
                return {"ok": False, "error": f"orders_get failed: {e}"}

        return {"ok": False, "error": f"unknown query tool: {name}"}

    def _assemble_tool_calls_from_stream(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将流式 delta 的 tool_calls 片段拼装成 OpenAI tool_calls 结构。
        """
        acc: Dict[int, Dict[str, Any]] = {}
        for ch in chunks:
            try:
                choice = ((ch.get("choices") or [{}])[0]) if isinstance(ch, dict) else {}
                delta = (choice.get("delta") or {}) if isinstance(choice, dict) else {}
                tcs = delta.get("tool_calls") or []
                if not isinstance(tcs, list):
                    continue
                for t in tcs:
                    idx = int(t.get("index") or 0)
                    cur = acc.get(idx) or {"id": t.get("id"), "type": t.get("type") or "function", "function": {"name": "", "arguments": ""}}
                    if t.get("id"):
                        cur["id"] = t.get("id")
                    fn = t.get("function") or {}
                    if fn.get("name"):
                        cur["function"]["name"] = fn.get("name")
                    if fn.get("arguments"):
                        cur["function"]["arguments"] = str(cur["function"].get("arguments") or "") + str(fn.get("arguments") or "")
                    acc[idx] = cur
            except Exception:
                continue
        return [acc[k] for k in sorted(acc.keys())]

    def generator():
        try:
            # 1) 阶段提示：思考
            yield sse("meta", {"phase": "thinking", "message": "思考中…"})

            # 2) 若是“查询意图”，先做一轮非流式拿查询 tool_calls 并执行
            if _is_query_intent(user_input):
                yield sse("meta", {"phase": "query", "message": "正在获取数据…"})
                try:
                    raw0 = chat_completions(
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        messages=messages,
                        tools=ai_tool_schemas(),
                        tool_choice="auto",
                        temperature=0.2,
                        timeout_sec=60,
                    )
                except Exception as e:
                    yield sse("meta", {"phase": "error", "message": "获取数据失败"})
                    yield sse(
                        "final",
                        {
                            "assistant": {"content": "请求失败：无法连接到模型服务或鉴权失败（请检查 AI Settings）。", "tool_calls": []},
                            "actions": [],
                            "warnings": ["query_phase_failed"],
                            "error": str(e),
                        },
                    )
                    return

                choice0 = ((raw0.get("choices") or [{}])[0]) if isinstance(raw0, dict) else {}
                msg0 = (choice0.get("message") or {}) if isinstance(choice0, dict) else {}
                tool_calls0 = msg0.get("tool_calls") or []
                content0 = str(msg0.get("content") or "")
                has_query = False
                for tc in tool_calls0:
                    fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                    if _is_query_tool(str(fn.get("name") or "")):
                        has_query = True
                        break
                if has_query:
                    messages.append({"role": "assistant", "content": content0 or "", "tool_calls": tool_calls0})
                    for tc in tool_calls0:
                        tc_id = str(tc.get("id") or "")
                        fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                        name = str(fn.get("name") or "")
                        args_raw = fn.get("arguments") or "{}"
                        args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw if isinstance(args_raw, dict) else {})
                        if _is_query_tool(name):
                            result = _execute_query_tool(name, args)
                            messages.append({"role": "tool", "tool_call_id": tc_id, "content": json.dumps(result, ensure_ascii=False)})
                yield sse("meta", {"phase": "thinking", "message": "组织回答中…"})

            # 3) 第二步：流式输出最终回答（delta）
            content_acc = ""
            stream_chunks: List[Dict[str, Any]] = []
            phase_tools_sent = False

            try:
                for ch in chat_completions_stream(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    tools=ai_tool_schemas(),
                    tool_choice="auto",
                    temperature=0.2,
                    timeout_sec=120,
                ):
                    stream_chunks.append(ch)
                    choice = ((ch.get("choices") or [{}])[0]) if isinstance(ch, dict) else {}
                    delta = (choice.get("delta") or {}) if isinstance(choice, dict) else {}
                    # 阶段：调用工具（出现 tool_calls 片段时提示一次）
                    if not phase_tools_sent and isinstance(delta, dict) and delta.get("tool_calls"):
                        phase_tools_sent = True
                        yield sse("meta", {"phase": "tools", "message": "正在调用工具…"})

                    piece = delta.get("content")
                    if piece:
                        content_acc += str(piece)
                        yield sse("delta", {"content": str(piece)})
            except Exception as e:
                # fallback：上游不支持流式时，退回非流式并一次性 final
                try:
                    raw = chat_completions(
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        messages=messages,
                        tools=ai_tool_schemas(),
                        tool_choice="auto",
                        temperature=0.2,
                        timeout_sec=120,
                    )
                    choice = ((raw.get("choices") or [{}])[0]) if isinstance(raw, dict) else {}
                    msg = (choice.get("message") or {}) if isinstance(choice, dict) else {}
                    tool_calls = msg.get("tool_calls") or []
                    content = str(msg.get("content") or "")
                    actions, warnings = ai_parse_tool_calls(tool_calls)
                    yield sse(
                        "final",
                        {
                            "assistant": {"content": content, "tool_calls": tool_calls},
                            "actions": actions,
                            "warnings": warnings,
                            "fallback": True,
                            "error": str(e),
                        },
                    )
                except Exception as e2:
                    yield sse("meta", {"phase": "error", "message": "请求失败"})
                    yield sse(
                        "final",
                        {
                            "assistant": {"content": "请求失败：无法连接到模型服务或鉴权失败（请检查 AI Settings）。", "tool_calls": []},
                            "actions": [],
                            "warnings": ["stream_and_fallback_failed"],
                            "error": f"{e} / {e2}",
                        },
                    )
                return

            tool_calls = _assemble_tool_calls_from_stream(stream_chunks)
            actions, warnings = ai_parse_tool_calls(tool_calls)

            yield sse("meta", {"phase": "final", "message": "完成"})
            yield sse("final", {"assistant": {"content": content_acc, "tool_calls": tool_calls}, "actions": actions, "warnings": warnings})
        except Exception as e:
            yield sse("meta", {"phase": "error", "message": "请求失败"})
            yield sse(
                "final",
                {
                    "assistant": {"content": "请求失败：服务端异常。", "tool_calls": []},
                    "actions": [],
                    "warnings": ["server_exception"],
                    "error": str(e),
                },
            )
            return

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.post("/ai/test")
async def ai_test(payload: Dict[str, Any] = Body(default={})):
    """
    测试 LLM 配置是否可用（不执行任何 tools，只做最小对话）。
    入参：settings {base_url, model, api_key}
    出参：ok + content
    """
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise HTTPException(status_code=400, detail="missing settings: base_url/api_key/model")

    messages = [
        {"role": "system", "content": "你是连接测试助手。只回复一个单词：OK"},
        {"role": "user", "content": "ping"},
    ]
    try:
        raw = await asyncio.to_thread(
            chat_completions,
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=None,
            tool_choice=None,
            temperature=0.0,
            timeout_sec=25,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")

    choice = ((raw.get("choices") or [{}])[0]) if isinstance(raw, dict) else {}
    msg = (choice.get("message") or {}) if isinstance(choice, dict) else {}
    content = str(msg.get("content") or "").strip()
    return {"ok": True, "content": content or "OK"}


@router.post("/ai/explain-selection")
async def ai_explain_selection(payload: Dict[str, Any] = Body(default={})):
    """
    Explain selection：对用户选中的时间区间做数据驱动解释（UTC 自然日/自然时间，不做投资建议）。
    入参：
      - settings {base_url, model, api_key}
      - symbol/timeframe/from_time/to_time
    """
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise HTTPException(status_code=400, detail="missing settings: base_url/api_key/model")

    symbol = str(payload.get("symbol") or "")
    timeframe = str(payload.get("timeframe") or "")
    from_time = int(payload.get("from_time") or 0)
    to_time = int(payload.get("to_time") or 0)
    if not symbol or not timeframe or from_time <= 0 or to_time <= 0 or from_time >= to_time:
        raise HTTPException(status_code=400, detail="missing/invalid symbol/timeframe/from_time/to_time")

    bars = historical_service.get_history_range(symbol, timeframe, from_time=from_time, to_time=to_time, limit=5000)
    if not bars:
        raise HTTPException(status_code=400, detail="no bars in range")

    # 轻量摘要（少而准）
    try:
        o0 = float(bars[0]["open"])
        c1 = float(bars[-1]["close"])
        hi = max(float(b["high"]) for b in bars)
        lo = min(float(b["low"]) for b in bars)
        ret = (c1 - o0) / o0 if o0 else 0.0
        rng = (hi - lo) / o0 if o0 else 0.0
        n = len(bars)
    except Exception:
        o0, c1, hi, lo, ret, rng, n = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, len(bars)

    # 生成一个 scene（只用选区窗口，作为 VP/Session 等已有指标的摘要来源）
    scene = {}
    try:
        window = [
            {
                "time": int(b["time"]),
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
                "tick_volume": int(b.get("tick_volume") or b.get("volume") or 0),
                "delta_volume": int(b.get("delta_volume") or 0),
            }
            for b in bars[-3000:]
        ]
        scene = scene_engine.build_from_bars(symbol, timeframe, window, fast=True)
    except Exception:
        scene = {}

    vp = (scene.get("volume_profile") or {}) if isinstance(scene, dict) else {}
    ctx = (scene.get("context") or {}) if isinstance(scene, dict) else {}
    vol = (scene.get("volatility") or {}) if isinstance(scene, dict) else {}
    # 控制上下文大小：events 只保留 id 列表
    ev_ids: List[str] = []
    try:
        for e in (vp.get("events") or [])[:30]:
            if isinstance(e, dict) and e.get("id"):
                ev_ids.append(str(e.get("id")))
    except Exception:
        ev_ids = []

    payload_for_llm = {
        "symbol": symbol,
        "timeframe": timeframe,
        "from_time": from_time,
        "to_time": to_time,
        "bars": n,
        "summary": {
            "open": o0,
            "close": c1,
            "high": hi,
            "low": lo,
            "return_pct": ret * 100.0,
            "range_pct": rng * 100.0,
        },
        "volatility": {"atr_14": vol.get("atr_14"), "atr_pct": vol.get("atr_pct")},
        "vp": {k: vp.get(k) for k in ["poc", "vah", "val", "value_area_pct"]},
        "vp_event_ids": ev_ids,
        # context 可能很大，只保留少量关键字段（如果存在）
        "context": {k: ctx.get(k) for k in ["session", "market_state", "trend"] if isinstance(ctx, dict) and k in ctx},
    }

    sys = "\n".join(
        [
            "你是专业且谨慎的交易市场解读助手（只做客观分析，不提供投资建议/保证）。",
            "用户提供的是一个选区时间段的结构化数据摘要（含 OHLC 摘要、波动率、VP 关键位与事件）。",
            "你必须：",
            "1) 先给出趋势/震荡判断（基于数据特征：高低点结构、回撤、波动区间）",
            "2) 给出波动放大的候选解释（可以提 session/开盘时段/新闻，但要明确不确定性）",
            "3) 给出可执行的观察点：关键价位、突破确认、无效条件",
            "输出 Markdown，结构：概览 / 结构判断 / 波动解释（候选） / 关键价位与观察点 / 一句话总结",
            "语言：中文，专业简洁。",
        ]
    )

    messages = [
        {"role": "system", "content": sys},
        {"role": "user", "content": f"请解释以下选区：\n```json\n{json.dumps(payload_for_llm, ensure_ascii=False)}\n```"},
    ]

    def _offline_explain() -> str:
        """
        当 LLM 不可用/超时时，返回一个纯本地的“离线解释”，避免前端直接报错不可用。
        """
        summ = payload_for_llm.get("summary") or {}
        vp0 = payload_for_llm.get("vp") or {}
        atr_pct = (payload_for_llm.get("volatility") or {}).get("atr_pct")
        ret_pct = float(summ.get("return_pct") or 0.0)
        range_pct = float(summ.get("range_pct") or 0.0)
        hi0 = summ.get("high")
        lo0 = summ.get("low")
        poc0 = vp0.get("poc")
        vah0 = vp0.get("vah")
        val0 = vp0.get("val")
        direction = "偏多" if ret_pct > 0.2 else ("偏空" if ret_pct < -0.2 else "偏震荡")
        vol_state = "偏高" if (isinstance(atr_pct, (int, float)) and atr_pct and atr_pct > 0.8) else "正常"

        lines = [
            "## 概览",
            f"- 标的：{symbol} {timeframe}",
            f"- 区间：{from_time} ~ {to_time}（unix秒）",
            f"- K线数量：{n}",
            f"- 区间涨跌：{ret_pct:.2f}%",
            f"- 区间振幅：{range_pct:.2f}%（高低点区间/开盘）",
            f"- 区间高低点：high={hi0} / low={lo0}",
            "",
            "## 结构判断",
            f"- 结构倾向：{direction}（基于区间涨跌与振幅的快速判断）",
            f"- 波动状态：{vol_state}" + (f"（atr_pct={atr_pct}）" if atr_pct is not None else ""),
            "",
            "## 关键价位与观察点",
        ]
        if any(v is not None for v in [poc0, vah0, val0]):
            lines += [
                f"- POC：{poc0}",
                f"- VAH：{vah0}",
                f"- VAL：{val0}",
                "- 观察：价格在 VAH 上方更偏多延续；跌破 VAL 更偏空延续；POC 附近更容易出现来回拉扯。",
            ]
        else:
            lines += ["- VP 关键位：本次离线摘要未能生成（可稍后重试）。"]
        lines += [
            "",
            "## 一句话总结",
            "当前为离线解释（LLM 超时/不可用时生成），可作为快速复盘的结构化要点参考。",
        ]
        return "\n".join(lines)

    try:
        raw = await asyncio.to_thread(
            chat_completions,
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=None,
            tool_choice=None,
            temperature=0.2,
            # 很多部署（反向代理/网关/云函数）会在 60s 左右对请求做超时切断并返回 504。
            # explain-selection 往往比 annotate-selection 更“慢”（输出更长、推理更重），
            # 因此这里将 LLM 超时主动降到 40s，超时则回退离线解释，避免用户看到 504。
            timeout_sec=40,
        )
    except Exception as e:
        # 不再让前端直接报错：返回离线解释兜底
        return {"ok": True, "content": _offline_explain(), "meta": {"bars": n, "fallback": True, "error": str(e)}}

    choice = ((raw.get("choices") or [{}])[0]) if isinstance(raw, dict) else {}
    msg = (choice.get("message") or {}) if isinstance(choice, dict) else {}
    content = str(msg.get("content") or "").strip()
    if not content:
        content = _offline_explain()
        return {"ok": True, "content": content, "meta": {"bars": n, "fallback": True, "error": "empty llm content"}}
    return {"ok": True, "content": content, "meta": {"bars": n, "fallback": False}}


@router.post("/ai/explain-selection-offline")
async def ai_explain_selection_offline(payload: Dict[str, Any] = Body(default={})):
    """
    离线解释（不调用 LLM）：对用户选中的时间区间做数据驱动的“本地复盘摘要”。
    目标：避免 explain-selection 在某些部署环境下被网关/反向代理 504 掐断。
    入参：
      - symbol/timeframe/from_time/to_time（settings 可有可无）
    """
    symbol = str(payload.get("symbol") or "")
    timeframe = str(payload.get("timeframe") or "")
    from_time = int(payload.get("from_time") or 0)
    to_time = int(payload.get("to_time") or 0)
    if not symbol or not timeframe or from_time <= 0 or to_time <= 0 or from_time >= to_time:
        raise HTTPException(status_code=400, detail="missing/invalid symbol/timeframe/from_time/to_time")

    bars = historical_service.get_history_range(symbol, timeframe, from_time=from_time, to_time=to_time, limit=5000)
    if not bars:
        raise HTTPException(status_code=400, detail="no bars in range")

    # 轻量摘要（少而准）
    try:
        o0 = float(bars[0]["open"])
        c1 = float(bars[-1]["close"])
        hi = max(float(b["high"]) for b in bars)
        lo = min(float(b["low"]) for b in bars)
        ret = (c1 - o0) / o0 if o0 else 0.0
        rng = (hi - lo) / o0 if o0 else 0.0
        n = len(bars)
    except Exception:
        o0, c1, hi, lo, ret, rng, n = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, len(bars)

    scene = {}
    try:
        window = [
            {
                "time": int(b["time"]),
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
                "tick_volume": int(b.get("tick_volume") or b.get("volume") or 0),
                "delta_volume": int(b.get("delta_volume") or 0),
            }
            for b in bars[-3000:]
        ]
        scene = scene_engine.build_from_bars(symbol, timeframe, window, fast=True)
    except Exception:
        scene = {}

    vp = (scene.get("volume_profile") or {}) if isinstance(scene, dict) else {}
    vol = (scene.get("volatility") or {}) if isinstance(scene, dict) else {}

    atr_pct = (vol.get("atr_pct") if isinstance(vol, dict) else None)
    ret_pct = ret * 100.0
    range_pct = rng * 100.0
    poc0 = vp.get("poc") if isinstance(vp, dict) else None
    vah0 = vp.get("vah") if isinstance(vp, dict) else None
    val0 = vp.get("val") if isinstance(vp, dict) else None

    direction = "偏多" if ret_pct > 0.2 else ("偏空" if ret_pct < -0.2 else "偏震荡")
    vol_state = "偏高" if (isinstance(atr_pct, (int, float)) and atr_pct and atr_pct > 0.8) else "正常"

    lines = [
        "# 离线解释（快速复盘）",
        "",
        "## 概览",
        f"- 标的：{symbol} {timeframe}",
        f"- 区间：{from_time} ~ {to_time}（unix秒）",
        f"- K线数量：{n}",
        f"- 区间涨跌：{ret_pct:.2f}%",
        f"- 区间振幅：{range_pct:.2f}%（高低点区间/开盘）",
        f"- 区间高低点：high={hi} / low={lo}",
        "",
        "## 结构判断",
        f"- 结构倾向：{direction}（基于区间涨跌与振幅的快速判断）",
        f"- 波动状态：{vol_state}" + (f"（atr_pct={atr_pct}）" if atr_pct is not None else ""),
        "",
        "## 关键价位与观察点",
    ]
    if any(v is not None for v in [poc0, vah0, val0]):
        lines += [
            f"- POC：{poc0}",
            f"- VAH：{vah0}",
            f"- VAL：{val0}",
            "- 观察：价格在 VAH 上方更偏多延续；跌破 VAL 更偏空延续；POC 附近更容易出现来回拉扯。",
        ]
    else:
        lines += ["- VP 关键位：本次未生成（可稍后重试）。"]

    lines += [
        "",
        "## 一句话总结",
        "这是离线版复盘摘要（不调用 AI），用于绕开 explain/复盘卡片在部分环境的 504 超时。",
    ]

    return {"ok": True, "content": "\n".join(lines), "meta": {"bars": n, "offline": True}}


@router.post("/ai/annotate-selection")
async def ai_annotate_selection(payload: Dict[str, Any] = Body(default={})):
    """
    自动标注：让 LLM 生成可复现的绘图指令（chart_draw objects）。
    入参同 explain-selection。
    出参：assistant + actions（包含 chart_draw）
    """
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise HTTPException(status_code=400, detail="missing settings: base_url/api_key/model")

    symbol = str(payload.get("symbol") or "")
    timeframe = str(payload.get("timeframe") or "")
    from_time = int(payload.get("from_time") or 0)
    to_time = int(payload.get("to_time") or 0)
    if not symbol or not timeframe or from_time <= 0 or to_time <= 0 or from_time >= to_time:
        raise HTTPException(status_code=400, detail="missing/invalid symbol/timeframe/from_time/to_time")

    bars = historical_service.get_history_range(symbol, timeframe, from_time=from_time, to_time=to_time, limit=5000)
    if not bars:
        raise HTTPException(status_code=400, detail="no bars in range")

    # 摘要（减少 token）
    hi = max(float(b["high"]) for b in bars)
    lo = min(float(b["low"]) for b in bars)
    c1 = float(bars[-1]["close"])
    o0 = float(bars[0]["open"])
    ret = (c1 - o0) / o0 * 100.0 if o0 else 0.0

    scene = {}
    try:
        window = [
            {
                "time": int(b["time"]),
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
                "tick_volume": int(b.get("tick_volume") or b.get("volume") or 0),
                "delta_volume": int(b.get("delta_volume") or 0),
            }
            for b in bars[-2500:]
        ]
        scene = scene_engine.build_from_bars(symbol, timeframe, window, fast=True)
    except Exception:
        scene = {}
    vp = (scene.get("volume_profile") or {}) if isinstance(scene, dict) else {}
    vol = (scene.get("volatility") or {}) if isinstance(scene, dict) else {}

    ctx_obj = {
        "symbol": symbol,
        "timeframe": timeframe,
        "from_time": from_time,
        "to_time": to_time,
        "bars": len(bars),
        "high": hi,
        "low": lo,
        "return_pct": ret,
        "atr_14": vol.get("atr_14"),
        "vp_poc": vp.get("poc"),
        "vp_vah": vp.get("vah"),
        "vp_val": vp.get("val"),
    }

    sys = "\n".join(
        [
            "你是图表标注助手。你的目标是把这段行情用“少量但有用”的绘图对象标出来，方便复盘。",
            "你必须使用 tools 调用 chart_draw 来输出 objects；不要输出代码。",
            "规则：",
            "- objects 不超过 12 个。",
            "- 优先画：区间高/低（hline）、VP 关键位（poc/vah/val 可选）、关键 break/回撤点（marker 可选）、区间框（box 可选）。",
            "- 时间用 Unix 秒，价格用数值。",
            "输出：先简短一句话说明，然后给 chart_draw。",
        ]
    )

    messages = [
        {"role": "system", "content": sys},
        {"role": "user", "content": f"请对选区自动标注：\n```json\n{json.dumps(ctx_obj, ensure_ascii=False)}\n```"},
    ]

    def _fallback_actions() -> List[Dict[str, Any]]:
        # 纯本地标注兜底：避免上游 LLM 504/超时导致“标注不可用”
        objs: List[Dict[str, Any]] = []
        try:
            objs.append({"type": "box", "from_time": from_time, "to_time": to_time, "low": lo, "high": hi, "color": "#94a3b8", "text": "选区"})
            objs.append({"type": "hline", "price": hi, "color": "#60a5fa", "text": "区间高"})
            objs.append({"type": "hline", "price": lo, "color": "#f87171", "text": "区间低"})
            if isinstance(vp, dict):
                if vp.get("poc") is not None:
                    objs.append({"type": "hline", "price": float(vp.get("poc")), "color": "#a78bfa", "text": "POC"})
                if vp.get("vah") is not None:
                    objs.append({"type": "hline", "price": float(vp.get("vah")), "color": "#34d399", "text": "VAH"})
                if vp.get("val") is not None:
                    objs.append({"type": "hline", "price": float(vp.get("val")), "color": "#fb7185", "text": "VAL"})
        except Exception:
            pass
        return [{"type": "chart_draw", "objects": objs}]

    try:
        raw = await asyncio.to_thread(
            chat_completions,
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=ai_tool_schemas(),
            tool_choice="auto",
            temperature=0.2,
            # 标注在部分网关也可能被 504 掐断；主动缩短等待，失败则走离线标注兜底。
            timeout_sec=40,
        )
    except Exception as e:
        return {
            "ok": True,
            "assistant": {"content": f"标注已使用离线兜底（LLM 不可用/超时：{e}）。", "tool_calls": []},
            "actions": _fallback_actions(),
            "warnings": ["fallback_offline_annotate"],
        }

    choice = ((raw.get("choices") or [{}])[0]) if isinstance(raw, dict) else {}
    msg = (choice.get("message") or {}) if isinstance(choice, dict) else {}
    tool_calls = msg.get("tool_calls") or []
    content = msg.get("content") or ""

    actions, warnings = ai_parse_tool_calls(tool_calls)
    if not content and actions:
        content = f"已生成 {len(actions)} 个标注动作。"

    return {"ok": True, "assistant": {"content": content, "tool_calls": tool_calls}, "actions": actions, "warnings": warnings}


@router.post("/ai/analyze-today")
async def ai_analyze_today(payload: Dict[str, Any] = Body(default={})):
    """
    分析“今天”的走势（按 UTC 自然日；以该 symbol 最新 bar 所在的 UTC day 为“今天”）。
    返回：analysis content + 建议的图表动作（actions）
    """
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise HTTPException(status_code=400, detail="missing settings: base_url/api_key/model")

    symbol = str(payload.get("symbol") or "").strip()
    timeframe = str(payload.get("timeframe") or "").strip() or "M15"
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    latest = historical_service.get_history(symbol, timeframe, before_time=0, limit=2)
    if not latest:
        raise HTTPException(status_code=400, detail="no data for symbol/timeframe")
    latest_t = int(latest[-1]["time"])
    import datetime as dt

    day = dt.datetime.utcfromtimestamp(latest_t).date()
    day0 = int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp())
    day_end = day0 + 86400 - 1
    to_time = min(latest_t, day_end)

    bars = historical_service.get_history_range(symbol, timeframe, from_time=day0, to_time=to_time, limit=5000)
    if not bars:
        raise HTTPException(status_code=400, detail="no bars for today")

    o0 = float(bars[0]["open"])
    c1 = float(bars[-1]["close"])
    hi = max(float(b["high"]) for b in bars)
    lo = min(float(b["low"]) for b in bars)
    ret = (c1 - o0) / o0 * 100.0 if o0 else 0.0
    n = len(bars)

    scene = {}
    try:
        window = [
            {
                "time": int(b["time"]),
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
                "tick_volume": int(b.get("tick_volume") or b.get("volume") or 0),
                "delta_volume": int(b.get("delta_volume") or 0),
            }
            for b in bars[-2500:]
        ]
        scene = scene_engine.build_from_bars(symbol, timeframe, window, fast=True)
    except Exception:
        scene = {}
    vp = (scene.get("volume_profile") or {}) if isinstance(scene, dict) else {}
    vol = (scene.get("volatility") or {}) if isinstance(scene, dict) else {}

    ctx_obj = {
        "symbol": symbol,
        "timeframe": timeframe,
        "day_utc": str(day),
        "bars": n,
        "summary": {"open": o0, "close": c1, "high": hi, "low": lo, "return_pct": ret},
        "volatility": {"atr_14": vol.get("atr_14"), "atr_pct": vol.get("atr_pct")},
        "vp": {k: vp.get(k) for k in ["poc", "vah", "val", "value_area_pct"]},
    }

    sys = "\n".join(
        [
            "你是黄金/外汇的市场复盘助手（只做客观分析，不提供投资建议）。",
            "请基于提供的“今天（UTC 自然日）”结构化摘要，给出：",
            "1) 今日主导结构：趋势/震荡、关键高低点、是否走出区间",
            "2) 波动与流动性：是否放大、可能的 session/开盘影响（明确不确定性）",
            "3) 接下来观察点：关键价位、突破确认、无效条件",
            "输出 Markdown，简洁可执行。",
        ]
    )
    messages = [
        {"role": "system", "content": sys},
        {"role": "user", "content": f"请分析今天走势：\n```json\n{json.dumps(ctx_obj, ensure_ascii=False)}\n```"},
    ]

    try:
        raw = await asyncio.to_thread(
            chat_completions,
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=None,
            tool_choice=None,
            temperature=0.2,
            timeout_sec=120,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")

    choice = ((raw.get("choices") or [{}])[0]) if isinstance(raw, dict) else {}
    msg = (choice.get("message") or {}) if isinstance(choice, dict) else {}
    content = str(msg.get("content") or "").strip()

    actions = [
        {"type": "chart_set_symbol", "symbol": symbol},
        {"type": "chart_set_timeframe", "timeframe": timeframe},
        {"type": "chart_set_range", "days": 1},
        {"type": "chart_draw", "objects": [{"type": "hline", "price": hi, "color": "#60a5fa"}, {"type": "hline", "price": lo, "color": "#f87171"}]},
    ]
    return {"ok": True, "content": content, "actions": actions, "meta": {"day_utc": str(day), "bars": n}}


@router.post("/ai/vision-analyze")
async def ai_vision_analyze(payload: Dict[str, Any] = Body(default={})):
    """
    多模态看图：前端传入 screenshot_data_url（data:image/png;base64,...）+ chart_state。
    LLM 输出：简短结论 + chart_draw（自动落图）。
    """
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise HTTPException(status_code=400, detail="missing settings: base_url/api_key/model")

    screenshot_data_url = str(payload.get("screenshot_data_url") or "").strip()
    if not screenshot_data_url.startswith("data:image"):
        raise HTTPException(status_code=400, detail="screenshot_data_url is required (data:image/...)")

    chart_state = payload.get("chart_state") if isinstance(payload.get("chart_state"), dict) else {}
    selection_range = payload.get("selection_range") if isinstance(payload.get("selection_range"), dict) else None

    sys = "\n".join(
        [
            "你是专业的多模态图表解读助手（只做客观分析，不提供投资建议）。",
            "你会看到一张交易图表截图。你的任务：",
            "1) 用 6-10 句话总结：趋势/震荡、关键结构点、关键位（支撑阻力/突破位）、当前所处位置。",
            "2) 给出“接下来观察点”：突破确认、无效条件。",
            "3) 必须调用工具 chart_draw 输出少量对象（<=12）：hline/box/trendline/marker，用于把你说的关键位画到图上。",
            "规则：不要臆造不存在的数值；如果价格读不清，请用相对描述，并只画少量对象。",
            "输出：先文字，再 tool calls。",
            "语言：中文。",
        ]
    )
    user_text = {
        "chart_state": chart_state,
        "selection_range": selection_range,
    }
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": sys},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"请解读并标注这张图表：\n```json\n{json.dumps(user_text, ensure_ascii=False)}\n```"},
                {"type": "image_url", "image_url": {"url": screenshot_data_url}},
            ],
        },
    ]

    try:
        raw = await asyncio.to_thread(
            chat_completions,
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=ai_tool_schemas(),
            tool_choice="auto",
            temperature=0.2,
            timeout_sec=120,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")

    choice = ((raw.get("choices") or [{}])[0]) if isinstance(raw, dict) else {}
    msg = (choice.get("message") or {}) if isinstance(choice, dict) else {}
    tool_calls = msg.get("tool_calls") or []
    content = str(msg.get("content") or "").strip()
    actions, warnings = ai_parse_tool_calls(tool_calls)
    return {"ok": True, "assistant": {"content": content, "tool_calls": tool_calls}, "actions": actions, "warnings": warnings}


@router.post("/ai/strategy-scan")
async def ai_strategy_scan(payload: Dict[str, Any] = Body(default={})):
    """
    策略 prompt → 编译成简化 DSL → 多品种/多周期扫描 → 返回候选列表（可落图 chart_draw）。
    """
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise HTTPException(status_code=400, detail="missing settings: base_url/api_key/model")

    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    source = str(payload.get("source") or "both")
    timeframes = payload.get("timeframes") if isinstance(payload.get("timeframes"), list) else ["M30"]
    lookback_hours = int(payload.get("lookback_hours") or 24)
    lookback_hours = max(6, min(168, lookback_hours))
    max_candidates = int(payload.get("max_candidates") or 30)
    max_candidates = max(5, min(200, max_candidates))

    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")
    active_syms = list((deps["meta_store"].get_active_symbols() or {}).keys())
    wl = list_watchlist()
    if source == "active":
        symbols = active_syms
    elif source == "watchlist":
        symbols = wl
    else:
        symbols = list(dict.fromkeys(active_syms + wl))

    # 1) compile prompt -> dsl
    compile_sys = "\n".join(
        [
            "你是策略编译器。把用户的策略描述编译成一个非常简单、可执行的 JSON DSL。",
            "你必须只输出 JSON（不要输出解释文字）。",
            "允许字段：",
            "- breakout: {lookback_bars:int, direction:'up'|'down'|'both'}",
            "- atr_expansion: {ratio:float, window_bars:int}  # 近 window vs 前 window 的 TR 均值比",
            "- volume_spike: {ratio:float, window_bars:int}  # 最新 bar volume vs 近 window 平均量",
            "- session_filter: {sessions:['asia'|'london'|'ny'], timezone:'UTC'}  # 仅在指定 session 触发",
            "- vp_reaccept: {direction:'from_above'|'from_below'|'both', lookback_bars:int}  # 从 VA 外回到 VA 内（简化）",
            "- structure: {pattern:'HH_HL'|'LH_LL'|'range', pivot:int, lookback_bars:int}  # 结构点识别（简化）",
            "- retest_reclaim: {level:'struct_high'|'struct_low', retest_window_bars:int, reclaim_window_bars:int}  # breakout→回踩→收复确认（简化）",
            "- risk: {hold_bars:int, atr_stop_mult:float, atr_tp_mult:float}  # 风控模板（用于画无效/目标线与回测参数）",
            "输出格式示例：",
            "{",
            "  \"name\": \"...\",",
            "  \"conditions\": {",
            "     \"breakout\": {\"lookback_bars\": 60, \"direction\": \"both\"},",
            "     \"atr_expansion\": {\"ratio\": 1.25, \"window_bars\": 40},",
            "     \"volume_spike\": {\"ratio\": 1.5, \"window_bars\": 40}",
            "     \"session_filter\": {\"sessions\": [\"london\"], \"timezone\": \"UTC\"},",
            "     \"vp_reaccept\": {\"direction\": \"both\", \"lookback_bars\": 200},",
            "     \"structure\": {\"pattern\": \"HH_HL\", \"pivot\": 2, \"lookback_bars\": 300}",
            "     \"retest_reclaim\": {\"level\": \"struct_high\", \"retest_window_bars\": 16, \"reclaim_window_bars\": 8},",
            "     \"risk\": {\"hold_bars\": 0, \"atr_stop_mult\": 2.0, \"atr_tp_mult\": 3.0}",
            "  },",
            "  \"score_weights\": {\"breakout\": 1.0, \"atr_expansion\": 0.8, \"volume_spike\": 0.8}",
            "}",
            "如果用户没提某个条件，可以省略该字段。",
        ]
    )
    messages = [
        {"role": "system", "content": compile_sys},
        {"role": "user", "content": prompt},
    ]
    try:
        raw = await asyncio.to_thread(
            chat_completions,
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=None,
            tool_choice=None,
            temperature=0.0,
            timeout_sec=60,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm compile failed: {e}")

    choice = ((raw.get("choices") or [{}])[0]) if isinstance(raw, dict) else {}
    msg = (choice.get("message") or {}) if isinstance(choice, dict) else {}
    dsl_text = str(msg.get("content") or "").strip()
    dsl = _extract_json_from_text(dsl_text)
    if not dsl:
        # fallback: minimal dsl
        dsl = {
            "name": "fallback",
            "conditions": {"breakout": {"lookback_bars": 60, "direction": "both"}, "atr_expansion": {"ratio": 1.25, "window_bars": 40}},
            "score_weights": {"breakout": 1.0, "atr_expansion": 0.8},
        }

    cond = dsl.get("conditions") if isinstance(dsl.get("conditions"), dict) else {}
    w = dsl.get("score_weights") if isinstance(dsl.get("score_weights"), dict) else {}

    def _w(k: str, default: float) -> float:
        try:
            return float(w.get(k, default))
        except Exception:
            return default

    def _session_of_utc(ts: int) -> str:
        import datetime as dt

        h = dt.datetime.utcfromtimestamp(int(ts)).hour
        # 简化版（UTC）
        if 0 <= h < 8:
            return "asia"
        if 8 <= h < 16:
            return "london"
        if 13 <= h < 21:
            return "ny"
        return "off"

    def _pivot_swings(highs: List[float], lows: List[float], times: List[int], pivot: int) -> Dict[str, Any]:
        """
        简化结构点：fractal pivot
        return: {highs:[(t,price)], lows:[(t,price)]} 升序
        """
        p = max(1, min(6, int(pivot)))
        sh = []
        sl = []
        n = len(highs)
        for i in range(p, n - p):
            h0 = highs[i]
            l0 = lows[i]
            if all(h0 > highs[i - k] for k in range(1, p + 1)) and all(h0 >= highs[i + k] for k in range(1, p + 1)):
                sh.append((times[i], h0))
            if all(l0 < lows[i - k] for k in range(1, p + 1)) and all(l0 <= lows[i + k] for k in range(1, p + 1)):
                sl.append((times[i], l0))
        return {"highs": sh, "lows": sl}

    def _try_get_atr14(sym: str, tf: str, window: List[Dict[str, Any]]) -> float:
        try:
            win2 = [
                {
                    "time": int(b["time"]),
                    "open": float(b["open"]),
                    "high": float(b["high"]),
                    "low": float(b["low"]),
                    "close": float(b["close"]),
                    "tick_volume": int(b.get("tick_volume") or b.get("volume") or 0),
                    "delta_volume": int(b.get("delta_volume") or 0),
                }
                for b in window[-600:]
            ]
            scene = scene_engine.build_from_bars(sym, tf, win2, fast=True)
            atr = float(((scene.get("volatility") or {}).get("atr_14") or 0.0))
            return atr if atr > 0 else 0.0
        except Exception:
            return 0.0

    # 2) scan
    results: List[Dict[str, Any]] = []
    total = max(1, len(symbols) * max(1, len(timeframes)))
    processed = 0
    for sym in symbols:
        for tf in timeframes:
            processed += 1
            try:
                last = historical_service.get_history(sym, tf, before_time=0, limit=1)
                if not last:
                    continue
                latest_t = int(last[-1]["time"])
                frm = latest_t - lookback_hours * 3600
                bars = historical_service.get_history_range(sym, tf, from_time=frm, to_time=latest_t, limit=6000)
                if len(bars) < 120:
                    continue
                closes = [float(b["close"]) for b in bars]
                highs = [float(b["high"]) for b in bars]
                lows = [float(b["low"]) for b in bars]
                vols = [float(b.get("tick_volume") or b.get("volume") or 0.0) for b in bars]
                times = [int(b["time"]) for b in bars]

                score = 0.0
                reasons = []
                draw_objects: List[Dict[str, Any]] = []
                direction_hint: str | None = None

                # risk params（用于画 SL/TP + 回测参数）
                risk = cond.get("risk") if isinstance(cond.get("risk"), dict) else {}
                hold_bars = int(risk.get("hold_bars") or 0) if risk else 0
                atr_stop_mult = float(risk.get("atr_stop_mult") or 2.0) if risk else 2.0
                atr_tp_mult = float(risk.get("atr_tp_mult") or 3.0) if risk else 3.0

                # session filter（基于触发时刻，即 latest_t）
                sf = cond.get("session_filter") if isinstance(cond.get("session_filter"), dict) else None
                if sf:
                    sess = sf.get("sessions") if isinstance(sf.get("sessions"), list) else []
                    sess = [str(x) for x in sess if str(x)]
                    if sess:
                        s_now = _session_of_utc(latest_t)
                        if s_now not in set(sess):
                            continue

                # breakout
                bo = cond.get("breakout") if isinstance(cond.get("breakout"), dict) else None
                if bo:
                    lb = int(bo.get("lookback_bars") or 60)
                    lb = max(20, min(500, lb))
                    direction = str(bo.get("direction") or "both")
                    if len(bars) > lb + 2:
                        prior_high = max(highs[-lb - 1 : -1])
                        prior_low = min(lows[-lb - 1 : -1])
                        last_close = closes[-1]
                        up = last_close > prior_high
                        down = last_close < prior_low
                        ok = (direction == "both" and (up or down)) or (direction == "up" and up) or (direction == "down" and down)
                        if ok:
                            score += _w("breakout", 1.0)
                            reasons.append(f"突破：close={last_close:.3f} vs 过去{lb}根区间 [{prior_low:.3f},{prior_high:.3f}]")
                            direction_hint = "LONG" if up else "SHORT"
                            draw_objects += [
                                {"type": "hline", "price": prior_high, "color": "#60a5fa"},
                                {"type": "hline", "price": prior_low, "color": "#f87171"},
                                {"type": "marker", "time": latest_t, "position": "aboveBar" if up else "belowBar", "color": "#fbbf24", "text": "break"},
                            ]

                # atr expansion
                ae = cond.get("atr_expansion") if isinstance(cond.get("atr_expansion"), dict) else None
                if ae:
                    ratio = float(ae.get("ratio") or 1.25)
                    win = int(ae.get("window_bars") or 40)
                    win = max(20, min(200, win))
                    trs = []
                    for i in range(1, len(bars)):
                        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
                        trs.append(tr)
                    if len(trs) >= win * 2 + 5:
                        recent = sum(trs[-win:]) / win
                        prev = sum(trs[-2 * win : -win]) / win
                        if prev > 0 and recent / prev >= ratio:
                            score += _w("atr_expansion", 0.8)
                            reasons.append(f"波动放大：TR均值比={recent/prev:.2f}（阈值 {ratio}）")

                # volume spike
                vs = cond.get("volume_spike") if isinstance(cond.get("volume_spike"), dict) else None
                if vs:
                    ratio = float(vs.get("ratio") or 1.5)
                    win = int(vs.get("window_bars") or 40)
                    win = max(20, min(200, win))
                    if len(vols) >= win + 2:
                        avg = sum(vols[-win - 1 : -1]) / win
                        lastv = vols[-1]
                        if avg > 0 and lastv / avg >= ratio:
                            score += _w("volume_spike", 0.8)
                            reasons.append(f"量能放大：vol比={lastv/avg:.2f}（阈值 {ratio}）")

                # VP re-accept（简化：上一根在 VA 外，最新收盘回到 VA 内）
                vr = cond.get("vp_reaccept") if isinstance(cond.get("vp_reaccept"), dict) else None
                if vr:
                    lb = int(vr.get("lookback_bars") or 200)
                    lb = max(120, min(2500, lb))
                    direction = str(vr.get("direction") or "both")
                    window = bars[-lb:] if len(bars) >= lb else bars
                    try:
                        win2 = [
                            {
                                "time": int(b["time"]),
                                "open": float(b["open"]),
                                "high": float(b["high"]),
                                "low": float(b["low"]),
                                "close": float(b["close"]),
                                "tick_volume": int(b.get("tick_volume") or b.get("volume") or 0),
                                "delta_volume": int(b.get("delta_volume") or 0),
                            }
                            for b in window
                        ]
                        scene = scene_engine.build_from_bars(sym, tf, win2, fast=True)
                        vp = (scene.get("volume_profile") or {}) if isinstance(scene, dict) else {}
                        vah = float(vp.get("vah") or 0.0)
                        val = float(vp.get("val") or 0.0)
                        poc = float(vp.get("poc") or 0.0)
                        if vah and val and vah > val and len(closes) >= 2:
                            prev_c = closes[-2]
                            last_c = closes[-1]
                            in_va = (val <= last_c <= vah)
                            from_above = prev_c > vah and in_va
                            from_below = prev_c < val and in_va
                            ok = (direction == "both" and (from_above or from_below)) or (direction == "from_above" and from_above) or (direction == "from_below" and from_below)
                            if ok:
                                score += _w("vp_reaccept", 0.9)
                                reasons.append("VP re-accept：收盘从 VA 外回到 VA 内（简化判定）")
                                draw_objects += [
                                    {"type": "hline", "price": vah, "color": "#22c55e"},
                                    {"type": "hline", "price": val, "color": "#ef4444"},
                                    {"type": "hline", "price": poc, "color": "#a855f7"},
                                    {"type": "marker", "time": latest_t, "position": "aboveBar", "color": "#a855f7", "text": "re-accept"},
                                ]
                    except Exception:
                        pass

                # 结构点（HH/HL/LH/LL / range）
                st = cond.get("structure") if isinstance(cond.get("structure"), dict) else None
                swings_last = None
                if st:
                    pattern = str(st.get("pattern") or "range")
                    pivot = int(st.get("pivot") or 2)
                    lb = int(st.get("lookback_bars") or 300)
                    lb = max(120, min(3000, lb))
                    hh = highs[-lb:] if len(highs) >= lb else highs
                    ll = lows[-lb:] if len(lows) >= lb else lows
                    tt = times[-lb:] if len(times) >= lb else times
                    swings = _pivot_swings(hh, ll, tt, pivot)
                    swings_last = swings
                    sh = swings["highs"]
                    sl = swings["lows"]
                    ok = False
                    if len(sh) >= 2 and len(sl) >= 2:
                        h1, h2 = sh[-2], sh[-1]
                        l1, l2 = sl[-2], sl[-1]
                        is_hh = h2[1] > h1[1]
                        is_hl = l2[1] > l1[1]
                        is_lh = h2[1] < h1[1]
                        is_ll = l2[1] < l1[1]
                        if pattern == "HH_HL":
                            ok = is_hh and is_hl
                        elif pattern == "LH_LL":
                            ok = is_lh and is_ll
                        elif pattern == "range":
                            # 简化：高点不创新高且低点不创新低
                            ok = (not is_hh) and (not is_ll)
                    if ok:
                        score += _w("structure", 1.0)
                        reasons.append(f"结构满足：{pattern}（pivot={pivot}）")
                        # 画最近几个结构点
                        for (t0, p0) in (sh[-3:] if len(sh) >= 3 else sh):
                            draw_objects.append({"type": "marker", "time": int(t0), "position": "aboveBar", "color": "#60a5fa", "text": "SH"})
                            draw_objects.append({"type": "hline", "price": float(p0), "color": "#60a5fa"})
                        for (t0, p0) in (sl[-3:] if len(sl) >= 3 else sl):
                            draw_objects.append({"type": "marker", "time": int(t0), "position": "belowBar", "color": "#f87171", "text": "SL"})
                            draw_objects.append({"type": "hline", "price": float(p0), "color": "#f87171"})

                # retest/reclaim（简化：对最近结构高/低做 breakout→回踩→收复）
                rr = cond.get("retest_reclaim") if isinstance(cond.get("retest_reclaim"), dict) else None
                if rr:
                    level = str(rr.get("level") or "struct_high")
                    retest_w = max(4, min(80, int(rr.get("retest_window_bars") or 16)))
                    reclaim_w = max(2, min(40, int(rr.get("reclaim_window_bars") or 8)))

                    # 需要结构点
                    if not swings_last:
                        swings_last = _pivot_swings(highs[-600:], lows[-600:], times[-600:], 2)
                    sh = swings_last.get("highs") or []
                    sl = swings_last.get("lows") or []
                    struct_high = float(sh[-1][1]) if sh else None
                    struct_low = float(sl[-1][1]) if sl else None
                    target = struct_high if level == "struct_high" else struct_low

                    if target is not None and len(closes) > retest_w + reclaim_w + 5:
                        last_close = closes[-1]
                        prev_close = closes[-2]
                        recent_lows = lows[-retest_w - reclaim_w : -reclaim_w]
                        recent_highs = highs[-retest_w - reclaim_w : -reclaim_w]
                        reclaim_closes = closes[-reclaim_w:]

                        if level == "struct_high":
                            breakout = prev_close <= target and last_close > target
                            retested = min(recent_lows) <= target
                            reclaimed = max(reclaim_closes) > target
                            ok = breakout and retested and reclaimed
                            if ok:
                                score += _w("retest_reclaim", 1.2)
                                reasons.append(f"retest→reclaim：上破结构高 {target:.3f}，回踩并收复确认")
                                direction_hint = direction_hint or "LONG"
                                draw_objects += [
                                    {"type": "hline", "price": target, "color": "#22c55e"},
                                    {"type": "marker", "time": latest_t, "position": "aboveBar", "color": "#22c55e", "text": "reclaim"},
                                ]
                        else:
                            breakout = prev_close >= target and last_close < target
                            retested = max(recent_highs) >= target
                            reclaimed = min(reclaim_closes) < target
                            ok = breakout and retested and reclaimed
                            if ok:
                                score += _w("retest_reclaim", 1.2)
                                reasons.append(f"retest→reclaim：下破结构低 {target:.3f}，回抽并压回确认")
                                direction_hint = direction_hint or "SHORT"
                                draw_objects += [
                                    {"type": "hline", "price": target, "color": "#ef4444"},
                                    {"type": "marker", "time": latest_t, "position": "belowBar", "color": "#ef4444", "text": "reclaim"},
                                ]

                if score > 0:
                    # entry/SL/TP（基于 ATR14，若缺失则用最近 TR 均值）
                    entry = closes[-1]
                    atr = _try_get_atr14(sym, tf, bars) or 0.0
                    if atr <= 0:
                        trs = []
                        for i in range(1, len(bars)):
                            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
                            trs.append(tr)
                        atr = (sum(trs[-14:]) / 14.0) if len(trs) >= 14 else (highs[-1] - lows[-1])
                    atr = max(1e-6, float(atr))
                    dirn = direction_hint or "LONG"
                    stop = entry - atr_stop_mult * atr if dirn == "LONG" else entry + atr_stop_mult * atr
                    tp = entry + atr_tp_mult * atr if dirn == "LONG" else entry - atr_tp_mult * atr
                    draw_objects += [
                        {"type": "marker", "time": latest_t, "position": "aboveBar" if dirn == "LONG" else "belowBar", "color": "#eab308", "text": "entry"},
                        {"type": "hline", "price": stop, "color": "#ef4444"},
                        {"type": "hline", "price": tp, "color": "#22c55e"},
                    ]

                    results.append(
                        {
                            "symbol": sym,
                            "timeframe": tf,
                            "trigger_time": latest_t,
                            "score": score,
                            "reason": "\n".join(reasons),
                            "draw_objects": draw_objects[:12],
                            "direction_hint": direction_hint,
                            "risk": {"hold_bars": hold_bars, "atr_stop_mult": atr_stop_mult, "atr_tp_mult": atr_tp_mult},
                            # 回测引擎参数（用于 reclaim_continuation 类策略）
                            "engine_params": {
                                "retest_window_bars": int(rr.get("retest_window_bars") or 16) if rr else None,
                                "reclaim_window_bars": int(rr.get("reclaim_window_bars") or 8) if rr else None,
                            },
                        }
                    )
            except Exception:
                continue

    results.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return {"ok": True, "dsl": dsl, "items": results[:max_candidates], "meta": {"symbols": len(symbols), "timeframes": timeframes}}


@router.post("/strategy/parse")
async def api_strategy_parse(payload: Dict[str, Any] = Body(default={})):
    """
    自然语言策略解析（复杂策略解析协议 v1.0）。
    MVP：仅保证 breakout 的确定性解析（不走 LLM）。

    payload:
      - prompt: str
      - source: active|watchlist|both  # 用于填充 universe.symbols
      - timeframes: ["M15","H1"]       # 用于填充 spec.timeframes
      - lookback_hours: int            # 运行期参数（不写入 spec）
    """
    prompt = str(payload.get("prompt") or "").strip()
    source = str(payload.get("source") or "both")
    timeframes = payload.get("timeframes") if isinstance(payload.get("timeframes"), list) else ["M15"]
    lookback_hours = int(payload.get("lookback_hours") or 24)
    lookback_hours = max(6, min(168, lookback_hours))

    deps = get_current_broker_deps()
    active_syms = list((deps["meta_store"].get_active_symbols() or {}).keys()) if deps else []
    wl = list_watchlist()
    if source == "active":
        symbols = active_syms
    elif source == "watchlist":
        symbols = wl
    else:
        symbols = list(dict.fromkeys(active_syms + wl))
    # 防止 universe 过大导致后续扫描太慢
    symbols = symbols[:200]

    if not symbols:
        # 允许解析继续进行，但提示用户配置 broker 或 watchlist
        out = parse_breakout_prompt_to_protocol(
            prompt=prompt,
            symbols=[],
            timeframes=[str(x).upper() for x in timeframes],
            lookback_bars=2000,
            n_breakout=48,
            top_n=20,
        )
        out["parse_meta"]["status"] = "needs_clarification"
        out["parse_meta"]["open_questions"] = [
            {
                "id": "Q_symbols",
                "question": "未找到可扫描的 symbols（请先配置 active broker 或在 Watchlist 添加品种）。要继续吗？",
                "options": [],
                "default": None,
                "required": True,
            }
        ]
        return {"ok": True, **out, "runtime": {"source": source, "timeframes": timeframes, "lookback_hours": lookback_hours, "symbols_count": 0}}

    out = parse_breakout_prompt_to_protocol(
        prompt=prompt,
        symbols=symbols,
        timeframes=[str(x).upper() for x in timeframes],
        lookback_bars=2000,
        n_breakout=48,
        top_n=20,
    )
    return {"ok": True, **out, "runtime": {"source": source, "timeframes": timeframes, "lookback_hours": lookback_hours, "symbols_count": len(symbols)}}


@router.post("/strategy/compile")
async def api_strategy_compile(payload: Dict[str, Any] = Body(default={})):
    """StrategySpec -> DSL/1.0（确定性编译）。MVP：仅支持 breakout_mvp。"""
    spec = payload.get("strategy_spec") if isinstance(payload.get("strategy_spec"), dict) else None
    if not spec:
        raise HTTPException(status_code=400, detail="strategy_spec is required")
    try:
        out = compile_breakout_spec_with_report(spec)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"compile failed: {e}")
    return {"ok": True, **out}


@router.post("/strategy/validate")
async def api_strategy_validate(payload: Dict[str, Any] = Body(default={})):
    """Stage1：StrategySpec schema 校验 + 默认值来源标注（MVP）。"""
    spec = payload.get("strategy_spec") if isinstance(payload.get("strategy_spec"), dict) else None
    if not spec:
        raise HTTPException(status_code=400, detail="strategy_spec is required")
    try:
        prev_spec = payload.get("prev_spec") if isinstance(payload.get("prev_spec"), dict) else None
        default_source = str(payload.get("default_source") or "system_default")
        if default_source not in ("system_default", "template_default"):
            default_source = "system_default"
        rep = validate_strategy_spec(spec, prev_spec=prev_spec, default_source=default_source)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"validate failed: {e}")
    return {"ok": True, **rep}


@router.post("/strategy/scan")
async def api_strategy_scan(payload: Dict[str, Any] = Body(default={})):
    """
    执行扫描（线路 B）：
    StrategySpec -> DSL（本地编译） -> ScanExecutor（本地 deterministic） -> EvidencePack -> candidates
    MVP：breakout（N=48，TopN=20）
    """
    spec = payload.get("strategy_spec") if isinstance(payload.get("strategy_spec"), dict) else None
    if not spec:
        raise HTTPException(status_code=400, detail="strategy_spec is required")

    uni = spec.get("universe") if isinstance(spec.get("universe"), dict) else {}
    symbols = uni.get("symbols") if isinstance(uni.get("symbols"), list) else []
    symbols = [str(s).strip() for s in symbols if str(s).strip()]
    timeframes = spec.get("timeframes") if isinstance(spec.get("timeframes"), list) else ["M15"]
    timeframes = [str(tf).upper() for tf in timeframes if str(tf).upper()]
    mvp = spec.get("mvp") if isinstance(spec.get("mvp"), dict) else {}
    n = int(mvp.get("n_breakout") or 48)
    top_n = int(mvp.get("top_n") or 20)
    direction = str(mvp.get("direction") or "both")
    top_n = max(5, min(200, top_n))
    n = max(20, min(500, n))

    dsl_text = compile_breakout_spec_to_dsl(spec)

    from backend.services.historical import historical_service

    items: List[Dict[str, Any]] = []
    lookback_bars = int((spec.get("lookback") or {}).get("bars") or 2000)
    lookback_bars = max(200, min(20000, lookback_bars))

    def _tf_sec(tf: str) -> int:
        return 60 if tf == "M1" else 300 if tf == "M5" else 900 if tf == "M15" else 1800 if tf == "M30" else 3600 if tf == "H1" else 14400 if tf == "H4" else 86400

    for sym in symbols[:200]:
        for tf in timeframes[:6]:
            try:
                last = historical_service.get_history(sym, tf, before_time=0, limit=1)
                if not last:
                    continue
                latest_t = int(last[-1]["time"])
                frm = latest_t - lookback_bars * _tf_sec(tf)
                bars = historical_service.get_history_range(sym, tf, from_time=frm, to_time=latest_t, limit=6000)
                evs = scan_breakout_candidates_on_bars(symbol=sym, timeframe=tf, bars=bars, n=n, direction=direction, top_n=top_n)
                for ev in evs:
                    items.append(
                        {
                            "symbol": sym,
                            "timeframe": tf,
                            "score": float(ev.get("score") or 0.0),
                            "trigger_time": int(ev.get("trigger_time") or latest_t),
                            "reason": str(((ev.get("facts") or {}).get("reason")) or ""),
                            "draw_objects": list(((ev.get("draw_plan") or {}).get("objects")) or []),
                            "evidence_pack": ev,
                        }
                    )
            except Exception:
                continue

    items.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    items = items[:top_n]
    return {"ok": True, "dsl_version": "1.0", "dsl_text": dsl_text, "items": items, "count": len(items)}



@router.post("/strategy/scan/run")
async def api_strategy_scan_run(payload: Dict[str, Any] = Body(default={})):
    """
    Stage3：扫描任务化（进度/取消）。
    返回 job_id；前端通过 /strategy/scan/status/{job_id} 轮询。
    """
    spec = payload.get("strategy_spec") if isinstance(payload.get("strategy_spec"), dict) else None
    if not spec:
        raise HTTPException(status_code=400, detail="strategy_spec is required")

    jid = job_store.create("strategy_scan", {"strategy_spec": spec})

    def _tf_sec(tf: str) -> int:
        return 60 if tf == "M1" else 300 if tf == "M5" else 900 if tf == "M15" else 1800 if tf == "M30" else 3600 if tf == "H1" else 14400 if tf == "H4" else 86400

    def _worker():
        import threading
        import time

        from backend.services.historical import historical_service

        try:
            uni = spec.get("universe") if isinstance(spec.get("universe"), dict) else {}
            symbols = uni.get("symbols") if isinstance(uni.get("symbols"), list) else []
            symbols2 = [str(s).strip() for s in symbols if str(s).strip()]
            timeframes = spec.get("timeframes") if isinstance(spec.get("timeframes"), list) else ["M15"]
            timeframes2 = [str(tf).upper() for tf in timeframes if str(tf).upper()]
            mvp = spec.get("mvp") if isinstance(spec.get("mvp"), dict) else {}
            n = int(mvp.get("n_breakout") or 48)
            top_n = int(mvp.get("top_n") or 20)
            direction = str(mvp.get("direction") or "both")
            top_n = max(5, min(200, top_n))
            n = max(20, min(500, n))

            dsl_text = compile_breakout_spec_to_dsl(spec)

            items: List[Dict[str, Any]] = []
            lookback_bars = int((spec.get("lookback") or {}).get("bars") or 2000)
            lookback_bars = max(200, min(20000, lookback_bars))

            total = max(1, len(symbols2[:200]) * max(1, len(timeframes2[:6])))
            k = 0
            for sym in symbols2[:200]:
                for tf in timeframes2[:6]:
                    # 支持取消：前端调用 cancel 会把 status 置为 cancelled
                    j = job_store.get(jid) or {}
                    if j.get("status") == "cancelled":
                        job_store.update(jid, progress=float(min(1.0, k / total)), message="cancelled", finished_at=int(time.time()))
                        return

                    k += 1
                    job_store.update(jid, progress=float(min(0.99, k / total)), message=f"{sym} {tf}")
                    try:
                        last = historical_service.get_history(sym, tf, before_time=0, limit=1)
                        if not last:
                            continue
                        latest_t = int(last[-1]["time"])
                        frm = latest_t - lookback_bars * _tf_sec(tf)
                        bars = historical_service.get_history_range(sym, tf, from_time=frm, to_time=latest_t, limit=6000)
                        evs = scan_breakout_candidates_on_bars(symbol=sym, timeframe=tf, bars=bars, n=n, direction=direction, top_n=top_n)
                        # 单一事实来源：同一策略 + 同一数据窗口 => snapshot_id 可复算
                        snapshot_id = f"{sym}:{tf}:{latest_t}:{lookback_bars}"
                        data_version = {"symbol": sym, "timeframe": tf, "from_time": int(frm), "to_time": int(latest_t), "bars": int(len(bars))}
                        for ev in evs:
                            try:
                                ev["snapshot_id"] = snapshot_id
                                ev["data_version"] = data_version
                                if isinstance(ev.get("facts"), dict):
                                    ev["facts"]["snapshot_id"] = snapshot_id
                                    ev["facts"]["data_version"] = data_version
                            except Exception:
                                pass
                            items.append(
                                {
                                    "symbol": sym,
                                    "timeframe": tf,
                                    "score": float(ev.get("score") or 0.0),
                                    "trigger_time": int(ev.get("trigger_time") or latest_t),
                                    "reason": str(((ev.get("facts") or {}).get("reason")) or ""),
                                    "draw_objects": list(((ev.get("draw_plan") or {}).get("objects")) or []),
                                    "evidence_pack": ev,
                                    "snapshot_id": snapshot_id,
                                    "data_version": data_version,
                                }
                            )
                    except Exception:
                        continue

            items.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
            items2 = items[:top_n]
            job_store.finish_ok(jid, {"dsl_version": "1.0", "dsl_text": dsl_text, "items": items2, "count": len(items2)}, files={})
        except Exception as e:
            job_store.finish_err(jid, str(e))

    import threading

    threading.Thread(target=_worker, daemon=True).start()
    return {"ok": True, "job_id": jid}


@router.get("/strategy/scan/status/{job_id}")
async def api_strategy_scan_status(job_id: str):
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": j}


@router.post("/strategy/scan/cancel/{job_id}")
async def api_strategy_scan_cancel(job_id: str):
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    if j.get("status") == "running":
        job_store.update(job_id, status="cancelled", message="cancelled")
    return {"ok": True, "job": job_store.get(job_id)}


@router.post("/strategy/annotation/list")
async def api_strategy_annotation_list(payload: Dict[str, Any] = Body(default={})):
    """Stage4：查询某个候选的 annotation 版本列表（持久化）。"""
    symbol = str(payload.get("symbol") or "").strip()
    timeframe = str(payload.get("timeframe") or "").strip().upper()
    trigger_time = int(payload.get("trigger_time") or 0)
    rule_id = str(payload.get("rule_id") or "").strip() or "unknown"
    if not symbol or not timeframe or trigger_time <= 0:
        raise HTTPException(status_code=400, detail="symbol/timeframe/trigger_time are required")
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")
    duck = deps["sqlite_manager"]
    out = await duck.list_strategy_annotations(symbol, timeframe, trigger_time, rule_id)
    return {"ok": True, **out}


@router.post("/strategy/annotation/save")
async def api_strategy_annotation_save(payload: Dict[str, Any] = Body(default={})):
    """Stage4：保存一个新的 annotation_version（默认设为 active）。"""
    symbol = str(payload.get("symbol") or "").strip()
    timeframe = str(payload.get("timeframe") or "").strip().upper()
    trigger_time = int(payload.get("trigger_time") or 0)
    rule_id = str(payload.get("rule_id") or "").strip() or "unknown"
    snapshot_id = str(payload.get("snapshot_id") or "")
    data_version = payload.get("data_version") if isinstance(payload.get("data_version"), dict) else {}
    evidence = payload.get("evidence_pack") if isinstance(payload.get("evidence_pack"), dict) else {}
    annotation = payload.get("annotation") if isinstance(payload.get("annotation"), dict) else {}
    set_active = bool(payload.get("set_active", True))
    if not symbol or not timeframe or trigger_time <= 0:
        raise HTTPException(status_code=400, detail="symbol/timeframe/trigger_time are required")
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")
    duck = deps["duckdb_manager"]
    meta = await duck.save_strategy_annotation(
        symbol=symbol,
        timeframe=timeframe,
        trigger_time=trigger_time,
        rule_id=rule_id,
        snapshot_id=snapshot_id,
        data_version=data_version,
        evidence=evidence,
        annotation=annotation,
        set_active=set_active,
    )
    out = await duck.list_strategy_annotations(symbol, timeframe, trigger_time, rule_id)
    return {"ok": True, "saved": meta, **out}


@router.post("/strategy/annotation/set_active")
async def api_strategy_annotation_set_active(payload: Dict[str, Any] = Body(default={})):
    """Stage4：设置某个版本为 active。"""
    symbol = str(payload.get("symbol") or "").strip()
    timeframe = str(payload.get("timeframe") or "").strip().upper()
    trigger_time = int(payload.get("trigger_time") or 0)
    rule_id = str(payload.get("rule_id") or "").strip() or "unknown"
    version = int(payload.get("version") or 0)
    if not symbol or not timeframe or trigger_time <= 0 or version <= 0:
        raise HTTPException(status_code=400, detail="symbol/timeframe/trigger_time/version are required")
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")
    duck = deps["duckdb_manager"]
    meta = await duck.set_active_strategy_annotation(symbol=symbol, timeframe=timeframe, trigger_time=trigger_time, rule_id=rule_id, version=version)
    out = await duck.list_strategy_annotations(symbol, timeframe, trigger_time, rule_id)
    return {"ok": True, "updated": meta, **out}


@router.post("/strategy/gate/suggest")
async def api_strategy_gate_suggest(payload: Dict[str, Any] = Body(default={})):
    """Stage5 MVP：基于 EvidencePack 生成 GateDecision + TradePlan（确定性模板）。"""
    evidence = payload.get("evidence_pack") if isinstance(payload.get("evidence_pack"), dict) else None
    if not evidence:
        raise HTTPException(status_code=400, detail="evidence_pack is required")
    decision = suggest_gate_decision_mvp(evidence)
    plan = suggest_trade_plan_from_evidence(evidence)
    return {"ok": True, "decision": decision, "trade_plan": plan}


@router.post("/strategy/gate/list")
async def api_strategy_gate_list(payload: Dict[str, Any] = Body(default={})):
    symbol = str(payload.get("symbol") or "").strip()
    timeframe = str(payload.get("timeframe") or "").strip().upper()
    trigger_time = int(payload.get("trigger_time") or 0)
    rule_id = str(payload.get("rule_id") or "").strip() or "unknown"
    if not symbol or not timeframe or trigger_time <= 0:
        raise HTTPException(status_code=400, detail="symbol/timeframe/trigger_time are required")
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")
    duck = deps["sqlite_manager"]
    out = await duck.list_strategy_gate_decisions(symbol, timeframe, trigger_time, rule_id)
    return {"ok": True, **out}


@router.post("/strategy/gate/save")
async def api_strategy_gate_save(payload: Dict[str, Any] = Body(default={})):
    symbol = str(payload.get("symbol") or "").strip()
    timeframe = str(payload.get("timeframe") or "").strip().upper()
    trigger_time = int(payload.get("trigger_time") or 0)
    rule_id = str(payload.get("rule_id") or "").strip() or "unknown"
    snapshot_id = str(payload.get("snapshot_id") or "")
    data_version = payload.get("data_version") if isinstance(payload.get("data_version"), dict) else {}
    annotation_version = payload.get("annotation_version")
    annotation_version = int(annotation_version) if annotation_version not in (None, "", 0) else None
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    trade_plan = payload.get("trade_plan") if isinstance(payload.get("trade_plan"), dict) else {}
    set_active = bool(payload.get("set_active", True))
    if not symbol or not timeframe or trigger_time <= 0:
        raise HTTPException(status_code=400, detail="symbol/timeframe/trigger_time are required")
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")
    duck = deps["sqlite_manager"]
    meta = await duck.save_strategy_gate_decision(
        symbol=symbol,
        timeframe=timeframe,
        trigger_time=trigger_time,
        rule_id=rule_id,
        snapshot_id=snapshot_id,
        data_version=data_version,
        annotation_version=annotation_version,
        decision=decision,
        trade_plan=trade_plan,
        set_active=set_active,
    )
    out = await duck.list_strategy_gate_decisions(symbol, timeframe, trigger_time, rule_id)
    return {"ok": True, "saved": meta, **out}


@router.post("/strategy/gate/set_active")
async def api_strategy_gate_set_active(payload: Dict[str, Any] = Body(default={})):
    symbol = str(payload.get("symbol") or "").strip()
    timeframe = str(payload.get("timeframe") or "").strip().upper()
    trigger_time = int(payload.get("trigger_time") or 0)
    rule_id = str(payload.get("rule_id") or "").strip() or "unknown"
    version = int(payload.get("version") or 0)
    if not symbol or not timeframe or trigger_time <= 0 or version <= 0:
        raise HTTPException(status_code=400, detail="symbol/timeframe/trigger_time/version are required")
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")
    duck = deps["sqlite_manager"]
    meta = await duck.set_active_strategy_gate_decision(symbol=symbol, timeframe=timeframe, trigger_time=trigger_time, rule_id=rule_id, version=version)
    out = await duck.list_strategy_gate_decisions(symbol, timeframe, trigger_time, rule_id)
    return {"ok": True, "updated": meta, **out}


# -----------------------------
# StrategySchema v2 (module-based)
# -----------------------------


@router.get("/strategy/schema/v2/schema.json")
async def api_strategy_schema_v2_jsonschema():
    """返回 StrategySchema v2 的 JSONSchema（供前端表单/LLM tool-calling 使用）。"""
    return {"ok": True, "spec_version": "2.0", "jsonschema": schema_v2_jsonschema()}


@router.get("/strategy/capabilities/v2")
async def api_strategy_capabilities_v2():
    """返回当前能力矩阵（工具名→状态/版本/原因/替代方案）。"""
    return {"ok": True, **(load_capabilities_config() or {})}


@router.get("/market/features/catalog")
async def api_market_features_catalog():
    return {"ok": True, "catalog": get_market_feature_catalog()}


@router.post("/strategy/schema/v2/compile")
async def api_strategy_schema_v2_compile(payload: Dict[str, Any] = Body(default={})):
    """
    编译 StrategySchema v2 -> IR v1 + Text DSL + CompilationReport
    """
    schema = payload.get("strategy_schema")
    if not isinstance(schema, dict):
        raise HTTPException(status_code=400, detail="strategy_schema is required")
    ok, rep = compile_schema_v2_to_ir(schema)
    return {"ok": bool(ok), **(rep or {})}


@router.post("/strategy/schema/v2/execute")
async def api_strategy_schema_v2_execute(payload: Dict[str, Any] = Body(default={})):
    """
    最小执行链路（预览版）：
    StrategySchema v2 -> IR -> 执行 ToolRegistry v1（load_data/indicators/structures）

    入参：
      - strategy_schema: v2 schema
      - bars_override?: { timeframe: [bars] } 用于无 broker 环境下的离线执行
    """
    schema = payload.get("strategy_schema")
    if not isinstance(schema, dict):
        raise HTTPException(status_code=400, detail="strategy_schema is required")
    bars_override = payload.get("bars_override") if isinstance(payload.get("bars_override"), dict) else None
    debug_tools = bool(payload.get("debug_tools") or False)
    okc, comp = compile_schema_v2_to_ir(schema)
    if not okc:
        return {"ok": False, "status": "error", "compile": comp}
    ir = comp.get("ir_graph")
    _, exe = execute_ir_v1(ir, bars_override=bars_override, stop_on_error=False, debug_tools=debug_tools)
    # 对于预览执行：即使后续步骤缺少工具（比如 action.plan.*），也返回 ok=true + status=warning
    return {"ok": True, "status": exe.get("status"), "compile": comp, "exec": exe}


@router.post("/strategy/schema/v2/validate")
async def api_strategy_schema_v2_validate(payload: Dict[str, Any] = Body(default={})):
    """
    校验 StrategySchema v2（pydantic + 自定义引用校验）。
    payload: { strategy_schema: {...} }
    """
    spec = payload.get("strategy_schema") if isinstance(payload.get("strategy_schema"), dict) else None
    if not spec:
        raise HTTPException(status_code=400, detail="strategy_schema is required")
    ok, rep = validate_schema_v2(spec)
    return {"ok": ok, **rep}


@router.post("/strategy/parse_ai")
async def api_strategy_parse_ai(payload: Dict[str, Any] = Body(default={})):
    """
    AI：将自然语言策略描述转换为 StrategySchema v2，并立即做 schema 校验。
    payload:
      - prompt: str
      - settings: {base_url, api_key, model}
      - temperature (optional)
    """
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or "").strip()
    if not base_url or not api_key or not model:
        raise HTTPException(status_code=400, detail="missing settings: base_url/api_key/model")
    temperature = float(payload.get("temperature") or 0.2)
    timeout_sec = int(payload.get("timeout_sec") or 300)

    # 最多两次尝试：第一次常规；若 schema 校验失败，第二次用更严格提示 + 更低温度重试
    attempts = [
        {"temperature": temperature, "system_append": ""},
        {
            "temperature": 0.0,
            "system_append": "强制要求：meta/universe/data/action/outputs 必须是 JSON 对象（不要用字符串）；patterns/indicators 必须是数组（即使只有一个元素）。未使用的可选模块请省略或置为 null，不要写 [] 代替 object。",
        },
    ]

    last_parse_meta: Dict[str, Any] = {}
    last_schema: Optional[Dict[str, Any]] = None
    last_rep: Dict[str, Any] = {}
    last_ok = False

    def _heuristic_action_type_fix(prompt_text: str, schema_obj: Dict[str, Any]) -> Dict[str, Any]:
        """
        容错：LLM 偶发把“回撤进场”类描述误归到 continuation。
        这里做一个非常保守的纠错：
        - 如果 prompt 明确包含“回撤/回踩”，且 schema.action.type 不是 pullback，则调整为 pullback
        注意：这只影响 parse_ai（AI 解析），不影响纯 schema validate 接口。
        """
        try:
            p = (prompt_text or "").lower()
            wants_pullback = ("回撤" in p) or ("回踩" in p) or ("pullback" in p)
            # 进一步确认：常见回撤触发词
            wants_pullback = wants_pullback and (("ema" in p) or ("均线" in p) or ("吞没" in p) or ("retest" in p))
            if not wants_pullback:
                return schema_obj
            act = schema_obj.get("action")
            if not isinstance(act, dict):
                return schema_obj
            if str(act.get("type") or "") != "pullback":
                act = dict(act)
                act["type"] = "pullback"
                # 给一个空 payload，让 schema 的 root_validator 补默认
                if "pullback" not in act:
                    act["pullback"] = {}
                schema_obj = dict(schema_obj)
                schema_obj["action"] = act
            return schema_obj
        except Exception:
            return schema_obj

    for idx, att in enumerate(attempts):
        schema, parse_meta = ai_parse_to_schema_v2(
            prompt=prompt,
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=float(att["temperature"]),
            timeout_sec=timeout_sec,
            system_append=str(att.get("system_append") or ""),
        )
        last_parse_meta = dict(parse_meta or {})
        last_parse_meta["attempt"] = idx + 1
        last_schema = schema if isinstance(schema, dict) else None
        if not last_schema:
            continue
        # heuristic fix before validate
        before_type = None
        try:
            before_type = str(((last_schema.get("action") or {}) if isinstance(last_schema.get("action"), dict) else {}).get("type") or "")
        except Exception:
            before_type = None
        last_schema = _heuristic_action_type_fix(prompt, last_schema)
        try:
            after_type = str(((last_schema.get("action") or {}) if isinstance(last_schema.get("action"), dict) else {}).get("type") or "")
            if before_type and after_type and before_type != after_type:
                fixes = last_parse_meta.get("fixes") if isinstance(last_parse_meta.get("fixes"), list) else []
                fixes.append(
                    {
                        "code": "HEURISTIC_ACTION_TYPE",
                        "path": "action.type",
                        "before": before_type,
                        "after": after_type,
                        "reason": "根据 prompt 关键词进行保守纠错（回撤/回踩类）",
                    }
                )
                last_parse_meta["fixes"] = fixes
        except Exception:
            pass
        ok, rep = validate_schema_v2(last_schema)
        last_rep = rep or {}
        last_ok = bool(ok) and (rep.get("status") != "error")
        if last_ok:
            break

    if not last_schema:
        return {"ok": False, "parse_meta": last_parse_meta, "strategy_schema": None}

    # 将 schema 校验结果并入 parse_meta，方便前端展示“可用/需修复”
    parse_meta2 = dict(last_parse_meta)
    parse_meta2["schema_validation_status"] = last_rep.get("status")
    parse_meta2["schema_validation_errors"] = last_rep.get("validation_errors")

    return {
        "ok": bool(last_ok),
        "parse_meta": parse_meta2,
        "strategy_schema": last_schema,
        "normalized_schema": last_rep.get("normalized_spec"),
        # full canonical schema（保证包含所有顶层模块键）
        "strategy_schema_full": last_rep.get("normalized_spec"),
        "capabilities_required": last_rep.get("capabilities_required"),
        "unsupported_features": last_rep.get("unsupported_features"),
        "warnings": last_rep.get("warnings"),
    }


@router.get("/vp/active")
async def vp_active(
    symbol: str = Query(...),
    timeframe: str = Query(...),
    limit: int = Query(3000, ge=200, le=20000),
):
    """
    调试用：返回后端“与前端一致口径”的当前 session VP（active_block）及 POC/VAH/VAL。
    用于你对比前端画出来的 SessionVP 数值。
    """
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")

    bars = historical_service.get_history(symbol, timeframe, limit=int(limit))
    if not bars:
        return {"ok": True, "active_block": None}
    window = [
        {
            "time": int(b["time"]),
            "open": float(b["open"]),
            "high": float(b["high"]),
            "low": float(b["low"]),
            "close": float(b["close"]),
            "tick_volume": int(b.get("tick_volume") or b.get("volume") or 0),
            "delta_volume": int(b.get("delta_volume") or 0),
        }
        for b in bars
    ]
    scene = scene_engine.build_from_bars(symbol, timeframe, window, fast=True)
    vp = (scene.get("volume_profile") or {}) if isinstance(scene, dict) else {}
    active_block = vp.get("active_block")
    return {
        "ok": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "active_session": vp.get("active_session"),
        "sessionvp_options": vp.get("sessionvp_options"),
        "active_block": active_block,
        "poc": (active_block or {}).get("pocPrice"),
        "vah": (active_block or {}).get("valueAreaHigh"),
        "val": (active_block or {}).get("valueAreaLow"),
    }


# -----------------------------
# Watchlist / Alerts / Scan (MVP)
# -----------------------------


@router.get("/watchlist")
async def api_watchlist_list():
    return {"symbols": list_watchlist()}


@router.post("/watchlist/add")
async def api_watchlist_add(payload: Dict[str, Any] = Body(default={})):
    sym = str(payload.get("symbol") or "").strip()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required")
    watchlist_add_symbol(sym)
    return {"ok": True}


@router.post("/watchlist/remove")
async def api_watchlist_remove(payload: Dict[str, Any] = Body(default={})):
    sym = str(payload.get("symbol") or "").strip()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required")
    watchlist_remove_symbol(sym)
    return {"ok": True}


@router.get("/alerts")
async def api_alerts_list():
    return {"alerts": await asyncio.to_thread(alerts_list)}


@router.get("/alerts/events")
async def api_alerts_events(limit: int = Query(100)):
    return {"events": await asyncio.to_thread(alerts_list_events, int(limit))}

@router.post("/alerts/events/clear")
async def api_alerts_events_clear(payload: Dict[str, Any] = Body(default={})):
    aid = payload.get("alert_id")
    try:
        aid = int(aid) if aid is not None else None
    except Exception:
        aid = None
    from backend.services.alerts_store import clear_events

    n = await asyncio.to_thread(clear_events, aid)
    return {"ok": True, "deleted": int(n)}


@router.get("/alerts/reports")
async def api_alerts_reports(limit: int = Query(50)):
    return {"reports": await asyncio.to_thread(alerts_list_reports, int(limit))}


@router.post("/alerts/reports/clear")
async def api_alerts_reports_clear(payload: Dict[str, Any] = Body(default={})):
    aid = payload.get("alert_id")
    try:
        aid = int(aid) if aid is not None else None
    except Exception:
        aid = None
    from backend.services.alerts_store import clear_ai_reports

    n = await asyncio.to_thread(clear_ai_reports, aid)
    return {"ok": True, "deleted": int(n)}


@router.get("/alerts/analyzer-prompt")
async def api_alerts_analyzer_prompt_get():
    from backend.services.ai.prompt_library import load_alert_analyzer_prompt

    text = await asyncio.to_thread(load_alert_analyzer_prompt)
    return {"prompt": str(text or "").rstrip("\n")}


@router.post("/alerts/analyzer-prompt")
async def api_alerts_analyzer_prompt_set(payload: Dict[str, Any] = Body(default={})):
    from backend.services.alerts_store import set_analyzer_system_prompt

    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        raise HTTPException(status_code=400, detail="prompt must be a string")
    await asyncio.to_thread(set_analyzer_system_prompt, prompt)
    return {"ok": True}



@router.post("/alerts/create")
async def api_alerts_create(payload: Dict[str, Any] = Body(default={})):
    name = str(payload.get("name") or "").strip() or "Alert"
    rule = payload.get("rule") if isinstance(payload.get("rule"), dict) else {}
    if not rule or not rule.get("type"):
        raise HTTPException(status_code=400, detail="rule.type is required")
    aid = await asyncio.to_thread(alerts_create, name, rule, bool(payload.get("enabled", True)))
    return {"ok": True, "id": aid}


@router.post("/alerts/delete")
async def api_alerts_delete(payload: Dict[str, Any] = Body(default={})):
    aid = int(payload.get("id") or 0)
    if aid <= 0:
        raise HTTPException(status_code=400, detail="id is required")
    await asyncio.to_thread(alerts_delete, aid)
    return {"ok": True}


@router.post("/alerts/toggle")
async def api_alerts_toggle(payload: Dict[str, Any] = Body(default={})):
    aid = int(payload.get("id") or 0)
    enabled = bool(payload.get("enabled", True))
    if aid <= 0:
        raise HTTPException(status_code=400, detail="id is required")
    await asyncio.to_thread(alerts_set_enabled, aid, enabled)
    return {"ok": True}


@router.post("/scan/run")
async def api_scan_run(payload: Dict[str, Any] = Body(default={})):
    """
    多品种/多周期扫描（MVP）。
    payload:
      - source: active|watchlist|both
      - timeframes: ["M5","M30"]
      - lookback_hours: 24
    """
    source = str(payload.get("source") or "both")
    timeframes = payload.get("timeframes") if isinstance(payload.get("timeframes"), list) else ["M30"]
    lookback_hours = int(payload.get("lookback_hours") or 24)
    lookback_hours = max(6, min(168, lookback_hours))

    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker configured.")
    active_syms = list((deps["meta_store"].get_active_symbols() or {}).keys())
    wl = list_watchlist()
    if source == "active":
        symbols = active_syms
    elif source == "watchlist":
        symbols = wl
    else:
        symbols = list(dict.fromkeys(active_syms + wl))

    jid = job_store.create("scan", {"source": source, "timeframes": timeframes, "lookback_hours": lookback_hours, "symbols": symbols})

    def _worker():
        from backend.services.historical import historical_service
        import math

        results = []
        total = max(1, len(symbols) * max(1, len(timeframes)))
        k = 0
        for sym in symbols:
            for tf in timeframes:
                k += 1
                job_store.update(jid, progress=min(0.99, k / total), message=f"{sym} {tf}")
                try:
                    last = historical_service.get_history(sym, tf, before_time=0, limit=1)
                    if not last:
                        continue
                    latest_t = int(last[-1]["time"])
                    frm = latest_t - lookback_hours * 3600
                    bars = historical_service.get_history_range(sym, tf, from_time=frm, to_time=latest_t, limit=5000)
                    if len(bars) < 120:
                        continue
                    closes = [float(b["close"]) for b in bars]
                    highs = [float(b["high"]) for b in bars]
                    lows = [float(b["low"]) for b in bars]
                    # 简化波动率：近 40 根 TR 均值 vs 前 40 根
                    trs = []
                    for i in range(1, len(bars)):
                        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
                        trs.append(tr)
                    if len(trs) < 100:
                        continue
                    recent = sum(trs[-40:]) / 40.0
                    prev = sum(trs[-80:-40]) / 40.0
                    vol_up = prev > 0 and recent / prev >= 1.25
                    # 突破：收盘突破前 60 根区间高/低
                    prior_high = max(highs[-61:-1])
                    prior_low = min(lows[-61:-1])
                    last_close = closes[-1]
                    breakout = last_close > prior_high or last_close < prior_low
                    if vol_up and breakout:
                        results.append(
                            {
                                "symbol": sym,
                                "timeframe": tf,
                                "latest_time": latest_t,
                                "vol_ratio": recent / prev if prev else None,
                                "breakout": "up" if last_close > prior_high else "down",
                                "prior_high": prior_high,
                                "prior_low": prior_low,
                                "last_close": last_close,
                            }
                        )
                except Exception:
                    continue
        job_store.finish_ok(jid, {"items": results, "count": len(results)}, files={})

    import threading

    threading.Thread(target=_worker, daemon=True).start()
    return {"job_id": jid}


@router.get("/scan/status/{job_id}")
async def api_scan_status(job_id: str):
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job": j}


@router.get("/scene/latest")
async def scene_latest(symbol: str = Query(...), timeframe: str = Query("M1")):
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker selected.")

    duck = deps["sqlite_manager"]
    key = (symbol, timeframe)
    if key not in _scene_runtime_restored:
        try:
            st = duck.get_runtime_state(symbol, timeframe)
            if isinstance(st, dict):
                scene_engine.restore_runtime_state(symbol, timeframe, st)
        except Exception:
            pass
        _scene_runtime_restored.add(key)

    scene = scene_engine.build_latest(symbol, timeframe)

    # snapshot + runtime state persistence（用于回放/重启恢复）
    try:
        await duck.upsert_scene_snapshot(
            symbol,
            timeframe,
            int(scene.get("ts_utc") or 0),
            str(scene.get("snapshot_id") or ""),
            str(scene.get("ai_controls", {}).get("state_hash") or ""),
            json.dumps(scene, ensure_ascii=False),
        )
        await duck.upsert_runtime_state(
            symbol,
            timeframe,
            int(scene.get("ts_utc") or 0),
            json.dumps(scene_engine.export_runtime_state(symbol, timeframe), ensure_ascii=False),
        )
    except Exception:
        pass

    return scene


@router.get("/scene/diff")
async def scene_diff(symbol: str = Query(...), timeframe: str = Query("M1"), since: str = Query(...)):
    _ = timeframe
    return scene_engine.diff_since(symbol, timeframe, since)


@router.get("/scene/params")
async def scene_params():
    return {"ok": True, "params": SceneParams.from_env().to_dict()}


@router.get("/scene/history")
async def scene_history(
    symbol: str = Query(...),
    timeframe: str = Query("M1"),
    from_ts: int = Query(0, ge=0),
    to_ts: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    desc: bool = Query(False),
):
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker selected.")
    duck = deps["sqlite_manager"]
    items = duck.query_scene_snapshots(
        symbol,
        timeframe,
        from_ts=int(from_ts),
        to_ts=int(to_ts),
        limit=int(limit),
        offset=int(offset),
        desc=bool(desc),
    )
    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "count": len(items), "items": items}


@router.get("/scene/history/summary")
async def scene_history_summary(
    symbol: str = Query(...),
    timeframe: str = Query("M1"),
    from_ts: int = Query(0, ge=0),
    to_ts: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    desc: bool = Query(False),
):
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker selected.")
    duck = deps["sqlite_manager"]
    items = duck.query_scene_snapshots_summary(
        symbol,
        timeframe,
        from_ts=int(from_ts),
        to_ts=int(to_ts),
        limit=int(limit),
        offset=int(offset),
        desc=bool(desc),
    )
    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "count": len(items), "items": items}


# -----------------------------
# Research (Event Study) - MVP
# -----------------------------


@router.post("/research/event-study/run")
async def research_event_study_run(payload: Dict[str, Any] = Body(default={})):
    """
    启动一个事件研究任务（MVP）。
    默认范围：最近 N 根 bars（limit），并在滚动窗口上生成 scene，统计事件后收益分布。
    """
    symbol = str(payload.get("symbol") or "XAUUSDz")
    timeframe = str(payload.get("timeframe") or "M1")
    limit = int(payload.get("limit") or 5000)
    horizons = payload.get("horizons") or [10, 30, 60]
    event_ids = payload.get("event_ids") or [
        "liquidity_sweep_down_recover",
        "liquidity_sweep_up_recover",
        "reclaim_vah_confirmed",
        "reclaim_val_confirmed",
    ]
    mode = str(payload.get("mode") or "any")
    engine_params = payload.get("engine_params") if isinstance(payload.get("engine_params"), dict) else None
    fast = bool(payload.get("fast", True))

    jid = job_store.create(
        "event-study",
        {"symbol": symbol, "timeframe": timeframe, "limit": limit, "horizons": horizons, "event_ids": event_ids, "mode": mode},
    )

    def _update(p: float, stats: Any = None):
        msg = "running"
        if isinstance(stats, dict):
            msg = f"trial {int(stats.get('trial', 0)) + 1}/{int(stats.get('trials', trials))}"
            if stats.get("best_score") is not None:
                try:
                    msg += f" · best_score={float(stats.get('best_score')):.4f}"
                except Exception:
                    pass
        job_store.update(jid, progress=float(max(0.0, min(0.99, p))), message=msg, stats=stats or {})

    async def _run():
        try:
            summary, files = await asyncio.to_thread(
                run_event_study,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                horizons=horizons,
                event_ids=event_ids,
                mode=mode,
                engine_params=engine_params,
                fast=fast,
                update_cb=_update,
            )
            job_store.finish_ok(jid, summary, files)
        except Exception as e:
            job_store.finish_err(jid, str(e))

    asyncio.create_task(_run())
    return {"ok": True, "job_id": jid}


@router.get("/research/event-study/status/{job_id}")
async def research_event_study_status(job_id: str):
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": j}


@router.get("/research/event-study/download/{job_id}")
async def research_event_study_download(job_id: str, format: str = Query("csv")):
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    if j.get("status") != "done":
        raise HTTPException(status_code=400, detail=f"job not ready: {j.get('status')}")
    files = j.get("files") or {}
    fmt = str(format).lower()
    path = files.get(fmt)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="file not found")
    media = "application/zip" if fmt == "zip" else ("text/csv" if fmt == "csv" else "application/json")
    return FileResponse(path, media_type=media, filename=os.path.basename(path))


# -----------------------------
# Research (Strategy Backtest) - MVP
# -----------------------------


@router.post("/research/strategy-backtest/run")
async def research_strategy_backtest_run(payload: Dict[str, Any] = Body(default={})):
    symbol = str(payload.get("symbol") or "XAUUSDz")
    timeframe = str(payload.get("timeframe") or "M5")
    limit = int(payload.get("limit") or (5000 if timeframe == "M1" else 8000))
    strategy_id = str(payload.get("strategy_id") or "sweep_recover_reversal")
    strategy_spec = payload.get("strategy_spec") if isinstance(payload.get("strategy_spec"), dict) else None

    # 若未显式传 strategy_spec，则从注册表取
    if strategy_spec is None:
        s = get_strategy_by_id(strategy_id) or get_strategy_by_id("sweep_recover_reversal") or {}
        strategy_spec = {
            "id": s.get("id"),
            "long_event_ids": s.get("long_event_ids") or [],
            "short_event_ids": s.get("short_event_ids") or [],
            "default_params": s.get("default_params") or {},
            "default_engine_params": s.get("default_engine_params") or {},
        }

    dp = (strategy_spec.get("default_params") or {}) if isinstance(strategy_spec, dict) else {}
    # 默认不 timeout：只有当用户显式传 hold_bars>0 时才启用超时出场
    if "hold_bars" in payload:
        hold_bars = int(payload.get("hold_bars") or 0)
    else:
        hold_bars = int(dp.get("hold_bars") or 0)
    atr_stop_mult = float(payload.get("atr_stop_mult") or dp.get("atr_stop_mult") or 2.0)
    atr_tp_mult = float(payload.get("atr_tp_mult") or dp.get("atr_tp_mult") or 3.0)

    engine_params = payload.get("engine_params") if isinstance(payload.get("engine_params"), dict) else None
    if engine_params is None and isinstance(strategy_spec, dict) and isinstance(strategy_spec.get("default_engine_params"), dict):
        engine_params = strategy_spec.get("default_engine_params")

    long_event_ids = strategy_spec.get("long_event_ids") if isinstance(strategy_spec, dict) else None
    short_event_ids = strategy_spec.get("short_event_ids") if isinstance(strategy_spec, dict) else None
    fast = bool(payload.get("fast", True))

    jid = job_store.create(
        "strategy-backtest",
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "strategy_id": strategy_id,
            "strategy_spec": strategy_spec,
            "hold_bars": hold_bars,
            "atr_stop_mult": atr_stop_mult,
            "atr_tp_mult": atr_tp_mult,
            "engine_params": engine_params or {},
        },
    )

    def _update(p: float, stats: Any = None):
        msg = "running"
        if isinstance(stats, dict):
            msg = f"trial {int(stats.get('trial', 0)) + 1}/{int(stats.get('trials', trials))}"
            if stats.get("best_score") is not None:
                try:
                    msg += f" · best_score={float(stats.get('best_score')):.4f}"
                except Exception:
                    pass
        job_store.update(jid, progress=float(max(0.0, min(0.99, p))), message=msg, stats=stats or {})

    async def _run():
        try:
            summary, files = await asyncio.to_thread(
                run_strategy_backtest,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                long_event_ids=long_event_ids,
                short_event_ids=short_event_ids,
                hold_bars=hold_bars,
                atr_stop_mult=atr_stop_mult,
                atr_tp_mult=atr_tp_mult,
                engine_params=engine_params,
                fast=fast,
                update_cb=lambda p, stats=None: job_store.update(
                    jid,
                    progress=float(max(0.0, min(0.99, p))),
                    message=(
                        f"bars {stats.get('bars_processed')}/{stats.get('bars_total')} · trades {stats.get('trades')} · "
                        f"{'持仓中' if stats.get('has_position') else '空仓'}"
                        + (f" · {stats.get('last_trade')}" if stats and stats.get("last_trade") else "")
                    )
                    if isinstance(stats, dict)
                    else "running",
                    stats=stats or {},
                ),
            )
            job_store.finish_ok(jid, summary, files)
        except Exception as e:
            job_store.finish_err(jid, str(e))

    asyncio.create_task(_run())
    return {"ok": True, "job_id": jid}


@router.get("/research/strategy-backtest/status/{job_id}")
async def research_strategy_backtest_status(job_id: str):
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": j}


@router.get("/strategies")
async def strategies_list():
    return {"ok": True, "strategies": list_strategies()}


@router.get("/research/strategy-backtest/download/{job_id}")
async def research_strategy_backtest_download(job_id: str, file: str = Query("json")):
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    if j.get("status") != "done":
        raise HTTPException(status_code=400, detail=f"job not ready: {j.get('status')}")
    files = j.get("files") or {}
    key = str(file)
    path = files.get(key)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="file not found")
    media = "application/zip" if key == "zip" else ("application/json" if key.endswith("json") else "text/csv")
    return FileResponse(path, media_type=media, filename=os.path.basename(path))


# -----------------------------
# Optimize - MVP
# -----------------------------


@router.post("/optimize/run")
async def optimize_run(payload: Dict[str, Any] = Body(default={})):
    symbol = str(payload.get("symbol") or "XAUUSDz")
    timeframe = str(payload.get("timeframe") or "M5")
    limit = int(payload.get("limit") or (5000 if timeframe == "M1" else 8000))
    trials = int(payload.get("trials") or 15)
    seed = int(payload.get("seed") or 7)
    fast = bool(payload.get("fast", True))
    default_strategy_id = "sweep_detected_reversal" if timeframe in ("M15", "M30") else "sweep_recover_reversal"
    strategy_id = str(payload.get("strategy_id") or default_strategy_id)
    strategy_spec = payload.get("strategy_spec") if isinstance(payload.get("strategy_spec"), dict) else None
    if strategy_spec is None:
        s = get_strategy_by_id(strategy_id) or get_strategy_by_id(default_strategy_id) or {}
        strategy_spec = {
            "id": s.get("id"),
            "long_event_ids": s.get("long_event_ids") or [],
            "short_event_ids": s.get("short_event_ids") or [],
        }
    long_event_ids = strategy_spec.get("long_event_ids") if isinstance(strategy_spec, dict) else None
    short_event_ids = strategy_spec.get("short_event_ids") if isinstance(strategy_spec, dict) else None

    jid = job_store.create(
        "optimize",
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "trials": trials,
            "seed": seed,
            "fast": fast,
            "strategy_id": strategy_id,
            "strategy_spec": strategy_spec,
        },
    )

    def _update(p: float, stats: Any = None):
        msg = "running"
        if isinstance(stats, dict):
            msg = f"trial {int(stats.get('trial', 0)) + 1}/{int(stats.get('trials', trials))}"
            if stats.get("best_score") is not None:
                try:
                    msg += f" · best_score={float(stats.get('best_score')):.4f}"
                except Exception:
                    pass
        job_store.update(jid, progress=float(max(0.0, min(0.99, p))), message=msg, stats=stats or {})

    async def _run():
        try:
            summary, files = await asyncio.to_thread(
                run_optimize,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                trials=trials,
                seed=seed,
                fast=fast,
                long_event_ids=long_event_ids,
                short_event_ids=short_event_ids,
                update_cb=_update,
            )
            job_store.finish_ok(jid, summary, files)
        except Exception as e:
            job_store.finish_err(jid, str(e))

    asyncio.create_task(_run())
    return {"ok": True, "job_id": jid}


@router.get("/optimize/status/{job_id}")
async def optimize_status(job_id: str):
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": j}


@router.get("/optimize/download/{job_id}")
async def optimize_download(job_id: str, format: str = Query("csv")):
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    if j.get("status") != "done":
        raise HTTPException(status_code=400, detail=f"job not ready: {j.get('status')}")
    files = j.get("files") or {}
    fmt = str(format).lower()
    path = files.get(fmt)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="file not found")
    media = "application/zip" if fmt == "zip" else ("text/csv" if fmt == "csv" else "application/json")
    return FileResponse(path, media_type=media, filename=os.path.basename(path))


@router.get("/scene/by-time")
async def scene_by_time(
    symbol: str = Query(...),
    timeframe: str = Query("M1"),
    time: int = Query(..., description="Unix seconds（与 lightweight-charts time 对齐）"),
    mode: str = Query("nearest", description="nearest | lte"),
):
    deps = get_current_broker_deps()
    if not deps:
        raise HTTPException(status_code=400, detail="No active broker selected.")
    duck = deps["sqlite_manager"]

    item = duck.get_scene_by_time(symbol, timeframe, int(time), mode=str(mode))
    if not item:
        return {"ok": False, "message": "No scene snapshot found (try calling /api/scene/latest first)."}
    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "item": item}

@router.get("/calendar")
async def fetch_calendar(force: bool = Query(False, description="Force re-fetch from source bypassing cache")):
    """Fetch the economic calendar (US, high/medium impact) with Beijing Time."""
    try:
        events = await get_calendar_events(force=force)
        return {"ok": True, "events": events}
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to fetch calendar: {e}")
        return {"ok": False, "detail": str(e)}
