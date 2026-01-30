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

    def _evaluar_con_llm(self, transcripcion: str, manual: str) -> dict:
        """Llama al LLM con prompt especializado en investigación completa"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion)

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de INVESTIGACIÓN en ventas consultivas.

TU TAREA: Evaluar la fase inicial completa (APERTURA + DESCUBRIMIENTO DE NECESIDADES).

CONTEXTO DEL MANUAL:
{manual_enriquecido}

CRITERIOS ESPECÍFICOS (Escala DECIMAL 1.0-5.0):
⚠️ IMPORTANTE: Ahora puedes usar .0 o .5 (ejemplo: 3.5, 4.0, 4.5)

🎯 REFERENCIA DE CALIBRACIÓN: La mayoría de llamadas deben estar en 3.0-3.5 (CORRECTO).
   El 4.0+ es para casos con evidencia clara de técnicas avanzadas.

1.0-1.5 = NEGLIGENTE / DESASTRE
   - Apertura fría o inexistente
   - Cero preguntas sobre el lead
   - Va directo a vender
   EJEMPLO: "[ASESOR]: Hola, te cuento del máster. Cuesta 10mil..."

2.0-2.5 = DEFICIENTE / MÍNIMO
   - Apertura mecánica: "Hola, soy Juan"
   - Solo 1-2 preguntas básicas: "¿En qué trabajas?"
   - No construye rapport ni profundiza
   EJEMPLO: "[ASESOR]: ¿Dónde trabajas? [LEAD]: En finanzas. [ASESOR]: OK, te explico el programa..."

3.0 = CORRECTO / PROTOCOLO ESTÁNDAR ⭐ (NOTA MÁS COMÚN)
   - Apertura adecuada: "Hola María, gracias por tu interés. Cuéntame un poco sobre ti"
   - Pregunta trabajo, experiencia, motivación (script estándar)
   - Funcional pero SIN profundidad emocional
   - NO descubre el dolor real
   EJEMPLO: "[ASESOR]: ¿Qué te motivó a buscar este máster? [LEAD]: Quiero crecer profesionalmente. [ASESOR]: Perfecto, te cuento..."

3.5 = CORRECTO CON DESTELLOS
   - Todo lo del 3.0 PERO con 1-2 momentos de repregunta
   - Alguna validación emocional básica: "Entiendo"
   EJEMPLO: "[ASESOR]: ¿Qué te motivó? [LEAD]: Crecer. [ASESOR]: ¿Qué significa crecer para ti?"

4.0 = BUENO / INVESTIGACIÓN ACTIVA
   - Apertura cálida y personalizada
   - Preguntas abiertas consistentes
   - Repregunta para clarificar: "¿A qué te refieres con...?"
   - Reformula: "Entiendo que buscas..."
   - Empieza a tocar motivaciones profundas (aunque no llega al DOLOR)
   EJEMPLO: "[ASESOR]: Vi que trabajas en finanzas hace 8 años. ¿Qué te hizo decidir explorar un MBA ahora? [LEAD]: Quiero liderar proyectos. [ASESOR]: ¿Qué significa liderar para ti?"

4.5 = MUY BUENO / CASI MAESTRÍA
   - Todo lo del 4.0 PERO descubre algún dolor o urgencia
   - Lead habla 60%+ del tiempo
   - Usa 1-2 técnicas avanzadas (SPIN parcial, validación emocional fuerte)

5.0 = MAESTRÍA / DISCOVERY CONSULTIVO (RARO)
   - Apertura que conecta emocionalmente desde el inicio
   - Pregunta el PORQUÉ detrás de CADA respuesta (técnica SPIN completa)
   - Descubre dolor real Y urgencia
   - Lead habla 70%+ del tiempo
   - Validaciones emocionales: "Tiene sentido que te sientas así..."
   EJEMPLO: "[ASESOR]: María, vi en tu perfil que llevas 10 años en finanzas corporativas. Cuéntame, ¿qué te ha funcionado bien y qué te está costando más últimamente? [LEAD]: Pues... [habla 3 minutos sobre frustración con liderazgo] [ASESOR]: Suena a que la parte técnica la dominas, pero te frustra no tener herramientas para influir. ¿Es así? ¿Qué pasa si esto no cambia?"

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

⚠️ CALIBRACIÓN ESTRICTA - LEE ESTO:
- El 3.0 es "CORRECTO/ESTÁNDAR" - NO es malo, es lo esperado en la mayoría de casos
- NO des 4.0+ solo porque "fue una llamada decente" - el 4.0 requiere técnicas avanzadas evidentes
- USA DECIMALES: Si está entre 3.0 y 4.0, usa 3.5
- El 5.0 es MUY RARO - solo para ejecución impecable con técnicas SPIN completas
- En "gap_para_5" explica QUÉ FALTÓ específicamente con ejemplos concretos
- En "recomendacion_accionable" NO repitas lo que ya hizo bien, solo lo que falta
"""

        prompt_usuario = f"""
Analiza la fase de INVESTIGACIÓN (apertura + descubrimiento) en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""

        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_investigacion")
        return self._extract_json_safe(resp)
