"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Settings, Play, Send, X, Plug, Trash2 } from "lucide-react";
import { getBaseUrl } from "@/lib/api";

type AgentConfig = {
  base_url: string;
  model: string;
  api_key: string;
};

type AiSettings = {
  supervisor: AgentConfig;
  analyzer: AgentConfig;
  executor: AgentConfig;
  eventTriggerEnabled: boolean;
  eventTimeframeRajaSR: string;
  eventTimeframeMSB: string;
  enableMSB: boolean;
  enableRajaSR: boolean;
};

const KEY = "awesome_trading_agent_settings_v3";

function defaultAgentConfig(): AgentConfig {
  return {
    base_url: "https://api.siliconflow.cn/v1",
    model: "Qwen/Qwen3.5-9B",
    api_key: "",
  };
}

function defaultSettings(): AiSettings {
  return {
    supervisor: {
      base_url: "https://api.siliconflow.cn/v1",
      model: "deepseek-ai/DeepSeek-V3",
      api_key: "",
    },
    analyzer: {
      base_url: "https://api.siliconflow.cn/v1",
      model: "deepseek-ai/DeepSeek-V3",
      api_key: "",
    },
    executor: {
      base_url: "https://api.siliconflow.cn/v1",
      model: "Qwen/Qwen3.5-35B-A3B",
      api_key: "",
    },
    eventTriggerEnabled: false,
    eventTimeframeRajaSR: "H1",
    eventTimeframeMSB: "M15",
    enableMSB: true,
    enableRajaSR: true,
  };
}

type AgentStatus = "idle" | "thinking" | "acting" | "finished" | "error";

type ChatMsg = {
  id: string;
  agent: string;
  status: AgentStatus;
  content: string;
  time: string;
};

export function AgentAdvisorPanel(props: {
  chartState: any;
  symbol: string;
  timeframe: string;
  onExecuteActions: (actions: any[]) => Promise<string[]> | string[];
}) {
  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [running, setRunning] = useState(false);
  const [sessionId, setSessionId] = useState<string>("");
  const [inputText, setInputText] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  
  const MSG_KEY = "awesome_trading_agent_messages_v1";

  const [agentsState, setAgentsState] = useState<{
    supervisor: AgentStatus;
    analyzer: AgentStatus;
    executor: AgentStatus;
  }>({
    supervisor: "idle",
    analyzer: "idle",
    executor: "idle"
  });

  const apiUrl = useMemo(() => {
    const base = getBaseUrl();
    if (base) return (p: string) => `${base}${p}`;
    if (typeof window !== "undefined") {
      const host = window.location.hostname;
      const port = window.location.port;
      if (port && window.location.protocol !== "file:") {
        const backendHost = (host === "0.0.0.0" || host === "localhost") ? "127.0.0.1" : host;
        return (p: string) => `http://${backendHost}:8123${p}`;
      }
    }
    return (p: string) => p;
  }, []);

  const wsUrl = useMemo(() => {
    if (typeof window !== "undefined") {
      const host = window.location.hostname;
      const port = window.location.port;
      if (port && window.location.protocol !== "file:") {
        const backendHost = (host === "0.0.0.0" || host === "localhost") ? "127.0.0.1" : host;
        return `ws://${backendHost}:8123/api/ws/AGENT/SYSTEM`;
      }
    }
    return "ws://127.0.0.1:8123/api/ws/AGENT/SYSTEM";
  }, []);

  useEffect(() => {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      try {
        setSettings(JSON.parse(raw));
      } catch {
        setSettings(defaultSettings());
      }
    } else {
      setSettings(defaultSettings());
    }
    
    // Load messages from local storage
    const rawMsgs = localStorage.getItem(MSG_KEY);
    if (rawMsgs) {
      try {
        setMessages(JSON.parse(rawMsgs));
      } catch {
        setMessages([]);
      }
    }
  }, []);

  const saveSettings = (s: AiSettings) => {
    setSettings(s);
    localStorage.setItem(KEY, JSON.stringify(s));
  };

  const saveMessages = (msgs: ChatMsg[]) => {
    setMessages(msgs);
    localStorage.setItem(MSG_KEY, JSON.stringify(msgs));
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, agentsState]);

  useEffect(() => {
    let ws: WebSocket;
    let retryTimer: any;
    const connect = () => {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          
          if (data.type === "tool_execution") {
            console.log("[DEBUG Frontend] Received tool_execution event:", data);
            if (data.payload && (data.payload.type || data.payload.action)) {
              props.onExecuteActions([data.payload]);
            }
            return;
          }
          
          if (data.type === "agent_status") {
            const { current_agent, status, latest_message } = data;
            
            setAgentsState(prev => ({
              ...prev,
              [current_agent]: status
            }));
            
            if (current_agent === "supervisor" && status === "finished") {
               setRunning(false);
            }

            if (latest_message) {
               setMessages(prev => {
                 // Prevent duplicate rendering by checking if the last message is identical
                 const lastMsg = prev[prev.length - 1];
                 if (lastMsg && lastMsg.agent === current_agent && lastMsg.content === latest_message) {
                   return prev;
                 }
                 const newMsgs = [
                   ...prev,
                   {
                     id: Date.now().toString() + Math.random(),
                     agent: current_agent,
                     status: status,
                     content: latest_message,
                     time: new Date().toLocaleTimeString()
                   }
                 ];
                 localStorage.setItem(MSG_KEY, JSON.stringify(newMsgs));
                 return newMsgs;
               });
            }
          }
        } catch (e) {}
      };
      ws.onclose = () => {
        retryTimer = setTimeout(connect, 3000);
      };
    };
    connect();
    return () => {
      clearTimeout(retryTimer);
      if (ws) ws.close();
    };
  }, [wsUrl]);

  const triggerDecision = async (overrideMessage?: string) => {
    if (!settings || running) return;
    const msgToSent = overrideMessage || inputText.trim() || "Please analyze the current market context and execute necessary actions.";
    
    setRunning(true);
    if (!overrideMessage) setInputText("");
    
    // Add user message to UI
    setMessages(prev => {
      const newMsgs = [
        ...prev,
        {
          id: Date.now().toString(),
          agent: "user",
          status: "idle" as AgentStatus,
          content: msgToSent,
          time: new Date().toLocaleTimeString()
        }
      ];
      localStorage.setItem(MSG_KEY, JSON.stringify(newMsgs));
      return newMsgs;
    });
    
    setAgentsState({ supervisor: "idle", analyzer: "idle", executor: "idle" });
    const sid = `session_${Date.now()}`;
    setSessionId(sid);
    
    try {
      const res = await fetch(apiUrl("/api/agent/trigger_decision"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sid,
          message: msgToSent,
          symbol: props.symbol || "XAUUSD",
          timeframe: props.timeframe || "M15",
          configs: {
            supervisor: settings.supervisor,
            analyzer: settings.analyzer,
            executor: settings.executor,
          }
        })
      });
      if (!res.ok) throw new Error("Failed to trigger agent");
    } catch (e) {
      console.error(e);
      setRunning(false);
    }
  };

  const testConnection = async () => {
    if (!settings) return;
    try {
      const res = await fetch(apiUrl("/api/agent/test_connection"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: "test",
          message: "test",
          configs: {
            supervisor: settings.supervisor,
            analyzer: settings.analyzer,
            executor: settings.executor,
          }
        })
      });
      if (res.ok) {
        const results = await res.json();
        const msg = Object.entries(results)
          .map(([role, data]: [string, any]) => `${role}: ${data.status === 'success' ? 'OK' : 'Error - ' + data.message}`)
          .join('\n');
        alert("Connection Test Results:\n" + msg);
      } else {
        alert("Failed to test connection.");
      }
    } catch (e) {
      alert("Error testing connection: " + e);
    }
  };

  const getLightColor = (status: AgentStatus) => {
    switch (status) {
      case "thinking": return "bg-green-500 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.8)]";
      case "acting": return "bg-green-500 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.8)]";
      case "finished": return "bg-green-500";
      case "error": return "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]";
      default: return "bg-gray-600";
    }
  };

  if (!settings) return <div className="p-4 text-xs text-gray-500">Loading...</div>;

  return (
    <div className="h-full flex flex-col relative bg-[#0b0f14]">
      {/* Header Panel */}
      <div className="flex items-center justify-between p-3 border-b border-white/10 shrink-0">
        <div className="flex gap-4">
          <div className="flex flex-col items-center gap-1">
            <div className={`w-3 h-3 rounded-full ${getLightColor(agentsState.supervisor)}`} />
            <span className="text-[10px] text-gray-400">Supervisor</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <div className={`w-3 h-3 rounded-full ${getLightColor(agentsState.analyzer)}`} />
            <span className="text-[10px] text-gray-400">Analyzer</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <div className={`w-3 h-3 rounded-full ${getLightColor(agentsState.executor)}`} />
            <span className="text-[10px] text-gray-400">Executor</span>
          </div>
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="icon" onClick={() => saveMessages([])} className="text-gray-400 hover:text-red-400" title="Clear Chat History">
            <Trash2 size={16} />
          </Button>
          <Button variant="ghost" size="icon" onClick={testConnection} className="text-gray-400 hover:text-[#00bfa5]" title="Test Connection">
            <Plug size={16} />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => setShowSettings(!showSettings)} className="text-gray-400 hover:text-white" title="Agent Configurations">
            <Settings size={16} />
          </Button>
        </div>
      </div>

      {/* Settings Modal */}
      {showSettings && (
        <div className="absolute inset-0 bg-[#0b0f14] z-10 p-4 overflow-y-auto custom-scrollbar border-b border-white/10 flex flex-col gap-4">
          <div className="flex justify-between items-center mb-2">
            <h3 className="font-semibold text-white">Agent Configurations</h3>
            <Button variant="ghost" size="icon" onClick={() => setShowSettings(false)}>
              <X size={16} />
            </Button>
          </div>
          
          <div className="space-y-3 border border-white/10 p-3 rounded-md mb-2">
            <h4 className="text-sm font-medium text-[#00bfa5]">Event Trigger Settings</h4>
            <div className="flex items-center gap-2 text-xs text-gray-300">
              <input type="checkbox" checked={settings.eventTriggerEnabled} onChange={(e) => saveSettings({...settings, eventTriggerEnabled: e.target.checked})} />
              <label>Enable Background Alerts Engine (Global)</label>
            </div>
            <div className="flex flex-col gap-2 mt-2">
              <div className="flex items-center justify-between text-xs text-gray-300">
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={settings.enableRajaSR} onChange={(e) => saveSettings({...settings, enableRajaSR: e.target.checked})} /> RajaSR Zones
                </label>
                <div className="flex items-center gap-1">
                  <span className="text-gray-500">TF:</span>
                  <select className="bg-black/30 border border-white/10 rounded px-1" value={settings.eventTimeframeRajaSR} onChange={(e) => saveSettings({...settings, eventTimeframeRajaSR: e.target.value})}>
                    <option value="M5">M5</option>
                    <option value="M15">M15</option>
                    <option value="H1">H1</option>
                    <option value="H4">H4</option>
                  </select>
                </div>
              </div>
              <div className="flex items-center justify-between text-xs text-gray-300">
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={settings.enableMSB} onChange={(e) => saveSettings({...settings, enableMSB: e.target.checked})} /> MSB ZigZag
                </label>
                <div className="flex items-center gap-1">
                  <span className="text-gray-500">TF:</span>
                  <select className="bg-black/30 border border-white/10 rounded px-1" value={settings.eventTimeframeMSB} onChange={(e) => saveSettings({...settings, eventTimeframeMSB: e.target.value})}>
                    <option value="M5">M5</option>
                    <option value="M15">M15</option>
                    <option value="H1">H1</option>
                    <option value="H4">H4</option>
                  </select>
                </div>
              </div>
            </div>
          </div>

          {['supervisor', 'analyzer', 'executor'].map((agent) => (
            <div key={agent} className="space-y-2 border border-white/10 p-3 rounded-md">
              <h4 className="text-sm font-medium text-gray-300 capitalize">{agent} Model</h4>
              <input
                className="w-full bg-black/30 border border-white/10 rounded px-2 py-1 text-xs text-white"
                placeholder="Base URL"
                value={(settings as any)[agent].base_url}
                onChange={(e) => saveSettings({...settings, [agent]: {...(settings as any)[agent], base_url: e.target.value}})}
              />
              <input
                className="w-full bg-black/30 border border-white/10 rounded px-2 py-1 text-xs text-white"
                placeholder="Model Name"
                value={(settings as any)[agent].model}
                onChange={(e) => saveSettings({...settings, [agent]: {...(settings as any)[agent], model: e.target.value}})}
              />
              <input
                type="password"
                className="w-full bg-black/30 border border-white/10 rounded px-2 py-1 text-xs text-white"
                placeholder="API Key"
                value={(settings as any)[agent].api_key}
                onChange={(e) => saveSettings({...settings, [agent]: {...(settings as any)[agent], api_key: e.target.value}})}
              />
            </div>
          ))}

          <div className="pt-2 pb-4 mt-auto">
            <Button 
              className="w-full bg-[#00bfa5] hover:bg-[#00bfa5]/80 text-black font-medium"
              onClick={() => setShowSettings(false)}
            >
              Save & Apply Configuration
            </Button>
          </div>
        </div>
      )}

      {/* Chat / Log Panel */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-3" ref={scrollRef}>
        {messages.map((msg) => (
          <div key={msg.id} className={`text-xs border rounded-md p-2 ${msg.agent === 'user' ? 'bg-[#00bfa5]/10 border-[#00bfa5]/30 ml-8' : 'bg-white/5 border-white/10 mr-8'}`}>
            <div className="flex justify-between items-center mb-1">
              <span className={`font-semibold capitalize ${
                msg.agent === 'supervisor' ? 'text-purple-400' :
                msg.agent === 'analyzer' ? 'text-blue-400' : 
                msg.agent === 'executor' ? 'text-green-400' : 'text-[#00bfa5]'
              }`}>
                {msg.agent}
              </span>
              <span className="text-[10px] text-gray-500">{msg.time}</span>
            </div>
            <div className="text-gray-300 whitespace-pre-wrap font-mono leading-relaxed">
              {msg.content}
            </div>
          </div>
        ))}
      </div>

      {/* Action Footer */}
      <div className="p-3 border-t border-white/10 shrink-0 flex flex-col gap-2">
        <div className="flex gap-2">
          <input 
            type="text" 
            className="flex-1 bg-black/30 border border-white/10 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-[#00bfa5]/50"
            placeholder="Ask agent to analyze or draw..."
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') triggerDecision(); }}
            disabled={running}
          />
          <Button 
            className="bg-[#00bfa5] hover:bg-[#00bfa5]/80 text-black px-3"
            onClick={() => triggerDecision()}
            disabled={running || !inputText.trim()}
          >
            <Send size={16} />
          </Button>
        </div>
        <Button 
          variant="outline"
          className="w-full border-white/10 hover:bg-white/5 text-gray-300 text-xs flex items-center justify-center gap-2"
          onClick={() => triggerDecision("Please analyze the current market context and execute necessary actions.")}
          disabled={running}
        >
          {running ? (
            <span className="animate-pulse">AI is working...</span>
          ) : (
            <>
              <Play size={14} />
              Auto Analyze Current Chart
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
