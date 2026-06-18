import { create } from "zustand";

const useUIStore = create((set) => ({
  view: "sovereign",
  splash: true,
  logPanel: false,
  settingsPanel: false,
  filePanel: false,
  agentModal: null,
  webPanel: false,
  notificationOpen: false,
  notifications: [],

  setView: (v) => set({ view: v }),
  setSplash: (v) => set({ splash: v }),
  toggleLogPanel: () => set((s) => ({ logPanel: !s.logPanel })),
  toggleSettings: () => set((s) => ({ settingsPanel: !s.settingsPanel })),
  toggleFilePanel: () => set((s) => ({ filePanel: !s.filePanel })),
  setAgentModal: (name) => set({ agentModal: name }),
  closeAgentModal: () => set({ agentModal: null }),
  toggleWebPanel: () => set((s) => ({ webPanel: !s.webPanel })),
  setNotificationsOpen: (v) => set({ notificationOpen: v }),
  setNotifications: (items) => set({ notifications: items }),
}));

export default useUIStore;
