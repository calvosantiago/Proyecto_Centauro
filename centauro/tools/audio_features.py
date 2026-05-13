"""
audio_features.py — Extracción de métricas acústicas objetivas con librosa

Analiza señales de audio (MP3/MP4→MP3) para obtener métricas cuantitativas
que enriquecen la evaluación de Estilo y Comunicación.

No depende del idioma: trabaja directamente con la onda de audio.
No clasifica emociones: extrae señales objetivas (energía, silencios, ritmo).

Uso:
    from centauro.tools.audio_features import extraer_metricas_audio, formatear_metricas_para_prompt
    metricas = extraer_metricas_audio(Path("audio.mp3"))
    bloque = formatear_metricas_para_prompt(metricas)
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional


def extraer_metricas_audio(audio_path: Path) -> Dict[str, Any]:
    """
    Extrae métricas acústicas objetivas de un archivo de audio.

    Retorna un dict con:
      - disponible (bool): False si librosa no está instalado o hay error
      - motivo (str): descripción del error si disponible=False
      - duracion_seg (float): duración total en segundos
      - energia_media (float): nivel RMS medio (proxy de volumen)
      - ratio_energia_final_vs_inicio (float): energía último 20% / primer 20%
          < 0.75 → caída notable de energía al final
          0.75-1.10 → estable
          > 1.10 → sube la energía al final
      - tempo_bpm (float): pulsos por minuto estimados (proxy de velocidad de habla)
      - ratio_silencio (float): fracción del audio que es silencio (0.0-1.0)
      - n_silencios_largos_4seg (int): número de pausas continuas de más de 4 segundos
    """
    try:
        import librosa
        import numpy as np
    except ImportError:
        return {"disponible": False, "motivo": "librosa no instalado (pip install librosa)"}

    try:
        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    except Exception as e:
        return {"disponible": False, "motivo": f"No se pudo cargar el audio: {e}"}

    try:
        import numpy as np

        duracion_seg = librosa.get_duration(y=y, sr=sr)

        # --- Energía RMS ---
        hop_length = 512
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        energia_media = float(np.mean(rms))

        # Comparar primer 20% vs último 20%
        n = len(rms)
        tramo = max(1, n // 5)
        energia_inicio = float(np.mean(rms[:tramo]))
        energia_final = float(np.mean(rms[-tramo:]))
        ratio_energia = round(energia_final / energia_inicio, 2) if energia_inicio > 1e-8 else 1.0

        # --- Tempo (proxy de velocidad de habla) ---
        tempo_arr, _ = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
        # beat_track puede devolver array o escalar según versión de librosa
        tempo_bpm = float(np.atleast_1d(tempo_arr)[0])

        # --- Silencios ---
        umbral_silencio = energia_media * 0.10
        silencio_mask = rms < umbral_silencio
        ratio_silencio = float(np.mean(silencio_mask))

        # Contar bloques continuos de silencio >= 4 segundos
        frame_dur_seg = hop_length / sr
        min_frames = max(1, int(4.0 / frame_dur_seg))
        n_silencios_largos = 0
        conteo = 0
        for es_silencio in silencio_mask:
            if es_silencio:
                conteo += 1
                if conteo == min_frames:
                    n_silencios_largos += 1
            else:
                conteo = 0

        return {
            "disponible": True,
            "duracion_seg": round(duracion_seg, 1),
            "energia_media": round(energia_media, 5),
            "ratio_energia_final_vs_inicio": ratio_energia,
            "tempo_bpm": round(tempo_bpm, 1),
            "ratio_silencio": round(ratio_silencio, 3),
            "n_silencios_largos_4seg": n_silencios_largos,
        }

    except Exception as e:
        return {"disponible": False, "motivo": f"Error al procesar audio: {e}"}


def calcular_ratio_habla_diarizada(transcripcion: str) -> Dict[str, Optional[float]]:
    """
    Calcula el porcentaje de habla de cada speaker a partir de la transcripción diarizada.
    Usa el número de caracteres por speaker como proxy del tiempo de habla.
    Devuelve pct_asesor y pct_lead (None si la transcripción no tiene etiquetas).
    """
    chars_asesor = 0
    chars_lead = 0
    for linea in transcripcion.splitlines():
        linea = linea.strip()
        m = re.match(r'^\[ASESOR\]:\s*(.+)', linea)
        if m:
            chars_asesor += len(m.group(1))
            continue
        m = re.match(r'^\[LEAD\]:\s*(.+)', linea)
        if m:
            chars_lead += len(m.group(1))
    total = chars_asesor + chars_lead
    if total == 0:
        return {"pct_asesor": None, "pct_lead": None}
    return {
        "pct_asesor": round(chars_asesor / total * 100, 1),
        "pct_lead": round(chars_lead / total * 100, 1),
    }


def _formatear_ratio_habla(ratio_habla: Optional[Dict]) -> str:
    """Genera la línea de % habla para insertar en el bloque de audio."""
    if not ratio_habla or ratio_habla.get("pct_asesor") is None:
        return ""
    pct_a = ratio_habla["pct_asesor"]
    pct_l = ratio_habla["pct_lead"]
    return f"• % habla asesor / lead: {pct_a}% asesor — {pct_l}% lead\n"


def formatear_sin_audio_para_prompt(ratio_habla: Optional[Dict] = None) -> str:
    """Bloque para insertar en el prompt cuando no hay archivo de audio disponible."""
    linea_ratio = _formatear_ratio_habla(ratio_habla)
    ratio_bloque = f"\n{linea_ratio}" if linea_ratio else ""
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 DATOS OBJETIVOS DEL AUDIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
No hay archivo de audio disponible para esta transcripción.
El input fue texto (TXT, VTT o DOCX), por lo que no es posible
analizar métricas acústicas (energía, silencios, ritmo).
Evalúa el estilo comunicativo únicamente a partir del texto transcrito.{ratio_bloque}
⚠️ REGLA DE MONÓLOGO (>80/20): Si el % de habla supera 80/20 en cualquier dirección,
   menciónalo explícitamente en el razonamiento como fallo de ritmo conversacional.
   La calificación final se ajustará automáticamente por esta regla.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


def formatear_metricas_para_prompt(metricas: Dict[str, Any], ratio_habla: Optional[Dict] = None) -> str:
    """
    Convierte el dict de métricas en un bloque de texto descriptivo
    listo para insertar en el prompt del LLM.
    """
    if not metricas or not metricas.get("disponible"):
        motivo = metricas.get("motivo", "desconocido") if metricas else "sin datos"
        return f"📊 DATOS DE AUDIO: No disponibles ({motivo})"

    dur = metricas["duracion_seg"]
    minutos = int(dur // 60)
    segundos = int(dur % 60)

    ratio_e = metricas["ratio_energia_final_vs_inicio"]
    if ratio_e < 0.75:
        energia_desc = (
            f"{ratio_e}× — el asesor habló con menos volumen/energía al final que al inicio. "
            f"Posible señal de cansancio o desenganche durante el cierre."
        )
    elif ratio_e > 1.10:
        energia_desc = (
            f"{ratio_e}× — el asesor ganó volumen/energía al final de la llamada. "
            f"Señal positiva: más impulso y convicción al cerrar que al abrir."
        )
    else:
        energia_desc = (
            f"{ratio_e}× — volumen y energía constantes de principio a fin. "
            f"El asesor mantuvo el mismo nivel de presencia vocal durante toda la llamada."
        )

    silencio_pct = round(metricas["ratio_silencio"] * 100, 1)
    if silencio_pct < 10:
        silencio_ctx = "por debajo del rango habitual — el asesor puede estar hablando sin dejar espacio al lead"
    elif silencio_pct <= 25:
        silencio_ctx = "dentro del rango habitual en llamadas comerciales (10-25%)"
    else:
        silencio_ctx = "por encima del rango habitual — puede haber muchas pausas o silencios del lead"

    n_pausas = metricas["n_silencios_largos_4seg"]
    if n_pausas == 0:
        pausas_desc = "ninguna detectada"
    elif n_pausas == 1:
        pausas_desc = "1 pausa larga (>4 seg) — puede ser un momento de reflexión o espera"
    else:
        pausas_desc = f"{n_pausas} pausas largas (>4 seg cada una) — pueden indicar momentos de incomodidad, espera o reflexión prolongada"

    tempo = metricas["tempo_bpm"]
    if tempo < 80:
        tempo_desc = "cadencia lenta — el asesor habla de forma pausada y deliberada"
    elif tempo < 130:
        tempo_desc = "cadencia moderada — ritmo conversacional normal, equilibrado"
    else:
        tempo_desc = "cadencia rápida — el asesor habla acelerado, riesgo de no dejar espacio al lead"

    linea_ratio = _formatear_ratio_habla(ratio_habla)

    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 DATOS OBJETIVOS DEL AUDIO (medición acústica)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Estos datos son señales objetivas medidas sobre la onda de audio.
Úsalos para COMPLEMENTAR tu análisis del texto, no para sustituirlo.

• Duración de la llamada: {minutos} min {segundos} seg
{linea_ratio}• Energía vocal (final vs inicio): {energia_desc}
• Silencios totales: {silencio_pct}% del audio — {silencio_ctx}
• Pausas largas (>4 seg): {pausas_desc}
• Ritmo conversacional: {tempo_desc}

⚠️ Interpretación orientativa:
- REGLA DE MONÓLOGO (>80/20): Si el % habla supera 80/20, menciónalo en el razonamiento
  como fallo de ritmo. La calificación final se ajusta automáticamente por esta regla.
- Caída de energía al final → posible desenganche o cansancio del asesor
- Múltiples pausas largas → pueden indicar incomodidad, espera o momentos de reflexión
- Cadencia muy rápida → riesgo de atropellar al lead sin dejarle espacio
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
