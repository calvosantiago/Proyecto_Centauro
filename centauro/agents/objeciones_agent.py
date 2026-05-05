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
            
            # Tope universal: 3+ fallos críticos = MALO
            contador_fallos = resultado_raw.get("contador_fallos_criticos", 0)
            cal_tmp, raz_tmp = self._aplicar_tope_fallos_criticos(
                resultado_raw.get("calificacion"), contador_fallos, resultado_raw.get("razonamiento", "")
            )
            if cal_tmp != resultado_raw.get("calificacion"):
                resultado_raw["calificacion"] = cal_tmp
                resultado_raw["razonamiento"] = raz_tmp

            # Registrar objeciones detectadas (el LLM decide cuándo usar NO_OBSERVABLE)
            objeciones_detectadas = resultado_raw.get("objeciones_identificadas", [])

            # NOTA: El coaching se aplica en batch desde el orchestrator para optimizar llamadas API
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")
            mejoras = self._formato_mejoras(resultado_raw.get("mejoras", []))

            return EvaluationResult(
                bloque=self.nombre_bloque,
                calificacion=resultado_raw.get("calificacion"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=resultado_raw.get("evidencias_extra", []),
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=recomendacion_base,
                mejoras=mejoras,
                metadata={
                    "num_objeciones": len(objeciones_detectadas),
                    "objeciones_identificadas": objeciones_detectadas,
                    "objeciones_no_abordadas": resultado_raw.get("objeciones_no_abordadas", []),
                    "pistas_mixtas_detectadas": resultado_raw.get("pistas_mixtas_detectadas", []),
                    "anticipo_objeciones": resultado_raw.get("anticipo_objeciones", False),
                    "anticipo_posibles_bajas": resultado_raw.get("anticipo_posibles_bajas", False),
                    "venta_preventiva_detectada": resultado_raw.get("venta_preventiva_detectada", False),
                    "revalido_informacion_explicada": resultado_raw.get("revalido_informacion_explicada", False),
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

⚠️ CUÁNDO USAR NO_OBSERVABLE:
Solo cuando la conversación no ofrece ninguna oportunidad evaluable: la llamada fue tan
corta o el lead tan entusiasta que no hubo resistencias ni señales de duda que pudieran
anticiparse. En ese caso usa observabilidad "NO_OBSERVABLE" y calificacion: null.
Si el asesor anticipó objeciones proactivamente (aunque el lead no las planteara), SÍ es evaluable.
Si hubo una conversación sustancial y el asesor no anticipó ninguna objeción → califica MEJORABLE
por falta de proactividad, no NO_OBSERVABLE. Reserva NO_OBSERVABLE para casos genuinamente vacíos.

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
PROCESO COMPLETO DE GESTIÓN DE OBJECIONES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El estándar del programa evalúa si el asesor sigue un proceso consultivo completo,
no si simplemente responde a la objeción:

1. EMPATIZAR: Validar la preocupación sin minimizarla.
   Ej: "Entiendo que eso genera incertidumbre, es completamente normal."

2. PROFUNDIZAR: Hacer preguntas para entender qué hay detrás de la objeción.
   Ej: "¿Qué es exactamente lo que te preocupa del timing hasta octubre?"
   ⚠️ No asumas la causa: una objeción de "timing" puede esconder resistencia de
   fondo (precio, miedo al compromiso, dudas sobre el programa). Preguntar ANTES
   de responder es obligatorio para una objeción no puramente logística.

3. AISLAR: Confirmar si esa objeción es el freno real o si hay más detrás.
   Ej: "Si pudiéramos resolver el tema del timing, ¿estarías listo para avanzar?"
   Ej: "¿Aparte de eso, hay algo más que te genera dudas?"
   Esto mide el peso real de la objeción y evita resolver la superficie mientras
   la resistencia de fondo queda sin explorar.

4. REENCUADRAR/RESOLVER: Usar técnica, evidencia o reencuadre del valor para resolver.
   Solo después de haber profundizado y aislado la causa real.

5. VERIFICAR: Confirmar que la objeción quedó resuelta.
   Ej: "¿Eso lo resuelve?" / "¿Te quedó más claro con esto?"

El fallo más frecuente: saltar directamente al paso 4 sin haber hecho el 2 y el 3.
Dar una respuesta técnicamente correcta a una objeción no explorada = MEJORABLE.

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
PISTAS MIXTAS — OBJECIONES ENCUBIERTAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cuando el lead descarta verbalmente una objeción para destacar otra, NO significa que
la primera quede neutralizada. Casi siempre es una PISTA MIXTA: el lead está priorizando
una variable, pero la otra sigue activa como criterio crítico.

PATRONES TÍPICOS DE PISTA MIXTA:
- "No es tanto por el dinero, sino por el tiempo" → tiempo es la objeción dominante,
  PERO el dinero sigue siendo variable crítica.
- "No es que no me interese el programa, lo que pasa es que no sé si ahora es el momento"
  → la urgencia es la objeción dominante, PERO el interés/encaje sigue por confirmar.
- "Por mí no hay problema, lo difícil es que mi pareja lo entienda" → autoridad es
  dominante, PERO la convicción propia del lead también está en cuestión.
- "El precio no me preocupa tanto, es más el formato online" → formato es dominante,
  PERO el coste sigue siendo variable que el lead vigila.

SEÑALES DE QUE LA VARIABLE "DESCARTADA" SIGUE VIVA:
- El lead pregunta poco después por esa variable ("¿y cuánto cuesta exactamente?")
- El lead vuelve a mencionarla más tarde aunque la haya minimizado al principio
- El lead reacciona emocionalmente (silencio, cambio de tono) cuando aparece la variable
- El lead pide opciones, descuentos, alternativas relacionadas con la variable "descartada"

CÓMO DEBE GESTIONARLO EL ASESOR:
1. RECONOCER la dominante: "Perfecto, entonces el punto más sensible para ti es el tiempo."
2. REABRIR la otra como pregunta diagnóstica, no como contradicción:
   "Y a nivel inversión, ¿ya tenías un rango contemplado para esta maestría?"
3. NO dar por cerrada la variable "descartada" sin haberla explorado.

⚠️ FALLO TÍPICO A PENALIZAR: el asesor toma al pie de la letra la palabra del lead,
descarta la variable "no era por X", y se centra solo en la dominante. Cuando el lead
luego pregunta por el precio o reacciona ante el formato, el asesor ya no tiene contexto
para responder bien porque dio por cerrada esa línea. Esto contribuye a MEJORABLE incluso
si el resto del manejo fue correcto: significa que el asesor escuchó las palabras pero
no leyó la pista mixta.

⚠️ NO INVENTES PISTAS MIXTAS: solo márcalas cuando el patrón sea claro (lead descartó
una variable Y luego dio señales de que sigue activa). Si el lead descartó una variable
y nunca volvió a mencionarla → no era pista mixta, era información honesta.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANTICIPACIÓN A LA OBJECIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Un asesor de alto nivel NO espera a que el lead plantee una objeción para trabajarla.
La ANTICIPA: menciona y resuelve antes de que surja la duda ("Quizás te preguntas
si vale la pena la inversión — déjame explicarte por qué este programa tiene ROI real...").
Trabajar sin miedo a la objeción y anticiparse a ella es una señal clara de BUENO.
También evalúa si el asesor retoma el tema económico o temporal de forma proactiva,
o si solo reacciona cuando el lead protesta.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANTICIPACIÓN A BAJAS FUTURAS — INFORMACIÓN PROACTIVA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Un asesor de alto nivel no solo resuelve objeciones en el momento — también PREVIENE
bajas futuras siendo transparente sobre aspectos del programa que el lead podría
descubrir después y considerar un engaño o decepción.

Este agente también evalúa si el asesor mencionó PROACTIVAMENTE información potencialmente
incómoda ANTES de que el lead la preguntara. Esto incluye, entre otros:
- Trabajos en grupo o en equipo (si el lead es introvertido o tiene poca disponibilidad)
- Diferencia entre titulación propia (de la institución) y titulación oficial (del Estado)
- Carga de trabajo real, horas semanales, ritmo del programa
- Requisitos de admisión que puedan ser obstáculos (expediente, idioma, experiencia)
- Condiciones de financiación que luego puedan ser motivo de baja

⚠️ Esta anticipación es una de las conductas MÁS VALORADAS del asesor:
✅ Asesor menciona "te aviso que los trabajos son en grupo, así que necesitarás
   coordinar con compañeros" → señal de transparencia y prevención de bajas → BUENO
✅ Asesor explica "la titulación es propia de OBS, no es un título oficial del Estado —
   te cuento por qué esto igual o más te conviene" → previene malentendido futuro → BUENO
❌ Asesor omite deliberadamente que la titulación es propia cuando es relevante para el lead
   o cuando el lead podría haberlo necesitado saber → señal de MALO

NOTA: No debes inventar que faltó info proactiva si el tema no era relevante para este lead.
Solo penaliza si el programa tiene un aspecto que claramente podría sorprender negativamente
a este lead específico Y el asesor no lo mencionó en ningún momento de la llamada.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REVALIDACIÓN DE LO EXPLICADO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Antes de avanzar o cerrar, el asesor debería confirmar que el lead ha entendido bien
todo lo que se explicó y no le ha quedado ninguna duda. Esta revalidación:
- Genera seguridad en el lead y reduce el riesgo de malentendidos que deriven en baja
- Permite al asesor detectar dudas latentes no verbalizadas espontáneamente
- Es la contrapartida de la anticipación: primero anticipa, luego confirma comprensión

Señales de revalidación:
✅ "¿Te ha quedado alguna duda sobre lo que te he explicado del programa?"
✅ "¿Hay algo de lo que hemos comentado que quieras que te aclare?"
✅ "Antes de seguir, ¿estás cómodo con todo lo que te he contado?"
Si esta revalidación existe → señal positiva que contribuye a BUENO.
Si falta completamente → menciónalo en las mejoras.

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
   - También: omite deliberadamente información que el lead claramente necesitaba conocer
     (titulación propia vs oficial, trabajos en grupo, carga real) → posible baja futura

🟡 MEJORABLE — el asesor responde pero de forma reactiva y sin seguir el proceso completo:
   - Solo reacciona a objeciones explícitas, nunca anticipa
   - Responde con información correcta pero mecánica, sin validar la preocupación del lead
   - Salta directamente a responder sin profundizar ni aislar: asume la causa de la
     objeción en vez de preguntar qué hay detrás ("planificación hasta octubre" tratada
     como logística sin explorar si esconde otra resistencia)
   - No aísla si la objeción es el freno real: resuelve la superficie pero la resistencia
     de fondo queda sin explorar
   - No profundiza en el porqué real de la objeción FUNDAMENTAL (precio, necesidad, valor)
     ⚠️ Para objeciones LOGÍSTICAS puras: MEJORABLE solo si el asesor no ofreció ninguna
     alternativa logística. No es fallo no interrogar la circunstancia personal del lead.
   - En objeción de autoridad: valida pero no arma al lead con argumentos para la
     conversación con el tercero (venta preventiva ausente)
   - El lead queda igual de dudoso o inseguro tras la respuesta
   - Intenta resolver pero no usa ninguna técnica estructurada

🟢 BUENO — el asesor maneja y/o anticipa objeciones con confianza y el lead suaviza su postura:
   - Anticipa objeciones comunes sin que el lead las plantee (trabaja sin miedo a ellas)
   - O si el lead objeta: sigue el proceso consultivo: valida la preocupación, profundiza
     para entender la causa real, aísla si es el freno principal, reencuadra con técnica.
     Saltarse profundizar y aislar no es "proceso incompleto" — es ausencia de proceso.
   - En objeción de autoridad: arma proactivamente al lead para la conversación con el
     tercero (venta preventiva: anticipa los bloqueos del tercero y da herramientas al lead)
   - Usa alguna técnica estructurada (feel-felt-found, boomerang, aislamiento, evidencia concreta, etc.)
   - TÉCNICA DE EVIDENCIA CONCRETA: usar brochure, datos reales, ejemplos de bolsas de empleo,
     casos de alumni, cifras específicas = técnica válida y efectiva. Valórala positivamente.
   - SEÑAL POSITIVA (no excepción absoluta): si el lead confirma que sus dudas quedaron
     resueltas, pesa a favor de BUENO — pero no borra el proceso. Si el asesor no
     profundizó ni aisló antes de responder, la satisfacción del lead puede ser
     circunstancial (lead entusiasta de base, no mérito del asesor). Evalúa el PROCESO,
     no solo el resultado final.
   - En objeciones logísticas (timing/viaje): acordar pago parcial, reserva o fecha
     alternativa = resolución exitosa → BUENO si además validó y ofreció alternativa.
   - SUMA POSITIVA: el asesor anticipa proactivamente información potencialmente incómoda
     (titulación propia, trabajos en grupo, etc.) → refuerza BUENO.
   - SUMA POSITIVA: el asesor revalida al final que el lead no tiene dudas pendientes
     → refuerza BUENO.
   - ⚠️ BUENO requiere evidencia de PROCESO, no solo de resultado. Una objeción puede
     quedar mitigada por el entusiasmo del lead o por suerte; lo que evalúas es si el
     asesor ejecutó el proceso consultivo. Si se saltó profundizar e aislar → MEJORABLE,
     aunque el lead pareciera satisfecho al final.

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

OBJECIÓN DE AUTORIDAD (familia, pareja, empresa):
⚠️ LÍMITE DE SCOPE — REGLA CRÍTICA:
Profundizar en quién financia exactamente, cuál es el rol de cada familiar o cuánto
peso tiene cada persona en la decisión es tarea del bloque de INVESTIGACIÓN, no de
Objeciones. NO penalices al asesor en este bloque por no haber indagado más en la
dinámica familiar o económica del entorno del lead.

Lo que SÍ evalúa este bloque cuando aparece una objeción de autoridad:
- ¿El asesor validó la necesidad de consultar (no la minimizó ni presionó)?
- ¿Ofreció alguna herramienta para facilitar esa consulta? (sesión con la familia,
  material para compartir, resumen económico, llamada conjunta)
- ¿Acordó un próximo paso concreto en vez de dejar todo abierto?

VENTA PREVENTIVA — nivel avanzado para objeciones de autoridad:
Un asesor de alto nivel no solo facilita la consulta — ARMA al lead para que pueda
defender la decisión frente a las posibles objeciones del tercero:
- Anticipar qué dudas o resistencias planteará el tercero (precio, credibilidad,
  tiempo, necesidad) antes de que el lead lo consulte.
- Proveer argumentos concretos al lead para rebatirlas:
  "Si tu pareja pregunta por el precio, recuérdale que tienes la opción de
  financiación de 200€/mes; eso suele cambiar mucho la perspectiva."
- Ofrecer material que el lead pueda compartir (brochure, resumen económico, enlace).
- Proponer, si es apropiado, una llamada conjunta con el tercero.

Señal de BUENO con venta preventiva: el asesor prepara activamente al lead para
"vender" la decisión a su pareja/familia/empresa, anticipando los bloqueos del tercero.
Señal de MEJORABLE sin venta preventiva: el asesor solo valida que hay que consultarlo
y acuerda seguimiento, sin armar al lead para la conversación con el tercero.

Si el asesor validó + ofreció un camino + acordó seguimiento → BUENO en este bloque,
independientemente de si preguntó o no quién financia exactamente.
Si además aplicó venta preventiva → refuerza la calificación BUENO.

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
  "mejoras": ["Frase de acción en infinitivo máx 8 palabras (ej: Concretar fecha y hora de seguimiento). Lista vacía [] si BUENO sin fallos relevantes."],
  "objeciones_identificadas": ["tipo de objeción 1", "tipo 2"],
  "objeciones_no_abordadas": ["objeción que el lead planteó pero el asesor no respondió ni exploró"],
  "pistas_mixtas_detectadas": [
    {{
      "lead_dijo": "Cita literal del lead minimizando una variable (ej: 'No es por dinero, es por tiempo')",
      "variable_dominante": "tiempo | dinero | autoridad | formato | encaje | otra",
      "variable_descartada_pero_viva": "dinero | tiempo | otra — la que el lead minimizó pero siguió activa",
      "evidencia_sigue_viva": "Cita literal o referencia que muestra que la variable 'descartada' siguió siendo crítica (lead la mencionó después, preguntó por ella, reaccionó al tema, etc.). 'Sin evidencia posterior' si nunca volvió a aparecer.",
      "asesor_la_recogio": true/false,
      "como_la_gestiono": "Descripción breve de qué hizo el asesor: la reabrió como pregunta diagnóstica, la dio por cerrada, la ignoró, etc."
    }}
  ],
  "anticipo_objeciones": true/false,
  "anticipo_posibles_bajas": true/false,
  "venta_preventiva_detectada": true/false,
  "revalido_informacion_explicada": true/false,
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
- Si no hay objeciones ni anticipación Y la conversación fue sustancial → MEJORABLE, no NO_OBSERVABLE
- Solo usa NO_OBSERVABLE cuando genuinamente no hubo oportunidad evaluable (llamada muy corta, lead 100% entusiasta)
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

DETENTE. Antes de elegir la calificación, DEBES responder SÍ o NO a cada uno de
estos 6 puntos. Cuenta cuántos tienen respuesta NEGATIVA (= fallo):

  1. ¿Validó la preocupación del lead antes de responder (no la ignoró ni minimizó)? → SÍ / NO
  2. ¿Profundizó para entender qué hay detrás de la objeción, en vez de asumir
     su causa y responder directamente?                                                → SÍ / NO
     ⚠️ EXCEPCIÓN LOGÍSTICA PURA: Para objeciones claramente logísticas (viaje,
     fecha puntual donde el lead SÍ quiere avanzar), responde SÍ si el asesor
     reconoció la circunstancia y buscó un camino alternativo. Pero si la objeción
     puede esconder resistencia de fondo (precio, compromiso, dudas sobre el programa),
     NO se aplica la excepción: debe profundizar igualmente.
  3. ¿Aisló si la objeción era el freno real o si había más detrás?                  → SÍ / NO
     Ej: "Si pudiéramos resolver esto, ¿avanzarías?" / "¿Hay algo más que te preocupe?"
     ⚠️ EXCEPCIÓN: Para objeciones logísticas puras donde está claro que el lead SÍ
     quiere avanzar y solo hay un obstáculo operativo, el aislamiento puede ser
     implícito. Marca SÍ en ese caso.
  4. ¿Usó técnica estructurada o evidencia concreta para resolver/reencuadrar?       → SÍ / NO
  5. ¿El lead suavizó su postura o quedó menos resistente tras la respuesta?          → SÍ / NO
  6. ¿Abordó TODAS las objeciones que surgieron? ¿No dejó ninguna sin responder
     ni explorar?                                                                      → SÍ / NO
     ⚠️ Si el lead planteó una objeción que el asesor ignoró o no abordó → NO.
     Este fallo es crítico independientemente de cómo manejó las otras objeciones.
     ⚠️ Si no hubo objeciones explícitas del lead → responde SÍ (no aplica).
  7. Si hubo PISTAS MIXTAS (lead dijo "no es por X sino por Y" + después dio señales
     de que X seguía vivo: preguntó por X, pidió alternativas relacionadas con X, etc.),
     ¿el asesor las recogió y reabrió la variable X como pregunta diagnóstica
     en vez de darla por cerrada?                                                      → SÍ / NO
     ⚠️ Si NO hubo pistas mixtas claras → responde SÍ (no aplica).
     ⚠️ Si las hubo y el asesor tomó las palabras del lead al pie de la letra → NO.

CUENTA los NOs. Ese número es tu "contador_fallos_criticos" en el JSON.
🚨 REGLA ABSOLUTA: Si hay 3 o más NOs → la calificación es MALO. Sin excepciones.
(Si observabilidad es NO_OBSERVABLE, pon contador_fallos_criticos = 0.)
NOTA: El compromiso concreto y el siguiente paso se evalúan en el bloque de Cierre, no aquí.
NOTA: Información proactiva sobre el programa (titulación, trabajos en grupo) y
revalidación final de dudas son señales POSITIVAS que refuerzan BUENO, pero no forman
parte de este checklist de fallos críticos.

🔴 COHERENCIA ENTRE FALLOS Y CALIFICACIÓN:
   Analiza el peso real de cada fallo. No validar la preocupación, no profundizar, no aislar,
   no usar técnica y dejar objeciones sin abordar son fallos que acumulados dejan la resistencia
   del lead sin resolver. Si la mayoría fallaron → MALO. No detectes múltiples fallos graves y
   concluyas MEJORABLE: sería incoherente.
   También a la inversa: si detectas que el asesor se saltó pasos fundamentales del proceso
   (no profundizó, no aisló), no concluyas BUENO aunque el lead pareciera satisfecho. El proceso
   refleja la habilidad del asesor, no el entusiasmo o la paciencia del lead.

⚠️ CALIBRACIÓN HONESTA — LEE ESTO ANTES DE DECIDIR:
Los modelos de lenguaje tienden a suavizar calificaciones buscando compensaciones positivas.
Si el asesor siguió el proceso consultivo completo (validó, profundizó, aisló, usó técnica)
→ di BUENO con confianza.
Si detectaste que se saltó pasos clave (no profundizó, no aisló, dejó objeciones sin abordar),
la calificación debe reflejarlo. No compenses esos fallos con que el resultado fue aceptable
o que el lead pareció satisfecho. MEJORABLE no es un fracaso: es la evaluación honesta de
trabajo reactivo sin proceso consultivo completo.

🚨 RECONOCER MALO — INSTRUCCIÓN ESPECÍFICA:
MALO no significa "agresivo" o "catastrófico". Significa que el asesor no gestionó las
objeciones con ningún proceso mínimo. Di MALO cuando los datos lo indiquen:
  - Si el razonamiento describe fallos en la gestión de varias objeciones y no puede
    citar ningún manejo correcto → MALO, no MEJORABLE.
  - Si el único argumento para no dar MALO es "el lead fue comprensivo" o "el lead
    no insistió más" → eso refleja la tolerancia del lead, no el trabajo del asesor → MALO.
PATRONES QUE SON MALO DIRECTAMENTE (sin necesidad de contar NOs del checklist):
  ▸ Objeción fundamental (precio / necesidad / valor) recibida + asesor responde
    mecánicamente sin validar, sin profundizar, sin aislar + lead queda igual de resistente
    → MALO aunque la respuesta técnica fuera correcta.
  ▸ 2 o más objeciones del lead que el asesor no abordó en ningún momento → MALO.
  ▸ Objeción de autoridad ("debo consultarlo") + asesor dice solo "claro, piénsalo y
    me dices" sin ofrecer ninguna herramienta, ni acordar seguimiento, ni anticipar
    los bloqueos del tercero → MALO.

PATRÓN ESPECÍFICO DE PISTA MIXTA NO RECOGIDA (contribuye a MEJORABLE):
  ▸ El lead minimizó una variable ("no es por el dinero") + más adelante volvió a
    plantear esa misma variable (preguntó por el precio, pidió descuento, reaccionó
    al coste) + el asesor NO recogió la pista, no reabrió la variable como pregunta
    diagnóstica y siguió como si estuviera resuelta → MEJORABLE como mínimo, aunque
    el resto del manejo de objeciones haya sido correcto.
    El asesor escuchó las palabras del lead pero no leyó la señal mixta.
  ▸ Si además el asesor cierra la conversación sin haber explorado nunca la variable
    que el lead "descartó" pero seguía señalando → contribuye a MALO si se acumula
    con otros fallos del proceso.

⚠️ REGLAS PARA CALIFICAR (después de contar los fallos):
- MALO: múltiples fallos críticos acumulados, O ignora/agrava objeciones, O deja objeciones sin abordar.
- MEJORABLE: intenta responder pero se salta el proceso (no profundiza, no aísla). La objeción
  puede quedar superficialmente mitigada, pero el asesor no demostró técnica consultiva real.
  También MEJORABLE si la reacción fue solo reactiva (respondió cuando el lead protestó, pero
  no anticipó ninguna objeción ni preparó el terreno).
  También MEJORABLE si tomó al pie de la letra una pista mixta del lead y dio por cerrada una
  variable que seguía activa (lead dijo "no es por X" pero luego volvió a X y el asesor no lo recogió).
- BUENO: ejecutó el proceso completo o la mayor parte: validó, profundizó para entender la
  causa real, aisló si era el freno principal, usó técnica para resolver, verificó resolución.
  El lead puede no quedar 100% convencido, pero el asesor demostró proceso consultivo real.
  SUMA: detectó pistas mixtas y reabrió la variable "descartada" como pregunta diagnóstica.
- Si dudas entre BUENO y MEJORABLE: ¿profundizó? ¿aisló? Si no hizo ambas → MEJORABLE.
  No resuelvas la duda dando BUENO por defecto.
- Si hubo pistas mixtas y el asesor las recogió bien → señal positiva que confirma BUENO.
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