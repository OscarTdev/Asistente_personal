"""Tests unitarios del servidor MCP (funciones puras, sin base de datos).

Se ejecutan con el venv del backend desde la raíz:
    backend/.venv/Scripts/python.exe -m pytest mcp/test_server.py -v
"""

from pathlib import Path

import pytest

from server import (
    DEFAULT_ROW_LIMIT,
    MAX_ROWS_HARD_CAP,
    ROOT,
    DOCS_DIR,
    list_migrations,
    redact_cell,
    redact_row,
    sanitize_dsn,
    search_docs,
    validate_select,
    _resolve_inside,
    _allowed_roots,
    _safe_read_text,
    list_files,
    read_file,
    search_code,
    write_file,
    replace_in_file,
)


class TestValidateSelect:
    def test_accepts_select_and_forces_limit(self):
        sql = validate_select("SELECT * FROM tenants", DEFAULT_ROW_LIMIT)
        assert sql.startswith("SELECT")
        assert f"LIMIT {DEFAULT_ROW_LIMIT}" in sql

    def test_accepts_with_cte(self):
        sql = validate_select("WITH t AS (SELECT 1 AS x) SELECT * FROM t", 10)
        assert sql.upper().startswith("WITH")
        assert "LIMIT 10" in sql

    def test_keeps_small_existing_limit(self):
        sql = validate_select("SELECT 1 LIMIT 10", 50)
        assert "LIMIT 10" in sql

    def test_caps_existing_limit_to_requested_rows(self):
        # Un LIMIT mayor se recorta al max_rows solicitado (aquí 50), no al hard cap.
        sql = validate_select("SELECT * FROM messages LIMIT 100000", 50)
        assert "LIMIT 50" in sql
        assert "100000" not in sql

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            validate_select("   ", 50)

    def test_rejects_multiple_statements(self):
        for query in (
            "SELECT 1; DROP TABLE tenants",
            "SELECT 1;; SELECT 2",
            "SELECT 1 --; DROP TABLE tenants",
        ):
            with pytest.raises(ValueError):
                validate_select(query, 50)

    def test_rejects_writes(self):
        for query in (
            "INSERT INTO tenants (name) VALUES ('x')",
            "UPDATE tenants SET plan = 'premium'",
            "DELETE FROM quotes",
            "DROP TABLE messages",
            "ALTER TABLE tenants ADD COLUMN x int",
            "CREATE TABLE evil (id int)",
            "TRUNCATE messages",
            "GRANT ALL ON tenants TO public",
            "COPY tenants TO '/tmp/x'",
            "VACUUM",
        ):
            with pytest.raises(ValueError):
                validate_select(query, 50)

    def test_rejects_non_select_prefix(self):
        for query in ("EXPLAIN SELECT 1", "SHOW TABLES", "TABLE tenants"):
            with pytest.raises(ValueError):
                validate_select(query, 50)

    def test_rejects_wrapped_write(self):
        with pytest.raises(ValueError):
            validate_select("WITH x AS (DELETE FROM quotes RETURNING *) SELECT * FROM x", 50)

    def test_word_boundaries_avoid_false_positives(self):
        # "created_at" no debe activar "create"; "offset" no debe activar "set".
        sql = validate_select(
            "SELECT created_at, status FROM quotes ORDER BY created_at DESC OFFSET 0", 10
        )
        assert "created_at" in sql


class TestRedaction:
    def test_sensitive_columns_are_redacted(self):
        for column in (
            "api_key",
            "api_key_hash",
            "access_token",
            "refresh_token",
            "totp_secret",
            "password_hash",
            "webhook_secret",
        ):
            assert redact_cell(column, "valor-secreto") == "[REDACTED]"

    def test_normal_columns_pass_through(self):
        assert redact_cell("created_at", "2026-10-23") == "2026-10-23"
        assert redact_cell("status", "sent") == "sent"
        assert redact_cell("total", 150000) == 150000

    def test_long_text_truncated(self):
        long_text = "a" * 2000
        value = redact_cell("content", long_text)
        assert len(value) < 600
        assert value.endswith("…[truncado]")

    def test_redact_row(self):
        row = redact_row({"id": 1, "api_key": "abc", "name": "Tienda"})
        assert row["api_key"] == "[REDACTED]"
        assert row["name"] == "Tienda"


class TestSanitizeDsn:
    def test_hides_password(self):
        dsn = "postgresql://asistente:supersecret@127.0.0.1:5433/asistente"
        assert "supersecret" not in sanitize_dsn(dsn)
        assert "***" in sanitize_dsn(dsn)
        assert "asistente" in sanitize_dsn(dsn)


class TestRepoHelpers:
    def test_list_migrations_finds_revisions(self):
        output = list_migrations()
        assert output and "ERROR" not in output
        assert "revision=" in output

    def test_search_docs_finds_known_term(self):
        output = search_docs("WhatsApp")
        assert "Sin coincidencias" not in output
        assert "ERROR" not in output
        assert ":" in output  # formato archivo:línea: texto

    def test_search_docs_root_independent(self):
        # ROOT es absoluto (derivado de __file__), no depende del cwd.
        import os

        prev = Path.cwd()
        os.chdir(Path(os.environ.get("TEMP", prev)))
        try:
            assert "ERROR" not in search_docs("WhatsApp")
        finally:
            os.chdir(prev)


class TestFilesystemSandbox:
    def test_allowed_roots_exist(self):
        roots = _allowed_roots()
        assert len(roots) == 4
        for r in roots:
            assert r.exists(), f"Raíz no existe: {r}"

    def test_resolve_inside_allowed(self):
        # Ruta absoluta dentro de backend/app
        p = _resolve_inside(str(ROOT / "backend" / "app" / "services"))
        assert p == (ROOT / "backend" / "app" / "services").resolve()

    def test_resolve_inside_rejected_outside(self):
        import pytest
        # .env en la raíz (fuera de zonas permitidas)
        with pytest.raises(ValueError):
            _resolve_inside(str(ROOT / ".env"))
        # backend/alembic (no permitido)
        with pytest.raises(ValueError):
            _resolve_inside(str(ROOT / "backend" / "alembic"))
        # root del proyecto
        with pytest.raises(ValueError):
            _resolve_inside(str(ROOT))

    def test_resolve_traversal_rejected(self):
        import pytest
        # Traversal desde zona permitida
        with pytest.raises(ValueError):
            _resolve_inside(str(ROOT / "backend" / "app" / ".." / ".." / ".env"))

    def test_read_write_roundtrip_docs_temp(self):
        """Usa docs/ (raíz permitida) para test roundtrip sin monkeypatch."""
        import server as srv
        test_file = DOCS_DIR / "_mcp_test_temp.txt"
        try:
            # write_file
            res = srv.write_file(str(test_file), "hola mundo")
            assert "OK" in res
            # read_file
            out = srv.read_file(str(test_file))
            assert "hola mundo" in out
            # replace_in_file
            res = srv.replace_in_file(str(test_file), "hola", "adiós")
            assert "OK" in res
            out = srv.read_file(str(test_file))
            assert "adiós mundo" in out
            # replace_in_file falla si no hay coincidencia
            res = srv.replace_in_file(str(test_file), "noexiste", "x")
            assert "ERROR" in res
            # replace_in_file falla si hay múltiples
            test_file.write_text("uno uno")
            res = srv.replace_in_file(str(test_file), "uno", "dos")
            assert "ERROR" in res
            # search_code
            test_file.write_text("def foo():\n    pass\n")
            res = srv.search_code(r"def foo", path="docs", glob="*.txt")
            assert "_mcp_test_temp.txt" in res
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_list_files_docs(self):
        import server as srv
        # docs/ existe y tiene archivos
        out = srv.list_files("docs")
        assert "docs" in out.lower() or ".md" in out
