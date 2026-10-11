from fastapi import FastAPI

from app.api import ws
from app.api.v1 import api_router

app = FastAPI(title="Asistente Personal API")

app.include_router(api_router, prefix="/api/v1")
app.include_router(ws.router)

@app.get("/health")
async def health():
    return {"status": "ok"}