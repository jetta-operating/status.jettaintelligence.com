#!/usr/bin/env python3
from pathlib import Path
import shutil
import re


EXPORT_DIR = Path("site/status-page/__sapper__/export")
THEME_SOURCE = Path("assets/jetta-status-theme.css")
THEME_TARGET = EXPORT_DIR / "jetta-status-theme.css"
GLOBAL_CSS = EXPORT_DIR / "global.css"
SERVICE_WORKER = EXPORT_DIR / "service-worker.js"
MARKER = "/* Jetta status theme */"
SERVICE_WORKER_RESET = """
self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((key) => caches.delete(key))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", () => {});
""".strip()


def main() -> None:
    if not EXPORT_DIR.exists():
        raise SystemExit(f"missing generated site export: {EXPORT_DIR}")
    if not THEME_SOURCE.exists():
        raise SystemExit(f"missing theme source: {THEME_SOURCE}")
    if not GLOBAL_CSS.exists():
        raise SystemExit(f"missing generated global.css: {GLOBAL_CSS}")

    theme = THEME_SOURCE.read_text()
    shutil.copyfile(THEME_SOURCE, THEME_TARGET)

    global_css = GLOBAL_CSS.read_text()
    if MARKER not in global_css:
        GLOBAL_CSS.write_text(f"{global_css.rstrip()}\n\n{MARKER}\n{theme}\n")

    SERVICE_WORKER.write_text(f"{SERVICE_WORKER_RESET}\n")

    for html_path in EXPORT_DIR.rglob("*.html"):
        html = html_path.read_text()
        html = html.replace(
            "if('serviceWorker' in navigator)navigator.serviceWorker.register('/service-worker.js');",
            "",
        )
        html = html.replace(
            "href=https://status.jettaintelligence.com/themes/",
            "href=/themes/",
        )
        html = html.replace(
            "href=https://status.jettaintelligence.com/global.css",
            "href=/global.css",
        )
        html = html.replace(
            "href=https://status.jettaintelligence.com/jetta-status-theme.css",
            "href=/jetta-status-theme.css",
        )
        html = html.replace(
            "href=https://status.jettaintelligence.com",
            "href=/",
        )
        if "id=\"jetta-critical-theme\"" not in html:
            inline_theme = f"<style id=\"jetta-critical-theme\">{theme}</style>"
            html = re.sub(r"</head>", f"{inline_theme}</head>", html, count=1)
        html_path.write_text(html)


if __name__ == "__main__":
    main()
