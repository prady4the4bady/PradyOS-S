import { useState, useEffect } from "react";
import useUIStore from "../stores/useUIStore";

export default function SettingsPanel() {
  const open = useUIStore((s) => s.settingsPanel);
  const toggle = useUIStore((s) => s.toggleSettings);
  const [data, setData] = useState({ tier: "—", version: "—", payment: "—" });
  const [llmInfo, setLlmInfo] = useState({ provider: "—", model: "—", base_url: "—", has_api_key: false });
  const [configuring, setConfiguring] = useState(false);
  const [llmForm, setLlmForm] = useState({ provider: "ollama", base_url: "", model: "", api_key: "", max_tokens: "", top_p: "" });
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!open) return;
    Promise.all([
      fetch("/api/v1/license/status").then((r) => r.json()).catch(() => ({})),
      fetch("/api/v1/config/public").then((r) => r.json()).catch(() => ({})),
      fetch("/api/v1/llm/info").then((r) => r.json()).catch(() => ({})),
    ]).then(([st, cfg, llm]) => {
      const tier = st?.open_mode ? "UNLOCKED" : ((st?.tier || cfg?.tier || "").toUpperCase() || "FREE");
      setData({ tier, version: cfg?.version || "—", payment: cfg?.payment_provider || "Stripe" });
      setLlmInfo({
        provider: llm?.provider || "—",
        model: llm?.model || "—",
        base_url: llm?.base_url || "—",
        has_api_key: llm?.has_api_key || false,
      });
    });
  }, [open]);

  const saveLlmConfig = async () => {
    setMsg("");
    const body = { provider: llmForm.provider };
    if (llmForm.base_url) body.base_url = llmForm.base_url;
    if (llmForm.model) body.model = llmForm.model;
    if (llmForm.api_key) body.api_key = llmForm.api_key;
    if (llmForm.max_tokens) body.max_tokens = parseInt(llmForm.max_tokens);
    if (llmForm.top_p) body.top_p = parseFloat(llmForm.top_p);
    try {
      const r = await fetch("/api/v1/llm/configure", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
      const result = await r.json();
      if (result.error) { setMsg(`Error: ${result.error}`); return; }
      setMsg("LLM provider configured! Refresh to apply to all agents.");
      setLlmInfo({ provider: result.provider, model: result.model || "—", base_url: result.base_url || "—", has_api_key: result.has_api_key });
      setConfiguring(false);
    } catch (e) {
      setMsg(`Error: ${e.message}`);
    }
  };

  if (!open) return null;

  return (
    <div className="scrim" onClick={(e) => { if (e.target === e.currentTarget) toggle(); }}>
      <div className="glass w-[540px] max-h-[85vh] overflow-auto p-6">
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-2xl font-light tracking-wide">
            <b className="font-bold text-accent-light">Settings</b>
          </h2>
          <button onClick={toggle} className="text-txt-dim cursor-pointer text-xl bg-transparent border-0">✕</button>
        </div>

        {msg && <div className="text-[0.72rem] mb-3 p-2 rounded-xl" style={{background: msg.startsWith("Error") ? "rgba(239,68,68,0.15)" : "rgba(34,197,94,0.15)", color: msg.startsWith("Error") ? "#ef4444" : "#22c55e"}}>{msg}</div>}

        <div className="space-y-3 text-sm leading-relaxed mb-5">
          <h3 className="text-sm font-semibold text-accent-light">System</h3>
          <Row label="Current tier" value={data.tier} />
          <Row label="Version" value={data.version} />
          <Row label="Payment" value={data.payment} />
          <div className="pt-3">
            <button
              className="w-full py-2.5 rounded-xl font-bold text-sm bg-gradient-to-br from-accent to-accent-light text-white border-0 cursor-pointer"
              onClick={() => (window.location.href = "/billing")}
            >Upgrade on /billing →</button>
          </div>
        </div>

        <div className="space-y-3 text-sm leading-relaxed mb-5 pt-4 border-t border-border">
          <h3 className="text-sm font-semibold text-accent-light">LLM Provider</h3>
          <Row label="Provider" value={llmInfo.provider} />
          <Row label="Model" value={llmInfo.model} />
          <Row label="Endpoint" value={llmInfo.base_url} />
          <Row label="API Key" value={llmInfo.has_api_key ? "✓ configured" : "—"} />
          <div className="text-[0.65rem] text-txt-dim mt-1">Configure in .env or use the form below for runtime changes.</div>
        </div>

        {configuring ? (
          <div className="space-y-3 pt-4 border-t border-border">
            <h3 className="text-sm font-semibold text-accent-light">Configure LLM</h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[0.65rem] text-txt-dim block mb-1">Provider</label>
                <select className="w-full p-2 rounded-xl text-sm" style={{background:"rgba(255,255,255,0.08)", border:"1px solid rgba(124,58,237,0.2)", color:"#e2e8f0"}}
                  value={llmForm.provider} onChange={(e) => setLlmForm({...llmForm, provider: e.target.value})}>
                  <option value="ollama">Ollama (local)</option>
                  <option value="nvidia">NVIDIA NIM</option>
                  <option value="openai-compat">OpenAI-compatible</option>
                </select>
              </div>
              <div>
                <label className="text-[0.65rem] text-txt-dim block mb-1">Model</label>
                <input className="w-full p-2 rounded-xl text-sm"
                  style={{background:"rgba(255,255,255,0.08)", border:"1px solid rgba(124,58,237,0.2)", color:"#e2e8f0"}}
                  placeholder="meta/llama-3.3-70b-instruct"
                  value={llmForm.model} onChange={(e) => setLlmForm({...llmForm, model: e.target.value})} />
              </div>
              <div className="col-span-2">
                <label className="text-[0.65rem] text-txt-dim block mb-1">Base URL</label>
                <input className="w-full p-2 rounded-xl text-sm"
                  style={{background:"rgba(255,255,255,0.08)", border:"1px solid rgba(124,58,237,0.2)", color:"#e2e8f0"}}
                  placeholder="https://integrate.api.nvidia.com/v1"
                  value={llmForm.base_url} onChange={(e) => setLlmForm({...llmForm, base_url: e.target.value})} />
              </div>
              <div className="col-span-2">
                <label className="text-[0.65rem] text-txt-dim block mb-1">API Key</label>
                <input className="w-full p-2 rounded-xl text-sm" type="password"
                  style={{background:"rgba(255,255,255,0.08)", border:"1px solid rgba(124,58,237,0.2)", color:"#e2e8f0"}}
                  placeholder="nvapi-..." value={llmForm.api_key} onChange={(e) => setLlmForm({...llmForm, api_key: e.target.value})} />
              </div>
            </div>
            <div className="flex gap-2 pt-2">
              <button className="flex-1 py-2 rounded-xl font-bold text-sm bg-gradient-to-br from-accent to-accent-light text-white border-0 cursor-pointer"
                onClick={saveLlmConfig}>Save</button>
              <button className="py-2 px-4 rounded-xl text-sm border-0 cursor-pointer"
                style={{background:"rgba(255,255,255,0.08)", color:"#94a3b8"}}
                onClick={() => setConfiguring(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <div className="pt-2">
            <button className="w-full py-2.5 rounded-xl font-bold text-sm border-0 cursor-pointer"
              style={{background:"rgba(255,255,255,0.08)", color:"#a78bfa"}}
              onClick={() => setConfiguring(true)}>⚙ Change LLM Provider</button>
          </div>
        )}
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
