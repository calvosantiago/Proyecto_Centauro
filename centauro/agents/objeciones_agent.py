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
   - No profundiza en el porqué real de la objeción
   - El lead queda igual de dudoso o inseguro tras la respuesta
   - Intenta resolver pero no usa ninguna técnica estructurada
   - Resuelve la objeción pero no genera compromiso concreto ni urgencia después

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
   - Tras resolver la objeción, genera compromiso concreto (documento, fecha, pago) y/o urgencia.
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

FORMATO JSON OBLIGATORIO:
{{
  "calificacion": "MALO" | "MEJORABLE" | "BUENO" | null,
  "observabilidad": "ALTA" | "NO_OBSERVABLE",
  "evidencia_principal": "[LEAD]: Objeción principal... [ASESOR]: Respuesta... (COPY-PASTE LITERAL). Si hubo anticipación, pon la frase del asesor anticipándose.",
  "evidencias_extra": [
    "[ASESOR]: Validación de la objeción o anticipación... (COPY-PASTE LITERAL)",
    "[LEAD]: Reacción posterior... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "Responde cada punto: ¿Las resistencias detectadas son objeciones reales o preguntas informativas? ¿Anticipó objeciones? ¿Validó la preocupación del lead antes de responder? ¿Profundizó en el porqué real? ¿Usó técnica estructurada o evidencia concreta (brochure, datos, ejemplos)? ¿El tipo de objeción era fundamental o logística/timing? ¿Resolvió o generó más resistencia? ¿El lead confirmó explícitamente que sus dudas quedaron resueltas? ¿Generó compromiso concreto y/o urgencia después de resolver? ¿Por qué esa calificación?",
  "recomendacion_accionable": "IMPORTANTE: Combina en un SOLO texto fluido: (1) Qué mejorar, (2) UNA técnica de los libros de ventas del CONTEXTO que aplique, explicando POR QUÉ funciona y dando 2 ejemplos de frases adaptadas a ESTA conversación. Máx 6-8 líneas. NO copies texto literal de los libros.",
  "objeciones_identificadas": ["tipo de objeción 1", "tipo 2"],
  "anticipo_objeciones": true/false,
  "tecnica_detectada": "feel-felt-found" | "boomerang" | "aislamiento" | "anticipacion" | "ninguna"
}}

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
DEBES integrarlos en tu "recomendacion_accionable" de forma ORGÁNICA:
- Elige la técnica MÁS relevante para lo que le faltó al asesor
- Explica POR QUÉ le ayudaría (conecta con la situación real de la llamada)
- Da 2 frases concretas que podría haber usado en ESTA conversación
- NO copies texto literal del libro, adapta con tus palabras
- Menciona de qué libro/autor viene

REGLAS CRÍTICAS:
- Evidencias LITERALES de la transcripción (COPY-PASTE exacto)
- Si no hay objeciones → observabilidad "NO_OBSERVABLE" y calificacion: null
- NO evalúes si el lead compró, evalúa si el ASESOR manejó bien la resistencia
- Una objeción bien manejada puede dejar al lead pensando (eso es OK)
⚠️ REGLAS PARA CALIFICAR:
- Sé decisivo: elige UNA etiqueta (o null si no hay objeciones ni anticipación).
- BUENO cuando el asesor resuelve o reduce la resistencia, o la anticipa proactivamente.
- MEJORABLE cuando hay intento de responder pero la objeción queda sin resolver realmente,
  o cuando resuelve la objeción pero no genera compromiso ni urgencia post-resolución.
- MALO cuando el asesor agrava la situación, ignora la objeción o huye del tema.
- Si dudas entre BUENO y MEJORABLE: ¿el lead quedó menos resistente después? Si sí → BUENO.
- Si el lead confirma explícitamente que sus dudas se resolvieron → BUENO sin excepción.
- Si la objeción era logística (timing/viaje) y se acordó pago parcial o alternativa → BUENO.
- NO marques BUENO si resolvió la objeción pero dejó la conversación sin siguiente paso concreto.
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.
"""
        
        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
Identifica y evalúa el manejo de objeciones en esta conversación:

{transcripcion}

Genera la evaluación en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_objeciones")
        return self._extract_json_safe(resp)