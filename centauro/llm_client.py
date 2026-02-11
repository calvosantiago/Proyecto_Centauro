import csv
import os
import datetime
import time
from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError, APIError
from .config import settings
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
GPT_TIMEOUT_SECONDS = 180  # Aumentado para transcripciones largas (diarización batch)
GPT_MAX_RETRIES = 2

# --- TARIFAS GPT-4o-mini (Actualizado Dic 2025) ---
# Precios por token (USD)
# Input: $0.15 por 1 millón
# Output: $0.60 por 1 millón
COST_PER_INPUT_TOKEN = 0.15 / 1_000_000
COST_PER_OUTPUT_TOKEN = 0.60 / 1_000_000

def registrar_gasto(referencia, uso):
    """
    Registra el consumo de tokens y el coste en un archivo CSV.
    Si el archivo no existe, lo crea con cabeceras.
    """
    archivo_csv = settings.OUTPUTS_DIR / "control_gastos.csv"
    archivo_existe = os.path.isfile(archivo_csv)
    
    # Extraer datos de uso
    tokens_in = uso.prompt_tokens
    tokens_out = uso.completion_tokens
    total_tokens = uso.total_tokens
    
    # Calcular coste
    coste_usd = (tokens_in * COST_PER_INPUT_TOKEN) + (tokens_out * COST_PER_OUTPUT_TOKEN)
    
    try:
        with open(archivo_csv, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Escribir cabecera si es nuevo
            if not archivo_existe:
                writer.writerow([
                    "Fecha", 
                    "Hora", 
                    "Archivo/Referencia", 
                    "Tokens Entrada (Prompt)", 
                    "Tokens Salida (Completion)", 
                    "Total Tokens", 
                    "Coste Estimado (USD)"
                ])
                
            # Escribir la línea de gasto
            writer.writerow([
                datetime.datetime.now().strftime("%d/%m/%Y"),
                datetime.datetime.now().strftime("%H:%M:%S"),
                referencia,
                tokens_in,
                tokens_out,
                total_tokens,
                f"{coste_usd:.6f}" # 6 decimales para ver los micro-centavos
            ])
    except Exception as e:
        print(f"⚠️ Aviso: No se pudo guardar el registro de gastos: {e}")

def obtener_embedding(texto):
    text = texto.replace("\n", " ")
    return client.embeddings.create(input=[text], model=settings.EMBEDDING_MODEL).data[0].embedding

def consultar_gpt(prompt_sistema, prompt_usuario, referencia_log="Desconocido", force_json=None):
    """
    Envía la consulta a OpenAI y registra el gasto asociado al archivo 'referencia_log'.

    Args:
        prompt_sistema: Prompt del sistema
        prompt_usuario: Prompt del usuario
        referencia_log: Referencia para el log de gastos
        force_json: Si True, fuerza JSON. Si False, texto libre. Si None, auto-detecta si el prompt pide JSON
    """
    # Auto-detectar si el prompt pide JSON (para compatibilidad con código existente)
    if force_json is None:
        # Si el prompt menciona "JSON" o "json", usar formato JSON
        prompt_completo = (prompt_sistema + " " + prompt_usuario).lower()
        force_json = "json" in prompt_completo

    # Configuración base
    kwargs = {
        "model": settings.MODEL_NAME,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario}
        ],
        "temperature": 0.0,
        "seed": 42
    }

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
        registrar_gasto(referencia_log, response.usage)
    # -------------------------------------

    return response.choices[0].message.content
