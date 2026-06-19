import { useState, useEffect } from "react";
import useUIStore from "../stores/useUIStore";
import useMetricsStore from "../stores/useMetricsStore";

export default function SystemPanel() {
  const open = useUIStore((s) => s.activePage === "system");
  const setPage = useUIStore((s) => s.setActivePage);
  const cpu = useMetricsStore((s) => s.cpu);
  const ram = useMetricsStore((s) => s.ram);
  const disk = useMetricsStore((s) => s.disk);
  const gpu = useMetricsStore((s) => s.gpu);
  const ramUsedGb = useMetricsStore((s) => s.ramUsedGb);
  const ramTotalGb = useMetricsStore((s) => s.ramTotalGb);
  const diskUsedGb = useMetricsStore((s) => s.diskUsedGb);
  const diskTotalGb = useMetricsStore((s) => s.diskTotalGb);
  const [llmInfo, setLlmInfo] = useState({});
  const [health, setHealth] = useState({});
  const [modules, setModules] = useState([]);

  useEffect(() => {
    if (!open) return;
    Promise.all([
      fetch("/api/v1/llm/info").then(r => r.json()).catch(() => ({})),
      fetch("/api/v1/health").then(r => r.json()).catch(() => ({})),
      fetch("/api/v1/codemap/modules?limit=200").then(r => r.json()).catch(() => ([]) ),
    ]).then(([llm, h, mods]) => {
      setLlmInfo(llm);
      setHealth(h);
      setModules(mods?.modules || []);
    });
  }, [open]);

  const moduleList = modules.length > 0 ? modules : [
    "core", "guild", "foresight", "drive", "critic", "causality", "ascent", "reverie",
    "skills", "campaign", "memory_citadel", "sovereign", "aegis", "chronicle_sage",
    "sentinel_watch", "warden_grid", "nexus_weave", "starmap", "prism", "specter"
  ];

  return (
    <div className="p-6 h-full overflow-auto">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-light tracking-wide"><b className="font-bold text-accent-light">System</b></h2>
        <button onClick={() => setPage("chat")} className="text-[0.65rem] px-3 py-1.5 rounded-xl border-0 cursor-pointer"
          style={{background:"rgba(255,255,255,0.08)", color:"#94a3b8"}}>← Back</button>
      </div>

      <div className="grid grid-cols-4 gap-3 mb-4">
        <MiniMeter label="CPU" value={cpu} color="#7c3aed" />
        <MiniMeter label="GPU" value={gpu} color="#6366f1" />
        <MiniMeter label="RAM" value={ram} color="#22c55e" detail={ramTotalGb > 0 ? `${ramUsedGb.toFixed(0)}/${ramTotalGb.toFixed(0)}GB` : ""} />
        <MiniMeter label="DISK" value={disk} color="#f97316" detail={diskTotalGb > 0 ? `${diskUsedGb.toFixed(0)}/${diskTotalGb.toFixed(0)}GB` : ""} />
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-3 rounded-xl" style={{background:"rgba(255,255,255,0.05)", border:"1px solid rgba(124,58,237,0.2)"}}>
          <div className="text-[0.65rem] text-txt-dim">LLM Provider</div>
          <div className="text-sm font-semibold mt-0.5">{llmInfo?.provider || "—"}</div>
          {llmInfo?.model && <div className="text-[0.6rem] text-txt-dim">{llmInfo.model}</div>}
        </div>
        <div className="p-3 rounded-xl" style={{background:"rgba(255,255,255,0.05)", border:"1px solid rgba(124,58,237,0.2)"}}>
          <div className="text-[0.65rem] text-txt-dim">Status</div>
          <div className="text-sm font-semibold mt-0.5 text-green-400">✓ Operational</div>
          {health?.status && <div className="text-[0.6rem] text-txt-dim">{health.status}</div>}
        </div>
      </div>

      <h3 className="text-sm font-semibold text-accent-light mb-2">OS Modules ({moduleList.length})</h3>
      <div className="flex flex-wrap gap-2">
        {moduleList.map((m, i) => (
          <div key={i} className="px-3 py-1.5 rounded-xl text-[0.65rem]"
            style={{background:"rgba(255,255,255,0.05)", border:"1px solid rgba(124,58,237,0.15)"}}>
            {typeof m === "string" ? m : (m.name || m.path || m.id || `mod_${i}`)}
          </div>
        ))}
      </div>
    </div>
  );
}

function MiniMeter({ label, value, color, detail }) {
  return (
    <div className="p-3 rounded-xl text-center" style={{background:"rgba(255,255,255,0.05)", border:"1px solid rgba(124,58,237,0.2)"}}>
      <div className="text-[0.55rem] text-txt-dim tracking-widest">{label}</div>
      <div className="text-lg font-bold mt-0.5" style={{color}}>{Math.round(value)}%</div>
      {detail && <div className="text-[0.5rem] text-txt-dim">{detail}</div>}
    </div>
  );
}
