import { useState, useEffect, useCallback } from "react";

export default function CognitionPanel() {
  const [state, setState] = useState({ latest_curiosity: "—", proposed_goals: [] });

  const refresh = useCallback(() => {
    fetch("/api/v1/sovereign/state")
      .then((r) => r.json())
      .then((d) => { if (d) setState(d); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 10000);
    return () => clearInterval(iv);
  }, [refresh]);

  const reflectNow = () => {
    fetch("/api/v1/reverie/reflect", { method: "POST" })
      .then(() => setTimeout(refresh, 1000))
      .catch(() => {});
  };

  return (
    <>
      <h4 className="text-[0.7rem] tracking-widest uppercase text-txt-dim mb-3 flex justify-between">
        Cognition <span className="text-accent-light cursor-pointer text-xs" onClick={reflectNow}>⟳ reflect</span>
      </h4>
      <div className="text-[0.72rem] text-txt-dim mb-1">Latest curiosity</div>
      <div className="text-[0.8rem] leading-snug mb-3">{state.latest_curiosity}</div>

      {state.proposed_goals?.length > 0 && (
        <>
          <div className="text-[0.72rem] text-txt-dim mb-1.5">
            Proposed goals <span className="text-accent-light">({state.proposed_goals.length})</span>
          </div>
          <div className="flex flex-col gap-1.5">
            {state.proposed_goals.slice(0, 4).map((g, i) => (
              <div key={i} className="p-2 rounded-xl bg-glass">
                <div className="text-[0.72rem]">{g.text}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
