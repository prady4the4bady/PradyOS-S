import { useEffect, useRef } from "react";
import useUIStore from "../stores/useUIStore";

export default function LogPanel() {
  const open = useUIStore((s) => s.logPanel);
  const toggle = useUIStore((s) => s.toggleLogPanel);
  const outRef = useRef(null);
  const esRef = useRef(null);

  useEffect(() => {
    if (!open) {
      esRef.current?.close();
      esRef.current = null;
      return;
    }

    const es = new EventSource("/api/v1/system/logs");
    esRef.current = es;
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        const col = d.level === "ERROR" ? "#ff5f57" : d.level === "WARNING" ? "#febc2e" : "#e2e8f0";
        const el = outRef.current;
        if (el) {
          el.innerHTML += `<span style="color:${col}">[${d.level}] ${d.line || d.message || ""}</span>\n`;
          el.scrollTop = el.scrollHeight;
        }
      } catch {}
    };
    return () => { es.close(); esRef.current = null; };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-40 h-52 flex flex-col font-mono text-xs px-4 py-2.5"
      style={{ background: "rgba(20,18,42,0.85)", backdropFilter: "blur(26px)", borderTop: "1px solid rgba(124,58,237,0.2)" }}
    >
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-accent-light text-[0.68rem] tracking-widest" style={{ fontFamily: "Inter, sans-serif" }}>
          LIVE LOG
        </span>
        <button onClick={toggle} className="text-txt-dim cursor-pointer text-lg bg-transparent border-0">
          ✕
        </button>
      </div>
      <div ref={outRef} className="flex-1 overflow-y-auto leading-relaxed whitespace-pre-wrap" style={{ color: "#e2e8f0" }}>
        Connecting to log stream…
      </div>
    </div>
  );
}
