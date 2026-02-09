"""
Agente Evaluador: Proceso de Admisión y Propuesta Económica (v3.0 - NUEVO)

Este agente evalúa cómo el asesor:
- Explica el proceso de admisión y requisitos
- Presenta la inversión económica y opciones de financiación
- Maneja la conversación sobre precio/valor
- Facilita el acceso sin presionar
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt

class AdmisionEconomicaAgent(BaseEvaluatorAgent):
    """
    Evalúa cómo se explica el proceso de admisión y la propuesta económica

    Criterios clave:
    - Claridad en explicación del proceso de admisión
    - Presentación transparente de inversión y financiación
    - Manejo profesional de la conversación sobre precio
    - Genera confianza sin presión comercial
    - Facilita decisión informada
    """

    def __init__(self):
        super().__init__(nombre_bloque="Proceso de Admisión y Propuesta Económica")

    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """Evalúa admisión y propuesta económica"""

        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual, contexto_usuario)
            confianza = self._calcular_confianza(resultado_raw)

            # Validar que se haya mencionado precio/inversión
            evidencias_extra = resultado_raw.get("evidencias_extra", [])
            menciona_precio = resultado_raw.get("menciona_precio", False)

            if not menciona_precio:
                print(f"   ⚠️ No se detectó mención de inversión/precio")
                confianza *= 0.7

            # Enriquecer recomendación con coaching si hay área de mejora
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")
            gap_para_5 = resultado_raw.get("gap_para_5", "")
            if gap_para_5 and "N/A" not in gap_para_5:
                recomendacion_enriquecida = self.enriquecer_recomendacion_con_coaching(
                    recomendacion_base,
                    area_mejora="presentación de inversión económica y proceso de admisión"
                )
            else:
                recomendacion_enriquecida = recomendacion_base

            return EvaluationResult(
                bloque=self.nombre_bloque,
                puntuacion_1_5=resultado_raw.get("puntuacion_1_5"),
                observabilidad=resultado_raw.get("observabilidad", "MEDIA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=evidencias_extra,
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=recomendacion_enriquecida,
                metadata={
                    "menciona_precio": menciona_precio,
                    "explica_financiacion": resultado_raw.get("explica_financiacion", False),
                    "claridad_admision": resultado_raw.get("claridad_admision", "MEDIA"),
                    "enfoque_valor_vs_precio": resultado_raw.get("enfoque_valor_vs_precio", "precio"),
                    "gap_para_5": gap_para_5
                }
            )

        except Exception as e:
            print(f"   ❌ Error en evaluación de Admisión/Económica: {e}")
            return self._create_fallback_result(str(e))

    def _evaluar_con_llm(self, transcripcion: str, manual: str, contexto_usuario: str = None) -> dict:
        """Llama al LLM con prompt especializado"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion)

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de PROCESO DE ADMISIÓN Y PROPUESTA ECONÓMICA.

TU TAREA: Evaluar cómo el [ASESOR] explica el proceso y la inversión.

CONTEXTO DEL MANUAL:
{manual_enriquecido}

CRITERIOS ESPECÍFICOS (Escala 1-5):

1 = NEGLIGENTE / EVITA EL TEMA
   - No menciona proceso de admisión
   - Evita hablar de precio o es evasivo
   - Genera confusión o desconfianza
   - No aclara pasos a seguir

2 = DEFICIENTE / INFORMACIÓN INCOMPLETA
   - Menciona precio pero sin contexto (suelta cifra y ya)
   - No explica proceso de admisión claramente
   - No menciona opciones de financiación
   - Reacciona defensivamente si el lead pregunta por precio

3 = CORRECTO / PRESENTACIÓN ESTÁNDAR
   - Explica proceso de admisión de forma básica
   - Menciona precio/inversión cuando se pregunta
   - Informa sobre financiación si existe
   - Funcional pero no genera confianza especial
   - Enfoque más en "precio" que en "valor"

4 = BUENO / TRANSPARENCIA PROFESIONAL
   - Explica proceso de admisión paso a paso con claridad
   - Presenta inversión de forma transparente y proactiva
   - Contextualiza precio con valor ("Inversión de X que incluye Y, Z...")
   - Explica opciones de financiación detalladamente
   - Facilita decisión sin presionar
   - Anticipa dudas sobre precio

5 = MAESTRÍA / FACILITADOR DE DECISIÓN
   - Proceso de admisión cristalino y sencillo
   - Presenta inversión como "inversión en ti mismo" vinculada a ROI
   - Compara valor recibido vs inversión (no solo precio)
   - Ofrece múltiples opciones de financiación adaptadas
   - Maneja objeciones de precio con confianza y empatía
   - El lead siente que es transparente y honesto
   - Genera confianza para tomar decisión informada

EVIDENCIA REQUERIDA:
Debes identificar MÍNIMO:
- 1 ejemplo de explicación del proceso de admisión (si se menciona)
- 1 ejemplo de mención de inversión/precio
- 1 ejemplo de financiación o contextualización (si existe)
- 1 reacción del lead sobre el tema económico

FORMATO JSON OBLIGATORIO:
{{
  "puntuacion_1_5": 3,
  "observabilidad": "ALTA" | "MEDIA" | "BAJA",
  "evidencia_principal": "[ASESOR]: Explicación de admisión o inversión... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Mención de precio/inversión... (COPY-PASTE LITERAL)",
    "[ASESOR]: Explicación de financiación... (COPY-PASTE LITERAL)",
    "[LEAD]: Reacción o pregunta sobre precio... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "¿Fue claro en admisión? ¿Transparente con precio? ¿Enfoque valor o precio? ¿Qué faltó para la nota siguiente?",
  "recomendacion_accionable": "Acción específica para mejorar (sin repetir lo ya logrado)",
  "gap_para_5": "Si nota es 3 o 4, explica ESPECÍFICAMENTE qué faltó para alcanzar el 5. Si nota es 5, pon 'N/A - Ya alcanzado'",
  "menciona_precio": true/false,
  "explica_financiacion": true/false,
  "claridad_admision": "ALTA" | "MEDIA" | "BAJA" | "NO_MENCIONADO",
  "enfoque_valor_vs_precio": "valor" | "precio" | "equilibrado"
}}

REGLAS CRÍTICAS:
- Todas las evidencias DEBEN ser copy-paste LITERAL (COPY-PASTE exacto)
- Incluye SIEMPRE [ASESOR] o [LEAD]
- Observabilidad puede ser BAJA si no se mencionó el tema en la llamada
- NO penalices si el tema no surgió naturalmente (puede ser llamada inicial)
- SÍ penaliza si evitó el tema cuando el lead preguntó directamente
- Enfoque "valor" = Habla de ROI, beneficios vs inversión
- Enfoque "precio" = Solo menciona cifra sin contexto
⚠️ CALIBRACIÓN JUSTA:
- USA TODA LA ESCALA: si la presentación económica es excelente, da 4.5 o 5.0
- NO limites artificialmente las notas. Si cumple los criterios, puntúa en consecuencia
- En "gap_para_5" sé específico (ej: "Faltó vincular inversión con ROI del lead")
- En "recomendacion_accionable" NO repitas lo que ya hizo bien
"""

        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
Analiza cómo manejó el proceso de admisión y la propuesta económica:

{transcripcion}

Genera la evaluación en JSON.
IMPORTANTE: Si el tema no se mencionó en la llamada, marca observabilidad como BAJA.
"""

        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_admision_economica")
        return self._extract_json_safe(resp)
