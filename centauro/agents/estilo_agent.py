"""
Agente Evaluador: Estilo, Tono y Vocabulario

INSTRUCCIÓN: Copia este archivo en:
C:\\Users\\uscp9a\\Grupo Planeta\\BI POWER - General\\PBI\\PROYECTOS\\Proyecto_Centauro\\centauro\\agents\\estilo_agent.py
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt

class EstiloAgent(BaseEvaluatorAgent):
    """
    Evalúa la calidad comunicativa del asesor a lo largo de toda la conversación
    
    Criterios clave:
    - Tono profesional pero cercano
    - Vocabulario adaptado al lead (no técnico en exceso ni coloquial)
    - Ritmo adecuado (no atropella ni aburre)
    - Empatía y escucha activa
    - Lenguaje positivo
    """
    
    def __init__(self):
        super().__init__(nombre_bloque="Estilo y comunicación")
    
    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """Evalúa el estilo comunicativo en toda la conversación"""

        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual, contexto_usuario)
            confianza = self._calcular_confianza(resultado_raw)
            
            # Validar aspectos críticos
            aspectos = resultado_raw.get("aspectos_evaluados", {})
            problemas_graves = []
            
            if aspectos.get("tono") == "inapropiado":
                problemas_graves.append("Tono inapropiado detectado")
                confianza *= 0.7
            
            if aspectos.get("empatia") == "ausente":
                problemas_graves.append("Falta de empatía")
                confianza *= 0.8
            
            return EvaluationResult(
                bloque=self.nombre_bloque,
                calificacion=resultado_raw.get("calificacion"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=resultado_raw.get("evidencias_extra", []),
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=resultado_raw.get("recomendacion_accionable", ""),
                metadata={
                    "aspectos_evaluados": aspectos,
                    "problemas_graves": problemas_graves,
                    "fortaleza_principal": resultado_raw.get("fortaleza_principal", "")
                }
            )
            
        except Exception as e:
            print(f"   ❌ Error en evaluación de Estilo: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, transcripcion: str, manual: str, contexto_usuario: str = None) -> dict:
        """Llama al LLM con prompt especializado"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion)

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de ESTILO, TONO Y VOCABULARIO en comunicación comercial.

TU ÚNICA TAREA: Evaluar la CALIDAD COMUNICATIVA del [ASESOR] a lo largo de toda la conversación.

CONTEXTO DEL SPEECH Y BUENAS PRÁCTICAS:
{manual_enriquecido}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EL SPEECH COMO CARRETERA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El speech NO define un tono o vocabulario exacto a imitar. Es la CARRETERA: define
los límites de lo profesional y apropiado. Un asesor con un estilo propio, cálido
y efectivo que conecta con el lead → BUENO, aunque no suene al speech de referencia.
Lo que evalúas es si el estilo DAÑA la conversación (tono inapropiado, muletillas
excesivas, falta de empatía) o si conduce bien dentro de los límites del profesionalismo.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ADAPTACIÓN AL PERFIL DEL LEAD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El estilo "correcto" NO es el mismo para todos los leads. El asesor debe adaptar
su comunicación al perfil de quien tiene delante:

El perfil del lead tiene DOS dimensiones que el asesor debe leer y a las que
debes atender para evaluar si el estilo fue apropiado:

DIMENSIÓN 1 — INDUSTRIA / ROL:
- PERFIL MARKETING / VENTAS / CREATIVO: valoran conversación cercana, empatía,
  tono humano, hablar "de tú a tú". Un estilo espontáneo e informal con este
  perfil es BUENO, no MEJORABLE. Lo que se penaliza es el tono robótico o
  demasiado comercial, no la informalidad que genera conexión real.
- PERFIL CORPORATIVO / DIRECTIVO / TÉCNICO: esperan más estructura, precisión
  y un tono más formal. El asesor que adapta su registro a esto = BUENO.

DIMENSIÓN 2 — EDAD / SENIORITY:
Tómala como contexto, no como regla rígida. Un lead joven puede perfectamente
desenvolverse en un entorno directivo, y un asesor de perfil similar puede adaptar
su tono de forma más cercana o entre iguales. Eso no es un error, es lectura del contexto.

Lo que sí evalúa esta dimensión:
- Si el asesor detectó el nivel del lead (junior, senior, etc.) y adaptó su
  registro natural a eso → señal positiva, aunque la adaptación sea sutil.
- Si el asesor habla de forma condescendiente con alguien de amplia trayectoria
  (sobre-explicando cosas básicas, ignorando su experiencia) → señal negativa.
- Si el asesor y el lead son de perfil similar o edad parecida y el asesor adapta
  el tono a algo más entre iguales → es apropiado, no penalices.

⚠️ PARA LA RECOMENDACIÓN DE COACHING:
Adapta SIEMPRE las frases de ejemplo a AMBAS dimensiones del perfil del lead.
Si el lead es joven y de marketing, usa un tono cercano y aspiracional. Si es
senior y directivo, usa un tono peer-to-peer y orientado al ROI profesional.
Las técnicas de los libros son válidas, pero los ejemplos concretos deben sonar
naturales para ese perfil específico.

ASPECTOS A EVALUAR:

1. **TONO**: ¿Cómo suena el asesor?
   - Profesional vs informal
   - Cercano vs distante
   - Entusiasta vs monótono
   - Respetuoso vs condescendiente

2. **VOCABULARIO**: ¿Qué palabras usa?
   - Adaptado al nivel del lead vs muy técnico/simple
   - Claro vs confuso
   - Positivo vs negativo
   - Ejemplos y analogías vs abstracto

3. **EMPATÍA**: ¿Conecta emocionalmente?
   - Valida emociones del lead
   - Usa frases empáticas ("Entiendo...", "Tiene sentido...")
   - Personaliza el lenguaje (usa el nombre del lead)
   - Comparte experiencia propia o analogía personal para generar conexión
   ⚠️ EMPATÍA INVERSA: cuando el asesor comparte su propia historia o experiencia
   para ponerse en el lugar del lead ("A mí también me pasó algo similar...",
   "Conozco a alguien que estaba en tu misma situación..."), esto ES una señal
   de empatía genuina. No requiere frases tipo "Entiendo...": contar algo propio
   que conecta con la situación del lead CUENTA como momento de empatía real.

4. **RITMO**: ¿Cómo gestiona el tiempo?
   - Deja hablar al lead vs monopoliza
   - Pausas adecuadas vs atropella
   - Verifica comprensión vs asume
   ⚠️ SEÑAL DE ALERTA — LEAD SILENCIOSO: si el lead apenas habla a lo largo de
   toda la conversación (respuestas muy cortas, monosílabos, largas intervenciones
   del asesor sin invitar al lead a participar) → el asesor no está generando
   diálogo real. Esto debe mencionarse en el razonamiento y contribuye a MEJORABLE.

5. **PROFESIONALISMO**: ¿Genera confianza?
   - Lenguaje profesional vs coloquial en exceso
   - Sin muletillas excesivas ("ehhh", "bueno", "vale vale")
   - Seguro vs dubitativo
   ⚠️ JERGA TÉCNICA: si el asesor usa terminología especializada que el lead no domina
   (tecnicismos del sector, siglas, conceptos académicos sin explicar) y esto genera
   distancia o falta de comprensión → señal negativa específica. Menciónalo explícitamente
   en el razonamiento y en las evidencias. Es diferente de "informal": la jerga técnica
   sin adaptar aleja al lead en vez de acercarlo.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ ANTES DE CALIFICAR — VERIFICACIÓN OBLIGATORIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DETENTE. Antes de elegir la calificación, DEBES responder SÍ o NO a cada uno
de estos 5 puntos. Cuenta cuántos tienen respuesta NEGATIVA (= fallo):

  1. ¿El tono fue profesional y cercano (no mecánico ni inapropiado)?              → SÍ / NO
  2. ¿El vocabulario estuvo adaptado al lead (sin jerga técnica inadecuada)?       → SÍ / NO
  3. ¿Hubo al menos un momento de empatía real (incluye empatía inversa)?          → SÍ / NO
  4. ¿El lead participó activamente (no lead silencioso ni asesor monopolizando)?   → SÍ / NO
  5. ¿El profesionalismo fue alto (sin muletillas excesivas, seguro)?              → SÍ / NO

CUENTA los NOs. Ese número es tu "contador_fallos_criticos" en el JSON.

🔴 COHERENCIA ENTRE FALLOS Y CALIFICACIÓN:
   Analiza el peso real de cada fallo. Los 5 criterios comunicativos son todos relevantes
   para que el lead se sienta cómodo y confíe en el asesor. Tono inapropiado, vocabulario
   inadaptado, ausencia de empatía, lead silencioso y profesionalismo bajo son señales que
   acumuladas dañan la conversación. Si la mayoría fallaron, la calificación debe ser MALO.
   No por un umbral mecánico, sino porque múltiples fallos comunicativos crean distancia y
   erosionan la confianza. No detectes múltiples fallos graves en el estilo y concluyas
   MEJORABLE: sería incoherente con tu propio análisis.

CRITERIOS DE CALIFICACIÓN (elige UNA de las 3 etiquetas):

⚠️ DISTINCIÓN CRÍTICA — INFORMAL vs. DESORGANIZADO:
Son dos cosas completamente diferentes. NO las confundas:
- INFORMAL: tono conversacional, cercano, sin rigidez. Para perfiles de marketing,
  ventas o creativos, esto es POSITIVO. Un asesor informal que conecta bien = BUENO.
- DESORGANIZADO: no tiene hilo conductor, salta de tema sin estructura, el lead no
  sabe dónde está la conversación. Esto sí es negativo e impacta la calificación.
Un asesor puede ser informal Y estructurado a la vez. NO marques MEJORABLE o MALO
solo porque el tono es informal si la conversación tiene coherencia y orden.

🔴 MALO — el estilo comunicativo genera rechazo, incomodidad o rompe la confianza:
   - Tono grosero, condescendiente, o tan desorganizado que el lead no entiende la conversación
   - Muletillas constantes que restan credibilidad o dificultan la comprensión
   - Cero empatía: el asesor habla sin considerar cómo se siente el lead
   - Genera incomodidad, distancia o rechazo visible en el lead
   - También: tono agresivo, impaciente o que hace sentir al lead presionado

🟡 MEJORABLE — el estilo es correcto pero frío, mecánico y sin conexión real:
   - Tono educado pero robótico, como si siguiera un guión
   - Sin momentos de empatía o cercanía genuina a lo largo de la conversación
   - El lead responde pero no hay señales de que se sienta cómodo o escuchado
   - Profesional pero impersonal: correcto, pero no conecta
   - TONO MECÁNICO: patrón específico a detectar — el asesor encadena bloques de
     información sin pausas ni preguntas, el lead apenas tiene espacio para hablar
     y la conversación suena más a monólogo que a diálogo

🟢 BUENO — el estilo genera confianza y el lead se siente cómodo participando:
   - Hay al menos un momento de empatía real o cercanía genuina (incluye: frases
     empáticas directas, uso del nombre del lead, compartir una experiencia propia
     relevante, generar un momento de humor o complicidad, o empatía inversa)
   - El tono es profesional sin ser rígido
   - El lead participa activamente y no parece incómodo
   - No es necesario que sea perfecto: basta con que el estilo sume a la conversación en vez de restarle

FORMATO JSON OBLIGATORIO:
{{
  "contador_fallos_criticos": 0,
  "calificacion": "MALO" | "MEJORABLE" | "BUENO",
  "observabilidad": "ALTA",
  "evidencia_principal": "[ASESOR]: Ejemplo representativo del tono/estilo... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "Ejemplo de empatía: [ASESOR]: ... (COPY-PASTE LITERAL)",
    "Ejemplo de vocabulario adaptado: [ASESOR]: ... (COPY-PASTE LITERAL)",
    "Muletilla o problema detectado: [ASESOR]: ... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "En 4-6 líneas de texto fluido, sin listas ni SÍ/NO: explica cómo fue el estilo comunicativo del asesor, qué tono usó, si conectó con el lead emocionalmente, qué funcionó y qué no. Por qué merece esa calificación. Conecta con lo que ocurrió realmente en la conversación.",
  "recomendacion_accionable": "IMPORTANTE: Combina en un SOLO texto fluido: (1) Qué mejorar en estilo/comunicación, (2) UNA técnica de los libros de ventas del CONTEXTO que aplique al estilo comunicativo, explicando POR QUÉ funciona y dando 2 ejemplos de frases. Máx 6-8 líneas. NO copies texto literal de los libros.",
  "aspectos_evaluados": {{
    "tono": "profesional_cercano" | "mecanico" | "inapropiado",
    "vocabulario": "adaptado" | "generico" | "inadecuado",
    "empatia": "presente" | "neutra" | "ausente",
    "ritmo": "equilibrado" | "monopoliza" | "pasivo",
    "profesionalismo": "alto" | "medio" | "bajo"
  }},
  "fortaleza_principal": "El aspecto comunicativo más destacable del asesor",
  "perfil_industria_lead": "MARKETING_VENTAS_CREATIVO" | "CORPORATIVO_DIRECTIVO" | "NO_DETERMINADO",
  "perfil_seniority_lead": "JOVEN_JUNIOR" | "SEMI_SENIOR" | "SENIOR_CONSOLIDADO" | "NO_DETERMINADO",
  "lead_participa_activamente": true/false
}}

⚠️ REGLAS PARA CALIFICAR (después de contar los fallos):
- MALO: contador_fallos_criticos >= 3, O el estilo genera rechazo/incomodidad/desconfianza.
- MEJORABLE: contador_fallos_criticos = 1-2. Correcto pero mecánico, educado pero sin calidez.
- BUENO: contador_fallos_criticos = 0. El estilo suma, el lead se siente cómodo, hay conexión real.
- Si dudas entre BUENO y MEJORABLE: ¿hay algún momento donde el lead se abre o responde con confianza? Si sí → BUENO.
- Si el asesor compartió una experiencia propia (empatía inversa) → cuenta como empatía real → inclínate por BUENO.
- Evidencias LITERALES (COPY-PASTE exacto).
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
DEBES integrarlos en tu "recomendacion_accionable" de forma ORGÁNICA, pero con
una regla crítica: la técnica elegida DEBE ser coherente con el patrón detectado.

CONEXIÓN OBLIGATORIA PATRÓN → TÉCNICA:
- Si detectaste MULETILLAS o problemas de RITMO → elige una técnica sobre
  comunicación, pausa, ritmo o presencia vocal. NO elijas una técnica de ventas
  genérica (SPIN, cierre, prospección) si el problema es comunicativo.
- Si detectaste falta de EMPATÍA → elige una técnica sobre conexión emocional,
  escucha activa o rapport. NO elijas una técnica de argumentación.
- Si detectaste TONO MECÁNICO → elige una técnica sobre naturalidad, espontaneidad
  o conversación consultiva.
- Si el asesor lo hizo todo bien (BUENO) → elige la técnica más avanzada que
  podría elevar aún más su nivel, conectada con su fortaleza principal.

Si el contexto tiene variedad de libros disponibles, evita recomendar siempre
el mismo. Elige el que tenga la técnica MÁS relevante para el patrón concreto
de esta llamada, aunque sea de un libro menos prominente en el contexto.

- Explica POR QUÉ esa técnica concreta le ayudaría (conecta con la situación real)
- Da 2 frases concretas que podría haber usado, adaptadas al perfil del lead
- NO copies texto literal del libro, adapta con tus palabras

REGLAS CRÍTICAS:
- Evalúa TODA la conversación, no solo un momento
- Evidencias LITERALES de la transcripción
- Diferencia entre "robot profesional" (MEJORABLE) y "humano profesional" (BUENO)
- BUENO requiere que el lead se sienta realmente conectado con el asesor en algún momento
- Identifica patrones: ¿Es consistente o cambia a lo largo de la conversación?
"""
        
        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
Evalúa el estilo comunicativo del [ASESOR] en esta conversación completa:

{transcripcion}

Genera la evaluación en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_estilo")
        return self._extract_json_safe(resp)