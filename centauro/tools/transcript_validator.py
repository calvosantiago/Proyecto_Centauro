"""
transcript_validator.py — Validador de calidad de transcripciones

Evalúa si una transcripción tiene suficiente calidad para ser analizada
por el sistema multi-agente. Si no la tiene, activa el plan B (Groq Whisper).

Señales evaluadas (sin LLM, sin coste):
  1. Densidad de palabras: muy pocas palabras para la duración estimada
  2. Ratio de puntuación: texto sin signos = posible corrupción
  3. Palabras ininteligibles: "inaudible", "xxx", "[música]", etc.
  4. Encoding roto: caracteres corruptos típicos de UTF-8 mal leído
  5. Idioma incorrecto: si no hay palabras españolas frecuentes
  6. Texto vacío o mínimo: menos de 100 palabras en total

Uso directo:
    python centauro/tools/transcript_validator.py
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Configuración de umbrales
# ---------------------------------------------------------------------------

# Mínimo de palabras para considerar una transcripción válida
MIN_PALABRAS = 150

# Mínimo de palabras por minuto estimado en una conversación normal
# Una conversación de ventas suele tener 100-150 ppm. Usamos 40 como mínimo
# para ser tolerantes con silencios, pausas largas, etc.
MIN_PALABRAS_POR_MINUTO = 40

# Máximo porcentaje de "palabras basura" permitido
MAX_RATIO_BASURA = 0.08  # 8%

# Máximo porcentaje de caracteres corruptos permitido
MAX_RATIO_CARACTERES_CORRUPTOS = 0.02  # 2%

# Mínimo de palabras españolas frecuentes sobre el total de palabras cortas
MIN_RATIO_ESPANOL = 0.05  # 5% del texto debe contener palabras españolas frecuentes

# Palabras y patrones que indican audio ininteligible
PALABRAS_BASURA = [
    r'\binaudible\b',
    r'\bincorrecto\b',
    r'\[inaudible\]',
    r'\[música\]',
    r'\[ruido\]',
    r'\bxxx+\b',
    r'\.\.\.\.',        # cuatro o más puntos seguidos
    r'\[unclear\]',
    r'\[noise\]',
    r'\[music\]',
]

# Caracteres típicos de encoding roto (UTF-8 mal leído como latin-1)
PATRON_ENCODING_ROTO = re.compile(
    r'[\x80-\x9f\ufffd]|Ã[\xa0-\xff]|â€[™œ\x9d]'
)

# Palabras españolas muy frecuentes — si no aparece ninguna, posible idioma incorrecto
PALABRAS_ESPANOL_FRECUENTES = [
    'que', 'de', 'en', 'el', 'la', 'los', 'las', 'un', 'una',
    'es', 'por', 'con', 'no', 'se', 'del', 'al', 'como', 'para',
    'pero', 'más', 'todo', 'también', 'me', 'te', 'lo', 'le',
    'muy', 'si', 'ya', 'su', 'hay', 'sí', 'porque', 'cuando',
]


# ---------------------------------------------------------------------------
# Resultado de validación
# ---------------------------------------------------------------------------

@dataclass
class ResultadoValidacion:
    es_valida: bool
    score: float           # 0.0 (pésima) → 1.0 (perfecta)
    problemas: list = field(default_factory=list)
    advertencias: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def resumen(self) -> str:
        estado = "✅ VÁLIDA" if self.es_valida else "❌ INVÁLIDA"
        lineas = [f"{estado} (score: {self.score:.2f})"]
        for p in self.problemas:
            lineas.append(f"  🔴 {p}")
        for a in self.advertencias:
            lineas.append(f"  🟡 {a}")
        return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Validador principal
# ---------------------------------------------------------------------------

def validar_transcripcion(
    texto: str,
    duracion_minutos: Optional[float] = None,
    nombre_archivo: str = "",
) -> ResultadoValidacion:
    """
    Evalúa la calidad de una transcripción.

    Args:
        texto: Contenido de la transcripción
        duracion_minutos: Duración del audio en minutos (opcional, mejora la detección)
        nombre_archivo: Solo para logs

    Returns:
        ResultadoValidacion con score, problemas detectados y veredicto final
    """
    problemas = []
    advertencias = []
    penalizaciones = 0.0
    stats = {}

    # --- 1. TEXTO VACÍO O MÍNIMO ---
    palabras = texto.split()
    num_palabras = len(palabras)
    stats["num_palabras"] = num_palabras

    if num_palabras < MIN_PALABRAS:
        problemas.append(
            f"Texto demasiado corto: {num_palabras} palabras (mínimo {MIN_PALABRAS})"
        )
        penalizaciones += 0.6  # Penalización fuerte — casi seguro inválido

    # --- 2. DENSIDAD PALABRAS/MINUTO (solo si se conoce la duración) ---
    if duracion_minutos and duracion_minutos > 0 and num_palabras > 0:
        ppm = num_palabras / duracion_minutos
        stats["palabras_por_minuto"] = round(ppm, 1)

        if ppm < MIN_PALABRAS_POR_MINUTO:
            problemas.append(
                f"Densidad muy baja: {ppm:.0f} palabras/min "
                f"(esperado >{MIN_PALABRAS_POR_MINUTO} en conversación normal)"
            )
            penalizaciones += 0.4

    # --- 3. PALABRAS ININTELIGIBLES ---
    texto_lower = texto.lower()
    total_basura = 0
    for patron in PALABRAS_BASURA:
        matches = re.findall(patron, texto_lower)
        total_basura += len(matches)

    ratio_basura = total_basura / max(num_palabras, 1)
    stats["palabras_basura"] = total_basura
    stats["ratio_basura"] = round(ratio_basura, 4)

    if ratio_basura > MAX_RATIO_BASURA:
        problemas.append(
            f"Alto porcentaje de audio ininteligible: "
            f"{ratio_basura*100:.1f}% ({total_basura} ocurrencias)"
        )
        penalizaciones += 0.3
    elif total_basura > 0:
        advertencias.append(
            f"Algunas partes ininteligibles detectadas ({total_basura} ocurrencias)"
        )
        penalizaciones += 0.05

    # --- 4. ENCODING ROTO ---
    matches_encoding = PATRON_ENCODING_ROTO.findall(texto)
    num_corruptos = len(matches_encoding)
    ratio_corruptos = num_corruptos / max(len(texto), 1)
    stats["caracteres_corruptos"] = num_corruptos
    stats["ratio_corruptos"] = round(ratio_corruptos, 6)

    if ratio_corruptos > MAX_RATIO_CARACTERES_CORRUPTOS:
        problemas.append(
            f"Encoding roto detectado: {num_corruptos} caracteres corruptos "
            f"({ratio_corruptos*100:.2f}% del texto)"
        )
        penalizaciones += 0.35
    elif num_corruptos > 5:
        advertencias.append(f"Algunos caracteres potencialmente corruptos ({num_corruptos})")
        penalizaciones += 0.05

    # --- 5. RATIO DE PUNTUACIÓN ---
    signos_puntuacion = len(re.findall(r'[.!?,;:]', texto))
    ratio_puntuacion = signos_puntuacion / max(num_palabras, 1)
    stats["signos_puntuacion"] = signos_puntuacion
    stats["ratio_puntuacion"] = round(ratio_puntuacion, 4)

    # Una transcripción normal tiene al menos 0.05 signos por palabra
    if num_palabras > 200 and ratio_puntuacion < 0.02:
        advertencias.append(
            f"Texto sin puntuación (ratio: {ratio_puntuacion:.3f}) — "
            f"posible transcripción degradada"
        )
        penalizaciones += 0.1

    # --- 6. IDIOMA (detección simple) ---
    palabras_lower = [p.lower().strip('.,!?;:()[]"\'') for p in palabras]
    palabras_espanol = sum(
        1 for p in palabras_lower if p in PALABRAS_ESPANOL_FRECUENTES
    )
    ratio_espanol = palabras_espanol / max(num_palabras, 1)
    stats["palabras_espanol"] = palabras_espanol
    stats["ratio_espanol"] = round(ratio_espanol, 4)

    if num_palabras > 100 and ratio_espanol < MIN_RATIO_ESPANOL:
        problemas.append(
            f"Posible idioma incorrecto: solo {ratio_espanol*100:.1f}% de "
            f"palabras españolas frecuentes (esperado >{MIN_RATIO_ESPANOL*100:.0f}%)"
        )
        penalizaciones += 0.4

    # --- SCORE FINAL ---
    score = max(0.0, min(1.0, 1.0 - penalizaciones))
    es_valida = len(problemas) == 0 and score >= 0.5

    return ResultadoValidacion(
        es_valida=es_valida,
        score=score,
        problemas=problemas,
        advertencias=advertencias,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Plan B: lanzar Groq Whisper para un archivo concreto
# ---------------------------------------------------------------------------

def activar_plan_b_whisper(nombre_asesor: str) -> Optional[str]:
    """
    Plan B automático ante transcripción de baja calidad.

    Prioridad de recuperación:
      1. ¿Existe ya un _whisper.txt en transcripts/? → usarlo directamente (gratis, instantáneo)
      2. ¿Existe MP3 en audios/?                     → transcribir con Groq Whisper
      3. Nada disponible                              → avisar y continuar con la original

    Args:
        nombre_asesor: Stem del archivo de transcripción (e.g. "Esther Lopez_whisper" o "Esther Lopez")
    """
    from centauro.config import settings

    audios_dir    = settings.INPUTS_DIR / "audios"
    transcripts_dir = settings.INPUTS_DIR / "transcripts"

    # Normalizar nombre base (sin sufijo _whisper si ya lo tiene)
    nombre_base = nombre_asesor.replace("_whisper", "").strip()
    nombre_con_guion  = nombre_base.replace(" ", "_")
    nombre_con_espacio = nombre_base.replace("_", " ")

    # ------------------------------------------------------------------
    # PASO 1: ¿Ya existe una transcripción Whisper válida en transcripts/?
    # ------------------------------------------------------------------
    candidatos_whisper = [
        transcripts_dir / f"{nombre_con_espacio}_whisper.txt",
        transcripts_dir / f"{nombre_con_guion}_whisper.txt",
    ]
    for candidato_txt in candidatos_whisper:
        if candidato_txt.exists():
            contenido = candidato_txt.read_text(encoding="utf-8").strip()
            if contenido:
                print(f"   ♻️  Plan B: Ya existe {candidato_txt.name}, reutilizando (sin coste)")
                return contenido
            else:
                print(f"   ⚠️  Plan B: {candidato_txt.name} existe pero está vacío, continuando...")

    # ------------------------------------------------------------------
    # PASO 2: ¿Existe el MP3 en audios/?
    # ------------------------------------------------------------------
    candidatos_mp3 = [
        audios_dir / f"{nombre_con_guion}.mp3",
        audios_dir / f"{nombre_con_espacio}.mp3",
    ]
    audio_path = None
    for candidato in candidatos_mp3:
        if candidato.exists():
            audio_path = candidato
            break

    if not audio_path:
        print(f"   ⚠️  Plan B: No se encontró transcripción Whisper ni MP3 para '{nombre_base}'")
        print(f"   💡 Opciones:")
        print(f"      • Coloca el audio en inputs/audios/{nombre_con_guion}.mp3")
        print(f"      • O coloca el video en inputs/videollamadas/ y ejecuta extract_audio.py")
        return None

    print(f"   🔄 Plan B: Transcribiendo {audio_path.name} con Groq Whisper...")

    try:
        import os
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")

        from groq import Groq
        from centauro.tools.whisper_transcribe import (
            texto_de_segmentos,
            registrar_gasto_whisper,
            _get_audio_duration_minutes,
            _extraer_segundos_espera,
            WHISPER_MODEL,
        )
        import time

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("   ❌ Plan B: No se encontró GROQ_API_KEY en el entorno / .env")
            return None

        client = Groq(api_key=api_key)
        duracion_min = _get_audio_duration_minutes(audio_path)

        # Transcribir con reintentos ante rate limit
        MAX_REINTENTOS = 3
        response = None
        for intento in range(1, MAX_REINTENTOS + 1):
            try:
                with open(audio_path, "rb") as f:
                    response = client.audio.transcriptions.create(
                        model=WHISPER_MODEL,
                        file=f,
                        response_format="verbose_json",
                        language="es",
                    )
                break
            except Exception as e:
                mensaje = str(e)
                if "429" in mensaje or "rate_limit" in mensaje.lower():
                    espera = _extraer_segundos_espera(mensaje)
                    print(f"   ⏳ Rate limit (intento {intento}/{MAX_REINTENTOS}). "
                          f"Esperando {espera // 60}m {espera % 60}s...")
                    time.sleep(espera)
                    print(f"   🔄 Reintentando...")
                else:
                    print(f"   ❌ Plan B: Error inesperado: {e}")
                    return None

        if response is None:
            print(f"   ❌ Plan B: No se pudo transcribir tras {MAX_REINTENTOS} intentos")
            return None

        # Extraer texto
        segmentos = getattr(response, "segments", [])
        contenido = texto_de_segmentos(segmentos)
        if not contenido:
            contenido = getattr(response, "text", "").strip()

        if not contenido:
            print("   ❌ Plan B: La transcripción devolvió texto vacío")
            return None

        # Guardar el nuevo .txt (sobreescribir la transcripción mala)
        nombre_txt = f"{nombre_con_espacio}_whisper.txt"
        salida_txt = transcripts_dir / nombre_txt
        salida_txt.write_text(contenido, encoding="utf-8")
        print(f"   ✅ Plan B completado: {salida_txt.name} guardado")

        # Registrar gasto
        request_id = getattr(response, "id", "")
        registrar_gasto_whisper(
            referencia=audio_path.name,
            duracion_minutos=duracion_min,
            request_id=request_id,
        )

        return contenido

    except Exception as e:
        print(f"   ❌ Plan B: Error inesperado: {e}")
        return None


# ---------------------------------------------------------------------------
# Ejecución directa (para testing manual)
# ---------------------------------------------------------------------------

def main():
    """Valida todas las transcripciones en inputs/transcripts/ y muestra el resultado."""
    from centauro.config import settings

    transcripts_dir = settings.INPUTS_DIR / "transcripts"
    archivos = (
        list(transcripts_dir.glob("*.txt")) +
        list(transcripts_dir.glob("*.vtt")) +
        list(transcripts_dir.glob("*.docx"))
    )

    if not archivos:
        print("⚠️  No hay transcripciones en inputs/transcripts/")
        return

    print(f"\n🔍 Validando {len(archivos)} transcripción(es)...\n")
    print("=" * 60)

    for archivo in sorted(archivos):
        print(f"\n📄 {archivo.name}")
        try:
            texto = archivo.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  ❌ No se pudo leer: {e}")
            continue

        resultado = validar_transcripcion(texto, nombre_archivo=archivo.name)
        print(resultado.resumen())
        print(f"  📊 Stats: {resultado.stats}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
