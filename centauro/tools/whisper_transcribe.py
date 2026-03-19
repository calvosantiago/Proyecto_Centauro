"""
whisper_transcribe.py — Transcripción de audios con Groq Whisper

Busca todos los .mp3 en inputs/audios/, los transcribe con whisper-large-v3-turbo
via Groq API y guarda el resultado como .txt en inputs/transcripts/ con sufijo _whisper.

El DiarizationAgent se encarga de separar ASESOR/LEAD por contenido via LLM.

Uso:
    python centauro/tools/whisper_transcribe.py

El gasto se registra en outputs/control_gastos.csv igual que el resto del sistema.
"""

import os
import sys
import csv
import re
import time
import datetime
from pathlib import Path
from mutagen.mp3 import MP3  # pip install mutagen

# Asegurar que el raíz del proyecto esté en el path para importar centauro
# centauro/tools/ → centauro/ → raíz
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from groq import Groq
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
AUDIOS_DIR = ROOT / "inputs" / "audios"
TRANSCRIPTS_DIR = ROOT / "inputs" / "transcripts"
CONTROL_GASTOS_CSV = ROOT / "outputs" / "control_gastos.csv"

WHISPER_MODEL = "whisper-large-v3-turbo"

# Tarifa Groq Whisper Large v3 Turbo: $0.04 USD por hora de audio (Feb 2026)
# https://groq.com/pricing → Speech → whisper-large-v3-turbo
WHISPER_COST_PER_HOUR = 0.04
WHISPER_COST_PER_MINUTE = WHISPER_COST_PER_HOUR / 60  # ~$0.000667/min

# Columnas del CSV de gastos (deben coincidir con llm_client.CSV_COLUMNS)
CSV_COLUMNS = [
    "Timestamp",
    "Fecha",
    "Hora",
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_audio_duration_minutes(audio_path: Path) -> float:
    """Devuelve la duración del MP3 en minutos."""
    try:
        audio = MP3(str(audio_path))
        return audio.info.length / 60.0
    except Exception as e:
        print(f"  ⚠️  No se pudo leer la duración de {audio_path.name}: {e}")
        return 0.0


def _append_cost_row(row: dict) -> None:
    """Añade una fila al CSV de control de gastos, creando cabecera si no existe."""
    write_header = not CONTROL_GASTOS_CSV.exists()
    with open(CONTROL_GASTOS_CSV, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def registrar_gasto_whisper(
    referencia: str,
    duracion_minutos: float,
    request_id: str = "",
) -> None:
    """Registra el coste de una transcripción Groq Whisper en control_gastos.csv."""
    coste = duracion_minutos * WHISPER_COST_PER_MINUTE

    now = datetime.datetime.now()
    row = {
        "Timestamp": now.isoformat(timespec="seconds"),
        "Fecha": now.strftime("%Y-%m-%d"),
        "Hora": now.strftime("%H:%M:%S"),
        "Archivo/Referencia": referencia,
        "Operacion": "transcripcion_groq_whisper",
        "Endpoint": "openai/v1/audio/transcriptions",
        "Modelo": WHISPER_MODEL,
        "Prompt Tokens": "",
        "Prompt Tokens Cacheados": "",
        "Prompt Tokens No Cacheados": "",
        "Completion Tokens": "",
        "Embedding Tokens": "",
        "Total Tokens": "",
        "Coste Input (USD)": "",
        "Coste Input Cacheado (USD)": "",
        "Coste Output (USD)": "",
        "Coste Embedding (USD)": "",
        "Coste Total (USD)": f"{coste:.6f}",
        "Request ID": request_id or "",
    }

    try:
        _append_cost_row(row)
        print(f"  💰 Gasto registrado: {duracion_minutos:.1f} min × ${WHISPER_COST_PER_MINUTE:.6f} = ${coste:.4f}")
    except Exception as e:
        print(f"  ⚠️  No se pudo guardar el registro de gastos: {e}")


def texto_de_segmentos(segmentos: list) -> str:
    """
    Construye texto plano a partir de los segmentos devueltos por Groq Whisper
    (verbose_json). Sin etiquetas de speaker para que el DiarizationAgent
    pueda diarizar por contenido usando LLM.
    """
    lineas = []
    for seg in segmentos:
        # Groq devuelve segmentos como dict, OpenAI como objeto con atributos
        texto = (seg["text"] if isinstance(seg, dict) else seg.text).strip()
        if texto:
            lineas.append(texto)
    return " ".join(lineas)


def segmentos_a_texto_timbrado(segmentos: list) -> str:
    """
    Construye texto con timestamps de segmento para diarización mejorada.

    Formato de salida:
        [0.0s-4.2s] Hola buenas tardes, soy María de OBS...
        [4.8s-6.1s] Hola, sí te escucho.
        [6.5s-15.3s] Perfecto, te llamo porque...

    Las pausas entre segmentos son la señal acústica clave para detectar
    cambios de hablante sin necesidad de un modelo de diarización dedicado.
    Si no hay segmentos disponibles, devuelve cadena vacía.
    """
    if not segmentos:
        return ""
    lineas = []
    for seg in segmentos:
        if isinstance(seg, dict):
            inicio = seg.get("start", 0.0)
            fin = seg.get("end", 0.0)
            texto = seg.get("text", "").strip()
        else:
            inicio = getattr(seg, "start", 0.0)
            fin = getattr(seg, "end", 0.0)
            texto = getattr(seg, "text", "").strip()
        if texto:
            lineas.append(f"[{inicio:.1f}s-{fin:.1f}s] {texto}")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def _extraer_segundos_espera(mensaje_error: str) -> int:
    """
    Extrae los segundos de espera del mensaje de rate limit de Groq.
    Ejemplo: 'Please try again in 9m29.5s' → 569 segundos.
    Si no puede extraerlo, devuelve 60 como fallback.
    """
    # Buscar patrón "Xm Y.Zs" o solo "Xs"
    match = re.search(r'(\d+)m(\d+(?:\.\d+)?)s', mensaje_error)
    if match:
        minutos = int(match.group(1))
        segundos = float(match.group(2))
        return int(minutos * 60 + segundos) + 5  # +5 seg de margen
    match = re.search(r'(\d+(?:\.\d+)?)s', mensaje_error)
    if match:
        return int(float(match.group(1))) + 5
    return 60  # fallback


def transcribir_audio(client: Groq, audio_path: Path, max_reintentos: int = 3) -> None:
    nombre_base = audio_path.stem  # e.g. "Esther_Lopez"
    nombre_limpio = nombre_base.replace("_", " ")  # e.g. "Esther Lopez"
    salida_txt = TRANSCRIPTS_DIR / f"{nombre_limpio}_whisper.txt"

    if salida_txt.exists():
        print(f"  ⏭️  Ya existe {salida_txt.name}, saltando.")
        return

    duracion_min = _get_audio_duration_minutes(audio_path)
    print(f"  🎙️  Transcribiendo: {audio_path.name}  ({duracion_min:.1f} min)")

    for intento in range(1, max_reintentos + 1):
        try:
            with open(audio_path, "rb") as f:
                response = client.audio.transcriptions.create(
                    model=WHISPER_MODEL,
                    file=f,
                    response_format="verbose_json",
                    language="es",
                )
            break  # Éxito, salir del bucle de reintentos

        except Exception as e:
            mensaje = str(e)
            if "429" in mensaje or "rate_limit" in mensaje.lower():
                espera = _extraer_segundos_espera(mensaje)
                minutos_espera = espera // 60
                segundos_espera = espera % 60
                print(f"  ⏳ Rate limit alcanzado (intento {intento}/{max_reintentos}). "
                      f"Esperando {minutos_espera}m {segundos_espera}s...")
                # Cuenta atrás visible cada 30 segundos
                transcurridos = 0
                while transcurridos < espera:
                    time.sleep(min(30, espera - transcurridos))
                    transcurridos += 30
                    restantes = max(0, espera - transcurridos)
                    if restantes > 0:
                        print(f"     ⏳ Quedan ~{restantes // 60}m {restantes % 60}s...")
                print(f"  🔄 Reintentando {audio_path.name}...")
            else:
                raise  # Error distinto al rate limit, relanzar

    else:
        print(f"  ❌ No se pudo transcribir {audio_path.name} tras {max_reintentos} intentos.")
        return

    # Extraer segmentos y construir texto plano (sin speaker tags)
    # El DiarizationAgent se encarga de separar ASESOR/LEAD por contenido via LLM
    segmentos = getattr(response, "segments", [])
    contenido_txt = texto_de_segmentos(segmentos)

    # Fallback: si Groq no devuelve segmentos, usar el texto completo directamente
    if not contenido_txt:
        contenido_txt = getattr(response, "text", "").strip()
        if contenido_txt:
            print(f"  ℹ️  Segmentos no disponibles, usando texto completo")

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    salida_txt.write_text(contenido_txt, encoding="utf-8")
    print(f"  ✅  Guardado: {salida_txt.name}")

    # Registrar gasto
    request_id = getattr(response, "id", "")
    registrar_gasto_whisper(
        referencia=audio_path.name,
        duracion_minutos=duracion_min,
        request_id=request_id,
    )


def main() -> None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("❌ No se encontró GROQ_API_KEY en el entorno / .env")
        print("   Añade GROQ_API_KEY=gsk_... a tu archivo .env")
        sys.exit(1)

    client = Groq(api_key=api_key)

    audios = sorted(AUDIOS_DIR.glob("*.mp3"))
    if not audios:
        print(f"No se encontraron archivos .mp3 en {AUDIOS_DIR}")
        sys.exit(0)

    print(f"\n🎧 Groq Whisper Transcriber — {len(audios)} audio(s) encontrado(s)\n")
    for audio in audios:
        transcribir_audio(client, audio)

    print("\n✅ Transcripciones completadas.")
    print(f"   Los archivos _whisper.txt están en: {TRANSCRIPTS_DIR}")
    print(f"   Los gastos se registraron en:       {CONTROL_GASTOS_CSV}")
    print("\nAhora puedes ejecutar main.py normalmente para analizar estas transcripciones.")


if __name__ == "__main__":
    main()
