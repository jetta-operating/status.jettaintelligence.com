# Status UI Roadmap

This page tracks product-level improvements that should survive beyond chat.

## Company-scoped filtering

Goal: the status page should support filtering by operating audience.

Required scopes:

| Scope | Includes |
|---|---|
| Jetta | Jetta Intelligence, Jetta Operating, Jetta identity, and Jetta platform services. |
| AIC | AIC corporate websites, AIC-owned apps, and AIC operating dependencies. |
| Greenmark | Greenmark websites, HT Disposal, Cerebro, QA, auth, reconciliation, data-quality, and Greenmark-owned dependencies. |
| Shared vendors | GitHub, Railway, Vercel, Supabase, OpenRouter, Claude/Anthropic, OpenAI/ChatGPT, and other shared infrastructure or AI vendors. |
| Deprecated | Paused or retired checks preserved for provenance but not monitored as active obligations. |

First implementation should be simple:

- add a human-maintained `Company scope` value for every active monitor in
  `docs/service-catalog.md`,
- render filter tabs or a segmented control on the Upptime site,
- default to `All`,
- keep vendor dependencies visible in `Shared vendors`,
- ensure Greenmark/Cerebro assets can be viewed without scanning unrelated
  Jetta/AIC services.

This is a presentation and triage feature, not a security boundary. Cloudflare
Access controls who can see the private status plane; company filters control
how approved users navigate it.

## Access-gate proof

Keep `tools/configure_cloudflare_access.py --verify-only --strict` as the
definition of done for hostname protection. A successful proof must show:

- public HTTP does not return GitHub Pages directly,
- system/default/public DNS views resolve to Cloudflare edge addresses,
- forced Cloudflare-edge probes detect the Access gate.

If incognito loads the page without a Cloudflare challenge, rerun the strict
check and treat any GitHub Pages `200` response as a release blocker for
sensitive content.
