"""Tests del anti-SSRF de la navegación web (web_search).

El bot no debe poder leer servicios internos (localhost, redes privadas,
metadatos de nube) aunque el dueño o su equipo se lo pidan.
"""

import ipaddress

import httpx
import pytest

from app.services import web_search
from app.services.web_search import _is_public_ip, assert_public_url, fetch_page_text

# ── IPs permitidas y bloqueadas ────────────────────────────────────────────


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.10",
        "169.254.169.254",  # metadatos de nube
        "100.64.0.1",  # CGNAT
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",  # IPv4 mapeada en IPv6
    ],
)
def test_non_public_ips_are_blocked(ip):
    assert not _is_public_ip(ipaddress.ip_address(ip))


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"])
def test_public_ips_are_allowed(ip):
    assert _is_public_ip(ipaddress.ip_address(ip))


# ── URLs ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/archivo",
        "file:///etc/passwd",
        "http://",
        "http://usuario:clave@example.com/",
        "https://example.com:8080/admin",
        "http://example.com:6379/",
    ],
)
async def test_assert_public_url_rejects_bad_urls(url):
    with pytest.raises(ValueError):
        await assert_public_url(url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://2130706433/",  # 127.0.0.1 en decimal
    ],
)
async def test_assert_public_url_rejects_internal_hosts(url):
    with pytest.raises(ValueError):
        await assert_public_url(url)


@pytest.mark.asyncio
async def test_assert_public_url_accepts_public_host(monkeypatch):
    async def fake_resolve(host, port):
        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr(web_search, "_resolve_ips", fake_resolve)
    await assert_public_url("https://example.com/pagina")


@pytest.mark.asyncio
async def test_assert_public_url_rejects_if_any_ip_is_private(monkeypatch):
    """Un dominio que resuelve a una IP pública y otra interna se rechaza."""

    async def fake_resolve(host, port):
        return [
            ipaddress.ip_address("93.184.216.34"),
            ipaddress.ip_address("10.0.0.5"),
        ]

    monkeypatch.setattr(web_search, "_resolve_ips", fake_resolve)
    with pytest.raises(ValueError):
        await assert_public_url("https://mezclado.example.com/")


# ── fetch_page_text: redirecciones, tipo y tamaño ──────────────────────────


def _patch_client(monkeypatch, handler):
    """Reemplaza el cliente httpx por uno con transporte simulado."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(web_search.httpx, "AsyncClient", factory)

    async def fake_resolve(host, port):
        # Los dominios de prueba resuelven a lo que diga el nombre
        if host.startswith("interno"):
            return [ipaddress.ip_address("127.0.0.1")]
        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr(web_search, "_resolve_ips", fake_resolve)


@pytest.mark.asyncio
async def test_fetch_page_text_reads_public_html(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body><script>x()</script><p>Hola mundo</p></body></html>",
        )

    _patch_client(monkeypatch, handler)
    text = await fetch_page_text("https://publico.example.com/")
    assert "Hola mundo" in text
    assert "x()" not in text


@pytest.mark.asyncio
async def test_fetch_page_text_blocks_redirect_to_internal(monkeypatch):
    """Una página pública que redirige a un host interno se corta."""

    def handler(request):
        if request.url.host == "publico.example.com":
            return httpx.Response(
                302, headers={"location": "http://interno.example.com/secreto"}
            )
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, text="DATO INTERNO"
        )

    _patch_client(monkeypatch, handler)
    with pytest.raises(ValueError):
        await fetch_page_text("https://publico.example.com/")


@pytest.mark.asyncio
async def test_fetch_page_text_limits_redirects(monkeypatch):
    def handler(request):
        return httpx.Response(302, headers={"location": "https://publico.example.com/otra"})

    _patch_client(monkeypatch, handler)
    with pytest.raises(ValueError):
        await fetch_page_text("https://publico.example.com/")


@pytest.mark.asyncio
async def test_fetch_page_text_rejects_binary_content(monkeypatch):
    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "application/octet-stream"}, content=b"\x00\x01"
        )

    _patch_client(monkeypatch, handler)
    with pytest.raises(ValueError):
        await fetch_page_text("https://publico.example.com/archivo.bin")


@pytest.mark.asyncio
async def test_fetch_page_text_truncates_output(monkeypatch):
    big = "<p>" + ("palabra " * 5000) + "</p>"

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=big)

    _patch_client(monkeypatch, handler)
    text = await fetch_page_text("https://publico.example.com/")
    assert 0 < len(text) <= web_search._MAX_PAGE_CHARS
