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

🟡 MEJORABLE — el asesor responde pero de forma reactiva y sin profundidad:
   - Solo reacciona a objeciones explícitas, nunca anticipa
   - Responde con información correcta pero mecánica, sin validar la preocupación
   - No profundiza en el porqué real de la objeción
   - El lead queda igual de dudoso o inseguro tras la respuesta
   - Intenta resolver pero no usa ninguna técnica estructurada

🟢 BUENO — el asesor maneja y/o anticipa objeciones con confianza y el lead suaviza su postura:
   - Anticipa objeciones comunes sin que el lead las plantee (trabaja sin miedo a ellas)
   - O si el lead objeta: valida la preocupación y profundiza antes de responder
   - Usa alguna técnica estructurada (feel-felt-found, boomerang, aislamiento, etc.)
   - El lead suaviza su resistencia, expresa más apertura o acepta el razonamiento
   - No es necesario que use técnica perfecta: basta con que la objeción quede resuelta o reducida

TIPOS COMUNES DE OBJECIONES:
- Precio ("Es caro", "No tengo presupuesto")
- Tiempo ("No tengo tiempo", "Es muy largo")
- Autoridad ("Tengo que consultarlo", "Mi empresa debe aprobarlo")
- Necesidad ("No estoy seguro si lo necesito")
- Urgencia ("Lo pensaré", "Más adelante")

FORMATO JSON OBLIGATORIO:
{{
  "calificacion": "MALO" | "MEJORABLE" | "BUENO" | null,
  "observabilidad": "ALTA" | "NO_OBSERVABLE",
  "evidencia_principal": "[LEAD]: Objeción principal... [ASESOR]: Respuesta... (COPY-PASTE LITERAL). Si hubo anticipación, pon la frase del asesor anticipándose.",
  "evidencias_extra": [
    "[ASESOR]: Validación de la objeción o anticipación... (COPY-PASTE LITERAL)",
    "[LEAD]: Reacción posterior... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "¿Anticipó objeciones? ¿Validó? ¿Aisló? ¿Usó técnica? ¿Resolvió o generó más resistencia? ¿Trabajó con miedo o con confianza? ¿Por qué esa calificación?",
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
- MEJORABLE cuando hay intento de responder pero la objeción queda sin resolver realmente.
- MALO cuando el asesor agrava la situación, ignora la objeción o huye del tema.
- Si dudas entre BUENO y MEJORABLE: ¿el lead quedó menos resistente después? Si sí → BUENO.
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