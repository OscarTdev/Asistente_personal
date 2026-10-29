"""Rate limiting utilities for authentication endpoints."""

import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

# Simple in-memory rate limiter (per IP)
# For production with multiple workers, use Redis-backed limiter
_attempts: dict[str, list[float]] = defaultdict(list)

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 300  # 5 minutes


@dataclass(frozen=True)
class RateLimiter:
    """Dependency to rate-limit login attempts by client IP."""

    max_attempts: int = MAX_ATTEMPTS
    window_seconds: int = WINDOW_SECONDS

    async def __call__(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old attempts
        _attempts[client_ip] = [t for t in _attempts[client_ip] if t > window_start]

        if len(_attempts[client_ip]) >= self.max_attempts:
            retry_after = int(self.window_seconds - (now - _attempts[client_ip][0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos. Intenta de nuevo en {retry_after} segundos.",
                headers={"Retry-After": str(retry_after)},
            )

        # Record this attempt
        _attempts[client_ip].append(now)


def reset_rate_limiter() -> None:
    """Reset the rate limiter state (useful for tests)."""
    _attempts.clear()


# Singleton instance for login endpoint
login_rate_limiter = RateLimiter()