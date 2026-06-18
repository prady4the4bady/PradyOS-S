"""Landing page HTML for the public marketing website at /"""

LANDING_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PradySovereign — Governed Autonomous AI</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #050510;
    color: #e2e8f0;
    overflow-x: hidden;
  }
  .star { position: fixed; border-radius: 50%; background: white; pointer-events: none; z-index: 0; }
  .container { max-width: 1100px; margin: 0 auto; padding: 0 24px; position: relative; z-index: 1; }

  /* Hero */
  .hero { min-height: 85vh; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 80px 0; }
  .hero h1 { font-size: 4.5rem; font-weight: 800; background: linear-gradient(135deg, #c9b6ff, #7c3aed); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: -0.02em; }
  .hero p { font-size: 1.15rem; color: #94a3b8; max-width: 600px; margin: 20px auto 36px; line-height: 1.7; }
  .hero-btns { display: flex; gap: 16px; flex-wrap: wrap; justify-content: center; }
  .btn-primary { display: inline-flex; align-items: center; gap: 8px; padding: 14px 32px; border-radius: 12px; font-weight: 700; font-size: 0.95rem; border: none; cursor: pointer; text-decoration: none; background: linear-gradient(135deg, #7c3aed, #a78bfa); color: white; }
  .btn-secondary { display: inline-flex; align-items: center; gap: 8px; padding: 14px 32px; border-radius: 12px; font-weight: 700; font-size: 0.95rem; border: 1px solid rgba(124,58,237,0.3); cursor: pointer; text-decoration: none; background: rgba(124,58,237,0.1); color: #c9b6ff; }

  /* Sections */
  section { padding: 80px 0; }
  .section-title { font-size: 2rem; font-weight: 700; text-align: center; margin-bottom: 48px; background: linear-gradient(135deg, #c9b6ff, #7c3aed); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }

  /* How it works */
  .cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
  .card { background: rgba(255,255,255,0.04); border: 1px solid rgba(124,58,237,0.2); border-radius: 16px; padding: 36px 28px; text-align: center; backdrop-filter: blur(12px); }
  .card-icon { font-size: 2.5rem; margin-bottom: 16px; }
  .card h3 { font-size: 1.15rem; font-weight: 700; margin-bottom: 10px; color: #c9b6ff; }
  .card p { font-size: 0.9rem; color: #94a3b8; line-height: 1.6; }

  /* Pricing */
  .pricing-box { max-width: 520px; margin: 0 auto; background: rgba(255,255,255,0.04); border: 1px solid rgba(124,58,237,0.2); border-radius: 16px; padding: 48px 36px; text-align: center; }
  .pricing-box h3 { font-size: 1.5rem; font-weight: 700; margin-bottom: 12px; }
  .pricing-box .price { font-size: 3rem; font-weight: 800; color: #c9b6ff; }
  .pricing-box .price span { font-size: 1rem; color: #94a3b8; }
  .pricing-box p { color: #94a3b8; margin: 16px 0 28px; line-height: 1.6; }

  /* Install */
  .install-box { max-width: 640px; margin: 0 auto; }
  .code-block { position: relative; background: rgba(0,0,0,0.4); border: 1px solid rgba(124,58,237,0.2); border-radius: 12px; padding: 24px; overflow-x: auto; }
  .code-block pre { font-family: 'JetBrains Mono', 'Cascadia Code', monospace; font-size: 0.85rem; line-height: 1.8; color: #c9b6ff; }
  .copy-btn { position: absolute; top: 12px; right: 12px; padding: 6px 14px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; border: 1px solid rgba(124,58,237,0.3); cursor: pointer; background: rgba(124,58,237,0.15); color: #c9b6ff; }
  .copy-btn:hover { background: rgba(124,58,237,0.3); }
  .copy-btn.copied { background: rgba(34,197,94,0.2); border-color: #22c55e; color: #22c55e; }

  /* Footer */
  footer { border-top: 1px solid rgba(124,58,237,0.15); padding: 40px 0; text-align: center; }
  footer a { color: #94a3b8; text-decoration: none; margin: 0 16px; font-size: 0.85rem; transition: color 0.2s; }
  footer a:hover { color: #c9b6ff; }

  @media (max-width: 768px) {
    .hero h1 { font-size: 2.5rem; }
    .cards { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div id="stars"></div>

<div class="container">
  <section class="hero">
    <h1>PradySovereign</h1>
    <p>A governed, self-improving cognitive layer for autonomous AI agents. Ships in production with 50+ probabilistic modules, 6 autonomy layers, and signed sovereign gating.</p>
    <div class="hero-btns">
      <a href="#install" class="btn-primary">⬇ Download & Install</a>
      <a href="https://github.com/prady4the4bady/PradyOS-S" class="btn-secondary">★ Star on GitHub</a>
    </div>
  </section>

  <section>
    <h2 class="section-title">How It Works</h2>
    <div class="cards">
      <div class="card">
        <div class="card-icon">🧠</div>
        <h3>Cognitive Layer</h3>
        <p>50+ probabilistic data structures (MinHash, HyperLogLog, T-Digest, Count-Sketch) composed into semantic memory, attention sketches, and experience distributions.</p>
      </div>
      <div class="card">
        <div class="card-icon">⚡</div>
        <h3>Dev Swarms</h3>
        <p>Guild of 6 specialist agents (Vega, Orion, Lyra, Atlas, Nova, Draco) collaborate on objectives — orchestrate, research, engineer, analyze, review, and synthesize.</p>
      </div>
      <div class="card">
        <div class="card-icon">🔒</div>
        <h3>Governed Autonomy</h3>
        <p>L1–L6 autonomy layers with Sovereign gating, AEGIS tamper-evident boot, and Three Laws enforcement. Self-healing loops, self-improvement, and full audit trails.</p>
      </div>
    </div>
  </section>

  <section>
    <h2 class="section-title">Pricing</h2>
    <div class="pricing-box">
      <h3>Open Core</h3>
      <div class="price">$0 <span>forever</span></div>
      <p>Free for developers. Self-host the full Sovereign Edition. Enterprise features (SSO, audit, TPM binding) available for teams.</p>
      <a href="/billing" class="btn-primary">View Pricing →</a>
    </div>
  </section>

  <section id="install">
    <h2 class="section-title">Install</h2>
    <div class="install-box">
      <div class="code-block">
        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
        <pre id="install-code">git clone https://github.com/prady4the4bady/PradyOS-S
cd PradyOS-S
pip install -e .
python examples/hello_skill.py</pre>
      </div>
    </div>
  </section>
</div>

<footer>
  <a href="https://github.com/prady4the4bady/PradyOS-S">GitHub</a>
  <a href="/billing">Pricing</a>
  <a href="/console">Console</a>
</footer>

<script>
function copyCode(btn) {
  var code = document.getElementById('install-code').textContent;
  navigator.clipboard.writeText(code).then(function() {
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(function() { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
  });
}

(function() {
  var s = document.getElementById('stars');
  for (var i = 0; i < 120; i++) {
    var dot = document.createElement('div');
    dot.className = 'star';
    dot.style.left = (Math.random() * 100) + '%';
    dot.style.top = (Math.random() * 70) + '%';
    var sz = Math.random() * 2 + 0.5;
    dot.style.width = sz + 'px';
    dot.style.height = sz + 'px';
    dot.style.opacity = Math.random() * 0.6 + 0.2;
    dot.style.animation = 'twinkle ' + (Math.random() * 3 + 2) + 's ease-in-out infinite alternate';
    s.appendChild(dot);
  }
})();
</script>
<style>
@keyframes twinkle { from { opacity: 0.1; } to { opacity: 0.8; } }
html { scroll-behavior: smooth; }
</style>
</body>
</html>"""
