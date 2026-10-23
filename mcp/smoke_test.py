"""Smoke test del servidor MCP: conecta vía stdio, lista herramientas y
llama db_schema e infra_status.

    backend\.venv\Scripts\python.exe mcp\smoke_test.py
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parent / "server.py"


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(tool.name for tool in tools.tools)
            print(f"TOOLS ({len(names)}):", ", ".join(names))

            calls: dict[str, dict] = {"db_schema": {"table": "quotes"}, "infra_status": {}}
            for name, arguments in calls.items():
                if name not in names:
                    print(f"FALTA la herramienta {name}")
                    return 1
                result = await session.call_tool(name, arguments)
                text = result.content[0].text
                print(f"--- {name} ---")
                print(text[:600])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
