"use client";

import React, { useEffect, useMemo, useReducer, useState } from "react";
import { Button } from "@/components/ui/button";
import { getBaseUrl } from "@/lib/api";

type StageStatus = "idle" | "draft" | "running" | "ok" | "warning" | "error" | "blocked";
type Mode = "simple" | "pro";

type StageId = "spec" | "compile" | "scan" | "explain" | "gate" | "exec";

type ScanDedupMode = "none" | "best_score" | "latest";
type ScanFilterState = {
  minScore: number; // score >=
  direction: "all" | "long" | "short";
  recencyDays: number; // 0=不限；>0 只看最近N天触发
  dedup: ScanDedupMode; // 同品种同周期去重
};

type StageMeta = {
  status: StageStatus;
  version?: string;
  startedAt?: number;
  finishedAt?: number;
  durationMs?: number;
  message?: string;
};

type PipelineState = {
  mode: Mode;
  activeStage: StageId;
  stages: Record<StageId, StageMeta>;

  // Inputs
  prompt: string;
  source: "active" | "watchlist" | "both";
  timeframesText: string; // e.g. "M30,H1"
  lookbackHours: number;

  // Artifacts
  parseResult?: any;
  strategySpec?: any;
  specText: string; // editable JSON view
  specJsonError?: string | null;
  specValidation?: any; // {status, validation_errors[], defaults_applied[], normalized_spec}

  compileResult?: any;
  dslText?: string;

  scanResult?: any;
  scanItems?: any[];
  scanFilters: ScanFilterState;
  selectedIndex: number;
  confirmedKeys: string[]; // 简洁模式：用户手动确认的候选（用于后续 Gate）
  scanJobId?: string | null;
  scanJob?: any | null;

  // UI
  err?: string | null;
};

const stageOrder: StageId[] = ["spec", "compile", "scan", "explain", "gate", "exec"];
const stageTitle: Record<StageId, string> = {
  spec: "StrategySpec",
  compile: "DSL 编译",
  scan: "扫描 EvidencePack",
  explain: "解释/落图",
  gate: "决策/风控",
  exec: "执行/监控",
};

function nowMs() {
  return Date.now();
}

function fmtTime(ts?: number) {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString();
  } catch {
    return "";
  }
}

function fmtDur(ms?: number) {
  if (ms == null) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function statusColor(s: StageStatus) {
  if (s === "ok") return "bg-emerald-500";
  if (s === "warning") return "bg-amber-500";
  if (s === "error") return "bg-red-500";
  if (s === "running") return "bg-sky-500";
  if (s === "blocked") return "bg-zinc-500";
  return "bg-zinc-600";
}

type Action =
  | { type: "setMode"; mode: Mode }
  | { type: "setActiveStage"; stage: StageId }
  | { type: "setField"; key: keyof PipelineState; value: any }
  | { type: "stageStart"; stage: StageId; message?: string }
  | { type: "stageFinish"; stage: StageId; status: StageStatus; message?: string; version?: string }
  | { type: "setError"; err: string | null }
  | { type: "setParse"; parseResult: any }
  | { type: "setStrategySpec"; strategySpec: any; specText: string }
  | { type: "setSpecValidation"; specValidation: any }
  | { type: "setCompile"; compileResult: any; dslText: string }
  | { type: "setScan"; scanResult: any; scanItems: any[] }
  | { type: "setScanJob"; scanJobId: string | null; scanJob: any | null }
  | { type: "setScanFilter"; key: keyof ScanFilterState; value: any }
  | { type: "selectIndex"; idx: number }
  | { type: "toggleConfirm"; key: string };

const initialState: PipelineState = {
  mode: "simple",
  activeStage: "spec",
  stages: {
    spec: { status: "draft", version: "1.0" },
    compile: { status: "idle", version: "1.0" },
    scan: { status: "idle", version: "1.0" },
    explain: { status: "idle" },
    gate: { status: "idle" },
    exec: { status: "idle" },
  },

  prompt: "找：收盘价突破近48根最高/最低（MVP）",
  source: "both",
  timeframesText: "M30",
  lookbackHours: 24,

  specText: "",
  scanFilters: { minScore: 0, direction: "all", recencyDays: 0, dedup: "none" },
  selectedIndex: 0,
  confirmedKeys: [],
  scanJobId: null,
  scanJob: null,
  err: null,
};

function reducer(state: PipelineState, action: Action): PipelineState {
  switch (action.type) {
    case "setMode":
      return { ...state, mode: action.mode };
    case "setActiveStage":
      return { ...state, activeStage: action.stage };
    case "setField":
      return { ...state, [action.key]: action.value };
    case "setError":
      return { ...state, err: action.err };
    case "stageStart": {
      const startedAt = nowMs();
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: { ...state.stages[action.stage], status: "running", startedAt, finishedAt: undefined, durationMs: undefined, message: action.message || "" },
        },
      };
    }
    case "stageFinish": {
      const st = state.stages[action.stage];
      const finishedAt = nowMs();
      const durationMs = st.startedAt ? finishedAt - st.startedAt : undefined;
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: { ...st, status: action.status, finishedAt, durationMs, message: action.message ?? st.message, version: action.version ?? st.version },
        },
      };
    }
    case "setParse":
      return { ...state, parseResult: action.parseResult };
    case "setStrategySpec":
      return { ...state, strategySpec: action.strategySpec, specText: action.specText, specJsonError: null };
    case "setSpecValidation":
      return { ...state, specValidation: action.specValidation };
    case "setCompile":
      return { ...state, compileResult: action.compileResult, dslText: action.dslText };
    case "setScan":
      return { ...state, scanResult: action.scanResult, scanItems: action.scanItems, selectedIndex: 0, confirmedKeys: [] };
    case "setScanJob":
      return { ...state, scanJobId: action.scanJobId, scanJob: action.scanJob };
    case "setScanFilter":
      return { ...state, scanFilters: { ...(state.scanFilters || (initialState.scanFilters as any)), [action.key]: action.value } };
    case "selectIndex":
      return { ...state, selectedIndex: action.idx };
    case "toggleConfirm": {
      const k = String(action.key || "");
      if (!k) return state;
      const set = new Set(state.confirmedKeys || []);
      if (set.has(k)) set.delete(k);
      else set.add(k);
      const confirmedKeys = Array.from(set);
      // 简单 Gate：只要确认>=1条，就把 gate 标为 ok（后续会替换为真正风控面板）
      const gateStatus: StageStatus = confirmedKeys.length ? "ok" : "idle";
      return {
        ...state,
        confirmedKeys,
        stages: {
          ...state.stages,
          gate: { ...state.stages.gate, status: gateStatus, message: confirmedKeys.length ? `已手动确认 ${confirmedKeys.length} 条候选` : "" },
        },
      };
    }
    default:
      return state;
  }
}

function tryParseJson(text: string): { ok: true; value: any } | { ok: false; error: string } {
  try {
    const v = JSON.parse(text);
    return { ok: true, value: v };
  } catch (e: any) {
    return { ok: false, error: e?.message || "JSON 解析失败" };
  }
}

function downloadText(filename: string, text: string, mime = "text/plain;charset=utf-8") {
  try {
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  } catch {}
}

function safeJson(v: any) {
  try {
    return JSON.stringify(v ?? null, null, 2);
  } catch {
    return "";
  }
}

function Modal(props: { open: boolean; title: string; onClose: () => void; children: React.ReactNode }) {
  if (!props.open) return null;
  return (
    <div className="fixed inset-0 z-[1000] bg-black/60 flex items-center justify-center p-4">
      <div className="w-full max-w-4xl bg-[#0b0f14] border border-white/10 rounded-lg overflow-hidden">
        <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between">
          <div className="text-sm font-semibold">{props.title}</div>
          <button className="text-xs px-2 py-1 rounded border border-white/10 hover:bg-white/5" onClick={props.onClose}>
            关闭
          </button>
        </div>
        <div className="p-3 max-h-[70vh] overflow-auto">{props.children}</div>
      </div>
    </div>
  );
}

function StageCard(props: { title: string; active: boolean; onClick: () => void; meta: StageMeta }) {
  const { meta } = props;
  return (
    <button
      className={[
        // 3x2 stepper：压缩高度，尽量把空间留给下方编辑区
        "min-w-0 text-left border rounded-lg px-2 py-1.5 hover:bg-white/5",
        props.active ? "border-emerald-400/60 bg-white/[0.03]" : "border-white/10",
      ].join(" ")}
      onClick={props.onClick}
      title={meta.message || ""}
    >
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2 h-2 rounded-full ${statusColor(meta.status)}`} />
        <div className="text-[11px] font-semibold truncate">{props.title}</div>
      </div>
      <div className="text-[10px] text-gray-500 mt-0.5 truncate">
        {meta.status === "running" ? "运行中" : meta.version ? `v${meta.version}` : "—"}
        {meta.durationMs != null ? ` · ${fmtDur(meta.durationMs)}` : ""}
      </div>
    </button>
  );
}

export function PipelineWorkbenchPanel(props: { onExecuteActions: (actions: any[]) => Promise<string[]> | string[] }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [modal, setModal] = useState<{ title: string; content: string } | null>(null);
  const specTextareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const lastSpecRef = React.useRef<any>(null);
  // 兼容 Web（走 Next rewrite）与 Electron/file（直连后端）
  const apiUrl = (path: string) => `${getBaseUrl()}${path}`;
  const [annotation, setAnnotation] = useState<{
    loading: boolean;
    err: string | null;
    candidate?: { symbol: string; timeframe: string; trigger_time: number; rule_id: string } | null;
    active_version: number | null;
    versions: any[];
    selected_version: number | null;
    notesText: string;
    objectsText: string;
  }>({ loading: false, err: null, candidate: null, active_version: null, versions: [], selected_version: null, notesText: "", objectsText: "[]" });
  const [gate, setGate] = useState<{
    loading: boolean;
    err: string | null;
    candidate?: { symbol: string; timeframe: string; trigger_time: number; rule_id: string } | null;
    active_version: number | null;
    versions: any[];
    selected_version: number | null;
    decisionText: string;
    tradePlanText: string;
  }>({ loading: false, err: null, candidate: null, active_version: null, versions: [], selected_version: null, decisionText: "{}", tradePlanText: "{}" });

  useEffect(() => {
    try {
      const raw = localStorage.getItem("awesome_chart_last_strategy_spec_v1");
      if (raw) lastSpecRef.current = JSON.parse(raw);
    } catch {}
  }, []);

  const timeframes = useMemo(() => state.timeframesText.split(",").map((s) => s.trim()).filter(Boolean), [state.timeframesText]);

  // 当 parseResult 更新后，自动填充 Spec 编辑器
  useEffect(() => {
    if (!state.parseResult?.strategy_spec) return;
    const txt = JSON.stringify(state.parseResult.strategy_spec, null, 2);
    if (!state.specText) dispatch({ type: "setStrategySpec", strategySpec: state.parseResult.strategy_spec, specText: txt });
  }, [state.parseResult, state.specText]);

  const runParse = async () => {
    dispatch({ type: "setError", err: null });
    dispatch({ type: "stageStart", stage: "spec", message: "解析 StrategySpec…" });
    dispatch({ type: "setActiveStage", stage: "spec" });
    try {
      const r = await fetch(apiUrl("/api/strategy/parse"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: state.prompt, source: state.source, timeframes, lookback_hours: state.lookbackHours }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      dispatch({ type: "setParse", parseResult: j });
      dispatch({ type: "setSpecValidation", specValidation: null });

      const status: StageStatus = j?.parse_meta?.status === "ok" ? "ok" : j?.parse_meta?.status === "unsupported" ? "error" : "warning";
      const msg =
        j?.parse_meta?.status === "ok"
          ? "已生成并校验 StrategySpec"
          : j?.parse_meta?.status === "unsupported"
            ? "不支持：请调整策略描述或降级"
            : "需要澄清/修复：请检查字段与默认值";
      dispatch({ type: "stageFinish", stage: "spec", status, message: msg, version: String(j?.strategy_spec?.spec_version || "1.0") });

      if (j?.strategy_spec) {
        const spec = j.strategy_spec;
        const specText = JSON.stringify(spec, null, 2);
        dispatch({ type: "setStrategySpec", strategySpec: spec, specText });
        // Stage1 联动增强：生成 Spec 后自动触发一次校验（并把“默认值来源”标成 template_default）
        try {
          const r2 = await fetch(apiUrl("/api/strategy/validate"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ strategy_spec: spec, prev_spec: lastSpecRef.current, default_source: "template_default" }),
          });
          const j2 = await r2.json().catch(() => ({}));
          if (r2.ok && j2?.ok) {
            dispatch({ type: "setSpecValidation", specValidation: j2 });
          }
        } catch {}
      }
    } catch (e: any) {
      dispatch({ type: "setError", err: e?.message || "解析失败" });
      dispatch({ type: "stageFinish", stage: "spec", status: "error", message: e?.message || "解析失败" });
    }
  };

  const runValidateSpec = async () => {
    dispatch({ type: "setError", err: null });
    dispatch({ type: "stageStart", stage: "spec", message: "校验 StrategySpec…" });
    dispatch({ type: "setActiveStage", stage: "spec" });
    try {
      const parsed = tryParseJson(state.specText || "");
      if (!parsed.ok) {
        dispatch({ type: "setField", key: "specJsonError", value: parsed.error });
        throw new Error(`StrategySpec JSON 无效：${parsed.error}`);
      }
      const r = await fetch(apiUrl("/api/strategy/validate"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // 手动校验：默认值来源按 system_default；并允许从“上次沿用”补默认
        body: JSON.stringify({ strategy_spec: parsed.value, prev_spec: lastSpecRef.current, default_source: "system_default" }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      dispatch({ type: "setSpecValidation", specValidation: j });
      const st = String(j?.status || "ok");
      const status: StageStatus = st === "error" ? "error" : st === "warning" ? "warning" : "ok";
      const errs = Array.isArray(j?.validation_errors) ? j.validation_errors : [];
      const msg = status === "ok" ? "Spec 校验通过" : status === "warning" ? `Spec 有警告（${errs.length}）` : `Spec 需修复（${errs.length}）`;
      dispatch({ type: "stageFinish", stage: "spec", status, message: msg });
      // 记住本次有效 spec，后续校验/生成可沿用默认
      try {
        localStorage.setItem("awesome_chart_last_strategy_spec_v1", JSON.stringify(parsed.value));
        lastSpecRef.current = parsed.value;
      } catch {}
    } catch (e: any) {
      dispatch({ type: "setError", err: e?.message || "校验失败" });
      dispatch({ type: "stageFinish", stage: "spec", status: "error", message: e?.message || "校验失败" });
    }
  };

  const jumpToPath = (path: string) => {
    const seg = String(path || "").split(".").filter(Boolean).slice(-1)[0];
    if (!seg) return;
    const el = specTextareaRef.current;
    if (!el) return;
    const text = el.value || "";
    const idx = text.indexOf(`"${seg}"`);
    if (idx >= 0) {
      el.focus();
      el.setSelectionRange(idx, Math.min(text.length, idx + seg.length + 2));
    } else {
      el.focus();
    }
  };

  const applyNormalizedSpec = () => {
    const ns = state.specValidation?.normalized_spec;
    if (!ns) return;
    const txt = JSON.stringify(ns, null, 2);
    dispatch({ type: "setStrategySpec", strategySpec: ns, specText: txt });
  };

  const runCompile = async () => {
    dispatch({ type: "setError", err: null });
    dispatch({ type: "stageStart", stage: "compile", message: "编译 DSL…" });
    dispatch({ type: "setActiveStage", stage: "compile" });
    try {
      const parsed = tryParseJson(state.specText || "");
      if (!parsed.ok) {
        dispatch({ type: "setField", key: "specJsonError", value: parsed.error });
        throw new Error(`StrategySpec JSON 无效：${parsed.error}`);
      }
      const spec = parsed.value;
      dispatch({ type: "setStrategySpec", strategySpec: spec, specText: state.specText });

      const r = await fetch(apiUrl("/api/strategy/compile"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy_spec: spec }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      dispatch({ type: "setCompile", compileResult: j, dslText: String(j?.dsl_text || "") });
      const repStatus = String(j?.report?.status || "ok");
      const status: StageStatus = repStatus === "warning" ? "warning" : repStatus === "error" ? "error" : "ok";
      const warnCnt = Array.isArray(j?.report?.warnings) ? j.report.warnings.length : 0;
      const errCnt = Array.isArray(j?.report?.errors) ? j.report.errors.length : 0;
      const msg = status === "ok" ? "编译成功" : status === "warning" ? `编译成功（警告 ${warnCnt}）` : `编译失败（错误 ${errCnt}）`;
      dispatch({ type: "stageFinish", stage: "compile", status, message: msg, version: String(j?.dsl_version || "1.0") });
    } catch (e: any) {
      dispatch({ type: "setError", err: e?.message || "编译失败" });
      dispatch({ type: "stageFinish", stage: "compile", status: "error", message: e?.message || "编译失败" });
    }
  };

  const runScan = async () => {
    dispatch({ type: "setError", err: null });
    dispatch({ type: "stageStart", stage: "scan", message: "扫描中…" });
    dispatch({ type: "setActiveStage", stage: "scan" });
    try {
      const parsed = tryParseJson(state.specText || "");
      if (!parsed.ok) {
        dispatch({ type: "setField", key: "specJsonError", value: parsed.error });
        throw new Error(`StrategySpec JSON 无效：${parsed.error}`);
      }
      const spec = parsed.value;
      dispatch({ type: "setStrategySpec", strategySpec: spec, specText: state.specText });

      const r = await fetch(apiUrl("/api/strategy/scan/run"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy_spec: spec }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      const jid = String(j?.job_id || "");
      if (!jid) throw new Error("启动扫描任务失败：job_id 缺失");
      dispatch({ type: "setScanJob", scanJobId: jid, scanJob: { status: "running", progress: 0, message: "" } });
      dispatch({ type: "stageStart", stage: "scan", message: "扫描任务已启动…" });
    } catch (e: any) {
      dispatch({ type: "setError", err: e?.message || "扫描失败" });
      dispatch({ type: "stageFinish", stage: "scan", status: "error", message: e?.message || "扫描失败" });
    }
  };

  // Stage3 轮询扫描任务状态（进度/完成/取消）
  useEffect(() => {
    const jid = state.scanJobId;
    if (!jid) return;
    let alive = true;
    const t = setInterval(async () => {
      try {
        const r = await fetch(apiUrl(`/api/strategy/scan/status/${jid}`));
        const j = await r.json().catch(() => ({}));
        if (!alive) return;
        const job = j?.job || null;
        dispatch({ type: "setScanJob", scanJobId: jid, scanJob: job });
        const st = String(job?.status || "");
        if (st && st !== "running") {
          clearInterval(t);
          const res = job?.result || null;
          if (st === "done" && res) {
            const items = Array.isArray(res?.items) ? res.items : [];
            dispatch({ type: "setScan", scanResult: res, scanItems: items });
            dispatch({
              type: "stageFinish",
              stage: "scan",
              status: items.length ? "ok" : "warning",
              message: items.length ? `完成：候选 ${items.length}` : "完成：0 候选（可尝试换周期/增大回看范围）",
              version: String(res?.dsl_version || "1.0"),
            });
          } else {
            const msg = String(job?.error || job?.message || "扫描失败/已取消");
            dispatch({ type: "stageFinish", stage: "scan", status: "error", message: msg });
          }
          // 结束后清理 jobId（避免重复轮询）
          dispatch({ type: "setScanJob", scanJobId: null, scanJob: job });
        }
      } catch {}
    }, 900);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [state.scanJobId]);

  const runAll = async () => {
    await runParse();
    // parse 不 ok 就不继续（作为 gate）
    const st = state.parseResult?.parse_meta?.status;
    // state.parseResult 在 runParse 内更新是异步的；这里用“文本是否有 spec”作为继续条件
    // 更严格可以把 runParse 返回值结构化，这里先保持简洁。
    if (!state.specText) return;
    await runCompile();
    await runScan();
  };

  const filteredScanItems = useMemo(() => {
    const items = Array.isArray(state.scanItems) ? state.scanItems : [];
    const f = state.scanFilters || (initialState.scanFilters as any);
    let out = items.slice();

    const minScore = Number(f.minScore || 0);
    if (Number.isFinite(minScore) && minScore > 0) out = out.filter((it: any) => Number(it?.score || 0) >= minScore);

    const dir = String(f.direction || "all");
    if (dir === "long" || dir === "short") {
      out = out.filter((it: any) => String(it?.evidence_pack?.facts?.direction || "") === dir);
    }

    const recencyDays = Number(f.recencyDays || 0);
    if (Number.isFinite(recencyDays) && recencyDays > 0) {
      const nowSec = Math.floor(Date.now() / 1000);
      const minT = nowSec - Math.floor(recencyDays * 86400);
      out = out.filter((it: any) => Number(it?.trigger_time || it?.evidence_pack?.trigger_time || 0) >= minT);
    }

    const dedup = String(f.dedup || "none");
    if (dedup === "best_score" || dedup === "latest") {
      const m = new Map<string, any>();
      for (const it of out) {
        const key = `${String(it?.symbol || "")}|${String(it?.timeframe || "")}`;
        const prev = m.get(key);
        if (!prev) {
          m.set(key, it);
          continue;
        }
        if (dedup === "best_score") {
          if (Number(it?.score || 0) > Number(prev?.score || 0)) m.set(key, it);
        } else {
          const t1 = Number(it?.trigger_time || 0);
          const t0 = Number(prev?.trigger_time || 0);
          if (t1 > t0) m.set(key, it);
        }
      }
      out = Array.from(m.values());
    }

    out.sort((a: any, b: any) => Number(b?.score || 0) - Number(a?.score || 0));
    return out;
  }, [state.scanItems, state.scanFilters]);

  useEffect(() => {
    // 筛选条件变化后，避免 selectedIndex 指向越界导致 detail 空白
    if ((filteredScanItems?.length || 0) === 0) {
      if (state.selectedIndex !== 0) dispatch({ type: "selectIndex", idx: 0 });
      return;
    }
    if (state.selectedIndex >= filteredScanItems.length) dispatch({ type: "selectIndex", idx: 0 });
  }, [filteredScanItems.length]);

  const selected = filteredScanItems?.[state.selectedIndex] || null;
  const specParsed = state.specText ? tryParseJson(state.specText) : null;
  const selectedKey = selected ? `${selected.symbol}|${selected.timeframe}|${selected.trigger_time || ""}` : "";
  const isConfirmed = selectedKey ? (state.confirmedKeys || []).includes(selectedKey) : false;

  const selectedCandidateMeta = useMemo(() => {
    if (!selected) return null;
    const symbol = String(selected.symbol || "").trim();
    const timeframe = String(selected.timeframe || "").trim().toUpperCase();
    const trigger_time = Number(selected.trigger_time || selected?.evidence_pack?.trigger_time || 0);
    const rule_id = String(selected?.evidence_pack?.rule_id || "unknown");
    if (!symbol || !timeframe || !Number.isFinite(trigger_time) || trigger_time <= 0) return null;
    return { symbol, timeframe, trigger_time: Math.floor(trigger_time), rule_id };
  }, [selected]);

  const loadGateDecisions = async (meta = selectedCandidateMeta) => {
    if (!meta) return;
    setGate((s) => ({ ...s, loading: true, err: null, candidate: meta }));
    try {
      const r = await fetch(apiUrl("/api/strategy/gate/list"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(meta),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      const versions = Array.isArray(j?.versions) ? j.versions : [];
      const active_version = j?.active_version != null ? Number(j.active_version) : null;
      const pick = active_version != null ? versions.find((v: any) => Number(v?.version) === active_version) : versions[0] || null;
      setGate((s) => ({
        ...s,
        loading: false,
        candidate: meta,
        versions,
        active_version,
        selected_version: pick ? Number(pick.version) : null,
        decisionText: JSON.stringify(pick?.decision || {}, null, 2),
        tradePlanText: JSON.stringify(pick?.trade_plan || {}, null, 2),
      }));
    } catch (e: any) {
      setGate((s) => ({ ...s, loading: false, err: e?.message || "加载失败", versions: [], active_version: null, selected_version: null }));
    }
  };

  const applyGateVersionToEditor = (v: any) => {
    if (!v) return;
    setGate((s) => ({
      ...s,
      selected_version: Number(v?.version || 0) || null,
      decisionText: JSON.stringify(v?.decision || {}, null, 2),
      tradePlanText: JSON.stringify(v?.trade_plan || {}, null, 2),
    }));
  };

  const suggestGate = async () => {
    if (!selected?.evidence_pack) return;
    setGate((s) => ({ ...s, loading: true, err: null }));
    try {
      const r = await fetch(apiUrl("/api/strategy/gate/suggest"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ evidence_pack: selected.evidence_pack }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      setGate((s) => ({
        ...s,
        loading: false,
        decisionText: JSON.stringify(j?.decision || {}, null, 2),
        tradePlanText: JSON.stringify(j?.trade_plan || {}, null, 2),
      }));
    } catch (e: any) {
      setGate((s) => ({ ...s, loading: false, err: e?.message || "生成失败" }));
    }
  };

  const saveGateNewVersion = async () => {
    const meta = selectedCandidateMeta;
    if (!meta || !selected?.evidence_pack) return;
    let decision: any = {};
    let trade_plan: any = {};
    try {
      decision = JSON.parse(gate.decisionText || "{}");
    } catch (e: any) {
      setGate((s) => ({ ...s, err: `decision JSON 无效：${e?.message || ""}` }));
      return;
    }
    try {
      trade_plan = JSON.parse(gate.tradePlanText || "{}");
    } catch (e: any) {
      setGate((s) => ({ ...s, err: `trade_plan JSON 无效：${e?.message || ""}` }));
      return;
    }

    const payload = {
      ...meta,
      snapshot_id: String(selected?.evidence_pack?.snapshot_id || selected?.snapshot_id || ""),
      data_version: selected?.evidence_pack?.facts?.data_version || selected?.data_version || {},
      annotation_version: annotation.active_version,
      decision,
      trade_plan,
      set_active: true,
    };
    setGate((s) => ({ ...s, loading: true, err: null }));
    try {
      const r = await fetch(apiUrl("/api/strategy/gate/save"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      const versions = Array.isArray(j?.versions) ? j.versions : [];
      const active_version = j?.active_version != null ? Number(j.active_version) : null;
      const pick = active_version != null ? versions.find((v: any) => Number(v?.version) === active_version) : versions[0] || null;
      setGate((s) => ({
        ...s,
        loading: false,
        versions,
        active_version,
        selected_version: pick ? Number(pick.version) : null,
      }));
    } catch (e: any) {
      setGate((s) => ({ ...s, loading: false, err: e?.message || "保存失败" }));
    }
  };

  const setActiveGate = async (version: number) => {
    const meta = selectedCandidateMeta;
    if (!meta) return;
    setGate((s) => ({ ...s, loading: true, err: null }));
    try {
      const r = await fetch(apiUrl("/api/strategy/gate/set_active"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...meta, version }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      const versions = Array.isArray(j?.versions) ? j.versions : [];
      const active_version = j?.active_version != null ? Number(j.active_version) : null;
      setGate((s) => ({ ...s, loading: false, versions, active_version }));
    } catch (e: any) {
      setGate((s) => ({ ...s, loading: false, err: e?.message || "设置失败" }));
    }
  };

  const setDecisionStatus = (status: string) => {
    try {
      const j = JSON.parse(gate.decisionText || "{}");
      j.status = status;
      setGate((s) => ({ ...s, decisionText: JSON.stringify(j, null, 2) }));
    } catch {
      // ignore
    }
  };

  const loadAnnotations = async (meta = selectedCandidateMeta) => {
    if (!meta) return;
    setAnnotation((s) => ({ ...s, loading: true, err: null, candidate: meta }));
    try {
      const r = await fetch(apiUrl("/api/strategy/annotation/list"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(meta),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      const versions = Array.isArray(j?.versions) ? j.versions : [];
      const active_version = j?.active_version != null ? Number(j.active_version) : null;
      const pick = active_version != null ? versions.find((v: any) => Number(v?.version) === active_version) : versions[0] || null;
      const ann = pick?.annotation || {};
      const notesText = String(ann?.notes || "");
      const objectsText = JSON.stringify(Array.isArray(ann?.objects) ? ann.objects : [], null, 2);
      setAnnotation((s) => ({
        ...s,
        loading: false,
        candidate: meta,
        versions,
        active_version,
        selected_version: pick ? Number(pick.version) : null,
        notesText,
        objectsText,
      }));
    } catch (e: any) {
      setAnnotation((s) => ({ ...s, loading: false, err: e?.message || "加载失败", versions: [], active_version: null, selected_version: null }));
    }
  };

  const initAnnotationFromEvidence = async () => {
    const meta = selectedCandidateMeta;
    if (!meta || !selected?.evidence_pack) return;
    const objects = (selected.evidence_pack?.draw_plan?.objects && Array.isArray(selected.evidence_pack.draw_plan.objects)) ? selected.evidence_pack.draw_plan.objects : (Array.isArray(selected.draw_objects) ? selected.draw_objects : []);
    const payload = {
      ...meta,
      snapshot_id: String(selected?.evidence_pack?.snapshot_id || selected?.snapshot_id || ""),
      data_version: selected?.evidence_pack?.facts?.data_version || selected?.data_version || {},
      evidence_pack: selected.evidence_pack,
      annotation: { notes: "", objects },
      set_active: true,
    };
    setAnnotation((s) => ({ ...s, loading: true, err: null }));
    try {
      const r = await fetch(apiUrl("/api/strategy/annotation/save"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      // 复用 list 响应结构
      const versions = Array.isArray(j?.versions) ? j.versions : [];
      const active_version = j?.active_version != null ? Number(j.active_version) : null;
      const pick = active_version != null ? versions.find((v: any) => Number(v?.version) === active_version) : versions[0] || null;
      const ann = pick?.annotation || {};
      setAnnotation((s) => ({
        ...s,
        loading: false,
        versions,
        active_version,
        selected_version: pick ? Number(pick.version) : null,
        notesText: String(ann?.notes || ""),
        objectsText: JSON.stringify(Array.isArray(ann?.objects) ? ann.objects : [], null, 2),
      }));
    } catch (e: any) {
      setAnnotation((s) => ({ ...s, loading: false, err: e?.message || "初始化失败" }));
    }
  };

  const saveAnnotationNewVersion = async () => {
    const meta = selectedCandidateMeta;
    if (!meta || !selected?.evidence_pack) return;
    let objects: any[] = [];
    try {
      const v = JSON.parse(annotation.objectsText || "[]");
      objects = Array.isArray(v) ? v : [];
    } catch (e: any) {
      setAnnotation((s) => ({ ...s, err: `objects JSON 无效：${e?.message || ""}` }));
      return;
    }
    const payload = {
      ...meta,
      snapshot_id: String(selected?.evidence_pack?.snapshot_id || selected?.snapshot_id || ""),
      data_version: selected?.evidence_pack?.facts?.data_version || selected?.data_version || {},
      evidence_pack: selected.evidence_pack,
      annotation: { notes: String(annotation.notesText || ""), objects },
      set_active: true,
    };
    setAnnotation((s) => ({ ...s, loading: true, err: null }));
    try {
      const r = await fetch(apiUrl("/api/strategy/annotation/save"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      const versions = Array.isArray(j?.versions) ? j.versions : [];
      const active_version = j?.active_version != null ? Number(j.active_version) : null;
      const pick = active_version != null ? versions.find((v: any) => Number(v?.version) === active_version) : versions[0] || null;
      setAnnotation((s) => ({ ...s, loading: false, versions, active_version, selected_version: pick ? Number(pick.version) : null }));
    } catch (e: any) {
      setAnnotation((s) => ({ ...s, loading: false, err: e?.message || "保存失败" }));
    }
  };

  const setActiveAnnotation = async (version: number) => {
    const meta = selectedCandidateMeta;
    if (!meta) return;
    setAnnotation((s) => ({ ...s, loading: true, err: null }));
    try {
      const r = await fetch(apiUrl("/api/strategy/annotation/set_active"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...meta, version }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      const versions = Array.isArray(j?.versions) ? j.versions : [];
      const active_version = j?.active_version != null ? Number(j.active_version) : null;
      setAnnotation((s) => ({ ...s, loading: false, versions, active_version }));
    } catch (e: any) {
      setAnnotation((s) => ({ ...s, loading: false, err: e?.message || "设置失败" }));
    }
  };

  const applyVersionToEditor = (v: any) => {
    if (!v) return;
    const ann = v?.annotation || {};
    setAnnotation((s) => ({
      ...s,
      selected_version: Number(v?.version || 0) || null,
      notesText: String(ann?.notes || ""),
      objectsText: JSON.stringify(Array.isArray(ann?.objects) ? ann.objects : [], null, 2),
    }));
  };

  const drawAnnotation = async () => {
    if (!selected) return;
    let objs: any[] = [];
    try {
      const v = JSON.parse(annotation.objectsText || "[]");
      objs = Array.isArray(v) ? v : [];
    } catch (e: any) {
      setAnnotation((s) => ({ ...s, err: `objects JSON 无效：${e?.message || ""}` }));
      return;
    }
    const actions: any[] = [
      { type: "chart_set_symbol", symbol: selected.symbol },
      { type: "chart_set_timeframe", timeframe: selected.timeframe },
      { type: "chart_clear_drawings" },
      { type: "chart_clear_markers" },
      { type: "chart_set_range", bars: 2000 },
    ];
    if (selected.trigger_time) actions.push({ type: "chart_scroll_to_time", time: selected.trigger_time });
    if (objs.length) actions.push({ type: "chart_draw", objects: objs });
    await props.onExecuteActions(actions);
  };

  useEffect(() => {
    // Stage4：当选中候选变化时自动加载 annotation 版本
    if (state.activeStage !== "explain") return;
    if (!selectedCandidateMeta) return;
    const prev = annotation.candidate;
    if (!prev || prev.symbol !== selectedCandidateMeta.symbol || prev.timeframe !== selectedCandidateMeta.timeframe || prev.trigger_time !== selectedCandidateMeta.trigger_time || prev.rule_id !== selectedCandidateMeta.rule_id) {
      loadAnnotations(selectedCandidateMeta);
    }
  }, [state.activeStage, selectedCandidateMeta?.symbol, selectedCandidateMeta?.timeframe, selectedCandidateMeta?.trigger_time, selectedCandidateMeta?.rule_id]);

  useEffect(() => {
    // Stage5：当选中候选变化时自动加载 Gate 版本
    if (state.activeStage !== "gate") return;
    if (!selectedCandidateMeta) return;
    const prev = gate.candidate;
    if (!prev || prev.symbol !== selectedCandidateMeta.symbol || prev.timeframe !== selectedCandidateMeta.timeframe || prev.trigger_time !== selectedCandidateMeta.trigger_time || prev.rule_id !== selectedCandidateMeta.rule_id) {
      loadGateDecisions(selectedCandidateMeta);
    }
  }, [state.activeStage, selectedCandidateMeta?.symbol, selectedCandidateMeta?.timeframe, selectedCandidateMeta?.trigger_time, selectedCandidateMeta?.rule_id]);

  // Stepper 状态灯联动（Stage4/5）
  useEffect(() => {
    // Stage4：只要存在 active annotation_version，就标绿（ok）
    if (!selectedCandidateMeta) return;
    const hasAny = (annotation.versions || []).length > 0;
    const hasActive = annotation.active_version != null;
    const status: StageStatus = hasActive ? "ok" : hasAny ? "warning" : "idle";
    const msg = hasActive ? `标注已激活 v${annotation.active_version}` : hasAny ? "有标注版本但未激活" : "尚无标注版本";
    dispatch({ type: "stageFinish", stage: "explain", status, message: msg });
  }, [selectedCandidateMeta?.symbol, selectedCandidateMeta?.timeframe, selectedCandidateMeta?.trigger_time, selectedCandidateMeta?.rule_id, annotation.active_version, (annotation.versions || []).length]);

  useEffect(() => {
    // Stage5：active 决策版本存在且 decision.status=pass => 绿灯
    if (!selectedCandidateMeta) return;
    const hasAny = (gate.versions || []).length > 0;
    const active = (gate.versions || []).find((v: any) => !!v?.is_active) || null;
    const decStatus = String(active?.decision?.status || "").toLowerCase();
    let status: StageStatus = "idle";
    let msg = "尚无决策版本";
    if (hasAny) {
      if (decStatus === "pass") {
        status = "ok";
        msg = `已通过（active v${active?.version}）`;
      } else if (decStatus === "reject") {
        status = "error";
        msg = `已拒绝（active v${active?.version}）`;
      } else if (decStatus === "downgrade") {
        status = "warning";
        msg = `已降级（active v${active?.version}）`;
      } else {
        status = "warning";
        msg = active ? `待复核（active v${active?.version}）` : "有决策版本但未激活";
      }
    }
    dispatch({ type: "stageFinish", stage: "gate", status, message: msg });
  }, [selectedCandidateMeta?.symbol, selectedCandidateMeta?.timeframe, selectedCandidateMeta?.trigger_time, selectedCandidateMeta?.rule_id, (gate.versions || []).length, gate.active_version]);

  return (
    <div className="h-full flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-gray-400">Pipeline 工作台</div>
          <div className="text-[11px] text-gray-500">StrategySpec → DSL/1.0 → EvidencePack（后续可接解释/风控/执行）</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className={`text-xs px-2 py-1 rounded border ${state.mode === "simple" ? "border-emerald-400/60 bg-white/[0.03]" : "border-white/10 hover:bg-white/5"}`}
            onClick={() => dispatch({ type: "setMode", mode: "simple" })}
          >
            简洁
          </button>
          <button
            className={`text-xs px-2 py-1 rounded border ${state.mode === "pro" ? "border-emerald-400/60 bg-white/[0.03]" : "border-white/10 hover:bg-white/5"}`}
            onClick={() => dispatch({ type: "setMode", mode: "pro" })}
          >
            专业
          </button>
        </div>
      </div>

      {/* Stepper */}
      {/* 3x2 栅格：上三下三 */}
      <div className="grid grid-cols-3 gap-2">
        {stageOrder.map((id) => (
          <StageCard key={id} title={stageTitle[id]} active={state.activeStage === id} onClick={() => dispatch({ type: "setActiveStage", stage: id })} meta={state.stages[id]} />
        ))}
      </div>

      {/* Actions */}
      <div className="border border-white/10 rounded p-2 flex flex-col gap-2">
        {/* 第一行：核心动作 + 状态信息（窄屏也不挤压） */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              className="h-8 px-3 text-xs"
              onClick={runAll}
              disabled={state.stages.spec.status === "running" || state.stages.compile.status === "running" || state.stages.scan.status === "running"}
            >
              一键跑通（Parse→Compile→Scan）
            </Button>
            <Button variant="outline" className="h-8 px-3 text-xs" onClick={runParse} disabled={state.stages.spec.status === "running"}>
              生成 Spec
            </Button>
            <Button variant="outline" className="h-8 px-3 text-xs" onClick={runCompile} disabled={state.stages.compile.status === "running"}>
              编译 DSL
            </Button>
            <Button variant="outline" className="h-8 px-3 text-xs" onClick={runScan} disabled={state.stages.scan.status === "running"}>
              扫描
            </Button>
            {state.stages.scan.status === "running" && state.scanJobId && (
              <Button
                variant="outline"
                className="h-8 px-3 text-xs border-red-400/40 text-red-300 hover:bg-red-500/10"
                onClick={async () => {
                  try {
                    await fetch(apiUrl(`/api/strategy/scan/cancel/${state.scanJobId}`), { method: "POST" });
                  } catch {}
                }}
                title="取消扫描"
              >
                取消
              </Button>
            )}
          </div>
          <div className="text-[11px] text-gray-500 text-right min-w-[120px]">
            {state.err ? <span className="text-red-400">{state.err}</span> : state.stages[state.activeStage].message || ""}
          </div>
        </div>

        {/* 第二行：专业模式工具栏（放到下面，避免窄屏挤压） */}
        {state.mode === "pro" && (
          <div className="flex items-center gap-2 flex-wrap">
            <button
              className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
              disabled={!state.specText}
              onClick={() => setModal({ title: "StrategySpec（JSON）", content: state.specText || "" })}
            >
              查看Spec
            </button>
            <button
              className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
              disabled={!state.specText}
              onClick={() => downloadText(`strategy_spec_v${state.stages.spec.version || "1.0"}.json`, state.specText || "", "application/json;charset=utf-8")}
            >
              下载Spec
            </button>
            <button
              className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
              disabled={!state.dslText}
              onClick={() => setModal({ title: "DSL/1.0", content: String(state.dslText || "") })}
            >
              查看DSL
            </button>
            <button
              className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
              disabled={!state.dslText}
              onClick={() => downloadText(`dsl_v${state.stages.compile.version || "1.0"}.txt`, String(state.dslText || ""))}
            >
              下载DSL
            </button>
            <button
              className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
              disabled={!state.compileResult?.report}
              onClick={() => setModal({ title: "CompilationReport（JSON）", content: safeJson(state.compileResult?.report || {}) })}
            >
              查看报告
            </button>
            <button
              className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
              disabled={!state.compileResult?.report}
              onClick={() => downloadText(`compilation_report_v${state.stages.compile.version || "1.0"}.json`, safeJson(state.compileResult?.report || {}), "application/json;charset=utf-8")}
            >
              下载报告
            </button>
            <button
              className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
              disabled={!filteredScanItems?.length}
              onClick={() => downloadText(`candidates_evidence.json`, safeJson(filteredScanItems || []), "application/json;charset=utf-8")}
            >
              下载候选
            </button>
          </div>
        )}
      </div>

      {/* Stage content */}
      <div className="flex-1 overflow-auto space-y-3">
        {/* Stage 1 */}
        {state.activeStage === "spec" && (
          <div className="border border-white/10 rounded p-2 space-y-2">
            <div className="text-xs text-gray-400">Stage 1 · StrategySpec（AI 生成 + 人可编辑）</div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-2">
                <div className="text-[11px] text-gray-500">自然语言策略（Prompt）</div>
                <textarea
                  className="w-full h-28 bg-transparent border border-white/10 rounded p-2 text-xs outline-none focus:border-emerald-400"
                  value={state.prompt}
                  onChange={(e) => dispatch({ type: "setField", key: "prompt", value: e.target.value })}
                />
                <div className="grid grid-cols-3 gap-2">
                  <select className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs" value={state.source} onChange={(e) => dispatch({ type: "setField", key: "source", value: e.target.value })}>
                    <option value="both">both</option>
                    <option value="active">active</option>
                    <option value="watchlist">watchlist</option>
                  </select>
                  <input className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs" value={state.timeframesText} onChange={(e) => dispatch({ type: "setField", key: "timeframesText", value: e.target.value })} placeholder="M15,M30,H1" />
                  <input className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs" type="number" value={state.lookbackHours} onChange={(e) => dispatch({ type: "setField", key: "lookbackHours", value: Number(e.target.value) })} />
                </div>
                {state.parseResult?.parse_meta && (
                  <div className="text-[11px] text-gray-500 whitespace-pre-wrap border border-white/10 rounded p-2">
                    parse_meta.status：{String(state.parseResult.parse_meta.status || "-")}
                    {state.parseResult.runtime?.symbols_count != null ? ` · symbols=${state.parseResult.runtime.symbols_count}` : ""}
                  </div>
                )}
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-[11px] text-gray-500">结构化 StrategySpec（JSON 视图 · 可编辑）</div>
                  <div className="flex gap-2">
                    <button
                      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      onClick={runValidateSpec}
                      disabled={!state.specText || state.stages.spec.status === "running"}
                      title="校验 schema + 显示默认值来源"
                    >
                      校验
                    </button>
                    <button
                      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      onClick={() => setModal({ title: "StrategySpec（JSON）", content: state.specText || "" })}
                      disabled={!state.specText}
                    >
                      查看
                    </button>
                  </div>
                </div>
                <textarea
                  ref={specTextareaRef as any}
                  className="w-full h-44 bg-transparent border border-white/10 rounded p-2 text-[11px] font-mono outline-none focus:border-emerald-400"
                  value={state.specText}
                  onChange={(e) => dispatch({ type: "setField", key: "specText", value: e.target.value })}
                  placeholder="点击“生成 Spec”后会自动填充。"
                />
                {state.specJsonError && <div className="text-[11px] text-red-400">JSON 错误：{state.specJsonError}</div>}
                {state.specValidation && (
                  <div className="border border-white/10 rounded p-2 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-[11px] text-gray-500">
                        校验状态：{String(state.specValidation.status || "-")}
                        {Array.isArray(state.specValidation.validation_errors) ? ` · issues ${state.specValidation.validation_errors.length}` : ""}
                      </div>
                      <div className="flex gap-2">
                        <button
                          className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                          onClick={applyNormalizedSpec}
                          disabled={!state.specValidation?.normalized_spec}
                          title="用 normalized_spec 覆盖当前编辑器内容（例如自动夹取后的参数）"
                        >
                          应用规范化
                        </button>
                        <button
                          className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                          onClick={() => downloadText("normalized_spec.json", safeJson(state.specValidation?.normalized_spec || {}), "application/json;charset=utf-8")}
                          disabled={!state.specValidation?.normalized_spec}
                        >
                          下载规范化
                        </button>
                      </div>
                    </div>
                    {Array.isArray(state.specValidation.validation_errors) && state.specValidation.validation_errors.length > 0 && (
                      <div className="space-y-1 max-h-28 overflow-auto">
                        {state.specValidation.validation_errors.map((e: any, i: number) => {
                          const sev = String(e?.severity || "error");
                          const c = sev === "warning" ? "text-amber-300" : "text-red-300";
                          return (
                            <button
                              key={i}
                              className={`w-full text-left text-[11px] ${c} hover:underline`}
                              onClick={() => jumpToPath(String(e?.path || ""))}
                              title="点击定位到 JSON 字段"
                            >
                              {String(e?.path || "")}：{String(e?.message || "")}
                            </button>
                          );
                        })}
                      </div>
                    )}
                    {Array.isArray(state.specValidation.defaults_applied) && state.specValidation.defaults_applied.length > 0 && (
                      <div className="space-y-1 max-h-24 overflow-auto">
                        <div className="text-[11px] text-gray-500">默认值来源：</div>
                        {state.specValidation.defaults_applied.map((d: any, i: number) => (
                          <div key={i} className="text-[11px] text-gray-400">
                            {String(d?.path || "")} ← {String(d?.source || "system_default")} = {safeJson(d?.value)}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                {state.mode === "pro" && (
                  <div className="text-[11px] text-gray-500">
                    当前校验：
                    {specParsed
                      ? specParsed.ok
                        ? <span className="text-emerald-400"> JSON 有效</span>
                        : <span className="text-red-400"> JSON 无效</span>
                      : "-"}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Stage 2 */}
        {state.activeStage === "compile" && (
          <div className="border border-white/10 rounded p-2 space-y-2">
            <div className="text-xs text-gray-400">Stage 2 · DSL/AST 编译（确定性）</div>
            {state.mode === "simple" ? (
              <div className="text-[11px] text-gray-500">
                简洁模式隐藏 DSL 细节。状态：{state.stages.compile.status === "ok" ? "编译成功" : state.stages.compile.status === "running" ? "编译中" : "尚未编译"}。
                <button className="ml-2 underline hover:text-gray-300" onClick={() => dispatch({ type: "setMode", mode: "pro" })}>
                  切到专业模式查看
                </button>
              </div>
            ) : (
              <>
                {state.compileResult?.report && (
                  <div className="border border-white/10 rounded p-2">
                    <div className="flex items-center justify-between">
                      <div className="text-[11px] text-gray-500">
                        编译报告：{String(state.compileResult.report.status || "-")}
                        {Array.isArray(state.compileResult.report.warnings) ? ` · warnings ${state.compileResult.report.warnings.length}` : ""}
                        {Array.isArray(state.compileResult.report.errors) ? ` · errors ${state.compileResult.report.errors.length}` : ""}
                      </div>
                      <div className="flex gap-2">
                        <button
                          className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                          onClick={() => setModal({ title: "CompilationReport（JSON）", content: safeJson(state.compileResult?.report || {}) })}
                        >
                          查看
                        </button>
                        <button
                          className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                          onClick={() => downloadText(`compilation_report_v${state.stages.compile.version || "1.0"}.json`, safeJson(state.compileResult?.report || {}), "application/json;charset=utf-8")}
                        >
                          下载
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <div className="text-[11px] text-gray-500">生成 DSL（只读）</div>
                  <div className="flex gap-2">
                    <button
                      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      onClick={() => setModal({ title: "DSL/1.0", content: String(state.dslText || "") })}
                      disabled={!state.dslText}
                    >
                      查看
                    </button>
                    <button
                      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      onClick={() => navigator.clipboard?.writeText(String(state.dslText || "")).catch(() => {})}
                      disabled={!state.dslText}
                    >
                      复制
                    </button>
                  </div>
                </div>
                <pre className="text-[11px] text-gray-300 whitespace-pre-wrap border border-white/10 rounded p-2 max-h-64 overflow-auto">
                  {state.dslText || "（尚未编译）"}
                </pre>
                <div className="text-[11px] text-gray-500">
                  提示：后续会在此处加入 CompilationReport（警告/不支持能力/默认值清单/规则摘要），并提供“回到 Spec 修复”的定位跳转。
                </div>
              </>
            )}
          </div>
        )}

        {/* Stage 3 */}
        {state.activeStage === "scan" && (
          <div className="border border-white/10 rounded p-2 space-y-2">
            <div className="text-xs text-gray-400">Stage 3 · 扫描 EvidencePack（确定性）</div>
            <div className="grid grid-cols-3 gap-2">
              {/* Filters */}
              <div className="border border-white/10 rounded p-2">
                <div className="text-[11px] text-gray-500 mb-2">筛选器（通用）</div>
                <div className="space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <div className="text-[11px] text-gray-500">最低 score</div>
                      <input
                        className="h-8 w-full bg-transparent border border-white/10 rounded px-2 text-xs"
                        type="number"
                        step="0.1"
                        value={Number(state.scanFilters?.minScore || 0)}
                        onChange={(e) => dispatch({ type: "setScanFilter", key: "minScore", value: Number(e.target.value) })}
                      />
                    </div>
                    <div className="space-y-1">
                      <div className="text-[11px] text-gray-500">方向</div>
                      <select
                        className="h-8 w-full bg-transparent border border-white/10 rounded px-2 text-xs"
                        value={String(state.scanFilters?.direction || "all")}
                        onChange={(e) => dispatch({ type: "setScanFilter", key: "direction", value: e.target.value })}
                      >
                        <option value="all">全部</option>
                        <option value="long">只看多</option>
                        <option value="short">只看空</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <div className="text-[11px] text-gray-500">新鲜度（天）</div>
                      <input
                        className="h-8 w-full bg-transparent border border-white/10 rounded px-2 text-xs"
                        type="number"
                        step="1"
                        min="0"
                        value={Number(state.scanFilters?.recencyDays || 0)}
                        onChange={(e) => dispatch({ type: "setScanFilter", key: "recencyDays", value: Number(e.target.value) })}
                        placeholder="0=不限"
                      />
                    </div>
                    <div className="space-y-1">
                      <div className="text-[11px] text-gray-500">去重</div>
                      <select
                        className="h-8 w-full bg-transparent border border-white/10 rounded px-2 text-xs"
                        value={String(state.scanFilters?.dedup || "none")}
                        onChange={(e) => dispatch({ type: "setScanFilter", key: "dedup", value: e.target.value })}
                      >
                        <option value="none">不去重</option>
                        <option value="best_score">同品种保留最高分</option>
                        <option value="latest">同品种保留最新</option>
                      </select>
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] text-gray-500">
                      显示 {filteredScanItems.length} / {(state.scanItems || []).length}
                    </div>
                    <button
                      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      onClick={() => dispatch({ type: "setField", key: "scanFilters", value: { minScore: 0, direction: "all", recencyDays: 0, dedup: "none" } })}
                      title="重置筛选"
                    >
                      重置
                    </button>
                  </div>
                </div>
                {state.scanJob && state.scanJob?.status === "running" && (
                  <div className="mt-2 text-[11px] text-gray-500">
                    进度：{Math.round(Number(state.scanJob.progress || 0) * 100)}% · {String(state.scanJob.message || "")}
                  </div>
                )}
              </div>

              {/* List */}
              <div className="border border-white/10 rounded p-2">
                <div className="text-[11px] text-gray-500 mb-2">候选列表</div>
                <div className="space-y-2 max-h-80 overflow-auto">
                  {(filteredScanItems || []).map((it: any, idx: number) => (
                    <button
                      key={idx}
                      className={[
                        "w-full text-left border rounded p-2 hover:bg-white/5",
                        idx === state.selectedIndex ? "border-emerald-400/60 bg-white/[0.03]" : "border-white/10",
                      ].join(" ")}
                      onClick={() => dispatch({ type: "selectIndex", idx })}
                    >
                      <div className="flex items-center justify-between">
                        <div className="text-xs flex items-center gap-2">
                          <span>{it.symbol} {it.timeframe}</span>
                          {(() => {
                            const dir = String(it?.evidence_pack?.facts?.direction || "");
                            if (dir === "long") return <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-400/20">多</span>;
                            if (dir === "short") return <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-300 border border-red-400/20">空</span>;
                            return null;
                          })()}
                        </div>
                        <div className="text-[11px] text-gray-500">score {Number(it.score || 0).toFixed(2)}</div>
                      </div>
                      <div className="text-[11px] text-gray-500 mt-1 line-clamp-2">{String(it.reason || "")}</div>
                    </button>
                  ))}
                  {(state.scanItems || []).length === 0 && <div className="text-xs text-gray-500">无候选（可尝试换周期/放宽条件/增大回看范围）</div>}
                  {(state.scanItems || []).length > 0 && filteredScanItems.length === 0 && <div className="text-xs text-gray-500">筛选后无候选（可调低 score/取消去重/放宽新鲜度）</div>}
                </div>
              </div>

              {/* Detail */}
              <div className="border border-white/10 rounded p-2">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[11px] text-gray-500">候选详情（EvidencePack）</div>
                  <div className="flex gap-2">
                    <Button
                      className="h-7 px-2 text-xs"
                      disabled={!selected}
                      onClick={async () => {
                        if (!selected) return;
                        const actions: any[] = [
                          { type: "chart_set_symbol", symbol: selected.symbol },
                          { type: "chart_set_timeframe", timeframe: selected.timeframe },
                          // 先清理旧标注，避免用户把不同候选的线混在一起
                          { type: "chart_clear_drawings" },
                          { type: "chart_clear_markers" },
                          // 拉更大范围的历史，确保 trigger_time 对应的K线已加载（否则 marker/box 会被映射到最老一根）
                          { type: "chart_set_range", bars: 2000 },
                        ];
                        if (selected.trigger_time) actions.push({ type: "chart_scroll_to_time", time: selected.trigger_time });
                        if (Array.isArray(selected.draw_objects) && selected.draw_objects.length) actions.push({ type: "chart_draw", objects: selected.draw_objects });
                        await props.onExecuteActions(actions);
                      }}
                    >
                      一键落图
                    </Button>
                    {state.mode === "simple" && (
                      <Button
                        variant={isConfirmed ? "outline" : "default"}
                        className="h-7 px-2 text-xs"
                        disabled={!selected}
                        onClick={() => {
                          if (!selected) return;
                          const k = `${selected.symbol}|${selected.timeframe}|${selected.trigger_time || ""}`;
                          dispatch({ type: "toggleConfirm", key: k });
                        }}
                      >
                        {isConfirmed ? "已确认" : "手动确认"}
                      </Button>
                    )}
                    {state.mode === "pro" && (
                      <button
                        className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                        disabled={!selected?.evidence_pack}
                        onClick={() => setModal({ title: "EvidencePack（JSON）", content: JSON.stringify(selected?.evidence_pack || {}, null, 2) })}
                      >
                        查看证据包
                      </button>
                    )}
                  </div>
                </div>
                {selected ? (
                  <div className="text-[11px] text-gray-400 whitespace-pre-wrap">
                    {selected.evidence_pack ? (
                      <>
                        <div>trigger_time：{String(selected.evidence_pack.trigger_time || selected.trigger_time || "-")}</div>
                        <div>direction：{String(selected.evidence_pack?.facts?.direction || "-")}</div>
                        <div>level：{String(selected.evidence_pack?.facts?.level || "-")}</div>
                        {state.mode === "pro" ? (
                          <>
                            <div>close：{String(selected.evidence_pack?.facts?.close || "-")}</div>
                            <div>atr14：{String(selected.evidence_pack?.facts?.atr14 || "-")}</div>
                          </>
                        ) : null}
                        <div className="mt-2 text-gray-500">说明：{String(selected.evidence_pack?.facts?.reason || selected.reason || "")}</div>
                      </>
                    ) : (
                      <div>（暂无 EvidencePack，后续会统一补齐）</div>
                    )}
                  </div>
                ) : (
                  <div className="text-xs text-gray-500">请选择一个候选</div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Stage 4/5/6 placeholders */}
        {state.activeStage === "explain" && (
          <div className="border border-white/10 rounded p-2 space-y-2">
            <div className="flex items-center justify-between">
              <div className="text-xs text-gray-400">Stage 4 · 解释/标注版本（annotation_version）</div>
              <div className="flex gap-2">
                <button
                  className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                  disabled={!selectedCandidateMeta || annotation.loading}
                  onClick={() => loadAnnotations()}
                >
                  刷新
                </button>
                <button
                  className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                  disabled={!selectedCandidateMeta || annotation.loading || !selected?.evidence_pack}
                  onClick={initAnnotationFromEvidence}
                  title="从 EvidencePack.draw_plan 初始化一个 v1（并设为当前 active）"
                >
                  初始化v1
                </button>
              </div>
            </div>

            {!selectedCandidateMeta ? (
              <div className="text-[11px] text-gray-500">请先在 Stage 3 选择一个候选。</div>
            ) : (
              <div className="grid grid-cols-3 gap-2">
                <div className="border border-white/10 rounded p-2 space-y-2">
                  <div className="text-[11px] text-gray-500">版本列表</div>
                  <div className="text-[11px] text-gray-500">
                    active：{annotation.active_version != null ? `v${annotation.active_version}` : "-"}
                  </div>
                  {annotation.err && <div className="text-[11px] text-red-400">{annotation.err}</div>}
                  <div className="space-y-1 max-h-56 overflow-auto">
                    {(annotation.versions || []).map((v: any) => (
                      <button
                        key={String(v?.version)}
                        className={[
                          "w-full text-left text-[11px] px-2 py-1 rounded border",
                          Number(v?.version) === annotation.selected_version ? "border-emerald-400/60 bg-white/[0.03]" : "border-white/10 hover:bg-white/5",
                        ].join(" ")}
                        onClick={() => applyVersionToEditor(v)}
                      >
                        v{Number(v?.version || 0)} {v?.is_active ? "（active）" : ""}
                      </button>
                    ))}
                    {(annotation.versions || []).length === 0 && <div className="text-[11px] text-gray-500">暂无标注版本（点“初始化v1”创建）</div>}
                  </div>
                  <div className="flex gap-2 flex-wrap pt-1">
                    <button
                      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      disabled={!annotation.selected_version || annotation.loading}
                      onClick={() => setActiveAnnotation(Number(annotation.selected_version))}
                    >
                      设为active
                    </button>
                    <button
                      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      disabled={!selected || annotation.loading}
                      onClick={drawAnnotation}
                    >
                      落图（标注）
                    </button>
                  </div>
                </div>

                <div className="border border-white/10 rounded p-2 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-[11px] text-gray-500">Notes（可编辑）</div>
                    <button
                      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      disabled={!selected?.evidence_pack || annotation.loading}
                      onClick={saveAnnotationNewVersion}
                      title="保存为新版本并设为 active"
                    >
                      保存新版本
                    </button>
                  </div>
                  <textarea
                    className="w-full h-40 bg-transparent border border-white/10 rounded p-2 text-[11px] outline-none focus:border-emerald-400"
                    value={annotation.notesText}
                    onChange={(e) => setAnnotation((s) => ({ ...s, notesText: e.target.value }))}
                    placeholder="写下你对该候选的解释/风险/计划（将随版本保存）"
                  />
                  <div className="text-[11px] text-gray-500">
                    该版本会绑定 snapshot_id/data_version，作为后续 Gate/复盘的审计依据。
                  </div>
                </div>

                <div className="border border-white/10 rounded p-2 space-y-2">
                  <div className="text-[11px] text-gray-500">Draw Objects（JSON · 可编辑）</div>
                  <textarea
                    className="w-full h-52 bg-transparent border border-white/10 rounded p-2 text-[11px] font-mono outline-none focus:border-emerald-400"
                    value={annotation.objectsText}
                    onChange={(e) => setAnnotation((s) => ({ ...s, objectsText: e.target.value }))}
                    placeholder='例如：[{"type":"hline","price":...}]'
                  />
                  <div className="flex gap-2 flex-wrap">
                    <button
                      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      onClick={() => setModal({ title: "annotation.objects（JSON）", content: annotation.objectsText || "[]" })}
                      disabled={!annotation.objectsText}
                    >
                      查看JSON
                    </button>
                    <button
                      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      onClick={() => downloadText("annotation_objects.json", annotation.objectsText || "[]", "application/json;charset=utf-8")}
                      disabled={!annotation.objectsText}
                    >
                      下载JSON
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
        {state.activeStage === "gate" && (
          <div className="border border-white/10 rounded p-2 space-y-2">
            <div className="text-xs text-gray-400">Stage 5 · 决策/风控（Gate）</div>
            {!selectedCandidateMeta ? (
              <div className="text-[11px] text-gray-500">请先在 Stage 3 选择一个候选。</div>
            ) : (
              <div className="grid grid-cols-3 gap-2">
                <div className="border border-white/10 rounded p-2 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-[11px] text-gray-500">决策版本（decision_version）</div>
                    <div className="flex gap-2">
                      <button className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5" onClick={() => loadGateDecisions()} disabled={gate.loading}>
                        刷新
                      </button>
                      <button className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5" onClick={suggestGate} disabled={gate.loading || !selected?.evidence_pack}>
                        生成计划
                      </button>
                    </div>
                  </div>

                  <div className="text-[11px] text-gray-500">active：{gate.active_version != null ? `v${gate.active_version}` : "-"}</div>
                  {gate.err && <div className="text-[11px] text-red-400">{gate.err}</div>}
                  <div className="space-y-1 max-h-56 overflow-auto">
                    {(gate.versions || []).map((v: any) => (
                      <button
                        key={String(v?.version)}
                        className={[
                          "w-full text-left text-[11px] px-2 py-1 rounded border",
                          Number(v?.version) === gate.selected_version ? "border-emerald-400/60 bg-white/[0.03]" : "border-white/10 hover:bg-white/5",
                        ].join(" ")}
                        onClick={() => applyGateVersionToEditor(v)}
                      >
                        v{Number(v?.version || 0)} {v?.is_active ? "（active）" : ""}
                      </button>
                    ))}
                    {(gate.versions || []).length === 0 && <div className="text-[11px] text-gray-500">暂无决策版本（点“生成计划”并保存）</div>}
                  </div>
                  <div className="flex gap-2 flex-wrap pt-1">
                    <button
                      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      disabled={!gate.selected_version || gate.loading}
                      onClick={() => setActiveGate(Number(gate.selected_version))}
                    >
                      设为active
                    </button>
                    <button className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5" disabled={gate.loading} onClick={saveGateNewVersion}>
                      保存新版本
                    </button>
                  </div>
                  <div className="flex gap-2 flex-wrap pt-1">
                    <button className="text-[11px] px-2 py-1 rounded border border-emerald-400/30 text-emerald-300 hover:bg-emerald-500/10" onClick={() => setDecisionStatus("pass")}>
                      通过
                    </button>
                    <button className="text-[11px] px-2 py-1 rounded border border-amber-400/30 text-amber-300 hover:bg-amber-500/10" onClick={() => setDecisionStatus("downgrade")}>
                      降级
                    </button>
                    <button className="text-[11px] px-2 py-1 rounded border border-red-400/30 text-red-300 hover:bg-red-500/10" onClick={() => setDecisionStatus("reject")}>
                      拒绝
                    </button>
                    <button className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5" onClick={() => setDecisionStatus("review")}>
                      复核
                    </button>
                  </div>
                </div>

                <div className="border border-white/10 rounded p-2 space-y-2">
                  <div className="text-[11px] text-gray-500">GateDecision（JSON）</div>
                  <textarea
                    className="w-full h-64 bg-transparent border border-white/10 rounded p-2 text-[11px] font-mono outline-none focus:border-emerald-400"
                    value={gate.decisionText}
                    onChange={(e) => setGate((s) => ({ ...s, decisionText: e.target.value }))}
                    placeholder='例如：{"status":"pass","reason":"..."}'
                  />
                  <div className="flex gap-2 flex-wrap">
                    <button className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5" onClick={() => setModal({ title: "GateDecision（JSON）", content: gate.decisionText || "{}" })}>
                      查看JSON
                    </button>
                    <button className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5" onClick={() => downloadText("gate_decision.json", gate.decisionText || "{}", "application/json;charset=utf-8")}>
                      下载JSON
                    </button>
                  </div>
                </div>

                <div className="border border-white/10 rounded p-2 space-y-2">
                  <div className="text-[11px] text-gray-500">TradePlan（JSON）</div>
                  <textarea
                    className="w-full h-64 bg-transparent border border-white/10 rounded p-2 text-[11px] font-mono outline-none focus:border-emerald-400"
                    value={gate.tradePlanText}
                    onChange={(e) => setGate((s) => ({ ...s, tradePlanText: e.target.value }))}
                    placeholder='例如：{"entry":...,"risk":...}'
                  />
                  <div className="flex gap-2 flex-wrap">
                    <button className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5" onClick={() => setModal({ title: "TradePlan（JSON）", content: gate.tradePlanText || "{}" })}>
                      查看JSON
                    </button>
                    <button className="text-[11px] px-2 py-1 rounded border border-white/10 hover:bg-white/5" onClick={() => downloadText("trade_plan.json", gate.tradePlanText || "{}", "application/json;charset=utf-8")}>
                      下载JSON
                    </button>
                  </div>
                  <div className="text-[11px] text-gray-500">
                    注：MVP 先生成“结构化可执行计划”，后续接多 agent 时会把 agent 输出汇总为新的决策版本。
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
        {state.activeStage === "exec" && (
          <div className="border border-white/10 rounded p-2 space-y-2">
            <div className="text-xs text-gray-400">Stage 6 · 执行/监控</div>
            <div className="text-[11px] text-gray-500">占位：后续加入交易状态机 timeline、回执、告警、复盘入口（snapshot+evidence+决策记录）。</div>
          </div>
        )}
      </div>

      <Modal open={!!modal} title={modal?.title || ""} onClose={() => setModal(null)}>
        <pre className="text-[11px] text-gray-200 whitespace-pre-wrap">{modal?.content || ""}</pre>
      </Modal>
    </div>
  );
}
