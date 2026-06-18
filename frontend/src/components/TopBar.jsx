import { useState, useEffect } from "react";
import useUIStore from "../stores/useUIStore";

export default function TopBar() {
  const view = useUIStore((s) => s.view);
  const setView = useUIStore((s) => s.setView);
  const setNotificationsOpen = useUIStore((s) => s.setNotificationsOpen);
  const toggleSettings = useUIStore((s) => s.toggleSettings);
  const [time, setTime] = useState("");
  const [date, setDate] = useState("");
  const [tier, setTier] = useState("FREE");

  useEffect(() => {
    const tick = () => {
      const d = new Date();
      setTime(d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: true }));
      setDate(d.toLocaleDateString([], { day: "numeric", month: "long", year: "numeric" }));
    };
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    fetch("/api/v1/license/status")
      .then((r) => r.json())
      .then((d) => setTier(d?.open_mode ? "OPEN" : (d?.tier || "FREE").toUpperCase()))
      .catch(() => {});
  }, []);

  return (
    <div className="flex items-center justify-between px-4 h-full rounded-2xl"
      style={{background: "rgba(5,5,20,0.9)", backdropFilter: "blur(24px)", borderBottom: "1px solid rgba(255,255,255,0.05)"}}>
      <div className="flex items-center gap-3">
        <div className="flex rounded-full p-0.5"
          style={{background: "rgba(255,255,255,0.08)", backdropFilter: "blur(20px)", border: "1px solid rgba(124,58,237,0.2)"}}>
          <button
            className={`px-4 py-1.5 rounded-full text-[0.65rem] font-bold tracking-wider transition ${
              view === "sovereign" ? "bg-purple-900/40 text-accent-light shadow-sm" : "text-txt-dim"
            }`}
            onClick={() => setView("sovereign")}
          >
            SOVEREIGN MODE
          </button>
          <span className="w-9 h-4 rounded-full relative mx-0.5 self-center cursor-pointer"
            style={{background: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.2)"}}
            onClick={() => setView(view === "sovereign" ? "manual" : "sovereign")}
          >
            <span className="absolute w-3.5 h-3.5 rounded-full bg-accent top-0.5 transition-all duration-300"
              style={{left: view === "manual" ? "20px" : "3px"}} />
          </span>
          <button
            className={`px-4 py-1.5 rounded-full text-[0.65rem] font-bold tracking-wider transition ${
              view === "manual" ? "bg-purple-900/40 text-accent-light shadow-sm" : "text-txt-dim"
            }`}
            onClick={() => setView("manual")}
          >
            MANUAL MODE
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2.5">
        <span
          className="text-[0.6rem] font-bold tracking-widest px-3 py-1 rounded-full bg-accent-soft text-accent-light border border-border cursor-pointer"
          onClick={() => (window.location.href = "/billing")}
        >
          {tier}
        </span>

        <button
          className="w-8 h-8 grid place-items-center rounded-xl text-txt hover:bg-glass2 hover:border-border border border-transparent transition"
          onClick={() => {
            fetch("/api/v1/notifications")
              .then((r) => r.json())
              .then((d) => {
                useUIStore.getState().setNotifications(d?.notifications || []);
                setNotificationsOpen(true);
              })
              .catch(() => {});
          }}
          title="Notifications"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0" />
          </svg>
        </button>

        <button className="w-8 h-8 grid place-items-center rounded-xl text-txt hover:bg-glass2 hover:border-border border border-transparent transition" title="Settings" onClick={toggleSettings}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 4.6 7a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V1a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H23a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z" />
          </svg>
        </button>

        <div className="w-8 h-8 rounded-full bg-accent-soft border border-border grid place-items-center text-accent-light cursor-pointer" title="Profile">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="8" r="4" />
            <path d="M4 21a8 8 0 0 1 16 0z" />
          </svg>
        </div>

        <div className="text-right leading-tight">
          <div className="text-xs font-bold">{time}</div>
          <div className="text-[0.6rem] text-txt-dim">{date}</div>
        </div>
      </div>
    </div>
  );
}
