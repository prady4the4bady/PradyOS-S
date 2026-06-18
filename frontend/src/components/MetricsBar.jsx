import { useEffect, useRef } from "react";
import useMetricsStore from "../stores/useMetricsStore";

export default function MetricsBar() {
  const cpu = useMetricsStore((s) => s.cpu);
  const ram = useMetricsStore((s) => s.ram);
  const disk = useMetricsStore((s) => s.disk);
  const gpu = useMetricsStore((s) => s.gpu);

  const rings = [
    { id: "cpu", label: "CPU", value: cpu },
    { id: "gpu", label: "GPU", value: gpu },
    { id: "ram", label: "RAM", value: ram },
    { id: "disk", label: "DISK", value: disk },
  ];

  return (
    <>
      <h4 className="text-[0.7rem] tracking-widest uppercase text-txt-dim mb-3 flex justify-between">
        System Overview <span>⇲</span>
      </h4>
      <div className="grid grid-cols-4 gap-2">
        {rings.map((r) => (
          <div key={r.id} className="text-center">
            <div
              className="ring-value mx-auto"
              style={{ "--v": Math.min(100, Math.max(0, Math.round(r.value))) }}
            >
              <i>{Math.round(r.value)}%</i>
            </div>
            <small className="block text-txt-dim text-[0.6rem] mt-1.5 tracking-wider">{r.label}</small>
          </div>
        ))}
      </div>
    </>
  );
}
