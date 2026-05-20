# Status Site Access Control

## Current conclusion

Do not use a client-side password gate as the security boundary for this
status site.

## Current implementation state

As of 2026-05-20, `status.jettaintelligence.com` is protected at the custom
hostname by Cloudflare Access.

Current verified behavior:

- Cloudflare DNS has the status CNAME proxied through Cloudflare.
- System DNS, default `dig`, `1.1.1.1`, and `8.8.8.8` resolve the hostname to
  Cloudflare edge addresses.
- `https://status.jettaintelligence.com/` returns a Cloudflare-managed access
  block/redirect before site content loads.
- Forced Cloudflare-edge probes return the Cloudflare Access login path.

Important boundary: Cloudflare Access protects the custom hostname. It does not
by itself make the public GitHub repository, generated history files, or raw
GitHub content undiscoverable if those remain public.

If incognito ever loads the page without an Access challenge, treat that as a
verification failure and run the strict check below. Incognito clears browser
session state, not every DNS resolver cache or origin-bypass path.

The status site is an Upptime static site. Upptime's generated website loads
status data from the GitHub repository and raw GitHub content at runtime. That
means any password check implemented only in browser JavaScript can hide the
page from casual visitors, but it cannot prevent a technical user from reading
the shipped HTML, JavaScript, history files, API JSON, or raw GitHub content.

If the goal is "only certain people can see the site," authentication must
happen before the content is served.

## Recommended pattern

Use Cloudflare Access in front of `status.jettaintelligence.com`.

## Relationship to `login.jettaintelligence.com`

`login.jettaintelligence.com` is the Access administration/control-plane app.
It is not the identity provider and status traffic should not be routed through
it.

The intended architecture is:

- Cloudflare Access authenticates users for `status.jettaintelligence.com`.
- Cloudflare Access authenticates admins for `login.jettaintelligence.com`.
- `login.jettaintelligence.com` reads and explains Access inventory and policy
  state.
- Status content is served directly from GitHub Pages behind Cloudflare Access.

So when a user opens `https://status.jettaintelligence.com`, the browser should
go to Cloudflare's Access login page for **Jetta Service Status**, not to the
login admin app. Both hostnames should stay as separate Access applications
under the same Cloudflare team and the same intended identity policy.

Preferred user experience:

1. User opens `https://status.jettaintelligence.com`.
2. Cloudflare Access blocks the request before serving the site.
3. User enters an approved email address.
4. Cloudflare sends a one-time PIN.
5. User enters the PIN and gets the status page.

This avoids shared passwords, avoids embedding a reversible secret in the
static site, and prevents the status content from loading until the user is
authorized.

## Why not a static password?

A static password prompt can be useful only as a casual screen.

It does not meet the stronger requirement because:

- the password-checking logic must be shipped to the browser,
- the static assets are still served before authorization,
- network requests can reveal the underlying data sources,
- public GitHub Pages/raw URLs remain readable if the repo and site are public,
- anyone with enough curiosity can bypass or reverse engineer the prompt.

Use this only for non-sensitive pages where the goal is "discourage casual
viewing," not "control access."

## Stronger options

### Option A: Cloudflare Access over the current GitHub Pages site

This is the lowest-friction path if the custom domain is already managed in
Cloudflare.

Requirements:

- `status.jettaintelligence.com` DNS is proxied through Cloudflare.
- Cloudflare Access application protects the hostname.
- Access policy allows only approved emails, email domains, or identity groups.
- One-time PIN is enabled, unless an identity provider such as Google or
  Microsoft is preferred.

Notes:

- This protects access at the edge.
- GitHub Pages can remain the origin.
- If the GitHub repo remains public, raw GitHub data may still be discoverable
  outside the protected domain. For stronger privacy, use Option B.

### Option B: Private repo plus authenticated content path

For stronger protection, make the status repo private or move the generated
site/data behind an authenticated edge.

Possible shapes:

- Cloudflare Pages protected by Cloudflare Access.
- Private GitHub repo plus a Cloudflare Worker/API proxy that fetches only for
  authorized users.
- Private status site hosted behind another identity-aware reverse proxy.

This is the right direction if service names, incidents, or uptime history
become sensitive.

### Option C: Public status page with trimmed content

If the status page is meant to be public, keep it public but trim anything that
should not be public.

Examples:

- Use public-friendly service names.
- Avoid internal hostnames.
- Avoid exposing vendors or implementation details that should stay private.
- Keep sensitive incidents in a separate private operational channel.

## Decision rule

Use this rule before adding sensitive content:

| Goal | Acceptable control |
|---|---|
| Public trust page | Public Upptime page is fine; trim sensitive details. |
| Keep casual visitors out | Static password gate is acceptable but weak. |
| Only approved people can see it | Cloudflare Access or equivalent edge auth. |
| Content/data must not be publicly discoverable | Private repo and private serving path. |

## Implementation checklist for Cloudflare Access

1. Confirm Cloudflare manages DNS for `jettaintelligence.com`.
2. Supply an API token with:
   - `Zone:DNS:Edit` for `jettaintelligence.com`,
   - `Zone:Zone:Read` for `jettaintelligence.com`,
   - `Access: Apps and Policies: Edit` for the Cloudflare account.
3. Dry-run the repo automation:
   ```bash
   CLOUDFLARE_API_TOKEN=... tools/configure_cloudflare_access.py
   ```
4. Apply the repo automation:
   ```bash
   CLOUDFLARE_API_TOKEN=... tools/configure_cloudflare_access.py --apply
   ```
5. Confirm `status.jettaintelligence.com` is proxied through Cloudflare.
6. Confirm the Access self-hosted application exists for
   `status.jettaintelligence.com`.
7. Confirm the reusable allow policy includes the approved email domains or
   individual emails. The automation default is:
   - `jettaintelligence.com`,
   - `aicholdings.com`,
   - `greenmarkwaste.com`.
8. Enable one-time PIN or the chosen identity provider.
9. Test from an incognito browser:
   - page does not load before auth,
   - approved user can enter,
   - unapproved user is blocked,
   - static assets and history links are also protected.
10. Re-test `https://status.jettaintelligence.com/history/<slug>/` deep links.

## Verification commands

Run these after applying Cloudflare Access:

```bash
tools/configure_cloudflare_access.py --verify-only --strict
curl -sSI https://status.jettaintelligence.com/ | sed -n '1,20p'
curl -sSI https://status.jettaintelligence.com/history/jetta-intelligence-website/ | sed -n '1,20p'
dig +short status.jettaintelligence.com CNAME
```

Expected signal:

- The public `curl` should not return the GitHub Pages `200` body directly.
- The response should be a Cloudflare Access redirect/block such as a `302`
  with a `/cdn-cgi/access/` location, or a Cloudflare-managed `403`.
- Deep links under `/history/.../` should be gated the same way as `/`.

If the public URL still returns `HTTP/2 200` from `server: GitHub.com`, the
custom domain is not yet protected.

The repo verifier intentionally checks multiple layers:

- public HTTP gate behavior,
- macOS/Python system resolver output,
- default `dig` output,
- public resolver output from `1.1.1.1` and `8.8.8.8`,
- forced Cloudflare-edge behavior using the Cloudflare IPs returned by public
  resolvers.

## References

- Upptime configuration: `https://upptime.js.org/docs/configuration/`
- Cloudflare Access one-time PIN: `https://developers.cloudflare.com/cloudflare-one/identity/one-time-pin/`
- Cloudflare Access policies: `https://developers.cloudflare.com/cloudflare-one/policies/access/`
