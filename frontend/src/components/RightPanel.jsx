import MetricsBar from "./MetricsBar";
import NetworkGraph from "./NetworkGraph";
import AgentRoster from "./AgentRoster";
import CognitionPanel from "./CognitionPanel";

export default function RightPanel() {
  return (
    <div className="flex flex-col gap-3 h-full overflow-auto pr-0.5">
      <div className="rounded-2xl p-3"
        style={{background: "rgba(255,255,255,0.05)", backdropFilter: "blur(24px) saturate(150%)", border: "1px solid rgba(124,58,237,0.2)"}}>
        <MetricsBar />
      </div>
      <div className="rounded-2xl p-3"
        style={{background: "rgba(255,255,255,0.05)", backdropFilter: "blur(24px) saturate(150%)", border: "1px solid rgba(124,58,237,0.2)"}}>
        <NetworkGraph />
      </div>
      <div className="rounded-2xl p-3"
        style={{background: "rgba(255,255,255,0.05)", backdropFilter: "blur(24px) saturate(150%)", border: "1px solid rgba(124,58,237,0.2)"}}>
        <AgentRoster />
      </div>
      <div className="rounded-2xl p-3"
        style={{background: "rgba(255,255,255,0.05)", backdropFilter: "blur(24px) saturate(150%)", border: "1px solid rgba(124,58,237,0.2)"}}>
        <CognitionPanel />
      </div>
    </div>
  );
}
