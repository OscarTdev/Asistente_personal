# MCP local del proyecto (Claude Desktop)

Servidor MCP **local (stdio)** que permite a Claude Desktop consultar datos del
negocio (read-only) y usar herramientas de desarrollo del proyecto. Nada se
expone a internet: Claude lanza un subproceso en tu máquina.

```
mcp/
  server.py                        # servidor MCP (FastMCP/MCPServer, stdio)
  test_server.py                   # tests unitarios (guardrails SQL, redacción)
  smoke_test.py                    # prueba end-to-end por stdio
  requirements.txt                 # dependencia: mcp[cli]
  extension/                       # extensión Desktop (.mcpb descomprimida)
    manifest.json
    server.py                      # copia empaquetada
    requirements.txt
  asistente-personal.mcpb          # paquete listo para instalar
```

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `run_sql(query, max_rows=50)` | `SELECT`/`WITH` de solo lectura. Una sentencia, `LIMIT` forzado (máx. 200), timeout 10 s, columnas sensibles → `[REDACTED]` |
| `db_schema(table="")` | Tablas y columnas de `public` (filtro opcional) |
| `business_snapshot()` | Agregados: tenants, contactos, cotizaciones por estado, mensajes 7 d, recordatorios, uso de IA 30 d |
| `infra_status()` | Postgres 5433, Redis 6379, backend `:8000/health`, frontend `:5173` |
| `list_migrations()` | Migraciones Alembic (revision, down_revision, descripción) |
| `search_docs(query)` | Busca en `docs/*.md`, `README`, `AGENTS`, `CLAUDE`, `PRODUCT`, `DESIGN` |
| `run_tests(args=[])` | `pytest` en `backend/tests` (máx. 15 min) usando el venv del backend |
| `run_lint()` | `ruff check .` en el backend |
| `list_files(path="", depth=2)` | Lista archivos/carpetas en zonas permitidas (`backend/app`, `backend/tests`, `admin-web/src`, `docs`). Profundidad 1-5. |
| `read_file(path, max_lines=400, start_line=1)` | Lee archivo con numeración de líneas (útil para ediciones precisas). Máx. 2000 líneas. |
| `search_code(pattern, path="", glob="*.py", max_results=40)` | Busca regex en código dentro de zonas permitidas. |
| `write_file(path, content)` | Escribe/crea archivo de texto (máx. 1 MB) en zonas permitidas. Crea directorios padre. |
| `replace_in_file(path, old, new)` | Reemplaza **exactamente una** ocurrencia. Falla si 0 o >1 coincidencias. |

## Instalación — Claude Desktop nuevo (versión 3.6+, MSIX, con Extensions)

Esta versión **ya no lee `claude_desktop_config.json`**; usa **Desktop
Extensions** (`.mcpb`):

1. Abre Claude Desktop → **Settings → Extensions**.
2. **Advanced settings / Extension Developer** → **Install Extension…**
   y elige `mcp/asistente-personal.mcpb`
   (o **Install Unpacked Extension…** y elige la carpeta `mcp/extension`).
3. Al instalarse, configura:
   - **Carpeta del proyecto**: `C:\Users\juand\OneDrive\Desktop\Asistente_personal`
   - **Python del venv del backend**: `...\backend\.venv\Scripts\python.exe`
4. En un chat nuevo, 🔧 debe mostrar **asistente-personal** con 13 herramientas.

Prueba rápida:

> Usa `business_snapshot` y dime cuántos tenants activos hay.

> Usa `list_files` con `path: "docs"` y dime qué archivos hay.

### Reconstruir el paquete

```powershell
Copy-Item mcp\server.py mcp\extension\server.py -Force
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
  "$PWD\mcp\extension", "$PWD\mcp\asistente-personal.mcpb", "Optimal", $false)
```

## Instalación — Claude Desktop clásico (config JSON)

Solo para versiones que aún leen el JSON (en la MSIX nueva la ruta real fue
`%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "asistente": {
      "command": "C:\\Users\\juand\\OneDrive\\Desktop\\Asistente_personal\\backend\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\juand\\OneDrive\\Desktop\\Asistente_personal\\mcp\\server.py"]
    }
  }
}
```

**Importante:** guarda el archivo **sin BOM** (UTF-8 plano). Windows PowerShell
5.1 (`Set-Content -Encoding utf8`) agrega BOM y Node lo rechaza en silencio.
Ejemplo correcto:

```powershell
[System.IO.File]::WriteAllText($path, $json, [System.Text.UTF8Encoding]::new($false))
```

## Seguridad

- Transporte **stdio local**: no abre puertos ni requiere red pública.
- SQL **solo lectura**: `SELECT`/`WITH`, una sola sentencia, sin palabras de
  escritura (`INSERT`, `UPDATE`, `DROP`, …), `LIMIT` forzado y
  `statement_timeout = 10 s`; `connect_timeout = 5 s`.
- **Redacción** de columnas sensibles (`api_key`, `token`, `secret`, `password`,
  `totp`, …) y truncado de textos largos (500 caracteres).
- Errores **sin secretos**: el DSN se sanitiza (`***`) antes de devolverse.
- Las herramientas **nunca lanzan excepciones** al protocolo: devuelven
  `ERROR: <tipo>: <mensaje>`.
- **Archivos — sandbox estricto**: solo `backend/app`, `backend/tests`,
  `admin-web/src`, `docs`. Rechaza rutas fuera, traversal (`..`), binarios,
  y `.env`/secretos (fuera de zonas). Escritura máx. 1 MB, lectura máx. 200 KB.
  `replace_in_file` exige coincidencia única para ediciones seguras.

## Pruebas

```powershell
# unitarios (sin BD)
backend\.venv\Scripts\python.exe -m pytest mcp\test_server.py -q

# end-to-end por stdio (requiere Postgres arriba)
backend\.venv\Scripts\python.exe mcp\smoke_test.py
```

## Notas

- `run_sql` rechaza consultas que contengan palabras de escritura incluso dentro
  de literales (p. ej. `LIKE '%delete%'`): es conservador a propósito.
- Docker Desktop debe estar arriba para las herramientas de base de datos; si
  no, responden `connection timeout expired` en ~10 s (nunca se cuelgan).
- `ASISTENTE_PROJECT_ROOT` permite ejecutar el servidor empaquetado desde otra
  carpeta apuntando a la raíz real del proyecto.
