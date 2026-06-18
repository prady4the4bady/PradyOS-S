import useUIStore from "../stores/useUIStore";

const SCORPION = (
  <svg viewBox="0 0 100 100" width="80" height="80">
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
    <div className="glass p-5 flex flex-col gap-3 h-full">
      <div className="text-center py-2">
        <div className="flex justify-center">{SCORPION}</div>
        <h1 className="text-2xl tracking-[9px] font-light mt-2 pl-2">PRADYOS</h1>
        <small className="text-accent-light text-[0.58rem] tracking-[6px] font-bold">SOVEREIGN EDITION</small>
      </div>

      <div
        className={`flex items-center gap-3 px-3.5 py-3 rounded-xl cursor-pointer transition ${
          view === "sovereign" ? "bg-glass2 border border-border shadow-sm" : "border border-transparent"
        }`}
        onClick={() => setView("sovereign")}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="text-accent-light">
          <path d="M5 16L3 7l5.5 4L12 5l3.5 6L21 7l-2 9H5z" />
        </svg>
        <span className="text-[0.76rem] font-bold tracking-wider">SOVEREIGN MODE</span>
      </div>

      <div
        className={`flex items-center gap-3 px-3.5 py-3 rounded-xl cursor-pointer transition ${
          view === "manual" ? "bg-glass2 border border-border shadow-sm" : "border border-transparent"
        }`}
        onClick={() => setView("manual")}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="text-accent-light">
          <path d="M4 5h16v10H4zM2 17h20v2H2z" />
        </svg>
        <span className="text-[0.76rem] font-bold tracking-wider">MANUAL MODE</span>
      </div>

      <div className="mt-auto p-3 rounded-xl bg-glass2 border border-border">
        {view === "sovereign" ? (
          <>
            <h3 className="text-base font-semibold leading-snug">
              The machine governs.<br />
              <em className="text-accent-light not-italic">You approve.</em>
            </h3>
            <p className="text-txt-dim text-[0.74rem] leading-relaxed mt-2">
              PRADYOS operates autonomously to achieve your objectives with precision and intelligence.
            </p>
          </>
        ) : (
          <>
            <h3 className="text-base font-semibold leading-snug">
              <em className="text-accent-light not-italic">Full control.</em><br />
              All tools. All yours.
            </h3>
            <p className="text-txt-dim text-[0.74rem] leading-relaxed mt-2">
              Access your desktop environment with complete freedom and flexibility.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
