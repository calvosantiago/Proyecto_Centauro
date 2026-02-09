"""
Agente Evaluador: Propuesta de Valor Institución y Programa (v3.0)

Renombrado de: PresentacionAgent

Evalúa cómo el asesor presenta:
- La institución (OBS)
- El programa específico
- Conexión con necesidades descubiertas
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt

class PropuestaValorAgent(BaseEvaluatorAgent):
    """
    Evalúa la presentación de la propuesta de valor institucional y del programa

    Criterios clave:
    - Presentación clara de la institución (OBS)
    - Explicación estructurada del programa
    - Personaliza según necesidades descubiertas
    - Enfatiza BENEFICIOS sobre características
    - Conecta con objetivos del lead
    """

    def __init__(self):
        super().__init__(nombre_bloque="Propuesta de valor Institución y Programa")

    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """Evalúa la propuesta de valor"""

        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual, contexto_usuario)
            confianza = self._calcular_confianza(resultado_raw)

            # Validar evidencia de personalización
            evidencias_extra = resultado_raw.get("evidencias_extra", [])
            personalizacion = resultado_raw.get("personalizacion_detectada", False)

            if not personalizacion:
                print(f"   ⚠️ No se detectó personalización en la propuesta")
                confianza *= 0.85

            # Enriquecer recomendación con coaching si hay área de mejora
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")
            gap_para_5 = resultado_raw.get("gap_para_5", "")
            if gap_para_5 and "N/A" not in gap_para_5:
                recomendacion_enriquecida = self.enriquecer_recomendacion_con_coaching(
                    recomendacion_base,
                    area_mejora="propuesta de valor y presentación de beneficios"
                )
            else:
                recomendacion_enriquecida = recomendacion_base

            return EvaluationResult(
                bloque=self.nombre_bloque,
                puntuacion_1_5=resultado_raw.get("puntuacion_1_5"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=evidencias_extra,
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=recomendacion_enriquecida,
                metadata={
                    "personalizacion_detectada": personalizacion,
                    "enfoque": resultado_raw.get("enfoque", "caracteristicas"),
                    "presenta_institucion": resultado_raw.get("presenta_institucion", False),
                    "gap_para_5": gap_para_5
                }
            )

        except Exception as e:
            print(f"   ❌ Error en evaluación de Propuesta de Valor: {e}")
            return self._create_fallback_result(str(e))

    def _evaluar_con_llm(self, transcripcion: str, manual: str, contexto_usuario: str = None) -> dict:
        """Llama al LLM con prompt especializado"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion)

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de PROPUESTA DE VALOR en venta consultiva.

TU TAREA: Evaluar cómo presentó el [ASESOR] la institución (OBS) y el programa.

CONTEXTO DEL MANUAL:
{manual_enriquecido}

CRITERIOS ESPECÍFICOS (Escala 1-5):

1 = DEFICIENTE / DESORGANIZADO
   - No explica claramente qué es OBS
   - Información del programa confusa o contradictoria
   - No conecta con lo que busca el lead

2 = INSUFICIENTE / DUMP DE INFORMACIÓN
   - Suelta características sin estructura ("dura 12 meses, es online...")
   - No personaliza (mismo discurso para todos)
   - No presenta la institución o lo hace superficialmente
   - No verifica comprensión

3 = CORRECTO / PRESENTACIÓN ESTÁNDAR (Robot)
   - Menciona OBS y sus credenciales básicas
   - Explica características principales del programa de forma ordenada
   - Clara pero genérica (no adapta al lead)
   - Menciona algunos beneficios pero no conecta con objetivo del lead
   - Funcional pero no persuasiva

4 = BUENO / PROPUESTA CONSULTIVA
   - Presenta OBS con credenciales relevantes (rankings, acreditaciones)
   - Personaliza según lo descubierto en investigación
   - Enfatiza BENEFICIOS sobre características
   - Conecta explícitamente con el objetivo del lead ("Esto te ayudará a...")
   - Verifica comprensión ("¿Tiene sentido?")
   - Estructura clara: Institución → Programa → Beneficios para ti

5 = MAESTRÍA / PROPUESTA DE VALOR PERSONALIZADA
   - Presenta OBS como institución líder para SU caso específico
   - El programa es LA SOLUCIÓN al problema del lead
   - Cada característica se traduce en beneficio específico
   - Usa ejemplos o casos de éxito relevantes
   - Anticipa dudas y las resuelve proactivamente
   - El lead expresa que "es justo lo que necesito"

EVIDENCIA REQUERIDA:
Debes identificar MÍNIMO:
- 1 ejemplo de presentación de la institución (OBS)
- 1 ejemplo de explicación del programa
- 1 ejemplo de conexión con necesidad del lead (si existe)
- 1 reacción del lead mostrando interés

FORMATO JSON OBLIGATORIO:
{{
  "puntuacion_1_5": 3,
  "observabilidad": "ALTA" | "MEDIA" | "BAJA",
  "evidencia_principal": "[ASESOR]: Presentación de OBS o programa... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Explicación de características/beneficios... (COPY-PASTE LITERAL)",
    "[ASESOR]: Conexión con necesidad del lead... (COPY-PASTE LITERAL)",
    "[LEAD]: Reacción mostrando interés o comprensión... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "¿Presentó OBS? ¿Personalizó? ¿Beneficios o características? ¿Conectó? ¿Qué faltó para la nota siguiente?",
  "recomendacion_accionable": "Acción específica para mejorar (sin repetir lo ya logrado)",
  "gap_para_5": "Si nota es 3 o 4, explica ESPECÍFICAMENTE qué faltó para alcanzar el 5. Si nota es 5, pon 'N/A - Ya alcanzado'",
  "personalizacion_detectada": true/false,
  "presenta_institucion": true/false,
  "enfoque": "caracteristicas" | "beneficios" | "mixto"
}}

REGLAS CRÍTICAS:
- Todas las evidencias DEBEN ser copy-paste LITERAL (COPY-PASTE exacto)
- Incluye SIEMPRE [ASESOR] o [LEAD]
- Personalización = Adaptar la explicación a LO QUE EL LEAD DIJO que necesitaba
- Diferencia: Características ("12 meses") vs Beneficios ("En 1 año estarás certificado")
⚠️ CALIBRACIÓN JUSTA:
- USA TODA LA ESCALA: si la propuesta de valor es excelente, da 4.5 o 5.0
- NO limites artificialmente las notas. Si cumple los criterios, puntúa en consecuencia
- En "gap_para_5" sé específico (ej: "Faltó usar caso de éxito similar al perfil del lead")
- En "recomendacion_accionable" NO repitas lo que ya hizo bien
"""

        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
Analiza cómo presentó la institución y el programa en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""

        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_propuesta_valor")
        return self._extract_json_safe(resp)
