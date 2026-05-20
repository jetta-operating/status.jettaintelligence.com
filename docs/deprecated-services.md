# Deprecated Status Checks

These services are intentionally not checked by the public Jetta Service
Status page. They were originally added during first-pass inventory, then
trimmed because the current probe evidence indicated retired, unresolved, or
non-current endpoints rather than active service obligations.

If any service below becomes current again, move it back into `.upptimerc.yml`
with a working production URL and let Upptime create fresh history from that
point forward.

| Service | Former URL | Last probe evidence | Deprecated on | Notes |
|---|---|---|---|---|
| Sable Data | `https://sable-data.jettaintelligence.com` | DNS did not resolve; Upptime code `0` | 2026-05-19 | Removed from active checks until a current Sable data surface exists. |
| Robin Meridian Chat | `https://chat.jettaintelligence.com` | DNS did not resolve; Upptime code `0` | 2026-05-19 | Removed from active checks until a current chat surface exists. |
| Anthraseek | `https://anthraseek.vercel.app` | HTTP `404` | 2026-05-19 | Removed from active checks; Vercel deployment name no longer represents a live obligation. |
| Whisper | `https://whisper.jettaintelligence.com` | DNS did not resolve; Upptime code `0` | 2026-05-19 | Removed from active checks until the hostname is restored or replaced. |
| AICync | `https://cync.aicholdings.com` | HTTP `404` | 2026-05-19 | Removed from active checks until a current AICync production URL is confirmed. |
| Helm | `https://jetta-helm.vercel.app` | HTTP `404` | 2026-05-19 | Removed from active checks; Vercel deployment name no longer represents a live obligation. |
| Data Orchestration | `https://data.jettaintelligence.com` | DNS did not resolve; Upptime code `0` | 2026-05-19 | Removed from active checks until an external data orchestration health URL exists. |

## Trim Proof

Evidence collected from the status repo and direct probes:

```text
Sable Data              https://sable-data.jettaintelligence.com  DNS did not resolve; Upptime code 0
Robin Meridian Chat    https://chat.jettaintelligence.com        DNS did not resolve; Upptime code 0
Anthraseek             https://anthraseek.vercel.app             HTTP 404
Whisper                https://whisper.jettaintelligence.com     DNS did not resolve; Upptime code 0
AICync                 https://cync.aicholdings.com              HTTP 404
Helm                   https://jetta-helm.vercel.app             HTTP 404
Data Orchestration     https://data.jettaintelligence.com        DNS did not resolve; Upptime code 0
```
