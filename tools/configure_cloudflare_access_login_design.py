#!/usr/bin/env python3
"""Configure the shared Cloudflare Access login-page design.

This updates the Zero Trust organization `login_design`. It is intentionally
small and explicit because the login page is shared by every Access application
in the Cloudflare team, including `status.jettaintelligence.com` and
`login.jettaintelligence.com`.

By default this is a dry-run. Pass `--apply` to update Cloudflare.
"""

from __future__ import annotations

import argparse
import secrets
import threading
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from typing import Any


API_BASE = "https://api.cloudflare.com/client/v4"
DEFAULT_ACCOUNT_ID = "df0f4b1a42c8f4ca692c2b187b699bae"
DEFAULT_LOGO_URL = (
    "https://raw.githubusercontent.com/jetta-operating/"
    "status.jettaintelligence.com/master/assets/logo/jetta-status-logo.svg"
)
DEFAULT_HEADER = "Jetta Operating access"
DEFAULT_FOOTER = (
    "Use your approved company email to receive a one-time code. "
    "Protected by Cloudflare Access."
)
DEFAULT_BACKGROUND = "#1f1f1f"
DEFAULT_TEXT = "#ffffff"


class CloudflareError(RuntimeError):
    """Raised when Cloudflare returns an unsuccessful API envelope."""


class CloudflareClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"{API_BASE}{path}",
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
            except Exception as parse_error:  # pragma: no cover
                raise CloudflareError(f"{method} {path} failed: HTTP {exc.code}") from parse_error
            raise CloudflareError(format_cf_error(method, path, data)) from exc

        if not data.get("success", False):
            raise CloudflareError(format_cf_error(method, path, data))
        return data


def format_cf_error(method: str, path: str, data: dict[str, Any]) -> str:
    errors = data.get("errors") or []
    if not errors:
        return f"{method} {path} failed with no Cloudflare error details"
    return f"{method} {path} failed: " + " | ".join(
        f"{error.get('code', '?')}: {error.get('message', 'unknown error')}" for error in errors
    )


def get_token(args: argparse.Namespace) -> str:
    if args.use_clawdflare_vault:
        local_clawdflare = Path.home() / "repos-eidos-agi" / "clawdflare"
        if local_clawdflare.exists():
            sys.path.insert(0, str(local_clawdflare))
        if args.visible_pin_url:
            from clawdflare.lib import vault  # type: ignore

            pin = prompt_pin_visible(vault.get_active_account())
            try:
                return vault._decrypt_token(pin)  # type: ignore[attr-defined]
            finally:
                del pin
        from clawdflare.lib import vault  # type: ignore

        return vault.authorize_write()
    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(
            f"Missing token. Set {args.token_env}=<token>, or rerun with --use-clawdflare-vault."
        )
    return token


def prompt_pin_visible(account: str) -> str:
    """Collect a PIN from a localhost form and print the URL for manual opening."""
    nonce = secrets.token_urlsafe(32)
    result: dict[str, str] = {}
    html = f"""<!doctype html>
<meta charset="utf-8">
<title>clawdflare authorization</title>
<style>
body {{
  margin: 0;
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: #1f1f1f;
  color: #f6f4ef;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}
.card {{
  width: min(420px, calc(100vw - 40px));
  border: 1px solid #3b454a;
  background: #272727;
  padding: 28px;
  box-shadow: 0 24px 80px rgba(0,0,0,.35);
}}
h1 {{ font-size: 20px; margin: 0 0 8px; }}
p {{ color: #c9d3d7; line-height: 1.45; margin: 0 0 22px; }}
label {{ display:block; font-size: 13px; margin-bottom: 8px; color: #d9e1e4; }}
input {{
  width: 100%;
  box-sizing: border-box;
  padding: 12px;
  border: 1px solid #60727a;
  background: #111;
  color: #fff;
  font-size: 18px;
}}
button {{
  width: 100%;
  margin-top: 16px;
  padding: 12px;
  border: 0;
  background: #7892a0;
  color: #111;
  font-weight: 700;
  cursor: pointer;
}}
</style>
<main class="card">
  <h1>clawdflare authorization</h1>
  <p>Enter the PIN for account <strong>{account}</strong>. The PIN is posted only to localhost and is not printed.</p>
  <form method="post" action="/{nonce}">
    <label for="pin">PIN</label>
    <input id="pin" name="pin" type="password" autocomplete="off" autofocus required>
    <button type="submit">Authorize Cloudflare write</button>
  </form>
</main>"""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != f"/{nonce}":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())

        def do_POST(self) -> None:
            if self.path != f"/{nonce}":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            params = parse_qs(self.rfile.read(length).decode())
            pin = params.get("pin", [""])[0]
            if pin:
                result["pin"] = pin
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Authorized</h1><p>You can close this tab.</p>")
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/{nonce}"
    print(f"Open this one-time PIN URL: {url}", flush=True)
    thread.join(timeout=180)
    server.server_close()
    if "pin" not in result:
        raise RuntimeError("No PIN received — dialog timed out.")
    return result["pin"]


def desired_login_design(args: argparse.Namespace) -> dict[str, str]:
    return {
        "background_color": args.background_color,
        "footer_text": args.footer_text,
        "header_text": args.header_text,
        "logo_path": args.logo_url,
        "text_color": args.text_color,
    }


def summarize_design(design: dict[str, Any] | None) -> dict[str, Any]:
    design = design or {}
    return {
        "background_color": design.get("background_color"),
        "footer_text": design.get("footer_text"),
        "header_text": design.get("header_text"),
        "logo_path": design.get("logo_path"),
        "text_color": design.get("text_color"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the login-page design.")
    parser.add_argument("--token-env", default="CLOUDFLARE_API_TOKEN")
    parser.add_argument("--use-clawdflare-vault", action="store_true")
    parser.add_argument("--visible-pin-url", action="store_true")
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID)
    parser.add_argument("--logo-url", default=DEFAULT_LOGO_URL)
    parser.add_argument("--header-text", default=DEFAULT_HEADER)
    parser.add_argument("--footer-text", default=DEFAULT_FOOTER)
    parser.add_argument("--background-color", default=DEFAULT_BACKGROUND)
    parser.add_argument("--text-color", default=DEFAULT_TEXT)
    args = parser.parse_args()

    token = get_token(args)
    client = CloudflareClient(token)

    org_data = client.request("GET", f"/accounts/{args.account_id}/access/organizations")
    current = org_data.get("result") or {}
    desired = desired_login_design(args)

    output = {
        "mode": "apply" if args.apply else "dry_run",
        "organization": {
            "auth_domain": current.get("auth_domain"),
            "name": current.get("name"),
        },
        "before": summarize_design(current.get("login_design")),
        "desired": desired,
    }

    if not args.apply:
        print(json.dumps(output, indent=2))
        return 0

    payload = {**current, "login_design": desired}
    updated = client.request("PUT", f"/accounts/{args.account_id}/access/organizations", payload=payload)
    after = updated.get("result") or {}
    output["after"] = summarize_design(after.get("login_design"))
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
