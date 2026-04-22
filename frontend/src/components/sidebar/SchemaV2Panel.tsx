"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { getBaseUrl } from "@/lib/api";

type Mode = "json" | "form";
type ValidateStatus = "ok" | "warning" | "error";

function apiUrl(path: string) {
  return `${getBaseUrl()}${path}`;
}

function safeJson(v: any) {
  try {
    return JSON.stringify(v ?? null, null, 2);
  } catch {
    return "";
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

function badgeColor(status: ValidateStatus) {
  if (status === "ok") return "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
  if (status === "warning") return "bg-amber-500/15 text-amber-200 border-amber-500/30";
  return "bg-red-500/15 text-red-200 border-red-500/30";
}

function downloadText(filename: string, text: string, mime = "application/json;charset=utf-8") {
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

const DEFAULT_SCHEMA_V2 = {
  spec_version: "2.0",
  meta: { strategy_id: "xau_schema_v2_demo", name: "Schema v2 Demo", version: "0.1.0", description: "示例：用于编辑/校验面板" },
  universe: { symbols: ["XAUUSDz"], primary_timeframe: "30m" },
  data: { history_lookback_bars: 600, higher_timeframes: ["4h"] },
  indicators: [],
  patterns: [],
  action: { type: "breakout" },
  outputs: { emit_evidence_pack: true, emit_draw_plan: true, emit_compilation_report: true, emit_trace: true, emit_intermediate_artifacts: false },
};

export function SchemaV2Panel() {
  const [mode, setMode] = useState<Mode>("json");
  const [jsonText, setJsonText] = useState<string>(safeJson(DEFAULT_SCHEMA_V2));
  const [jsonErr, setJsonErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [validateResp, setValidateResp] = useState<any | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const [form, setForm] = useState({
    strategy_id: "xau_schema_v2_demo",
    name: "Schema v2 Demo",
    version: "0.1.0",
    description: "",
    symbolsText: "XAUUSDz",
    primary_timeframe: "30m",
    lookback: 600,
    higherTFsText: "4h",
    actionType: "breakout",
  });

  // load last
  useEffect(() => {
    try {
      const raw = localStorage.getItem("awesome_chart_last_schema_v2");
      if (raw) setJsonText(raw);
    } catch {}
  }, []);

  const status: ValidateStatus | null = useMemo(() => {
    const st = String(validateResp?.status || "");
    if (st === "ok") return "ok";
    if (st === "warning") return "warning";
    if (st === "error") return "error";
    return null;
  }, [validateResp]);

  const jumpToPath = (path: string) => {
    const seg = String(path || "").split(".").filter(Boolean).slice(-1)[0];
    if (!seg) return;
    const el = textareaRef.current;
    if (!el) return;
    const text = el.value || "";
    const idx = text.indexOf(`"${seg}"`);
    el.focus();
    if (idx >= 0) el.setSelectionRange(idx, Math.min(text.length, idx + seg.length + 2));
  };

  const buildFromForm = () => {
    const symbols = form.symbolsText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const htfs = form.higherTFsText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    return {
      spec_version: "2.0",
      meta: { strategy_id: form.strategy_id, name: form.name, version: form.version, description: form.description || "" },
      universe: { symbols: symbols.length ? symbols : ["XAUUSDz"], primary_timeframe: form.primary_timeframe || "30m" },
      data: { history_lookback_bars: Number(form.lookback || 600), higher_timeframes: htfs },
      indicators: [],
      patterns: [],
      action: { type: form.actionType || "breakout" },
      outputs: { emit_evidence_pack: true, emit_draw_plan: true, emit_compilation_report: true, emit_trace: true, emit_intermediate_artifacts: false },
    };
  };

  const syncFormFromJson = () => {
    const parsed = tryParseJson(jsonText);
    if (!parsed.ok) return;
    const v = parsed.value || {};
    const meta = v.meta || {};
    const uni = v.universe || {};
    const data = v.data || {};
    const action = v.action || {};
    setForm((f) => ({
      ...f,
      strategy_id: String(meta.strategy_id || f.strategy_id),
      name: String(meta.name || f.name),
      version: String(meta.version || f.version),
      description: String(meta.description || ""),
      symbolsText: Array.isArray(uni.symbols) ? uni.symbols.join(",") : f.symbolsText,
      primary_timeframe: String(uni.primary_timeframe || f.primary_timeframe),
      lookback: Number(data.history_lookback_bars || f.lookback),
      higherTFsText: Array.isArray(data.higher_timeframes) ? data.higher_timeframes.join(",") : f.higherTFsText,
      actionType: String(action.type || f.actionType),
    }));
  };

  const validate = async (payloadObj?: any) => {
    setBusy(true);
    setJsonErr(null);
    try {
      const obj = payloadObj ?? (() => {
        const parsed = tryParseJson(jsonText);
        if (!parsed.ok) throw new Error(parsed.error);
        return parsed.value;
      })();

      const r = await fetch(apiUrl("/api/strategy/schema/v2/validate"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy_schema: obj }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      setValidateResp(j);
      try {
        localStorage.setItem("awesome_chart_last_schema_v2", jsonText);
      } catch {}
    } catch (e: any) {
      setValidateResp({ status: "error", validation_errors: [{ path: "", message: e?.message || "校验失败" }] });
      setJsonErr(e?.message || "校验失败");
    } finally {
      setBusy(false);
    }
  };

  const applyNormalized = () => {
    const ns = validateResp?.normalized_spec;
    if (!ns) return;
    setJsonText(safeJson(ns));
  };

  return (
    <div className="h-full overflow-hidden flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <button
            className={[
              "text-xs px-2 py-1 rounded border",
              mode === "json" ? "border-emerald-400 bg-emerald-500/10 text-emerald-200" : "border-white/10 hover:bg-white/5 text-gray-300",
            ].join(" ")}
            onClick={() => setMode("json")}
          >
            JSON 模式
          </button>
          <button
            className={[
              "text-xs px-2 py-1 rounded border",
              mode === "form" ? "border-emerald-400 bg-emerald-500/10 text-emerald-200" : "border-white/10 hover:bg-white/5 text-gray-300",
            ].join(" ")}
            onClick={() => {
              syncFormFromJson();
              setMode("form");
            }}
          >
            表单模式
          </button>

          {status && <span className={["text-[11px] px-2 py-1 rounded border", badgeColor(status)].join(" ")}>{status.toUpperCase()}</span>}
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              setJsonText(safeJson(DEFAULT_SCHEMA_V2));
              setValidateResp(null);
            }}
          >
            载入示例
          </Button>
          <Button variant="secondary" onClick={() => downloadText("strategy_schema_v2.json", jsonText || safeJson(DEFAULT_SCHEMA_V2))}>
            下载
          </Button>
        </div>
      </div>

      {mode === "form" ? (
        <div className="flex-1 overflow-auto border border-white/10 rounded-lg p-3 bg-black/20">
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-gray-300">
              strategy_id
              <input className="mt-1 w-full px-2 py-1 rounded bg-black/40 border border-white/10" value={form.strategy_id} onChange={(e) => setForm((f) => ({ ...f, strategy_id: e.target.value }))} />
            </label>
            <label className="text-xs text-gray-300">
              name
              <input className="mt-1 w-full px-2 py-1 rounded bg-black/40 border border-white/10" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            </label>
            <label className="text-xs text-gray-300">
              version
              <input className="mt-1 w-full px-2 py-1 rounded bg-black/40 border border-white/10" value={form.version} onChange={(e) => setForm((f) => ({ ...f, version: e.target.value }))} />
            </label>
            <label className="text-xs text-gray-300">
              primary_timeframe
              <input className="mt-1 w-full px-2 py-1 rounded bg-black/40 border border-white/10" value={form.primary_timeframe} onChange={(e) => setForm((f) => ({ ...f, primary_timeframe: e.target.value }))} />
            </label>
            <label className="text-xs text-gray-300 col-span-2">
              description
              <input className="mt-1 w-full px-2 py-1 rounded bg-black/40 border border-white/10" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
            </label>
            <label className="text-xs text-gray-300">
              symbols（逗号分隔）
              <input className="mt-1 w-full px-2 py-1 rounded bg-black/40 border border-white/10" value={form.symbolsText} onChange={(e) => setForm((f) => ({ ...f, symbolsText: e.target.value }))} />
            </label>
            <label className="text-xs text-gray-300">
              higher_timeframes（逗号分隔）
              <input className="mt-1 w-full px-2 py-1 rounded bg-black/40 border border-white/10" value={form.higherTFsText} onChange={(e) => setForm((f) => ({ ...f, higherTFsText: e.target.value }))} />
            </label>
            <label className="text-xs text-gray-300">
              history_lookback_bars
              <input
                type="number"
                className="mt-1 w-full px-2 py-1 rounded bg-black/40 border border-white/10"
                value={form.lookback}
                onChange={(e) => setForm((f) => ({ ...f, lookback: Number(e.target.value) }))}
              />
            </label>
            <label className="text-xs text-gray-300">
              action.type
              <select className="mt-1 w-full px-2 py-1 rounded bg-black/40 border border-white/10" value={form.actionType} onChange={(e) => setForm((f) => ({ ...f, actionType: e.target.value }))}>
                <option value="breakout">breakout</option>
                <option value="pullback">pullback</option>
                <option value="mean_reversion">mean_reversion</option>
                <option value="continuation">continuation</option>
                <option value="range">range</option>
                <option value="custom">custom</option>
              </select>
            </label>
          </div>

          <div className="mt-4 flex items-center gap-2">
            <Button
              onClick={() => {
                const obj = buildFromForm();
                const txt = safeJson(obj);
                setJsonText(txt);
                setMode("json");
                validate(obj);
              }}
              disabled={busy}
            >
              生成 JSON 并校验
            </Button>
            <Button variant="secondary" onClick={() => setJsonText(safeJson(buildFromForm()))} disabled={busy}>
              仅生成 JSON
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-hidden grid grid-rows-[1fr_auto] gap-3">
          <div className="border border-white/10 rounded-lg overflow-hidden">
            <textarea
              ref={textareaRef}
              className="w-full h-full p-3 bg-black/30 text-[12px] font-mono outline-none"
              value={jsonText}
              onChange={(e) => setJsonText(e.target.value)}
              spellCheck={false}
            />
          </div>
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs text-gray-400">{jsonErr ? <span className="text-red-300">{jsonErr}</span> : "提示：点击错误项可定位字段"}</div>
            <div className="flex items-center gap-2">
              <Button onClick={() => validate()} disabled={busy}>
                {busy ? "校验中…" : "校验"}
              </Button>
              <Button variant="secondary" onClick={applyNormalized} disabled={!validateResp?.normalized_spec}>
                应用 normalized
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      {validateResp && (
        <div className="border border-white/10 rounded-lg bg-black/20 p-3 overflow-auto max-h-[45vh]">
          <div className="text-sm font-semibold mb-2">校验结果</div>

          {Array.isArray(validateResp?.validation_errors) && validateResp.validation_errors.length > 0 && (
            <div className="mb-3">
              <div className="text-xs text-gray-400 mb-1">Errors</div>
              <div className="space-y-1">
                {validateResp.validation_errors.slice(0, 50).map((e: any, idx: number) => (
                  <button
                    key={idx}
                    className="w-full text-left text-[12px] px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                    onClick={() => jumpToPath(String(e?.path || ""))}
                    title="点击定位"
                  >
                    <span className="text-gray-400">{String(e?.path || "")}</span>
                    <span className="mx-2 text-gray-600">—</span>
                    <span className="text-gray-200">{String(e?.message || "")}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {Array.isArray(validateResp?.unsupported_features) && validateResp.unsupported_features.length > 0 && (
            <div className="mb-3">
              <div className="text-xs text-gray-400 mb-1">Unsupported</div>
              <div className="space-y-1">
                {validateResp.unsupported_features.map((u: any, idx: number) => (
                  <div key={idx} className="text-[12px] px-2 py-1 rounded border border-white/10">
                    <div className="text-gray-200">{u?.feature}</div>
                    <div className="text-gray-400">原因：{u?.reason}</div>
                    <div className="text-gray-500">替代：{u?.workaround}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {Array.isArray(validateResp?.capabilities_required) && validateResp.capabilities_required.length > 0 && (
            <div className="mb-3">
              <div className="text-xs text-gray-400 mb-1">Capabilities</div>
              <div className="space-y-1">
                {validateResp.capabilities_required.map((c: any, idx: number) => (
                  <div key={idx} className="flex items-center justify-between text-[12px] px-2 py-1 rounded border border-white/10">
                    <div className="text-gray-200">{c?.tool}</div>
                    <div className="text-gray-400 flex items-center gap-2">
                      <span className={c?.supported ? "text-emerald-300" : "text-amber-200"}>{String(c?.status || (c?.supported ? "supported" : "unknown"))}</span>
                      <span className="text-gray-600">{c?.version ? `v${c.version}` : ""}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {Array.isArray(validateResp?.normalization_fixes) && validateResp.normalization_fixes.length > 0 && (
            <div className="mb-3">
              <div className="text-xs text-gray-400 mb-1">Normalization fixes</div>
              <div className="space-y-1">
                {validateResp.normalization_fixes.slice(0, 80).map((f: any, idx: number) => (
                  <div key={idx} className="text-[12px] px-2 py-1 rounded border border-white/10">
                    <div className="text-gray-200">
                      {f?.code} <span className="text-gray-500">{f?.path}</span>
                    </div>
                    <div className="text-gray-500">{f?.reason}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {validateResp?.normalized_spec && (
            <details className="mt-2">
              <summary className="text-xs text-gray-300 cursor-pointer select-none">查看 normalized_spec</summary>
              <pre className="mt-2 text-[11px] p-2 rounded bg-black/30 overflow-auto">{safeJson(validateResp.normalized_spec)}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

