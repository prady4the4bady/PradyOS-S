import { useEffect, useMemo } from "react";
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

function Starfield() {
  const stars = useMemo(() =>
    Array.from({length: 150}, (_, i) => ({
      id: i, x: Math.random() * 100, y: Math.random() * 60,
      size: Math.random() * 2 + 0.5, opacity: Math.random() * 0.6 + 0.3,
      duration: Math.random() * 3 + 2, delay: Math.random() * 3,
    })), []);
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none" style={{zIndex: 0}}>
      {stars.map(s => (
        <div key={s.id} className="absolute rounded-full bg-white"
          style={{
            left: `${s.x}%`, top: `${s.y}%`,
            width: s.size, height: s.size,
            opacity: s.opacity,
            animation: `twinkle ${s.duration}s ease-in-out ${s.delay}s infinite alternate`
          }}/>
      ))}
    </div>
  );
}

function Mountains() {
  return (
    <div className="absolute bottom-0 left-[5%] right-[5%] pointer-events-none" style={{zIndex: 0}}>
      <svg viewBox="0 0 800 300" preserveAspectRatio="none" className="w-full" style={{height: '200px'}}>
        <defs>
          <radialGradient id="glow" cx="50%" cy="80%" r="50%">
            <stop offset="0%" stopColor="rgba(124,58,237,0.12)" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
        </defs>
        <rect x="0" y="0" width="800" height="200" fill="url(#glow)" />
        <polygon points="0,300 200,70 400,300" fill="#2d1b69" opacity="0.7"/>
        <polygon points="80,300 350,35 580,300" fill="#1e1040" opacity="0.82"/>
        <polygon points="200,300 450,80 680,300" fill="#14102e" opacity="0.92"/>
        <polygon points="350,300 550,120 800,300" fill="#0d0a1f" opacity="1"/>
        <polygon points="550,300 700,160 900,300" fill="#2d1b69" opacity="0.6"/>
      </svg>
    </div>
  );
}

export default function App() {
  const splash = useUIStore((s) => s.splash);
  const setSplash = useUIStore((s) => s.setSplash);

  useEffect(() => {
    const t = setTimeout(() => setSplash(false), 450);
    return () => clearTimeout(t);
  }, [setSplash]);

  return (
    <div className="h-dvh overflow-hidden" style={{background: 'linear-gradient(180deg, #050510 0%, #0a0a2e 50%, #0d0d2b 100%)'}}>
      <Starfield />
      <Mountains />
      <WebSocketHandler />
      {splash && (
        <div className="splash" style={{ opacity: splash ? 1 : 0 }}>
          PRADY OS · SOVEREIGN EDITION
        </div>
      )}

      <div className="relative h-full" style={{zIndex: 1}}>
        <div className="h-full"
          style={{
            display: "grid",
            gridTemplateColumns: "220px 1fr 260px",
            gridTemplateRows: "56px 1fr 96px",
            gridTemplateAreas: `
              "top top top"
              "side main rail"
              "side dock dock"
            `,
            gap: "16px",
            padding: "14px 20px",
          }}
        >
          <div style={{ gridArea: "top" }}><TopBar /></div>
          <div style={{ gridArea: "side" }}><Sidebar /></div>
          <div style={{ gridArea: "main" }}><MainPanel /></div>
          <div style={{ gridArea: "rail" }}><RightPanel /></div>
          <div style={{ gridArea: "dock", justifySelf: "center", alignSelf: "end", marginBottom: "20px" }}><Dock /></div>
        </div>
      </div>

      <LogPanel />
      <SettingsPanel />
      <FileBrowser />
      <AgentModal />
      <WebPanel />
    </div>
  );
}
