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

            # Tope universal: 3+ fallos críticos = MALO
            contador_fallos = resultado_raw.get("contador_fallos_criticos", 0)
            cal_tmp, raz_tmp = self._aplicar_tope_fallos_criticos(
                resultado_raw.get("calificacion"), contador_fallos, resultado_raw.get("razonamiento", "")
            )
            if cal_tmp != resultado_raw.get("calificacion"):
                resultado_raw["calificacion"] = cal_tmp
                resultado_raw["razonamiento"] = raz_tmp

            # Validar evidencia de personalización
            evidencias_extra = resultado_raw.get("evidencias_extra", [])
            personalizacion = resultado_raw.get("personalizacion_detectada", False)

            if not personalizacion:
                print(f"   ⚠️ No se detectó personalización en la propuesta")
                confianza *= 0.85

            # NOTA: El coaching se integra directamente en el prompt del agente via RAG
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")
            mejoras = self._formato_mejoras(resultado_raw.get("mejoras", []))

            return EvaluationResult(
                bloque=self.nombre_bloque,
                calificacion=resultado_raw.get("calificacion"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=evidencias_extra,
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=recomendacion_base,
                mejoras=mejoras,
                metadata={
                    "personalizacion_detectada": personalizacion,
                    "enfoque": resultado_raw.get("enfoque", "caracteristicas"),
                    "presenta_institucion": resultado_raw.get("presenta_institucion", False),
                    "afirmaciones_superlativas_detectadas": resultado_raw.get("afirmaciones_superlativas_detectadas", False),
                    "superlativas_justificadas": resultado_raw.get("superlativas_justificadas", False),
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
AFIRMACIONES SUPERLATIVAS — DEBEN JUSTIFICARSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cuando el asesor hace afirmaciones superlativas o de liderazgo sobre OBS
("somos los número 1 online", "somos la mejor escuela online", "somos los primeros
en formación online en España", "tenemos el mejor claustro"...), esas afirmaciones
DEBEN ir acompañadas de al menos un argumento concreto que las sostenga.

⚠️ DECIR QUE OBS ES LA MEJOR SIN EXPLICAR POR QUÉ = DISCURSO VACÍO, no propuesta de valor.

Argumentos válidos que justifican afirmaciones de liderazgo:
- Trayectoria: "llevamos 20 años en formación online, fuimos los primeros"
- Rankings o reconocimientos: "estamos en el top X de rankings europeos / del FT"
- Metodología probada: "desarrollamos nuestra metodología específicamente para el formato online"
- Red alumni: "más de X mil alumni directivos en activo"
- Claustro: "nuestros profesores son profesionales en activo, no solo académicos"
- Datos de empleabilidad: "X% de nuestros alumnos mejoran su posición en 12 meses"

✅ Asesor dice "OBS es la #1 online porque llevamos 20 años siendo la primera escuela
   en desarrollar un modelo exclusivamente online, cuando otras todavía no existían" → BUENO
❌ Asesor dice "OBS es la número 1 en España online" sin añadir ningún argumento
   que justifique esa afirmación → oportunidad de valor perdida → penaliza

⚠️ Si el asesor no hace afirmaciones superlativas en esta llamada, esta regla no aplica.
Solo evalúa si HIZO una afirmación superlativa y si la respaldó o no.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACTOR DETERMINANTE DE COMPRA (FDC) — CRITERIO CENTRAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El FDC es la razón más importante, específica y personal por la que ESTE lead podría
matricularse. No es una motivación genérica ("quiero crecer") sino el dolor, la meta
o la situación concreta que el lead reveló durante la investigación.

EJEMPLOS DE FDC REAL:
  ✅ "Necesito el título para acceder al puesto de manager que llevan meses buscando"
  ✅ "Mi empresa financia si demuestro que el programa es relevante para mi rol"
  ✅ "Quiero cambiar de carrera hacia marketing digital y necesito credenciales"
  ✅ "Llevo años en operaciones sin formación formal y siento que me bloquea al ascender"

CÓMO DETECTARLO: Escanea la fase de investigación de la transcripción. Busca el momento
en que el lead explicó POR QUÉ está buscando el programa ahora y QUÉ cambiaría en su
situación si lo hiciera. Eso es el FDC.

CÓMO VERIFICAR SI EL ASESOR LO USÓ: Busca en la propuesta de valor frases donde el
asesor conecte explícitamente el programa con ese FDC específico del lead. No basta
con mencionar el perfil del lead — el asesor debe vincular el programa a ESA RAZÓN:

  ✅ VINCULACIÓN REAL: "Como me comentabas que necesitas cambiar hacia marketing
     digital, el máster te da exactamente eso: un título con salida directa al sector
     y una red de contactos ya en activo en ese ámbito."
  ✅ VINCULACIÓN REAL: "Dado que tu empresa financia si el programa es relevante para
     tu rol, te cuento por qué este máster encaja exactamente con lo que haces..."
  ❌ NO ES VINCULACIÓN: "El programa está muy bien valorado y hay mucha demanda" (genérico)
  ❌ NO ES VINCULACIÓN: Mencionar el trabajo del lead de pasada sin conectarlo al FDC
  ❌ NO ES VINCULACIÓN: "Como te decía, el programa te ayudará a crecer" (vago, sin ancla)

⚠️ SI NO HAY FDC CLARO EN LA INVESTIGACIÓN: Si el asesor no investigó bien y no hay FDC
identificable, el problema principal está en Investigación. Para este bloque, evalúa si
el asesor al menos conectó la presentación con algo que el lead dijo explícitamente, aunque
sea una motivación superficial. Sin FDC detectado → la propuesta de valor solo puede ser
MEJORABLE como máximo (no BUENO), porque sin ese dato el asesor no tenía con qué personalizar.

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

🟡 MEJORABLE — la presentación existe pero no usa el FDC para vincular el programa al lead:
   - Explica OBS y el programa de forma ordenada, pero no recupera el FDC del lead
     para conectar la propuesta — es el MISMO discurso que daría a cualquier candidato
   - Puede mencionar superficialmente el perfil del lead (su trabajo, su sector) pero
     sin conectar con la razón específica por la que ESTE lead quiere el programa ahora
   - El lead escucha información útil pero no siente que el programa resuelve SU problema
   - También: el asesor afirma que OBS es la mejor o la #1 pero no da ningún argumento
     que lo justifique → declaración vacía que no genera credibilidad ni añade valor
   ⚠️ La diferencia con BUENO no es cuánto habló el asesor, sino si ancló la propuesta
   al FDC o a un motivo concreto del lead vs. si fue un discurso de catálogo genérico.

🟢 BUENO — la presentación conecta el programa con el FDC del lead:
   - Presenta la institución y el programa con claridad y orden
   - Enfatiza beneficios sobre características (qué le aporta, no solo qué incluye)
   - REQUISITO CLAVE: recupera explícitamente el FDC del lead (o al menos su motivación
     más concreta) y lo vincula con lo que el programa ofrece — el lead siente que el
     programa fue pensado para resolver SU situación específica
   - Si el lead es junior, destaca empleabilidad y bolsas de trabajo
   - El lead muestra interés o comprensión genuina
   - También es BUENO si el asesor distribuyó bien la propuesta de valor a lo largo de la
     llamada siempre que la vinculación con el FDC esté presente en algún momento
   ⚠️ NO basta con mencionar el nombre del lead o su trabajo de pasada. La vinculación
   debe ser explícita: el asesor dice (con sus palabras) por qué ESTE programa resuelve
   ESTA necesidad concreta de ESTE lead.

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
  "mejoras": ["Frase de acción en infinitivo máx 8 palabras (ej: Concretar fecha y hora de seguimiento). Lista vacía [] si BUENO sin fallos relevantes."],
  "personalizacion_detectada": true/false,
  "fdc_detectado": "El FDC que identificaste en la investigación. Escribe la razón concreta que el lead dio: su meta, su dolor, su situación específica. 'No detectado' si no hay FDC claro en la transcripción.",
  "fdc_vinculado_programa": true/false,
  "evidencia_vinculacion_fdc": "[ASESOR]: Cita literal donde el asesor vincula el FDC con el programa (COPY-PASTE). 'No encontrada' si no ocurrió.",
  "presenta_institucion": true/false,
  "enfoque": "caracteristicas" | "beneficios" | "mixto",
  "perfil_lead": "JUNIOR" | "SENIOR" | "NO_DETERMINADO",
  "bolsas_trabajo_mencionadas": true/false,
  "afirmaciones_superlativas_detectadas": true/false,
  "superlativas_justificadas": true/false,
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
de estos 6 puntos. Cuenta cuántos tienen respuesta NEGATIVA (= fallo):

  1. ¿Presentó la institución (OBS) con claridad?                                 → SÍ / NO
  2. ¿Explicó el programa con beneficios (no solo características)?                → SÍ / NO
  3. ¿Recuperó el FDC del lead (su motivo o necesidad más concreta) y lo vinculó
     explícitamente con el programa? (Mención superficial del trabajo = NO)        → SÍ / NO
  4. ¿El lead mostró interés o comprensión genuina?                                → SÍ / NO
  5. ¿Adaptó argumentos al perfil del lead (junior→empleabilidad, senior→ROI)?     → SÍ / NO
  6. Si el asesor hizo afirmaciones superlativas sobre OBS ("somos el #1", "somos
     los mejores online"), ¿las justificó con al menos un argumento concreto?
     Si NO hizo afirmaciones superlativas → SÍ automático.                         → SÍ / NO

CUENTA los NOs. Ese número es tu "contador_fallos_criticos" en el JSON.
🚨 REGLA ABSOLUTA: Si hay 3 o más NOs → la calificación es MALO. Sin excepciones.

🔴 COHERENCIA ENTRE FALLOS Y CALIFICACIÓN:
   Analiza el peso real de cada fallo. Los 5 criterios son todos relevantes para que el
   lead entienda y valore el programa. No presentar la institución con claridad, no
   enfatizar beneficios, no conectar con el lead, que el lead no muestre interés y no
   adaptar los argumentos al perfil son fallos que acumulados dejan la propuesta sin impacto.
   Si la mayoría fallaron, la calificación debe ser MALO. No por un umbral mecánico, sino
   porque una propuesta que no conecta con el lead ni genera interés no cumple su función.
   No detectes múltiples fallos graves y concluyas MEJORABLE: sería incoherente.

⚠️ CALIBRACIÓN HONESTA — LEE ESTO ANTES DE DECIDIR:
Los modelos de lenguaje tienden a suavizar calificaciones buscando compensaciones positivas.
Si la propuesta fue genuinamente personalizada y conectó con lo que importa a ESTE lead
→ di BUENO con confianza.
Si la propuesta fue correcta y completa pero genérica (válida para cualquier lead), la
calificación debe reflejarlo. Una presentación extensa no es una presentación personalizada.
MEJORABLE no es un fracaso: es la evaluación honesta de una propuesta que informó pero no conectó.

🚨 RECONOCER MALO — INSTRUCCIÓN ESPECÍFICA:
MALO no significa "el asesor no dijo nada" o "la presentación fue caótica". También es
MALO cuando la propuesta fue tan genérica que no sirvió para que el lead se viera reflejado
en el programa. Di MALO cuando los datos lo indiquen:
  - Si el razonamiento describe una presentación en la que el asesor enumeró
    características sin conectar ninguna con el lead, y no puedes citar ni UN momento
    donde el lead sintiera que el programa era para él → MALO, no MEJORABLE.
  - Si el único argumento para no dar MALO es "la presentación fue completa y ordenada"
    → la extensión o el orden no compensan la ausencia total de conexión con el lead.
    Una presentación larga y genérica = catálogo de catálogo → MALO si no hay anclaje.
PATRONES QUE SON MALO DIRECTAMENTE (sin necesidad de contar NOs del checklist):
  ▸ Presentación de OBS + programa de principio a fin sin recuperar el FDC del lead
    ni hacer referencia a nada que el lead dijo durante la investigación → MALO.
    El lead escuchó un catálogo que podría haber recibido cualquier candidato.
  ▸ El asesor afirmó que OBS "es la mejor" o "la #1" sin ningún argumento que lo
    respalde + no vinculó el FDC con el programa + el lead no mostró interés genuino
    → discurso vacío sin impacto → MALO.
  ▸ El lead es claramente junior/recién graduado y el asesor no mencionó en ningún
    momento empleabilidad, bolsas de trabajo ni red de contactos, centrándose solo
    en características del programa sin conexión con la situación del lead → MALO.

⚠️ REGLAS PARA CALIFICAR (después de contar los fallos):
- MALO: múltiples fallos críticos acumulados, O presentación confusa/desorganizada, O el lead no entiende qué se le ofrece.
- MEJORABLE: presentación correcta y ordenada pero genérica — no recuperó el FDC del lead
  para anclarlo al programa. El lead escucha información válida pero no siente que el programa
  resuelve SU situación concreta. Catálogo sin ancla personal al FDC.
- BUENO: clara, estructurada y vincula explícitamente el FDC del lead con lo que el programa
  ofrece. El lead siente que el asesor habla de SU caso, no de un candidato genérico.
  Requiere ancla real al FDC — no menciones superficiales del nombre, trabajo o sector.
- Si dudas entre BUENO y MEJORABLE: ¿el asesor recuperó el FDC y lo vinculó al programa
  con una frase explícita? Si no hay esa vinculación directa → MEJORABLE, aunque la
  presentación haya sido extensa, ordenada y haya mencionado el perfil del lead de pasada.
- Si no hay FDC claro en la investigación (el asesor no investigó bien): la propuesta
  de valor no puede ser BUENO, porque el asesor no tenía el dato con el que personalizar.
  Máximo MEJORABLE. El problema raíz está en Investigación, pero este bloque lo refleja.
- El asesor puede haber trabajado elementos de propuesta desde el inicio; evalúa si el
  conjunto incluye la vinculación con el FDC, no si empezó antes de lo habitual.
- Si hubo presión de tiempo del lead, ajusta la exigencia de profundidad pero no la de
  vinculación al FDC — aunque sea en una sola frase, debe estar presente para ser BUENO.
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
