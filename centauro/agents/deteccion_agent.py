"""
Agente Evaluador: Detección de Necesidades

INSTRUCCIÓN: Copia este archivo en:
C:\\Users\\uscp9a\\Grupo Planeta\\BI POWER - General\\PBI\\PROYECTOS\\Proyecto_Centauro\\centauro\\agents\\deteccion_agent.py
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt

class DeteccionNecesidadesAgent(BaseEvaluatorAgent):
    """
    Evalúa cómo el asesor descubre las motivaciones y situación del cliente
    
    Criterios clave:
    - Calidad y profundidad de las preguntas
    - Escucha activa (reformula, valida)
    - Descubre el DOLOR real (no solo datos superficiales)
    - El lead habla más que el asesor
    """
    
    def __init__(self):
        super().__init__(nombre_bloque="Detección de necesidades")
    
    def evaluate(self, transcripcion: str, contexto_manual: str) -> EvaluationResult:
        """Evalúa el descubrimiento de necesidades"""
        
        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual)
            confianza = self._calcular_confianza(resultado_raw)
            
            # Validar que haya múltiples evidencias
            evidencias_extra = resultado_raw.get("evidencias_extra", [])
            if len(evidencias_extra) < 2:
                print(f"   ⚠️ Pocas evidencias de preguntas ({len(evidencias_extra)})")
                confianza *= 0.8
            
            return EvaluationResult(
                bloque=self.nombre_bloque,
                puntuacion_1_5=resultado_raw.get("puntuacion_1_5"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=evidencias_extra,
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=resultado_raw.get("recomendacion_accionable", ""),
                metadata={
                    "num_preguntas_detectadas": len(evidencias_extra),
                    "indicios_escucha_activa": resultado_raw.get("indicios_escucha_activa", False)
                }
            )
            
        except Exception as e:
            print(f"   ❌ Error en evaluación de Detección: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, transcripcion: str, manual: str) -> dict:
        """Llama al LLM con prompt especializado"""
        
        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de DETECCIÓN DE NECESIDADES en venta consultiva.

TU ÚNICA TAREA: Evaluar cómo descubrió el [ASESOR] las motivaciones y situación del cliente.

CONTEXTO DEL MANUAL:
{manual}

CRITERIOS ESPECÍFICOS (Escala 1-5):

1 = NEGLIGENTE / SIN EXPLORACIÓN
   - No pregunta nada sobre el lead
   - Asume información sin verificar
   - Va directo a vender sin entender al cliente

2 = SUPERFICIAL / CHECKLIST MÍNIMO
   - Pregunta 1-2 datos básicos ("¿En qué trabajas?")
   - No profundiza ni repregunta
   - Escucha pasiva (no valida lo que dice el lead)

3 = CORRECTO / PROTOCOLO ESTÁNDAR (Robot)
   - Hace preguntas del script estándar
   - Cubre datos básicos (trabajo, experiencia, motivación)
   - Funcional pero sin profundidad
   - No descubre el DOLOR real

4 = BUENO / EXPLORACIÓN ACTIVA
   - Preguntas abiertas que invitan a desarrollar
   - Repregunta para clarificar ("¿Qué quieres decir con...?")
   - Escucha activa (reformula: "Entiendo que...")
   - Empieza a tocar motivaciones profundas

5 = MAESTRÍA / DISCOVERY CONSULTIVO
   - Pregunta el PORQUÉ detrás de cada respuesta
   - Descubre el dolor real (no solo lo que dice, sino lo que necesita)
   - El LEAD habla más que el ASESOR (70/30)
   - Valida emocionalmente ("Tiene sentido que...")
   - Usa técnica SPIN o similar

EVIDENCIA REQUERIDA:
Debes identificar MÍNIMO:
- 2 ejemplos de preguntas del [ASESOR]
- 1 ejemplo de respuesta elaborada del [LEAD]
- 1 indicio de escucha activa (si existe)

FORMATO JSON OBLIGATORIO:
{{
  "puntuacion_1_5": 3,
  "observabilidad": "ALTA" | "MEDIA" | "BAJA",
  "evidencia_principal": "[ASESOR]: Primera pregunta clave...",
  "evidencias_extra": [
    "[ASESOR]: Segunda pregunta...",
    "[LEAD]: Respuesta del lead donde comparte info relevante...",
    "[ASESOR]: Reformulación o validación..."
  ],
  "razonamiento": "Análisis técnico: ¿Qué hizo bien? ¿Qué faltó para el siguiente nivel?",
  "recomendacion_accionable": "Acción específica para mejorar",
  "indicios_escucha_activa": true/false
}}

REGLAS CRÍTICAS:
- Todas las evidencias DEBEN ser copy-paste LITERAL de la transcripción
- Incluye SIEMPRE [ASESOR] o [LEAD] en cada cita
- NO evalúes si el lead dio información, evalúa si el ASESOR preguntó bien
- NO penalices si el lead es cerrado, penaliza si el asesor no intentó abrir
- Sé técnico, no motivacional
"""
        
        prompt_usuario = f"""
Analiza SOLO la detección de necesidades en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_deteccion")
        return self._extract_json_safe(resp)