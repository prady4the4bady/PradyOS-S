import { useEffect } from "react";
import useUIStore from "./stores/useUIStore";
import TopBar from "./components/TopBar";
import Sidebar from "./components/Sidebar";
import MainPanel from "./components/MainPanel";
import WebSocketHandler from "./components/WebSocketHandler";
import RightPanel from "./components/RightPanel";
import Dock from "./components/Dock";
import LogPanel from "./components/LogPanel";
import SettingsPanel from "./components/SettingsPanel";
import FileBrowser from "./components/FileBrowser";
import AgentModal from "./components/AgentModal";
import WebPanel from "./components/WebPanel";

export default function App() {
  const splash = useUIStore((s) => s.splash);
  const setSplash = useUIStore((s) => s.setSplash);

  useEffect(() => {
    const t = setTimeout(() => setSplash(false), 450);
    return () => clearTimeout(t);
  }, [setSplash]);

  return (
    <div className="h-screen bg-[#0a0a1a] overflow-hidden">
      <WebSocketHandler />
      {splash && (
        <div className="splash" style={{ opacity: splash ? 1 : 0 }}>
          PRADY OS · SOVEREIGN EDITION
        </div>
      )}

      <div
        className="h-full"
        style={{
          display: "grid",
          gridTemplateColumns: "266px 1fr 348px",
          gridTemplateRows: "66px 1fr 92px",
          gridTemplateAreas: `
            "top top top"
            "side main rail"
            "side dock dock"
          `,
          gap: "20px",
          padding: "20px 24px",
        }}
      >
        <div style={{ gridArea: "top" }}><TopBar /></div>
        <div style={{ gridArea: "side" }}><Sidebar /></div>
        <div style={{ gridArea: "main" }}><MainPanel /></div>
        <div style={{ gridArea: "rail" }}><RightPanel /></div>
        <div style={{ gridArea: "dock", justifySelf: "center", alignSelf: "end" }}><Dock /></div>
      </div>

      <LogPanel />
      <SettingsPanel />
      <FileBrowser />
      <AgentModal />
      <WebPanel />
    </div>
  );
}
