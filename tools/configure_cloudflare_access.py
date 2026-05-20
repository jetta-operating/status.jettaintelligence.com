#!/usr/bin/env python3
"""Configure Cloudflare Access for the Jetta status site.

This script is intentionally small and direct. It uses the Cloudflare API to:

1. Find the `jettaintelligence.com` zone.
2. Ensure `status.jettaintelligence.com` is proxied through Cloudflare.
3. Create or update a reusable Cloudflare Access policy.
4. Create or update a self-hosted Access application for the status hostname.

It never prints the API token. By default it runs in dry-run mode; pass
`--apply` to make changes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


API_BASE = "https://api.cloudflare.com/client/v4"

DEFAULT_ZONE = "jettaintelligence.com"
DEFAULT_HOSTNAME = "status.jettaintelligence.com"
DEFAULT_ORIGIN = "jetta-operating.github.io"
DEFAULT_ACCOUNT_ID = "df0f4b1a42c8f4ca692c2b187b699bae"
DEFAULT_APP_NAME = "Jetta Service Status"
DEFAULT_POLICY_NAME = "Jetta status approved domains"
DEFAULT_SESSION_DURATION = "168h"
DEFAULT_ALLOWED_DOMAINS = ("jettaintelligence.com", "aicholdings.com", "greenmarkwaste.com")


class CloudflareError(RuntimeError):
    """Raised when the Cloudflare API returns an error envelope."""


@dataclass
class CloudflareClient:
    token: str

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{API_BASE}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                data = json.loads(exc.read().decode("utf-8"))
            except Exception as parse_error:  # pragma: no cover - defensive
                raise CloudflareError(f"{method} {path} failed: HTTP {exc.code}") from parse_error
            raise CloudflareError(_format_cf_error(method, path, data)) from exc

        if not data.get("success", False):
            raise CloudflareError(_format_cf_error(method, path, data))
        return data


def _format_cf_error(method: str, path: str, data: dict[str, Any]) -> str:
    errors = data.get("errors") or []
    if not errors:
        return f"{method} {path} failed with no Cloudflare error details"
    parts = []
    for error in errors:
        code = error.get("code", "?")
        message = error.get("message", "unknown error")
        chain = error.get("error_chain") or []
        if chain:
            message = f"{message}; " + "; ".join(c.get("message", "") for c in chain)
        parts.append(f"{code}: {message}")
    return f"{method} {path} failed: " + " | ".join(parts)


def get_token(args: argparse.Namespace) -> str:
    if args.use_clawdflare_vault:
        from clawdflare.lib import vault  # type: ignore

        return vault.authorize_write()

    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(
            f"Missing token. Set {args.token_env}=<token>, or rerun with "
            "--use-clawdflare-vault if the local clawdflare vault is configured."
        )
    return token


def find_zone(client: CloudflareClient, zone_name: str) -> dict[str, Any]:
    data = client.request("GET", "/zones", query={"name": zone_name, "per_page": 50})
    results = data.get("result") or []
    if not results:
        raise CloudflareError(f"Zone not found: {zone_name}")
    return results[0]


def ensure_dns_record(
    client: CloudflareClient,
    *,
    zone_id: str,
    hostname: str,
    origin: str,
    apply: bool,
) -> dict[str, Any]:
    data = client.request(
        "GET",
        f"/zones/{zone_id}/dns_records",
        query={"type": "CNAME", "name": hostname, "per_page": 50},
    )
    records = data.get("result") or []
    record = records[0] if records else None
    target = {
        "type": "CNAME",
        "name": hostname,
        "content": origin,
        "ttl": 1,
        "proxied": True,
        "comment": "Jetta status page origin; proxied for Cloudflare Access.",
    }

    if not record:
        if not apply:
            return {"action": "would_create_dns_record", "target": target}
        created = client.request("POST", f"/zones/{zone_id}/dns_records", payload=target)["result"]
        return {"action": "created_dns_record", "id": created["id"], "proxied": created.get("proxied")}

    needs_update = (
        record.get("content", "").rstrip(".") != origin.rstrip(".")
        or record.get("proxied") is not True
        or record.get("ttl") != 1
    )
    if not needs_update:
        return {
            "action": "dns_record_ok",
            "id": record["id"],
            "proxied": record.get("proxied"),
            "content": record.get("content"),
        }

    payload = {
        **target,
        "comment": record.get("comment") or target["comment"],
    }
    if not apply:
        return {
            "action": "would_update_dns_record",
            "id": record["id"],
            "from": {
                "content": record.get("content"),
                "proxied": record.get("proxied"),
                "ttl": record.get("ttl"),
            },
            "to": payload,
        }
    updated = client.request("PATCH", f"/zones/{zone_id}/dns_records/{record['id']}", payload=payload)["result"]
    return {"action": "updated_dns_record", "id": updated["id"], "proxied": updated.get("proxied")}


def ensure_policy(
    client: CloudflareClient,
    *,
    account_id: str,
    policy_name: str,
    domains: list[str],
    apply: bool,
) -> dict[str, Any]:
    include = [{"email_domain": {"domain": domain}} for domain in domains]
    payload = {
        "name": policy_name,
        "decision": "allow",
        "include": include,
        "exclude": [],
        "require": [],
        "precedence": 1,
    }

    data = client.request("GET", f"/accounts/{account_id}/access/policies", query={"per_page": 100})
    policies = data.get("result") or []
    existing = next((p for p in policies if p.get("name") == policy_name), None)

    if not existing:
        if not apply:
            return {"action": "would_create_access_policy", "target": payload}
        created = client.request("POST", f"/accounts/{account_id}/access/policies", payload=payload)["result"]
        return {"action": "created_access_policy", "id": created["id"], "name": created["name"]}

    # PUT is used because Cloudflare documents reusable policy update as a full update.
    if not apply:
        return {"action": "would_update_access_policy", "id": existing["id"], "target": payload}
    updated = client.request("PUT", f"/accounts/{account_id}/access/policies/{existing['id']}", payload=payload)["result"]
    return {"action": "updated_access_policy", "id": updated["id"], "name": updated["name"]}


def ensure_app(
    client: CloudflareClient,
    *,
    account_id: str,
    app_name: str,
    hostname: str,
    policy_id: str | None,
    session_duration: str,
    apply: bool,
) -> dict[str, Any]:
    payload = {
        "name": app_name,
        "domain": hostname,
        "type": "self_hosted",
        "session_duration": session_duration,
        "app_launcher_visible": False,
        "auto_redirect_to_identity": False,
        "allow_authenticate_via_warp": False,
        "allowed_idps": [],
    }
    if policy_id:
        payload["policies"] = [{"id": policy_id}]

    data = client.request("GET", f"/accounts/{account_id}/access/apps", query={"per_page": 100})
    apps = data.get("result") or []
    existing = next((a for a in apps if a.get("domain") == hostname or a.get("name") == app_name), None)

    if not existing:
        if not apply:
            return {"action": "would_create_access_app", "target": payload}
        created = client.request("POST", f"/accounts/{account_id}/access/apps", payload=payload)["result"]
        return {"action": "created_access_app", "id": created["id"], "domain": created["domain"]}

    if not apply:
        return {"action": "would_update_access_app", "id": existing["id"], "target": payload}
    updated = client.request("PUT", f"/accounts/{account_id}/access/apps/{existing['id']}", payload=payload)["result"]
    return {"action": "updated_access_app", "id": updated["id"], "domain": updated["domain"]}


def verify_public_gate(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {
                "url": url,
                "status": resp.status,
                "server": resp.headers.get("server"),
                "location": resp.headers.get("location"),
                "access_gate_detected": "cloudflare" in (resp.headers.get("server") or "").lower()
                and resp.status in (302, 403),
            }
    except urllib.error.HTTPError as exc:
        return {
            "url": url,
            "status": exc.code,
            "server": exc.headers.get("server"),
            "location": exc.headers.get("location"),
            "access_gate_detected": exc.code in (302, 403)
            and ("cloudflare" in (exc.headers.get("server") or "").lower()
                 or "/cdn-cgi/access/" in (exc.headers.get("location") or "")),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply changes. Omit for dry-run.")
    parser.add_argument("--verify-only", action="store_true", help="Only check the public gate.")
    parser.add_argument("--token-env", default="CLOUDFLARE_API_TOKEN")
    parser.add_argument("--use-clawdflare-vault", action="store_true")
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID)
    parser.add_argument("--zone", default=DEFAULT_ZONE)
    parser.add_argument("--hostname", default=DEFAULT_HOSTNAME)
    parser.add_argument("--origin", default=DEFAULT_ORIGIN)
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME)
    parser.add_argument("--policy-name", default=DEFAULT_POLICY_NAME)
    parser.add_argument("--session-duration", default=DEFAULT_SESSION_DURATION)
    parser.add_argument(
        "--allowed-domain",
        action="append",
        dest="allowed_domains",
        default=[],
        help="Allowed email domain. May be repeated. Defaults to Jetta/AIC/Greenmark domains.",
    )
    args = parser.parse_args()

    public_url = f"https://{args.hostname}/"
    if args.verify_only:
        print(json.dumps({"verify": verify_public_gate(public_url)}, indent=2))
        return 0

    domains = args.allowed_domains or list(DEFAULT_ALLOWED_DOMAINS)
    token = get_token(args)
    try:
        client = CloudflareClient(token=token)
        zone = find_zone(client, args.zone)
        policy_result = ensure_policy(
            client,
            account_id=args.account_id,
            policy_name=args.policy_name,
            domains=domains,
            apply=args.apply,
        )
        policy_id = policy_result.get("id")
        dns_result = ensure_dns_record(
            client,
            zone_id=zone["id"],
            hostname=args.hostname,
            origin=args.origin,
            apply=args.apply,
        )
        app_result = ensure_app(
            client,
            account_id=args.account_id,
            app_name=args.app_name,
            hostname=args.hostname,
            policy_id=policy_id,
            session_duration=args.session_duration,
            apply=args.apply,
        )
        output = {
            "mode": "apply" if args.apply else "dry_run",
            "zone": {"id": zone["id"], "name": zone["name"], "status": zone.get("status")},
            "access_policy": policy_result,
            "dns": dns_result,
            "access_app": app_result,
            "public_gate_after": verify_public_gate(public_url) if args.apply else "not_checked_in_dry_run",
        }
        print(json.dumps(output, indent=2))
    except CloudflareError as exc:
        print(f"Cloudflare setup failed: {exc}", file=sys.stderr)
        return 2
    finally:
        del token
    return 0


if __name__ == "__main__":
    sys.exit(main())
