"""Guardián LLM: tarea periódica ARQ que monitorea salud de proveedores IA
y decide cambios automáticos de proveedor/modelo + notifica al superadmin.

Se ejecuta cada N minutos (configurable via ARQ cron).
"""
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels import get_channel
from app.core.config import get_settings
from app.services import platform_ai as ai_config_svc

logger = logging.getLogger(__name__)

# Proveedores conocidos con sus modelos recomendados (fallback order)
PROVIDER_CHAIN = [
    {
        "name": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": {
            "chat": "meta-llama/llama-3.1-70b-instruct",
            "intent": "meta-llama/llama-3.1-8b-instruct",
            "vision": "qwen/qwen2.5-vl-72b-instruct",
        },
        "env_key_prefix": "OPENROUTER",
    },
    {
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models": {
            "chat": "meta-llama/llama-3.1-70b-instruct",
            "intent": "meta-llama/llama-3.1-8b-instant",
            "vision": None,  # Groq no tiene visión multimodal estable
        },
        "env_key_prefix": "GROQ",
    },
    {
        "name": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "models": {
            "chat": "nvidia/nemotron-3-ultra-550b-a55b",
            "intent": "nvidia/nemotron-3-ultra-550b-a55b",
            "vision": "nvidia/nemotron-3.5-super-vl-120b-a12b",
        },
        "env_key_prefix": "NVIDIA",
    },
]


async def _collect_health_metrics(db: AsyncSession, window_minutes: int = 15) -> dict[str, Any]:
    """Recopila métricas de salud de proveedores IA de los últimos N minutos."""
    since = datetime.now(UTC) - timedelta(minutes=window_minutes)
    
    metrics = {
        "window_minutes": window_minutes,
        "since": since.isoformat(),
        "llm_usage": {},
        "events": {},
        "audit": {},
    }

    # 1. LlmUsage: errores, latencias, tokens por proveedor/modelo
    try:
        # Usamos raw SQL para eficiencia
        stmt = text("""
            SELECT 
                provider,
                model,
                COUNT(*) as total_calls,
                COUNT(*) FILTER (WHERE error IS NOT NULL AND error != '') as errors,
                AVG(latency_ms) as avg_latency_ms,
                MAX(latency_ms) as max_latency_ms,
                SUM(prompt_tokens + completion_tokens) as total_tokens
            FROM llm_usage
            WHERE created_at >= :since
            GROUP BY provider, model
        """)
        result = await db.execute(stmt, {"since": since})
        metrics["llm_usage"]["by_provider_model"] = [
            {
                "provider": r.provider,
                "model": r.model,
                "total_calls": r.total_calls,
                "errors": r.errors,
                "error_rate": r.errors / r.total_calls if r.total_calls > 0 else 0,
                "avg_latency_ms": float(r.avg_latency_ms) if r.avg_latency_ms else 0,
                "max_latency_ms": r.max_latency_ms,
                "total_tokens": r.total_tokens,
            }
            for r in result
        ]
    except Exception as e:
        logger.warning("Error recopilando llm_usage: %s", e)
        metrics["llm_usage"]["error"] = str(e)

    # 2. Events: fallos de canal, webhooks, etc.
    try:
        stmt = text("""
            SELECT type, COUNT(*) as count
            FROM events
            WHERE created_at >= :since
            AND (type LIKE '%error%' OR type LIKE '%fail%' OR type LIKE '%timeout%')
            GROUP BY type
        """)
        result = await db.execute(stmt, {"since": since})
        metrics["events"]["errors"] = [
            {"type": r.type, "count": r.count} for r in result
        ]
    except Exception as e:
        logger.warning("Error recopilando events: %s", e)
        metrics["events"]["error"] = str(e)

    # 3. AuditLog: cambios de config, fallos de plan, etc.
    try:
        stmt = text("""
            SELECT action, COUNT(*) as count
            FROM audit_log
            WHERE created_at >= :since
            GROUP BY action
        """)
        result = await db.execute(stmt, {"since": since})
        metrics["audit"] = [
            {"action": r.action, "count": r.count} for r in result
        ]
    except Exception as e:
        logger.warning("Error recopilando audit_log: %s", e)
        metrics["audit"]["error"] = str(e)

    return metrics


def _build_guardian_prompt(metrics: dict[str, Any], current_config: dict[str, Any]) -> str:
    """Construye el prompt para el LLM guardián."""
    header = (
        "Eres el guardián de la infraestructura IA de una plataforma multi-tenant.\n"
        f"Analiza las métricas de los últimos {metrics['window_minutes']} minutos "
        "y decide si hay que cambiar de proveedor/modelo."
    )
    return f"""{header}

CONFIGURACIÓN ACTUAL:
{json.dumps(current_config, indent=2, ensure_ascii=False)}

PROVEEDORES DISPONIBLES (orden de preferencia):
{json.dumps(PROVIDER_CHAIN, indent=2, ensure_ascii=False)}

MÉTRICAS RECIENTES:
{json.dumps(metrics, indent=2, ensure_ascii=False)}

REGLAS DE DECISIÓN:
1. Si error_rate > 5% en un modelo/proveedor → considerar fallback al siguiente proveedor
2. Si avg_latency_ms > 10000 (10s) consistentemente → considerar modelo más rápido
3. Si hay timeouts repetidos en visión → cambiar LLM_MODEL_VISION a proveedor con visión estable
4. Si STT falla mucho → verificar STT_API_KEY / STT_BASE_URL
5. Si TTS falla y TTS_API_KEY vacío → OK (usa Edge TTS gratis)
6. NUNCA cambies a un proveedor sin API key configurada
7. Cambia UNA sola cosa a la vez para aislar causas
8. Prioridad: chat > intent > vision > stt > tts

RESPONDE SOLO EN JSON con esta estructura:
{{
  "should_act": true/false,
  "reason": "explicación breve",
  "actions": [
    {{"key": "LLM_BASE_URL", "value": "https://nuevo-proveedor.com/v1", "reason": "por qué"}},
    {{"key": "LLM_MODEL", "value": "nuevo-modelo", "reason": "por qué"}},
    ...
  ],
  "notify_superadmin": true/false,
  "notification_message": "mensaje para WhatsApp del superadmin (si notify_superadmin=true)"
}}"""


async def _call_guardian_llm(prompt: str) -> dict[str, Any] | None:
    """Llama al LLM guardián (usa config actual para no crear dependencia circular)."""
    try:
        from openai import AsyncOpenAI

        from app.core.config import get_settings
        
        settings = get_settings()
        if not settings.llm_api_key:
            logger.warning("Guardián: LLM_API_KEY no configurada, no se puede analizar")
            return None

        client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=30,
        )
        
        response = await client.chat.completions.create(
            model=settings.llm_model_intent or settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un sistema de monitoreo automático. "
                        "Responde SOLO en JSON válido."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        
        content = response.choices[0].message.content
        if content:
            return json.loads(content)
    except Exception as e:
        logger.exception("Error llamando al LLM guardián: %s", e)
    return None


async def _apply_actions(db: AsyncSession, actions: list[dict[str, str]]) -> list[str]:
    """Aplica las acciones decididas por el guardián."""
    applied = []
    for action in actions:
        key = action.get("key")
        value = action.get("value")
        if key and value:
            await ai_config_svc.set_ai_config(db, key, value)
            applied.append(f"{key}={value}")
            logger.info("Guardián aplicó: %s = %s (%s)", key, value, action.get("reason"))
    return applied


async def _notify_superadmin(message: str) -> None:
    """Envía notificación al superadmin por WhatsApp."""
    try:
        settings = get_settings()
        admin_wa = getattr(settings, "admin_support_wa_id", None)
        if not admin_wa:
            return
        
        channel = get_channel("evolution")
        await channel.send_text(admin_wa, f"🤖 *Guardián IA*\n{message}")
        logger.info("Notificación enviada al superadmin: %s", message[:100])
    except Exception as e:
        logger.warning("No se pudo notificar al superadmin: %s", e)


async def guardian_task(ctx: dict[str, Any]) -> dict[str, Any]:
    """Tarea principal del guardián (entrypoint ARQ)."""
    logger.info("🛡️ Guardián IA: iniciando chequeo de salud")
    
    from app.core.database import async_session_maker
    
    async with async_session_maker() as db:
        # 1. Recopilar métricas
        metrics = await _collect_health_metrics(db, window_minutes=15)
        
        # 2. Obtener config actual
        current_config = await ai_config_svc.get_all_ai_config(db)
        
        # 3. Pedir decisión al LLM guardián
        prompt = _build_guardian_prompt(metrics, current_config)
        decision = await _call_guardian_llm(prompt)
        
        if not decision:
            return {"status": "no_decision", "reason": "LLM guardián no respondió"}
        
        logger.info("Guardián decisión: %s", decision.get("reason", "sin razón"))
        
        # 4. Aplicar acciones si corresponde
        applied = []
        if decision.get("should_act") and decision.get("actions"):
            applied = await _apply_actions(db, decision["actions"])
            await ai_config_svc.refresh_ai_config_cache()
        
        # 5. Notificar al superadmin si corresponde
        if decision.get("notify_superadmin") and decision.get("notification_message"):
            await _notify_superadmin(decision["notification_message"])
        
        return {
            "status": "completed",
            "metrics_summary": {
                "llm_calls": len(metrics["llm_usage"].get("by_provider_model", [])),
                "event_errors": len(metrics["events"].get("errors", [])),
            },
            "decision": decision,
            "applied": applied,
        }


# ARQ cron job: se registra en worker/__init__.py
cron_job = {
    "cron": "*/10 * * * *",  # cada 10 minutos
    "func": "app.workers.guardian:guardian_task",
}