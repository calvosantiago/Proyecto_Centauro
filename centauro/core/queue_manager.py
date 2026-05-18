"""
Cola de análisis — evita colisiones de rate limit cuando múltiples jefes analizan en simultáneo.

Solo un análisis LLM pesado corre a la vez; los demás esperan en cola con su posición
y tiempo estimado visibles. Cuando llega su turno, el análisis arranca automáticamente.

Dos APIs disponibles:

  1. Nivel alto (recomendado para código nuevo):

        from centauro.core.queue_manager import ejecutar_con_cola

        async def _run():
            # ... análisis pesado ...

        await ejecutar_con_cola(_run)

  2. Nivel bajo (para integrar en código existente sin refactorizar):

        from centauro.core.queue_manager import adquirir_slot

        liberar = await adquirir_slot()
        try:
            # ... análisis pesado (código existente sin cambios) ...
        finally:
            liberar()
"""

import asyncio
import uuid
import logging
import time
from typing import Callable, Awaitable, Any

logger = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────
MINUTOS_POR_ANALISIS: float = 3.5  # estimación de duración de un análisis típico
MAX_CONCURRENT: int = 1            # análisis pesados simultáneos permitidos

# ── Estado global (único por proceso, compartido entre sesiones Chainlit) ──────
_semaphore: asyncio.Semaphore | None = None
_waiting: list[dict] = []  # [{"id": str, "cl_ctx": ctx, "status_msg": cl.Message}]


def _get_semaphore() -> asyncio.Semaphore:
    """Crea el semáforo la primera vez dentro de un event loop activo."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    return _semaphore


# ── Helpers de mensajería ─────────────────────────────────────────────────────

def _posicion_texto(pos: int, espera_min: float) -> str:
    if espera_min < 1:
        espera_str = "menos de 1 minuto"
    elif espera_min < 2:
        espera_str = "~1 minuto"
    else:
        espera_str = f"~{espera_min:.0f} minutos"

    return (
        f"🕐 **Tu análisis está en cola** — posición **{pos}**\n"
        f"⏱️ Tiempo estimado de espera: **{espera_str}**\n\n"
        f"_El análisis comenzará automáticamente cuando llegue tu turno. "
        f"Puedes seguir usando el chat mientras esperas._"
    )


async def _actualizar_msg(w: dict, content: str) -> None:
    """Actualiza el mensaje de posición de un usuario que está esperando.

    Cambia temporalmente el context var de Chainlit al de ese usuario para que
    el mensaje llegue a su sesión y no a la del análisis en curso.
    """
    try:
        from chainlit.context import context_var
        token = context_var.set(w["cl_ctx"])
        try:
            w["status_msg"].content = content
            await w["status_msg"].update()
        finally:
            context_var.reset(token)
    except Exception as exc:
        logger.debug("No se pudo actualizar mensaje de cola para %s: %s", w["id"], exc)


# ── API nivel bajo ────────────────────────────────────────────────────────────

async def adquirir_slot() -> Callable[[], None]:
    """Encola este análisis, muestra posición al usuario y espera su turno.

    Devuelve una función de liberación que DEBE llamarse en un bloque finally
    cuando el análisis termine (con éxito o con error).

    Ejemplo de uso en código existente sin refactorizar:

        liberar = await adquirir_slot()
        try:
            # ... análisis pesado existente ...
        finally:
            liberar()

    Returns:
        Callable sincrónico sin argumentos que libera el slot.
    """
    import chainlit as cl
    from chainlit.context import context_var

    sem = _get_semaphore()
    item_id = str(uuid.uuid4())
    cl_ctx = context_var.get()

    item: dict = {"id": item_id, "cl_ctx": cl_ctx, "status_msg": None}
    _waiting.append(item)

    pos = len(_waiting)
    hay_espera = pos > 1 or sem.locked()

    if hay_espera:
        espera_min = pos * MINUTOS_POR_ANALISIS
        status_msg = await cl.Message(content=_posicion_texto(pos, espera_min)).send()
    else:
        # Semáforo probablemente libre — mensaje neutro que actualizamos si hay espera
        status_msg = await cl.Message(content="⏳ Preparando análisis...").send()

    item["status_msg"] = status_msg

    # Esperar turno (bloquea hasta que el semáforo esté libre)
    try:
        await sem.acquire()
    except asyncio.CancelledError:
        # El usuario cerró la sesión antes de que llegara su turno
        _waiting[:] = [w for w in _waiting if w["id"] != item_id]
        raise

    # ── Es nuestro turno ──────────────────────────────────────────────────────
    _waiting[:] = [w for w in _waiting if w["id"] != item_id]

    # Actualizar posiciones de los que siguen esperando
    for i, w in enumerate(_waiting):
        espera_restante = (i + 1) * MINUTOS_POR_ANALISIS
        await _actualizar_msg(w, _posicion_texto(i + 1, espera_restante))

    # Notificar al usuario actual
    status_msg.content = "🚀 **¡Es tu turno!** El análisis está comenzando ahora..."
    await status_msg.update()
    await asyncio.sleep(0.4)  # pausa corta para que el mensaje sea legible

    def _liberar() -> None:
        try:
            sem.release()
        except Exception as exc:
            logger.warning("Error al liberar slot de análisis: %s", exc)

    return _liberar


# ── API nivel alto ────────────────────────────────────────────────────────────

async def ejecutar_con_cola(run_fn: Callable[[], Awaitable[Any]]) -> Any:
    """Encola un análisis y lo ejecuta cuando hay slot libre.

    Versión de alto nivel que gestiona automáticamente la adquisición y
    liberación del slot. Úsala para código nuevo o si puedes extraer el
    análisis en una función/closure.

    Args:
        run_fn: Coroutine function sin argumentos con el análisis a ejecutar.

    Returns:
        El valor de retorno de run_fn.
    """
    liberar = await adquirir_slot()
    try:
        return await run_fn()
    finally:
        liberar()
