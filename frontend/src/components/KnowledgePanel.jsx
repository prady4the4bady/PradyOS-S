import { useState, useEffect } from "react";
import useUIStore from "../stores/useUIStore";

export default function KnowledgePanel() {
  const open = useUIStore((s) => s.activePage === "knowledge");
  const setPage = useUIStore((s) => s.setActivePage);
  const [state, setState] = useState({ curiosity: "—", goals: [], insights: [] });
  const [skills, setSkills] = useState([]);
  const [stats, setStats] = useState({});

  useEffect(() => {
    if (!open) return;
    Promise.all([
      fetch("/api/v1/sovereign/state").then(r => r.json()).catch(() => ({})),
      fetch("/api/v1/skills/library?limit=10").then(r => r.json()).catch(() => ({})),
      fetch("/api/v1/guild/stats").then(r => r.json()).catch(() => ({})),
    ]).then(([sov, sk, gs]) => {
      setState({ curiosity: sov?.latest_curiosity || "—", goals: sov?.proposed_goals || [], insights: sov?.insights || [] });
      setSkills(sk?.skills || []);
      setStats(gs);
    });
  }, [open]);

  return (
    <div className="p-6 h-full overflow-auto">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-light tracking-wide"><b className="font-bold text-accent-light">Knowledge</b></h2>
        <button onClick={() => setPage("chat")} className="text-[0.65rem] px-3 py-1.5 rounded-xl border-0 cursor-pointer"
          style={{background:"rgba(255,255,255,0.08)", color:"#94a3b8"}}>← Back</button>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-3 rounded-xl" style={{background:"rgba(255,255,255,0.05)", border:"1px solid rgba(124,58,237,0.2)"}}>
          <div className="text-[0.65rem] text-txt-dim">Projects</div>
          <div className="text-lg font-bold text-accent-light">{stats?.project_count || 0}</div>
        </div>
        <div className="p-3 rounded-xl" style={{background:"rgba(255,255,255,0.05)", border:"1px solid rgba(124,58,237,0.2)"}}>
          <div className="text-[0.65rem] text-txt-dim">Skills</div>
          <div className="text-lg font-bold text-accent-light">{skills.length}</div>
        </div>
        <div className="p-3 rounded-xl" style={{background:"rgba(255,255,255,0.05)", border:"1px solid rgba(124,58,237,0.2)"}}>
          <div className="text-[0.65rem] text-txt-dim">Curiosity</div>
          <div className="text-xs mt-1 text-txt">{state.curiosity}</div>
        </div>
        <div className="p-3 rounded-xl" style={{background:"rgba(255,255,255,0.05)", border:"1px solid rgba(124,58,237,0.2)"}}>
          <div className="text-[0.65rem] text-txt-dim">Contributions</div>
          <div className="text-lg font-bold text-accent-light">{stats?.contributions || 0}</div>
        </div>
      </div>

      {skills.length > 0 && (
        <>
          <h3 className="text-sm font-semibold text-accent-light mb-2">Skills Library ({skills.length})</h3>
          <div className="flex flex-wrap gap-2 mb-4">
            {skills.map((s, i) => (
              <div key={i} className="px-3 py-1.5 rounded-xl text-[0.68rem]"
                style={{background:"rgba(124,58,237,0.1)", border:"1px solid rgba(124,58,237,0.2)"}}>
                {s.name || s.id || `skill_${i}`}
                {s.confidence !== undefined && <span className="text-txt-dim ml-1">({(s.confidence * 100).toFixed(0)}%)</span>}
              </div>
            ))}
          </div>
        </>
      )}

      {state.goals.length > 0 && (
        <>
          <h3 className="text-sm font-semibold text-accent-light mb-2">Proposed Goals ({state.goals.length})</h3>
          <div className="flex flex-col gap-2">
            {state.goals.map((g, i) => (
              <div key={i} className="p-3 rounded-xl" style={{background:"rgba(255,255,255,0.05)"}}>
                <div className="text-[0.72rem]">{g.text}</div>
                <div className="text-[0.55rem] text-txt-dim mt-1">status: {g.status || "proposed"}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
