# Service Catalog

This page is the human taxonomy for the monitors in `.upptimerc.yml`.

Upptime owns the generated live state. This catalog owns the maintainers'
intent: why a service is monitored, which group it belongs to, and what kind of
truth the check provides.

## Jetta websites and identity surfaces

| Monitor | What it proves | Notes |
|---|---|---|
| Jetta Intelligence Website | Public website loads. | External availability only. |
| Jetta Operating Website | Public website loads. | External availability only. |
| Jetta Login | Jetta login surface responds. | Does not prove user-specific login success. |

## AIC and Jetta-managed application surfaces

| Monitor | What it proves | Notes |
|---|---|---|
| AIC Holdings Website | Public website loads. | External availability only. |
| Sable | Current Sable surface responds. | Validate owner/runbook before adding deeper checks. |
| Artemis | Current Artemis surface responds. | Validate owner/runbook before adding deeper checks. |
| Meridian | Current Meridian surface responds. | Validate owner/runbook before adding deeper checks. |

## Greenmark and Cerebro surfaces

| Monitor | What it proves | Notes |
|---|---|---|
| Greenmark Website | Public website loads. | External availability only. |
| HT Disposal Website | Public website loads. | External availability only. |
| Cerebro Production Health | Production health endpoint responds. | Does not prove every Cerebro workflow. |
| Cerebro Staging Health | Staging health endpoint responds. | Used for release confidence. |
| Cerebro QA Site | QA site responds or redirects as expected. | Expected `200` or `302`. |
| Supabase Production Auth Health | Supabase auth health endpoint is reachable. | Expected `200` or `401`; does not prove invite flow. |

## Infrastructure vendors and control planes

| Monitor | What it proves | Notes |
|---|---|---|
| GitHub | GitHub web surface responds. | Dependency for repo/actions workflow. |
| GitHub Status | GitHub status page responds. | Vendor-reported status source. |
| Railway Control Plane | Railway GraphQL endpoint responds with an expected unauthenticated/control-plane status. | Expected `200`, `400`, `401`, `403`, or `405`. |
| Railway Status Page | Railway status page responds. | Vendor-reported status source. |
| Vercel | Vercel web surface responds. | Vendor dependency. |
| Vercel Status | Vercel status page responds. | Vendor-reported status source. |
| Supabase Status | Supabase status page responds. | Vendor-reported status source. |

## AI vendor surfaces and component-status APIs

| Monitor | What it proves | Notes |
|---|---|---|
| OpenRouter | OpenRouter web surface responds. | Vendor dependency. |
| OpenRouter API Models | OpenRouter models endpoint responds. | Public API availability check. |
| OpenRouter Status | OpenRouter status page responds. | Vendor-reported status source. |
| Claude Web | `claude.ai` responds. | Expected `200` or bot-protection `403`. |
| Claude Status All Services | Claude status page responds. | Vendor-reported rollup page. |
| Claude Components API | Claude component-status JSON endpoint responds. | Proves status feed availability, not a specific component's health. |
| Claude Console | Anthropic console responds. | Does not prove account-specific login. |
| Anthropic API Models | Anthropic API models endpoint responds. | Expected `200` or unauthenticated `401`. |
| ChatGPT Web | ChatGPT web surface responds. | Expected `200` or bot-protection `403`. |
| OpenAI API Models | OpenAI API models endpoint responds. | Expected `200` or unauthenticated `401`. |
| OpenAI Status All Services | OpenAI status page responds. | Vendor-reported rollup page. |
| OpenAI Components API | OpenAI component-status JSON endpoint responds. | Proves status feed availability, not a specific component's health. |

## Deprecated or paused checks

Deprecated checks live in [`deprecated-services.md`](./deprecated-services.md).

Do not re-add a deprecated service unless there is a current production URL and
a clear owner/runbook path.

## Future metadata to add

The next useful improvement is a small owner/runbook table for each active
monitor:

| Monitor | Owner | Runbook | Escalation |
|---|---|---|---|
| TBD | TBD | TBD | TBD |

Keep this human-maintained until there is a reason to generate it.
