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

from pathlib import Path
from typing import Any, Dict


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
      - n_silencios_largos_3seg (int): número de pausas continuas de más de 3 segundos
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

        # Contar bloques continuos de silencio >= 3 segundos
        frame_dur_seg = hop_length / sr
        min_frames = max(1, int(3.0 / frame_dur_seg))
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
            "n_silencios_largos_3seg": n_silencios_largos,
        }

    except Exception as e:
        return {"disponible": False, "motivo": f"Error al procesar audio: {e}"}


def formatear_sin_audio_para_prompt() -> str:
    """Bloque para insertar en el prompt cuando no hay archivo de audio disponible."""
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 DATOS OBJETIVOS DEL AUDIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
No hay archivo de audio disponible para esta transcripción.
El input fue texto (TXT, VTT o DOCX), por lo que no es posible
analizar métricas acústicas (energía, silencios, ritmo).
Evalúa el estilo comunicativo únicamente a partir del texto transcrito.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


def formatear_metricas_para_prompt(metricas: Dict[str, Any]) -> str:
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
        energia_desc = f"{ratio_e}× — caída notable de energía/voz al final de la llamada"
    elif ratio_e > 1.10:
        energia_desc = f"{ratio_e}× — la energía sube al final (asesor gana impulso al cerrar)"
    else:
        energia_desc = f"{ratio_e}× — energía estable durante toda la llamada"

    silencio_pct = round(metricas["ratio_silencio"] * 100, 1)
    n_pausas = metricas["n_silencios_largos_3seg"]
    if n_pausas == 0:
        pausas_desc = "ninguna pausa larga detectada"
    elif n_pausas == 1:
        pausas_desc = "1 pausa larga detectada (>3 seg)"
    else:
        pausas_desc = f"{n_pausas} pausas largas detectadas (>3 seg cada una)"

    tempo = metricas["tempo_bpm"]
    if tempo < 80:
        tempo_desc = f"{tempo} BPM — ritmo lento"
    elif tempo < 130:
        tempo_desc = f"{tempo} BPM — ritmo moderado"
    else:
        tempo_desc = f"{tempo} BPM — ritmo rápido"

    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 DATOS OBJETIVOS DEL AUDIO (medición acústica)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Estos datos son señales objetivas medidas sobre la onda de audio.
Úsalos para COMPLEMENTAR tu análisis del texto, no para sustituirlo.

• Duración de la llamada: {minutos} min {segundos} seg
• Energía vocal final vs inicio: {energia_desc}
• Silencios totales: {silencio_pct}% del audio
• Pausas largas (>3 seg): {pausas_desc}
• Velocidad estimada del habla: {tempo_desc}

⚠️ Interpretación orientativa:
- Caída de energía al final → posible desenganche o cansancio del asesor
- Múltiples pausas largas → pueden indicar incomodidad, espera o momentos de reflexión
- Ritmo muy rápido → riesgo de atropellar al lead sin dejarle espacio
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
