import { useState, useRef, useEffect } from "react";
import useGuildStore from "../stores/useGuildStore";

const ROLE_LABELS = {
  planner: "Planner",
  researcher: "Researcher",
  engineer: "Engineer",
  analyst: "Analyst",
  critic: "Critic",
  synthesizer: "Synthesizer",
};

function greet() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning,";
  if (h < 17) return "Good afternoon,";
  if (h < 21) return "Good evening,";
  return "Good night,";
}

function renderGuildResponse(data) {
  const parts = [];
  if (data.contributions) {
    for (const c of data.contributions) {
      const content = (c.content || "").trim();
      if (!content) continue;
      const label = ROLE_LABELS[c.role] || c.role;
      parts.push({ type: "contribution", role: c.role, label, content });
    }
  }
  const synthesis = (data.synthesis || "").trim();
  if (synthesis) {
    parts.push({ type: "synthesis", label: "Synthesis", content: synthesis });
  }
  return parts;
}

export default function MainPanel() {
  const messages = useGuildStore((s) => s.messages);
  const streaming = useGuildStore((s) => s.streaming);
  const addMessage = useGuildStore((s) => s.addMessage);
  const setStreaming = useGuildStore((s) => s.setStreaming);
  const setTask = useGuildStore((s) => s.setTask);
  const clearMessages = useGuildStore((s) => s.clearMessages);
  const [input, setInput] = useState("");
  const responseRef = useRef(null);

  useEffect(() => {
    if (responseRef.current) {
      responseRef.current.scrollTop = responseRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSubmit = async () => {
    const v = input.trim();
    if (!v || streaming) return;
    setInput("");
    setTask(v);
    setStreaming(true);
    addMessage("TASK", v);

    try {
      const res = await fetch("/api/v1/guild/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ objective: v }),
      });
      const d = await res.json();
      const parts = renderGuildResponse(d);
      if (parts.length > 0) {
        for (const p of parts) {
          addMessage(p.type === "synthesis" ? "SYNTH" : "CONTRIB", `[${p.label}] ${p.content}`);
        }
      } else if (d?.error) {
        addMessage("ERROR", d.error);
      } else {
        addMessage("ERROR", "Guild agents ran but returned no content. Set OPENAI_API_KEY or ANTHROPIC_API_KEY to enable LLM responses.");
      }
    } catch {
      addMessage("ERROR", "Could not reach Guild. Is the LLM provider configured?");
    }
    setStreaming(false);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden items-center">
      <div className="text-center pt-6 pb-1">
        <div className="text-accent-light text-sm tracking-wide mb-0.5">{greet()}</div>
        <h2 className="text-[4.5rem] font-extrabold leading-none text-white tracking-tight">Sovereign.</h2>
        <p className="text-txt-dim text-base flex items-center justify-center gap-1.5 mt-1.5">
          The machine is at your service.
          <span className="inline-block w-2 h-2 rounded-full bg-accent-light animate-pulse" />
        </p>
      </div>

      <div className="flex items-center gap-3 max-w-xl w-full mx-auto mt-4 px-5 py-3.5 rounded-full"
        style={{
          background: "rgba(255,255,255,0.05)",
          backdropFilter: "blur(20px)",
          border: "1px solid rgba(255,255,255,0.1)",
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="#7c3aed">
          <path d="M12 2l2 6 6 2-6 2-2 6-2-6-6-2 6-2z" />
        </svg>
        <input
          className="flex-1 bg-transparent border-0 outline-none text-sm text-txt placeholder-txt-dim"
          placeholder="Ask PRADYOS anything..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          disabled={streaming}
        />
        <button
          className="w-9 h-9 rounded-full border-0 cursor-pointer text-white grid place-items-center"
          style={{background: "linear-gradient(135deg, #7c3aed, #a78bfa)"}}
          onClick={handleSubmit}
          disabled={streaming}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {messages.length > 0 && (
        <div className="max-w-xl w-full mx-auto mt-5 flex-1 overflow-hidden flex flex-col rounded-2xl"
          style={{
            background: "rgba(255,255,255,0.05)",
            backdropFilter: "blur(24px) saturate(150%)",
            border: "1px solid rgba(124,58,237,0.2)",
          }}
        >
          <div className="px-4 py-2.5 border-b border-border flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent-light" />
            <span className="text-[0.62rem] tracking-widest font-bold text-accent-light">
              PRADYOS · GUILD RESPONSE
            </span>
            <button
              onClick={clearMessages}
              className="ml-auto text-txt-dim text-[0.6rem] tracking-wider bg-transparent border-0 cursor-pointer hover:text-red-400"
            >
              Clear
            </button>
          </div>
          <div ref={responseRef} className="flex-1 overflow-y-auto p-4 text-left text-xs leading-relaxed max-h-60">
            {messages.map((m, i) => (
              <div key={i} className="mb-2.5">
                {m.role === "TASK" ? (
                  <span className="text-txt-dim italic">&rsaquo; {m.text}</span>
                ) : m.role === "CONTRIB" || m.role === "SYNTH" ? (
                  <div>
                    <span className="text-accent-light text-[0.6rem] font-bold tracking-wider">
                      {m.text.match(/\[(.*?)\]/)?.[1] || m.role}
                    </span>
                    <span className="text-txt-dim ml-1">
                      {m.text.replace(/\[.*?\]\s*/, "")}
                    </span>
                  </div>
                ) : (
                  <div>
                    <span className={`text-[0.6rem] font-bold tracking-wider ${
                      m.role === "ERROR" ? "text-red-400" : "text-purple-300"
                    }`}>
                      [{m.role}]
                    </span>
                    <span className="text-txt-dim ml-1">{m.text}</span>
                  </div>
                )}
              </div>
            ))}
            {streaming && (
              <div className="text-accent-light text-xs animate-pulse">processing...</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
