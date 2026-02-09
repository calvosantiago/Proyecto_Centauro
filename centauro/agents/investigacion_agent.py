"""
Agente Evaluador: Investigación (v4.1)

Fusiona: Apertura + Detección de Necesidades

Evalúa:
- Bienvenida y establecimiento de rapport (primeros minutos)
- Exploración de necesidades, motivaciones y situación del lead
- Calidad de preguntas y escucha activa

NUEVO v4.1:
- Detección de técnicas avanzadas (SPIN, Mirroring, etc.)
- Feedback personalizado con coaching de libros de ventas
- Bonificación por técnicas similares a buenas prácticas
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

    v4.1: Detecta y premia técnicas avanzadas, genera coaching personalizado
    """

    def __init__(self):
        super().__init__(nombre_bloque="Investigación")

    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """Evalúa investigación (apertura + detección necesidades)"""

        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual, contexto_usuario)
            confianza = self._calcular_confianza(resultado_raw)

            # Validar evidencias múltiples
            evidencias_extra = resultado_raw.get("evidencias_extra", [])
            if len(evidencias_extra) < 3:
                print(f"   ⚠️ Pocas evidencias de investigación ({len(evidencias_extra)})")
                confianza *= 0.85

            # NUEVO: Detectar técnicas y enriquecer recomendación
            tecnicas_detectadas = resultado_raw.get("tecnicas_detectadas", [])
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")
            gap_para_5 = resultado_raw.get("gap_para_5", "")

            # Enriquecer con coaching si hay área de mejora clara
            if gap_para_5 and "N/A" not in gap_para_5:
                recomendacion_enriquecida = self.enriquecer_recomendacion_con_coaching(
                    recomendacion_base,
                    area_mejora="preguntas de descubrimiento y apertura"
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
                    "calidad_apertura": resultado_raw.get("calidad_apertura", "MEDIA"),
                    "num_preguntas_detectadas": len([e for e in evidencias_extra if "[ASESOR]" in e and "?" in e]),
                    "indicios_escucha_activa": resultado_raw.get("indicios_escucha_activa", False),
                    "tecnicas_detectadas": tecnicas_detectadas,
                    "gap_para_5": gap_para_5,
                    "feedback_personalizado": resultado_raw.get("feedback_personalizado", "")
                }
            )

        except Exception as e:
            print(f"   ❌ Error en evaluación de Investigación: {e}")
            return self._create_fallback_result(str(e))

    def _evaluar_con_llm(self, transcripcion: str, manual: str, contexto_usuario: str = None) -> dict:
        """Llama al LLM con prompt especializado en investigación completa"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion)

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de INVESTIGACIÓN en ventas consultivas.

TU TAREA: Evaluar la fase inicial completa (APERTURA + DESCUBRIMIENTO DE NECESIDADES).

CONTEXTO DEL MANUAL:
{manual_enriquecido}

CRITERIOS ESPECÍFICOS (Escala DECIMAL 1.0-5.0):
⚠️ IMPORTANTE: Usa toda la escala. Un buen asesor MERECE un 4.5 o 5.0.

1.0-1.5 = NEGLIGENTE
   - Apertura fría o inexistente, va directo a vender
   EJEMPLO: "[ASESOR]: Hola, te cuento del máster. Cuesta 10mil..."

2.0-2.5 = DEFICIENTE
   - Apertura mecánica, solo 1-2 preguntas básicas, no profundiza
   EJEMPLO: "[ASESOR]: ¿Dónde trabajas? [LEAD]: En finanzas. [ASESOR]: OK, te explico el programa..."

3.0 = CORRECTO / PROTOCOLO ESTÁNDAR
   - Apertura adecuada, pregunta trabajo/experiencia/motivación (script estándar)
   - Funcional pero sin profundidad emocional, no descubre el dolor real
   EJEMPLO: "[ASESOR]: ¿Qué te motivó? [LEAD]: Quiero crecer. [ASESOR]: Perfecto, te cuento..."

3.5 = CORRECTO CON DESTELLOS
   - Todo lo del 3.0 PERO con alguna repregunta o validación emocional básica
   EJEMPLO: "[ASESOR]: ¿Qué te motivó? [LEAD]: Crecer. [ASESOR]: ¿Qué significa crecer para ti?"

4.0 = BUENO / INVESTIGACIÓN ACTIVA
   - Apertura cálida y personalizada, preguntas abiertas consistentes
   - Repregunta y reformula, toca motivaciones profundas
   EJEMPLO: "[ASESOR]: Vi que trabajas en finanzas hace 8 años. ¿Qué te hizo explorar un MBA ahora?"

4.5 = MUY BUENO
   - Descubre algún dolor o urgencia real, lead se abre y comparte
   - Usa técnicas de profundización (repregunta el porqué, valida emociones)
   - El lead habla con confianza y soltura

5.0 = EXCELENTE / DISCOVERY CONSULTIVO
   - Conexión genuina desde el inicio
   - Profundiza en motivaciones hasta llegar al dolor real y la urgencia
   - Validaciones emocionales naturales y efectivas
   - El lead se siente escuchado y comparte información valiosa
   EJEMPLO: "[ASESOR]: Cuéntame, ¿qué te ha funcionado bien y qué te está costando más? [LEAD]: [se abre sobre frustración] [ASESOR]: Suena a que la parte técnica la dominas, pero te frustra no tener herramientas para influir. ¿Es así?"

EVIDENCIA REQUERIDA:
Debes identificar MÍNIMO:
- 1 ejemplo de apertura/bienvenida del [ASESOR]
- 3 ejemplos de preguntas clave del [ASESOR]
- 2 ejemplos de respuestas elaboradas del [LEAD]
- 1 indicio de escucha activa (si existe)

FORMATO JSON OBLIGATORIO:
{{
  "puntuacion_1_5": 3.0,  ← USA DECIMALES: 3.0, 3.5, 4.0, 4.5, etc.
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
  "indicios_escucha_activa": true/false,
  "tecnicas_detectadas": ["lista de técnicas que usó el asesor, ej: 'repregunta', 'validación emocional', 'SPIN parcial', 'mirroring'"],
  "feedback_personalizado": "Mensaje DIRECTO al asesor mencionando su NOMBRE si aparece, reconociendo algo ESPECÍFICO que hizo bien, y sugiriendo UNA mejora concreta con ejemplo de frase que podría usar"
}}

🎯 FEEDBACK PERSONALIZADO - INSTRUCCIONES CRÍTICAS:
El campo "feedback_personalizado" debe ser un mensaje que el asesor pueda leer y sentir que es PARA ÉL/ELLA.

MALO (genérico): "El asesor debería hacer más preguntas abiertas"
BUENO (personalizado): "Hiciste bien al preguntar sobre su experiencia en finanzas. Para subir al siguiente nivel, cuando te dijo 'quiero crecer', podrías haber preguntado: '¿Qué significa crecer para ti? ¿Qué te gustaría estar haciendo en 2 años que hoy no puedes?'"

MALO (genérico): "Falta profundizar en las motivaciones"
BUENO (personalizado): "Cuando María te contó que lleva 8 años en su empresa, ahí tenías una oportunidad de oro. Podrías haber dicho: 'María, 8 años es mucho tiempo. ¿Qué ha cambiado en este último año que te hizo pensar en un máster ahora?'"

REGLAS DEL FEEDBACK PERSONALIZADO:
1. USA el nombre del lead si aparece en la transcripción
2. CITA algo específico que el asesor dijo o hizo
3. DA un ejemplo de frase alternativa que podría usar
4. SÉ constructivo, no crítico
5. Máximo 3-4 líneas, directo al grano

REGLAS CRÍTICAS:
- Todas las evidencias DEBEN ser copy-paste LITERAL de la transcripción
- Incluye SIEMPRE [ASESOR] o [LEAD] en cada cita
- Evalúa TANTO la apertura COMO la investigación
- NO penalices si el lead es cerrado, penaliza si el asesor no intentó abrir
- Sé técnico, no motivacional

⚠️ CALIBRACIÓN JUSTA - LEE ESTO:
- USA TODA LA ESCALA: si el asesor hizo un trabajo excelente, da 4.5 o 5.0
- NO limites artificialmente las notas. Si cumple los criterios de 5.0, da 5.0
- USA DECIMALES: 3.0, 3.5, 4.0, 4.5, 5.0
- En "gap_para_5" explica QUÉ FALTÓ específicamente con ejemplos concretos
- En "recomendacion_accionable" NO repitas lo que ya hizo bien, solo lo que falta
- IMPORTANTE: Un asesor que profundiza, repregunta y conecta con el lead merece 4.5+
"""

        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
Analiza la fase de INVESTIGACIÓN (apertura + descubrimiento) en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""

        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_investigacion")
        return self._extract_json_safe(resp)
