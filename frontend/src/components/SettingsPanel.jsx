import { useState, useEffect } from "react";
import useUIStore from "../stores/useUIStore";

export default function SettingsPanel() {
  const open = useUIStore((s) => s.settingsPanel);
  const toggle = useUIStore((s) => s.toggleSettings);
  const [data, setData] = useState({ tier: "—", version: "—", payment: "—" });

  useEffect(() => {
    if (!open) return;
    Promise.all([
      fetch("/api/v1/license/status").then((r) => r.json()).catch(() => ({})),
      fetch("/api/v1/config/public").then((r) => r.json()).catch(() => ({})),
    ]).then(([st, cfg]) => {
      const tier = st?.open_mode ? "OPEN" : ((st?.tier || cfg?.tier || "").toUpperCase() || "FREE");
      setData({ tier, version: cfg?.version || "—", payment: cfg?.payment_provider || "Stripe" });
    });
  }, [open]);

  if (!open) return null;

  return (
    <div className="scrim" onClick={(e) => { if (e.target === e.currentTarget) toggle(); }}>
      <div className="glass w-[500px] max-h-[80vh] overflow-auto p-6">
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-2xl font-light tracking-wide">
            <b className="font-bold text-accent-light">Settings</b>
          </h2>
          <button onClick={toggle} className="text-txt-dim cursor-pointer text-xl bg-transparent border-0">✕</button>
        </div>
        <div className="space-y-3 text-sm leading-relaxed">
          <Row label="Current tier" value={data.tier} />
          <Row label="Version" value={data.version} />
          <Row label="Payment" value={data.payment} />
          <div className="pt-3 border-t border-border">
            <button
              className="w-full py-2.5 rounded-xl font-bold text-sm bg-gradient-to-br from-accent to-accent-light text-white border-0 cursor-pointer"
              onClick={() => (window.location.href = "/billing")}
            >
              Upgrade on /billing →
            </button>
          </div>
        </div>
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
