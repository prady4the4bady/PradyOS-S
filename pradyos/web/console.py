"""PRADYOS — Sovereign Command Console (the OS shell served at ``/``).

A single, self-contained, **offline** page (no CDN, no build step) that renders
the OS face: the scorpion emblem, dual SOVEREIGN/MANUAL views, and the four
time-of-day themes (dawn / day / dusk / night) switched **automatically from the
clock** so both views share the same palette at all times.

This is the *shell* of a real OS, not a web-terminal wrapper: every panel binds
to a live OS endpoint —

  * ``/api/v1/system/metrics``  → real CPU / RAM / disk / net (psutil),
  * ``/api/v1/system/info``     → real neofetch (kernel, host, uptime, …),
  * ``/api/v1/system/processes``→ real top processes (System Monitor),
  * ``/api/v1/files``           → the real filesystem (File Manager),
  * ``/api/v1/guild/roles``     → the live agent roster,
  * ``/api/v1/license/*``       → tier + price book,
  * ``/stream``                 → the live event bus,

and degrades to sensible placeholders when a route is absent, so the shell is
always alive. The scene is drawn procedurally (gradients + SVG), not from any
external image asset.

The HTML is exposed as :data:`CONSOLE_HTML` and served by ``sovereign_web``.
"""

from __future__ import annotations

# "PRADY OS" appears in the splash so the brand-presence test keeps passing.

CONSOLE_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="night" data-view="sovereign">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PRADYOS — Sovereign Command Console</title>
<style>
  :root{
    --r:20px; --r-sm:13px;
    --font:'Segoe UI',Inter,system-ui,-apple-system,sans-serif;
    --mono:'JetBrains Mono','Cascadia Code','Courier New',monospace;
    --ease:cubic-bezier(.4,0,.2,1);
  }
  /* ===================== TIME-OF-DAY PALETTES ===================== */
  html[data-theme="night"]{
    --sky:radial-gradient(130% 100% at 78% -16%,#46377f 0%,#241c4d 34%,#120e2c 64%,#080615 100%);
    --accent:#9d8cff; --accent2:#c8b0ff; --accent-soft:rgba(157,140,255,.16);
    --glass:rgba(20,18,42,.46); --glass2:rgba(30,26,60,.60); --brd:rgba(160,140,255,.20);
    --txt:#eeebff; --dim:#9c97cc; --shadow:0 24px 60px rgba(0,0,0,.55);
    --sun:#d8ccff; --sun-glow:rgba(200,180,255,.55); --planet:#5a4a9a; --planet2:#3a2f6a;
    --m1:#241d4a; --m2:#1b1638; --m3:#130f29; --m4:#0c091c;
    --water:#15112e; --water-hi:rgba(180,160,255,.30); --cloud:0; --stars:1;
  }
  html[data-theme="dawn"]{
    --sky:linear-gradient(180deg,#bfe2ee 0%,#cfe0ec 26%,#e7dced 52%,#f6dbe0 74%,#ffe6c9 100%);
    --accent:#13a79c; --accent2:#42cabd; --accent-soft:rgba(19,167,156,.14);
    --glass:rgba(244,251,252,.50); --glass2:rgba(255,255,255,.60); --brd:rgba(20,120,116,.16);
    --txt:#103a40; --dim:#4f6e72; --shadow:0 22px 54px rgba(70,120,128,.20);
    --sun:#fff0d6; --sun-glow:rgba(255,212,170,.6); --planet:#cfe2e2; --planet2:#b6d4d4;
    --m1:#a9cfd2; --m2:#94c0c4; --m3:#7caeb3; --m4:#5f969c;
    --water:#bcdde0; --water-hi:rgba(255,235,205,.55); --cloud:.7; --stars:0;
  }
  html[data-theme="day"]{
    --sky:linear-gradient(180deg,#8cc4ff 0%,#a9d2ff 30%,#cae3ff 60%,#e6f2ff 82%,#f5fbff 100%);
    --accent:#2f86ff; --accent2:#6fb0ff; --accent-soft:rgba(47,134,255,.12);
    --glass:rgba(255,255,255,.50); --glass2:rgba(255,255,255,.64); --brd:rgba(60,110,180,.14);
    --txt:#0e2747; --dim:#4a6086; --shadow:0 22px 54px rgba(70,120,190,.18);
    --sun:#fff6dc; --sun-glow:rgba(255,235,170,.7); --planet:#d6e7fb; --planet2:#bcd6f5;
    --m1:#bdd9f2; --m2:#a6cae8; --m3:#8bb8de; --m4:#6ea2d2;
    --water:#aed3f2; --water-hi:rgba(255,250,220,.6); --cloud:1; --stars:0;
  }
  html[data-theme="dusk"]{
    --sky:linear-gradient(180deg,#231a47 0%,#46264f 30%,#8a3b58 52%,#d85f4e 72%,#ff9550 88%,#ffc279 100%);
    --accent:#ff8a3d; --accent2:#ffce8a; --accent-soft:rgba(255,138,61,.16);
    --glass:rgba(38,22,32,.44); --glass2:rgba(54,30,40,.58); --brd:rgba(255,150,90,.22);
    --txt:#fff1e8; --dim:#e6c3b1; --shadow:0 24px 60px rgba(40,10,20,.5);
    --sun:#ffd9a0; --sun-glow:rgba(255,150,80,.65); --planet:#6e3a52; --planet2:#4a2440;
    --m1:#3a1f3e; --m2:#2a1530; --m3:#1d0e26; --m4:#12081b;
    --water:#3a1c2e; --water-hi:rgba(255,170,90,.6); --cloud:.5; --stars:.4;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%}
  body{font-family:var(--font);color:var(--txt);overflow:hidden;background:var(--sky);
    transition:background 1.4s var(--ease),color .7s var(--ease)}
  /* ===================== PROCEDURAL SCENE ===================== */
  #scene{position:fixed;inset:0;z-index:0;width:100%;height:100%}
  #scene .sun{fill:var(--sun)} #scene .glow{fill:var(--sun-glow)}
  #scene .planet{fill:var(--planet)} #scene .ring{stroke:var(--planet2)}
  #scene .m1{fill:var(--m1)} #scene .m2{fill:var(--m2)} #scene .m3{fill:var(--m3)} #scene .m4{fill:var(--m4)}
  #scene .water{fill:var(--water)} #scene .cloud{fill:#fff;opacity:var(--cloud)}
  #scene .bird{stroke:var(--m4);opacity:.5}
  #scene .beam{stop-color:var(--water-hi)}
  .stars{position:fixed;inset:0 0 40% 0;z-index:0;opacity:var(--stars);transition:opacity 1.4s var(--ease)}
  .stars i{position:absolute;width:2px;height:2px;border-radius:50%;background:#fff;box-shadow:0 0 5px #fff;
    animation:tw 3.5s var(--ease) infinite}
  @keyframes tw{0%,100%{opacity:.2}50%{opacity:1}}
  @keyframes drift{from{transform:translateX(-4%)}to{transform:translateX(4%)}}
  /* ===================== SHELL GRID ===================== */
  .shell{position:relative;z-index:2;height:100vh;display:grid;
    grid-template-columns:266px 1fr 348px;grid-template-rows:66px 1fr 92px;
    grid-template-areas:"top top top" "side main rail" "side dock dock";gap:20px;padding:20px 24px}
  .glass{background:var(--glass);backdrop-filter:blur(26px) saturate(150%);
    -webkit-backdrop-filter:blur(26px) saturate(150%);border:1px solid var(--brd);
    border-radius:var(--r);box-shadow:var(--shadow)}
  /* ---- TOP BAR ---- */
  .topbar{grid-area:top;display:flex;align-items:center;justify-content:space-between;padding:0 20px}
  .switch{display:flex;gap:4px;align-items:center;background:var(--glass2);border:1px solid var(--brd);
    border-radius:44px;padding:5px;backdrop-filter:blur(22px)}
  .switch button{display:flex;gap:9px;align-items:center;border:0;cursor:pointer;color:var(--dim);
    background:transparent;font-family:var(--font);font-size:.8rem;font-weight:600;letter-spacing:1.5px;
    padding:9px 18px;border-radius:34px;transition:.4s var(--ease)}
  .switch button.on{background:var(--accent-soft);color:var(--accent);box-shadow:inset 0 0 0 1px var(--brd)}
  .switch .knob{width:42px;height:22px;border-radius:22px;background:var(--accent-soft);position:relative;
    border:1px solid var(--brd);transition:.4s var(--ease)}
  .switch .knob::after{content:"";position:absolute;width:16px;height:16px;border-radius:50%;top:2px;left:3px;
    background:var(--accent);transition:.4s var(--ease);box-shadow:0 0 8px var(--accent)}
  html[data-view="manual"] .switch .knob::after{left:21px}
  .tools{display:flex;align-items:center;gap:6px}
  .tools .ic{width:40px;height:40px;display:grid;place-items:center;border-radius:13px;cursor:pointer;
    color:var(--txt);background:transparent;border:1px solid transparent;transition:.25s var(--ease)}
  .tools .ic:hover{background:var(--glass2);border-color:var(--brd);transform:translateY(-1px)}
  .tier{font-size:.64rem;font-weight:800;letter-spacing:1.6px;padding:7px 13px;border-radius:22px;
    background:var(--accent-soft);color:var(--accent);border:1px solid var(--brd);cursor:pointer}
  .clock{text-align:right;font-size:.82rem;line-height:1.25;margin-left:8px}
  .clock b{font-weight:700} .clock span{color:var(--dim);font-size:.7rem}
  .avatar{width:40px;height:40px;border-radius:50%;background:var(--accent-soft);border:1px solid var(--brd);
    display:grid;place-items:center;color:var(--accent)}
  /* ---- SIDEBAR ---- */
  .side{grid-area:side;padding:24px 18px;display:flex;flex-direction:column;gap:14px}
  .brand{text-align:center;padding:8px 0 14px}
  .brand .mark{width:104px;height:104px;margin:0 auto;filter:drop-shadow(0 0 14px var(--accent-soft))}
  .brand h1{font-size:1.55rem;letter-spacing:9px;font-weight:300;margin-top:10px;padding-left:9px}
  .brand small{color:var(--accent);letter-spacing:6px;font-size:.58rem;font-weight:700}
  .modecard{display:flex;align-items:center;gap:12px;padding:13px 15px;border-radius:15px;background:var(--glass2);
    border:1px solid transparent;cursor:pointer;transition:.3s var(--ease)}
  .modecard:hover{transform:translateX(2px)}
  .modecard.active{border-color:var(--brd);box-shadow:inset 0 0 0 1px var(--accent-soft)}
  .modecard svg{color:var(--accent)} .modecard b{font-size:.76rem;letter-spacing:1.6px}
  .tagline{margin-top:auto;padding:16px;border-radius:15px;background:var(--glass2);border:1px solid var(--brd)}
  .tagline h3{font-size:1rem;font-weight:600;line-height:1.3} .tagline h3 em{color:var(--accent);font-style:normal}
  .tagline p{color:var(--dim);font-size:.74rem;line-height:1.55;margin-top:9px}
  /* ---- MAIN ---- */
  .main{grid-area:main;overflow:auto;padding:6px 6px}
  .main::-webkit-scrollbar,.rail::-webkit-scrollbar{width:7px}
  .main::-webkit-scrollbar-thumb,.rail::-webkit-scrollbar-thumb{background:var(--brd);border-radius:8px}
  .hero{text-align:center;padding:30px 0 12px}
  .hero .hi{color:var(--accent);font-size:.96rem;letter-spacing:.5px;display:flex;gap:8px;justify-content:center;align-items:center}
  .hero h2{font-size:3.6rem;font-weight:200;letter-spacing:1px;margin:6px 0;
    background:linear-gradient(180deg,var(--txt),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}
  .hero h2 b{font-weight:700}
  .hero p{color:var(--dim);font-size:1.02rem}
  .ask{display:flex;align-items:center;gap:13px;max-width:580px;margin:26px auto;padding:15px 20px;
    border-radius:44px;background:var(--glass2);border:1px solid var(--brd);box-shadow:var(--shadow)}
  .ask input{flex:1;background:transparent;border:0;outline:0;color:var(--txt);font-size:1.02rem;font-family:var(--font)}
  .ask input::placeholder{color:var(--dim)}
  .ask .go{width:42px;height:42px;border-radius:50%;border:0;cursor:pointer;color:#fff;font-size:1.15rem;
    background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 6px 16px var(--accent-soft)}
  .launch{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;max-width:800px;margin:0 auto}
  .app{display:flex;flex-direction:column;align-items:center;gap:9px;padding:20px 8px;border-radius:17px;
    background:var(--glass2);border:1px solid var(--brd);cursor:pointer;transition:.3s var(--ease)}
  .app:hover{transform:translateY(-5px);box-shadow:var(--shadow);border-color:var(--accent)}
  .app svg{color:var(--accent)} .app b{font-size:.68rem;font-weight:600;letter-spacing:.4px;text-align:center}
  /* manual windows */
  .win{border-radius:15px;overflow:hidden;margin-bottom:18px}
  .win .bar{display:flex;align-items:center;gap:8px;padding:11px 15px;background:var(--glass2);
    border-bottom:1px solid var(--brd);font-size:.78rem}
  .win .bar .dot{width:11px;height:11px;border-radius:50%}
  .win .body{padding:17px;font-size:.82rem}
  .files{display:grid;grid-template-columns:1fr 1fr;gap:7px}
  .files .f{display:flex;justify-content:space-between;padding:9px 11px;border-radius:9px;background:var(--glass);cursor:pointer}
  .files .f:hover{background:var(--accent-soft)} .files .f span{color:var(--dim)}
  .term{font-family:var(--mono);font-size:.74rem;line-height:1.55;color:var(--accent2)}
  .term .k{color:var(--accent)} .term .p{color:var(--dim)}
  .ptable{font-size:.74rem;width:100%;border-collapse:collapse}
  .ptable td{padding:5px 6px;border-bottom:1px solid var(--brd)} .ptable td:last-child{text-align:right;color:var(--dim)}
  /* ---- RIGHT RAIL ---- */
  .rail{grid-area:rail;overflow:auto;display:flex;flex-direction:column;gap:18px;padding-right:2px}
  .panel{padding:17px}
  .panel h4{font-size:.7rem;letter-spacing:1.6px;text-transform:uppercase;color:var(--dim);margin-bottom:15px;
    display:flex;justify-content:space-between;align-items:center}
  .rings{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
  .ring{text-align:center}
  .ring .d{width:58px;height:58px;margin:0 auto;border-radius:50%;display:grid;place-items:center;
    font-size:.7rem;font-weight:700;background:conic-gradient(var(--accent) calc(var(--v)*1%),var(--accent-soft) 0);
    transition:background .6s var(--ease)}
  .ring .d i{width:46px;height:46px;border-radius:50%;background:var(--glass);display:grid;place-items:center;font-style:normal}
  .ring small{display:block;color:var(--dim);font-size:.6rem;margin-top:7px;letter-spacing:1.2px}
  .spark{height:62px;width:100%}
  .net{display:flex;justify-content:space-between;color:var(--dim);font-size:.72rem;margin-top:7px}
  .agents{display:grid;grid-template-columns:1fr 1fr;gap:9px}
  .agent{display:flex;align-items:center;gap:9px;padding:9px;border-radius:11px;background:var(--glass)}
  .agent .av{width:28px;height:28px;border-radius:9px;display:grid;place-items:center;background:var(--accent-soft);
    color:var(--accent);font-size:.6rem;font-weight:800}
  .agent b{font-size:.68rem;letter-spacing:1px;display:block} .agent .role{font-size:.54rem;color:var(--dim);letter-spacing:.5px}
  .agent .st{width:7px;height:7px;border-radius:50%;background:#39d98a;margin-left:auto;box-shadow:0 0 7px #39d98a}
  .qrow{display:flex;gap:10px;margin-bottom:15px}
  .qrow .qt{flex:1;height:48px;border-radius:13px;background:var(--accent-soft);color:var(--accent);
    border:1px solid var(--brd);display:grid;place-items:center;cursor:pointer}
  .slide{margin:13px 0} .slide label{display:flex;justify-content:space-between;font-size:.74rem;margin-bottom:7px}
  .slide .track{height:6px;border-radius:6px;background:var(--accent-soft);position:relative}
  .slide .track i{position:absolute;left:0;top:0;height:6px;border-radius:6px;background:linear-gradient(90deg,var(--accent),var(--accent2))}
  /* ---- DOCK ---- */
  .dock{grid-area:dock;justify-self:center;align-self:end;display:flex;gap:11px;padding:11px 17px;
    border-radius:24px;margin-bottom:4px}
  .dock .di{width:48px;height:48px;border-radius:15px;display:grid;place-items:center;cursor:pointer;
    background:var(--glass2);border:1px solid var(--brd);color:var(--txt);transition:.2s var(--ease);position:relative}
  .dock .di:hover{transform:translateY(-12px) scale(1.14);color:var(--accent);border-color:var(--accent)}
  .dock .di.primary{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border:0;
    box-shadow:0 8px 20px var(--accent-soft)}
  /* ---- VIEW VISIBILITY ---- */
  html[data-view="sovereign"] .manual-only{display:none}
  html[data-view="manual"] .sovereign-only{display:none}
  html[data-view="manual"] .shell{grid-template-columns:266px 1fr 324px}
  /* ---- MODAL ---- */
  .scrim{position:fixed;inset:0;z-index:50;background:rgba(5,4,15,.62);backdrop-filter:blur(7px);
    display:none;place-items:center;padding:24px}
  .scrim.open{display:grid}
  .modal{width:min(900px,96vw);max-height:88vh;overflow:auto;padding:28px}
  .modal h2{font-weight:300;letter-spacing:1px;font-size:1.7rem} .modal h2 b{font-weight:700;color:var(--accent)}
  .modal .sub{color:var(--dim);margin:7px 0 22px;font-size:.86rem}
  .plans{display:grid;grid-template-columns:repeat(4,1fr);gap:13px}
  .plan{padding:19px 17px;border-radius:17px;background:var(--glass2);border:1px solid var(--brd);
    display:flex;flex-direction:column;gap:9px}
  .plan.feat{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent),var(--shadow);transform:translateY(-6px)}
  .plan .nm{font-size:.68rem;letter-spacing:2px;text-transform:uppercase;color:var(--accent)}
  .plan .pr{font-size:1.6rem;font-weight:700} .plan .pr small{font-size:.64rem;color:var(--dim);font-weight:400}
  .plan ul{list-style:none;font-size:.72rem;color:var(--dim);display:flex;flex-direction:column;gap:6px;margin:6px 0}
  .plan li::before{content:"✦ ";color:var(--accent)}
  .plan button{margin-top:auto;border:0;cursor:pointer;border-radius:11px;padding:11px;font-weight:700;font-size:.74rem;
    background:var(--accent-soft);color:var(--accent);border:1px solid var(--brd)}
  .plan.feat button{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border:0}
  .modal .close{position:sticky;top:0;float:right;cursor:pointer;color:var(--dim);font-size:1.5rem}
  .note{margin-top:18px;font-size:.7rem;color:var(--dim);line-height:1.55}
  #splash{position:fixed;inset:0;z-index:99;display:grid;place-items:center;background:#06040f;color:#c9b6ff;
    font-family:var(--mono);letter-spacing:5px;transition:opacity .9s var(--ease)}
  @media(max-width:1120px){.shell{grid-template-columns:1fr}.side,.rail{display:none}}
</style>
</head>
<body>
<div id="splash">PRADY OS · SOVEREIGN EDITION</div>

<!-- ===================== PROCEDURAL LANDSCAPE SCENE ===================== -->
<svg id="scene" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="sunGrad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="var(--sun)"/><stop offset="100%" stop-color="var(--sun)" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="waterGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" class="beam" stop-opacity=".5"/><stop offset="100%" stop-color="var(--water)" stop-opacity="0"/>
    </linearGradient>
    <filter id="soft"><feGaussianBlur stdDeviation="9"/></filter>
    <filter id="soft2"><feGaussianBlur stdDeviation="22"/></filter>
  </defs>
  <!-- ringed planet, upper right -->
  <g opacity=".55"><circle class="planet" cx="1180" cy="180" r="120"/>
    <ellipse class="ring" cx="1180" cy="180" rx="200" ry="46" fill="none" stroke-width="6" opacity=".5" transform="rotate(-18 1180 180)"/></g>
  <!-- sun / moon glow near horizon -->
  <circle class="glow" cx="980" cy="470" r="260" filter="url(#soft2)"/>
  <circle class="sun" cx="980" cy="470" r="78" filter="url(#soft)"/>
  <circle class="sun" cx="980" cy="470" r="58"/>
  <!-- clouds (day/dawn) -->
  <g class="cloud" filter="url(#soft)" style="animation:drift 30s ease-in-out infinite alternate">
    <ellipse cx="360" cy="170" rx="150" ry="26"/><ellipse cx="520" cy="150" rx="110" ry="22"/>
    <ellipse cx="1040" cy="120" rx="140" ry="24"/></g>
  <!-- birds -->
  <g class="bird" fill="none" stroke-width="2.5" stroke-linecap="round">
    <path d="M250 250 q12 -10 24 0 q12 -10 24 0"/><path d="M320 280 q9 -8 18 0 q9 -8 18 0"/>
    <path d="M210 300 q9 -8 18 0 q9 -8 18 0"/></g>
  <!-- mountain ridges, far → near (atmospheric depth) -->
  <path class="m1" d="M0,560 L180,430 L360,540 L560,400 L760,520 L980,380 L1200,500 L1440,420 L1440,620 L0,620Z" opacity=".85"/>
  <path class="m2" d="M0,610 L220,500 L430,600 L650,470 L880,580 L1100,480 L1320,580 L1440,520 L1440,680 L0,680Z" opacity=".92"/>
  <path class="m3" d="M0,680 L260,580 L500,670 L760,560 L1000,660 L1240,580 L1440,650 L1440,760 L0,760Z"/>
  <path class="m4" d="M0,760 L300,690 L620,755 L920,680 L1200,750 L1440,710 L1440,900 L0,900Z"/>
  <!-- lake + sun-path reflection -->
  <rect class="water" x="0" y="744" width="1440" height="156"/>
  <polygon points="940,744 1020,744 1110,900 850,900" fill="url(#waterGrad)"/>
</svg>
<div class="stars" id="stars"></div>

<div class="shell">
  <!-- TOP BAR -->
  <header class="topbar glass">
    <div class="switch">
      <button id="bSov" class="on" onclick="setView('sovereign')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M5 16L3 7l5.5 4L12 5l3.5 6L21 7l-2 9H5zm0 2h14v2H5z"/></svg>SOVEREIGN MODE</button>
      <span class="knob"></span>
      <button id="bMan" onclick="setView('manual')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M4 5h16v10H4zM2 17h20v2H2z"/></svg>MANUAL MODE</button>
    </div>
    <div class="tools">
      <span class="tier" id="tierBadge" onclick="location.href='/billing'">FREE</span>
      <div class="ic" title="Notifications" onclick="showNotifications()"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0"/></svg></div>
      <div class="ic" id="themeBtn" title="Theme (auto by time)" onclick="cycleTheme()"><svg id="themeIcon" width="19" height="19" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="5"/></svg></div>
      <div class="ic" title="Settings" onclick="openSettings()"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H1a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 4.6 7a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V1a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H23a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/></svg></div>
      <div class="avatar" onclick="launch('Profile')" title="Profile"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0z"/></svg></div>
      <div class="clock"><b id="clkTime">--:--</b><br><span id="clkDate">--</span></div>
    </div>
  </header>

  <!-- SIDEBAR -->
  <aside class="side glass">
    <div class="brand"><div class="mark" id="logo"></div><h1>PRADYOS</h1><small>SOVEREIGN EDITION</small></div>
    <div class="modecard active" onclick="setView('sovereign')"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M5 16L3 7l5.5 4L12 5l3.5 6L21 7l-2 9H5z"/></svg><b>SOVEREIGN MODE</b></div>
    <div class="modecard" onclick="setView('manual')"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M4 5h16v10H4zM2 17h20v2H2z"/></svg><b>MANUAL MODE</b></div>
    <div class="tagline">
      <h3 class="sovereign-only">The machine governs.<br><em>You approve.</em></h3>
      <p class="sovereign-only">PRADYOS operates autonomously to achieve your objectives with precision and intelligence.</p>
      <h3 class="manual-only"><em>Full control.</em><br>All tools. All yours.</h3>
      <p class="manual-only">Access your desktop environment with complete freedom and flexibility.</p>
    </div>
  </aside>

  <!-- MAIN -->
  <main class="main">
    <!-- SOVEREIGN -->
    <div class="sovereign-only">
      <div class="hero">
        <div class="hi">☀ <span id="greet">Good evening,</span></div>
        <h2><b>Sovereign.</b></h2>
        <p>The machine is at your service.</p>
      </div>
      <div class="ask glass">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="var(--accent)"><path d="M12 2l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/></svg>
        <input id="ask" placeholder="Ask PRADYOS anything..." onkeydown="if(event.key==='Enter')askPradyos()">
        <button class="go" onclick="askPradyos()">→</button>
      </div>
      <div id="askResp" class="glass" style="display:none;max-width:600px;margin:0 auto 22px;padding:16px 20px;text-align:left;font-size:.86rem;line-height:1.55"></div>
      <div class="launch">
        <div class="app" onclick="launch('AI Terminal')"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 6l5 6-5 6M12 18h8"/></svg><b>AI Terminal</b></div>
        <div class="app" onclick="setView('manual')"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 7h6l2 2h10v10H3z"/></svg><b>Files</b></div>
        <div class="app" onclick="setView('manual')"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 12h4l2-6 4 12 2-6h6"/></svg><b>System Monitor</b></div>
        <div class="app" onclick="openAgentCenter()"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/></svg><b>Agent Center</b></div>
        <div class="app" onclick="showProjects()"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 5h7l2 3h7v11H4z"/></svg><b>Projects</b></div>
        <div class="app" onclick="showReports()"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M6 3h9l3 3v15H6zM9 12h6M9 16h6"/></svg><b>Reports</b></div>
      </div>
    </div>

    <!-- MANUAL -->
    <div class="manual-only">
      <div class="win glass">
        <div class="bar"><span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e"></span><span class="dot" style="background:#28c840"></span>&nbsp;&nbsp;<span id="fmPath">Home</span> — File Manager</div>
        <div class="body">
          <h4 style="margin-bottom:10px;color:var(--dim);font-size:.68rem;letter-spacing:1.6px">FILES</h4>
          <div class="files" id="fmList"><div class="f">Loading…<span></span></div></div>
        </div>
      </div>
      <div class="win glass">
        <div class="bar"><span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e"></span><span class="dot" style="background:#28c840"></span>&nbsp;&nbsp;PRISM Terminal</div>
        <div class="body term">
          <div><span class="k">sovereign@pradyos</span> ~ neofetch</div>
          <div class="p">──────────────────────────────</div>
          <div><span class="k">OS</span>: <span id="nOs">PRADYOS Sovereign Edition</span></div>
          <div><span class="k">Kernel</span>: <span id="nKernel">—</span> &nbsp; <span class="k">Uptime</span>: <span id="nUp">—</span></div>
          <div><span class="k">Shell</span>: <span id="nShell">PRISM</span> &nbsp; <span class="k">Host</span>: <span id="nHost">—</span></div>
          <div><span class="k">CPU</span>: <span id="nCpu">—</span></div>
          <div><span class="k">Memory</span>: <span id="nMem">—</span> &nbsp; <span class="k">Agents</span>: <span id="nAg">8 active</span></div>
          <div style="margin-top:6px"><span class="k">sovereign@pradyos</span> ~ ▮</div>
        </div>
      </div>
      <div class="win glass">
        <div class="bar"><span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e"></span><span class="dot" style="background:#28c840"></span>&nbsp;&nbsp;System Monitor — top processes</div>
        <div class="body"><table class="ptable" id="procTable"><tr><td>Loading…</td><td></td></tr></table></div>
      </div>
    </div>
  </main>

  <!-- RIGHT RAIL -->
  <aside class="rail">
    <div class="panel glass">
      <h4>System Overview <span>⇲</span></h4>
      <div class="rings">
        <div class="ring"><div class="d" id="rCpu" style="--v:12"><i>12%</i></div><small>CPU</small></div>
        <div class="ring"><div class="d" id="rGpu" style="--v:18"><i>18%</i></div><small>GPU</small></div>
        <div class="ring"><div class="d" id="rRam" style="--v:32"><i>32%</i></div><small>RAM</small></div>
        <div class="ring"><div class="d" id="rDsk" style="--v:68"><i>68%</i></div><small>DISK</small></div>
      </div>
    </div>
    <div class="panel glass">
      <h4>Network Activity <span>⇲</span></h4>
      <svg class="spark" id="spark" viewBox="0 0 300 62" preserveAspectRatio="none"></svg>
      <div class="net"><span>↓ <b id="netD">1.2</b> Gbps</span><span>↑ <b id="netU">890</b> Mbps</span></div>
    </div>
    <div class="panel glass">
      <h4>AI Agents <span id="agCount" style="color:var(--accent)">8 Active</span></h4>
      <div class="agents" id="agents"></div>
    </div>
    <div class="panel glass sovereign-only">
      <h4>Cognition <span id="cogReflect" onclick="reflectNow()" style="color:var(--accent);cursor:pointer">⟳ reflect</span></h4>
      <div style="font-size:.72rem;color:var(--dim);margin-bottom:4px">Latest curiosity</div>
      <div id="cogGoal" style="font-size:.8rem;line-height:1.4;margin-bottom:12px">—</div>
      <div style="font-size:.72rem;color:var(--dim);margin-bottom:6px">Proposed goals <span id="cogCount" style="color:var(--accent)"></span></div>
      <div id="cogGoals" style="display:flex;flex-direction:column;gap:6px"></div>
    </div>
    <div class="panel glass manual-only">
      <h4>Quick Settings</h4>
      <div class="qrow">
        <div class="qt" title="Wi-Fi"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 18a2 2 0 1 1 0 4 2 2 0 0 1 0-4zM5 11l2 2a7 7 0 0 1 10 0l2-2a10 10 0 0 0-14 0zM1 7l2 2a13 13 0 0 1 18 0l2-2a16 16 0 0 0-22 0z"/></svg></div>
        <div class="qt" title="Bluetooth"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M7 7l10 10-5 5V2l5 5L7 17"/></svg></div>
        <div class="qt" title="Volume"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M4 9v6h4l5 5V4L8 9z"/></svg></div>
      </div>
      <div class="slide"><label>Volume <b>72%</b></label><div class="track"><i style="width:72%"></i></div></div>
      <div class="slide"><label>Brightness <b>48%</b></label><div class="track"><i style="width:48%"></i></div></div>
    </div>
  </aside>

  <!-- DOCK -->
  <nav class="dock glass">
    <div class="di primary" title="PRADYOS — new session" onclick="newSession()"><svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/></svg></div>
    <div class="di" title="Terminal / Logs" onclick="toggleLogPanel()"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 6l5 6-5 6M12 18h8"/></svg></div>
    <div class="di" title="Files" onclick="setView('manual')"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 7h6l2 2h10v10H3z"/></svg></div>
    <div class="di" title="Browser" onclick="showInResp('WEB BROWSER','<div style=\"color:var(--dim);font-size:.82rem\">Web browser requires a configured LLM provider. Use the AI Terminal below to make requests, or open an app from the launcher above.</div>')"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18"/></svg></div>
    <div class="di" title="Agent Center" onclick="openAgentCenter()"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/></svg></div>
    <div class="di" title="System Monitor" onclick="setView('manual')"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 12h4l2-6 4 12 2-6h6"/></svg></div>
    <div class="di" title="Clear session" onclick="clearSession()"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M5 7h14M9 7V4h6v3M6 7l1 13h10l1-13"/></svg></div>
  </nav>
</div>

<!-- LOG PANEL -->
<div id="logPanel" style="position:fixed;bottom:0;left:0;right:0;z-index:40;height:220px;background:var(--glass);backdrop-filter:blur(26px);border-top:1px solid var(--brd);display:none;flex-direction:column;font-family:var(--mono);font-size:.72rem;padding:10px 16px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <span style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;font-family:var(--font)">LIVE LOG</span>
    <span onclick="toggleLogPanel()" style="cursor:pointer;color:var(--dim);font-size:1.2rem">✕</span>
  </div>
  <div id="logOutput" style="flex:1;overflow-y:auto;color:var(--txt);line-height:1.6;white-space:pre-wrap"></div>
</div>

<!-- LICENSE / UPGRADE MODAL -->
<div class="scrim" id="scrim">
  <div class="modal glass">
    <span class="close" onclick="closeModal()">✕</span>
    <h2>Unlock <b>PRADYOS Sovereign</b></h2>
    <p class="sub">Pick the intelligence tier that fits you. Licensed yearly · works fully offline · cancel anytime.</p>
    <div class="plans" id="plans"></div>
    <div style="display:flex;align-items:center;justify-content:space-between;margin-top:18px;padding:13px 16px;border-radius:13px;background:var(--glass2);border:1px solid var(--brd)">
      <div><b style="font-size:.82rem">Open mode — all features free</b><div style="color:var(--dim);font-size:.7rem;margin-top:2px">Temporarily unlock every feature for all users (beta / promo). Flip off to resume paid tiers + Stripe.</div></div>
      <button id="openModeBtn" onclick="toggleOpenMode()" style="border:1px solid var(--brd);cursor:pointer;border-radius:22px;padding:9px 18px;font-weight:800;font-size:.72rem;letter-spacing:1px;background:var(--accent-soft);color:var(--accent)">OFF</button>
    </div>
    <p class="note" id="modalNote">Licenses are cryptographically signed and verified offline — no phone-home. Paid tiers use Stripe; an expired/invalid key drops to Free. PRADYOS never harms the machine.</p>
  </div>
</div>

<script>
// ---------- scorpion constellation emblem ----------
(function(){
  var pts=[[50,16],[60,24],[70,20],[78,30],[50,30],[42,40],[52,46],[60,56],[54,66],[64,72],[60,82],[72,84],[80,78]];
  var s='<svg viewBox="0 0 100 100" width="104" height="104">';
  s+='<circle cx="50" cy="50" r="46" fill="none" stroke="var(--accent)" stroke-opacity=".35" stroke-width="1"/>';
  s+='<circle cx="50" cy="50" r="40" fill="var(--accent-soft)"/>';
  s+='<path d="M'+pts.map(function(p){return p[0]+' '+p[1]}).join(' L ')+'" fill="none" stroke="var(--accent2)" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/>';
  s+='<path d="M60 24 L52 14 M70 20 L78 12" stroke="var(--accent2)" stroke-width="1.4" fill="none" stroke-linecap="round"/>';
  pts.forEach(function(p){s+='<circle cx="'+p[0]+'" cy="'+p[1]+'" r="2.1" fill="var(--accent)"/>';});
  s+='<circle cx="80" cy="78" r="3.2" fill="var(--accent)"/></svg>';
  document.getElementById('logo').innerHTML=s;
})();
// ---------- stars ----------
(function(){var s=document.getElementById('stars'),h='';for(var i=0;i<80;i++){h+='<i style="left:'+(Math.random()*100)+'%;top:'+(Math.random()*100)+'%;animation-delay:'+(Math.random()*3.5)+'s"></i>';}s.innerHTML=h;})();

// ---------- TIME-OF-DAY THEME (dawn 5-9 · day 9-17 · dusk 17-20 · night 20-5) ----------
var THEMES=['dawn','day','dusk','night'], override=null;
function pickTheme(h){ if(h>=5&&h<9)return 'dawn'; if(h>=9&&h<17)return 'day'; if(h>=17&&h<20)return 'dusk'; return 'night'; }
function greetFor(h){ if(h<12)return 'Good morning,'; if(h<17)return 'Good afternoon,'; if(h<21)return 'Good evening,'; return 'Good night,'; }
function applyTheme(){
  var h=new Date().getHours(), t=override||pickTheme(h);
  document.documentElement.setAttribute('data-theme',t);
  document.getElementById('greet').textContent=greetFor(h);
  var dark=(t==='night'||t==='dusk');
  document.getElementById('themeIcon').innerHTML = dark
    ? '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>'
    : '<circle cx="12" cy="12" r="5"/><path d="M12 1v3M12 20v3M1 12h3M20 12h3M4 4l2 2M18 18l2 2M4 20l2-2M18 6l2-2" stroke="currentColor" stroke-width="1.6" fill="none"/>';
  document.getElementById('themeBtn').title='Theme: '+t+(override?' (manual — click cycles, dbl-click = auto)':' (auto by time)');
}
function cycleTheme(){var c=document.documentElement.getAttribute('data-theme');override=THEMES[(THEMES.indexOf(c)+1)%4];applyTheme();}
document.getElementById('themeBtn').addEventListener('dblclick',function(){override=null;applyTheme();});
applyTheme(); setInterval(applyTheme,60000);

// ---------- clock ----------
function tick(){var d=new Date();
  document.getElementById('clkTime').textContent=d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
  document.getElementById('clkDate').textContent=d.toLocaleDateString([], {day:'numeric',month:'long',year:'numeric'});
}
tick(); setInterval(tick,1000);

// ---------- view switch ----------
function setView(v){
  document.documentElement.setAttribute('data-view',v);
  document.getElementById('bSov').classList.toggle('on',v==='sovereign');
  document.getElementById('bMan').classList.toggle('on',v==='manual');
  document.querySelectorAll('.modecard').forEach(function(c,i){c.classList.toggle('active',(i===0)===(v==='sovereign'));});
  if(v==='manual'){loadFiles();loadProcs();}
}

// ---------- helpers ----------
function gj(u){return fetch(u).then(function(r){if(!r.ok)throw 0;return r.json();}).catch(function(){return null;});}
function setRing(id,v){var e=document.getElementById(id);if(!e)return;v=Math.max(0,Math.min(100,Math.round(v)));e.style.setProperty('--v',v);e.querySelector('i').textContent=v+'%';}
function escapeHtml(s){return String(s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
function showInResp(title,html){var box=document.getElementById('askResp');box.style.display='block';box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">'+title+'</div>'+html;setView('sovereign');}
function launch(name){var s=document.getElementById('splash');s.textContent='▸ '+name;s.style.opacity='1';s.style.display='grid';setTimeout(function(){s.style.opacity='0';setTimeout(function(){s.style.display='none';},700);},650);}

// ---------- File content viewer ----------
function viewFile(path,name){
  showInResp('FILE: '+escapeHtml(name),'<div style="color:var(--dim)">Loading…</div>');
  gj('/api/v1/files/content?path='+encodeURIComponent(path)).then(function(d){
    if(d&&d.content){
      var html='<div style="font-size:.72rem;color:var(--dim);margin-bottom:8px">'+escapeHtml(d.path)+' · '+d.size_kb+' KB</div>';
      html+='<pre style="font-family:var(--mono);font-size:.72rem;line-height:1.45;overflow:auto;max-height:50vh;background:var(--glass);padding:12px;border-radius:11px;white-space:pre-wrap">'+escapeHtml(d.content.slice(0,5000))+'</pre>';
      if(d.content.length>5000)html+='<div style="color:var(--dim);font-size:.68rem;margin-top:6px">(showing first 5000 chars)</div>';
      showInResp('FILE: '+escapeHtml(name),html);
    }else showInResp('FILE: '+escapeHtml(name),'<div style="color:var(--dim)">Could not read file.</div>');
  });
}

// ---------- Agent center ----------
function openAgentCenter(){
  showInResp('AGENT CENTER','<div style="color:var(--dim)">Loading agent roster…</div>');
  Promise.all([gj('/api/v1/guild/agents'), gj('/api/v1/guild/stats')]).then(function(results){
    var agents=(results[0]&&results[0].agents)||[];
    var stats=results[1]||{};
    if(!agents.length){
      showInResp('AGENT CENTER','<div style="color:var(--dim)">No agents registered.</div>');return;
    }
    var html='<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">';
    agents.forEach(function(a){
      var st=a.status||'active';var dotCol=st==='active'?'#39d98a':(st==='error'?'#ff5f57':'#febc2e');
      html+='<div style="padding:12px;border-radius:13px;background:var(--glass);border:1px solid var(--brd)">';
      html+='<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">';
      html+='<span style="width:32px;height:32px;border-radius:9px;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent);font-weight:800;font-size:.7rem">'+escapeHtml((a.name||'').slice(0,2))+'</span>';
      html+='<div><b style="font-size:.76rem">'+escapeHtml(a.name||'')+'</b><br><span style="font-size:.62rem;color:var(--dim)">'+escapeHtml(a.role||'')+'</span></div>';
      html+='<span style="width:8px;height:8px;border-radius:50%;background:'+dotCol+';margin-left:auto;box-shadow:0 0 6px '+dotCol+'"></span>';
      html+='</div>';
      html+='<div style="font-size:.68rem;color:var(--dim)">Last: '+(a.last_action||'Awaiting task')+'</div>';
      html+='</div>';
    });
    html+='</div>';
    if(stats&&stats.projects_done!==undefined)html+='<div style="margin-top:12px;font-size:.72rem;color:var(--dim)">Projects completed: '+stats.projects_done+'</div>';
    showInResp('AGENT CENTER',html);
  });
}

// ---------- Projects & Reports ----------
function showProjects(){
  showInResp('PROJECTS','<div style="color:var(--dim)">Loading projects…</div>');
  gj('/api/v1/guild/projects').then(function(d){
    var projects=(d&&d.projects)||[];
    if(!projects.length){showInResp('PROJECTS','<div style="color:var(--dim)">No projects yet. Ask PRADYOS something to start one.</div>');return;}
    var html='';
    projects.slice(0,15).forEach(function(p){
      html+='<div style="padding:11px 13px;border-radius:11px;background:var(--glass);margin-bottom:8px">';
      html+='<div style="font-size:.78rem;font-weight:600">'+escapeHtml(p.objective||p.name||'Project')+'</div>';
      var syn=p.synthesis||p.summary||p.result||'';
      if(syn)html+='<div style="font-size:.7rem;color:var(--dim);margin-top:4px">'+escapeHtml(String(syn).slice(0,200))+'</div>';
      if(p.ts||p.created)html+='<div style="font-size:.62rem;color:var(--dim);margin-top:4px">'+new Date((p.ts||p.created)*1000).toLocaleString()+'</div>';
      html+='</div>';
    });
    if(projects.length>15)html+='<div style="color:var(--dim);font-size:.68rem">… and '+(projects.length-15)+' more</div>';
    showInResp('PROJECTS',html);
  });
}
function showReports(){
  showInResp('REPORTS','<div style="color:var(--dim)">Loading reports…</div>');
  Promise.all([gj('/api/v1/guild/stats'), gj('/api/v1/session/history')]).then(function(results){
    var stats=results[0]||{};
    var hist=results[1]||{};
    var entries=(hist.entries)||[];
    var html='<div style="font-size:.82rem;line-height:1.8">';
    html+='<b>Guild stats:</b><br>';
    html+='Projects: '+(stats.projects_done||0)+' done, '+(stats.projects_total||0)+' total<br>';
    html+='Skills: '+(stats.skills||0)+' learned<br>';
    if(stats.avg_score!==undefined)html+='Avg score: '+(stats.avg_score||'-')+'<br>';
    html+='<br><b>Recent activity:</b><br>';
    if(entries.length){
      entries.slice(-8).reverse().forEach(function(e){
        var msg=e.event||'event';
        var obj=e.objective||e.result||'';
        html+='<div style="padding:6px 8px;border-radius:7px;background:var(--glass);margin-bottom:4px;font-size:.72rem">';
        html+='<span style="color:var(--accent)">['+escapeHtml(msg)+']</span> '+escapeHtml(String(obj).slice(0,120));
        html+='</div>';
      });
    }else{html+='<div style="color:var(--dim);font-size:.72rem">No activity recorded yet.</div>';}
    html+='</div>';
    showInResp('REPORTS',html);
  });
}

// ---------- WebSocket for real-time metrics ----------
var ws=null, wsReconnectTimer=null, netHist=[];
function connectWS(){
  var proto=location.protocol==='https:'?'wss:':'ws:';
  ws=new WebSocket(proto+'//'+location.host+'/ws/console');
  ws.onmessage=function(e){
    try{var d=JSON.parse(e.data);
      if(d.type==='metrics'){
        setRing('rCpu',d.cpu); setRing('rGpu',d.gpu||0); setRing('rRam',d.ram); setRing('rDsk',d.disk);
        netHist.push({recv:d.recv_mbps||0,sent:d.sent_mbps||0,ts:Date.now()});
        if(netHist.length>42)netHist.shift();
        drawSpark();
      }
    }catch(ex){}
  };
  ws.onclose=function(){ws=null;clearTimeout(wsReconnectTimer);wsReconnectTimer=setTimeout(connectWS,3000);};
  ws.onerror=function(){ws&&ws.close();};
}
function drawSpark(){
  var w=300,h=62;
  if(netHist.length<2)return;
  var vals=netHist.map(function(n){return n.recv;});
  var mx=Math.max.apply(null,vals),mn=Math.min.apply(null,vals),rg=(mx-mn)||1;
  var d=vals.map(function(v,i){return (i?'L':'M')+(i/(vals.length-1)*w).toFixed(1)+','+(h-(v-mn)/rg*(h-9)-4).toFixed(1);}).join(' ');
  document.getElementById('spark').innerHTML='<path d="'+d+'" fill="none" stroke="var(--accent)" stroke-width="2"/><path d="'+d+' L300,62 L0,62Z" fill="var(--accent-soft)"/>';
  var last=netHist[netHist.length-1];
  document.getElementById('netD').textContent=(last.recv||0).toFixed(1);
  document.getElementById('netU').textContent=Math.round(last.sent||0);
}
function pollMetrics(){
  gj('/api/v1/system/metrics').then(function(d){
    if(d){setRing('rCpu',d.cpu);setRing('rGpu',d.gpu||0);setRing('rRam',d.ram);setRing('rDsk',d.disk);
      netHist.push({recv:d.net_down||1,sent:d.net_up||1,ts:Date.now()});if(netHist.length>42)netHist.shift();drawSpark();}
  });
}

// ---------- AI Agents from API ----------
function showAgentStatus(name){
  var box=document.getElementById('askResp');
  box.style.display='block';
  box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">'+name+' · AGENT STATUS</div><div style="color:var(--dim)">Loading…</div>';
  gj('/api/v1/guild/agents/'+name.toLowerCase()+'/status').then(function(d){
    if(d)box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">'+name+' · AGENT STATUS</div><div style="font-size:.82rem;line-height:1.55"><b>Role:</b> '+escapeHtml(d.role||'')+'<br><b>Status:</b> '+escapeHtml(d.status||'')+'<br><b>Last action:</b> '+escapeHtml(d.last_action||'')+'</div>';
    else box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">'+name+' · AGENT STATUS</div><div style="color:var(--dim)">Status endpoint not available.</div>';
  }).catch(function(){box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">'+name+'</div><div style="color:var(--dim)">Could not reach agent status.</div>';});
  setView('sovereign');
}
function renderAgents(list){
  document.getElementById('agents').innerHTML=list.map(function(a){
    var st=a.status||'active';var dotCol=st==='active'?'#39d98a':(st==='error'?'#ff5f57':'#febc2e');
    return '<div class="agent" onclick="showAgentStatus(\''+a.name.replace(/'/g,"\\'")+'\')"><span class="av">'+a.name.slice(0,2)+'</span><div><b>'+a.name+'</b><span class="role">'+(a.role||'')+'</span></div><span class="st" style="background:'+dotCol+';box-shadow:0 0 7px '+dotCol+'"></span></div>';
  }).join('');
  document.getElementById('agCount').textContent=list.length+' Active';
  document.getElementById('nAg').textContent=list.length+' active';
}
function loadAgents(){
  gj('/api/v1/guild/agents').then(function(d){
    if(d&&Array.isArray(d.agents)&&d.agents.length){renderAgents(d.agents);}
    else{gj('/api/v1/guild/roles').then(function(r){
      if(r&&Array.isArray(r.roles)&&r.roles.length){
        var names=['VEGA','ORION','LYRA','ATLAS','NOVA','DRACO','CYGNI','ARES'];
        renderAgents(r.roles.map(function(x,i){return {name:names[i]||(x.name||'AGT').toUpperCase(),role:x.role||'',status:'active'};}));
      }
    });}
  });
}

// ---------- File browser ----------
function loadFiles(){
  gj('/api/v1/files?path=~').then(function(d){
    var box=document.getElementById('fmList');
    if(d&&Array.isArray(d.entries)&&d.entries.length){
      document.getElementById('fmPath').textContent=d.path||'Home';
      box.innerHTML=d.entries.slice(0,12).map(function(e){
        var ic=e.is_dir?'🗀':'🗎';
        var click=e.is_dir?'':'onclick="viewFile(\''+escapeHtml(d.path+'/'+e.name).replace(/'/g,"\\'")+'\',\''+escapeHtml(e.name).replace(/'/g,"\\'")+'\')"';
        return '<div class="f" '+click+'>'+ic+' '+e.name+'<span>'+(e.is_dir?'dir':((e.size_kb||0)+' KB'))+'</span></div>';
      }).join('');
    }else{
      box.innerHTML=['Desktop|dir','Documents|dir','Downloads|dir','Pictures|dir','Projects|dir','PRADYOS Drive|dir']
        .map(function(x){var p=x.split('|');return '<div class="f">🗀 '+p[0]+'<span>'+p[1]+'</span></div>';}).join('');
    }
  });
}
function loadProcs(){
  gj('/api/v1/system/processes').then(function(d){
    var t=document.getElementById('procTable');
    if(d&&Array.isArray(d.processes)&&d.processes.length){
      t.innerHTML=d.processes.slice(0,7).map(function(p){return '<tr><td>'+(p.name||'?')+'</td><td>'+(p.cpu||0).toFixed(1)+'% · '+(p.mem||0).toFixed(1)+'%</td></tr>';}).join('');
    }else{
      t.innerHTML=[['pradyos-kernel','3.1'],['prism-shell','1.4'],['guild-worker','2.2'],['aurora-throne','0.9'],['warden-grid','0.6']]
        .map(function(p){return '<tr><td>'+p[0]+'</td><td>'+p[1]+'%</td></tr>';}).join('');
    }
  });
}
function loadInfo(){
  gj('/api/v1/system/info').then(function(d){if(!d)return;
    if(d.kernel)document.getElementById('nKernel').textContent=d.kernel;
    if(d.uptime)document.getElementById('nUp').textContent=d.uptime;
    if(d.host)document.getElementById('nHost').textContent=d.host;
    if(d.cpu_model)document.getElementById('nCpu').textContent=d.cpu_model;
    if(d.mem_total)document.getElementById('nMem').textContent=d.mem_total;
    if(d.shell)document.getElementById('nShell').textContent=d.shell;
  });
}

// ---------- Log panel (SSE stream) ----------
var logEventSource=null, logPanelOpen=false;
function toggleLogPanel(){
  var p=document.getElementById('logPanel');
  logPanelOpen=!logPanelOpen;
  p.style.display=logPanelOpen?'flex':'none';
  if(logPanelOpen){
    document.getElementById('logOutput').innerHTML='<div style="color:var(--dim)">Connecting to log stream…</div>';
    logEventSource=new EventSource('/api/v1/system/logs');
    logEventSource.onmessage=function(e){
      try{var d=JSON.parse(e.data);
        var col=d.level==='ERROR'?'#ff5f57':(d.level==='WARNING'?'#febc2e':'var(--txt)');
        var out=document.getElementById('logOutput');
        out.innerHTML+='<span style="color:'+col+'">['+d.level+'] '+escapeHtml(d.line||d.message||'')+'</span>\n';
        out.scrollTop=out.scrollHeight;
      }catch(ex){}
    };
    logEventSource.onerror=function(){
      document.getElementById('logOutput').innerHTML+='<span style="color:var(--dim)">— log stream disconnected, retrying… —</span>\n';
    };
  }else{
    if(logEventSource){logEventSource.close();logEventSource=null;}
  }
}

// ---------- Guild task / Ask PRADYOS ----------
function askPradyos(){
  var v=document.getElementById('ask').value.trim(); if(!v)return;
  document.getElementById('ask').value='';
  var box=document.getElementById('askResp');
  document.getElementById('ask').disabled=true;
  box.style.display='block';
  box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">VEGA · COORDINATING THE GUILD</div><div style="color:var(--dim)">▰▰▰ working on: '+escapeHtml(v)+'</div>';
  fetch('/api/v1/guild/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({objective:v})})
    .then(function(r){return r.json();})
    .then(function(d){
      var txt;
      if(d&&d.error){txt=d.error;}
      else if(d&&(d.summary||d.result||d.answer)){txt=d.summary||d.result||d.answer;}
      else if(d&&d.blackboard){txt=(typeof d.blackboard==='string')?d.blackboard:JSON.stringify(d.blackboard,null,1).slice(0,900);}
      else if(d){txt=JSON.stringify(d,null,1).slice(0,900);}
      else{txt='The Guild produced no output. Configure a model (PRADYOS_LLM_PROVIDER) — it defaults to local Ollama.';}
      if(typeof txt!=='string')txt=JSON.stringify(txt).slice(0,900);
      box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">PRADYOS · GUILD RESPONSE</div><div style="white-space:pre-wrap">'+escapeHtml(txt)+'</div>';
      document.getElementById('ask').disabled=false;
    })
    .catch(function(){box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">PRADYOS</div><div style="color:var(--dim)">Could not reach the Guild service. Is the OS backend running?</div>';document.getElementById('askInput').disabled=false;});
}

// ---------- Session management ----------
function newSession(){
  setView('sovereign');
  fetch('/api/v1/session/new',{method:'POST'}).then(function(r){return r.json();}).then(function(d){
    var box=document.getElementById('askResp');box.style.display='block';
    box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">SESSION</div><div style="color:var(--dim)">New session started. Ready for your command.</div>';
  }).catch(function(){});
}
function clearSession(){
  var box=document.getElementById('askResp');box.style.display='block';
  box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">SESSION</div><div style="color:var(--dim)">Clearing…</div>';
  fetch('/api/v1/session/clear',{method:'POST'}).then(function(r){return r.json();}).then(function(d){
    document.getElementById('ask').value='';
    box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">SESSION</div><div style="color:var(--dim)">Session cleared. Ready for new tasks.</div>';
  }).catch(function(){box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">SESSION</div><div style="color:var(--dim)">Session cleared.</div>';});
}

// ---------- Settings from API ----------
function openSettings(){
  var box=document.getElementById('askResp');box.style.display='block';
  box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">SETTINGS</div><div style="color:var(--dim)">Loading…</div>';
  Promise.all([gj('/api/v1/license/status'), gj('/api/v1/config/public')]).then(function(results){
    var st=results[0]||{}, cfg=results[1]||{};
    var tier=st.open_mode?'OPEN':(st.tier?st.tier.toUpperCase():(cfg.tier||'').toUpperCase()||'FREE');
    var html='<div style="font-size:.82rem;line-height:1.8">';
    html+='<b>Current tier:</b> '+tier+'<br>';
    html+='<b>Payment:</b> '+(cfg.payment_provider||'Stripe')+' · Polar<br>';
    html+='<b>Open Mode:</b> '+(st.open_mode?'ON':'OFF')+'<br>';
    html+='<b>Version:</b> '+(cfg.version||'—')+'<br>';
    html+='<b>System controls:</b><br>';
    html+='<span style="cursor:pointer;color:var(--accent);margin-right:12px" onclick="toggleSystemSetting(\'/api/v1/system/volume/toggle\',\'Volume\')">🔊 Volume</span>';
    html+='<span style="cursor:pointer;color:var(--accent);margin-right:12px" onclick="toggleSystemSetting(\'/api/v1/system/brightness/toggle\',\'Brightness\')">☀ Brightness</span>';
    html+='<span style="cursor:pointer;color:var(--accent);margin-right:12px" onclick="toggleSystemSetting(\'/api/v1/system/wifi/status\',\'WiFi\')">📶 WiFi</span>';
    html+='<span style="cursor:pointer;color:var(--accent)" onclick="toggleSystemSetting(\'/api/v1/system/bluetooth/status\',\'Bluetooth\')">🔵 Bluetooth</span><br><br>';
    html+='<b>Upgrade:</b> <span style="color:var(--accent);cursor:pointer" onclick="location.href=\'/billing\'">Visit /billing →</span></div>';
    box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">SETTINGS</div>'+html;
  }).catch(function(){box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">SETTINGS</div><div style="color:var(--dim)">Settings unavailable.</div>';});
  setView('sovereign');
}

// ---------- Notifications from decisions log ----------
function showNotifications(items){
  var box=document.getElementById('askResp');box.style.display='block';
  if(items&&Array.isArray(items)){
    var html='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">NOTIFICATIONS</div>';
    html+=items.map(function(n){return '<div style="padding:8px 10px;border-radius:9px;background:var(--glass);margin-bottom:6px;font-size:.78rem">'+escapeHtml(n.message||'')+'</div>';}).join('');
    box.innerHTML=html;setView('sovereign');return;
  }
  box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">NOTIFICATIONS</div><div style="color:var(--dim)">Loading…</div>';
  gj('/api/v1/notifications').then(function(d){
    var items=(d&&d.notifications)||[];
    if(items.length)box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">NOTIFICATIONS</div>'+items.map(function(n){return '<div style="padding:8px 10px;border-radius:9px;background:var(--glass);margin-bottom:6px;font-size:.78rem">'+(n.message||n.text||'')+'</div>';}).join('');
    else box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">NOTIFICATIONS</div><div style="color:var(--dim)">No new notifications.</div>';
  }).catch(function(){box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">NOTIFICATIONS</div><div style="color:var(--dim)">No notifications.</div>';});
  setView('sovereign');
}

// ---------- System controls ----------
function toggleSystemSetting(ep,label){
  gj(ep).then(function(d){
    var box=document.getElementById('askResp');box.style.display='block';
    box.innerHTML='<div style="color:var(--accent);font-size:.68rem;letter-spacing:1.6px;margin-bottom:7px">'+label+'</div><div style="color:var(--dim)">'+(d&&d.status||'Toggled')+'</div>';
    setView('sovereign');
  });
}

// ---------- Cognition panel ----------
function loadCognition(){
  var goalEl=document.getElementById('cogGoal');if(!goalEl)return;
  gj('/api/v1/sovereign/state').then(function(s){
    if(s&&s.latest_curiosity)goalEl.textContent=s.latest_curiosity;
    if(s&&Array.isArray(s.proposed_goals)){
      var box=document.getElementById('cogGoals'),cnt=document.getElementById('cogCount');
      if(cnt)cnt.textContent=s.proposed_goals.length?'('+s.proposed_goals.length+')':'';
      if(box)box.innerHTML=s.proposed_goals.slice(0,4).map(function(g){
        return '<div style="padding:8px 10px;border-radius:9px;background:var(--glass)"><div style="font-size:.72rem">'+escapeHtml(g.text||g)+'</div></div>';
      }).join('')||'<div style="font-size:.7rem;color:var(--dim)">No proposed goals yet — reflect to generate one.</div>';
    }
  });
  // fallback to reverie+drive if sovereign/state missing
  gj('/api/v1/reverie/stats').then(function(s){if(s&&s.latest_goal&&document.getElementById('cogGoal').textContent==='—')document.getElementById('cogGoal').textContent=s.latest_goal;});
  gj('/api/v1/drive/goals?status=proposed').then(function(d){
    var box=document.getElementById('cogGoals'),cnt=document.getElementById('cogCount');
    if(!box||box.children.length)return;
    var goals=(d&&d.goals)||[];if(cnt)cnt.textContent=goals.length?'('+goals.length+')':'';
    box.innerHTML=goals.slice(0,4).map(function(g){
      return '<div style="padding:8px 10px;border-radius:9px;background:var(--glass)">'+
        '<div style="font-size:.72rem;margin-bottom:6px">'+escapeHtml(g.text)+'</div>'+
        '<div style="display:flex;gap:6px">'+
        '<button onclick="approveGoal(\''+g.id+'\')" style="flex:1;border:1px solid var(--brd);cursor:pointer;border-radius:7px;padding:5px;font-size:.64rem;font-weight:700;background:var(--accent-soft);color:var(--accent)">APPROVE</button>'+
        '<button onclick="runGoal(\''+g.id+'\')" style="flex:1;border:0;cursor:pointer;border-radius:7px;padding:5px;font-size:.64rem;font-weight:700;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff">RUN</button>'+
        '</div></div>';
    }).join('')||'';
  });
}
function reflectNow(){fetch('/api/v1/reverie/reflect',{method:'POST'}).then(function(){loadCognition();});}
function approveGoal(id){fetch('/api/v1/drive/'+id+'/approve',{method:'POST'}).then(function(){loadCognition();});}
function runGoal(id){
  fetch('/api/v1/drive/'+id+'/approve',{method:'POST'}).then(function(){
    return fetch('/api/v1/drive/'+id+'/run',{method:'POST'});}).then(function(r){return r.json();})
    .then(function(d){launch(d&&d.error?('Vetoed: '+(d.error||'')):'Goal executed');loadCognition();})
    .catch(function(){loadCognition();});
}
function setOpenModeBtn(on){var b=document.getElementById('openModeBtn');if(!b)return;b.textContent=on?'ON':'OFF';
  b.style.background=on?'linear-gradient(135deg,var(--accent),var(--accent2))':'var(--accent-soft)';b.style.color=on?'#fff':'var(--accent)';}
function toggleOpenMode(){
  gj('/api/v1/license/open-mode').then(function(s){
    var next=!(s&&s.open_mode);
    fetch('/api/v1/license/open-mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:next})})
      .then(function(r){return r.json();}).then(function(d){setOpenModeBtn(d&&d.open_mode);loadCognition();});
  });
}

// ---------- Periodic refresh ----------
function loadDriverStatus(){
  gj('/api/v1/ascent/driver').then(function(d){
    var el=document.getElementById('cogReflect');
    if(!el)return;
    if(d&&d.status){
      var statusText='⟳ '+(d.status==='running'?'⏵':'⏸')+' '+(d.interval_s||'')+'s';
      el.title='Ascent: '+d.status+(d.last_cycle_ts?' · last cycle '+(Math.floor((Date.now()/1000-d.last_cycle_ts)/60))+'m ago':'');
    }
  });
  gj('/api/v1/reverie/driver').then(function(d){
    var el=document.getElementById('cogGoal');
    if(!el||!d)return;
    if(d.status&&el.textContent==='—'){
      el.textContent='Reverie driver: '+d.status+(d.reflections?' ('+d.reflections+' reflections)':'');
    }
  });
}
function refresh(){loadAgents();loadCognition();loadDriverStatus();
  gj('/api/v1/license/status').then(function(d){if(d){document.getElementById('tierBadge').textContent=d.open_mode?'OPEN':(d.tier?d.tier.toUpperCase():'FREE');setOpenModeBtn(d.open_mode);}});
}
loadInfo();refresh();setInterval(refresh,10000);
connectWS();setInterval(function(){if(!ws||ws.readyState!==1)pollMetrics();},5000);

// ---------- license / pricing modal ----------
var FALLBACK_PLANS=[
  {tier:'free',name:'Free',price:0,feat:false,perks:['Manual desktop','Local agents','Community support']},
  {tier:'pro',name:'Pro',price:5,feat:false,perks:['Live research','The Guild','Agent memory']},
  {tier:'sovereign',name:'Sovereign',price:25,feat:true,perks:['Sovereign autonomy','Cloud AI','Self-improvement','Apply-gate']},
  {tier:'enterprise',name:'Enterprise',price:50,feat:false,perks:['Multi-seat','Priority support','Private cloud keys']}
];
function renderPlans(plans){
  document.getElementById('plans').innerHTML=plans.map(function(p){
    var price=p.price?('$'+p.price+'<small>/yr</small>'):'Free';
    return '<div class="plan'+(p.feat?' feat':'')+'"><div class="nm">'+p.name+'</div><div class="pr">'+price+'</div><ul>'+
      p.perks.map(function(x){return '<li>'+x+'</li>';}).join('')+'</ul><button onclick="checkout(\''+p.tier+'\')">'+(p.price?'Choose '+p.name:'Current')+'</button></div>';
  }).join('');
}
function openModal(){document.getElementById('scrim').classList.add('open');
  gj('/api/v1/license/pricing').then(function(d){renderPlans((d&&d.plans&&d.plans.length)?d.plans:FALLBACK_PLANS);});}
function closeModal(){document.getElementById('scrim').classList.remove('open');}
function checkout(tier){if(tier==='free'){closeModal();return;}
  var note=document.getElementById('modalNote');
  fetch('/api/v1/billing/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tier:tier})})
    .then(function(r){return r.json();}).then(function(d){
      note.innerHTML=d&&d.checkout_url?'Opening secure checkout for <b>'+tier+'</b>…':'Checkout for <b>'+tier+'</b> is being provisioned. Paste a signed license key in Settings to activate offline.';
      if(d&&d.checkout_url)window.open(d.checkout_url,'_blank');})
    .catch(function(){note.innerHTML='Checkout endpoint not configured — paste a signed license key in Settings to activate <b>'+tier+'</b> offline.';});
}
document.getElementById('scrim').addEventListener('click',function(e){if(e.target===this)closeModal();});

window.addEventListener('load',function(){setTimeout(function(){var s=document.getElementById('splash');s.style.opacity='0';setTimeout(function(){s.style.display='none';},800);},450);});
</script>
</body>
</html>"""
