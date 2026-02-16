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

            # Detectar técnicas
            tecnicas_detectadas = resultado_raw.get("tecnicas_detectadas", [])
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")

            # NOTA: El coaching se aplica en batch desde el orchestrator para optimizar llamadas API

            return EvaluationResult(
                bloque=self.nombre_bloque,
                calificacion=resultado_raw.get("calificacion"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=evidencias_extra,
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=recomendacion_base,
                metadata={
                    "calidad_apertura": resultado_raw.get("calidad_apertura", "MEDIA"),
                    "num_preguntas_detectadas": len([e for e in evidencias_extra if "[ASESOR]" in e and "?" in e]),
                    "indicios_escucha_activa": resultado_raw.get("indicios_escucha_activa", False),
                    "tecnicas_detectadas": tecnicas_detectadas,
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

CRITERIOS DE CALIFICACIÓN (elige UNA de las 3 etiquetas):

🔴 MALO — cuando el asesor NO investiga o lo hace de forma claramente insuficiente:
   - Apertura fría o inexistente, va directo a vender sin explorar
   - Solo hace 1-2 preguntas superficiales sin profundizar
   - Habla más que el lead en la fase de investigación
   - No descubre ninguna motivación, necesidad ni situación del lead
   EJEMPLO: "[ASESOR]: Hola, te cuento del máster. Cuesta 10mil..." (sin preguntar nada)
   EJEMPLO: "[ASESOR]: ¿Dónde trabajas? [LEAD]: En finanzas. [ASESOR]: OK, te explico el programa..."

🟡 MEJORABLE — cuando el asesor investiga con protocolo básico pero sin profundidad real:
   - Apertura adecuada, sigue el script estándar (trabajo, experiencia, motivación)
   - Funcional pero sin profundidad emocional ni descubrimiento del dolor real
   - Hace preguntas pero no repregunta ni valida lo que le dicen
   - El lead da respuestas cortas o genéricas y el asesor no profundiza
   EJEMPLO: "[ASESOR]: ¿Qué te motivó? [LEAD]: Quiero crecer. [ASESOR]: Perfecto, te cuento el programa..."

🟢 BUENO — cuando el asesor hace una investigación activa y consultiva:
   - Apertura cálida y personalizada que genera confianza real
   - Preguntas abiertas que llevan a motivaciones y necesidades profundas
   - Repregunta, reformula y valida emocionalmente lo que el lead comparte
   - El lead habla más que el asesor y se siente genuinamente escuchado
   - Descubre algún dolor, urgencia o contexto relevante que va más allá del script
   EJEMPLO: "[ASESOR]: Vi que trabajas en finanzas hace 8 años. ¿Qué te hizo explorar un MBA ahora?"
   EJEMPLO: "[ASESOR]: ¿Qué significa crecer para ti? [LEAD]: [se abre]... [ASESOR]: Suena a que dominas lo técnico pero te frustra no poder influir más. ¿Es así?"

EVIDENCIA REQUERIDA:
Debes identificar MÍNIMO:
- 1 ejemplo de apertura/bienvenida del [ASESOR]
- 3 ejemplos de preguntas clave del [ASESOR]
- 2 ejemplos de respuestas elaboradas del [LEAD]
- 1 indicio de escucha activa (si existe)

FORMATO JSON OBLIGATORIO:
{{
  "calificacion": "MALO" | "MEJORABLE" | "BUENO",
  "observabilidad": "ALTA" | "MEDIA" | "BAJA",
  "evidencia_principal": "[ASESOR]: Pregunta o momento clave de apertura...",
  "evidencias_extra": [
    "[ASESOR]: Pregunta investigativa 1...",
    "[LEAD]: Respuesta del lead compartiendo info relevante...",
    "[ASESOR]: Pregunta de profundización...",
    "[LEAD]: Respuesta elaborada revelando motivación...",
    "[ASESOR]: Validación o reformulación (si hay)..."
  ],
  "razonamiento": "Análisis técnico: ¿Qué hizo bien en apertura? ¿Calidad de preguntas? ¿Por qué merece esa calificación?",
  "recomendacion_accionable": "IMPORTANTE: Combina en un SOLO texto fluido: (1) Qué mejorar, (2) UNA técnica de los libros de ventas del CONTEXTO que aplique, explicando POR QUÉ funciona y dando 2 ejemplos de frases. Máximo 6-8 líneas. NO copies texto literal de los libros, explícalo con tus palabras adaptado a esta conversación específica.",
  "calidad_apertura": "EXCELENTE | BUENA | CORRECTA | DEFICIENTE",
  "indicios_escucha_activa": true/false,
  "tecnicas_detectadas": ["lista de técnicas que usó el asesor"],
  "feedback_personalizado": "Mensaje DIRECTO al asesor: reconoce algo ESPECÍFICO que hizo bien, sugiere UNA mejora concreta con ejemplo de frase. Máximo 3-4 líneas."
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

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
DEBES integrarlos en tu "recomendacion_accionable" de forma ORGÁNICA:
- Elige la técnica MÁS relevante para lo que le faltó al asesor
- Explica POR QUÉ le ayudaría (conecta con la situación real de la llamada)
- Da 2 frases concretas que podría haber usado en ESTA conversación
- NO copies texto literal del libro, adapta con tus palabras
- Menciona de qué libro/autor viene la técnica (ej: "Como sugiere Rackham en SPIN Selling...")

REGLAS CRÍTICAS:
- Todas las evidencias DEBEN ser copy-paste LITERAL de la transcripción
- Incluye SIEMPRE [ASESOR] o [LEAD] en cada cita
- Evalúa TANTO la apertura COMO la investigación
- NO penalices si el lead es cerrado, penaliza si el asesor no intentó abrir
- Sé técnico, no motivacional

⚠️ REGLAS PARA CALIFICAR:
- Sé decisivo: elige UNA etiqueta. No existe el término medio.
- BUENO no requiere perfección, requiere que el asesor haya investigado activamente y el lead se haya abierto.
- MEJORABLE es el estándar: protocolo seguido pero sin profundidad real.
- MALO cuando el asesor claramente NO investigó o fue insuficiente.
- En "recomendacion_accionable" NO repitas lo que ya hizo bien, solo lo que falta mejorar.
"""

        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
Analiza la fase de INVESTIGACIÓN (apertura + descubrimiento) en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""

        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_investigacion")
        return self._extract_json_safe(resp)
