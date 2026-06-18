# Monetization — Open-Core Billing

PradySovereign uses an open-core model. The core agent runtime, all six
cognitive primitives, the dev swarm examples, and local personal mode are
**free and open-source**. Paid tiers unlock governance, audit, fleet, and
enterprise features.

## What's Free

- Skill engine (learn, run, reinforce, match)
- Dev swarm mode — 6-role multi-agent guild
- Codemap introspection — 430+ modules, 72k LOC
- 8 internal throughput benchmarks
- Local personal mode (sovereign daemon)
- All cognitive primitives (SemanticMemory, AttentionSketch, etc.)

## Paid Tiers

| Tier | Price | Key unlocks |
|------|-------|-------------|
| Pro | $9/mo | Audit log export, guild memory, research agent |
| Sovereign | $29/mo | Blueprint manager, Prometheus metrics, self-improvement loop |
| Enterprise | $99/mo | Fleet orchestration, AEGIS integrity, seat management, SLA |

## Payment Providers

Two payment backends are supported. Both are opt-in and env-driven; when
unconfigured, the OS runs entirely on the free tier.

### Stripe (default)

Set these environment variables:

```
STRIPE_SECRET_KEY           # Live checkout (Stripe dashboard)
STRIPE_WEBHOOK_SECRET       # Webhook signature verification
PRADYOS_STRIPE_PRICE_PRO    # Override Stripe Price id for Pro
PRADYOS_STRIPE_PRICE_SOVEREIGN  # Override for Sovereign
PRADYOS_STRIPE_PRICE_ENTERPRISE # Override for Enterprise
STRIPE_SUCCESS_URL          # Redirect after payment
STRIPE_CANCEL_URL           # Redirect on cancellation
```

### Polar.sh (alternative)

Polar.sh is a payment platform built for open-source and indie developers. It
provides simpler product management and per-commit funding. Set:

```
POLAR_ACCESS_TOKEN                  # Polar.sh API access
PRADYOS_POLAR_PRODUCT_PRO           # Polar product ID for Pro
PRADYOS_POLAR_PRODUCT_SOVEREIGN     # Polar product ID for Sovereign
PRADYOS_POLAR_PRODUCT_ENTERPRISE    # Polar product ID for Enterprise
PRADYOS_PAYMENT_PROVIDER=polar      # Switch from Stripe to Polar
```

When `PRADYOS_PAYMENT_PROVIDER=polar`, the checkout endpoint redirects to
`https://buy.polar.sh/{product_id}` instead of Stripe Checkout.

## Billing API

See [docs/COMMANDS.md](COMMANDS.md) for billing API commands.

## License Activation

When a payment completes:

- **Stripe**: the webhook at `/api/v1/billing/webhook` verifies the signature,
  extracts the tier from `checkout.session.completed`, and calls
  `vault.grant_tier()` to activate it immediately.
- **Polar.sh**: webhook support is planned (Polar sends webhooks to a
  configurable URL). For now, activate manually via the admin API.
- **Manual**: send `POST /api/v1/license/activate` with `{"tier": "pro"}`
  and the `X-Admin-Token` header (if `PRADYOS_ADMIN_TOKEN` is set).

## Feature Gating

Feature gating is enforced at two levels:

1. **API level**: enterprise routes (`/api/v1/aegis/*`, `/api/v1/metrics`,
   `/metrics`) return HTTP 402 with a JSON body when the current tier is
   insufficient.
2. **SDK level**: `LicenseVault.entitled(feature)` returns `True`/`False`.
   `LicenseVault.require(feature)` raises `LicenseError` if gated.

The full gate map is in `pradyos/licensing/vault.py` (`FEATURE_MIN_TIER`).
Any feature not listed is ungated (free).
