import useUIStore from "../stores/useUIStore";

const SCORPION = (
  <svg viewBox="0 0 100 100" width="72" height="72">
    <circle cx="50" cy="50" r="46" fill="none" stroke="#7c3aed" strokeOpacity="0.35" strokeWidth="1" />
    <circle cx="50" cy="50" r="40" fill="rgba(124,58,237,0.15)" />
    <path d="M50 16 L60 24 L70 20 L78 30 L50 30 L42 40 L52 46 L60 56 L54 66 L64 72 L60 82 L72 84 L80 78" fill="none" stroke="#a78bfa" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" />
    <line x1="60" y1="24" x2="52" y2="14" stroke="#a78bfa" strokeWidth="1.4" strokeLinecap="round" />
    <line x1="70" y1="20" x2="78" y2="12" stroke="#a78bfa" strokeWidth="1.4" strokeLinecap="round" />
    {[[50,16],[60,24],[70,20],[78,30],[50,30],[42,40],[52,46],[60,56],[54,66],[64,72],[60,82],[72,84],[80,78]].map((p,i) => (
      <circle key={i} cx={p[0]} cy={p[1]} r="2.1" fill="#7c3aed" />
    ))}
    <circle cx="80" cy="78" r="3.2" fill="#7c3aed" />
  </svg>
);

export default function Sidebar() {
  const view = useUIStore((s) => s.view);
  const setView = useUIStore((s) => s.setView);

  return (
    <div className="rounded-2xl p-4 flex flex-col gap-2 h-full"
      style={{background: "rgba(255,255,255,0.05)", backdropFilter: "blur(24px) saturate(150%)", border: "1px solid rgba(124,58,237,0.2)"}}>
      <div className="text-center py-2">
        <div className="flex justify-center">{SCORPION}</div>
        <h1 className="text-xl tracking-[8px] font-light mt-1 pl-2">P R A D Y O S</h1>
        <small className="text-accent-light text-[0.5rem] tracking-[5px] font-bold">SOVEREIGN EDITION</small>
      </div>

      <div
        className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg cursor-pointer transition ${
          view === "sovereign" ? "bg-glass2 border-l-2 border-accent" : "border-l-2 border-transparent"
        }`}
        onClick={() => setView("sovereign")}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" className="text-accent-light">
          <path d="M5 16L3 7l5.5 4L12 5l3.5 6L21 7l-2 9H5z" />
        </svg>
        <span className="text-[0.7rem] font-bold tracking-wider">SOVEREIGN MODE</span>
      </div>

      <div
        className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg cursor-pointer transition ${
          view === "manual" ? "bg-glass2 border-l-2 border-accent" : "border-l-2 border-transparent"
        }`}
        onClick={() => setView("manual")}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" className="text-accent-light">
          <path d="M4 5h16v10H4zM2 17h20v2H2z" />
        </svg>
        <span className="text-[0.7rem] font-bold tracking-wider">MANUAL MODE</span>
      </div>

      <div className="mt-auto p-3 rounded-xl" style={{background: "rgba(255,255,255,0.08)", backdropFilter: "blur(20px)", border: "1px solid rgba(124,58,237,0.2)"}}>
        {view === "sovereign" ? (
          <>
            <h3 className="text-sm font-semibold leading-snug">
              The machine governs.<br />
              <em className="text-accent-light not-italic">You approve.</em>
            </h3>
            <p className="text-txt-dim text-[0.68rem] leading-relaxed mt-1.5">
              PRADYOS operates autonomously to achieve your objectives with precision and intelligence.
            </p>
          </>
        ) : (
          <>
            <h3 className="text-sm font-semibold leading-snug">
              <em className="text-accent-light not-italic">Full control.</em><br />
              All tools. All yours.
            </h3>
            <p className="text-txt-dim text-[0.68rem] leading-relaxed mt-1.5">
              Access your desktop environment with complete freedom and flexibility.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
