import { useState, useEffect } from "react";
import useUIStore from "../stores/useUIStore";

export default function AgentModal() {
  const agentName = useUIStore((s) => s.agentModal);
  const close = useUIStore((s) => s.closeAgentModal);
  const [status, setStatus] = useState(null);

  useEffect(() => {
    if (!agentName) { setStatus(null); return; }
    setStatus(null);
    fetch(`/api/v1/guild/agents/${agentName.toLowerCase()}/status`)
      .then((r) => r.json())
      .then((d) => setStatus(d))
      .catch(() => setStatus({ name: agentName, status: "unavailable", role: "" }));
  }, [agentName]);

  const agents = useUIStore.getState().agentModal;
  if (!agentName) return null;

  return (
    <div className="scrim" onClick={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div className="glass w-[420px] p-6">
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-2xl font-light">
            <b className="font-bold text-accent-light">{agentName}</b>
          </h2>
          <button onClick={close} className="text-txt-dim cursor-pointer text-xl bg-transparent border-0">✕</button>
        </div>
        {!status ? (
          <div className="text-txt-dim text-sm">Loading…</div>
        ) : (
          <div className="space-y-3 text-sm leading-relaxed">
            <Row label="Name" value={status.name || agentName} />
            <Row label="Status" value={status.status || "—"} />
            <Row label="Role" value={status.role || "—"} />
            <Row label="Last action" value={status.last_action || "Awaiting task"} />
            {status.uptime && <Row label="Uptime" value={status.uptime} />}
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-txt-dim">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}
