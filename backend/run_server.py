#!/usr/bin/env python
"""Entry point for running the server on Windows with correct event loop."""

import asyncio
import sys

# Set event loop policy BEFORE ANY OTHER IMPORTS
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Verify the policy is set
print(f"Event loop policy: {asyncio.get_event_loop_policy().__class__.__name__}")

# Now import and run
import uvicorn  # noqa: E402  # Must load after the Windows event-loop policy.

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        loop="asyncio:SelectorEventLoop"
    )