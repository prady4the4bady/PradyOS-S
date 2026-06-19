import useUIStore from "../stores/useUIStore";
import useGuildStore from "../stores/useGuildStore";

const Ico = ({ path, viewBox }) => (
  <svg width="18" height="18" viewBox={viewBox || "0 0 24 24"} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {path}
  </svg>
);

const icons = {
  plus: <Ico path={<><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></>} />,
  terminal: <Ico path={<><polyline points="4 6 10 12 4 18" /><line x1="14" y1="18" x2="20" y2="18" /></>} />,
  folder: <Ico path={<path d="M3 7h6l2 2h10v10H3z" />} />,
  globe: <Ico path={<><circle cx="12" cy="12" r="9" /><line x1="3" y1="12" x2="21" y2="12" /><path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18" /></>} />,
  activity: <Ico path={<polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />} />,
  trash: <Ico path={<><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></>} />,
  book: <Ico path={<><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></>} />,
  cpu: <Ico path={<><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="14" x2="23" y2="14" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="14" x2="4" y2="14" /></>} />,
};

export default function Dock() {
  const activePage = useUIStore((s) => s.activePage);
  const setPage = useUIStore((s) => s.setActivePage);
  const clearMessages = useGuildStore((s) => s.clearMessages);
  const toggleLogPanel = useUIStore((s) => s.toggleLogPanel);
  const toggleFilePanel = useUIStore((s) => s.toggleFilePanel);
  const toggleWebPanel = useUIStore((s) => s.toggleWebPanel);
  const toggleTerminalPanel = useUIStore((s) => s.toggleTerminalPanel);

  const newSession = async () => {
    try { await fetch("/api/v1/session/new", { method: "POST" }); } catch {}
    clearMessages();
  };

  const clearSession = async () => {
    try { await fetch("/api/v1/session/clear", { method: "POST" }); } catch {}
    clearMessages();
  };

  const btnClass = (page) =>
    `w-11 h-11 rounded-xl grid place-items-center cursor-pointer transition border ${
      activePage === page
        ? "text-accent-light bg-accent-soft border-accent"
        : "text-txt-dim hover:text-accent-light hover:bg-accent-soft hover:border-accent bg-glass2 border-border"
    }`;

  const dockButtons = [
    { icon: "plus", label: "New Session", action: newSession },
    { icon: "book", label: "Projects", page: "projects" },
    { icon: "terminal", label: "Terminal", action: toggleTerminalPanel },
    { icon: "folder", label: "Files", action: toggleFilePanel },
    { icon: "globe", label: "Web Search", action: toggleWebPanel },
    { icon: "cpu", label: "System", page: "system" },
    { icon: "activity", label: "Knowledge", page: "knowledge" },
    { icon: "trash", label: "Clear Session", action: clearSession },
  ];

  return (
    <nav className="glass flex gap-2.5 px-5 py-3 rounded-2xl mb-1">
      {dockButtons.map((item) => (
        <button
          key={item.label}
          title={item.label}
          onClick={item.page ? () => setPage(item.page) : item.action}
          className={item.page ? btnClass(item.page) : "w-11 h-11 rounded-xl grid place-items-center cursor-pointer transition text-txt-dim hover:text-accent-light hover:bg-accent-soft hover:border-accent bg-glass2 border border-border"}
        >
          {icons[item.icon]}
        </button>
      ))}
    </nav>
  );
}
