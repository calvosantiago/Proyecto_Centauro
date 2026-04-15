import csv
import os
import datetime
import time
from pathlib import Path
from typing import Any, Dict, List
from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError, APIError
from .config import settings
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
GPT_TIMEOUT_SECONDS = 180  # Aumentado para transcripciones largas (diarización batch)
GPT_MAX_RETRIES = 2

# --- TARIFAS OPENAI (Standard API, Mar 2026) ---
# gpt-4o-mini: input $0.15/M, cached input $0.075/M, output $0.60/M
# gpt-5-mini: input $0.25/M, cached input $0.025/M, output $2.00/M
# text-embedding-3-small: $0.02/M
#
# --- TARIFAS ASSEMBLYAI (Mar 2026) ---
# Universal-3 Pro (transcripción): $0.0001/seg
# Speaker Diarization (añadido):   $0.0001/seg
# Total con diarización:           $0.0002/seg = $0.012/min = $0.72/hora
MODEL_PRICING_USD_PER_1M = {
    "gpt-4o-mini": {
        "input": 0.15,
        "cached_input": 0.075,
        "output": 0.60,
    },
    "gpt-5-mini": {
        "input": 0.25,
        "cached_input": 0.025,
        "output": 2.00,
    },
}
COST_PER_EMBEDDING_TOKEN = 0.02 / 1_000_000

# Modelo por defecto para rutas no mapeadas
DEFAULT_CHAT_MODEL = settings.MODEL_NAME

# Enrutado por referencia_log: referencias críticas en gpt-5-mini
MODEL_BY_REFERENCE_EXACT = {
    "eval_investigacion": "gpt-5-mini",
    "eval_admision_economica": "gpt-5-mini",
    "eval_objeciones": "gpt-5-mini",
    "eval_cierre": "gpt-5-mini",
    "eval_propuesta_valor": "gpt-5-mini",
    "eval_estilo": "gpt-5-mini",
    "diar_batch": "gpt-4o-mini",
    "diar_classify": "gpt-4o-mini",
    "diar_timbrado": "gpt-4o-mini",
    "eval_deteccion": "gpt-4o-mini",
    "chat_interactivo": "gpt-4o-mini",
    "rag_temas": "gpt-4o-mini",
}


def _get_model_for_reference(referencia_log: str) -> str:
    """Resuelve el modelo de chat según la referencia del flujo."""
    ref = (referencia_log or "").strip()

    if ref in MODEL_BY_REFERENCE_EXACT:
        return MODEL_BY_REFERENCE_EXACT[ref]

    if ref.endswith("_batch_secundarios"):
        return "gpt-5-mini"

    if ref.endswith("_resumen_contextual"):
        return "gpt-4o-mini"

    return DEFAULT_CHAT_MODEL


def _get_token_costs_for_model(model_name: str):
    """Devuelve coste por token (input, cached_input, output) para el modelo."""
    pricing = MODEL_PRICING_USD_PER_1M.get(model_name) or MODEL_PRICING_USD_PER_1M.get(DEFAULT_CHAT_MODEL)
    return (
        pricing["input"] / 1_000_000,
        pricing["cached_input"] / 1_000_000,
        pricing["output"] / 1_000_000,
    )

CSV_COLUMNS = [
    "Timestamp",
    "Fecha",
    "Hora",
    "Usuario",
    "Archivo/Referencia",
    "Operacion",
    "Endpoint",
    "Modelo",
    "Prompt Tokens",
    "Prompt Tokens Cacheados",
    "Prompt Tokens No Cacheados",
    "Completion Tokens",
    "Embedding Tokens",
    "Total Tokens",
    "Coste Input (USD)",
    "Coste Input Cacheado (USD)",
    "Coste Output (USD)",
    "Coste Embedding (USD)",
    "Coste Total (USD)",
    "Request ID",
]

# Usuario activo en la sesión actual (se actualiza desde app.py al inicio de cada sesión)
_usuario_activo: str = "sistema"


def set_usuario_activo(username: str) -> None:
    """Registra el usuario autenticado activo para incluirlo en los logs de gasto."""
    global _usuario_activo
    _usuario_activo = username or "sistema"


def get_usuario_activo() -> str:
    return _usuario_activo


def _control_gastos_path() -> Path:
    return settings.OUTPUTS_DIR / "control_gastos.csv"


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _migrar_csv_legacy_si_hace_falta(archivo_csv: Path) -> None:
    if not archivo_csv.exists():
        return

    try:
        with open(archivo_csv, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
    except Exception:
        return

    if header == CSV_COLUMNS:
        return

    # Migrar formato legacy:
    # Fecha,Hora,Archivo/Referencia,Tokens Entrada (Prompt),Tokens Salida (Completion),Total Tokens,Coste Estimado (USD)
    legacy_rows: List[Dict[str, Any]] = []
    try:
        with open(archivo_csv, mode="r", newline="", encoding="utf-8") as f:
            dict_reader = csv.DictReader(f)
            for row in dict_reader:
                fecha = row.get("Fecha", "")
                hora = row.get("Hora", "")
                referencia = row.get("Archivo/Referencia", "Desconocido")
                prompt_tokens = _safe_int(row.get("Tokens Entrada (Prompt)", 0))
                completion_tokens = _safe_int(row.get("Tokens Salida (Completion)", 0))
                total_tokens = _safe_int(row.get("Total Tokens", prompt_tokens + completion_tokens))
                coste_total = _safe_float(row.get("Coste Estimado (USD)", 0.0))

                legacy_rows.append({
                    "Timestamp": "",
                    "Fecha": fecha,
                    "Hora": hora,
                    "Archivo/Referencia": referencia,
                    "Operacion": "chat_completion_legacy",
                    "Endpoint": "v1/chat/completions",
                    "Modelo": settings.MODEL_NAME,
                    "Prompt Tokens": prompt_tokens,
                    "Prompt Tokens Cacheados": "",
                    "Prompt Tokens No Cacheados": "",
                    "Completion Tokens": completion_tokens,
                    "Embedding Tokens": "",
                    "Total Tokens": total_tokens,
                    "Coste Input (USD)": "",
                    "Coste Input Cacheado (USD)": "",
                    "Coste Output (USD)": "",
                    "Coste Embedding (USD)": "",
                    "Coste Total (USD)": f"{coste_total:.6f}",
                    "Request ID": "",
                })
    except Exception as e:
        print(f"⚠️ Aviso: No se pudo migrar control_gastos.csv: {e}")
        return

    try:
        with open(archivo_csv, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            if legacy_rows:
                writer.writerows(legacy_rows)
    except Exception as e:
        print(f"⚠️ Aviso: No se pudo reescribir control_gastos.csv migrado: {e}")


def _append_cost_row(row: Dict[str, Any]) -> None:
    archivo_csv = _control_gastos_path()
    _migrar_csv_legacy_si_hace_falta(archivo_csv)

    if not archivo_csv.exists():
        with open(archivo_csv, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()

    with open(archivo_csv, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writerow(row)


def registrar_gasto_chat(
    referencia: str,
    uso: Any,
    model_name: str,
    request_id: str = "",
) -> None:
    """
    Registra el coste de una llamada chat.completions.
    """
    prompt_tokens = _safe_int(getattr(uso, "prompt_tokens", 0))
    completion_tokens = _safe_int(getattr(uso, "completion_tokens", 0))
    total_tokens = _safe_int(getattr(uso, "total_tokens", prompt_tokens + completion_tokens))

    prompt_details = getattr(uso, "prompt_tokens_details", None)
    cached_tokens = _safe_int(getattr(prompt_details, "cached_tokens", 0))
    non_cached_prompt_tokens = max(prompt_tokens - cached_tokens, 0)

    cost_per_input, cost_per_cached_input, cost_per_output = _get_token_costs_for_model(model_name)
    cost_input = non_cached_prompt_tokens * cost_per_input
    cost_input_cached = cached_tokens * cost_per_cached_input
    cost_output = completion_tokens * cost_per_output
    cost_total = cost_input + cost_input_cached + cost_output

    now = datetime.datetime.now()
    row = {
        "Timestamp": now.isoformat(timespec="seconds"),
        "Fecha": now.strftime("%Y-%m-%d"),
        "Hora": now.strftime("%H:%M:%S"),
        "Usuario": _usuario_activo,
        "Archivo/Referencia": referencia,
        "Operacion": "chat_completion",
        "Endpoint": "v1/chat/completions",
        "Modelo": model_name,
        "Prompt Tokens": prompt_tokens,
        "Prompt Tokens Cacheados": cached_tokens,
        "Prompt Tokens No Cacheados": non_cached_prompt_tokens,
        "Completion Tokens": completion_tokens,
        "Embedding Tokens": "",
        "Total Tokens": total_tokens,
        "Coste Input (USD)": f"{cost_input:.6f}",
        "Coste Input Cacheado (USD)": f"{cost_input_cached:.6f}",
        "Coste Output (USD)": f"{cost_output:.6f}",
        "Coste Embedding (USD)": "",
        "Coste Total (USD)": f"{cost_total:.6f}",
        "Request ID": request_id or "",
    }

    try:
        _append_cost_row(row)
    except Exception as e:
        print(f"⚠️ Aviso: No se pudo guardar el registro de gastos (chat): {e}")


def registrar_gasto_embedding(
    referencia: str,
    total_tokens: int,
    model_name: str,
    request_id: str = "",
) -> None:
    """
    Registra el coste de una llamada de embeddings.
    """
    embedding_tokens = _safe_int(total_tokens)
    cost_embedding = embedding_tokens * COST_PER_EMBEDDING_TOKEN

    now = datetime.datetime.now()
    row = {
        "Timestamp": now.isoformat(timespec="seconds"),
        "Fecha": now.strftime("%Y-%m-%d"),
        "Hora": now.strftime("%H:%M:%S"),
        "Usuario": _usuario_activo,
        "Archivo/Referencia": referencia,
        "Operacion": "embedding",
        "Endpoint": "v1/embeddings",
        "Modelo": model_name,
        "Prompt Tokens": "",
        "Prompt Tokens Cacheados": "",
        "Prompt Tokens No Cacheados": "",
        "Completion Tokens": "",
        "Embedding Tokens": embedding_tokens,
        "Total Tokens": embedding_tokens,
        "Coste Input (USD)": "",
        "Coste Input Cacheado (USD)": "",
        "Coste Output (USD)": "",
        "Coste Embedding (USD)": f"{cost_embedding:.6f}",
        "Coste Total (USD)": f"{cost_embedding:.6f}",
        "Request ID": request_id or "",
    }

    try:
        _append_cost_row(row)
    except Exception as e:
        print(f"⚠️ Aviso: No se pudo guardar el registro de gastos (embedding): {e}")


def obtener_embedding(texto):
    text = texto.replace("\n", " ")
    resp = client.embeddings.create(input=[text], model=settings.MODELO_EMBEDDING)
    if resp.usage:
        registrar_gasto_embedding(
            referencia="embedding_directo_llm_client",
            total_tokens=getattr(resp.usage, "total_tokens", 0),
            model_name=settings.MODELO_EMBEDDING,
            request_id=getattr(resp, "id", ""),
        )
    return resp.data[0].embedding

def _log_prompt_debug(referencia_log: str, prompt_sistema: str, prompt_usuario: str, respuesta: str = None):
    """Guarda prompts y respuestas en archivo de debug si CENTAURO_DEBUG_PROMPTS está activo."""
    if not os.environ.get("CENTAURO_DEBUG_PROMPTS"):
        return
    try:
        debug_dir = Path("debug_prompts")
        debug_dir.mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = debug_dir / f"{timestamp}_{referencia_log}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"{'='*80}\n")
            f.write(f"REFERENCIA: {referencia_log}\n")
            f.write(f"TIMESTAMP: {timestamp}\n")
            f.write(f"{'='*80}\n\n")
            f.write(f"--- PROMPT SISTEMA ({len(prompt_sistema)} chars) ---\n")
            f.write(prompt_sistema)
            f.write(f"\n\n--- PROMPT USUARIO ({len(prompt_usuario)} chars) ---\n")
            f.write(prompt_usuario)
            if respuesta:
                f.write(f"\n\n--- RESPUESTA ({len(respuesta)} chars) ---\n")
                f.write(respuesta)
        print(f"  [DEBUG] Prompt guardado: {filename}")
    except Exception as e:
        print(f"  [DEBUG] Error guardando prompt: {e}")


def consultar_gpt(prompt_sistema, prompt_usuario, referencia_log="Desconocido", force_json=None, max_tokens=None):
    """
    Envía la consulta a OpenAI y registra el gasto asociado al archivo 'referencia_log'.

    Args:
        prompt_sistema: Prompt del sistema
        prompt_usuario: Prompt del usuario
        referencia_log: Referencia para el log de gastos
        force_json: Si True, fuerza JSON. Si False, texto libre. Si None, auto-detecta si el prompt pide JSON
        max_tokens: Límite explícito de tokens de salida. Si None, usa el default del modelo.
                    Recomendado para evaluaciones con JSON estructurado: 2500-3000.
    """
    # Auto-detectar si el prompt pide JSON (para compatibilidad con código existente)
    if force_json is None:
        # Si el prompt menciona "JSON" o "json", usar formato JSON
        prompt_completo = (prompt_sistema + " " + prompt_usuario).lower()
        force_json = "json" in prompt_completo

    model_name = _get_model_for_reference(referencia_log)

    # Modelos de razonamiento no soportan temperature ni seed
    REASONING_MODELS = {"o1", "o1-mini", "o1-preview", "o3", "o3-mini", "gpt-5-mini"}

    # Configuración base
    kwargs = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario}
        ],
    }

    # Solo añadir temperature y seed para modelos que los soporten
    if model_name not in REASONING_MODELS:
        kwargs["temperature"] = 0.0
        kwargs["seed"] = 42

    # max_tokens explícito (evita truncamiento de respuestas JSON largas).
    # Los modelos de razonamiento (o-series, gpt-5-mini) usan max_completion_tokens;
    # los modelos estándar usan max_tokens.
    if max_tokens is not None:
        if model_name in REASONING_MODELS:
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

    # Agregar response_format solo si se necesita JSON
    if force_json:
        kwargs["response_format"] = {"type": "json_object"}

    response = None
    ultimo_error = None

    for intento in range(1, GPT_MAX_RETRIES + 2):
        try:
            response = client.chat.completions.create(
                **kwargs,
                timeout=GPT_TIMEOUT_SECONDS
            )
            break
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            ultimo_error = e
            if intento > GPT_MAX_RETRIES:
                break

            espera = min(2 ** (intento - 1), 8)
            print(
                f"⚠️ GPT intento {intento}/{GPT_MAX_RETRIES + 1} falló ({type(e).__name__}). "
                f"Reintentando en {espera}s..."
            )
            time.sleep(espera)
        except APIError as e:
            ultimo_error = e
            # Errores de API no transitorios: cortar directamente
            break

    if response is None:
        raise RuntimeError(
            f"Fallo al consultar GPT tras {GPT_MAX_RETRIES + 1} intentos: {ultimo_error}"
        )

    # --- REGISTRO AUTOMÁTICO DE GASTOS ---
    if response.usage:
        registrar_gasto_chat(
            referencia=referencia_log,
            uso=response.usage,
            model_name=model_name,
            request_id=getattr(response, "id", ""),
        )
    # -------------------------------------

    resultado = response.choices[0].message.content

    # Los reasoning models (gpt-5-mini, o-series) pueden devolver content=None si
    # max_completion_tokens se agotó en el thinking antes de generar la respuesta.
    if resultado is None:
        finish_reason = getattr(response.choices[0], "finish_reason", "unknown")
        raise RuntimeError(
            f"El modelo ({model_name}) devolvió content=None "
            f"[finish_reason={finish_reason}]. "
            f"Posible causa: max_completion_tokens insuficiente para reasoning + respuesta."
        )

    # Log de debug con respuesta incluida
    _log_prompt_debug(referencia_log, prompt_sistema, prompt_usuario, resultado)

    return resultado
