"use client";

import React from "react";
import { CalendarDays, MessageSquare, Bot, Siren, Radar, Activity } from "lucide-react";

export type RightPanelId = "none" | "ai" | "chat" | "alerts" | "scan" | "patterns" | "calendar";

function RailButton(props: { active: boolean; title: string; onClick: () => void; children: React.ReactNode }) {
  const { active, title, onClick, children } = props;
  return (
    <button
      className={[
        "w-12 h-12 mx-auto",
        "flex items-center justify-center",
        "rounded-xl border",
        "transition",
        active
          ? "border-emerald-400 dark:bg-emerald-500/10 bg-emerald-500/20 text-emerald-500 dark:text-emerald-300 shadow-[0_0_0_1px_rgba(16,185,129,0.25)]"
          : "dark:border-white/10 border-black/10 bg-transparent dark:text-gray-300 text-gray-600 dark:hover:bg-white/5 hover:bg-black/5 dark:hover:text-white hover:text-black",
      ].join(" ")}
      onClick={onClick}
      title={title}
    >
      {children}
    </button>
  );
}

export function RightRail(props: { active: RightPanelId; onToggle: (id: RightPanelId) => void }) {
  const { active, onToggle } = props;
  return (
    <aside className="h-full w-[56px] shrink-0 border-l dark:border-white/10 border-black/10 dark:bg-[#0b0f14] bg-white flex flex-col items-center py-3 gap-3">
      <div className="flex-1 flex flex-col gap-3 items-center">
        <RailButton active={active === "ai"} title="AI Assistant" onClick={() => onToggle(active === "ai" ? "none" : "ai")}>
          <Bot size={20} />
        </RailButton>
        <RailButton active={active === "chat"} title="Chat / Strategy" onClick={() => onToggle(active === "chat" ? "none" : "chat")}>
          <MessageSquare size={20} />
        </RailButton>
        <RailButton active={active === "alerts"} title="Alerts" onClick={() => onToggle(active === "alerts" ? "none" : "alerts")}>
          <Siren size={20} />
        </RailButton>
        <RailButton active={active === "scan"} title="Pipeline" onClick={() => onToggle(active === "scan" ? "none" : "scan")}>
          <Radar size={20} />
        </RailButton>
        <RailButton active={active === "patterns"} title="Patterns" onClick={() => onToggle(active === "patterns" ? "none" : "patterns")}>
          <Activity size={20} />
        </RailButton>
        <RailButton active={active === "calendar"} title="Calendar" onClick={() => onToggle(active === "calendar" ? "none" : "calendar")}>
          <CalendarDays size={20} />
        </RailButton>

        {/* 后续 Research/Optimize 也按同样模式往下加按钮 */}
        <div className="w-8 h-px dark:bg-white/10 bg-black/10 my-1" />
      </div>

      <div className="text-[10px] text-gray-500 select-none">AC</div>
    </aside>
  );
}
