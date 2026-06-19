import { useEffect, useRef } from "react";
import { Terminal as Xterm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import useUIStore from "../stores/useUIStore";

export default function TerminalPanel() {
  const open = useUIStore((s) => s.terminalPanel);
  const toggle = useUIStore((s) => s.toggleTerminalPanel);
  const containerRef = useRef(null);
  const termRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (!open || !containerRef.current) return;
    const term = new Xterm({ cursorBlink: true, fontSize: 13, fontFamily: '"JetBrains Mono","Cascadia Code",monospace', theme: { background: "#0a0a1a", foreground: "#e2e8f0", cursor: "#a78bfa", selectionBackground: "rgba(124,58,237,0.4)" } });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    fit.fit();
    termRef.current = term;

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/terminal`);
    wsRef.current = ws;

    ws.onopen = () => {
      term.write("\x1b[32mPradyOS Terminal\x1b[0m — type 'exit' to close\r\n");
    };
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "output") term.write(msg.data);
      } catch {
        term.write(e.data);
      }
    };
    ws.onclose = () => term.write("\r\n\x1b[31m[Connection closed]\x1b[0m\r\n");
    ws.onerror = () => term.write("\r\n\x1b[31m[Connection error]\x1b[0m\r\n");

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });

    const ro = new ResizeObserver(() => { try { fit.fit(); } catch {} });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      ws.close();
      term.dispose();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="scrim" onClick={(e) => { if (e.target === e.currentTarget) toggle(); }}>
      <div className="rounded-2xl overflow-hidden flex flex-col"
        style={{width: "90vw", height: "80vh", background: "#0a0a1a", border: "1px solid rgba(124,58,237,0.2)"}}>
        <div className="flex justify-between items-center px-4 py-2"
          style={{background: "rgba(255,255,255,0.05)", borderBottom: "1px solid rgba(124,58,237,0.15)"}}>
          <span className="text-[0.7rem] tracking-widest text-purple-300 font-semibold">⚡ TERMINAL</span>
          <button onClick={toggle} className="text-txt-dim cursor-pointer text-lg bg-transparent border-0">✕</button>
        </div>
        <div ref={containerRef} className="flex-1" />
      </div>
    </div>
  );
}
