"""
Agente Evaluador: Manejo de Objeciones

INSTRUCCIÓN: Copia este archivo en:
C:\\Users\\uscp9a\\Grupo Planeta\\BI POWER - General\\PBI\\PROYECTOS\\Proyecto_Centauro\\centauro\\agents\\objeciones_agent.py
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt

class ObjecionesAgent(BaseEvaluatorAgent):
    """
    Evalúa cómo el asesor maneja las dudas y resistencias del cliente
    
    Criterios clave:
    - Valida la objeción (no la ignora ni minimiza)
    - Aísla la objeción real del pretexto
    - Usa técnicas estructuradas (feel-felt-found, etc.)
    - No presiona, ayuda a resolver
    """
    
    def __init__(self):
        super().__init__(nombre_bloque="Manejo de objeciones")
    
    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """Evalúa el manejo de objeciones"""

        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual, contexto_usuario)
            confianza = self._calcular_confianza(resultado_raw)
            
            # Validar que se detectaron objeciones
            objeciones_detectadas = resultado_raw.get("objeciones_identificadas", [])
            
            anticipo = resultado_raw.get("anticipo_objeciones", False)
            if len(objeciones_detectadas) == 0 and not anticipo:
                print(f"   ℹ️ No se detectaron objeciones ni anticipación en la conversación")
                # No es malo, simplemente no hubo objeciones ni proactividad evaluable
                resultado_raw["observabilidad"] = "NO_OBSERVABLE"
                resultado_raw["calificacion"] = None

            # NOTA: El coaching se aplica en batch desde el orchestrator para optimizar llamadas API
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")

            return EvaluationResult(
                bloque=self.nombre_bloque,
                calificacion=resultado_raw.get("calificacion"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=resultado_raw.get("evidencias_extra", []),
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=recomendacion_base,
                metadata={
                    "num_objeciones": len(objeciones_detectadas),
                    "objeciones_identificadas": objeciones_detectadas,
                    "anticipo_objeciones": resultado_raw.get("anticipo_objeciones", False),
                    "tecnica_detectada": resultado_raw.get("tecnica_detectada", "ninguna")
                }
            )
            
        except Exception as e:
            print(f"   ❌ Error en evaluación de Objeciones: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, transcripcion: str, manual: str, contexto_usuario: str = None) -> dict:
        """Llama al LLM con prompt especializado"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion)

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de MANEJO DE OBJECIONES en venta consultiva.

TU ÚNICA TAREA: Evaluar cómo manejó el [ASESOR] las dudas y resistencias del cliente.

TONO DE REDACCIÓN: Escribe SIEMPRE en TERCERA PERSONA al referirte al asesor ("el asesor hizo...", "el asesor podría..."). NUNCA uses segunda persona ("hiciste...", "podrías...", "tu objetivo...").

CONTEXTO DEL SPEECH Y BUENAS PRÁCTICAS:
{manual_enriquecido}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EL SPEECH COMO CARRETERA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El speech NO es una checklist de frases exactas. Es la CARRETERA: define los límites.
Un asesor que maneja la objeción con sus propias palabras pero valida, profundiza
y reduce la resistencia del lead → BUENO.
Lo que evalúas es si se sale de los límites (presionar, ignorar, ponerse defensivo)
o si navega bien dentro de ellos con su propio estilo.

IMPORTANTE: Si NO hay objeciones claras del [LEAD] NI anticipación del asesor, marca observabilidad "NO_OBSERVABLE" y calificacion: null.
Si el asesor anticipa objeciones proactivamente (aunque el lead no las plantee explícitamente), sí es evaluable.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CIRCUNSTANCIAS ATÍPICAS DE LA CONVERSACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Antes de evaluar, detecta si el lead declaró alguna restricción que condicionó
la conversación. En particular:

⚠️ RESTRICCIÓN DE TIEMPO: Si el lead indicó en cualquier punto anterior de la
llamada que tenía poco tiempo ("no tengo mucho tiempo", "tengo que cortar pronto",
"voy con prisa", "solo tengo unos minutos") → la evaluación debe tenerlo en cuenta.
Un asesor que maneja una objeción de forma más directa y concisa bajo presión de
tiempo está adaptándose a la situación, no siendo superficial. Detecta y menciona
esta circunstancia en el razonamiento si ocurrió.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALCANCE: EVALÚA TODA LA CONVERSACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Las objeciones NO aparecen solo en un bloque específico de la entrevista.
Una resistencia puede surgir durante la investigación, durante la propuesta
de valor, durante la presentación económica o en el cierre.

Busca en TODA la transcripción:
  ✓ Cualquier resistencia o duda del lead que frene el avance
  ✓ Cómo respondió el asesor a cada resistencia en el momento en que ocurrió
  ✓ Objeciones que el asesor anticipó antes de que el lead las expresara
  ✓ Señales de resolución o persistencia de la objeción a lo largo de la llamada

Evalúa el CONJUNTO de cómo el asesor manejó las resistencias durante toda la
conversación, no solo lo que ocurrió en el tramo final o en un bloque específico.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PREGUNTA INFORMATIVA vs. OBJECIÓN REAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NO toda duda o pregunta del lead es una objeción. Distingue:

PREGUNTA INFORMATIVA: el lead pide datos para entender mejor ("¿Cuánto dura el programa?",
"¿Qué titulación obtengo?", "¿Hay bolsa de empleo?"). No hay resistencia, solo curiosidad.
→ Responderla bien es BUENA ATENCIÓN, no manejo de objeciones. No la cuentes como objeción.

OBJECIÓN REAL: el lead expresa resistencia, duda o un motivo por el que no quiere avanzar
("Es muy caro", "No tengo tiempo", "Tengo que pensarlo", "Me voy de viaje y no puedo pagar").
→ Estas SÍ son objeciones. El asesor debe validarlas, profundizar y reducir la resistencia.

REGLA: solo incluye en "objeciones_identificadas" las resistencias reales al avance,
no las preguntas de información aunque el lead muestre curiosidad.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANTICIPACIÓN A LA OBJECIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Un asesor de alto nivel NO espera a que el lead plantee una objeción para trabajarla.
La ANTICIPA: menciona y resuelve antes de que surja la duda ("Quizás te preguntas
si vale la pena la inversión — déjame explicarte por qué este programa tiene ROI real...").
Trabajar sin miedo a la objeción y anticiparse a ella es una señal clara de BUENO.
También evalúa si el asesor retoma el tema económico o temporal de forma proactiva,
o si solo reacciona cuando el lead protesta.

⚠️ SENSIBILIDAD CONTEXTUAL — REGLA ANTES DE CALIFICAR:
Cuando el lead revela una circunstancia personal (viaje, compromiso familiar, trabajo,
situación médica), preguntar por qué esa circunstancia existe o cuándo cambiará es
INTRUSIVO e INAPROPIADO. Un asesor sensible NO interroga la circunstancia: ofrece
una salida (fecha alternativa, reserva, aplazamiento). Penalizar al asesor por "no
explorar la urgencia del viaje" o "no preguntar cuándo vuelve" es un ERROR: eso
sería presionar al lead, que es criterio de MALO, no de BUENO.
La sensibilidad y la lectura del contexto son parte de una venta consultiva de calidad.

CRITERIOS DE CALIFICACIÓN (elige UNA de las 3 etiquetas):

🔴 MALO — el asesor maneja la objeción de forma contraproducente o la evita activamente:
   - Ignora o minimiza la objeción del lead
   - Se pone a la defensiva ("No es caro, otros cobran más")
   - Presiona al lead sin escucharle ("Tienes que decidirte ya")
   - Genera más resistencia en vez de reducirla
   - También: el lead lanza una objeción seria y el asesor la pasa por alto o cambia de tema

🟡 MEJORABLE — el asesor responde pero de forma reactiva y sin lograr resolución real:
   - Solo reacciona a objeciones explícitas, nunca anticipa
   - Responde con información correcta pero mecánica, sin validar la preocupación del lead
   - No profundiza en el porqué real de la objeción FUNDAMENTAL (precio, necesidad, valor)
     ⚠️ Para objeciones LOGÍSTICAS: "no profundizar en los detalles" NO es fallo — ver regla
     de sensibilidad contextual arriba. MEJORABLE solo si el asesor no ofreció ninguna
     alternativa logística, no si no interrogó la circunstancia personal del lead.
   - El lead queda igual de dudoso o inseguro tras la respuesta
   - Intenta resolver pero no usa ninguna técnica estructurada

🟢 BUENO — el asesor maneja y/o anticipa objeciones con confianza y el lead suaviza su postura:
   - Anticipa objeciones comunes sin que el lead las plantee (trabaja sin miedo a ellas)
   - O si el lead objeta: valida la preocupación y profundiza antes de responder
   - Usa alguna técnica estructurada (feel-felt-found, boomerang, aislamiento, evidencia concreta, etc.)
   - TÉCNICA DE EVIDENCIA CONCRETA: usar brochure, datos reales, ejemplos de bolsas de empleo,
     casos de alumni, cifras específicas = técnica válida y efectiva. Valórala positivamente.
   - SEÑAL DEFINITIVA: si el lead confirma explícitamente que sus dudas quedaron resueltas
     ("no me queda ninguna duda", "estoy de acuerdo", "ya lo entiendo") → BUENO sin excepción.
   - En objeciones logísticas (timing/viaje): acordar pago parcial, reserva o fecha alternativa
     = resolución exitosa → BUENO.
   - No es necesario que use técnica perfecta: basta con que la objeción quede resuelta o reducida

TIPOS DE OBJECIONES Y CÓMO LEERLAS:

OBJECIONES FUNDAMENTALES (resistencia real al programa o la inversión):
- Precio ("Es caro", "No tengo ese presupuesto", "No puedo permitírmelo")
- Necesidad ("No estoy seguro si lo necesito", "No sé si es para mí")
- Valor ("No veo la diferencia con otras opciones")
- Autoridad ("Tengo que consultarlo con mi pareja/empresa/padres")
- Urgencia existencial ("Lo pensaré", "Más adelante quizás")

OBJECIONES LOGÍSTICAS/TIMING (circunstanciales, no de fondo):
- Timing puntual ("Me voy de viaje esta semana", "Ahora mismo no puedo pagar pero quiero apuntarme")
- Estas son más fáciles de resolver: el lead SÍ quiere avanzar, solo hay un obstáculo puntual.
- Un pago parcial, una reserva, o un aplazamiento acordado = RESOLUCIÓN EXITOSA de este tipo.
- NO las trates igual que una objeción de precio o de necesidad.

OBJECIÓN DE AUTORIDAD CON PADRES:
- Cuando los padres intervienen en la decisión económica, el asesor no debe presuponer su apoyo.
- Debe investigar el rol real de los padres: ¿están informados? ¿tienen dudas propias?
- Técnica adecuada: ofrecer una sesión con los padres para resolver sus dudas directamente.
- Si el asesor solo pregunta "¿te ayudan los padres?" sin explorar más → oportunidad perdida.

OBJECIONES ADMINISTRATIVAS/DOCUMENTACIÓN:
- El lead menciona dificultades para obtener su título, expediente académico o certificaciones previas.
- El lead tiene pendiente trámites burocráticos con su universidad o institución anterior.
- Estas son objeciones operativas que el asesor debe gestionar activamente:
  → Ofrecer orientación o alternativas para conseguir la documentación = técnica válida.
  → Decir "nosotros te ayudamos con ese trámite" o "eso es algo que podemos resolver juntos" = BUENO.
- Pueden aparecer en cualquier momento de la llamada (no solo al cierre).
- NO las ignores por ser "administrativas" — si el lead las menciona, son una barrera real al avance.

⚠️ PATRÓN RESERVA/SEÑAL DE COMPROMISO:
Si el asesor ofrece al lead reservar su plaza con un pago simbólico o parcial (ej: "puedes reservar
con solo 100 euros ahora y el resto cuando vuelvas") Y el lead reacciona positivamente (acepta la
idea, muestra interés, no la rechaza) → cuenta como RESOLUCIÓN EXITOSA de la objeción logística.
Busca activamente este patrón en la transcripción. Si ocurrió → BUENO sin excepción.

FORMATO JSON OBLIGATORIO:
{{
  "contador_fallos_criticos": 0,
  "calificacion": "MALO" | "MEJORABLE" | "BUENO" | null,
  "observabilidad": "ALTA" | "NO_OBSERVABLE",
  "evidencia_principal": "[LEAD]: Objeción principal... [ASESOR]: Respuesta... (COPY-PASTE LITERAL). Si hubo anticipación, pon la frase del asesor anticipándose.",
  "evidencias_extra": [
    "[ASESOR]: Validación de la objeción o anticipación... (COPY-PASTE LITERAL)",
    "[LEAD]: Reacción posterior... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "En 4-6 líneas de texto fluido, sin listas ni SÍ/NO: explica qué objeciones surgieron, cómo las gestionó el asesor, qué hizo bien y en qué falló. Por qué merece esa calificación. Conecta con lo que ocurrió realmente en la conversación. OBLIGATORIO si la calificación es MALO o MEJORABLE: incluye en el texto al menos una cita literal entre comillas de la conversación que muestre el fallo principal.",
  "recomendacion_accionable": "IMPORTANTE: Combina en un SOLO texto fluido: (1) Qué mejorar, (2) UNA técnica de los libros de ventas del CONTEXTO que aplique, explicando POR QUÉ funciona y dando 2 ejemplos de frases adaptadas a ESTA conversación. Máx 6-8 líneas. NO copies texto literal de los libros.",
  "objeciones_identificadas": ["tipo de objeción 1", "tipo 2"],
  "anticipo_objeciones": true/false,
  "tecnica_detectada": "feel-felt-found" | "boomerang" | "aislamiento" | "anticipacion" | "ninguna",
  "restriccion_tiempo_detectada": true/false
}}

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
Úsalos en "recomendacion_accionable" SOLO si se cumplen las dos condiciones:
  (a) Hay un aspecto concreto donde el asesor tiene margen real de mejora en ESTA llamada.
  (b) El fragmento de coaching es genuinamente relevante para ESA situación específica.

Si el asesor manejó la objeción correctamente (calificación BUENO) y no encuentras
una técnica de los libros que aplique de forma natural a lo ocurrido → NO fuerces
una referencia de coaching. En ese caso escribe solo refuerzo de lo hecho bien
y, si procede, un matiz menor de mejora sin citar libros.

Cuando SÍ uses coaching:
- Elige la técnica más relevante para lo que le faltó al asesor
- Explica POR QUÉ le ayudaría conectándola con la situación real de la llamada
- Da 2 frases concretas que podría haber usado en ESTA conversación
- NO copies texto literal del libro, adapta con tus palabras
- Menciona de qué libro/autor viene

⚠️ VERIFICA ANTES DE RECOMENDAR: Si el asesor ya demostró en la conversación
el comportamiento que ibas a recomendar, NO lo recomiendes — sería invalidar su trabajo.
Elige otro aspecto con margen real o, si no hay ninguno, reconoce la buena gestión.

REGLAS CRÍTICAS:
- Evidencias LITERALES de la transcripción (COPY-PASTE exacto)
- Si no hay objeciones → observabilidad "NO_OBSERVABLE" y calificacion: null
- NO evalúes si el lead compró, evalúa si el ASESOR manejó bien la resistencia
- Una objeción bien manejada puede dejar al lead pensando (eso es OK)
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

Si hay objeciones detectadas, DETENTE. Antes de elegir la calificación, DEBES
responder SÍ o NO a cada uno de estos 4 puntos. Cuenta cuántos tienen respuesta
NEGATIVA (= fallo):

  1. ¿Validó la preocupación del lead antes de responder (no la ignoró ni minimizó)? → SÍ / NO
  2. ¿Profundizó en el porqué real de la objeción (no se quedó en la superficie)?    → SÍ / NO
     ⚠️ EXCEPCIÓN LOGÍSTICA: Para objeciones de timing/viaje/circunstancia puntual,
     "profundizar" NO significa interrogar los detalles logísticos del lead (cuándo
     vuelve, por qué el viaje es urgente, etc.) — eso sería intrusivo e inapropiado.
     Para estas objeciones, responde SÍ si el asesor: (a) reconoció la circunstancia,
     y (b) buscó activamente un camino alternativo (fecha anterior, reserva, pago
     parcial). El asesor que no presiona y ofrece una salida está manejando bien la
     objeción logística. Marca este ítem como SÍ en ese caso.
  3. ¿Usó técnica estructurada o evidencia concreta para resolver?                   → SÍ / NO
  4. ¿El lead suavizó su postura o quedó menos resistente tras la respuesta?          → SÍ / NO

CUENTA los NOs. Ese número es tu "contador_fallos_criticos" en el JSON.
(Si observabilidad es NO_OBSERVABLE, pon contador_fallos_criticos = 0.)
NOTA: El compromiso concreto y el siguiente paso se evalúan en el bloque de Cierre, no aquí.

🔴 COHERENCIA ENTRE FALLOS Y CALIFICACIÓN:
   Analiza el peso real de cada fallo. Los 4 criterios son todos relevantes para gestionar
   las resistencias del lead. No validar la preocupación, no profundizar, no usar técnica
   y que el lead no suavice su postura son fallos que acumulados dejan la objeción sin
   resolver o la agravan. Si la mayoría fallaron, la calificación debe ser MALO. No por
   un umbral mecánico, sino porque múltiples fallos en el manejo de objeciones dejan al
   lead igualmente o más resistente. No detectes múltiples fallos graves y concluyas
   MEJORABLE: sería incoherente con tu propio análisis.

⚠️ REGLAS PARA CALIFICAR (después de contar los fallos):
- MALO: múltiples fallos críticos acumulados, O ignora/agrava objeciones, O huye del tema.
- MEJORABLE: intenta responder pero la objeción queda sin resolver realmente, o la resuelve de forma superficial sin técnica consultiva. El lead sigue resistente o simplemente no la presiona más.
- BUENO: resuelve o reduce la resistencia con técnica real. No es necesario que el lead quede convencido al 100%: si el asesor aplicó un proceso consultivo y el lead avanzó → es BUENO.
- Si dudas entre BUENO y MEJORABLE: ¿el lead quedó menos resistente después? Si sí → BUENO.
- Si el lead confirma explícitamente que sus dudas se resolvieron → BUENO sin excepción.
- Si la objeción era logística (timing/viaje) y se acordó pago parcial o alternativa → BUENO.
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.
"""
        
        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
ANTES DE EVALUAR: Lee la transcripción completa de principio a fin. Las objeciones pueden
surgir en CUALQUIER momento — al inicio, en el medio o al final de la llamada. Presta
especial atención a: (1) resistencias logísticas tipo "me voy de viaje" y si el asesor
ofreció reserva/pago parcial, (2) problemas administrativos con títulos o documentación
y si el asesor ofreció ayuda, (3) cualquier momento donde el lead expresó una barrera y
el asesor respondió. Identifica TODAS las objeciones antes de decidir la calificación.

Identifica y evalúa el manejo de objeciones en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_objeciones")
        return self._extract_json_safe(resp)