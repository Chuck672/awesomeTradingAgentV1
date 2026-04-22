from __future__ import annotations

"""
StrategySchema v2（正式结构）- Pydantic 模型

目标：
1) 模块化、可组合：meta/universe/data/indicators/structures/patterns/action/entry/context/risk/execution/outputs
2) 可编译：后续编译器将 Schema -> Executable IR -> Text DSL（由 IR 渲染）
3) 可验证：Pydantic 校验 + 自定义校验（indicator_ref 等）
4) 可导出 JSONSchema：供 LLM tool-calling 与前端表单生成使用
"""

from typing import Any, Dict, List, Literal, Optional, Union, Set, Tuple

from pydantic.v1 import BaseModel, Field, root_validator, validator


# -------------------------
# Common small types
# -------------------------

def _coerce_indicator_ref(v: Any) -> Any:
    """
    容错：允许 LLM 用字符串直接写 indicator id，例如：
      "atr_30m_14"
    自动转为：
      {"type":"indicator_ref","ref":"atr_30m_14","mult":1.0}
    """
    if isinstance(v, str):
        s = v.strip()
        if s:
            return {"type": "indicator_ref", "ref": s, "mult": 1.0}
    if isinstance(v, dict):
        # 允许只给 ref/mult
        if v.get("ref") and not v.get("type"):
            v = dict(v)
            v["type"] = "indicator_ref"
        return v
    return v


class FixedPips(BaseModel):
    type: Literal["fixed_pips"] = "fixed_pips"
    pips: float = Field(..., ge=0)


DistanceBySymbol = Dict[str, FixedPips]


class PipsDistance(BaseModel):
    """
    允许：
      {"default": {"type":"fixed_pips","pips":35}, "XAUUSDz": {"type":"fixed_pips","pips":35}}
    """

    # 允许 LLM/用户只填 symbol-specific 而漏填 default；会在 root_validator 中自动补 default
    default: Optional[FixedPips] = None

    class Config:
        extra = "allow"

    @root_validator(pre=True)
    def _ensure_default(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(values, dict) and values.get("default") is None:
            # 从第一个额外字段推断 default
            for k, v in values.items():
                if k == "default":
                    continue
                if isinstance(v, dict) and (v.get("type") == "fixed_pips") and ("pips" in v):
                    values["default"] = v
                    break
        # 若仍无 default，交由 pydantic 后续校验（会允许 None 但下游可决定是否接受）
        return values


class Session(BaseModel):
    name: str
    tz: str = "UTC"
    start: str  # "05:00"
    end: str  # "08:00"
    days: List[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]] = Field(default_factory=list)


class Meta(BaseModel):
    strategy_id: str = Field(..., min_length=3, description="策略唯一 ID（用于回测/实盘/审计对齐）。建议全局唯一且可读。")
    name: str = Field(..., min_length=1, description="策略名称（展示用）。")
    version: str = Field(..., min_length=1, description="策略版本号（建议语义化版本）。")
    description: str = Field("", max_length=5000, description="策略描述（可包含关键规则摘要与假设）。")

    tags: List[str] = Field(default_factory=list)
    authors: List[str] = Field(default_factory=list)
    notes: str = ""


class Universe(BaseModel):
    symbols: List[str] = Field(..., min_items=1, description="交易品种列表。")
    primary_timeframe: str = Field(..., min_length=2, description="主周期（例如 30m / 15m / 4h）。")

    max_new_trades_per_symbol_per_day: int = Field(1, ge=0)
    allow_multiple_positions_per_symbol: bool = False
    max_positions_total: int = Field(3, ge=0)
    trade_sessions: List[Session] = Field(default_factory=list)


class DataQuality(BaseModel):
    drop_incomplete_last_bar: bool = True
    allow_gaps: bool = True


class NewsCalendar(BaseModel):
    enabled: bool = False


class DataConfig(BaseModel):
    history_lookback_bars: int = Field(..., ge=50, description="主周期历史回看 bars，用于 scan/backtest/形态检测等。")
    higher_timeframes: List[str] = Field(default_factory=list, description="高周期上下文（不需要则 []）。")
    data_quality: DataQuality = Field(default_factory=DataQuality)
    news_calendar: NewsCalendar = Field(default_factory=NewsCalendar)


class IndicatorDecl(BaseModel):
    """
    声明式指标：
    - id 必须唯一，供 indicator_ref 引用
    - name/timeframe/params 决定 tool registry 的调用
    """

    id: str = Field(..., min_length=3, description="指标输出 ID（必须唯一），供 indicator_ref 引用。")
    name: str = Field(..., min_length=2, description="指标名称（ATR/EMA/SMA/RSI/ADX/VWAP/BB/KC 等）。")
    timeframe: str = Field(..., min_length=2, description="指标计算周期（例如 30m / 4h）。")
    params: Dict[str, Any] = Field(default_factory=dict)
    unit: Optional[str] = None  # "pips" | "price" | "percent" | "index" ...


# -------------------------
# Structures (Level/Zone)
# -------------------------


class LevelSourceHTFSwingPoints(BaseModel):
    type: Literal["htf_swing_points"] = "htf_swing_points"
    timeframe: str = "4h"
    lookback_bars: int = Field(300, ge=20)
    pivot_left: int = Field(3, ge=1)
    pivot_right: int = Field(3, ge=1)


class LevelSourcePrevDayHL(BaseModel):
    type: Literal["prev_day_high_low"] = "prev_day_high_low"


class LevelSourcePrevWeekHL(BaseModel):
    type: Literal["prev_week_high_low"] = "prev_week_high_low"


class LevelSourceSessionHL(BaseModel):
    type: Literal["session_high_low"] = "session_high_low"
    session_name: str = Field(..., min_length=1)
    tz: str = "UTC"


class LevelSourceFractalLevels(BaseModel):
    type: Literal["fractal_levels"] = "fractal_levels"
    timeframe: str = "4h"
    lookback_bars: int = Field(300, ge=20)
    fractal_left: int = Field(2, ge=1)
    fractal_right: int = Field(2, ge=1)


class LevelSourceVolumeProfilePOC(BaseModel):
    """
    预留：Volume Profile / Session VP / Fixed Range VP 的 POC/VAH/VAL。
    注意：该 source 的可执行性取决于 Tool Registry 是否实现。
    """

    type: Literal["vp_poc"] = "vp_poc"
    timeframe: str = "30m"
    lookback_bars: int = Field(300, ge=50)


LevelSource = Union[
    LevelSourceHTFSwingPoints,
    LevelSourcePrevDayHL,
    LevelSourcePrevWeekHL,
    LevelSourceSessionHL,
    LevelSourceFractalLevels,
    LevelSourceVolumeProfilePOC,
]


class LevelMerge(BaseModel):
    distance_pips: PipsDistance
    prefer_higher_timeframe: bool = True


class LevelScoring(BaseModel):
    enabled: bool = True
    weights: Dict[str, float] = Field(default_factory=dict)
    min_score: float = 0


class LevelOutput(BaseModel):
    max_levels: int = Field(8, ge=1, le=100)
    emit_zone: bool = True
    zone_half_width_pips: PipsDistance
    # zone 的默认有效期（用于生成 from_time/to_time），以 bar 数计
    zone_max_age_bars: int = Field(300, ge=10, le=5000)


class LevelGenerator(BaseModel):
    sources: List[LevelSource] = Field(default_factory=list)
    merge: LevelMerge
    scoring: LevelScoring = Field(default_factory=LevelScoring)
    output: LevelOutput


class Structures(BaseModel):
    level_generator: Optional[LevelGenerator] = None


# -------------------------
# Patterns
# -------------------------


class PatternTriangleContraction(BaseModel):
    type: Literal["triangle_contraction"] = "triangle_contraction"
    timeframe: str = "30m"
    lookback_bars: int = Field(120, ge=20, le=5000)
    pivot_left: int = Field(3, ge=1, le=20)
    pivot_right: int = Field(3, ge=1, le=20)
    min_score_to_emit: float = Field(70, ge=0, le=100)
    emit_boundary_as_zone: bool = True

    # 预留：更多参数后续可加（touch_tolerance、slope_threshold、violations 等）
    class Config:
        extra = "allow"


class PatternChannel(BaseModel):
    type: Literal["channel"] = "channel"
    timeframe: str = "30m"
    lookback_bars: int = Field(160, ge=20, le=5000)
    pivot_left: int = Field(3, ge=1, le=20)
    pivot_right: int = Field(3, ge=1, le=20)
    min_score_to_emit: float = Field(60, ge=0, le=100)

    class Config:
        extra = "allow"


class PatternFlag(BaseModel):
    type: Literal["flag"] = "flag"
    timeframe: str = "30m"
    lookback_bars: int = Field(120, ge=20, le=5000)
    min_score_to_emit: float = Field(60, ge=0, le=100)

    class Config:
        extra = "allow"


class PatternWedge(BaseModel):
    type: Literal["wedge"] = "wedge"
    timeframe: str = "30m"
    lookback_bars: int = Field(160, ge=20, le=5000)
    min_score_to_emit: float = Field(60, ge=0, le=100)

    class Config:
        extra = "allow"


class PatternHeadAndShoulders(BaseModel):
    type: Literal["head_shoulders"] = "head_shoulders"
    timeframe: str = "30m"
    lookback_bars: int = Field(220, ge=50, le=5000)
    min_score_to_emit: float = Field(60, ge=0, le=100)

    class Config:
        extra = "allow"


class PatternCandlestick(BaseModel):
    """
    蜡烛形态检测（pinbar/engulfing/doji/inside_bar 等），通常属于“弱证据”。
    """

    type: Literal["candlestick"] = "candlestick"
    timeframe: str = "30m"
    patterns: List[str] = Field(default_factory=list)
    min_strength: Optional[Literal["weak", "medium", "strong"]] = "weak"

    class Config:
        extra = "allow"


class PatternRectangleRange(BaseModel):
    """
    矩形盘整/箱体（deterministic）：
    - 用 lookback_bars 内的 top/bottom + touch 统计构造区间边界
    """

    type: Literal["rectangle_range"] = "rectangle_range"
    timeframe: str = "30m"
    lookback_bars: int = Field(120, ge=20, le=5000)
    min_touches_per_side: int = Field(2, ge=1, le=20)
    tolerance_atr_mult: float = Field(0.25, ge=0.0, le=5.0)
    # 输出模式：
    # - best：只输出评分最高的一个箱体（默认，适合策略执行）
    # - distinct：输出多个“去重后”的箱体（推荐做扫描/研究）
    # - all：输出所有通过过滤的候选箱体（可能很多，适合离线分析/调参）
    emit: Literal["best", "distinct", "all"] = "best"
    max_results: int = Field(50, ge=1, le=2000)
    # distinct 输出的行为控制：
    # - distinct_no_overlap=True：保证输出的箱体时间区间互不重叠、互不包含（推荐，便于可视化/结构化研究）
    # - distinct_no_overlap=False：允许一定重叠（仅用于调参/研究）
    distinct_no_overlap: bool = True
    # 当 distinct_no_overlap=False 时，用该阈值做时间区间去重（IoU >= 阈值认为是同一个箱体，保留高分）
    dedup_iou: float = Field(0.55, ge=0.0, le=1.0)
    # 过滤趋势段：收盘在箱体内比例
    min_containment: float = Field(0.80, ge=0.0, le=1.0)
    # 箱体高度（按 ATR 归一化）上限：过大通常不是“盘整”
    max_height_atr: float = Field(8.0, ge=0.1, le=50.0)
    # 净位移（按 ATR 归一化）上限：过大通常是趋势推进
    max_drift_atr: float = Field(3.0, ge=0.1, le=50.0)
    # 方向效率上限（net_change / path）：箱体应更“来回”，效率更低
    max_efficiency: float = Field(0.45, ge=0.0, le=1.0)

    class Config:
        extra = "allow"


class PatternCloseOutsideLevelZone(BaseModel):
    """
    关键位有效突破（close outside level/zone）。
    """

    type: Literal["close_outside_level_zone"] = "close_outside_level_zone"
    timeframe: str = "30m"
    close_buffer: float = Field(0.0, ge=0.0)
    # 扫描模式：
    # - realtime：只评估最后一根（以及必要时上一根）K 线，适合实时推送/盘中
    # - historical：在 lookback_bars 区间内扫描所有触发事件，适合回测/研究/可视化
    scan_mode: Literal["realtime", "historical"] = "realtime"
    lookback_bars: int = Field(300, ge=10, le=5000)
    max_events: int = Field(50, ge=1, le=2000)

    # 确认方式（mode）：
    # - one_body：默认，1 根实体收盘确认（body 在 zone 外）
    # - two_close：二次确认，连续 2 根 close 在 zone 外
    confirm_mode: Literal["one_body", "two_close"] = "one_body"
    confirm_n: int = Field(2, ge=2, le=5)  # 仅对 two_close 生效，默认 2

    class Config:
        extra = "allow"


class PatternBreakoutRetestHold(BaseModel):
    """
    突破-回踩确认（Breakout + Retest Hold）。
    """

    type: Literal["breakout_retest_hold"] = "breakout_retest_hold"
    timeframe: str = "30m"
    # 扫描模式
    # - realtime：只评估最后一根（以及必要的上一根），适合盘中
    # - historical：在 lookback_bars 内扫描所有符合的形态事件
    scan_mode: Literal["realtime", "historical"] = "realtime"
    lookback_bars: int = Field(300, ge=20, le=5000)

    # Breakout 确认方式（mode）
    confirm_mode: Literal["one_body", "two_close"] = "one_body"
    confirm_n: int = Field(2, ge=2, le=5)  # 仅对 two_close 生效

    # Retest/Pullback 规则（默认：回踩到边界 zone）
    retest_window_bars: int = Field(16, ge=1, le=200)
    continue_window_bars: int = Field(8, ge=1, le=200)

    # 阈值（价格单位）
    # - buffer：突破阈值（close 出界需要超过该值）
    # - pullback_margin：回踩容差（edge zone 宽度）
    buffer: float = Field(0.0, ge=0.0)
    pullback_margin: float = Field(0.0, ge=0.0)
    max_events: int = Field(50, ge=1, le=2000)

    class Config:
        extra = "allow"


class PatternFalseBreakout(BaseModel):
    """
    假突破/失败突破：刺破边界但收回区间内（wick/close 规则）。
    """

    type: Literal["false_breakout"] = "false_breakout"
    timeframe: str = "30m"
    lookback_bars: int = Field(120, ge=20, le=5000)
    buffer: float = Field(0.0, ge=0.0)

    class Config:
        extra = "allow"


class PatternLiquiditySweep(BaseModel):
    """
    流动性扫损/Stop Run：扫过关键位后在 N 根内收回。
    """

    type: Literal["liquidity_sweep"] = "liquidity_sweep"
    timeframe: str = "30m"
    lookback_bars: int = Field(160, ge=20, le=5000)
    buffer: float = Field(0.0, ge=0.0)
    recover_within_bars: int = Field(3, ge=1, le=50)

    class Config:
        extra = "allow"


class PatternBOS(BaseModel):
    """
    BOS（Break of Structure）：顺趋势突破结构点。
    """

    type: Literal["bos"] = "bos"
    timeframe: str = "30m"
    lookback_bars: int = Field(220, ge=50, le=5000)
    pivot_left: int = Field(3, ge=1, le=20)
    pivot_right: int = Field(3, ge=1, le=20)
    buffer: float = Field(0.0, ge=0.0)

    class Config:
        extra = "allow"


class PatternCHOCH(BaseModel):
    """
    CHOCH（Change of Character）：逆趋势突破结构点（早期反转信号）。
    """

    type: Literal["choch"] = "choch"
    timeframe: str = "30m"
    lookback_bars: int = Field(220, ge=50, le=5000)
    pivot_left: int = Field(3, ge=1, le=20)
    pivot_right: int = Field(3, ge=1, le=20)
    buffer: float = Field(0.0, ge=0.0)

    class Config:
        extra = "allow"


PatternDetector = Union[
    PatternTriangleContraction,
    PatternChannel,
    PatternFlag,
    PatternWedge,
    PatternHeadAndShoulders,
    PatternCandlestick,
    PatternRectangleRange,
    PatternCloseOutsideLevelZone,
    PatternBreakoutRetestHold,
    PatternFalseBreakout,
    PatternLiquiditySweep,
    PatternBOS,
    PatternCHOCH,
]


# -------------------------
# Action (breakout/pullback/...)
# -------------------------


class IndicatorRef(BaseModel):
    type: Literal["indicator_ref"] = "indicator_ref"
    ref: str
    mult: float = 1.0


class BreakoutCloseRule(BaseModel):
    must_close_outside_zone: bool = True
    close_buffer_pips: Optional[PipsDistance] = None


class BreakoutBodyRule(BaseModel):
    min_body_ratio: float = Field(0.65, ge=0, le=1)


class BreakoutDisplacementRule(BaseModel):
    mode: Literal["either", "atr", "fixed_pips"] = "either"
    threshold: Optional[IndicatorRef] = None

    _coerce_threshold = validator("threshold", pre=True, allow_reuse=True)(_coerce_indicator_ref)


class BreakoutValidBreakout(BaseModel):
    close_rule: BreakoutCloseRule = Field(default_factory=BreakoutCloseRule)
    body_rule: BreakoutBodyRule = Field(default_factory=BreakoutBodyRule)
    displacement_rule: Optional[BreakoutDisplacementRule] = None


class FollowThrough(BaseModel):
    mode: Literal["either", "momentum", "retest_hold", "off"] = "either"
    window_bars: int = Field(3, ge=1, le=50)


class ActionBreakout(BaseModel):
    valid_breakout: BreakoutValidBreakout = Field(default_factory=BreakoutValidBreakout)
    follow_through: FollowThrough = Field(default_factory=FollowThrough)


class PullbackDepth(BaseModel):
    mode: Literal["atr_mult", "percent", "fixed_pips"] = "atr_mult"
    atr: Optional[IndicatorRef] = None
    mult: float = 1.0
    percent: Optional[float] = Field(None, ge=0, le=1)
    pips: Optional[float] = Field(None, ge=0)

    _coerce_atr = validator("atr", pre=True, allow_reuse=True)(_coerce_indicator_ref)


class ActionPullback(BaseModel):
    """
    回踩/回撤型：通常需要先定义 impulse，然后定义 pullback depth 与 reclaim/confirm。
    这里保留通用骨架，细节参数允许通过 extra 扩展。
    """

    impulse_lookback_bars: int = Field(50, ge=5, le=2000)
    pullback_depth: PullbackDepth = Field(default_factory=PullbackDepth)
    confirm: Literal["none", "reclaim_level", "candlestick", "structure"] = "reclaim_level"

    class Config:
        extra = "allow"


class MeanReversionDeviation(BaseModel):
    mode: Literal["atr_mult", "fixed_pips", "percent"] = "atr_mult"
    atr: Optional[IndicatorRef] = None
    mult: float = 2.0
    pips: Optional[float] = Field(None, ge=0)
    percent: Optional[float] = Field(None, ge=0)

    _coerce_atr = validator("atr", pre=True, allow_reuse=True)(_coerce_indicator_ref)


class ActionMeanReversion(BaseModel):
    mean: Literal["vwap", "ema", "sma", "midband", "custom"] = "vwap"
    deviation: MeanReversionDeviation = Field(default_factory=MeanReversionDeviation)
    entry_signal: Literal["pinbar", "engulfing", "doji", "none"] = "pinbar"

    class Config:
        extra = "allow"


class ActionContinuation(BaseModel):
    """
    趋势延续：趋势定义 + 回调定义 + 再加速触发。
    """

    trend_mode: Literal["ma_slope", "market_structure", "adx"] = "ma_slope"
    class Config:
        extra = "allow"


class ActionRange(BaseModel):
    """
    区间：区间识别 + 高抛低吸或假突破反向。
    """

    range_lookback_bars: int = Field(120, ge=20, le=5000)
    class Config:
        extra = "allow"


class Action(BaseModel):
    type: Literal["breakout", "pullback", "mean_reversion", "continuation", "range", "custom"] = Field(
        "breakout",
        description="行为模型类型：breakout（突破）/ pullback（回撤）/ mean_reversion（均值回归）/ continuation（延续）/ range（区间）/ custom。",
    )
    breakout: Optional[ActionBreakout] = None
    pullback: Optional[ActionPullback] = None
    mean_reversion: Optional[ActionMeanReversion] = None
    continuation: Optional[ActionContinuation] = None
    range: Optional[ActionRange] = None

    class Config:
        extra = "allow"

    @root_validator
    def _ensure_action_payload(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        t = values.get("type")
        if t == "breakout" and values.get("breakout") is None:
            values["breakout"] = ActionBreakout()
        if t == "pullback" and values.get("pullback") is None:
            values["pullback"] = ActionPullback()
        if t == "mean_reversion" and values.get("mean_reversion") is None:
            values["mean_reversion"] = ActionMeanReversion()
        if t == "continuation" and values.get("continuation") is None:
            values["continuation"] = ActionContinuation()
        if t == "range" and values.get("range") is None:
            values["range"] = ActionRange()
        return values


# -------------------------
# Entry / Context / Risk / Execution / Outputs
# -------------------------


class EntryRetestConfirm(BaseModel):
    confirm_candle: str = "close"
    max_wait_bars: int = Field(6, ge=1, le=200)


class Entry(BaseModel):
    type: Literal["market", "limit", "retest_confirm", "stop_order", "split_entries"] = "retest_confirm"
    retest_confirm: Optional[EntryRetestConfirm] = None
    validity_bars: int = Field(8, ge=1, le=500)

    @root_validator
    def _ensure_entry_payload(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values.get("type") == "retest_confirm" and values.get("retest_confirm") is None:
            values["retest_confirm"] = EntryRetestConfirm()
        return values


class HTFBiasMarketStructure(BaseModel):
    timeframe: str = "4h"
    require_bos_in_direction: bool = True
    lookback_swings: int = Field(8, ge=1, le=200)


class HTFBiasMASlope(BaseModel):
    timeframe: str = "4h"
    ma_type: Literal["ema", "sma"] = "ema"
    period: int = Field(50, ge=2, le=500)
    min_slope: Optional[float] = None


class HTFBias(BaseModel):
    enabled: bool = True
    mode: Literal["market_structure", "ma_slope", "none"] = "market_structure"
    market_structure: Optional[HTFBiasMarketStructure] = None
    ma_slope: Optional[HTFBiasMASlope] = None

    @root_validator
    def _ensure_payload(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values.get("enabled") is False:
            return values
        if values.get("mode") == "market_structure" and values.get("market_structure") is None:
            values["market_structure"] = HTFBiasMarketStructure()
        if values.get("mode") == "ma_slope" and values.get("ma_slope") is None:
            values["ma_slope"] = HTFBiasMASlope()
        return values


class SpaceFilter(BaseModel):
    enabled: bool = False
    min_distance_to_next_htf_level_pips: Optional[PipsDistance] = None


class SpreadFilter(BaseModel):
    enabled: bool = False
    max_spread_pips: Optional[PipsDistance] = None


class VolatilityRegime(BaseModel):
    enabled: bool = False
    mode: Literal["atr_percentile", "atr_threshold", "off"] = "off"
    class Config:
        extra = "allow"


class SessionFilter(BaseModel):
    enabled: bool = False
    sessions: List[str] = Field(default_factory=list)


class MicroFilters(BaseModel):
    spread: Optional[SpreadFilter] = None


class Context(BaseModel):
    htf_bias: Optional[HTFBias] = None
    space_filter: Optional[SpaceFilter] = None
    micro_filters: Optional[MicroFilters] = None
    volatility_regime: Optional[VolatilityRegime] = None
    session_filter: Optional[SessionFilter] = None

    class Config:
        extra = "allow"


class StopLossBeyondZone(BaseModel):
    extra_buffer_pips: PipsDistance


class StopLossATRMult(BaseModel):
    atr: IndicatorRef
    mult: float = Field(1.5, ge=0.1, le=10)

    _coerce_atr = validator("atr", pre=True, allow_reuse=True)(_coerce_indicator_ref)


class StopLossStructurePoint(BaseModel):
    point: Literal["swing_low", "swing_high", "pattern_boundary"] = "pattern_boundary"
    extra_buffer_pips: Optional[PipsDistance] = None


class StopLoss(BaseModel):
    method: Literal["beyond_zone", "atr_mult", "structure_point"] = "beyond_zone"
    beyond_zone: Optional[StopLossBeyondZone] = None
    atr_mult: Optional[StopLossATRMult] = None
    structure_point: Optional[StopLossStructurePoint] = None

    @root_validator
    def _ensure_payload(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        m = values.get("method")
        if m == "beyond_zone" and values.get("beyond_zone") is None:
            values["beyond_zone"] = StopLossBeyondZone(extra_buffer_pips=PipsDistance(default=FixedPips(pips=25)))
        return values


class TakeProfitRR(BaseModel):
    r_multiple: float = Field(2.0, ge=0.1, le=20)


class TakeProfitNextLevel(BaseModel):
    level_source: Literal["structure", "pattern", "either"] = "either"


class TakeProfitHybrid(BaseModel):
    min_R: float = Field(1.5, ge=0.1, le=20)


class TakeProfit(BaseModel):
    method: Literal["rr", "next_level", "hybrid"] = "hybrid"
    rr: Optional[TakeProfitRR] = None
    next_level: Optional[TakeProfitNextLevel] = None
    hybrid: Optional[TakeProfitHybrid] = None

    @root_validator
    def _ensure_payload(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        m = values.get("method")
        if m == "hybrid" and values.get("hybrid") is None:
            values["hybrid"] = TakeProfitHybrid()
        if m == "rr" and values.get("rr") is None:
            values["rr"] = TakeProfitRR()
        if m == "next_level" and values.get("next_level") is None:
            values["next_level"] = TakeProfitNextLevel()
        return values


class RiskGuards(BaseModel):
    min_rr: float = Field(1.5, ge=0, le=50)
    max_trades_per_day_total: int = Field(5, ge=0, le=100)
    max_daily_loss_pct: Optional[float] = Field(None, ge=0, le=100)
    max_sl_pips: Optional[PipsDistance] = None


class Risk(BaseModel):
    risk_per_trade_pct: float = Field(1.0, ge=0, le=100)
    stop_loss: StopLoss = Field(default_factory=StopLoss)
    take_profit: TakeProfit = Field(default_factory=TakeProfit)
    guards: RiskGuards = Field(default_factory=RiskGuards)

    class Config:
        extra = "allow"


class Execution(BaseModel):
    order_type_preference: Literal["market", "limit", "auto"] = "auto"
    max_slippage_pips: Optional[float] = Field(None, ge=0)
    cancel_after_sec: int = Field(120, ge=0, le=36000)

    partial_fill_policy: Literal["accept", "cancel_remaining", "retry"] = "accept"

    retry_policy: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class Outputs(BaseModel):
    emit_evidence_pack: bool = True
    emit_draw_plan: bool = True
    emit_compilation_report: bool = True
    emit_trace: bool = True
    emit_intermediate_artifacts: bool = False


class StrategySchemaV2(BaseModel):
    spec_version: Literal["2.0"] = "2.0"
    meta: Meta
    universe: Universe
    data: DataConfig

    indicators: List[IndicatorDecl] = Field(default_factory=list)
    structures: Optional[Structures] = None
    patterns: List[PatternDetector] = Field(default_factory=list)

    action: Action
    entry: Optional[Entry] = None
    context: Optional[Context] = None
    risk: Optional[Risk] = None
    execution: Optional[Execution] = None

    outputs: Outputs = Field(default_factory=Outputs)

    # -------- Custom validation --------
    @validator("indicators")
    def _unique_indicator_ids(cls, v: List[IndicatorDecl]) -> List[IndicatorDecl]:
        seen = set()
        dup = []
        for it in v or []:
            if it.id in seen:
                dup.append(it.id)
            seen.add(it.id)
        if dup:
            raise ValueError(f"duplicate indicator ids: {sorted(set(dup))}")
        return v

    @root_validator
    def _validate_indicator_refs(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        ind_ids: Set[str] = {it.id for it in (values.get("indicators") or [])}

        def _walk(o: Any, refs: Set[str]):
            if o is None:
                return
            if isinstance(o, IndicatorRef):
                refs.add(o.ref)
                return
            if isinstance(o, BaseModel):
                for _, v in o.__dict__.items():
                    _walk(v, refs)
                return
            if isinstance(o, dict):
                # 兼容：dict 形态的 indicator_ref（来自外部 JSON）
                if o.get("type") == "indicator_ref" and "ref" in o:
                    refs.add(str(o.get("ref")))
                for v in o.values():
                    _walk(v, refs)
                return
            if isinstance(o, list):
                for it in o:
                    _walk(it, refs)
                return

        refs: Set[str] = set()
        for k in ("action", "context", "risk", "execution"):
            _walk(values.get(k), refs)

        missing = sorted([r for r in refs if r and r not in ind_ids])
        if missing:
            raise ValueError(f"indicator_ref not found in indicators[]: {missing}")
        return values


def schema_json() -> Dict[str, Any]:
    """导出 JSONSchema（给前端与 LLM tool-calling 用）。"""
    return StrategySchemaV2.schema()  # pydantic v1 compatible
