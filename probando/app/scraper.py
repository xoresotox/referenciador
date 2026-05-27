"""Scraper de metadatos para repositorios institucionales (principalmente DSpace).

Estrategia en cascada:
  1. Intento directo con `requests` (rápido) usando un User-Agent realista.
  2. Si la respuesta es un reto JS (Cloudflare Turnstile, Anubis PoW, etc.)
     o el código HTTP indica bloqueo, se reintenta con `cloudscraper`.
  3. Si aun así no hay metadatos, se lanza un navegador real con Playwright
     (Chromium headless) -- el "Web Agent" que el usuario solicita -- para
     resolver retos JavaScript automáticamente.

Los repositorios DSpace exponen los metadatos en etiquetas <meta name="..."
content="..."> con prefijos como `citation_`, `DC.` y `dcterms.`. Esto es
estándar Highwire / Dublin Core y lo siguen UCSM, UNSA, UCSP, UTP, UNMSM,
UNI y la mayoría de repositorios peruanos.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FIREFOX_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) "
    "Gecko/20100101 Firefox/120.0"
)
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": FIREFOX_UA,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

INSTITUTION_BY_HOST = {
    "repositorio.ucsm.edu.pe": "Universidad Católica de Santa María",
    "repositorio.unsa.edu.pe": "Universidad Nacional de San Agustín de Arequipa",
    "repositorio.ucsp.edu.pe": "Universidad Católica San Pablo",
    "repositorio.utp.edu.pe": "Universidad Tecnológica del Perú",
    "cybertesis.unmsm.edu.pe": "Universidad Nacional Mayor de San Marcos",
    "repositorio.unmsm.edu.pe": "Universidad Nacional Mayor de San Marcos",
    "repositorio.pucp.edu.pe": "Pontificia Universidad Católica del Perú",
    "tesis.pucp.edu.pe": "Pontificia Universidad Católica del Perú",
    "repositorio.uni.edu.pe": "Universidad Nacional de Ingeniería",
    "repositorio.unfv.edu.pe": "Universidad Nacional Federico Villarreal",
    "repositorio.unprg.edu.pe": "Universidad Nacional Pedro Ruiz Gallo",
    "repositorio.upao.edu.pe": "Universidad Privada Antenor Orrego",
    "repositorio.usil.edu.pe": "Universidad San Ignacio de Loyola",
    "repositorio.upn.edu.pe": "Universidad Privada del Norte",
    "repositorio.urp.edu.pe": "Universidad Ricardo Palma",
    "repositorio.continental.edu.pe": "Universidad Continental",
    "repositorio.unp.edu.pe": "Universidad Nacional de Piura",
}


@dataclass
class Metadata:
    """Metadatos normalizados extraídos del repositorio."""

    url: str
    title: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    year: Optional[str] = None
    date_full: Optional[str] = None
    publisher: Optional[str] = None
    institution: Optional[str] = None
    type: Optional[str] = None
    language: Optional[str] = None
    abstract: Optional[str] = None
    handle: Optional[str] = None
    doi: Optional[str] = None
    advisor: Optional[str] = None
    degree: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    raw_meta: dict[str, list[str]] = field(default_factory=dict)

    def is_usable(self) -> bool:
        return bool(self.title) and bool(self.authors)


class ScrapeError(Exception):
    """No se pudieron extraer metadatos de la URL."""


def fetch_html(url: str, *, prefer_browser: bool = False) -> str:
    """Descarga el HTML de la URL aplicando la cascada de estrategias."""
    if not prefer_browser:
        # 1) requests directo
        try:
            html = _fetch_requests(url)
            if not _is_challenge(html):
                return html
            logger.info("Reto JS detectado en %s; probando cloudscraper", url)
        except requests.RequestException as exc:
            logger.info("requests falló para %s (%s); probando cloudscraper", url, exc)

        # 2) cloudscraper
        try:
            html = _fetch_cloudscraper(url)
            if not _is_challenge(html):
                return html
            logger.info("cloudscraper también atascado; usando Playwright")
        except Exception as exc:
            logger.info("cloudscraper falló (%s); usando Playwright", exc)

    # 3) Playwright (Web Agent)
    return _fetch_playwright(url)


def _fetch_requests(url: str, timeout: int = 25) -> str:
    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _fetch_cloudscraper(url: str, timeout: int = 30) -> str:
    import cloudscraper

    scraper = cloudscraper.create_scraper(
        browser={"browser": "firefox", "platform": "windows", "mobile": False}
    )
    resp = scraper.get(url, timeout=timeout, headers=DEFAULT_HEADERS)
    return resp.text


_CHALLENGE_SIGNATURES = (
    "Just a moment",
    "Un momento",
    "challenge-platform",
    "cf-challenge",
    "Anubis",
    "Making sure you",
    "Enable JavaScript and cookies",
    "anubis_challenge",
)

_CHALLENGE_TITLE_SIGNATURES = (
    "just a moment",
    "un momento",
    "making sure you",
    "attention required",
    "access denied",
    "cloudflare",
    "checking your browser",
    "403 forbidden",
    "anubis",
)


def _is_challenge(html: str) -> bool:
    """Heurística para detectar si la respuesta es una página de reto antibot."""
    if not html:
        return True
    head = html[:8000]
    return any(sig in head for sig in _CHALLENGE_SIGNATURES) and "citation_title" not in head


def _looks_like_challenge_title(title: Optional[str]) -> bool:
    if not title:
        return False
    t = title.strip().lower()
    return any(sig in t for sig in _CHALLENGE_TITLE_SIGNATURES)


def _fetch_playwright(url: str, *, max_wait_s: int = 50) -> str:
    """Renderiza la página con un navegador real (Playwright Chromium)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        ctx = browser.new_context(
            user_agent=CHROME_UA,
            locale="es-ES",
            viewport={"width": 1366, "height": 800},
            extra_http_headers={
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            },
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "Object.defineProperty(navigator, 'languages', {get: () => ['es-ES','es','en']});"
            "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});"
            "window.chrome = { runtime: {} };"
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            deadline = time.time() + max_wait_s
            while time.time() < deadline:
                title = (page.title() or "").lower()
                if not any(s.lower() in title for s in ("just a moment", "un momento", "making sure")):
                    # ¿Hay etiquetas de metadatos?
                    has_meta = page.evaluate(
                        "() => !!document.querySelector('meta[name^=\"citation_\"], "
                        "meta[name^=\"DC.\"], meta[name^=\"dc.\"], meta[name^=\"dcterms.\"]')"
                    )
                    if has_meta:
                        break
                time.sleep(1.5)
            return page.content()
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Parsing de metadatos
# ---------------------------------------------------------------------------


def _meta_all(soup: BeautifulSoup, *names: str) -> list[str]:
    """Devuelve todos los `content` para los nombres dados (sin importar caja)."""
    wanted = {n.lower() for n in names}
    out: list[str] = []
    for m in soup.find_all("meta"):
        key = (m.get("name") or m.get("property") or "").strip().lower()
        if key in wanted:
            content = (m.get("content") or "").strip()
            if content:
                out.append(content)
    return out


def _meta_first(soup: BeautifulSoup, *names: str) -> Optional[str]:
    values = _meta_all(soup, *names)
    return values[0] if values else None


_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_HANDLE_RE = re.compile(r"handle/(\d+/\d+|\d+\.\d+/\d+|[\w.]+/\d+)", re.IGNORECASE)


def parse_metadata(html: str, url: str) -> Metadata:
    soup = BeautifulSoup(html, "lxml")
    md = Metadata(url=url)

    # Recolecta todos los meta-tags para depuración
    raw: dict[str, list[str]] = {}
    for m in soup.find_all("meta"):
        key = (m.get("name") or m.get("property") or "").strip()
        if not key:
            continue
        content = (m.get("content") or "").strip()
        if not content:
            continue
        raw.setdefault(key, []).append(content)
    md.raw_meta = raw

    # Título
    md.title = (
        _meta_first(soup, "citation_title", "DC.title", "dc.title", "dcterms.title")
        or (soup.title.get_text(strip=True) if soup.title else None)
    )

    # Autores (puede haber múltiples meta tags)
    authors = (
        _meta_all(soup, "citation_author")
        or _meta_all(soup, "DC.creator", "dc.creator")
        or _meta_all(soup, "DC.contributor", "dc.contributor", "dcterms.creator")
    )
    md.authors = [a.strip() for a in authors if a and a.strip()]

    # Fecha (citation_date, citation_publication_date, DC.date.issued, DC.date)
    date_str = _meta_first(
        soup,
        "citation_publication_date",
        "citation_date",
        "DC.date.issued",
        "dc.date.issued",
        "DC.date",
        "dc.date",
        "dcterms.issued",
    )
    md.date_full = date_str
    if date_str:
        m = _YEAR_RE.search(date_str)
        if m:
            md.year = m.group(0)

    # Editor / institución
    md.publisher = _meta_first(soup, "citation_publisher", "DC.publisher", "dc.publisher")
    host = urlparse(url).netloc.lower().lstrip("www.")
    md.institution = INSTITUTION_BY_HOST.get(host) or md.publisher

    # Tipo, idioma, resumen, asesor, grado
    md.type = _meta_first(soup, "DC.type", "dc.type", "citation_dissertation_name")
    md.language = _meta_first(soup, "citation_language", "DC.language", "dc.language")
    md.abstract = _meta_first(
        soup, "DC.description.abstract", "dc.description.abstract", "DC.description", "dc.description"
    )
    md.advisor = _meta_first(
        soup, "DC.contributor.advisor", "dc.contributor.advisor", "thesis.degree.grantor"
    )
    md.degree = _meta_first(
        soup, "DC.thesis.degree.name", "dc.thesis.degree.name", "thesis.degree.name"
    )
    md.doi = _meta_first(soup, "citation_doi", "DC.identifier.doi", "dc.identifier.doi")
    md.keywords = _meta_all(soup, "DC.subject", "dc.subject", "citation_keywords")

    # Handle (DSpace)
    for candidate in (
        _meta_first(soup, "DC.identifier.uri", "dc.identifier.uri", "citation_public_url"),
        url,
    ):
        if not candidate:
            continue
        m = _HANDLE_RE.search(candidate)
        if m:
            md.handle = m.group(1)
            break

    return md


def _has_real_metadata(md: Metadata) -> bool:
    """True solo si hay metadatos DSpace genuinos (no solo un <title> fallback)."""
    if not md.title:
        return False
    if _looks_like_challenge_title(md.title):
        return False
    # ¿Encontramos al menos una etiqueta citation_*/DC.*/dcterms.*?
    for key in md.raw_meta:
        k = key.lower()
        if k.startswith(("citation_", "dc.", "dcterms.")):
            return True
    # Sin meta-tags estándar pero con título y autores: aceptable.
    return bool(md.authors)


def scrape(url: str) -> Metadata:
    """Pipeline público: descarga y parsea metadatos desde la URL."""
    if not url or not url.lower().startswith(("http://", "https://")):
        raise ScrapeError("La URL debe comenzar con http:// o https://")

    html = fetch_html(url)
    md = parse_metadata(html, url)

    if not _has_real_metadata(md):
        # Reintenta forzando navegador real (Web Agent)
        logger.info("Sin metadatos DSpace tras 1ª pasada; forzando Playwright para %s", url)
        html = fetch_html(url, prefer_browser=True)
        md = parse_metadata(html, url)

    if not _has_real_metadata(md):
        if _looks_like_challenge_title(md.title):
            raise ScrapeError(
                "El repositorio respondió con una página de protección antibot "
                "(Cloudflare / Anubis) que no se pudo resolver desde esta red. "
                "Intenta abrirlo desde una red residencial o vuelve a intentarlo más tarde."
            )
        raise ScrapeError(
            "No se encontraron metadatos. Es posible que el repositorio bloquee "
            "el acceso automatizado desde esta red, o que la URL no corresponda a "
            "una página de ítem DSpace."
        )
    return md
