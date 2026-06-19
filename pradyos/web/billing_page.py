"""Billing & pricing page — HTML served by FastAPI.

Serves GET /billing as a clean pricing table and wires into the existing
checkout endpoints. No external dependencies; pure HTML+CSS.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi.responses import HTMLResponse, JSONResponse

from pradyos.licensing.vault import PRICING, LicenseVault, _TIER_ORDER

TIER_NAMES = {
    "free": "Free",
    "pro": "Pro",
    "sovereign": "Sovereign",
    "enterprise": "Enterprise",
}

TIER_PRICES = {
    "free": 0,
    "pro": 9,
    "sovereign": 29,
    "enterprise": 99,
}

TIER_COLORS = {
    "free": "#6b7280",
    "pro": "#3b82f6",
    "sovereign": "#8b5cf6",
    "enterprise": "#ef4444",
}

TIER_FEATURES = {
    "free": [
        "Skill engine (learn, run, reinforce, match)",
        "Dev swarm mode (6-role guild)",
        "Codemap introspection (430+ modules)",
        "8 internal benchmarks",
        "Local personal mode",
    ],
    "pro": [
        "Everything in Free",
        "Audit log export (JSON/CSV)",
        "Multi-agent guild memory",
        "Research agent integration",
        "Priority community support",
    ],
    "sovereign": [
        "Everything in Pro",
        "Blueprint manager & validator",
        "Prometheus metrics endpoint",
        "Self-improvement loop (Ascent)",
        "Sovereign governance chamber",
        "Causal credit assignment (L5)",
    ],
    "enterprise": [
        "Everything in Sovereign",
        "Fleet orchestration (multi-machine)",
        "AEGIS integrity boot checks",
        "Enterprise seat management",
        "Priority support SLA",
        "Private cloud keys / BYO-model",
    ],
}

_PAGE_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #e2e8f0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
}
header {
    text-align: center;
    padding: 3rem 1rem 1rem;
    max-width: 800px;
}
header h1 {
    font-size: 2rem;
    font-weight: 700;
    background: linear-gradient(135deg, #60a5fa, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.5rem;
}
header p { color: #94a3b8; font-size: 1.05rem; line-height: 1.6; }
.pricing-grid {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 1.5rem;
    padding: 2rem 1rem 4rem;
    max-width: 1200px;
    width: 100%;
}
.card {
    background: rgba(30, 41, 59, 0.8);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 1rem;
    padding: 1.75rem;
    width: 260px;
    display: flex;
    flex-direction: column;
    transition: transform .15s, box-shadow .15s;
}
.card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,.3); }
.card.featured {
    border-color: #8b5cf6;
    box-shadow: 0 0 20px rgba(139, 92, 246, 0.15);
    transform: scale(1.04);
}
.card.featured:hover { transform: scale(1.04) translateY(-4px); }
.card h2 { font-size: 1.25rem; font-weight: 600; margin-bottom: 0.25rem; }
.card .price {
    font-size: 2.5rem;
    font-weight: 700;
    margin: 0.75rem 0 0.25rem;
}
.card .price span { font-size: 1rem; font-weight: 400; color: #94a3b8; }
.card .tagline { color: #94a3b8; font-size: 0.85rem; margin-bottom: 1rem; }
.card ul { list-style: none; flex: 1; margin: 1rem 0 1.5rem; }
.card ul li {
    padding: 0.35rem 0;
    font-size: 0.9rem;
    color: #cbd5e1;
}
.card ul li::before {
    content: "\\2713\\00a0";
    color: #22c55e;
    font-weight: 700;
}
.card button {
    padding: 0.65rem 1.5rem;
    border: none;
    border-radius: 0.5rem;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    color: #fff;
    transition: opacity .15s;
}
.card button:hover { opacity: 0.85; }
.card .current-tier {
    text-align: center;
    padding: 0.65rem 1.5rem;
    border-radius: 0.5rem;
    font-size: 0.85rem;
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
    border: 1px solid rgba(34, 197, 94, 0.3);
}
footer {
    text-align: center;
    padding: 1.5rem;
    color: #64748b;
    font-size: 0.85rem;
}
footer a { color: #60a5fa; text-decoration: none; }
footer a:hover { text-decoration: underline; }
"""


def _build_page(current_tier: str, open_mode: bool) -> str:
    cards_html = ""
    for tier in sorted(_TIER_ORDER, key=lambda t: _TIER_ORDER[t]):
        info = TIER_NAMES[tier]
        price = TIER_PRICES.get(tier, 0)
        features = TIER_FEATURES.get(tier, [])
        color = TIER_COLORS.get(tier, "#6b7280")
        featured = tier == "sovereign"
        is_current = tier == current_tier

        card_class = "card"
        if featured:
            card_class += " featured"

        button_html = ""
        if open_mode:
            button_html = f'<div class="current-tier" style="background:rgba(139,92,246,0.15);color:#a78bfa;border-color:rgba(139,92,246,0.3)">All Features Unlocked</div>'
        elif is_current and tier == "free":
            button_html = f'<div class="current-tier">Current Plan</div>'
        elif is_current:
            button_html = f'<div class="current-tier">Active</div>'
        elif tier == "free":
            button_html = (
                f'<button style="background:{color}" '
                f'onclick="window.location.href=\'/\'">Get Started</button>'
            )
        else:
            button_html = (
                f'<button style="background:{color}" '
                f'onclick="window.location.href=\'/api/v1/billing/checkout?tier={tier}\'">'
                f"Subscribe &mdash; ${price}/mo</button>"
            )

        price_html = (
            f'<div class="price">Free</div>'
            if price == 0
            else f'<div class="price">${price}<span>/mo</span></div>'
        )

        cards_html += f"""
        <div class="{card_class}">
            <h2 style="color:{color}">{info}</h2>
            {price_html}
            <div class="tagline">{description_for(tier)}</div>
            <ul>
                {"".join(f"<li>{f}</li>" for f in features)}
            </ul>
            {button_html}
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pricing — PradySovereign</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<header>
<h1>PradySovereign</h1>
<p>Open-core pricing. All core features are free; paid tiers unlock
governance, fleet orchestration, and enterprise audit capabilities.</p>
</header>
<div class="pricing-grid">
{cards_html}
</div>
<footer>
<p><a href="/">Back to Console</a> &middot;
<a href="https://github.com/prady4the4bady/PradyOS-S">GitHub</a></p>
</footer>
</body>
</html>"""


def description_for(tier: str) -> str:
    descs = {
        "free": "Everything you need to build and experiment locally.",
        "pro": "For teams that need audit trails and shared memory.",
        "sovereign": "Full autonomy with governance, self-improvement, and metrics.",
        "enterprise": "Fleet-scale deployment with integrity guarantees.",
    }
    return descs.get(tier, "")


def register_billing_page_routes(app: Any, vault: LicenseVault | None = None) -> None:
    if vault is None:
        vault = LicenseVault()

    @app.get("/billing", include_in_schema=False)
    async def billing_page() -> HTMLResponse:
        html = _build_page(current_tier=vault.tier(), open_mode=vault.open_mode())
        return HTMLResponse(html)

    @app.get("/billing/success", include_in_schema=False)
    async def billing_success(tier: str = "free") -> HTMLResponse:
        name = TIER_NAMES.get(tier.lower(), tier)
        body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>Payment Confirmed — PradySovereign</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<header>
<h1>Payment Confirmed</h1>
<p>Your <strong>{name}</strong> tier is now active.</p>
<p style="margin-top:1rem"><a href="/" style="color:#60a5fa">Return to Console</a></p>
</header>
</body>
</html>"""
        return HTMLResponse(body)
