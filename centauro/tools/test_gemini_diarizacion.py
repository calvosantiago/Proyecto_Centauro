"""
test_gemini_diarizacion.py — Prueba comparativa: transcripción + diarización con Gemini
(rama gemini_pruebas, exploración de alternativas a AssemblyAI).

Extrae el audio de un video/audio con ffmpeg (mismo comando que extract_audio.py) y lo
envía a Gemini pidiendo transcripción con identificación de interlocutores por voz.
Guarda el resultado en outputs/transcripciones_cache/gemini_comparacion/ para comparar
manualmente contra el .txt ya cacheado de AssemblyAI del mismo archivo.

No sustituye nada del flujo de producción — es solo para evaluar calidad antes de decidir
si vale la pena integrarlo.

Uso:
    python centauro/tools/test_gemini_diarizacion.py "ruta/al/video.mp4" [otro.mp4 ...]
    python centauro/tools/test_gemini_diarizacion.py "ruta/al/video.mp4" --clip 20
        (--clip N transcribe solo los primeros N segundos, para pruebas rápidas)
"""
import os
import sys
import time
import tempfile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from google import genai
from google.genai import types as genai_types
from google.genai.errors import ServerError as GeminiServerError

from centauro.tools.extract_audio import FFMPEG_PATH

MAX_RETRIES = 4  # el modelo 3.6-flash a veces devuelve 503 "high demand"

SALIDA_DIR = ROOT / "outputs" / "transcripciones_cache" / "gemini_comparacion"
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov"}

PROMPT = (
    "Transcribe este audio completo en español, palabra por palabra, tal como se escucha "
    "(incluye muletillas, repeticiones y errores de pronunciación del hablante, no los corrijas). "
    "Identifica a los distintos interlocutores por su voz, no por el contenido de lo que dicen, "
    "y etiqueta cada intervención como [Hablante_A]: o [Hablante_B]: de forma consistente durante "
    "todo el audio (la misma persona debe mantener siempre la misma etiqueta). "
    "No resumas ni omitas ninguna parte."
)


def extraer_audio_mp3(video_path: Path, clip_seg: int = None) -> Path:
    salida = Path(tempfile.gettempdir()) / f"gemini_test_{video_path.stem}.mp3"
    comando = [str(FFMPEG_PATH), "-i", str(video_path)]
    if clip_seg:
        comando += ["-t", str(clip_seg)]
    comando += [
        "-vn", "-c:a", "libmp3lame", "-b:a", "32k", "-ac", "1", "-ar", "16000",
        "-y", str(salida),
    ]
    resultado = subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg fallo en {video_path.name}:\n{resultado.stderr[-800:]}")
    return salida


def transcribir_con_gemini(audio_path: Path) -> str:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    audio_bytes = audio_path.read_bytes()
    parte_audio = genai_types.Part.from_bytes(data=audio_bytes, mime_type="audio/mp3")

    response = None
    ultimo_error = None
    for intento in range(1, MAX_RETRIES + 2):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=[parte_audio, PROMPT],
                config=genai_types.GenerateContentConfig(temperature=0.0),
            )
            break
        except GeminiServerError as e:
            ultimo_error = e
            if intento > MAX_RETRIES:
                break
            espera = min(5 * intento, 30)
            print(f"  AVISO: intento {intento}/{MAX_RETRIES + 1} fallo (503). Reintentando en {espera}s...")
            time.sleep(espera)

    if response is None:
        raise RuntimeError(f"Fallo tras {MAX_RETRIES + 1} intentos: {ultimo_error}")

    if not response.text:
        candidatos = getattr(response, "candidates", None) or []
        finish_reason = getattr(candidatos[0], "finish_reason", "unknown") if candidatos else "unknown"
        raise RuntimeError(f"Gemini devolvio texto vacio [finish_reason={finish_reason}]")
    return response.text


def main():
    args = sys.argv[1:]
    clip_seg = None
    if "--clip" in args:
        idx = args.index("--clip")
        clip_seg = int(args[idx + 1])
        del args[idx:idx + 2]

    if not args:
        print("Uso: python test_gemini_diarizacion.py <archivo1> [archivo2 ...] [--clip N]")
        sys.exit(1)

    SALIDA_DIR.mkdir(parents=True, exist_ok=True)

    for arg in args:
        video_path = Path(arg)
        if not video_path.exists():
            print(f"AVISO: no encontrado: {video_path}")
            continue

        print(f"\n=== {video_path.name} ===")
        if video_path.suffix.lower() in VIDEO_EXTENSIONS:
            print("Extrayendo audio con ffmpeg...")
            audio_path = extraer_audio_mp3(video_path, clip_seg=clip_seg)
        else:
            audio_path = video_path

        tam_mb = audio_path.stat().st_size / 1024 / 1024
        print(f"Audio: {audio_path.name} ({tam_mb:.1f} MB)")
        if tam_mb > 19:
            print("AVISO: archivo >19MB, podria fallar el envio inline (limite ~20MB de Gemini).")

        print("Enviando a Gemini (gemini-3.6-flash)...")
        try:
            texto = transcribir_con_gemini(audio_path)
        except Exception as e:
            print(f"ERROR transcribiendo {video_path.name}: {e}")
            continue

        nombre_corto = video_path.stem[:60].strip()
        salida = SALIDA_DIR / f"{nombre_corto}_gemini.txt"
        salida.write_text(texto, encoding="utf-8")
        print(f"Guardado: {salida} ({len(texto)} caracteres)")


if __name__ == "__main__":
    main()
