from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

URLS_FILE = Path("urls.txt")
STATE_FILE = Path("state.json")
CHANGES_FILE = Path("changes.md")

# Sicherheits-/Lastbegrenzung pro Gemeinde.
# Bei Bedarf später erhöhen.
MAX_PAGES_PER_SITE = 150

TIMEOUT = 15
PAUSE_BETWEEN_REQUESTS = 0.15

USER_AGENT = (
    "Mozilla/5.0 (compatible; GemeindeChangeMonitor/1.0; "
    "+https://github.com/)"
)

IGNORE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".rar", ".7z", ".mp3", ".mp4", ".avi", ".mov",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
}

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def canonicalize(url: str) -> str:
    """Entfernt Fragment (#...) und normalisiert leere Pfade."""
    p = urlparse(url)
    path = p.path or "/"
    return urlunparse((p.scheme, p.netloc.lower(), path, p.params, p.query, ""))


def same_site(url: str, root_url: str) -> bool:
    """Erlaubt dieselbe Domain sowie www-/non-www-Varianten."""
    a = urlparse(url).netloc.lower().split(":")[0]
    b = urlparse(root_url).netloc.lower().split(":")[0]
    a = a[4:] if a.startswith("www.") else a
    b = b[4:] if b.startswith("www.") else b
    return a == b


def should_visit(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in {"http", "https"}:
        return False

    path_lower = p.path.lower()
    for ext in IGNORE_EXTENSIONS:
        if path_lower.endswith(ext):
            return False

    # PDF-Dateien selbst werden nicht heruntergeladen.
    # Neue/geänderte PDF-Links werden aber über den Seiteninhalt erkannt.
    if path_lower.endswith(".pdf"):
        return False

    return True


def normalize_page(html: str, base_url: str) -> str:
    """
    Reduziert HTML auf sichtbaren Text + relevante Links.
    Dadurch werden viele rein technische HTML-Unterschiede ignoriert,
    aber inhaltliche Änderungen und neue Links erkannt.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    text = " ".join(soup.stripped_strings)
    text = re.sub(r"\s+", " ", text).strip()

    links = []
    for a in soup.find_all("a", href=True):
        href = canonicalize(urljoin(base_url, a["href"]))
        label = " ".join(a.stripped_strings)
        if href.startswith(("http://", "https://")):
            links.append(f"{label} -> {href}")

    links = sorted(set(links))
    return text + "\n\nLINKS\n" + "\n".join(links)


def page_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def fetch(url: str):
    try:
        r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
            return None, None, None
        final_url = canonicalize(r.url)
        return r.text, final_url, r.status_code
    except requests.RequestException as exc:
        print(f"FEHLER {url}: {exc}")
        return None, None, None


def crawl(root_url: str) -> dict[str, str]:
    root_url = canonicalize(root_url.strip())
    queue = deque([root_url])
    visited = set()
    hashes = {}

    while queue and len(visited) < MAX_PAGES_PER_SITE:
        url = canonicalize(queue.popleft())

        if url in visited or not same_site(url, root_url) or not should_visit(url):
            continue

        visited.add(url)
        html, final_url, _ = fetch(url)
        time.sleep(PAUSE_BETWEEN_REQUESTS)

        if html is None or final_url is None:
            continue

        normalized = normalize_page(html, final_url)
        hashes[final_url] = page_hash(normalized)

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            child = canonicalize(urljoin(final_url, a["href"]))
            if same_site(child, root_url) and should_visit(child) and child not in visited:
                queue.append(child)

    print(f"{root_url}: {len(hashes)} Seiten erfasst")
    return hashes


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    roots = [
        line.strip()
        for line in URLS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    old_state = load_state()
    new_state = {}
    report = []

    first_run = not bool(old_state)

    for root in roots:
        print(f"\n=== Prüfe {root} ===")
        current = crawl(root)
        new_state[root] = current

        if first_run:
            continue

        previous = old_state.get(root, {})

        old_urls = set(previous)
        new_urls = set(current)

        added = sorted(new_urls - old_urls)
        removed = sorted(old_urls - new_urls)
        changed = sorted(
            url for url in (old_urls & new_urls)
            if previous.get(url) != current.get(url)
        )

        if added or removed or changed:
            report.append(f"## {root}")

            if changed:
                report.append("\n### Geänderte Seiten")
                report.extend(f"- {u}" for u in changed)

            if added:
                report.append("\n### Neue Seiten")
                report.extend(f"- {u}" for u in added)

            if removed:
                report.append("\n### Nicht mehr gefundene Seiten")
                report.extend(f"- {u}" for u in removed)

            report.append("")

    STATE_FILE.write_text(
        json.dumps(new_state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    if first_run:
        CHANGES_FILE.write_text(
            "# Gemeinde-Monitor\n\nErster Lauf: Ausgangsstand gespeichert. Noch keine Meldung.\n",
            encoding="utf-8",
        )
        print("\nErster Lauf abgeschlossen. Ausgangsstand wurde gespeichert.")
        return 0

    if report:
        CHANGES_FILE.write_text(
            "# Änderungen auf Gemeinde-Websites\n\n" + "\n".join(report),
            encoding="utf-8",
        )
        print("\nÄnderungen gefunden.")
        return 2

    CHANGES_FILE.write_text(
        "# Gemeinde-Monitor\n\nKeine Änderungen gefunden.\n",
        encoding="utf-8",
    )
    print("\nKeine Änderungen gefunden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
