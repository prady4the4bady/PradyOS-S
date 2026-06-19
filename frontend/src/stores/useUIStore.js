import { create } from "zustand";

const useUIStore = create((set) => ({
  view: "sovereign",
  splash: true,
  activePage: "chat",
  logPanel: false,
  settingsPanel: false,
  filePanel: false,
  agentModal: null,
  webPanel: false,
  terminalPanel: false,
  notificationOpen: false,
  notifications: [],

  setView: (v) => set({ view: v }),
  setSplash: (v) => set({ splash: v }),
  setActivePage: (p) => set({ activePage: p }),
  toggleLogPanel: () => set((s) => ({ logPanel: !s.logPanel })),
  toggleSettings: () => set((s) => ({ settingsPanel: !s.settingsPanel })),
  toggleFilePanel: () => set((s) => ({ filePanel: !s.filePanel })),
  toggleTerminalPanel: () => set((s) => ({ terminalPanel: !s.terminalPanel })),
  setAgentModal: (name) => set({ agentModal: name }),
  closeAgentModal: () => set({ agentModal: null }),
  toggleWebPanel: () => set((s) => ({ webPanel: !s.webPanel })),
  setNotificationsOpen: (v) => set({ notificationOpen: v }),
  setNotifications: (items) => set({ notifications: items }),
}));

export default useUIStore;
