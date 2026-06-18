import { useState, useEffect, useCallback } from "react";
import useUIStore from "../stores/useUIStore";

export default function FileBrowser() {
  const open = useUIStore((s) => s.filePanel);
  const toggle = useUIStore((s) => s.toggleFilePanel);
  const [entries, setEntries] = useState([]);
  const [content, setContent] = useState(null);
  const [path, setPath] = useState("~");

  const load = useCallback((p) => {
    setContent(null);
    setPath(p);
    fetch(`/api/v1/files?path=${encodeURIComponent(p)}`)
      .then((r) => r.json())
      .then((d) => { if (d?.entries) setEntries(d.entries.slice(0, 30)); })
      .catch(() => setEntries([]));
  }, []);

  useEffect(() => { if (open) load("~"); }, [open, load]);

  const viewFile = (fp, name) => {
    fetch(`/api/v1/files/content?path=${encodeURIComponent(fp)}`)
      .then((r) => r.json())
      .then((d) => {
        if (d?.content) setContent({ name, content: d.content.slice(0, 5000), path: fp, size: d.size_kb });
        else setContent({ name, content: "(could not read)", path: fp, size: 0 });
      })
      .catch(() => setContent({ name, content: "(error reading file)", path: fp, size: 0 }));
  };

  if (!open) return null;

  return (
    <div className="scrim" onClick={(e) => { if (e.target === e.currentTarget) toggle(); }}>
      <div className="glass w-[600px] max-h-[80vh] overflow-auto p-5">
        <div className="flex justify-between items-start mb-3">
          <h2 className="text-xl font-light">
            <b className="font-bold text-accent-light">Files</b>
            <span className="text-txt-dim text-xs ml-2">{path}</span>
          </h2>
          <button onClick={toggle} className="text-txt-dim cursor-pointer text-xl bg-transparent border-0">✕</button>
        </div>

        {content ? (
          <div>
            <button
              className="text-accent-light text-xs mb-2 bg-transparent border-0 cursor-pointer"
              onClick={() => setContent(null)}
            >
              ← Back to listing
            </button>
            <div className="text-[0.72rem] text-txt-dim mb-2">{content.path} · {content.size} KB</div>
            <pre className="font-mono text-xs leading-relaxed overflow-auto max-h-96 bg-glass p-3 rounded-xl whitespace-pre-wrap">
              {content.content}
            </pre>
            {content.content.length >= 5000 && (
              <div className="text-txt-dim text-[0.68rem] mt-1">(showing first 5000 chars)</div>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-1.5">
            {entries.length === 0 && <div className="text-txt-dim text-xs col-span-2">Loading…</div>}
            {entries.map((e, i) => (
              <div
                key={i}
                className={`flex justify-between p-2 rounded-lg bg-glass cursor-pointer hover:bg-accent-soft transition ${
                  e.is_dir ? "" : "hover:bg-accent-soft"
                }`}
                onClick={() => {
                  if (e.is_dir) {
                    load(path === "~" ? `~/${e.name}` : `${path}/${e.name}`);
                  } else {
                    viewFile(path === "~" ? `~/${e.name}` : `${path}/${e.name}`, e.name);
                  }
                }}
              >
                <span>{e.is_dir ? "🗀" : "🗎"} {e.name}</span>
                <span className="text-txt-dim text-xs">{e.is_dir ? "dir" : `${e.size_kb || 0} KB`}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
