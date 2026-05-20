#!/usr/bin/env python3
from pathlib import Path
import shutil
import re
import json


EXPORT_DIR = Path("site/status-page/__sapper__/export")
THEME_SOURCE = Path("assets/jetta-status-theme.css")
THEME_TARGET = EXPORT_DIR / "jetta-status-theme.css"
GLOBAL_CSS = EXPORT_DIR / "global.css"
SERVICE_WORKER = EXPORT_DIR / "service-worker.js"
INDEX_HTML = EXPORT_DIR / "index.html"
SOURCE_SUMMARY = Path("history/summary.json")
MARKER = "/* Jetta status theme */"
END_MARKER = "/* End Jetta status theme */"
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
    if not INDEX_HTML.exists():
        raise SystemExit(f"missing generated index.html: {INDEX_HTML}")

    theme = THEME_SOURCE.read_text()
    shutil.copyfile(THEME_SOURCE, THEME_TARGET)

    global_css = GLOBAL_CSS.read_text()
    theme_block = f"{MARKER}\n{theme}\n{END_MARKER}"
    if MARKER in global_css and END_MARKER in global_css:
        global_css = re.sub(
            rf"{re.escape(MARKER)}.*?{re.escape(END_MARKER)}",
            theme_block,
            global_css,
            flags=re.S,
        )
    elif MARKER in global_css:
        global_css = re.sub(
            rf"{re.escape(MARKER)}.*",
            theme_block,
            global_css,
            flags=re.S,
        )
    else:
        global_css = f"{global_css.rstrip()}\n\n{theme_block}\n"
    GLOBAL_CSS.write_text(global_css)

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
        inline_theme = f"<style id=\"jetta-critical-theme\">{theme}</style>"
        if "id=\"jetta-critical-theme\"" in html:
            html = re.sub(
                r"<style id=\"jetta-critical-theme\">.*?</style>",
                inline_theme,
                html,
                count=1,
                flags=re.S,
            )
        else:
            html = re.sub(r"</head>", f"{inline_theme}</head>", html, count=1)
        html_path.write_text(html)

    # Upptime exports a client-routed Sapper app, but GitHub Pages returns
    # a hard 404 for direct deep links unless concrete files exist. Create
    # lightweight route shells for each status detail page so copied links and
    # normal anchor navigation are durable on GitHub Pages.
    index_html = INDEX_HTML.read_text()
    if SOURCE_SUMMARY.exists():
        summary = json.loads(SOURCE_SUMMARY.read_text())
        for service in summary:
            slug = service.get("slug")
            if not slug:
                continue
            route_dir = EXPORT_DIR / "history" / slug
            route_dir.mkdir(parents=True, exist_ok=True)
            (route_dir / "index.html").write_text(index_html)

    # Keep the SPA shell available for unknown routes too. GitHub Pages will
    # still return a 404 status, but the app can render instead of showing the
    # stock GitHub error page.
    (EXPORT_DIR / "404.html").write_text(index_html)


if __name__ == "__main__":
    main()
