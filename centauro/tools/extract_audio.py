"""
extract_audio.py — Extracción de audio MP3 desde videollamadas

Busca todos los vídeos (.mp4, .mkv, .webm, .mov) en inputs/videollamadas/,
extrae el audio como MP3 con ffmpeg y guarda el resultado en inputs/audios/.

Requiere ffmpeg instalado en C:/ffmpeg/bin/ffmpeg.exe

Uso:
    python centauro/tools/extract_audio.py
"""

import os
import sys
import subprocess
from pathlib import Path

# Asegurar que el raíz del proyecto esté en el path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
VIDEOS_DIR    = ROOT / "inputs" / "videollamadas"
AUDIOS_DIR    = ROOT / "inputs" / "audios"
FFMPEG_PATH   = Path(r"C:\ffmpeg\bin\ffmpeg.exe")

# Extensiones de vídeo soportadas
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ffmpeg_disponible() -> bool:
    """Comprueba que ffmpeg existe y es ejecutable."""
    if not FFMPEG_PATH.exists():
        print(f"❌ No se encontró ffmpeg en: {FFMPEG_PATH}")
        print("   Instálalo desde https://ffmpeg.org/download.html")
        return False
    return True


def extraer_audio(video_path: Path) -> bool:
    """
    Extrae el audio de un vídeo y lo guarda como MP3 en inputs/audios/.
    Devuelve True si se completó correctamente, False si hubo error.
    """
    nombre_salida = video_path.stem + ".mp3"
    salida_mp3 = AUDIOS_DIR / nombre_salida

    if salida_mp3.exists():
        print(f"  ⏭️  Ya existe {salida_mp3.name}, saltando.")
        return True

    print(f"  🎬 Extrayendo audio de: {video_path.name}")

    comando = [
        str(FFMPEG_PATH),
        "-i", str(video_path),   # input
        "-vn",                    # sin vídeo
        "-c:a", "libmp3lame",    # codec MP3
        "-q:a", "2",             # calidad alta (0=mejor, 9=peor)
        "-y",                    # sobreescribir sin preguntar
        str(salida_mp3),
    ]

    try:
        resultado = subprocess.run(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if resultado.returncode == 0:
            tamanyo_mb = salida_mp3.stat().st_size / 1024 / 1024
            print(f"  ✅ Guardado: {salida_mp3.name} ({tamanyo_mb:.1f} MB)")
            return True
        else:
            print(f"  ❌ Error al procesar {video_path.name}:")
            # Mostrar solo las últimas líneas del error de ffmpeg (suelen ser las relevantes)
            lineas_error = [l for l in resultado.stderr.splitlines() if l.strip()]
            for linea in lineas_error[-5:]:
                print(f"     {linea}")
            return False

    except Exception as e:
        print(f"  ❌ Excepción al ejecutar ffmpeg: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not _ffmpeg_disponible():
        sys.exit(1)

    # Buscar todos los vídeos en la carpeta
    videos = []
    for ext in VIDEO_EXTENSIONS:
        videos.extend(VIDEOS_DIR.glob(f"*{ext}"))
        videos.extend(VIDEOS_DIR.glob(f"*{ext.upper()}"))
    videos = sorted(set(videos))

    if not videos:
        print(f"\n⚠️  No se encontraron vídeos en {VIDEOS_DIR}")
        print(f"   Formatos soportados: {', '.join(VIDEO_EXTENSIONS)}")
        sys.exit(0)

    AUDIOS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n🎬 Extract Audio — {len(videos)} vídeo(s) encontrado(s)\n")

    completados = 0
    fallidos = 0
    for video in videos:
        ok = extraer_audio(video)
        if ok:
            completados += 1
        else:
            fallidos += 1

    print(f"\n{'='*50}")
    print(f"✅ Completados: {completados} | ❌ Fallidos: {fallidos}")
    print(f"   Los MP3 están en: {AUDIOS_DIR}")
    if completados > 0:
        print(f"\nAhora puedes ejecutar whisper_transcribe.py para transcribirlos.")


if __name__ == "__main__":
    main()
