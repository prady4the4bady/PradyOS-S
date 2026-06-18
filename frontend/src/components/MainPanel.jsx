import { useState } from "react";
import useUIStore from "../stores/useUIStore";
import useGuildStore from "../stores/useGuildStore";

function greet() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning,";
  if (h < 17) return "Good afternoon,";
  if (h < 21) return "Good evening,";
  return "Good night,";
}

export default function MainPanel() {
  const view = useUIStore((s) => s.view);
  const setView = useUIStore((s) => s.setView);
  const messages = useGuildStore((s) => s.messages);
  const streaming = useGuildStore((s) => s.streaming);
  const addMessage = useGuildStore((s) => s.addMessage);
  const setStreaming = useGuildStore((s) => s.setStreaming);
  const setTask = useGuildStore((s) => s.setTask);
  const [input, setInput] = useState("");
  const [gs, setGs] = useState("");

  const handleSubmit = async () => {
    const v = input.trim();
    if (!v || streaming) return;
    setInput("");
    setGs(v);
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
      if (d?.synthesis) {
        addMessage("SYNTH", d.synthesis);
      } else if (d?.summary) {
        addMessage("SYNTH", d.summary);
      } else if (d?.error) {
        addMessage("ERROR", d.error);
      } else {
        addMessage("SYNTH", JSON.stringify(d, null, 1).slice(0, 600));
      }
    } catch {
      addMessage("ERROR", "Could not reach Guild. Is the LLM provider configured?");
    }
    setStreaming(false);
  };

  if (view === "sovereign") {
    return (
      <div className="flex flex-col h-full overflow-auto">
        <div className="text-center pt-6 pb-3">
          <div className="flex items-center justify-center gap-2 text-accent-light text-sm tracking-wide">
            ☀ <span>{greet()}</span>
          </div>
          <h2 className="text-5xl font-extralight tracking-wide my-1">
            <span className="font-bold">Sovereign.</span>
          </h2>
          <p className="text-txt-dim text-base">The machine is at your service.</p>
        </div>

        <div className="glass flex items-center gap-3 max-w-lg mx-auto my-5 px-5 py-3.5 rounded-full">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="#7c3aed">
            <path d="M12 2l2 6 6 2-6 2-2 6-2-6-6-2 6-2z" />
          </svg>
          <input
            className="flex-1 bg-transparent border-0 outline-none text-base text-txt placeholder-txt-dim"
            placeholder="Ask PRADYOS anything..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            disabled={streaming}
          />
          <button
            className="w-10 h-10 rounded-full border-0 cursor-pointer text-white text-lg bg-gradient-to-br from-accent to-accent-light shadow-lg"
            onClick={handleSubmit}
            disabled={streaming}
          >
            →
          </button>
        </div>

        {messages.length > 0 && (
          <div className="glass max-w-lg mx-auto mb-6 p-4 text-left text-sm leading-relaxed overflow-auto max-h-80">
            {messages.map((m, i) => (
              <div key={i} className="mb-2">
                <span className={`text-xs font-bold tracking-wider ${
                  m.role === "ERROR" ? "text-red-400" :
                  m.role === "SYNTH" ? "text-accent-light" :
                  m.role === "TASK" ? "text-txt-dim" :
                  "text-purple-300"
                }`}>
                  [{m.role}]{" "}
                </span>
                <span className="text-txt-dim text-xs">{m.text}</span>
              </div>
            ))}
            {streaming && (
              <div className="text-accent-light text-xs animate-pulse">▰▰▰ working...</div>
            )}
          </div>
        )}

        <div className="grid grid-cols-3 gap-3 max-w-2xl mx-auto">
          <AppButton icon="terminal" label="AI Terminal" />
          <AppButton icon="folder" label="Files" onClick={() => setView("manual")} />
          <AppButton icon="chart" label="System Monitor" onClick={() => setView("manual")} />
          <AppButton icon="shield" label="Agent Center" onClick={() => useUIStore.getState().setAgentModal("VEGA")} />
          <AppButton icon="project" label="Projects" onClick={showProjects} />
          <AppButton icon="report" label="Reports" onClick={showReports} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 h-full overflow-auto">
      <div className="glass">
        <div className="flex items-center gap-2 px-3.5 py-2.5 bg-glass2 border-b border-border text-xs">
          <span className="w-2.5 h-2.5 rounded-full bg-red-400" />
          <span className="w-2.5 h-2.5 rounded-full bg-yellow-300" />
          <span className="w-2.5 h-2.5 rounded-full bg-green-400" />
          &nbsp;&nbsp;PRISM Terminal — System Info
        </div>
        <div className="p-4 font-mono text-xs leading-relaxed text-accent-light">
          <TermLine label="OS" value="PRADYOS Sovereign Edition" />
          <TermLine label="Kernel" value="6.x" />
          <TermLine label="Shell" value="PRISM" />
          <TermLine label="Host" value="pradyos-server" />
          <div className="mt-1 text-txt-dim">sovereign@pradyos ~ ▮</div>
        </div>
      </div>
    </div>
  );
}

function AppButton({ icon, label, onClick }) {
  const icons = {
    terminal: <path d="M4 6l5 6-5 6M12 18h8" />,
    folder: <path d="M3 7h6l2 2h10v10H3z" />,
    chart: <path d="M3 12h4l2-6 4 12 2-6h6" />,
    shield: <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" />,
    project: <path d="M4 5h7l2 3h7v11H4z" />,
    report: <path d="M6 3h9l3 3v15H6zM9 12h6M9 16h6" />,
  };
  return (
    <div
      className="flex flex-col items-center gap-2 p-4 rounded-xl bg-glass2 border border-border cursor-pointer transition hover:-translate-y-1 hover:shadow-xl hover:border-accent"
      onClick={onClick}
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="text-accent-light">
        {icons[icon]}
      </svg>
      <span className="text-[0.68rem] font-semibold tracking-wider text-center">{label}</span>
    </div>
  );
}

function TermLine({ label, value }) {
  return (
    <div>
      <span className="text-purple-300">{label}</span>: <span className="text-txt-dim">{value}</span>
    </div>
  );
}

function showProjects() {
  const el = document.getElementById("splash");
  if (el) { el.textContent = "▸ Projects"; el.style.opacity = "1"; el.style.display = "grid"; setTimeout(() => { el.style.opacity = "0"; setTimeout(() => { el.style.display = "none"; }, 700); }, 650); }
}

function showReports() {
  const el = document.getElementById("splash");
  if (el) { el.textContent = "▸ Reports"; el.style.opacity = "1"; el.style.display = "grid"; setTimeout(() => { el.style.opacity = "0"; setTimeout(() => { el.style.display = "none"; }, 700); }, 650); }
}
