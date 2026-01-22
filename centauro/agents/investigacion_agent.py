"""
Agente Evaluador: Investigación (v3.0)

Fusiona: Apertura + Detección de Necesidades

Evalúa:
- Bienvenida y establecimiento de rapport (primeros minutos)
- Exploración de necesidades, motivaciones y situación del lead
- Calidad de preguntas y escucha activa
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt

class InvestigacionAgent(BaseEvaluatorAgent):
    """
    Evalúa la fase de investigación completa: apertura + descubrimiento

    Criterios clave:
    - Apertura cálida y profesional que genera confianza
    - Preguntas de calidad que exploran motivaciones profundas
    - Escucha activa (reformula, valida, profundiza)
    - El LEAD habla más que el ASESOR
    - Descubre el DOLOR real, no solo datos superficiales
    """

    def __init__(self):
        super().__init__(nombre_bloque="Investigación")

    def evaluate(self, transcripcion: str, contexto_manual: str) -> EvaluationResult:
        """Evalúa investigación (apertura + detección necesidades)"""

        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual)
            confianza = self._calcular_confianza(resultado_raw)

            # Validar evidencias múltiples
            evidencias_extra = resultado_raw.get("evidencias_extra", [])
            if len(evidencias_extra) < 3:
                print(f"   ⚠️ Pocas evidencias de investigación ({len(evidencias_extra)})")
                confianza *= 0.85

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
                    "calidad_apertura": resultado_raw.get("calidad_apertura", "MEDIA"),
                    "num_preguntas_detectadas": len([e for e in evidencias_extra if "[ASESOR]" in e and "?" in e]),
                    "indicios_escucha_activa": resultado_raw.get("indicios_escucha_activa", False)
                }
            )

        except Exception as e:
            print(f"   ❌ Error en evaluación de Investigación: {e}")
            return self._create_fallback_result(str(e))

    def _evaluar_con_llm(self, transcripcion: str, manual: str) -> dict:
        """Llama al LLM con prompt especializado en investigación completa"""

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de INVESTIGACIÓN en ventas consultivas.

TU TAREA: Evaluar la fase inicial completa (APERTURA + DESCUBRIMIENTO DE NECESIDADES).

CONTEXTO DEL MANUAL:
{manual}

CRITERIOS ESPECÍFICOS (Escala 1-5):

1 = NEGLIGENTE / DESASTRE
   - Apertura fría, sin presentación adecuada
   - No pregunta nada sobre el lead
   - Va directo a vender sin investigar
   - Lead no comparte información

2 = DEFICIENTE / MÍNIMO
   - Apertura mecánica, sin calidez
   - Pregunta 1-2 datos básicos ("¿En qué trabajas?")
   - No profundiza ni construye rapport
   - Escucha pasiva

3 = CORRECTO / PROTOCOLO ESTÁNDAR
   - Apertura adecuada pero genérica
   - Hace preguntas del script estándar
   - Cubre datos básicos (trabajo, experiencia, motivación)
   - Funcional pero sin profundidad emocional
   - No descubre el DOLOR real

4 = BUENO / INVESTIGACIÓN ACTIVA
   - Apertura cálida que genera confianza
   - Preguntas abiertas que invitan a desarrollar
   - Repregunta para clarificar ("¿Qué quieres decir con...?")
   - Escucha activa (reformula: "Entiendo que...")
   - Empieza a tocar motivaciones profundas

5 = MAESTRÍA / DISCOVERY CONSULTIVO
   - Apertura personalizada que conecta emocionalmente
   - Pregunta el PORQUÉ detrás de cada respuesta
   - Descubre el dolor real y urgencia
   - El LEAD habla 70% del tiempo (asesor escucha)
   - Valida emocionalmente ("Tiene sentido que...")
   - Usa técnica SPIN o similar

EVIDENCIA REQUERIDA:
Debes identificar MÍNIMO:
- 1 ejemplo de apertura/bienvenida del [ASESOR]
- 3 ejemplos de preguntas clave del [ASESOR]
- 2 ejemplos de respuestas elaboradas del [LEAD]
- 1 indicio de escucha activa (si existe)

FORMATO JSON OBLIGATORIO:
{{
  "puntuacion_1_5": 3,
  "observabilidad": "ALTA" | "MEDIA" | "BAJA",
  "evidencia_principal": "[ASESOR]: Pregunta o momento clave de apertura...",
  "evidencias_extra": [
    "[ASESOR]: Pregunta investigativa 1...",
    "[LEAD]: Respuesta del lead compartiendo info relevante...",
    "[ASESOR]: Pregunta de profundización...",
    "[LEAD]: Respuesta elaborada revelando motivación...",
    "[ASESOR]: Validación o reformulación (si hay)..."
  ],
  "razonamiento": "Análisis técnico: ¿Qué hizo bien en apertura? ¿Calidad de preguntas? ¿Qué faltó para la nota siguiente?",
  "recomendacion_accionable": "Acción específica y concreta para mejorar (sin repetir lo ya logrado)",
  "gap_para_5": "Si nota es 3 o 4, explica ESPECÍFICAMENTE qué faltó para alcanzar el 5. Si nota es 5, pon 'N/A - Ya alcanzado'",
  "calidad_apertura": "EXCELENTE | BUENA | CORRECTA | DEFICIENTE",
  "indicios_escucha_activa": true/false
}}

REGLAS CRÍTICAS:
- Todas las evidencias DEBEN ser copy-paste LITERAL de la transcripción
- Incluye SIEMPRE [ASESOR] o [LEAD] en cada cita
- Evalúa TANTO la apertura COMO la investigación
- NO penalices si el lead es cerrado, penaliza si el asesor no intentó abrir
- Sé técnico, no motivacional
- ⚠️ IMPORTANTE: El 5/5 ES ALCANZABLE si el asesor cumple todos los criterios de MAESTRÍA
- Si la ejecución es realmente excelente, NO te limites a dar 4
- En "gap_para_5" explica QUÉ FALTÓ específicamente, no generalidades
- En "recomendacion_accionable" NO repitas lo que ya hizo bien, solo menciona lo que falta mejorar
"""

        prompt_usuario = f"""
Analiza la fase de INVESTIGACIÓN (apertura + descubrimiento) en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""

        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_investigacion")
        return self._extract_json_safe(resp)
