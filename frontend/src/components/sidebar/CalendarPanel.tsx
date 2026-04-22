"use client";

import React, { useEffect, useState, useMemo } from "react";
import { getBaseUrl } from "@/lib/api";

type CalendarEvent = {
  id: string;
  title: string;
  impact: string; // "High", "Medium", "Low"
  date_group: string; // e.g., "2026年04月16日 星期四"
  time_str: string; // e.g., "20:30"
  weekday: number; // 0=Mon, 1=Tue... 6=Sun
  timestamp: number;
  previous: string;
  forecast: string;
  actual: string;
};

const WEEKDAYS = [
  { label: "日", val: 6 },
  { label: "一", val: 0 },
  { label: "二", val: 1 },
  { label: "三", val: 2 },
  { label: "四", val: 3 },
  { label: "五", val: 4 },
  { label: "六", val: 5 },
];

export function CalendarPanel() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<number>(0);
  const [impactFilter, setImpactFilter] = useState<string>("All"); // "All", "High", "Medium", "Low"

  // Initialize active tab to current Beijing weekday
  useEffect(() => {
    const localDate = new Date();
    const utc = localDate.getTime() + localDate.getTimezoneOffset() * 60000;
    const bjDate = new Date(utc + 3600000 * 8);
    const bjDay = bjDate.getDay(); // 0 is Sunday
    const bjWeekday = bjDay === 0 ? 6 : bjDay - 1; // Map to 0=Mon, 6=Sun
    setActiveTab(bjWeekday);
  }, []);

  const apiUrl = useMemo(() => {
    const base = getBaseUrl();
    if (base) return (p: string) => `${base}${p}`;
    if (typeof window !== "undefined") {
      const host = window.location.hostname;
      const port = window.location.port;
      if (port && window.location.protocol !== "file:") {
        const backendHost = host === "0.0.0.0" ? "127.0.0.1" : host;
        return (p: string) => `http://${backendHost}:8123${p}`;
      }
    }
    return (p: string) => p;
  }, []);

  const fetchCalendar = async (forceRefresh: boolean = false) => {
    setLoading(true);
    setErr(null);
    try {
      const url = apiUrl(`/api/calendar?_t=${Date.now()}${forceRefresh ? '&force=true' : ''}`);
      const res = await fetch(url, {
        cache: "no-store",
      });
      const data = await res.json();
      if (data.ok) {
        setEvents(data.events || []);
      } else {
        setErr(data.detail || "获取数据失败");
      }
    } catch (e: any) {
      setErr("请求异常: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCalendar();
    // Refresh every 5 minutes automatically
    const timer = setInterval(() => fetchCalendar(false), 300000);
    return () => clearInterval(timer);
  }, [apiUrl]);

  // Filter and group events by selected weekday and impact
  const grouped = useMemo(() => {
    const groups: Record<string, CalendarEvent[]> = {};
    const filteredEvents = events.filter((ev) => {
      if (ev.weekday !== activeTab) return false;
      if (impactFilter !== "All" && ev.impact !== impactFilter) return false;
      return true;
    });
    
    for (const ev of filteredEvents) {
      if (!groups[ev.date_group]) groups[ev.date_group] = [];
      groups[ev.date_group].push(ev);
    }
    return groups;
  }, [events, activeTab, impactFilter]);

  const getImpactColor = (impact: string) => {
    if (impact === "High") return "text-red-500";
    if (impact === "Medium") return "text-orange-400";
    return "text-yellow-500";
  };

  const getImpactStars = (impact: string) => {
    if (impact === "High") return "★★★★★";
    if (impact === "Medium") return "★★★☆☆";
    return "★☆☆☆☆";
  };

  return (
    <div className="flex flex-col h-full bg-white dark:bg-[#0b0f14] text-gray-800 dark:text-gray-200">
      <div className="flex items-center justify-between p-3 border-b border-gray-200 dark:border-white/10">
        <div className="text-sm font-semibold flex items-center gap-2">
          <span className="text-orange-500">📅</span>
          财经日历 (USD)
        </div>
        <button
          className="text-xs text-gray-500 hover:text-black dark:text-gray-400 dark:hover:text-white"
          onClick={() => fetchCalendar(true)}
          disabled={loading}
          title="强制从数据源刷新"
        >
          {loading ? "..." : "刷新"}
        </button>
      </div>

      {/* Weekday Tabs */}
      <div className="flex flex-col px-3 py-2 bg-gray-50 dark:bg-[#131722] border-b border-gray-200 dark:border-white/5 gap-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-600 dark:text-gray-400">选择本周日期:</span>
          <select 
            value={impactFilter}
            onChange={(e) => setImpactFilter(e.target.value)}
            className="text-xs bg-white dark:bg-[#1e222d] border border-gray-300 dark:border-[#2B2B43] rounded px-2 py-1 text-gray-800 dark:text-gray-300 focus:outline-none focus:border-[#00bfa5] cursor-pointer"
          >
            <option value="All" className="bg-white dark:bg-[#1e222d] text-gray-800 dark:text-gray-300">全部事件</option>
            <option value="High" className="bg-white dark:bg-[#1e222d] text-gray-800 dark:text-gray-300">重要 (High)</option>
            <option value="Medium" className="bg-white dark:bg-[#1e222d] text-gray-800 dark:text-gray-300">中等 (Medium)</option>
            <option value="Low" className="bg-white dark:bg-[#1e222d] text-gray-800 dark:text-gray-300">一般 (Low)</option>
          </select>
        </div>
        <div className="flex items-center justify-between">
          {WEEKDAYS.map((day) => {
            // FF API uses a Sunday-to-Saturday week.
            // So we calculate the dates relative to the most recent Sunday.
            const today = new Date();
            const currentDayNum = today.getDay(); // 0=Sun, 1=Mon, ..., 6=Sat
            const sundayDate = new Date(today);
            sundayDate.setDate(today.getDate() - currentDayNum);
            
            // Map day.val (6=Sun, 0=Mon, ..., 5=Sat) to an offset from Sunday (0-6)
            const offsetFromSunday = day.val === 6 ? 0 : day.val + 1;
            
            const targetDate = new Date(sundayDate);
            targetDate.setDate(sundayDate.getDate() + offsetFromSunday);
            const dateStr = `${targetDate.getMonth() + 1}/${targetDate.getDate()}`;

            return (
              <button
                key={day.val}
                onClick={() => setActiveTab(day.val)}
                className={`flex flex-col items-center flex-1 py-1 rounded-md transition-colors ${
                  activeTab === day.val
                    ? "bg-[#00bfa5]/20 text-[#00bfa5] font-bold"
                    : "text-gray-500 hover:text-gray-800 dark:hover:text-gray-300 hover:bg-black/5 dark:hover:bg-white/5"
                }`}
              >
                <span className="text-xs">{day.label}</span>
                <span className="text-[10px] opacity-70">{dateStr}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-6 custom-scrollbar">
        {err && <div className="text-red-500 dark:text-red-400 text-xs">{err}</div>}
        {!err && Object.keys(grouped).length === 0 && !loading && (
          <div className="text-gray-500 text-xs text-center py-10">该日暂无美国重要经济数据</div>
        )}

        {Object.entries(grouped).map(([dateGroup, dayEvents]) => (
          <div key={dateGroup} className="space-y-3">
            <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-white/10 pb-1">
              {dateGroup}
            </div>
            
            {dayEvents.map((ev) => (
              <div key={ev.id} className="bg-gray-50 dark:bg-white/5 rounded-lg p-3 space-y-2 border border-gray-200 dark:border-white/5">
                <div className="flex justify-between items-start">
                  <div className="flex flex-col gap-1">
                    <span className="text-lg font-mono font-bold text-gray-800 dark:text-gray-200">{ev.time_str}</span>
                    <span className={`text-sm font-medium ${getImpactColor(ev.impact)}`}>
                      {ev.title}
                    </span>
                  </div>
                  <span className={`text-[10px] mt-1 ${getImpactColor(ev.impact)}`}>
                    {getImpactStars(ev.impact)}
                  </span>
                </div>
                
                <div className="grid grid-cols-3 gap-2 text-[10px] mt-2">
                  <div className="flex flex-col">
                    <span className="text-gray-500 scale-90 origin-left">前值</span>
                    <span className="font-mono text-gray-600 dark:text-gray-400">{ev.previous || "-"}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-gray-500 scale-90 origin-left">预期</span>
                    <span className="font-mono text-gray-600 dark:text-gray-400">{ev.forecast || "-"}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-gray-500 scale-90 origin-left">公布</span>
                    <span className={`font-mono ${ev.actual ? 'text-black dark:text-white font-bold' : 'text-gray-400 dark:text-gray-600'}`}>
                      {ev.actual || "待公布"}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
