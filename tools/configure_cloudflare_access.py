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
import socket
import subprocess
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
DEFAULT_PUBLIC_RESOLVERS = ("1.1.1.1", "8.8.8.8")


class CloudflareError(RuntimeError):
    """Raised when the Cloudflare API returns an error envelope."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


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


def _access_gate_detected(status: int, server: str | None, location: str | None, auth_header: str | None) -> bool:
    server_value = (server or "").lower()
    location_value = location or ""
    auth_value = (auth_header or "").lower()
    return (
        status in (302, 403)
        and (
            "cloudflare" in server_value
            or "/cdn-cgi/access/" in location_value
            or "cloudflare-access" in auth_value
        )
    )


def verify_public_gate(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, method="HEAD")
    opener = urllib.request.build_opener(NoRedirectHandler)
    try:
        with opener.open(req, timeout=15) as resp:
            server = resp.headers.get("server")
            location = resp.headers.get("location")
            auth_header = resp.headers.get("www-authenticate")
            return {
                "url": url,
                "status": resp.status,
                "server": server,
                "location": location,
                "www_authenticate": auth_header,
                "access_gate_detected": _access_gate_detected(resp.status, server, location, auth_header),
            }
    except urllib.error.HTTPError as exc:
        server = exc.headers.get("server")
        location = exc.headers.get("location")
        auth_header = exc.headers.get("www-authenticate")
        return {
            "url": url,
            "status": exc.code,
            "server": server,
            "location": location,
            "www_authenticate": auth_header,
            "access_gate_detected": _access_gate_detected(exc.code, server, location, auth_header),
        }


def resolve_with_system(hostname: str) -> dict[str, Any]:
    try:
        values = sorted({item[4][0] for item in socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)})
        return {"resolver": "system", "values": values, "ok": True}
    except socket.gaierror as exc:
        return {"resolver": "system", "values": [], "ok": False, "error": str(exc)}


def dig_short(hostname: str, resolver: str | None = None) -> dict[str, Any]:
    command = ["dig"]
    if resolver:
        command.append(f"@{resolver}")
    command.extend(["+short", hostname])
    try:
        proc = subprocess.run(command, check=False, text=True, capture_output=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"resolver": resolver or "default", "values": [], "ok": False, "error": str(exc)}
    values = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return {
        "resolver": resolver or "default",
        "values": values,
        "ok": proc.returncode == 0,
        "stderr": proc.stderr.strip() or None,
    }


def looks_like_cloudflare_dns(values: list[str]) -> bool:
    joined = " ".join(values).lower()
    if "github.io" in joined or "185.199." in joined:
        return False
    return any(value.startswith(("104.", "172.", "188.", "190.", "198.", "162.", "2606:4700:")) for value in values)


def verify_dns(hostname: str) -> dict[str, Any]:
    default_dig = dig_short(hostname)
    public = [dig_short(hostname, resolver) for resolver in DEFAULT_PUBLIC_RESOLVERS]
    system = resolve_with_system(hostname)
    all_views = [default_dig, *public, system]
    return {
        "hostname": hostname,
        "system": system,
        "default_dig": default_dig,
        "public_resolvers": public,
        "all_views_look_proxied": all(looks_like_cloudflare_dns(view.get("values", [])) for view in all_views),
        "any_view_still_github": any(
            "github.io" in " ".join(view.get("values", [])).lower()
            or "185.199." in " ".join(view.get("values", []))
            for view in all_views
        ),
    }


def verify_edge_gate_with_public_ips(hostname: str) -> list[dict[str, Any]]:
    ips: list[str] = []
    for view in [dig_short(hostname, resolver) for resolver in DEFAULT_PUBLIC_RESOLVERS]:
        for value in view.get("values", []):
            if value and value[0].isdigit() and value not in ips:
                ips.append(value)

    results = []
    for ip in ips[:4]:
        command = [
            "curl",
            "-sSI",
            "--max-time",
            "15",
            "--resolve",
            f"{hostname}:443:{ip}",
            f"https://{hostname}/",
        ]
        try:
            proc = subprocess.run(command, check=False, text=True, capture_output=True, timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            results.append({"ip": ip, "ok": False, "error": str(exc)})
            continue
        headers = proc.stdout
        first_line = headers.splitlines()[0] if headers.splitlines() else ""
        results.append(
            {
                "ip": ip,
                "ok": proc.returncode == 0,
                "first_line": first_line,
                "access_gate_detected": "/cdn-cgi/access/" in headers
                or "Cloudflare-Access" in headers
                or ("cloudflare" in headers.lower() and (" 302" in first_line or " 403" in first_line)),
            }
        )
    return results


def verify_all(hostname: str) -> dict[str, Any]:
    public_url = f"https://{hostname}/"
    public_gate = verify_public_gate(public_url)
    dns = verify_dns(hostname)
    edge_gate = verify_edge_gate_with_public_ips(hostname)
    return {
        "public_gate": public_gate,
        "dns": dns,
        "forced_cloudflare_edge_gate": edge_gate,
        "effective_access_gate": public_gate["access_gate_detected"] and dns["all_views_look_proxied"],
        "diagnosis": diagnose_verification(public_gate, dns, edge_gate),
    }


def diagnose_verification(public_gate: dict[str, Any], dns: dict[str, Any], edge_gate: list[dict[str, Any]]) -> str:
    if public_gate["access_gate_detected"] and dns["all_views_look_proxied"]:
        return "protected: default traffic resolves through Cloudflare and Access gates the hostname"
    if dns["any_view_still_github"] and any(item.get("access_gate_detected") for item in edge_gate):
        return "partial: Cloudflare Access works at the edge, but at least one resolver still bypasses to GitHub Pages"
    if any(item.get("access_gate_detected") for item in edge_gate):
        return "partial: Cloudflare Access works when forced to edge, but default public request is not gated"
    if public_gate.get("server") == "GitHub.com":
        return "unprotected: default request is still served directly by GitHub Pages"
    return "unverified: Access gate was not detected"


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2))


def is_effectively_gated(data: dict[str, Any]) -> bool:
    return bool(data.get("effective_access_gate"))


def strict_exit(data: dict[str, Any]) -> int:
    return 0 if is_effectively_gated(data) else 1


def verify_only(args: argparse.Namespace) -> int:
    data = {"verify": verify_all(args.hostname)}
    print_json(data)
    return strict_exit(data["verify"]) if args.strict else 0


def applied_result_exit(data: dict[str, Any], strict: bool) -> int:
    if not strict:
        return 0
    return strict_exit(data.get("public_gate_after", {}))


def cloudflare_result(
    *,
    args: argparse.Namespace,
    client: CloudflareClient,
    token: str,
) -> dict[str, Any]:
    del token
    zone = find_zone(client, args.zone)
    policy_result = ensure_policy(
        client,
        account_id=args.account_id,
        policy_name=args.policy_name,
        domains=args.allowed_domains or list(DEFAULT_ALLOWED_DOMAINS),
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
    return {
        "mode": "apply" if args.apply else "dry_run",
        "zone": {"id": zone["id"], "name": zone["name"], "status": zone.get("status")},
        "access_policy": policy_result,
        "dns": dns_result,
        "access_app": app_result,
        "public_gate_after": verify_all(args.hostname) if args.apply else "not_checked_in_dry_run",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply changes. Omit for dry-run.")
    parser.add_argument("--verify-only", action="store_true", help="Only check DNS and the public gate.")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero unless the hostname is effectively gated.")
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

    if args.verify_only:
        return verify_only(args)

    token = get_token(args)
    try:
        client = CloudflareClient(token=token)
        output = cloudflare_result(args=args, client=client, token=token)
        print_json(output)
        return applied_result_exit(output, args.strict)
    except CloudflareError as exc:
        print(f"Cloudflare setup failed: {exc}", file=sys.stderr)
        return 2
    finally:
        del token
    return 0


if __name__ == "__main__":
    sys.exit(main())
