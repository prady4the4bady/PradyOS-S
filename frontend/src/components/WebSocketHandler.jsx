import { useEffect } from "react";
import useMetricsStore from "../stores/useMetricsStore";

export default function WebSocketHandler() {
  const updateFromWs = useMetricsStore((s) => s.updateFromWs);
  const setConnected = useMetricsStore((s) => s.setConnected);

  useEffect(() => {
    let ws = null;
    let timer = null;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(`${proto}//${location.host}/ws/console`);
      ws.onmessage = (e) => {
        try {
          updateFromWs(JSON.parse(e.data));
        } catch {}
      };
      ws.onclose = () => {
        setConnected(false);
        ws = null;
        clearTimeout(timer);
        timer = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      ws?.close();
      clearTimeout(timer);
    };
  }, []);

  return null;
}
