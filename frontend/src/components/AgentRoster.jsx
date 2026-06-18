import { useState, useEffect } from "react";
import useUIStore from "../stores/useUIStore";

const DEFAULT_AGENTS = [
  { name: "VEGA", role: "Orchestrator", status: "active" },
  { name: "ORION", role: "Engineer", status: "active" },
  { name: "LYRA", role: "Researcher", status: "active" },
  { name: "ATLAS", role: "Operations", status: "active" },
  { name: "NOVA", role: "Analyst", status: "active" },
  { name: "DRACO", role: "Security", status: "active" },
];

export default function AgentRoster() {
  const [agents, setAgents] = useState(DEFAULT_AGENTS);
  const setAgentModal = useUIStore((s) => s.setAgentModal);

  useEffect(() => {
    fetch("/api/v1/guild/agents")
      .then((r) => r.json())
      .then((d) => { if (d?.agents?.length) setAgents(d.agents); })
      .catch(() => {});
  }, []);

  return (
    <>
      <h4 className="text-[0.7rem] tracking-widest uppercase text-txt-dim mb-3 flex justify-between">
        AI Agents <span className="text-accent-light">{agents.length} Active</span>
      </h4>
      <div className="grid grid-cols-2 gap-2">
        {agents.slice(0, 6).map((a) => (
          <div
            key={a.name}
            className="flex items-center gap-2 p-2 rounded-xl bg-glass cursor-pointer hover:bg-accent-soft transition"
            onClick={() => setAgentModal(a.name)}
          >
            <span className="w-7 h-7 rounded-lg grid place-items-center bg-accent-soft text-accent-light text-[0.6rem] font-bold">
              {a.name.slice(0, 2)}
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-[0.68rem] font-bold tracking-wider truncate">{a.name}</div>
              <div className="text-[0.54rem] text-txt-dim tracking-wider truncate">{a.role || ""}</div>
            </div>
            <span
              className="w-1.5 h-1.5 rounded-full ml-auto flex-shrink-0"
              style={{
                background: a.status === "active" ? "#39d98a" : a.status === "error" ? "#ff5f57" : "#febc2e",
                boxShadow: a.status === "active" ? "0 0 6px #39d98a" : "none",
              }}
            />
          </div>
        ))}
      </div>
    </>
  );
}
