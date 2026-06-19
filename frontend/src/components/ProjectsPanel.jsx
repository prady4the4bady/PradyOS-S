import { useState, useEffect } from "react";
import useUIStore from "../stores/useUIStore";

export default function ProjectsPanel() {
  const open = useUIStore((s) => s.activePage === "projects");
  const setPage = useUIStore((s) => s.setActivePage);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    fetch("/api/v1/guild/projects?limit=20")
      .then((r) => r.json())
      .then((d) => { setProjects(d?.projects || []); setLoading(false); })
      .catch(() => { setProjects([]); setLoading(false); });
  }, [open]);

  return (
    <div className="p-6 h-full overflow-auto">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-light tracking-wide">
          <b className="font-bold text-accent-light">Projects</b>
          <span className="text-txt-dim text-sm ml-2">{projects.length > 0 ? `(${projects.length})` : ""}</span>
        </h2>
        <button onClick={() => setPage("chat")} className="text-[0.65rem] px-3 py-1.5 rounded-xl border-0 cursor-pointer"
          style={{background:"rgba(255,255,255,0.08)", color:"#94a3b8"}}>← Back</button>
      </div>

      {loading && <div className="text-txt-dim text-center py-8">Loading projects...</div>}

      {!loading && projects.length === 0 && (
        <div className="text-center py-12">
          <div className="text-4xl mb-3 opacity-30">📂</div>
          <div className="text-txt-dim">No projects yet</div>
          <div className="text-txt-dim text-[0.72rem] mt-2">Ask PRADYOS something to create a project.</div>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {projects.map((p, i) => (
          <div key={p.id || i} className="p-4 rounded-2xl"
            style={{background: "rgba(255,255,255,0.05)", backdropFilter: "blur(24px) saturate(150%)", border: "1px solid rgba(124,58,237,0.2)"}}>
            <div className="flex justify-between items-start mb-2">
              <h3 className="text-sm font-semibold">{p.objective || "Untitled"}</h3>
              <span className="text-[0.6rem] px-2 py-0.5 rounded-full"
                style={{background: p.status === "completed" ? "rgba(34,197,94,0.15)" : "rgba(251,191,36,0.15)", color: p.status === "completed" ? "#22c55e" : "#fbbf24"}}>
                {p.status || "unknown"}
              </span>
            </div>
            {p.synthesis && <div className="text-[0.72rem] text-txt-dim leading-relaxed mb-2">{p.synthesis}</div>}
            {p.contributions && p.contributions.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {p.contributions.map((c, j) => (
                  <span key={j} className="text-[0.55rem] px-2 py-0.5 rounded-full"
                    style={{background:"rgba(124,58,237,0.1)", color:"#a78bfa"}}>{c.role || "agent"}</span>
                ))}
              </div>
            )}
            <div className="text-[0.55rem] text-txt-dim mt-2">
              {p.created_at ? new Date(p.created_at).toLocaleString() : ""}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
