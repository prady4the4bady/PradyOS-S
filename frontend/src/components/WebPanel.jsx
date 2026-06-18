import { useState } from "react";
import useUIStore from "../stores/useUIStore";

export default function WebPanel() {
  const open = useUIStore((s) => s.webPanel);
  const toggle = useUIStore((s) => s.toggleWebPanel);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setResults(null);
    try {
      const res = await fetch(`/api/v1/web/search?q=${encodeURIComponent(query)}`);
      const d = await res.json();
      setResults(d);
    } catch {
      setResults({ error: "Search endpoint unavailable. Requires configured web agent." });
    }
    setLoading(false);
  };

  if (!open) return null;

  return (
    <div className="scrim" onClick={(e) => { if (e.target === e.currentTarget) toggle(); }}>
      <div className="glass w-[600px] max-h-[80vh] overflow-auto p-6">
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-2xl font-light">
            <b className="font-bold text-accent-light">Web Search</b>
          </h2>
          <button onClick={toggle} className="text-txt-dim cursor-pointer text-xl bg-transparent border-0">✕</button>
        </div>
        <div className="flex gap-2 mb-4">
          <input
            className="flex-1 bg-glass2 border border-border rounded-xl px-4 py-2.5 text-sm text-txt outline-none placeholder-txt-dim"
            placeholder="Search the web…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
          />
          <button
            className="px-4 py-2 rounded-xl bg-gradient-to-br from-accent to-accent-light text-white font-bold text-sm border-0 cursor-pointer"
            onClick={search}
            disabled={loading}
          >
            {loading ? "…" : "Search"}
          </button>
        </div>
        {results && (
          <div className="text-sm text-txt-dim">
            {results.error ? (
              <div>{results.error}</div>
            ) : (
              <pre className="font-mono text-xs whitespace-pre-wrap">{JSON.stringify(results, null, 1).slice(0, 2000)}</pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
