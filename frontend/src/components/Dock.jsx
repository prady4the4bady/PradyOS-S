import useUIStore from "../stores/useUIStore";
import useGuildStore from "../stores/useGuildStore";

export default function Dock() {
  const setView = useUIStore((s) => s.setView);
  const clearMessages = useGuildStore((s) => s.clearMessages);
  const toggleLogPanel = useUIStore((s) => s.toggleLogPanel);
  const toggleFilePanel = useUIStore((s) => s.toggleFilePanel);
  const toggleWebPanel = useUIStore((s) => s.toggleWebPanel);

  const items = [
    { icon: "star", title: "PRADYOS — new session", primary: true, onClick: () => { clearMessages(); setView("sovereign"); } },
    { icon: "terminal", title: "Terminal / Logs", onClick: toggleLogPanel },
    { icon: "folder", title: "Files", onClick: toggleFilePanel },
    { icon: "globe", title: "Browser", onClick: toggleWebPanel },
    { icon: "shield", title: "Agent Center", onClick: () => useUIStore.getState().setAgentModal("VEGA") },
    { icon: "chart", title: "System Monitor", onClick: () => setView("manual") },
    { icon: "trash", title: "Clear session", onClick: clearMessages },
  ];

  const iconSvgs = {
    star: <path d="M12 2l2 6 6 2-6 2-2 6-2-6-6-2 6-2z" />,
    terminal: <><path d="M4 6l5 6-5 6" /><path d="M12 18h8" /></>,
    folder: <path d="M3 7h6l2 2h10v10H3z" />,
    globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18" /></>,
    shield: <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" />,
    chart: <path d="M3 12h4l2-6 4 12 2-6h6" />,
    trash: <><path d="M5 7h14" /><path d="M9 7V4h6v3" /><path d="M6 7l1 13h10l1-13" /></>,
  };

  return (
    <nav className="glass flex gap-2.5 px-3.5 py-2.5 rounded-2xl mb-1">
      {items.map((item) => (
        <button
          key={item.title}
          title={item.title}
          onClick={item.onClick}
          className={`w-11 h-11 rounded-xl grid place-items-center cursor-pointer transition text-txt hover:-translate-y-3 hover:scale-110 hover:text-accent-light hover:border-accent ${
            item.primary
              ? "bg-gradient-to-br from-accent to-accent-light text-white border-0 shadow-lg"
              : "bg-glass2 border border-border"
          }`}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill={item.primary ? "currentColor" : "none"} stroke={item.primary ? "none" : "currentColor"} strokeWidth="1.6">{iconSvgs[item.icon]}</svg>
        </button>
      ))}
    </nav>
  );
}
