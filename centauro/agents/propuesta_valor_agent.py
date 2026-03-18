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

TONO DE REDACCIÓN: Escribe SIEMPRE en TERCERA PERSONA al referirte al asesor ("el asesor hizo...", "el asesor podría..."). NUNCA uses segunda persona ("hiciste...", "podrías...", "tu objetivo...").

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
ALCANCE: EVALÚA TODA LA CONVERSACIÓN — INSTRUCCIÓN CRÍTICA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANTES DE CALIFICAR: Lee la transcripción COMPLETA de inicio a fin buscando
activamente los siguientes elementos en CUALQUIER momento de la conversación:

  ✓ Posicionamiento de marca / reputación de OBS
  ✓ Metodología del programa (cómo se estudia, formato, carga)
  ✓ Ecosistema del programa (red de contactos, alumni, claustro)
  ✓ Diferenciación institución presencial vs. online
  ✓ Ajuste del perfil del lead con el programa
  ✓ Comparación de perfiles de alumnos
  ✓ Beneficios concretos conectados al lead

Si encuentras ALGUNO de estos elementos en CUALQUIER parte de la conversación
(inicio, mitad o final), cuenta como propuesta de valor presente.

⚠️ SEÑAL DE EXCELENCIA: Si el asesor trabajó el posicionamiento de marca, la
metodología, el ecosistema o el ajuste de perfil desde el INICIO de la conversación
(antes del bloque específico), esto es una estrategia avanzada, no una irregularidad.
Un asesor que construye valor a lo largo de toda la entrevista = BUENO.

NO limites la búsqueda a un bloque o sección específica de la transcripción.
Si los elementos están distribuidos, evalúa el CONJUNTO de la conversación.

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
  "contador_fallos_criticos": 0,
  "calificacion": "MALO" | "MEJORABLE" | "BUENO",
  "observabilidad": "ALTA" | "MEDIA" | "BAJA",
  "evidencia_principal": "[ASESOR]: Presentación de OBS o programa... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Explicación de características/beneficios... (COPY-PASTE LITERAL)",
    "[ASESOR]: Conexión con necesidad del lead... (COPY-PASTE LITERAL)",
    "[LEAD]: Reacción mostrando interés o comprensión... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "En 4-6 líneas de texto fluido, sin listas ni SÍ/NO: explica cómo presentó el asesor la institución y el programa, si conectó con el lead, qué hizo bien y en qué falló. Por qué merece esa calificación. Conecta con lo que ocurrió realmente en la conversación. OBLIGATORIO si la calificación es MALO o MEJORABLE: incluye en el texto al menos una cita literal entre comillas de la conversación que muestre el fallo principal.",
  "recomendacion_accionable": "IMPORTANTE: Combina en un SOLO texto fluido: (1) Qué mejorar en la propuesta de valor, (2) UNA técnica de los libros de ventas del CONTEXTO que aplique, explicando POR QUÉ funciona y dando 2 ejemplos de frases adaptadas a ESTA conversación. Máx 6-8 líneas. NO copies texto literal de los libros.",
  "personalizacion_detectada": true/false,
  "presenta_institucion": true/false,
  "enfoque": "caracteristicas" | "beneficios" | "mixto",
  "perfil_lead": "JUNIOR" | "SENIOR" | "NO_DETERMINADO",
  "bolsas_trabajo_mencionadas": true/false,
  "circunstancia_atipica": "Describe si el lead expresó presión de tiempo u otra condición que limitó la presentación. 'Ninguna' si no ocurrió.",
  "distribucion_propuesta_valor": "DESDE_INICIO" | "DISTRIBUIDA_TODA_ENTREVISTA" | "SOLO_BLOQUE_ESPECIFICO" | "AUSENTE"
}}

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
DEBES integrarlos en tu "recomendacion_accionable" de forma ORGÁNICA:
- Elige la técnica MÁS relevante para mejorar la propuesta de valor
- Explica POR QUÉ le ayudaría (conecta con la situación real de la llamada)
- Da 2 frases concretas que podría haber usado en ESTA conversación
- NO copies texto literal del libro, adapta con tus palabras
- Menciona de qué libro/autor viene
⚠️ VERIFICA ANTES DE RECOMENDAR: Comprueba si el asesor ya demostró en la conversación
el comportamiento que vas a recomendar. Si ya lo hizo, NO lo recomiendes — elige otro
aspecto donde haya margen real de mejora. Recomendar algo que el asesor ya hizo invalida
el coaching.

REGLAS CRÍTICAS:
- Todas las evidencias DEBEN ser copy-paste LITERAL (COPY-PASTE exacto)
- Incluye SIEMPRE [ASESOR] o [LEAD]
- Personalización = Adaptar la explicación a LO QUE EL LEAD DIJO que necesitaba
- Diferencia: Características ("12 meses") vs Beneficios ("En 1 año estarás certificado")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ ANTES DE CALIFICAR — VERIFICACIÓN OBLIGATORIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 CALIBRA con los ejemplos del CONTEXTO:
Los ejemplos de buenas prácticas que aparecen arriba son el estándar de referencia
del programa — no son inspiración para el coaching, son la definición concreta de BUENO.
Si lo que hizo este asesor se parece en espíritu a esos ejemplos (aunque use otras
palabras o no cubra cada punto al pie de la letra), está en zona BUENO.
⚠️ Matiz: un momento aislado que se parece a un ejemplo NO hace BUENO el bloque
completo. Evalúa el CONJUNTO de la fase, no el mejor instante. Los ejemplos marcan
el estándar para el nivel general, no para un fragmento aislado.
Tenlo presente al interpretar los fallos del checklist.

DETENTE. Antes de elegir la calificación, DEBES responder SÍ o NO a cada uno
de estos 5 puntos. Cuenta cuántos tienen respuesta NEGATIVA (= fallo):

  1. ¿Presentó la institución (OBS) con claridad?                                 → SÍ / NO
  2. ¿Explicó el programa con beneficios (no solo características)?                → SÍ / NO
  3. ¿Conectó al menos un punto con el perfil o necesidades del lead?              → SÍ / NO
  4. ¿El lead mostró interés o comprensión genuina?                                → SÍ / NO
  5. ¿Adaptó argumentos al perfil del lead (junior→empleabilidad, senior→ROI)?     → SÍ / NO

CUENTA los NOs. Ese número es tu "contador_fallos_criticos" en el JSON.

🔴 COHERENCIA ENTRE FALLOS Y CALIFICACIÓN:
   Analiza el peso real de cada fallo. Los 5 criterios son todos relevantes para que el
   lead entienda y valore el programa. No presentar la institución con claridad, no
   enfatizar beneficios, no conectar con el lead, que el lead no muestre interés y no
   adaptar los argumentos al perfil son fallos que acumulados dejan la propuesta sin impacto.
   Si la mayoría fallaron, la calificación debe ser MALO. No por un umbral mecánico, sino
   porque una propuesta que no conecta con el lead ni genera interés no cumple su función.
   No detectes múltiples fallos graves y concluyas MEJORABLE: sería incoherente.

⚠️ REGLAS PARA CALIFICAR (después de contar los fallos):
- MALO: múltiples fallos críticos acumulados, O presentación confusa/desorganizada, O el lead no entiende qué se le ofrece.
- MEJORABLE: presentación correcta pero genérica, sin conexión real con la situación del lead. El lead escucha pero no se reconoce en lo que le cuentan. Catálogo sin anclaje personal.
- BUENO: clara, estructurada y conecta con lo que importa a este lead. No es necesario usar todas las técnicas: si la propuesta resonó con el lead y lo movió a avanzar → es BUENO.
- Si dudas entre BUENO y MEJORABLE: ¿el asesor mencionó algo del perfil o las palabras del lead?
  Si sí → BUENO. Si la presentación es buena pero sin ningún anclaje personal → MEJORABLE.
- Si el asesor trabajó elementos de propuesta de valor desde el INICIO de la conversación
  → BUENO sin excepción, independientemente de si repitió todos los elementos en el bloque.
- Si hubo presión de tiempo del lead, ajusta la exigencia de profundidad pero no la de claridad.
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.
"""

        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
ANTES DE EVALUAR: Lee la transcripción completa de principio a fin. El asesor puede
construir la propuesta de valor a lo largo de toda la conversación — datos, estadísticas,
beneficios y anclajes al perfil del lead pueden aparecer en cualquier momento. Identifica
TODOS los momentos en que presentó beneficios o conectó el programa con el lead antes
de decidir la calificación. Evalúa el CONJUNTO, no solo el bloque central de presentación.

Analiza cómo presentó la institución y el programa en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""

        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_propuesta_valor")
        return self._extract_json_safe(resp)
