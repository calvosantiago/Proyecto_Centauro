"""
Agente de Diarización Mejorado v2.0

Mejoras sobre el sistema anterior:
1. Ventana de contexto deslizante (no chunking ciego)
2. Detección de cambios de turno con contexto
3. Validación cruzada con heurísticas
4. Fusión inteligente de turnos consecutivos
"""
import re
import json
from typing import List, Tuple, Optional
from ..llm_client import consultar_gpt
from ..config import settings

class DiarizationAgent:
    """
    Agente especializado en separar interlocutores en transcripciones
    """
    
    def __init__(self, nombre_asesor: str):
        self.nombre_asesor = nombre_asesor
        self.ventana_contexto = 3  # Número de frases anteriores/posteriores
        self.confidence_threshold = 0.7
        
    def diarizar(self, texto_crudo: str, log_id: str = "unknown") -> str:
        """
        Proceso completo de diarización
        
        Args:
            texto_crudo: Transcripción sin etiquetar
            log_id: Identificador para logging
            
        Returns:
            Texto diarizado con etiquetas [ASESOR] y [LEAD]
        """
        print(f"🎙️ [DiarizationAgent v2.0] Iniciando para: {self.nombre_asesor}")
        
        # Paso 1: Segmentación inteligente
        frases = self._segmentar_por_pausas_naturales(texto_crudo)
        print(f"   📝 Detectadas {len(frases)} unidades conversacionales")
        
        # Paso 2: Clasificación con contexto deslizante
        dialogo_etiquetado = []
        speaker_anterior = None
        
        for idx, frase in enumerate(frases):
            # Determinar speaker con contexto
            speaker, confianza = self._clasificar_con_contexto(
                frases, idx, speaker_anterior
            )
            
            # Si la confianza es baja y hay cambio de speaker, re-evaluar
            if speaker_anterior and speaker != speaker_anterior and confianza < self.confidence_threshold:
                print(f"   🔄 Re-evaluando turno {idx} (confianza baja: {confianza:.2f})")
                # Aumentar ventana de contexto temporalmente
                original_ventana = self.ventana_contexto
                self.ventana_contexto = 5
                speaker, confianza = self._clasificar_con_contexto(frases, idx, speaker_anterior)
                self.ventana_contexto = original_ventana
            
            dialogo_etiquetado.append({
                "speaker": speaker,
                "text": frase,
                "confidence": confianza,
                "index": idx
            })
            
            speaker_anterior = speaker
        
        # Paso 3: Fusión de turnos consecutivos
        dialogo_fusionado = self._fusionar_turnos_consecutivos(dialogo_etiquetado)
        
        # Paso 4: Formatear salida
        resultado = "\n\n".join([
            f"[{turno['speaker']}]: {turno['text']}"
            for turno in dialogo_fusionado
        ])
        
        print(f"   ✅ Diarización completada: {len(dialogo_fusionado)} turnos")
        print(f"   📊 Distribución: {self._calcular_distribucion(dialogo_fusionado)}")
        
        return resultado
    
    def _segmentar_por_pausas_naturales(self, texto: str) -> List[str]:
        """
        Divide el texto respetando pausas conversacionales naturales
        
        Mejoras vs sistema anterior:
        - No corta mid-sentence por límite de caracteres
        - Respeta puntuación y mayúsculas
        - Identifica pausas largas (doble salto de línea)
        """
        # Si ya tiene estructura (saltos de línea frecuentes), respetarla
        if texto.count('\n') > len(texto) / 200:
            return [linea.strip() for linea in texto.split('\n') if linea.strip()]
        
        # Si es muro de texto, segmentar por puntuación
        # Patrón: Punto/Interrogación/Exclamación + Espacio + Mayúscula
        patron = r'(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])'
        frases = re.split(patron, texto)
        
        # Limpiar y filtrar vacíos
        return [frase.strip() for frase in frases if frase.strip() and len(frase) > 10]
    
    def _clasificar_con_contexto(self, frases: List[str], idx: int, 
                                 speaker_anterior: Optional[str]) -> Tuple[str, float]:
        """
        Clasifica una frase usando ventana de contexto deslizante
        
        Returns:
            Tuple[speaker, confianza]
        """
        # Construir ventana de contexto
        inicio = max(0, idx - self.ventana_contexto)
        fin = min(len(frases), idx + 2)
        contexto_frases = frases[inicio:fin]
        
        # Marcar la frase objetivo
        contexto_con_marca = []
        for i, frase in enumerate(contexto_frases):
            offset = i + inicio
            if offset == idx:
                contexto_con_marca.append(f">>> {frase}")
            else:
                contexto_con_marca.append(frase)
        
        contexto_texto = "\n".join(contexto_con_marca)
        
        # Intentar clasificación con LLM
        try:
            resultado = self._clasificar_llm(contexto_texto, speaker_anterior)
            return resultado["speaker"], resultado["confianza"]
        except Exception as e:
            print(f"   ⚠️ LLM falló en turno {idx}, usando heurística: {e}")
            # Fallback a clasificación heurística
            speaker = self._clasificar_heuristico(frases[idx], speaker_anterior)
            return speaker, 0.5  # Confianza media
    
    def _clasificar_llm(self, contexto: str, speaker_anterior: Optional[str]) -> dict:
        """
        Clasifica usando el LLM con prompt especializado
        """
        prompt_sistema = f"""
Eres un experto en análisis de diálogos comerciales.

CONTEXTO:
- ASESOR ({self.nombre_asesor}): Quien vende, explica programas, hace preguntas estructuradas
- LEAD (Cliente): Quien pregunta sobre sí mismo, expresa dudas personales

TAREA:
Identifica quién dice la frase marcada con >>> en el contexto siguiente.

REGLAS DE ATRIBUCIÓN:
- El ASESOR suele: Explicar, preguntar sobre motivaciones, hablar del programa/metodología
- El LEAD suele: Hablar de su trabajo/vida, expresar dudas, preguntar precios/horarios

{f"CONTEXTO PREVIO: El speaker anterior era {speaker_anterior}" if speaker_anterior else ""}

FORMATO JSON OBLIGATORIO:
{{
  "speaker": "ASESOR" o "LEAD",
  "confianza": 0.0 a 1.0,
  "razon": "Justificación breve"
}}
"""
        
        resp = consultar_gpt(prompt_sistema, contexto, f"diar_classify")
        data = json.loads(resp)
        
        # Validar formato
        if "speaker" not in data:
            raise ValueError("Respuesta sin campo 'speaker'")
        
        return {
            "speaker": data["speaker"].upper(),
            "confianza": float(data.get("confianza", 0.5)),
            "razon": data.get("razon", "")
        }
    
    def _clasificar_heuristico(self, frase: str, speaker_anterior: Optional[str]) -> str:
        """
        Clasificación de respaldo basada en keywords y patrones
        """
        frase_lower = frase.lower()
        
        # Patrones fuertes de ASESOR (alta confianza)
        patrones_asesor_fuertes = [
            r'\b(obs business school|universidad de barcelona)\b',
            r'\b(matrícula|admisión|documentación necesaria)\b',
            r'\b(alguna duda|te parece bien|perfecto entonces)\b',
            r'\b(cuéntame|explícame más|qué te motivó)\b'
        ]
        
        # Patrones fuertes de LEAD (alta confianza)
        patrones_lead_fuertes = [
            r'\b(mi trabajo|mi jefe|mi empresa|mi situación)\b',
            r'\b(trabajo en|llevo \d+ años|soy de)\b',
            r'\b(cuánto cuesta|precio total|qué incluye)\b'
        ]
        
        # Patrones débiles (menor peso)
        patrones_asesor_debiles = [
            r'\b(campus|metodología|online|presencial)\b',
            r'\b(programa|master|especialización)\b'
        ]
        
        patrones_lead_debiles = [
            r'\b(horario|duración|cuando empez)\b',
            r'\b(no estoy seguro|tengo que pensarlo)\b'
        ]
        
        # Scoring
        score_asesor = 0
        score_lead = 0
        
        for patron in patrones_asesor_fuertes:
            if re.search(patron, frase_lower):
                score_asesor += 3
        
        for patron in patrones_lead_fuertes:
            if re.search(patron, frase_lower):
                score_lead += 3
        
        for patron in patrones_asesor_debiles:
            if re.search(patron, frase_lower):
                score_asesor += 1
        
        for patron in patrones_lead_debiles:
            if re.search(patron, frase_lower):
                score_lead += 1
        
        # Decidir
        if score_asesor > score_lead:
            return "ASESOR"
        elif score_lead > score_asesor:
            return "LEAD"
        else:
            # Empate: usar continuidad (mismo speaker que el anterior)
            return speaker_anterior if speaker_anterior else "LEAD"
    
    def _fusionar_turnos_consecutivos(self, dialogo_etiquetado: List[dict]) -> List[dict]:
        """
        Une intervenciones consecutivas del mismo speaker
        
        Mejora legibilidad y reduce ruido en evaluaciones posteriores
        """
        if not dialogo_etiquetado:
            return []
        
        fusionado = []
        buffer = {
            "speaker": dialogo_etiquetado[0]["speaker"],
            "text": dialogo_etiquetado[0]["text"],
            "confidence": dialogo_etiquetado[0]["confidence"]
        }
        
        for i in range(1, len(dialogo_etiquetado)):
            turno_actual = dialogo_etiquetado[i]
            
            if turno_actual["speaker"] == buffer["speaker"]:
                # Mismo speaker: fusionar
                buffer["text"] += f" {turno_actual['text']}"
                # Confianza promedio
                buffer["confidence"] = (buffer["confidence"] + turno_actual["confidence"]) / 2
            else:
                # Cambio de speaker: guardar buffer
                fusionado.append(buffer)
                buffer = {
                    "speaker": turno_actual["speaker"],
                    "text": turno_actual["text"],
                    "confidence": turno_actual["confidence"]
                }
        
        # Añadir último turno
        fusionado.append(buffer)
        
        return fusionado
    
    def _calcular_distribucion(self, dialogo: List[dict]) -> str:
        """
        Calcula estadísticas de distribución ASESOR vs LEAD
        """
        total = len(dialogo)
        asesor_count = sum(1 for t in dialogo if t["speaker"] == "ASESOR")
        lead_count = total - asesor_count
        
        asesor_pct = (asesor_count / total * 100) if total > 0 else 0
        lead_pct = (lead_count / total * 100) if total > 0 else 0
        
        return f"ASESOR: {asesor_count} ({asesor_pct:.1f}%) | LEAD: {lead_count} ({lead_pct:.1f}%)"