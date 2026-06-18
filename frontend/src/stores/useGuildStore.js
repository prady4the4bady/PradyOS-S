import { create } from "zustand";

const useGuildStore = create((set, get) => ({
  messages: [],
  streaming: false,
  task: "",

  addMessage: (role, text) =>
    set((s) => ({ messages: [...s.messages, { role, text, ts: Date.now() }] })),

  setStreaming: (v) => set({ streaming: v }),

  setTask: (t) => set({ task: t }),

  clearMessages: () => set({ messages: [], task: "" }),
}));

export default useGuildStore;
