"""Servidor MCP local (stdio) del proyecto Asistente personal.

Expone herramientas read-only sobre la base de datos del proyecto y
herramientas de desarrollo (tests, lint, docs) para usarlo desde
Claude Desktop (plan gratuito soporta servidores MCP locales).

Diseño:
    - stdio: Claude Desktop lanza este proceso; nada escucha en red.
    - Solo lectura: guardrails estrictos sobre SQL (SELECT/WITH único,
      LIMIT forzado, statement_timeout, redacción de columnas sensibles).
    - Sin secretos en salida: el DSN se sanitiza en los mensajes de error.

Ejecución directa (para probar): python mcp/server.py  (Ctrl+C para salir)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server import MCPServer
from psycopg import connect
from psycopg.rows import dict_row

ROOT = Path(
    os.environ.get("ASISTENTE_PROJECT_ROOT") or Path(__file__).resolve().parents[1]
)  # raíz del repo (configurable para la extensión .mcpb)
BACKEND_DIR = ROOT / "backend"
DOCS_DIR = ROOT / "docs"

# Mismo default que backend/app/core/config.py (evita importar la app)
_DEFAULT_DSN = "postgresql://asistente:asistente@127.0.0.1:5433/asistente"

MAX_ROWS_HARD_CAP = 200
DEFAULT_ROW_LIMIT = 50
MAX_CELL_CHARS = 500
STATEMENT_TIMEOUT_MS = 10_000

# Columnas cuyo valor nunca sale de este servidor (claves, tokens, secretos).
SENSITIVE_COLUMN_RE = re.compile(
    r"(api_?key|token|secret|password|passwd|totp|credential|authorization|"
    r"private_key|access_key|otp_?code)",
    re.IGNORECASE,
)

# Solo consultas de lectura: SELECT o WITH (CTE). Una sola sentencia.
SELECT_PREFIX_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

# Escritura o administración: bloqueadas como palabra completa en cualquier
# parte de la consulta (los límites de palabra evitan falsos positivos como
# "created_at" por "create").
FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|"
    r"vacuum|analyze|analyse|reindex|merge|call|do|set|reset|listen|notify|"
    r"begin|commit|rollback|savepoint|release|prepare|execute|lock|comment)\b",
    re.IGNORECASE,
)

LIMIT_RE = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)

# Oculta la contraseña en un DSN antes de mostrarlo en un error.
DSN_PASSWORD_RE = re.compile(r"(://[^:@/\s]+:)[^@/\s]+(@)")


def sanitize_dsn(text: str) -> str:
    """Reemplaza la contraseña de un DSN por *** (nada de secretos en salida)."""
    return DSN_PASSWORD_RE.sub(r"\1***\2", text)


def load_dsn() -> str:
    """Resuelve DATABASE_URL: variable de entorno > .env de la raíz > default."""
    load_dotenv(ROOT / ".env")  # no pisa variables ya presentes en el entorno
    dsn = os.environ.get("DATABASE_URL", "").strip() or _DEFAULT_DSN
    # psycopg síncrono no usa el driver async declarado en la app
    return dsn.replace("postgresql+psycopg_async://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


def validate_select(query: str, max_rows: int) -> str:
    """Valida y normaliza una consulta read-only. Lanza ValueError si no.

    Reglas: una única sentencia, debe iniciar con SELECT/WITH, sin palabras
    de escritura/administración, con LIMIT forzado y acotado.
    """
    cleaned = (query or "").strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if not cleaned:
        raise ValueError("Consulta vacía.")
    if ";" in cleaned:
        raise ValueError("Solo se permite una única sentencia (sin ';').")
    if not SELECT_PREFIX_RE.match(cleaned):
        raise ValueError("Solo se permiten consultas que inicien con SELECT o WITH.")
    forbidden = FORBIDDEN_RE.search(cleaned)
    if forbidden:
        raise ValueError(f"Palabra no permitida en modo read-only: '{forbidden.group(1)}'.")

    max_rows = min(int(max_rows), MAX_ROWS_HARD_CAP)
    match = LIMIT_RE.search(cleaned)
    if match:
        if int(match.group(1)) > max_rows:
            cleaned = LIMIT_RE.sub(f"LIMIT {max_rows}", cleaned, count=1)
    else:
        cleaned = f"{cleaned}\nLIMIT {max_rows}"
    return cleaned


def redact_cell(column: str, value: Any) -> Any:
    """Redacta columnas sensibles y trunca textos largos."""
    if SENSITIVE_COLUMN_RE.search(column or ""):
        return "[REDACTED]"
    if isinstance(value, str) and len(value) > MAX_CELL_CHARS:
        return value[:MAX_CELL_CHARS] + "…[truncado]"
    return value


def redact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: redact_cell(key, value) for key, value in row.items()}


def fetch_readonly(
    query: str, max_rows: int = DEFAULT_ROW_LIMIT, params: tuple | None = None
) -> dict[str, Any]:
    """Ejecuta una consulta SELECT validada y devuelve filas como dicts."""
    sql = validate_select(query, max_rows)
    try:
        with connect(load_dsn(), row_factory=dict_row, connect_timeout=5) as conn:
            conn.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
            cur = conn.execute(sql, params)
            rows = [redact_row(r) for r in cur.fetchall()]
    except ValueError:
        raise
    except Exception as exc:  # error de BD: sin traceback ni DSN con secretos
        raise RuntimeError(f"Error de base de datos: {sanitize_dsn(str(exc))}") from None
    return {
        "row_count": len(rows),
        "truncated": len(rows) >= min(max_rows, MAX_ROWS_HARD_CAP),
        "rows": rows,
    }


def dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str, indent=1)


mcp = MCPServer("asistente-personal")


# ---------------------------------------------------------------------------
# Herramientas de datos del negocio (read-only)
# ---------------------------------------------------------------------------


@mcp.tool()
def run_sql(query: str, max_rows: int = DEFAULT_ROW_LIMIT) -> str:
    """Ejecuta una consulta SELECT de solo lectura sobre la base de datos del proyecto.

    Reglas: una sola sentencia que inicie con SELECT o WITH; LIMIT forzado
    (máximo 200 filas); columnas sensibles (api_key, tokens, secretos) salen
    como [REDACTED]. Usa primero db_schema() para conocer tablas y columnas.
    """
    try:
        return dump(fetch_readonly(query, max_rows))
    except Exception as exc:  # noqa: BLE001 — una herramienta nunca debe reventar el servidor
        return f"ERROR: {type(exc).__name__}: {sanitize_dsn(str(exc))}"


@mcp.tool()
def db_schema(table: str = "") -> str:
    """Lista las tablas y columnas del esquema public de la base de datos.

    Con `table` filtra a una sola tabla (coincidencia parcial). Úsala antes
    de escribir consultas con run_sql().
    """
    sql = (
        "SELECT table_name, column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public'"
    )
    params: tuple = ()
    if table:
        sql += " AND table_name ILIKE %s"
        params = (f"%{table.strip()}%",)
    sql += " ORDER BY table_name, ordinal_position"
    try:
        result = fetch_readonly(sql, MAX_ROWS_HARD_CAP, params)
    except (ValueError, RuntimeError) as exc:
        return f"ERROR: {exc}"
    grouped: dict[str, list[str]] = {}
    for row in result["rows"]:
        grouped.setdefault(row["table_name"], []).append(
            f"{row['column_name']} {row['data_type']}"
        )
    lines = [f"{name}({', '.join(cols)})" for name, cols in grouped.items()]
    return "\n".join(lines) or "Sin tablas."


@mcp.tool()
def business_snapshot() -> str:
    """Resumen agregado del negocio: tenants, cotizaciones por estado, mensajes
    de los últimos 7 días, recordatorios pendientes/vencidos y consumo de IA
    de los últimos 30 días. Todo agregado, sin datos personales.
    """
    queries = {
        "tenants": "SELECT count(*) AS total, count(*) FILTER (WHERE is_active) AS activos FROM tenants",
        "contacts": "SELECT count(*) AS total FROM contacts",
        "quotes_by_status": "SELECT status, count(*) AS total FROM quotes GROUP BY status ORDER BY total DESC",
        "messages_last_7d": "SELECT count(*) AS total FROM messages WHERE created_at > now() - interval '7 days'",
        "reminders": (
            "SELECT count(*) FILTER (WHERE status = 'pending') AS pendientes, "
            "count(*) FILTER (WHERE status = 'pending' AND remind_at < now()) AS vencidos "
            "FROM reminders"
        ),
        "llm_usage_30d": (
            "SELECT count(*) AS llamadas, COALESCE(sum(input_tokens), 0) AS tokens_entrada, "
            "COALESCE(sum(output_tokens), 0) AS tokens_salida, "
            "COALESCE(sum(audio_seconds), 0) AS audio_segundos "
            "FROM llm_usage WHERE created_at > now() - interval '30 days'"
        ),
    }
    snapshot: dict[str, Any] = {}
    for name, query in queries.items():
        try:
            snapshot[name] = fetch_readonly(query, 1)["rows"]
        except Exception as exc:  # noqa: BLE001
            snapshot[name] = f"ERROR: {type(exc).__name__}: {sanitize_dsn(str(exc))}"
    return dump(snapshot)


# ---------------------------------------------------------------------------
# Herramientas de desarrollo
# ---------------------------------------------------------------------------


def _run_subprocess(cmd: list[str], cwd: Path, timeout_s: int) -> str:
    """Corre un proceso capturando salida; devuelve el final (lo relevante)."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.run(  # noqa: S603 — argv fijo, sin shell
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: el proceso excedió {timeout_s}s y fue terminado."
    output = (proc.stdout or "") + (proc.stderr or "")
    lines = output.strip().splitlines()
    tail = "\n".join(lines[-80:]) if lines else "(sin salida)"
    return f"exit_code={proc.returncode}\n{tail}"


def _backend_python() -> str:
    """Intérprete con las dependencias del proyecto (venv del backend)."""
    candidate = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    if os.name != "nt":
        candidate = BACKEND_DIR / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


@mcp.tool()
def run_tests(args: list[str] | None = None) -> str:
    """Corre los tests del backend con pytest (carpeta backend/tests).

    `args` opcional: lista de argumentos extra de pytest, p. ej.
    ["tests/test_google.py", "-k", "callback"] o ["-v"]. Máximo 15 minutos.
    """
    cmd = [_backend_python(), "-m", "pytest", "-q", *(args or [])]
    return _run_subprocess(cmd, BACKEND_DIR, timeout_s=900)


@mcp.tool()
def run_lint() -> str:
    """Corre ruff check sobre el backend (lint del proyecto)."""
    ruff = Path(_backend_python()).parent / ("ruff.exe" if os.name == "nt" else "ruff")
    if not ruff.exists():
        found = shutil.which("ruff")
        if not found:
            return "ERROR: ruff no está disponible en el venv."
        ruff = Path(found)
    return _run_subprocess([str(ruff), "check", "."], BACKEND_DIR, timeout_s=120)


@mcp.tool()
def search_docs(query: str) -> str:
    """Busca texto (sin distinguir mayúsculas) en la documentación del proyecto:
    docs/*.md, README.md, AGENTS.md, CLAUDE.md, PRODUCT.md y DESIGN.md.
    Devuelve coincidencias como archivo:línea: texto.
    """
    needle = (query or "").strip().lower()
    if not needle:
        return "ERROR: indica un texto a buscar."
    files = sorted(DOCS_DIR.rglob("*.md")) + [
        ROOT / name
        for name in ("README.md", "AGENTS.md", "CLAUDE.md", "PRODUCT.md", "DESIGN.md")
        if (ROOT / name).exists()
    ]
    matches: list[str] = []
    for path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(ROOT)
        for number, line in enumerate(content.splitlines(), start=1):
            if needle in line.lower():
                matches.append(f"{rel}:{number}: {line.strip()[:200]}")
                if len(matches) >= 40:
                    matches.append("…(más coincidencias omitidas)")
                    return "\n".join(matches)
    return "\n".join(matches) or f"Sin coincidencias para '{query}'."


@mcp.tool()
def list_migrations() -> str:
    """Lista las migraciones de Alembic (backend/alembic/versions) con su
    revisión, revisión padre y descripción, en orden de archivo.
    """
    versions_dir = BACKEND_DIR / "alembic" / "versions"
    if not versions_dir.exists():
        return "ERROR: no existe backend/alembic/versions."
    rev_re = re.compile(r"^revision(?::\s*str)?\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
    down_re = re.compile(r"^down_revision[^\n=]*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
    lines: list[str] = []
    for path in sorted(versions_dir.glob("*.py")):
        content = path.read_text(encoding="utf-8", errors="replace")
        revision = rev_re.search(content)
        down = down_re.search(content)
        stripped = content.lstrip()
        summary = stripped[3:].splitlines()[0].strip() if stripped.startswith('"""') else ""
        lines.append(
            f"{path.stem} | revision={revision.group(1) if revision else '?'} "
            f"| down={down.group(1) if down else 'None'} | {summary[:80]}"
        )
    return "\n".join(lines) or "Sin migraciones."


@mcp.tool()
def infra_status() -> str:
    """Estado de la infraestructura local: Postgres (5433), Redis (6379),
    backend FastAPI (http://127.0.0.1:8000/health) y frontend Vite (:5173).
    """
    status: dict[str, str] = {}

    def tcp_ok(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            return False

    status["postgres_5433"] = "arriba" if tcp_ok("127.0.0.1", 5433) else "caído"
    status["redis_6379"] = "arriba" if tcp_ok("127.0.0.1", 6379) else "caído"

    try:
        import httpx

        for name, url in (
            ("backend_8000", "http://127.0.0.1:8000/health"),
            ("frontend_5173", "http://localhost:5173"),
        ):
            try:
                resp = httpx.get(url, timeout=3)
                status[name] = f"HTTP {resp.status_code}"
            except Exception:  # noqa: BLE001 — httpx.ConnectError no es OSError
                status[name] = "caído"
    except ImportError:
        status["backend_8000"] = "no verificado (httpx no disponible)"
        status["frontend_5173"] = "no verificado (httpx no disponible)"

    return dump(status)


# ---------------------------------------------------------------------------
# Herramientas de archivos (sandbox: solo carpetas permitidas)
# ---------------------------------------------------------------------------


def _allowed_roots() -> list[Path]:
    """Raíces permitidas para lectura/escritura (relativas a ROOT del proyecto)."""
    return [
        BACKEND_DIR / "app",
        BACKEND_DIR / "tests",
        ROOT / "admin-web" / "src",
        DOCS_DIR,
    ]


def _resolve_inside(path: str) -> Path:
    """
    Resuelve una ruta (absoluta o relativa a ROOT) y verifica que esté
    dentro de una raíz permitida. Lanza ValueError si no.
    """
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    for root in _allowed_roots():
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    allowed = ", ".join(str(r.relative_to(ROOT)) for r in _allowed_roots())
    raise ValueError(f"Ruta fuera de la zona permitida. Raíces: {allowed}")


def _safe_read_text(path: Path, max_bytes: int = 200_000) -> str:
    """Lee texto UTF-8 con límite de tamaño; rechaza binarios (bytes nulos).
    Usa newline='' para NO traducir saltos de línea (preserva \\r\\n, \\r, \\n tal cual)."""
    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")
    if path.stat().st_size > max_bytes:
        raise ValueError(f"Archivo demasiado grande (> {max_bytes} bytes).")
    data = path.read_bytes()
    if b"\x00" in data:
        raise ValueError("Archivo binario (contiene bytes nulos), no se puede leer como texto.")
    return data.decode("utf-8", errors="replace")


def _normalize_newlines(text: str) -> str:
    """Normaliza CRLF y CR a LF para búsquedas/comparaciones internas."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _detect_newline(text: str) -> str:
    """Detecta el estilo de salto de línea predominante en el texto original."""
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def _safe_write_text(path: Path, content: str) -> None:
    """Escribe texto UTF-8 SIN traducir saltos de línea (newline='')."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(content)


@mcp.tool()
def list_files(path: str = "", depth: int = 2) -> str:
    """
    Lista archivos y carpetas bajo una ruta permitida.
    `path`: relativa a la raíz del proyecto o absoluta (debe caer en zona permitida).
    `depth`: profundidad máxima (1-5). Omite __pycache__, node_modules, .git, .venv, dist.
    """
    try:
        # Si path es vacío, listar desde cada raíz permitida (vista general)
        if not path:
            out: list[str] = []
            for root in _allowed_roots():
                out.append(f"\n=== {root.relative_to(ROOT)} ===")
                out.extend(_list_dir(root, max_depth=depth))
            return "\n".join(out) or "(vacío)"
        base = _resolve_inside(path)
        return "\n".join(_list_dir(base, max_depth=depth)) or "(vacío)"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {type(exc).__name__}: {exc}"


def _list_dir(dir_path: Path, max_depth: int, current_depth: int = 0) -> list[str]:
    if current_depth >= max_depth:
        return []
    skip = {"__pycache__", "node_modules", ".git", ".venv", "dist", "build", ".pytest_cache", ".mypy_cache"}
    items: list[str] = []
    try:
        for entry in sorted(dir_path.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
            if entry.name in skip:
                continue
            rel = entry.relative_to(ROOT)
            prefix = "📁 " if entry.is_dir() else "📄 "
            items.append(f"{prefix}{rel}")
            if entry.is_dir() and current_depth + 1 < max_depth:
                items.extend(_list_dir(entry, max_depth, current_depth + 1))
    except OSError:
        pass
    return items


@mcp.tool()
def read_file(path: str, max_lines: int = 400, start_line: int = 1) -> str:
    """
    Lee un archivo de texto con numeración de líneas (útil para ediciones precisas).
    `path`: ruta permitida. `max_lines`: máx. líneas a devolver (1-2000).
    `start_line`: línea inicial (1-indexed).
    """
    try:
        resolved = _resolve_inside(path)
        content = _safe_read_text(resolved)
        lines = content.splitlines()
        total = len(lines)
        start = max(1, start_line) - 1
        end = min(total, start + max(max_lines, 1))
        snippet = "\n".join(f"{i+1:5d}: {lines[i]}" for i in range(start, end))
        header = f"# {resolved.relative_to(ROOT)}  ({total} líneas totales; mostrando {start+1}–{end})"
        return f"{header}\n{snippet}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {type(exc).__name__}: {exc}"


@mcp.tool()
def search_code(pattern: str, path: str = "", glob: str = "*.py", max_results: int = 40) -> str:
    """
    Busca regex en archivos bajo zonas permitidas.
    `path`: subcarpeta opcional (relativa a ROOT o absoluta permitida).
    `glob`: patrón tipo glob (ej. '*.py', '*.tsx', '*.json').
    `max_results`: tope de coincidencias.
    """
    try:
        if not pattern:
            return "ERROR: patrón vacío."
        base = _resolve_inside(path) if path else None
        roots = [base] if base else _allowed_roots()
        import re
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"ERROR: regex inválida: {e}"
        matches: list[str] = []
        for root in roots:
            for file_path in root.rglob(glob):
                if file_path.is_dir() or file_path.stat().st_size > 500_000:
                    continue
                if any(part in {"__pycache__", "node_modules", ".git", ".venv", "dist"} for part in file_path.parts):
                    continue
                try:
                    text = _safe_read_text(file_path)
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        rel = file_path.relative_to(ROOT)
                        matches.append(f"{rel}:{i}: {line.strip()[:200]}")
                        if len(matches) >= max_results:
                            matches.append("…(más coincidencias omitidas)")
                            return "\n".join(matches)
        return "\n".join(matches) or f"Sin coincidencias para '{pattern}'."
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {type(exc).__name__}: {exc}"


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """
    Escribe un archivo de texto (crea directorios padre si es necesario).
    `path`: ruta permitida. `content`: texto UTF-8 (máx. 1 MB).
    Sobrescribe si existe. NO permite escribir fuera de las raíces permitidas.
    Preserva los saltos de línea tal cual se pasen en `content`.
    """
    try:
        resolved = _resolve_inside(path)
        if len(content.encode("utf-8")) > 1_000_000:
            return "ERROR: contenido demasiado grande (> 1 MB)."
        _safe_write_text(resolved, content)
        return f"OK: escrito {resolved.relative_to(ROOT)} ({len(content)} caracteres)."
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {type(exc).__name__}: {exc}"


@mcp.tool()
def replace_in_file(path: str, old: str, new: str) -> str:
    """
    Reemplaza EXACTAMENTE UNA ocurrencia de `old` por `new` en el archivo.
    Útil para ediciones quirúrgicas sin reescribir todo el archivo.
    Falla si `old` no aparece o aparece más de una vez.
    Normaliza saltos de línea (CRLF/CR → LF) para la búsqueda, pero escribe
    preservando el estilo original del archivo.
    """
    try:
        resolved = _resolve_inside(path)
        original = _safe_read_text(resolved)
        # Normalizar para búsqueda
        norm_original = _normalize_newlines(original)
        norm_old = _normalize_newlines(old)
        count = norm_original.count(norm_old)
        if count == 0:
            return "ERROR: el texto a reemplazar no se encuentra en el archivo."
        if count > 1:
            return f"ERROR: el texto aparece {count} veces; debe ser único para replace_in_file."
        # Encontrar posición en el original (usando versión normalizada)
        idx_norm = norm_original.index(norm_old)
        # Mapear al original: contar cuántos \r hay antes de esa posición
        # Estrategia simple: reemplazar en la versión normalizada y luego
        # convertir al estilo de salto de línea original
        norm_new = _normalize_newlines(new)
        norm_result = norm_original[:idx_norm] + norm_new + norm_original[idx_norm + len(norm_old):]
        # Convertir al estilo original
        nl = _detect_newline(original)
        if nl != "\n":
            result = norm_result.replace("\n", nl)
        else:
            result = norm_result
        _safe_write_text(resolved, result)
        return f"OK: reemplazado en {resolved.relative_to(ROOT)}."
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {type(exc).__name__}: {exc}"


if __name__ == "__main__":
    mcp.run()  # transporte stdio por defecto: Claude Desktop habla por stdin/stdout
