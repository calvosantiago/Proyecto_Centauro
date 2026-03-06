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

            # NOTA: El coaching se integra directamente en el prompt del agente via RAG
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")

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
                    "personalizacion_detectada": personalizacion,
                    "enfoque": resultado_raw.get("enfoque", "caracteristicas"),
                    "presenta_institucion": resultado_raw.get("presenta_institucion", False)
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

CONTEXTO DEL SPEECH Y BUENAS PRÁCTICAS:
{manual_enriquecido}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EL SPEECH COMO CARRETERA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El speech NO es una checklist de frases que el asesor debe decir palabra por palabra.
Es la CARRETERA: define los límites de lo que se puede y no se puede decir/hacer.
Un asesor que presenta el valor con sus propias palabras pero logra conectar con el lead → BUENO.
Lo que evalúas es si se sale de los límites (presentación genérica sin personalización,
no conecta con lo descubierto en investigación) o si conduce bien dentro de ellos.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALCANCE: EVALÚA TODA LA CONVERSACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
La propuesta de valor NO tiene por qué concentrarse en un único bloque de la llamada.
El asesor puede presentar el posicionamiento de la institución, la metodología, el
ecosistema del programa y los beneficios a lo largo de TODA la conversación.
Si el asesor construyó valor desde el inicio y lo mantuvo durante la entrevista,
evalúa el CONJUNTO, no solo el momento en que "debería" haberlo dicho.
Un asesor que distribuye bien la propuesta de valor en toda la conversación = BUENO.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CIRCUNSTANCIAS ATÍPICAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ Si el lead advirtió que tenía poco tiempo disponible, la profundidad de la
presentación estará condicionada por esa limitación. El asesor que condensa bien
priorizando lo más importante bajo presión de tiempo merece reconocimiento, no penalización.
Detecta si ocurrió esta situación y reflétala en el razonamiento como circunstancia atípica.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ADAPTACIÓN AL PERFIL DEL LEAD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El asesor debe adaptar los argumentos al perfil del lead:
- PERFIL JUNIOR / JOVEN: el argumento de las bolsas de trabajo (empleabilidad, red de
  contactos, salidas profesionales) es especialmente relevante y debe recibir énfasis.
  Si el lead es joven y el asesor no menciona las bolsas de empleo → oportunidad perdida.
- PERFIL SENIOR / PROFESIONAL CONSOLIDADO: el argumento clave es el ascenso, el cambio
  de rol, la red directiva, el retorno de inversión profesional.
Detecta el perfil del lead y evalúa si el asesor usó los argumentos correctos para ese perfil.

CRITERIOS DE CALIFICACIÓN (elige UNA de las 3 etiquetas):

🔴 MALO — la presentación es confusa, desorganizada o completamente genérica sin ningún intento de conectar:
   - No explica con claridad qué es OBS o qué incluye el programa
   - Suelta características sin estructura, sin orden y sin conexión
   - No hace ningún intento de conectar con lo que busca el lead
   - La información es confusa, contradictoria o tan genérica que no aporta nada

🟡 MEJORABLE — la presentación existe pero es claramente un discurso de catálogo sin ninguna conexión:
   - Explica OBS y el programa de forma ordenada, pero es el MISMO discurso para cualquier lead
     sin ningún punto de contacto con lo que ESTE lead específico dijo o necesita
   - El asesor no hace referencia en ningún momento a algo que el lead mencionó
   - El lead escucha pero no hay ninguna señal de que sienta que el programa es para él/ella
   ⚠️ NO marques MEJORABLE solo porque la presentación podría haber sido más personalizada.
   MEJORABLE requiere que la conexión con el lead sea completamente ausente o casi nula.

🟢 BUENO — la presentación es clara, estructurada y conecta con lo que importa a este lead:
   - Presenta la institución y el programa con claridad y orden
   - Enfatiza beneficios sobre características (qué le aporta, no solo qué incluye)
   - Conecta al menos un punto clave con el perfil o necesidades del lead
   - Si el lead es junior, destaca empleabilidad y bolsas de trabajo
   - El lead muestra interés o comprensión genuina
   - También es BUENO si el asesor distribuyó bien la propuesta de valor a lo largo de la llamada
   - No es necesario personalizar cada detalle: basta con que el programa se presente como
     relevante para ESTE lead, no solo como un catálogo

EVIDENCIA REQUERIDA:
Debes identificar MÍNIMO:
- 1 ejemplo de presentación de la institución (OBS)
- 1 ejemplo de explicación del programa
- 1 ejemplo de conexión con necesidad del lead (si existe)
- 1 reacción del lead mostrando interés

FORMATO JSON OBLIGATORIO:
{{
  "calificacion": "MALO" | "MEJORABLE" | "BUENO",
  "observabilidad": "ALTA" | "MEDIA" | "BAJA",
  "evidencia_principal": "[ASESOR]: Presentación de OBS o programa... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Explicación de características/beneficios... (COPY-PASTE LITERAL)",
    "[ASESOR]: Conexión con necesidad del lead... (COPY-PASTE LITERAL)",
    "[LEAD]: Reacción mostrando interés o comprensión... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "Responde cada punto: ¿Presentó OBS y el programa con claridad? ¿La propuesta de valor se distribuyó a lo largo de la conversación o solo en un bloque? ¿Hubo presión de tiempo del lead que condicionó la presentación (circunstancia atípica)? ¿El lead es junior/joven — se enfatizaron bolsas de trabajo y empleabilidad? ¿Personalizó conectando con algo que el lead dijo, o fue catálogo puro? ¿Beneficios o características? ¿El lead mostró interés o comprensión? ¿Por qué esa calificación?",
  "recomendacion_accionable": "IMPORTANTE: Combina en un SOLO texto fluido: (1) Qué mejorar en la propuesta de valor, (2) UNA técnica de los libros de ventas del CONTEXTO que aplique, explicando POR QUÉ funciona y dando 2 ejemplos de frases adaptadas a ESTA conversación. Máx 6-8 líneas. NO copies texto literal de los libros.",
  "personalizacion_detectada": true/false,
  "presenta_institucion": true/false,
  "enfoque": "caracteristicas" | "beneficios" | "mixto",
  "perfil_lead": "JUNIOR" | "SENIOR" | "NO_DETERMINADO",
  "bolsas_trabajo_mencionadas": true/false,
  "circunstancia_atipica": "Describe si el lead expresó presión de tiempo u otra condición que limitó la presentación. 'Ninguna' si no ocurrió."
}}

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
DEBES integrarlos en tu "recomendacion_accionable" de forma ORGÁNICA:
- Elige la técnica MÁS relevante para mejorar la propuesta de valor
- Explica POR QUÉ le ayudaría (conecta con la situación real de la llamada)
- Da 2 frases concretas que podría haber usado en ESTA conversación
- NO copies texto literal del libro, adapta con tus palabras
- Menciona de qué libro/autor viene

REGLAS CRÍTICAS:
- Todas las evidencias DEBEN ser copy-paste LITERAL (COPY-PASTE exacto)
- Incluye SIEMPRE [ASESOR] o [LEAD]
- Personalización = Adaptar la explicación a LO QUE EL LEAD DIJO que necesitaba
- Diferencia: Características ("12 meses") vs Beneficios ("En 1 año estarás certificado")
⚠️ REGLAS PARA CALIFICAR:
- Sé decisivo: elige UNA etiqueta.
- BUENO cuando el asesor presenta el programa con claridad y conecta con el lead en al menos
  un punto clave, aunque no personalice absolutamente todo. Una buena presentación estructurada
  con beneficios y algún anclaje al perfil del lead = BUENO.
- MEJORABLE cuando la presentación es correcta pero es 100% catálogo sin NINGÚN punto de
  contacto con lo que este lead específico dijo o necesita. La ausencia total de conexión
  es el criterio, no la imperfección en la personalización.
- MALO cuando la presentación es confusa, desorganizada o el lead no entiende qué se le ofrece.
- Si dudas entre BUENO y MEJORABLE: ¿el asesor mencionó algo del perfil o las palabras del lead?
  Si sí → BUENO. Si la presentación es buena pero sin ningún anclaje personal → MEJORABLE.
- Si hubo presión de tiempo del lead, ajusta la exigencia de profundidad pero no la de claridad.
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.
"""

        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
Analiza cómo presentó la institución y el programa en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""

        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_propuesta_valor")
        return self._extract_json_safe(resp)
