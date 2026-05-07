"""
Agente Evaluador: Cierre y Próximos Pasos (v4.1)

Evalúa:
- Cómo el asesor cierra la conversación
- Establecimiento de próximos pasos
- Técnicas de cierre utilizadas

NUEVO v4.1:
- Detección de técnicas de cierre avanzadas
- Feedback personalizado con coaching de libros
- Bonificación por técnicas efectivas
"""
from .base_agent import BaseEvaluatorAgent, EvaluationResult
from ..llm_client import consultar_gpt
import re

class CierreAgent(BaseEvaluatorAgent):
    """
    Evalúa cómo el asesor cierra la conversación y establece próximos pasos

    IMPORTANTE: El cierre NO es necesariamente una venta inmediata.
    En venta consultiva de formación, el objetivo suele ser:
    - Comprometer envío de documentación al comité de admisiones
    - Agendar próxima llamada/reunión
    - Establecer fecha concreta para siguiente paso

    Criterios clave:
    - Define próximo paso claro y específico
    - Genera compromiso (fecha/hora)
    - Resume lo acordado
    - Usa técnica de cierre (no solo "piénsalo")

    v4.1: Detecta y premia técnicas de cierre, genera coaching personalizado
    """

    def __init__(self):
        super().__init__(nombre_bloque="Cierre y próximos pasos")
        self.longitud_analisis = 12000  # v5.2: Usado solo para detección Python (fin abrupto, desconexión)

    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None) -> EvaluationResult:
        """Evalúa el cierre usando principalmente el final de la conversación"""

        # Extraer final de la conversación
        final_conversacion = transcripcion[-self.longitud_analisis:]

        # Detectar si la grabación cortó antes del cierre (problema técnico)
        if self._detectar_fin_abrupto(final_conversacion):
            return self._crear_resultado_off_record()

        # Detectar posible desconexión del lead — se pasa como SEÑAL al LLM,
        # no como decisión final. El LLM decide si fue real/definitiva o parcial.
        indicio_desconexion = self._detectar_desconexion_lead(final_conversacion)

        try:
            resultado_raw = self._evaluar_con_llm(
                final_conversacion, transcripcion, contexto_manual, contexto_usuario,
                indicio_desconexion=indicio_desconexion
            )
            # Si el LLM confirma que la desconexión fue definitiva → resultado especial
            if resultado_raw.get("desconexion_definitiva") is True:
                print(f"   ℹ️ LLM confirmó desconexión definitiva del lead — evaluación no aplicable")
                return self._crear_resultado_desconexion()

            confianza = self._calcular_confianza(resultado_raw)

            # Tope universal: 3+ fallos críticos = MALO
            contador_fallos = resultado_raw.get("contador_fallos_criticos", 0)
            cal_tmp, raz_tmp = self._aplicar_tope_fallos_criticos(
                resultado_raw.get("calificacion"), contador_fallos, resultado_raw.get("razonamiento", "")
            )
            if cal_tmp != resultado_raw.get("calificacion"):
                resultado_raw["calificacion"] = cal_tmp
                resultado_raw["razonamiento"] = raz_tmp

            # Validar que haya próximo paso concreto
            proximo_paso = resultado_raw.get("proximo_paso_concreto", "")
            if not proximo_paso or "vago" in proximo_paso.lower():
                print(f"   ⚠️ Próximo paso no suficientemente concreto")
                confianza *= 0.8

            # Detectar técnicas
            tecnicas_detectadas = resultado_raw.get("tecnicas_detectadas", [])
            recomendacion_base = resultado_raw.get("recomendacion_accionable", "")
            mejoras = self._formato_mejoras(resultado_raw.get("mejoras", []))

            # ── Validar razonamiento: detectar truncamiento del LLM ──────────
            razonamiento_raw = resultado_raw.get("razonamiento", "")
            razonamiento_ok  = razonamiento_raw.strip()
            _truncado = (
                len(razonamiento_ok) < 120
                or razonamiento_ok.endswith("(")
                or razonamiento_ok.endswith(",")
            )
            if _truncado:
                print(f"   ⚠️ Razonamiento de Cierre posiblemente truncado "
                      f"({len(razonamiento_ok)} chars). Añadiendo nota.")
                razonamiento_ok = (
                    razonamiento_ok
                    + (" ..." if not razonamiento_ok.endswith("...") else "")
                    + "\n\n[Nota automática: el texto anterior puede estar incompleto — "
                    "el modelo recortó la respuesta. Consultar el feedback de coaching "
                    "más abajo para el análisis completo.]"
                )
                confianza *= 0.7  # Reducir confianza si el razonamiento es dudoso

            # NOTA: El coaching se aplica en batch desde el orchestrator para optimizar llamadas API

            return EvaluationResult(
                bloque=self.nombre_bloque,
                calificacion=resultado_raw.get("calificacion"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=resultado_raw.get("evidencias_extra", []),
                razonamiento=razonamiento_ok,
                recomendacion_accionable=recomendacion_base,
                mejoras=mejoras,
                metadata={
                    "proximo_paso": proximo_paso,
                    "compromiso_fecha": resultado_raw.get("compromiso_fecha", False),
                    "valido_antes_cerrar": resultado_raw.get("valido_antes_cerrar", False),
                    "tecnica_cierre": resultado_raw.get("tecnica_cierre", "ninguna"),
                    "recepcion_cliente": resultado_raw.get("recepcion_cliente", {}),
                    "tecnicas_detectadas": tecnicas_detectadas,
                    "feedback_personalizado": resultado_raw.get("feedback_personalizado", ""),
                    "seguimiento_proximos_pasos": resultado_raw.get("seguimiento_proximos_pasos", {})
                }
            )

        except Exception as e:
            print(f"   ❌ Error en evaluación de Cierre: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, final: str, transcripcion_completa: str, manual: str, contexto_usuario: str = None, indicio_desconexion: bool = False) -> dict:
        """Llama al LLM con prompt especializado"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion_completa)

        if indicio_desconexion:
            seccion_desconexion = """⚠️ SEÑAL AUTOMÁTICA: el sistema detectó un posible patrón de desconexión del lead
en el tramo final de la transcripción (asesor hablando sin respuesta del lead,
o frases como '¿Hola?', '¿Me escuchas?'). Lee el final con atención y determina:

¿La desconexión fue DEFINITIVA (el lead nunca volvió a responder)?
  → SÍ: "desconexion_definitiva": true — la evaluación no es aplicable
  → NO (el lead volvió a conectarse y hubo cierre real): "desconexion_definitiva": false
     y evalúa el cierre normalmente

Si marcas desconexion_definitiva=true, el resto de los campos pueden estar vacíos
o con valores neutros — solo importa el razonamiento explicando la situación.
"""
        else:
            seccion_desconexion = """Si en la transcripción encuentras señales claras de que el lead se desconectó
definitivamente (el asesor dice "¿Hola?", "¿Me escuchas?" sin respuesta, varias
intervenciones del asesor sin que el lead conteste), marca "desconexion_definitiva": true
y NO evalúes el cierre como un fallo del asesor.
Si no hay desconexión o el lead volvió a conectarse, marca "desconexion_definitiva": false.
"""

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de CIERRE Y PRÓXIMOS PASOS en venta consultiva de formación.

TU ÚNICA TAREA: Evaluar cómo cerró el [ASESOR] la conversación y qué próximos pasos estableció.

TONO DE REDACCIÓN: Escribe SIEMPRE en TERCERA PERSONA al referirte al asesor ("el asesor hizo...", "el asesor podría..."). NUNCA uses segunda persona ("hiciste...", "podrías...", "tu objetivo...").

CONTEXTO DEL SPEECH Y BUENAS PRÁCTICAS:
{manual_enriquecido}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EL SPEECH COMO CARRETERA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El speech NO es una checklist de frases exactas. Es la CARRETERA: define los límites.
Un asesor que cierra con sus propias palabras pero logra compromiso real → BUENO.
Lo que evalúas es si se sale de los límites (cierre pasivo, sin próximo paso, sin validar)
o si conduce bien dentro de ellos.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ DETECCIÓN PRIORITARIA: ¿SE DESCONECTÓ EL LEAD?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{seccion_desconexion}
⚠️ DIFERENCIA IMPORTANTE:
- Desconexión del lead = lead cuelga o pierde señal → NO es fallo del asesor
- Cierre pasivo = lead sí está pero el asesor no propone nada → SÍ es fallo del asesor

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CIRCUNSTANCIAS ATÍPICAS DE LA CONVERSACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Antes de evaluar el cierre, detecta si el lead declaró alguna restricción que
condicionó el ritmo de la conversación. En particular:

⚠️ RESTRICCIÓN DE TIEMPO: Si el lead indicó en algún momento anterior de la
llamada que tenía poco tiempo ("no tengo mucho tiempo", "tengo que cortar pronto",
"voy con prisa", "solo tengo unos minutos") → un cierre más rápido o condensado
puede ser la respuesta adecuada del asesor, no una falta de técnica. El asesor
que ajusta la velocidad del cierre a la disponibilidad declarada del lead está
leyendo bien la situación. Detecta y menciona esta circunstancia en el razonamiento.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALCANCE: EVALÚA TODA LA CONVERSACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El cierre no empieza cuando el asesor "pasa al bloque de cierre". La construcción
del compromiso y los siguientes pasos puede comenzar desde los primeros minutos
de la conversación.

Busca en TODA la transcripción:
  ✓ Momentos en que el asesor orientó la conversación hacia un siguiente paso
  ✓ Señales de compromiso del lead en cualquier punto (no solo al final)
  ✓ Cómo el asesor gestionó la urgencia y el timing a lo largo de la llamada
  ✓ Vinculación al comité de admisión o ayudas económicas mencionadas en cualquier tramo

Evalúa el CONJUNTO de cómo el asesor construyó el camino hacia el compromiso
durante toda la conversación, no solo el tramo final.

⚠️ SEÑAL CRÍTICA — Conversación sin ningún próximo paso ni seguimiento:
Al leer el tramo final de la conversación, comprueba si se acordó ALGO concreto:
  - Una fecha de llamada, aunque sea vaga ("mañana", "el lunes", "esta semana")
  - Un envío de documentación que el lead aceptó explícitamente
  - Una acción concreta comprometida por alguna de las dos partes
  - Un siguiente paso en el proceso de admisión mencionado y aceptado

Si NO encuentras NINGUNO de estos elementos, estás ante una AUSENCIA TOTAL DE CIERRE.
En ese caso, la calificación es MALO sin excepción, independientemente de lo bien que
haya transcurrido el resto de la conversación.

⚠️ OJO CON ESTE PATRÓN FRECUENTE — "despedida pasiva sin acuerdo":
"Te mando la información" / "Ya te escribo" / "Nos hablamos" sin que el lead lo
acepte explícitamente Y sin que quede definida ninguna acción o fecha concreta
→ NO cuenta como cierre. Es un fin de llamada pasivo sin estructura.
Si el asesor termina así y el lead no confirma nada, la conversación terminó sin avance.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOBRE EL CIERRE EN VENTA CONSULTIVA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El "cierre exitoso" NO es necesariamente que el lead diga "SÍ, lo compro ahora".
El objetivo es avanzar al siguiente paso del proceso:
- Envío de documentación al comité de admisiones
- Compromiso de enviar CV/titulación
- Agendar llamada de seguimiento con fecha concreta
- Programar entrevista de admisión

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DISTINCIÓN CRÍTICA: CIERRE DE VENTA vs. COMPROMISO DE SEGUIMIENTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Un compromiso de seguimiento (fecha + hora para la próxima llamada) es PARTE del cierre
consultivo, pero NO ES el cierre en sí. El asesor debe hacer ambas cosas y en este orden:

PRIMERO — Intentar cerrar o comprometer al lead en el proceso de admisión:
  El asesor debe preguntar activamente si el lead quiere avanzar ANTES de aceptar que el
  seguimiento sea el plan A: "¿Te parece si damos el primer paso hoy?" / "¿Lo damos por
  hecho y te meto en el próximo comité?" / "¿Qué necesitarías para arrancar esta semana?"
  Este intento de avanzar en la venta debe ocurrir ANTES de proponer el seguimiento.

DESPUÉS — Si el lead no puede comprometerse ahora → fijar seguimiento concreto (plan B):
  Solo cuando el lead no puede avanzar en el acto, el asesor propone fecha + hora.
  El seguimiento es el plan B consultivo, no el plan A.

⚠️ PATRÓN A PENALIZAR — Seguimiento sin intento de cierre:
El asesor fija directamente un seguimiento ("te llamo el martes a las 11") sin antes
preguntar si el lead quiere avanzar = no intentó cerrar la venta.
Esto limita la calificación a MEJORABLE como máximo, aunque la fecha+hora sean correctas.

⚠️ PATRÓN CRÍTICO — MALO — Lead en control del cierre:
Si el lead termina la llamada con frases como "Mándame la info y te respondo" / "Ya te
escribo yo" / "Lo pienso y te aviso" — y el asesor acepta sin proponer ningún compromiso
alternativo — la venta quedó completamente en manos del lead. El asesor perdió el control
del proceso. → MALO sin excepción. No importa qué pasó antes: si el lead dicta los
próximos pasos sin comprometerse con nada y el asesor no reacciona, la conversación
terminó sin avance real.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLAVES DE ESTE CIERRE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. REVALIDACIÓN ANTES DE CERRAR:
   El asesor no da por supuesto que el lead está convencido. Antes de proponer el
   siguiente paso, revalida los puntos clave tratados: se asegura de que el lead no
   tiene dudas sobre el programa, el proceso de admisión y la inversión. No basta con
   preguntar "¿Tienes alguna duda?": el asesor debe repasar activamente lo hablado y
   confirmar que el lead lo ve claro. "¿Cómo lo ves? ¿Todo lo que hemos visto encaja
   con lo que buscas?" / "¿Hay algo que no te haya quedado claro antes de avanzar?"
   Esta revalidación es especialmente crítica en el cierre porque es el último momento
   para resolver lo que impide comprometerse.

2. PREGUNTA DIRECTA DE COMPROMISO (señal positiva, no penaliza si no se hace):
   Aunque el lead haya verbalizado durante la conversación que quiere avanzar, hacer
   una pregunta directa al cerrar es la mejor práctica para formalizar ese compromiso:
   "¿Entonces lo damos por hecho y te meto en el próximo comité?" /
   "¿Puedo contar con que me mandas la documentación hoy?"
   Si el asesor la hace → suma. Si no la hace pero el lead sí avanzó → no penaliza.
   NO reduzcas la calificación por ausencia de esta pregunta.

3. GENERAR URGENCIA CON COMITÉ Y AYUDAS ECONÓMICAS:
   Al cerrar, el asesor debe vincular el siguiente paso a la fecha del comité
   y/o a las ayudas económicas disponibles para crear urgencia real:
   "El próximo comité es el [fecha] — si me mandas la documentación esta semana
   puedo incluirte" / "La bonificación que hemos hablado es válida hasta el comité,
   si lo dejamos para más adelante perdería ese descuento."
   Ausencia de estas palancas al cerrar = oportunidad perdida (contribuye a MEJORABLE).

3b. COHERENCIA ENTRE URGENCIA EMPLEADA Y CIERRE:
   Si el asesor usó argumentos de urgencia en cualquier momento de la conversación
   (plazas limitadas, fecha del próximo comité, descuento con fecha límite), DEBE
   reflejar esa urgencia en el cierre y actuar en consecuencia.
   ⚠️ INCOHERENCIA QUE DEBE SER MALO: El asesor usó urgencia en un bloque previo
   ("quedan pocas plazas", "la oferta expira esta semana", "el comité cierra el viernes")
   pero en el cierre dejó todo abierto sin reflejar esa urgencia ni usarla para
   comprometer al lead. No solo es un cierre pasivo: el asesor contradice su propia
   estrategia. Si usó urgencia y luego cerró de forma abierta y ambigua → MALO,
   no MEJORABLE. El feedback debe señalar la incoherencia explícitamente.

3c. INTENTO REAL DE CIERRE DE VENTA:
   El asesor debe intentar que el lead avance en el proceso de admisión ANTES de
   aceptar que el siguiente paso sea una llamada futura. Esto incluye:
   - Preguntar directamente si el lead está listo para avanzar
   - Proponer el inicio del proceso de admisión o el envío de documentación
   - Gestionar las objeciones que impiden comprometerse ahora
   Un asesor que salta directamente al seguimiento sin intentar el cierre real = no
   vendió, solo agendó. El seguimiento es necesario pero insuficiente por sí solo para
   alcanzar BUENO.

4. PRÓXIMO PASO CONCRETO CON FECHA Y HORA:
   El siguiente paso debe ser específico y con fecha Y hora reales. Hay grados:
   - SIN FECHA (→ MALO): "Piénsalo y me dices", "Ya hablaremos", ningún próximo paso.
   - SOLO FECHA SIN HORA (→ MEJORABLE): "Te llamo mañana", "Esta semana te escribo",
     "El lunes hablamos" — hay referencia temporal pero SIN hora concreta. MÁXIMO MEJORABLE.
   - FECHA + HORA CONCRETA + COMPROMISO DEL LEAD (→ BUENO): "Te llamo el martes a las 11,
     ¿te va bien?" con el lead confirmando. "Mañana a las 5" también cuenta si el lead acepta.
   ⚠️ REGLA ESTRICTA: Sin hora concreta → la calificación es MEJORABLE como máximo, incluso
   si todo lo demás está bien. La hora es obligatoria para alcanzar BUENO.
   IMPORTANTE: "mañana", "esta tarde", "el lunes" SÍ son referencias temporales reales y
   deben recogerse en fecha_hora. NO los marques como "No especificada".

4. TÉCNICA DE CIERRE:
   - Doble alternativa: "¿Prefieres que te llame martes o jueves?"
   - Asuntivo: "Entonces te envío el formulario hoy y tú me lo devuelves el viernes, ¿perfecto?"
   - Resumen-acción: "Hemos visto que X encaja con tu objetivo Y. El siguiente paso es Z."

5. NO CIERRE PASIVO:
   "Piénsalo y me dices" sin fecha ni compromiso = MALO. El asesor lidera el proceso,
   no espera que el lead tome la iniciativa.

6. SIMPLICIDAD EN EL PROCESO:
   El asesor debe cerrar con el mínimo de pasos necesarios. Crear complejidad
   innecesaria debilita el cierre:
   ⚠️ PATRÓN A PENALIZAR: "Mañana te mando otra propuesta con los números" /
   "Déjame que lo reviso y te escribo" cuando ese paso podría haberse resuelto
   en la misma llamada. Posponer al día siguiente lo que podría cerrar ahora =
   MEJORABLE. El asesor debe llegar al cierre con la propuesta lista, no construirla
   después de la llamada.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITERIOS DE CALIFICACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 MALO — el asesor no cierra, lo hace de forma completamente pasiva, o deja el proceso sin avance:
   - Termina con "Piénsalo y me dices" sin ningún próximo paso concreto
   - No propone ni fecha, ni acción, ni compromiso de ningún tipo
   - No genera ningún avance en el proceso de admisión
   - También: el lead pregunta por el siguiente paso y el asesor no lo define
   - CRÍTICO: si no hay ni compromiso del lead, NI hora de seguimiento, NI fecha de seguimiento,
     NI próximos pasos bien definidos → es MALO sin excepción. Ausencia de todo esto = MALO.
   - TAMBIÉN MALO — próximo paso vacío sin compromiso real: si el asesor propuso algo
     (ej: "te envío la información") pero el lead respondió con resistencia o negativamente,
     Y el asesor no validó las dudas, Y no generó ningún compromiso real → la conversación
     terminó sin avance real. Proponer enviar información sin que el lead lo acepte con
     compromiso NO cuenta como cierre. Si además no se validaron las dudas del lead →
     MALO, no MEJORABLE.
   ⚠️ REGLA DE ACUMULACIÓN: Si detectas simultáneamente (1) sin validación de dudas,
     (2) sin compromiso real del lead, (3) respuesta negativa o evasiva del lead →
     la calificación debe ser MALO. El feedback debe enumerar estos fallos.
   - TAMBIÉN MALO — urgencia usada pero cierre incoherente: el asesor usó urgencia
     durante la conversación (plazas, comité, descuento) pero en el cierre dejó todo
     abierto sin reflejar esa urgencia. La contradicción entre estrategia y ejecución
     es un fallo grave. → MALO, no MEJORABLE.
   - TAMBIÉN MALO — lead en control del cierre: el lead dictó el siguiente paso
     ("te respondo por WhatsApp", "ya te escribo yo", "lo pienso y te digo") y el
     asesor aceptó sin proponer ningún compromiso alternativo ni fecha concreta.
     El asesor perdió el control del proceso → MALO.

🟡 MEJORABLE — hay un cierre pero le falta al menos uno de los requisitos para ser BUENO:
   - Hay próximo paso pero solo fecha sin hora ("te llamo mañana", "el lunes hablamos") → MEJORABLE
   - Hay fecha y hora pero el lead no confirma compromiso explícito → MEJORABLE
   - Hay compromiso del lead pero sin fecha ni hora concretas → MEJORABLE
   - No valida si el lead tiene dudas antes de cerrar
   - El lead acepta de forma pasiva, sin convicción real
   - El asesor no conecta el cierre con el objetivo del lead ni resume lo acordado
   - No vincula el cierre a la fecha del comité ni a las ayudas económicas disponibles
   - Crea complejidad innecesaria: pospone al día siguiente algo que podría haberse
     cerrado en la llamada ("mañana te mando la propuesta", "lo reviso y te escribo")
   - Fijó un seguimiento con fecha + hora correctas, pero no intentó cerrar la venta
     antes: fue directo al seguimiento sin preguntar si el lead quería avanzar ahora
   ⚠️ Si falla UN solo requisito de los tres (fecha+hora / compromiso / próximos pasos
     bien definidos), la calificación es MEJORABLE aunque todo lo demás esté bien.

🟢 BUENO — el asesor lidera el cierre y genera un compromiso claro con estructura completa:
   ⚠️ REQUISITOS MÍNIMOS OBLIGATORIOS para ser BUENO (deben cumplirse los cuatro):
     (A) Próximos pasos bien definidos con FECHA Y HORA concretas
         (ej: "mañana a las 5", "martes a las 11") — solo fecha sin hora → MEJORABLE
     (B) Compromiso explícito del lead (acepta el siguiente paso con claridad)
     (C) Alguna estructura de cierre: revalida dudas, usa técnica, o resume lo acordado
     (D) Intentó cerrar la venta antes del seguimiento: preguntó activamente si el lead
         quería avanzar en el proceso de admisión antes de proponer la llamada de seguimiento
   - Revalida que el lead no tiene dudas antes de cerrar, o resume lo acordado
   - Usa alguna técnica de cierre (doble alternativa, asuntivo, resumen-acción)
   - El lead confirma su compromiso con claridad
   - Hace una pregunta directa de compromiso, aunque el lead ya hubiera expresado intención
   - Vincula el cierre a la fecha del comité y/o a las ayudas económicas para generar urgencia
   - La urgencia usada durante la conversación se refleja en el tono y la concreción del cierre
   - No es necesario que use todas las técnicas: basta con que cumpla (A)+(B)+(C)+(D)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVIDENCIA REQUERIDA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 1 frase de cierre del asesor con próximo paso
- 1 validación previa al cierre (si existe)
- 1 respuesta del lead confirmando (o no) el compromiso

FORMATO JSON OBLIGATORIO:
{{
  "desconexion_definitiva": false,
  "contador_fallos_criticos": 0,
  "calificacion": "MALO" | "MEJORABLE" | "BUENO" | null,
  "observabilidad": "ALTA" | "NO_OBSERVABLE_OFF_RECORD",
  "evidencia_principal": "[ASESOR]: Frase del cierre con próximo paso... (COPY-PASTE LITERAL)",
  "evidencias_extra": [
    "[ASESOR]: Validación antes del cierre (si existe)... (COPY-PASTE LITERAL)",
    "[ASESOR]: Resumen de acuerdos... (COPY-PASTE LITERAL)",
    "[LEAD]: Respuesta confirmando compromiso... (COPY-PASTE LITERAL)"
  ],
  "razonamiento": "En 4-6 líneas de texto fluido, sin listas ni SÍ/NO: explica cómo condujo el asesor el cierre, qué hizo bien y en qué aspectos falló. Por qué merece esa calificación. Conecta con lo que ocurrió realmente al final de la conversación. OBLIGATORIO si la calificación es MALO o MEJORABLE: incluye en el texto al menos una cita literal entre comillas de la conversación que muestre el fallo principal.",
  "recomendacion_accionable": "Qué mejorar + UNA técnica concreta de los libros de ventas del CONTEXTO con 2 frases que el asesor podría haber usado en ESTA conversación. Máx 6-8 líneas. No copies texto literal.",
  "mejoras": ["Frase de acción en infinitivo máx 8 palabras (ej: Concretar fecha y hora de seguimiento). Lista vacía [] si BUENO sin fallos relevantes."],
  "proximo_paso_concreto": "Descripción del próximo paso acordado (o 'ninguno' si no lo hubo)",
  "compromiso_fecha": true/false,
  "valido_antes_cerrar": true/false,
  "tecnica_cierre": "doble_alternativa" | "asuntivo" | "resumen_accion" | "ninguna",
  "recepcion_cliente": {{
    "estado": "COMPROMETIDO" | "NEUTRO" | "RESISTENTE" | "ENTUSIASTA",
    "evidencia": "[LEAD]: Respuesta del lead... (COPY-PASTE LITERAL)"
  }},
  "tecnicas_detectadas": ["lista de técnicas que usó"],
  "feedback_personalizado": "Mensaje sobre el asesor en TERCERA PERSONA: algo específico que hizo bien + UNA mejora concreta con ejemplo de frase. Máx 3-4 líneas.",
  "seguimiento_proximos_pasos": {{
    "acuerdo_textual": "COPY-PASTE LITERAL de la frase exacta donde quedan en algo (ej: '[ASESOR]: Te llamo el martes a las 8, ¿te va bien? [LEAD]: Perfecto.'). 'No acordado' si no hubo acuerdo.",
    "fecha_hora": "Referencia temporal acordada tal como se dijo (ej: 'martes a las 8:00', 'mañana', 'esta tarde', 'el lunes'). 'No especificada' SOLO si no se mencionó ninguna fecha ni plazo.",
    "accion_acordada": "Qué debe ocurrir: enviar documentación, llamada de seguimiento, entrevista de admisión, etc. 'Ninguna' si no se acordó nada.",
    "quien_da_siguiente_paso": "ASESOR llama / LEAD envía docs / AMBOS / NINGUNO"
  }}
}}

REGLAS DEL FEEDBACK PERSONALIZADO:
1. USA el nombre del lead si aparece en la transcripción
2. CITA algo específico que el asesor dijo en el cierre
3. DA un ejemplo de frase de cierre alternativa que podría usar
4. SÉ constructivo, no crítico — máximo 3-4 líneas
5. SIEMPRE en TERCERA PERSONA ("el asesor logró...", "podría mejorar..."). NUNCA en segunda persona ("hiciste...", "podrías...")

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
DEBES integrarlos en tu "recomendacion_accionable" de forma ORGÁNICA:
- Elige la técnica MÁS relevante para lo que le faltó al asesor
- Explica POR QUÉ le ayudaría (conecta con la situación real de la llamada)
- Da 2 frases concretas que podría haber usado en ESTA conversación
- NO copies texto literal del libro, adapta con tus palabras
- Menciona de qué libro/autor viene
⚠️ VERIFICA ANTES DE RECOMENDAR: Comprueba si el asesor ya demostró en la conversación
el comportamiento que vas a recomendar. Si ya lo hizo, NO lo recomiendes — elige otro
aspecto donde haya margen real de mejora. Recomendar algo que el asesor ya hizo invalida
el coaching.

REGLAS CRÍTICAS:
- NO evalúes si el lead dijo "SÍ" a comprar — evalúa TÉCNICA del asesor
- Un lead que dice "Lo pensaré" después de un buen cierre = BUENO si usó técnica
- EVIDENCIAS LITERALES OBLIGATORIAS: copia exacta, NUNCA parafrasees

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

  1. ¿Revalidó lo hablado y se aseguró de que el lead no tiene dudas antes de cerrar?  → SÍ / NO
  2. ¿Propuso un próximo paso con FECHA Y HORA concretas? (solo fecha → NO)            → SÍ / NO
  3. ¿El lead aceptó con compromiso real y explícito (no pasivo ni evasivo)?            → SÍ / NO
  4. ¿Vinculó el cierre a urgencia real (comité, ayudas, plazos)?                      → SÍ / NO
  5. ¿Usó alguna técnica de cierre (doble alternativa, asuntivo, resumen)?              → SÍ / NO
  6. ¿Intentó cerrar la venta antes de aceptar el seguimiento?                         → SÍ / NO
     ¿Preguntó si el lead quería avanzar ahora? (Si fue directo al seguimiento → NO)

CUENTA los NOs. Ese número es tu "contador_fallos_criticos" en el JSON.
🚨 REGLA ABSOLUTA: Si hay 3 o más NOs → la calificación es MALO. Sin excepciones.

🚦 TOPE AUTOMÁTICO — aplica ANTES de decidir la calificación final:
   ¿El punto 2 (fecha Y hora) es NO?  → calificación máxima: MEJORABLE. No puede ser BUENO.
   ¿El punto 3 (compromiso del lead) es NO? → calificación máxima: MEJORABLE. No puede ser BUENO.
   ¿El punto 6 (intento de cierre real) es NO? → calificación máxima: MEJORABLE. No puede ser BUENO.
   ¿Los puntos 2 Y 3 son ambos NO, Y además no hay ningún próximo paso definido? → MALO.
   Estos topes son absolutos: aunque el resto esté bien, sin hora+compromiso+intento de cierre no hay BUENO.

🔴 COHERENCIA ENTRE FALLOS Y CALIFICACIÓN:
   Analiza el peso real de cada fallo. Los 5 criterios son todos relevantes para que el
   lead avance con un compromiso real. No validar dudas, no fijar próximo paso, que el lead
   no se comprometa, no generar urgencia y no usar técnica de cierre son fallos que acumulados
   dejan la conversación sin avance. Si la mayoría fallaron, la calificación debe ser MALO.
   No por un umbral mecánico, sino porque múltiples fallos en el cierre significan que el
   proceso quedó sin avance real. No puedes detectar múltiples fallos graves en el cierre
   y concluir MEJORABLE: sería incoherente con tu propio análisis.

⚠️ CALIBRACIÓN HONESTA — LEE ESTO ANTES DE DECIDIR:
Los modelos de lenguaje tienden a suavizar calificaciones buscando compensaciones positivas.
Si el asesor lideró el cierre, fijó fecha y hora, obtuvo compromiso real e intentó cerrar la
venta antes del seguimiento → di BUENO con confianza.
Si faltó cualquiera de los cuatro requisitos (fecha+hora, compromiso, estructura, intento de cierre),
la calificación debe reflejarlo. Un cierre correcto pero incompleto = MEJORABLE, no BUENO.
No compenses la ausencia de un requisito con que el resto estuvo bien.

🚨 RECONOCER MALO — INSTRUCCIÓN ESPECÍFICA:
MALO no significa "el asesor fue grosero" o "el cierre fue caótico". También es MALO
cuando el asesor no lideró el proceso y lo dejó sin avance real. Di MALO cuando los
datos lo indiquen:
  - Si el razonamiento describe que no hubo compromiso del lead, ni fecha, ni próximos
    pasos definidos, y no puedes citar ningún elemento concreto que avanzó → MALO,
    no MEJORABLE.
  - Si el único argumento para no dar MALO es "el lead fue amable al despedirse" o
    "el asesor intentó cerrar" sin que el lead respondiera nada concreto → eso refleja
    la cortesía del lead, no el avance del proceso → MALO.
PATRONES QUE SON MALO DIRECTAMENTE (sin necesidad de contar NOs del checklist):
  ▸ El asesor termina con "piénsalo y me dices" o equivalente + el lead no acepta ningún
    próximo paso concreto + no hay fecha ni hora acordada → MALO, aunque la llamada
    haya ido bien hasta ese momento.
  ▸ El lead dicta el siguiente paso ("ya te escribo yo", "te mando un mensaje") Y el
    asesor acepta sin proponer ningún compromiso alternativo ni fecha → el asesor
    perdió el control del proceso → MALO.
  ▸ El asesor usó urgencia en algún momento de la conversación (comité, descuento,
    plazas limitadas) Y en el cierre lo ignoró completamente, dejando todo abierto →
    incoherencia estratégica + cierre pasivo → MALO.

⚠️ REGLAS PARA CALIFICAR (después de contar los fallos y aplicar los topes):
- MALO: cierre completamente pasivo, O sin próximos pasos ni seguimiento de ningún tipo, O el lead respondió negativamente y el asesor no reaccionó, O sin compromiso del lead NI fecha/hora NI próximos pasos definidos.
- MEJORABLE: hay un cierre pero le falta al menos uno de los cuatro requisitos de BUENO: hora concreta, compromiso explícito del lead, estructura de cierre, o intento de cierre antes del seguimiento.
- BUENO: el asesor lideró el cierre, fijó fecha Y hora concretas, el lead confirmó su compromiso, y el proceso avanzó con un siguiente paso claro. Deben cumplirse los cuatro requisitos.
- Si dudas entre BUENO y MEJORABLE: ¿hay hora concreta Y compromiso del lead? Si falta alguno → MEJORABLE.
- Si no hay próximos pasos Y tampoco seguimiento → MALO sin excepción.
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.
"""
        
        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
TRANSCRIPCIÓN COMPLETA DE LA ENTREVISTA:
{transcripcion_completa}

⚠️ INSTRUCCIÓN DE LECTURA: Lee la transcripción completa. El cierre y los próximos
pasos ocurren típicamente al FINAL — enfoca tu análisis en esa sección.
Sin embargo, busca también señales de compromiso, pago o reserva que puedan
aparecer en cualquier punto (comprobante de pago, confirmación de inscripción,
mención de transferencia, etc.). Si la venta se cerró en la llamada, debe
reflejarse en la calificación aunque no haya un "siguiente paso" pendiente.

Evalúa el cierre y próximos pasos en JSON.
"""

        # max_tokens=16000: gpt-5-mini es reasoning model — usa tokens internos de "thinking".
        # v5.2: Se eliminó el truncamiento de la transcripción (antes [:8000]).
        # La transcripción completa se envía al LLM para evitar zona ciega en llamadas largas.
        # gpt-5-mini tiene ventana de ~200K tokens — no hay límite de contexto relevante.
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_cierre", max_tokens=16000)
        return self._extract_json_safe(resp)
    
    def _detectar_fin_abrupto(self, final: str) -> bool:
        """Detecta si la grabación cortó antes del cierre (problema técnico)"""
        final_lower = final.lower()

        indicadores = [
            "continuará",
            "seguimos hablando",
            "ahora tengo que",
            "me está entrando otra llamada"
        ]

        for indicador in indicadores:
            if indicador in final_lower:
                return True

        # Si el final tiene menos de 200 chars y no hay despedida
        if len(final) < 200:
            despedidas = ["gracias", "hasta", "adiós", "perfecto", "genial"]
            tiene_despedida = any(d in final_lower for d in despedidas)
            if not tiene_despedida:
                return True

        return False

    def _detectar_desconexion_lead(self, final: str) -> bool:
        """
        Detecta si el lead se desconectó durante la llamada (no es un corte de grabación,
        es el lead que colgó o perdió la señal).

        Señales típicas: la asesora llama "¿Hola?", "¿Me escuchas?" al vacío,
        o el lead deja de responder tras un momento crítico (precio, objeción).
        """
        final_lower = final.lower()

        # Patrones donde el asesor habla pero nadie responde
        patrones_asesor_solo = [
            "¿hola?", "hola?",
            "¿me escuchas?", "me escuchas?",
            "¿sigues ahí?", "sigues ahí?",
            "¿estás ahí?", "estás ahí?",
            "parece que se ha cortado",
            "creo que se cortó",
            "se ha ido",
            "se cortó la llamada",
            "no me escucha",
            "se ha caído",
        ]

        for patron in patrones_asesor_solo:
            if patron in final_lower:
                return True

        # Patrón: hay intervenciones del asesor pero el lead deja de aparecer
        # en el último tramo (últimas ~1500 chars)
        ultimo_tramo = final[-1500:] if len(final) > 1500 else final
        lineas_asesor = [l for l in ultimo_tramo.split("\n") if "[ASESOR]" in l.upper()]
        lineas_lead = [l for l in ultimo_tramo.split("\n") if "[LEAD]" in l.upper() or "[CLIENTE]" in l.upper()]

        # Si hay 3+ intervenciones del asesor y 0 del lead en el último tramo → desconexión probable
        if len(lineas_asesor) >= 3 and len(lineas_lead) == 0:
            return True

        return False

    def _crear_resultado_off_record(self) -> EvaluationResult:
        """Resultado para casos donde la grabación cortó antes del cierre"""
        return EvaluationResult(
            bloque=self.nombre_bloque,
            calificacion=None,
            observabilidad="NO_OBSERVABLE_OFF_RECORD",
            confianza=1.0,
            evidencia_principal="Grabación finalizó antes del cierre (corte detectado)",
            evidencias_extra=[],
            razonamiento=(
                "La conversación parece haber sido interrumpida o la grabación finalizó "
                "antes del cierre formal. No se puede evaluar este bloque."
            ),
            recomendacion_accionable="Verificar que la grabación capture la conversación completa hasta la despedida"
        )

    def _crear_resultado_desconexion(self) -> EvaluationResult:
        """
        Resultado para casos donde el lead se desconectó durante la llamada.
        No se penaliza al asesor: la desconexión no es un fallo de cierre.
        """
        return EvaluationResult(
            bloque=self.nombre_bloque,
            calificacion=None,
            observabilidad="NO_OBSERVABLE_DESCONEXION",
            confianza=1.0,
            evidencia_principal="El lead se desconectó durante la llamada (detectado por patrones de transcripción)",
            evidencias_extra=[],
            razonamiento=(
                "La transcripción indica que el lead se desconectó o perdió la señal durante "
                "la llamada — el asesor intentó retomar el contacto pero no hubo respuesta. "
                "Esta situación no es evaluable como cierre: la conversación terminó por causas "
                "ajenas al asesor. No se asigna calificación."
            ),
            recomendacion_accionable=(
                "Si el lead se desconectó tras recibir el precio u otro momento de tensión, "
                "es recomendable hacer un seguimiento por escrito (WhatsApp o email) para "
                "retomar la conversación desde ese punto."
            )
        )