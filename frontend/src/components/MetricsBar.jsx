import useMetricsStore from "../stores/useMetricsStore";

function DonutGauge({ value, label, color = "#7c3aed", detail }) {
  const r = 28, circ = 2 * Math.PI * r;
  const normalized = Math.min(100, Math.max(0, value));
  const offset = circ - (normalized / 100) * circ;
  return (
    <div className="flex flex-col items-center gap-1.5">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="6"/>
        <circle cx="36" cy="36" r={r} fill="none" stroke={color} strokeWidth="6"
          strokeDasharray={circ} strokeDashoffset={offset}
          strokeLinecap="round" transform="rotate(-90 36 36)"
          style={{transition: "stroke-dashoffset 0.6s ease"}}/>
        <text x="36" y="40" textAnchor="middle" fill="white"
          fontSize="13" fontWeight="bold">{Math.round(normalized)}%</text>
      </svg>
      <span className="text-[0.58rem] text-purple-300 tracking-widest font-semibold">{label}</span>
      {detail && <span className="text-[0.5rem] text-txt-dim -mt-1">{detail}</span>}
    </div>
  );
}

export default function MetricsBar() {
  const cpu = useMetricsStore((s) => s.cpu);
  const ram = useMetricsStore((s) => s.ram);
  const ramUsedGb = useMetricsStore((s) => s.ramUsedGb);
  const ramTotalGb = useMetricsStore((s) => s.ramTotalGb);
  const disk = useMetricsStore((s) => s.disk);
  const diskUsedGb = useMetricsStore((s) => s.diskUsedGb);
  const diskTotalGb = useMetricsStore((s) => s.diskTotalGb);
  const gpu = useMetricsStore((s) => s.gpu);

  return (
    <>
      <h4 className="text-[0.7rem] tracking-widest uppercase text-txt-dim mb-4 flex justify-between items-center">
        SYSTEM OVERVIEW
        <span className="text-txt-dim text-xs">⇲</span>
      </h4>
      <div className="grid grid-cols-2 gap-y-5 gap-x-2">
        <DonutGauge value={cpu} label="CPU" color="#7c3aed" />
        <DonutGauge value={gpu} label="GPU" color="#6366f1" />
        <DonutGauge value={ram} label="RAM" color="#22c55e"
          detail={ramTotalGb > 0 ? `${ramUsedGb.toFixed(1)}/${ramTotalGb.toFixed(0)} GB` : ""} />
        <DonutGauge value={disk} label="DISK" color="#f97316"
          detail={diskTotalGb > 0 ? `${diskUsedGb.toFixed(0)}/${diskTotalGb.toFixed(0)} GB` : ""} />
      </div>
    </>
  );
}
