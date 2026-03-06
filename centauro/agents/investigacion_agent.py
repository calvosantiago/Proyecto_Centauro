"""
Agente Evaluador: Investigación (v5.0)

Fusiona: Apertura + Detección de Necesidades

Evalúa:
- Bienvenida y establecimiento de rapport (primeros minutos)
- Exploración activa del lead: Factor de Compra, inversión esperada,
  competidores explorados, motivaciones, fortalezas/debilidades
- Calidad de preguntas y escucha activa
- Si el asesor aprovechó luego la información que recopiló

NUEVO v5.0:
- Output explícito del Factor de Compra del lead
- Seguimiento de si la info recopilada se usa más adelante en la llamada
- El speech se trata como límite de carretera (no checklist)
- Sin sección "Plan de Acción" redundante
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt

class InvestigacionAgent(BaseEvaluatorAgent):
    """
    Evalúa la fase de investigación completa: apertura + descubrimiento

    Criterios clave:
    - Apertura cálida y profesional que genera confianza
    - Extrae Factor de Compra, inversión esperada y competidores explorados
    - Preguntas de calidad que exploran motivaciones y fortalezas/debilidades
    - Escucha activa (reformula, valida, profundiza)
    - El LEAD habla más que el ASESOR
    - El asesor usa después la información que recogió

    v5.0: Hallazgos estructurados del lead + evaluación del uso posterior de la info
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

            # Hallazgos estructurados del lead
            hallazgos = resultado_raw.get("hallazgos_del_lead", {})

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
                    "feedback_personalizado": resultado_raw.get("feedback_personalizado", ""),
                    "hallazgos_del_lead": hallazgos,
                    "info_aprovechada_despues": resultado_raw.get("info_aprovechada_despues", False),
                    "nota_aprovechamiento": resultado_raw.get("nota_aprovechamiento", "")
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
Eres un AUDITOR ESPECIALIZADO en evaluación de INVESTIGACIÓN en ventas consultivas de formación.

TU TAREA: Evaluar la fase inicial completa (APERTURA + DESCUBRIMIENTO DE NECESIDADES) y extraer
los hallazgos clave que el asesor obtuvo del lead.

CONTEXTO DEL SPEECH Y BUENAS PRÁCTICAS:
{manual_enriquecido}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EL SPEECH COMO CARRETERA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El speech NO es una checklist de frases que el asesor debe decir palabra por palabra.
Es la CARRETERA: define los límites de lo que se puede y no se puede decir/hacer.
El asesor puede moverse con libertad dentro de esa carretera; lo que evalúas es
si se sale de los límites (mala investigación) o si conduce bien dentro de ellos.
Un asesor que usa sus propias palabras pero logra el objetivo de la fase → BUENO.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUÉ DEBES EXTRAER DE LA INVESTIGACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
La investigación tiene como objetivo RECOPILAR INFORMACIÓN que se usará más adelante
para personalizar la propuesta y el cierre. Los datos clave a detectar son:

1. FACTOR DE COMPRA: ¿Qué necesita realmente el lead? ¿Qué problema o situación lo
   trajo aquí? (No solo "quiero crecer" — busca el dolor o deseo específico)
   Preguntas típicas: "¿Para qué buscas el máster, qué necesitas?" / "¿Qué cambiarías
   de tu situación actual?"

2. PERFIL FINANCIERO: ¿El asesor exploró el contexto económico del lead?
   NO busques discusiones de precio — lo que importa es calificar quién y cómo paga:
   ¿Es inversión propia o la financia la empresa? ¿Si es perfil junior, cuenta con apoyo familiar?
   ¿Lleva tiempo buscando y tiene un presupuesto destinado a su formación?
   Este perfil permite al asesor abordar la parte económica de forma personalizada más adelante.
   Preguntas típicas: "¿La formación la asumes tú o tienes apoyo de empresa?" / "¿Es una
   inversión que harías tú mismo o tienes respaldo familiar?"

3. COMPETIDORES EXPLORADOS: ¿Está comparando con otras instituciones o programas?
   ¿Qué otras opciones está evaluando?

4. MOTIVACIONES PROFUNDAS: ¿Por qué ahora? ¿Qué cambió en su situación?
   ¿Qué espera conseguir con el máster?

5. FORTALEZAS Y DEBILIDADES: ¿Qué sabe el lead de sí mismo? ¿Qué le falta?
   Preguntas típicas: "¿Cuáles son tus fortalezas y debilidades en lo que haces?"

6. INFORMACIÓN APROVECHABLE: ¿Hay datos personales, profesionales o emocionales
   que el asesor podría usar más adelante para personalizar el discurso?

7. RECONDUCCIÓN (si aplica): ¿El lead llegó interesado en un programa o formato diferente
   al que finalmente se le ofreció? Si el asesor detectó esto durante la investigación y
   recondujo al lead hacia la opción adecuada, es un indicador de calidad consultiva alta.

⚠️ ALCANCE DE LOS HALLAZGOS:
Los "hallazgos_del_lead" reflejan lo que se aprendió en TODA la conversación, no solo
en los primeros minutos. Si el asesor exploró competidores o el perfil financiero más
adelante en la llamada, igualmente cuenta como "explorado".
La CALIFICACIÓN, en cambio, evalúa principalmente la FASE INICIAL de investigación.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITERIOS DE CALIFICACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 MALO — el asesor no investiga o la investigación es tan superficial que no aporta nada útil:
   - Va directo a presentar sin explorar la situación del lead
   - Hace 1-2 preguntas de trámite y no profundiza en ninguna
   - No descubre el Factor de Compra ni ninguna motivación relevante
   - El lead no tuvo espacio real para abrirse
   - También: hace preguntas pero ignora las respuestas o no las aprovecha en absoluto
   - Si faltan MÚLTIPLES elementos clave (factor de compra, perfil financiero, puntos de dolor
     o de ilusión, objetivos concretos) y lo que hay es genérico y vago → es MALO, no MEJORABLE
   EJEMPLO: "[ASESOR]: Hola, te cuento del máster. Cuesta 10mil..." (sin preguntar nada)

🟡 MEJORABLE — investiga pero sin lograr profundidad ni información aprovechable:
   - Hace preguntas pero son superficiales o genéricas y no repregunta cuando el lead se abre
   - Recopila datos básicos (nombre, trabajo, motivación vaga) pero no llega al Factor de Compra
   - El lead da respuestas cortas porque el asesor no invita a desarrollar
   - La información obtenida es insuficiente para personalizar nada después
   EJEMPLO: "[ASESOR]: ¿Qué te motivó? [LEAD]: Quiero crecer. [ASESOR]: Perfecto, te cuento..."

🟢 BUENO — el asesor investiga activamente y obtiene información útil que podría usar:
   - Identifica el Factor de Compra o al menos las motivaciones reales del lead
   - Repregunta o profundiza en al menos un punto relevante
   - El lead comparte información personal, profesional o emocional de valor
   - La apertura genera confianza y el lead habla con comodidad
   - No es necesario cubrir TODOS los puntos: basta con que la investigación sea real y aprovechable
   - Si el asesor detecta que el lead viene por un programa/formato diferente y lo reconduce
     exitosamente, valóralo como investigación consultiva de alta calidad → contribuye a BUENO
   - Si el asesor recupera el Factor de Compra más adelante para personalizar la propuesta
     o el cierre ("como me comentabas antes que..."), esto confirma y refuerza el BUENO
   EJEMPLO: "[ASESOR]: ¿Qué significa crecer para ti? [LEAD]: [se abre]... [ASESOR]: Suena a que..."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USO POSTERIOR DE LA INFORMACIÓN — AFECTA LA CALIFICACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Analiza también el RESTO de la transcripción (no solo la fase inicial):
¿El asesor usó después la información que recopiló? ¿Personalizó la propuesta con
los datos del lead? ¿O dejó la información sin aprovechar y siguió con el discurso genérico?

Pon especial atención al Factor de Compra:

✅ Si el asesor lo identificó Y lo recuperó más adelante para argumentar, rebatir
   objeciones o cerrar ("como me comentabas que necesitas X, este programa es ideal
   porque...") → indicador de calidad consultiva de primer nivel → refuerza BUENO.

⚠️ Si el asesor identificó el Factor de Compra pero NO lo usó en NINGÚN momento
   posterior de la conversación (ni en propuesta de valor, ni en objeciones, ni en cierre,
   ni de ninguna forma) → la investigación fue mecánica, no consultiva.
   CONDICIÓN ESTRICTA: solo aplica si de verdad no hay ni una sola referencia posterior
   al Factor de Compra. Si lo usó aunque sea una vez, aunque sea brevemente → no baja nota.
   IMPACTO EN CALIFICACIÓN cuando SÍ aplica:
   - Si la investigación era BUENO por calidad de preguntas, pero el Factor de Compra
     no se usó en absoluto → baja a MEJORABLE.
   - Si además la investigación fue superficial Y no se usó el Factor de Compra →
     refuerza MALO o MEJORABLE según el caso.
   OBLIGATORIO: si bajas la nota por este motivo, debes escribir explícitamente en el
   razonamiento: "Bajo la calificación de [X] a [Y] porque el Factor de Compra identificado
   no fue utilizado en ningún momento posterior de la conversación." Sin esta declaración
   explícita, no apliques la bajada de nota.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVIDENCIA REQUERIDA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Debes identificar MÍNIMO:
- 1 ejemplo de apertura/bienvenida del [ASESOR]
- 3 ejemplos de preguntas clave del [ASESOR]
- 2 ejemplos de respuestas elaboradas del [LEAD]
- 1 indicio de escucha activa (si existe)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORMATO JSON OBLIGATORIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{{
  "contador_fallos_criticos": 0,
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
  "hallazgos_del_lead": {{
    "factor_de_compra": "Descripción del dolor/necesidad real del lead. 'No detectado' si no se exploró.",
    "perfil_financiero": "Perfil financiero del lead: ¿quién paga y cómo? NO hace falta que se haya hablado de importes ni de precio. Basta con que el lead haya indicado su situación financiera de cualquier forma. Ejemplos que SIEMPRE cuentan como 'explorado': 'lo asumo por cuenta propia', 'lo pago yo mismo', 'mi empresa me lo cubre', 'mis padres me ayudan', 'estoy buscando financiación'. Escribe el perfil detectado. 'No explorado' SOLO si no hubo absolutamente ninguna referencia a quién paga ni cómo en toda la llamada.",
    "competidores": "Otras opciones que el lead mencionó estar evaluando. SIEMPRE cuenta como explorado si: (a) el lead lo mencionó espontáneamente, O (b) el asesor preguntó y el lead respondió nombrando instituciones o países donde ha consultado. Escribe las instituciones o referencias mencionadas. 'No explorado' SOLO si no hubo ninguna referencia en toda la llamada.",
    "reconduccion": "Si el asesor detectó que el lead venía interesado en un programa/formato diferente y lo recondujo exitosamente, describe cómo lo gestionó. 'No aplica' si no ocurrió.",
    "motivacion_principal": "Por qué quiere el máster y por qué ahora.",
    "fortalezas_debilidades": "Lo que el lead dijo sobre sí mismo. 'No explorado' si no se preguntó.",
    "datos_aprovechables": "Resumen en 2-3 frases de la info clave que el asesor podría usar para personalizar."
  }},
  "info_aprovechada_despues": true | false,
  "nota_aprovechamiento": "Explica brevemente si el asesor usó (o no) la info recopilada más adelante en la llamada. Cita un ejemplo específico si lo hay.",
  "razonamiento": "En 4-6 líneas de texto fluido, sin listas ni SÍ/NO: explica qué logró el asesor en la investigación, qué calidad tuvo la apertura y las preguntas, qué información obtuvo del lead y por qué merece esa calificación. Conecta con lo que ocurrió realmente en la conversación.",
  "recomendacion_accionable": "Qué mejorar + UNA técnica concreta de los libros de ventas del CONTEXTO que aplique, con 2 frases que el asesor podría haber usado en ESTA conversación. Máximo 6-8 líneas. No copies texto literal, adapta con tus palabras.",
  "calidad_apertura": "EXCELENTE | BUENA | CORRECTA | DEFICIENTE",
  "indicios_escucha_activa": true | false,
  "tecnicas_detectadas": ["lista de técnicas que usó el asesor"],
  "feedback_personalizado": "Mensaje DIRECTO al asesor: reconoce algo ESPECÍFICO que hizo bien, sugiere UNA mejora concreta con ejemplo de frase. Máximo 3-4 líneas."
}}

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
- COMPETIDORES: Marca como "explorado" si (a) el lead mencionó espontáneamente otras
  instituciones, O (b) el asesor preguntó y el lead respondió nombrando instituciones,
  países o programas que consultó. Si el asesor preguntó y el lead respondió → SIEMPRE explorado.
- PERFIL FINANCIERO: Marca como "explorado" si en cualquier punto de la conversación
  el lead indicó quién paga o cómo. Ejemplos que SIEMPRE cuentan: "lo asumo por cuenta
  propia", "lo pago yo", "mi empresa me lo cubre", "mis padres me ayudan", "busco financiación".
  NO se necesita que se haya hablado de importes o precios concretos.
- NEVER marques 'No explorado' si hay cualquier indicio de que el tema se tocó, aunque
  haya sido brevemente o en cualquier momento de la conversación

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ ANTES DE CALIFICAR — VERIFICACIÓN OBLIGATORIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DETENTE. Antes de elegir la calificación, DEBES responder SÍ o NO a cada uno
de estos 5 puntos. Cuenta cuántos tienen respuesta NEGATIVA (= fallo):

  1. ¿Exploró el Factor de Compra (dolor/necesidad real, no solo "quiero crecer")? → SÍ / NO
  2. ¿Exploró el perfil financiero (quién paga, cómo)?                            → SÍ / NO
  3. ¿Hizo preguntas de profundización (repreguntó, no se quedó en la superficie)?  → SÍ / NO
  4. ¿El lead tuvo espacio real para hablar y abrirse?                             → SÍ / NO
  5. ¿Obtuvo información aprovechable para personalizar la propuesta después?       → SÍ / NO

CUENTA los NOs. Ese número es tu "contador_fallos_criticos" en el JSON.

🔴 COHERENCIA ENTRE FALLOS Y CALIFICACIÓN:
   Analiza el peso real de cada fallo. Los 5 criterios son esenciales para que la
   investigación sea útil. Sin Factor de Compra, sin perfil financiero del lead, sin
   preguntas de profundización, sin espacio real para que el lead se abra y sin
   información aprovechable, la investigación fue superficial. Si la mayoría fallaron,
   la calificación debe ser MALO. No por un umbral mecánico, sino porque sin información
   real del lead, nada de lo que sigue puede personalizarse. No detectes múltiples fallos
   graves y concluyas MEJORABLE: sería incoherente con tu propio análisis.

⚠️ REGLAS PARA CALIFICAR (después de contar los fallos):
- MALO: múltiples fallos críticos acumulados, O no investiga, O preguntas puro trámite sin ningún valor.
- MEJORABLE: 1-2 fallos. Hay intento pero el resultado es escaso para personalizar.
- BUENO: ningún fallo o fallos menores. Obtiene información real y aprovechable del lead.
- Si dudas entre BUENO y MEJORABLE: ¿el asesor sabe algo útil del lead después de esta fase? Si sí → BUENO.
- Si dudas entre MEJORABLE y BUENO y el asesor usó el Factor de Compra más adelante → inclínate por BUENO.
- En "recomendacion_accionable" NO repitas lo que ya hizo bien, solo lo que falta mejorar.
"""

        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
Analiza la fase de INVESTIGACIÓN (apertura + descubrimiento) en esta conversación.
Extrae los hallazgos del lead de forma estructurada y evalúa si el asesor los aprovechó
más adelante en la llamada.

{transcripcion}

Genera la evaluación en JSON.
"""

        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_investigacion")
        return self._extract_json_safe(resp)
