import { useRef, useEffect } from "react";
import useMetricsStore from "../stores/useMetricsStore";

export default function NetworkGraph() {
  const history = useMetricsStore((s) => s.history);
  const svgRef = useRef(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || history.length < 2) return;
    const w = 300, h = 56;
    const vals = history.map((n) => n.recv);
    const mx = Math.max(...vals, 1);
    const mn = Math.min(...vals, 0);
    const rg = mx - mn || 1;
    const points = vals
      .map((v, i) => `${((i / (vals.length - 1)) * w).toFixed(1)},${(h - ((v - mn) / rg) * (h - 8) - 4).toFixed(1)}`)
      .join(" ");
    svg.innerHTML = `<polyline points="${points}" fill="none" stroke="#7c3aed" stroke-width="2"/>`;
  }, [history]);

  return (
    <>
      <h4 className="text-[0.7rem] tracking-widest uppercase text-txt-dim mb-3 flex justify-between">
        Network <span>⇲</span>
      </h4>
      <svg ref={svgRef} className="w-full h-14" viewBox="0 0 300 56" preserveAspectRatio="none" />
      <div className="flex justify-between text-txt-dim text-[0.72rem] mt-1">
        <span>↓ <b className="text-txt">{(history.length > 0 ? history[history.length - 1].recv : 0).toFixed(1)}</b> Gbps</span>
        <span>↑ <b className="text-txt">{Math.round(history.length > 0 ? history[history.length - 1].sent : 0)}</b> Mbps</span>
      </div>
    </>
  );
}
