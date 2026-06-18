import MetricsBar from "./MetricsBar";
import NetworkGraph from "./NetworkGraph";
import AgentRoster from "./AgentRoster";
import CognitionPanel from "./CognitionPanel";
import useUIStore from "../stores/useUIStore";

export default function RightPanel() {
  const view = useUIStore((s) => s.view);

  return (
    <div className="flex flex-col gap-4 h-full overflow-auto pr-1">
      <div className="glass p-4">
        <MetricsBar />
      </div>
      <div className="glass p-4">
        <NetworkGraph />
      </div>
      <div className="glass p-4">
        <AgentRoster />
      </div>
      {view === "sovereign" && (
        <div className="glass p-4">
          <CognitionPanel />
        </div>
      )}
    </div>
  );
}
