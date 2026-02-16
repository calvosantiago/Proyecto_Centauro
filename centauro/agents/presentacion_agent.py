"""
Agente Evaluador: Presentación del Programa y Encaje

INSTRUCCIÓN: Copia este archivo en:
C:\\Users\\uscp9a\\Grupo Planeta\\BI POWER - General\\PBI\\PROYECTOS\\Proyecto_Centauro\\centauro\\agents\\presentacion_agent.py
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt

class PresentacionAgent(BaseEvaluatorAgent):
    """
    Evalúa cómo el asesor presenta el programa y conecta con las necesidades del lead
    
    Criterios clave:
    - Personaliza la presentación según lo descubierto
    - Explica beneficios (no solo características)
    - Conecta el programa con el objetivo del lead
    - Maneja información de forma estructurada
    """
    
    def __init__(self):
        super().__init__(nombre_bloque="Presentación del programa")
    
    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """Evalúa la presentación del programa"""
        
        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual)
            confianza = self._calcular_confianza(resultado_raw)
            
            # Validar evidencia de personalización
            evidencias_extra = resultado_raw.get("evidencias_extra", [])
            personalizacion = resultado_raw.get("personalizacion_detectada", False)
            
            if not personalizacion:
                print(f"   ⚠️ No se detectó personalización en la presentación")
                confianza *= 0.85
            
            return EvaluationResult(
                bloque=self.nombre_bloque,
                calificacion=resultado_raw.get("calificacion"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=evidencias_extra,
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=resultado_raw.get("recomendacion_accionable", ""),
                metadata={
                    "personalizacion_detectada": personalizacion,
                    "enfoque": resultado_raw.get("enfoque", "caracteristicas")  # vs "beneficios"
                }
            )
            
        except Exception as e:
            print(f"   ❌ Error en evaluación de Presentación: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, transcripcion: str, manual: str) -> dict:
        """Llama al LLM con prompt especializado"""
        
        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de PRESENTACIÓN DEL PROGRAMA en venta consultiva.

TU ÚNICA TAREA: Evaluar cómo presentó el [ASESOR] el programa y lo conectó con las necesidades del lead.

CONTEXTO DEL MANUAL:
{manual}

CRITERIOS ESPECÍFICOS (Escala 1-5):

1 = DEFICIENTE / DESORGANIZADO
   - No explica el programa claramente
   - Información confusa o contradictoria
   - No conecta con lo que busca el lead

2 = INSUFICIENTE / DUMP DE INFORMACIÓN
   - Suelta características sin estructura ("dura 12 meses, es online...")
   - No personaliza (mismo discurso para todos)
   - No verifica comprensión

3 = CORRECTO / PRESENTACIÓN ESTÁNDAR (Robot)
   - Explica características principales de forma ordenada
   - Clara pero genérica (no adapta al lead)
   - Menciona algunos beneficios pero no conecta con el objetivo del lead
   - Funcional pero no persuasiva

4 = BUENO / PRESENTACIÓN CONSULTIVA
   - Personaliza según lo descubierto en exploración
   - Enfatiza BENEFICIOS sobre características
   - Conecta explícitamente con el objetivo del lead ("Esto te ayudará a...")
   - Verifica comprensión ("¿Tiene sentido?")
   - Estructura clara: Qué es → Cómo funciona → Por qué te sirve

5 = MAESTRÍA / PROPUESTA DE VALOR PERSONALIZADA
   - Presenta el programa como LA SOLUCIÓN al problema del lead
   - Cada característica se traduce en beneficio específico para él
   - Usa ejemplos o casos de éxito relevantes
   - Anticipa dudas y las resuelve proactivamente
   - El lead expresa que "es justo lo que necesito"

EVIDENCIA REQUERIDA:
Debes identificar MÍNIMO:
- 1 ejemplo de cómo explica el programa
- 1 ejemplo de conexión con necesidad del lead (si existe)
- 1 reacción del lead mostrando comprensión o interés

FORMATO JSON OBLIGATORIO:
{{
  "puntuacion_1_5": 3,
  "observabilidad": "ALTA" | "MEDIA" | "BAJA",
  "evidencia_principal": "[ASESOR]: Explicación principal del programa...",
  "evidencias_extra": [
    "[ASESOR]: Conexión con necesidad del lead...",
    "[LEAD]: Reacción mostrando interés o comprensión..."
  ],
  "razonamiento": "Análisis técnico: ¿Personalizó? ¿Habló de beneficios o características? ¿Conectó con el objetivo?",
  "recomendacion_accionable": "Acción específica para mejorar",
  "personalizacion_detectada": true/false,
  "enfoque": "caracteristicas" | "beneficios" | "mixto"
}}

REGLAS CRÍTICAS:
- Todas las evidencias DEBEN ser copy-paste LITERAL
- Incluye SIEMPRE [ASESOR] o [LEAD]
- Personalización = Adaptar la explicación a LO QUE EL LEAD DIJO que necesitaba
- NO evalúes si el programa es bueno, evalúa si el ASESOR lo presentó bien
- Diferencia: Características ("12 meses") vs Beneficios ("En 1 año estarás certificado")
"""
        
        prompt_usuario = f"""
Analiza cómo presentó el programa en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_presentacion")
        return self._extract_json_safe(resp)