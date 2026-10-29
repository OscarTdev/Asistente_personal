"""Tests del módulo de búsqueda web (web_search).

Cubre: limpieza de consultas, extracción de URLs, saneo de HTML,
decodificación de redirects de DuckDuckGo, formato para chat y el
registro del módulo en el catálogo.
"""

from app.core.modules_registry import (
    AVAILABLE_MODULES,
    DEV_STATUS,
    plan_allows,
)
from app.services.orchestrator import _clean_search_query
from app.services.web_search import (
    _clean_url,
    _strip_tags,
    extract_url_from_text,
    format_results_for_chat,
)

# ── Limpieza de la consulta ─────────────────────────────────────────────────


def test_clean_query_strips_search_prefixes():
    assert _clean_search_query("busca en internet el precio del cobre") == (
        "el precio del cobre"
    )
    assert _clean_search_query("googlea el clima de medellin") == (
        "el clima de medellin"
    )
    assert _clean_search_query("Busca en la web horarios SENA?") == (
        "horarios sena"
    )


def test_clean_query_keeps_plain_queries():
    assert _clean_search_query("precio del cobre") == "precio del cobre"


# ── Extracción de URLs ──────────────────────────────────────────────────────


def test_extract_url_from_text():
    assert extract_url_from_text("navega a https://example.com") == (
        "https://example.com"
    )
    assert extract_url_from_text("mira http://a.co/pagina?x=1.") == (
        "http://a.co/pagina?x=1"
    )
    assert extract_url_from_text("no hay enlace aquí") is None


# ── Saneo de HTML ──────────────────────────────────────────────────────────


def test_strip_tags_removes_scripts_and_styles():
    html = (
        "<html><head><style>body{color:red}</style></head>"
        "<body><script>alert('x')</script>"
        "<p>Hola & bienvenido</p></body></html>"
    )
    text = _strip_tags(html)
    assert "Hola & bienvenido" in text
    assert "alert" not in text
    assert "color:red" not in text


# ── Redirects de DuckDuckGo ────────────────────────────────────────────────


def test_clean_url_decodes_ddg_redirect():
    raw = (
        "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpagina"
        "&rut=abc123"
    )
    assert _clean_url(raw) == "https://example.com/pagina"


def test_clean_url_keeps_direct_links():
    assert _clean_url("https://example.com") == "https://example.com"


# ── Formato para chat ──────────────────────────────────────────────────────


def test_format_results_for_chat_with_results():
    results = [
        {
            "title": "Precio del cobre",
            "url": "https://example.com/cobre",
            "snippet": "El cobre subió 3% esta semana.",
        },
        {"title": "Mercado de metales", "url": "https://metales.com",
         "snippet": ""},
    ]
    msg = format_results_for_chat(results, "precio del cobre")
    assert "precio del cobre" in msg
    assert "1. Precio del cobre" in msg
    assert "example.com" in msg
    assert "abre [número]" in msg


def test_format_results_for_chat_empty():
    msg = format_results_for_chat([], "xyz")
    assert "no encontré resultados" in msg


# ── Registro del módulo ────────────────────────────────────────────────────


def test_web_search_module_registered_and_active():
    keys = [m["key"] for m in AVAILABLE_MODULES]
    assert "web_search" in keys
    assert DEV_STATUS["web_search"] == "active"


def test_web_search_included_in_premium_plan():
    assert plan_allows("premium", "web_search")


def test_web_search_not_in_trial_plan():
    assert not plan_allows("trial", "web_search")