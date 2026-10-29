"""Navegación web del bot: búsqueda en internet y lectura de páginas.

El dueño pide «busca en internet el precio del cobre» o «navega a
[URL]» y el bot trae la información al chat.

Seguridad:
- El contenido descargado se trata como DATO, nunca como instrucciones
  (anti prompt-injection). Se sanea y trunca antes de devolverlo.
- Anti-SSRF: solo se leen páginas públicas. Se rechazan IPs locales,
  privadas o de metadatos de nube (127.0.0.1, 10.x, 192.168.x,
  169.254.169.254...), puertos distintos de 80/443 y URLs con
  credenciales. Cada redirección se valida de nuevo y la descarga tiene
  tope de tamaño y de tipo de contenido.

Sin API keys: usa DuckDuckGo HTML (público) para buscar y httpx para
leer páginas. Si la red falla, el handler responde con un mensaje
amable — nunca revienta.
"""

import asyncio
import ipaddress
import logging
import re
import socket
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import httpx

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}
_TIMEOUT = httpx.Timeout(15.0)
_MAX_PAGE_CHARS = 3500

# Límites anti-SSRF / anti-abuso al leer páginas
_ALLOWED_PORTS = {80, 443}
_ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
_MAX_DOWNLOAD_BYTES = 1_000_000
_MAX_REDIRECTS = 3


def _strip_tags(html: str) -> str:
    """HTML → texto visible (sin scripts/estilos)."""
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html,
                  flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", html,
                  flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    # Colapsar espacios y saltos excesivos
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_url(href: str) -> str:
    """Los resultados de DDG vienen como redirect: decodifica el uddg."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return href


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Busca en DuckDuckGo y retorna [{title, url, snippet}].

    Sin dependencias externas: parsea el HTML lite de DDG.
    Falla con excepción normal (el handler la captura).
    """
    url = "https://html.duckduckgo.com/html/"
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS,
                                 follow_redirects=True) as client:
        r = await client.post(url, data={"q": query})
        r.raise_for_status()

    html = r.text
    results: list[dict] = []
    # Bloques de resultado: <a class="result__a" href="...">Title</a>
    # seguido (opcionalmente) de <a class="result__snippet" ...>Snip</a>
    pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        r'(?:.*?class="result__snippet"[^>]*>(.*?)</a>)?',
        re.DOTALL,
    )
    for match in pattern.finditer(html):
        raw_url, title_html, snip_html = match.groups()
        title = _strip_tags(title_html or "")[:120]
        clean = _clean_url(raw_url)
        snippet = _strip_tags(snip_html or "")[:280]
        if not title or not clean.startswith("http"):
            continue
        results.append(
            {"title": title, "url": clean, "snippet": snippet}
        )
        if len(results) >= max_results:
            break

    if not results:
        logger.debug("Sin resultados de DDG para: %s", query[:50])
    return results


# ── Anti-SSRF ───────────────────────────────────────────────────────────────


def _is_public_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """True solo para direcciones enrutables en internet público."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def _resolve_ips(
    host: str, port: int
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resuelve el dominio a todas sus IPs (separado para poder probarlo)."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise ValueError("No se pudo resolver el dominio") from exc
    return [ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos]


async def assert_public_url(url: str) -> None:
    """Lanza ValueError si la URL no apunta a un sitio público seguro."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Solo se pueden abrir páginas http/https")
    host = parsed.hostname
    if not host:
        raise ValueError("La URL no tiene dominio")
    if parsed.username or parsed.password:
        raise ValueError("No se permiten URLs con credenciales")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in _ALLOWED_PORTS:
        raise ValueError("Puerto no permitido")

    ips = await _resolve_ips(host, port)
    if not ips:
        raise ValueError("No se pudo resolver el dominio")
    if not all(_is_public_ip(ip) for ip in ips):
        raise ValueError("Dirección no permitida")


async def fetch_page_text(url: str) -> str:
    """Descarga una página pública y extrae su texto visible (truncado).

    Solo http/https hacia sitios públicos (ver assert_public_url). Las
    redirecciones se siguen a mano, validando cada destino. El contenido
    es DATO: nunca instrucciones.
    """
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=False
    ) as client:
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            await assert_public_url(current)
            async with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise ValueError("Redirección sin destino")
                    current = str(httpx.URL(current).join(location))
                    continue

                resp.raise_for_status()
                ctype = (
                    resp.headers.get("content-type", "")
                    .split(";")[0]
                    .strip()
                    .lower()
                )
                if ctype not in _ALLOWED_CONTENT_TYPES:
                    raise ValueError("Tipo de contenido no permitido")

                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > _MAX_DOWNLOAD_BYTES:
                        break
                raw = bytes(body[:_MAX_DOWNLOAD_BYTES])
                try:
                    text = raw.decode(resp.encoding or "utf-8", errors="replace")
                except LookupError:
                    text = raw.decode("utf-8", errors="replace")
                return _strip_tags(text)[:_MAX_PAGE_CHARS]
        raise ValueError("Demasiadas redirecciones")


def extract_url_from_text(text: str) -> str | None:
    """Si el mensaje trae una URL, la devuelve (para navegar directo)."""
    match = re.search(r"https?://[^\s,;:)\"'>]+", text)
    if not match:
        return None
    url = match.group(0).rstrip(".,")
    return url if urlparse(url).netloc else None


def format_results_for_chat(results: list[dict], query: str) -> str:
    """Resultados → mensaje WhatsApp (corto, con fuente)."""
    if not results:
        return (
            f"🔍 Busqué «{query}» pero no encontré resultados útiles. "
            "Prueba con otras palabras."
        )
    lines = [f"🔍 Resultados para «{query}»:", ""]
    for i, r in enumerate(results, start=1):
        lines.append(f"{i}. {r['title']}")
        if r["snippet"]:
            lines.append(f"   {r['snippet']}")
        # Dominio como fuente citable
        domain = urlparse(r["url"]).netloc.replace("www.", "")
        lines.append(f"   🔗 {domain}")
        lines.append("")
    lines.append("Dime «abre [número]» y te traigo el contenido de esa página.")
    return "\n".join(lines).strip()[:1800]
