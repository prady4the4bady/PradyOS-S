import { create } from "zustand";

const useMetricsStore = create((set, get) => ({
  cpu: 0,
  ram: 0,
  ramUsedGb: 0,
  ramTotalGb: 0,
  disk: 0,
  diskUsedGb: 0,
  diskTotalGb: 0,
  diskFreeGb: 0,
  gpu: 0,
  recvMbps: 0,
  sentMbps: 0,
  history: [],
  connected: false,

  updateFromWs: (data) =>
    set((s) => {
      const h = [...s.history, { recv: data.recv_mbps || 0, sent: data.sent_mbps || 0, ts: Date.now() }];
      if (h.length > 42) h.shift();
      return {
        cpu: data.cpu || 0,
        ram: data.ram || 0,
        ramUsedGb: data.ram_used_gb || 0,
        ramTotalGb: data.ram_total_gb || 0,
        disk: data.disk || 0,
        diskUsedGb: data.disk_used_gb || 0,
        diskTotalGb: data.disk_total_gb || 0,
        diskFreeGb: data.disk_free_gb || 0,
        gpu: data.gpu || 0,
        recvMbps: data.recv_mbps || (h.length > 1 ? h[h.length - 1].recv : 0),
        sentMbps: data.sent_mbps || (h.length > 1 ? h[h.length - 1].sent : 0),
        history: h,
        connected: true,
      };
    }),

  setConnected: (v) => set({ connected: v }),
}));

export default useMetricsStore;
