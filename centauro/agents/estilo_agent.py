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
    
    # ── Valores que representan un fallo en cada aspecto de aspectos_evaluados ──
    _FALLOS_ASPECTOS = {
        "tono":            {"mecanico", "inapropiado"},
        "vocabulario":     {"inadecuado"},
        "empatia":         {"ausente"},
        "ritmo":           {"monopoliza"},
        "profesionalismo": {"bajo"},
    }

    def _aplicar_topes_estilo(
        self,
        calificacion: str,
        resultado_raw: dict,
        razonamiento: str,
    ) -> tuple:
        """
        Validación Python adicional al tope genérico de base_agent.

        Regla A — Aspectos fallidos: si los aspectos_evaluados muestran ≥3 áreas
        con valor de fallo, la calificación no puede superar MALO.

        Regla B — Sin fortaleza: si la calificación es MEJORABLE pero el LLM no
        pudo identificar ninguna fortaleza comunicativa real, se baja a MALO.

        Regla C — Lead no participa + 2 aspectos fallidos: combinación que indica
        que la conversación fue monólogo sin conexión, fuerza MALO.

        Estas reglas usan los propios campos semánticos del JSON del LLM (no el
        contador), porque el LLM tiende a manipular el contador a la baja para
        evitar llegar a 3 y así justificar MEJORABLE.
        """
        if calificacion == "MALO":
            return calificacion, razonamiento  # ya es el mínimo, nada que bajar

        aspectos = resultado_raw.get("aspectos_evaluados", {})

        # ── Regla A: contar áreas con valor de fallo ──
        fallos_aspectos = sum(
            1 for asp, malos in self._FALLOS_ASPECTOS.items()
            if aspectos.get(asp, "") in malos
        )

        if fallos_aspectos >= 3:
            nota = (
                f"[Ajuste automático] Calificación bajada de {calificacion} a MALO: "
                f"los aspectos evaluados muestran {fallos_aspectos} áreas con fallos "
                f"(tono / vocabulario / empatía / ritmo / profesionalismo). "
                f"Con 3 o más áreas fallidas el resultado no puede ser {calificacion}."
            )
            print(f"   ⚠️ Tope estilo Regla A: {fallos_aspectos} aspectos fallidos → MALO")
            return "MALO", f"{razonamiento}\n\n{nota}"

        # ── Regla B: sin fortaleza real → MEJORABLE no es posible ──
        if calificacion == "MEJORABLE":
            fortaleza = str(resultado_raw.get("fortaleza_principal", "") or "").strip().lower()
            sin_fortaleza = fortaleza in ("", "ninguna", "no identificada", "n/a", "-", "no hay", "ninguno")
            if sin_fortaleza:
                nota = (
                    "[Ajuste automático] Calificación bajada de MEJORABLE a MALO: "
                    "el agente no pudo identificar ninguna fortaleza comunicativa real. "
                    "Sin al menos una fortaleza observable, la calificación no puede ser MEJORABLE."
                )
                print("   ⚠️ Tope estilo Regla B: sin fortaleza real → MALO")
                return "MALO", f"{razonamiento}\n\n{nota}"

        # ── Regla C: lead no participa + 2 aspectos fallidos ──
        lead_pasivo = not resultado_raw.get("lead_participa_activamente", True)
        if lead_pasivo and fallos_aspectos >= 2:
            nota = (
                f"[Ajuste automático] Calificación bajada de {calificacion} a MALO: "
                f"el lead no participó activamente Y se detectaron {fallos_aspectos} "
                f"áreas comunicativas fallidas. Una conversación monólogo sin conexión "
                f"real no puede calificarse como {calificacion}."
            )
            print(f"   ⚠️ Tope estilo Regla C: lead pasivo + {fallos_aspectos} fallos → MALO")
            return "MALO", f"{razonamiento}\n\n{nota}"

        return calificacion, razonamiento

    def evaluate(self, transcripcion: str, contexto_manual: str, contexto_usuario: str = None, audio_features: dict = None) -> EvaluationResult:
        """Evalúa el estilo comunicativo en toda la conversación"""

        try:
            resultado_raw = self._evaluar_con_llm(transcripcion, contexto_manual, contexto_usuario, audio_features)
            confianza = self._calcular_confianza(resultado_raw)

            # Tope universal: 3+ fallos en checklist = MALO
            contador_fallos = resultado_raw.get("contador_fallos_criticos", 0)
            cal_tmp, raz_tmp = self._aplicar_tope_fallos_criticos(
                resultado_raw.get("calificacion"), contador_fallos, resultado_raw.get("razonamiento", "")
            )
            if cal_tmp != resultado_raw.get("calificacion"):
                resultado_raw["calificacion"] = cal_tmp
                resultado_raw["razonamiento"] = raz_tmp

            # Tope específico de estilo: cross-validación con aspectos_evaluados
            # (el LLM tiende a bajar el contador para evitar MALO, pero los aspectos
            #  los rellena más honestamente — usamos esos para la decisión final)
            cal_tmp, raz_tmp = self._aplicar_topes_estilo(
                resultado_raw.get("calificacion"), resultado_raw, resultado_raw.get("razonamiento", "")
            )
            if cal_tmp != resultado_raw.get("calificacion"):
                resultado_raw["calificacion"] = cal_tmp
                resultado_raw["razonamiento"] = raz_tmp

            # Validar aspectos críticos (para confianza y metadatos)
            aspectos = resultado_raw.get("aspectos_evaluados", {})
            problemas_graves = []

            if aspectos.get("tono") in ("inapropiado", "mecanico"):
                problemas_graves.append(f"Tono: {aspectos.get('tono')}")
                confianza *= 0.85

            if aspectos.get("empatia") == "ausente":
                problemas_graves.append("Empatía ausente")
                confianza *= 0.85

            if aspectos.get("ritmo") == "monopoliza":
                problemas_graves.append("Asesor monopoliza la conversación")
                confianza *= 0.9

            from ..tools.audio_features import calcular_ratio_habla_diarizada
            ratio_habla_meta = calcular_ratio_habla_diarizada(transcripcion)

            return EvaluationResult(
                bloque=self.nombre_bloque,
                calificacion=resultado_raw.get("calificacion"),
                observabilidad=resultado_raw.get("observabilidad", "ALTA"),
                confianza=confianza,
                evidencia_principal=resultado_raw.get("evidencia_principal", ""),
                evidencias_extra=resultado_raw.get("evidencias_extra", []),
                razonamiento=resultado_raw.get("razonamiento", ""),
                recomendacion_accionable=resultado_raw.get("recomendacion_accionable", ""),
                mejoras=self._formato_mejoras(resultado_raw.get("mejoras", [])),
                metadata={
                    "aspectos_evaluados": aspectos,
                    "problemas_graves": problemas_graves,
                    "fortaleza_principal": resultado_raw.get("fortaleza_principal", ""),
                    "audio_features": audio_features,
                    "pct_asesor": ratio_habla_meta.get("pct_asesor"),
                    "pct_lead": ratio_habla_meta.get("pct_lead"),
                }
            )
            
        except Exception as e:
            print(f"   ❌ Error en evaluación de Estilo: {e}")
            return self._create_fallback_result(str(e))
    
    def _evaluar_con_llm(self, transcripcion: str, manual: str, contexto_usuario: str = None, audio_features: dict = None) -> dict:
        """Llama al LLM con prompt especializado"""

        # Enriquecer contexto con ejemplos de buenas prácticas
        manual_enriquecido = self._enriquecer_contexto_con_ejemplos(manual, transcripcion)

        # Bloque de métricas de audio (siempre presente)
        from ..tools.audio_features import (
            formatear_metricas_para_prompt,
            formatear_sin_audio_para_prompt,
            calcular_ratio_habla_diarizada,
        )
        ratio_habla = calcular_ratio_habla_diarizada(transcripcion)
        if audio_features and audio_features.get("disponible"):
            bloque_audio = f"\n{formatear_metricas_para_prompt(audio_features, ratio_habla)}\n"
        else:
            bloque_audio = f"\n{formatear_sin_audio_para_prompt(ratio_habla)}\n"

        prompt_sistema = f"""
Eres un AUDITOR ESPECIALIZADO en evaluación de ESTILO, TONO Y VOCABULARIO en comunicación comercial.

TU ÚNICA TAREA: Evaluar la CALIDAD COMUNICATIVA del [ASESOR] a lo largo de toda la conversación.

TONO DE REDACCIÓN: Escribe SIEMPRE en TERCERA PERSONA al referirte al asesor ("el asesor hizo...", "el asesor podría..."). NUNCA uses segunda persona ("hiciste...", "podrías...", "tu objetivo...").

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚫 LÍMITES DUROS — LEE ESTO ANTES DE ANALIZAR NADA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Estas reglas se aplican SIEMPRE. No hay excepciones.

MALO no requiere que el asesor haya sido grosero o agresivo. También es MALO cuando
el estilo acumula varios fallos comunicativos sin ninguna fortaleza real que lo compense.
Si el razonamiento no puede citar ni un aspecto genuinamente positivo del estilo del
asesor, la calificación no puede ser MEJORABLE — debe ser MALO.

Regla concreta: MEJORABLE requiere al menos UNA fortaleza comunicativa real y observable
(tono cercano, momento de empatía, ritmo adecuado, vocabulario bien adaptado...).
Si no existe ninguna, la calificación es MALO.

⚠️ QUÉ NO CUENTA COMO FORTALEZA REAL:
La tentación habitual es buscar el mínimo positivo para justificar MEJORABLE. Estas
cosas NO son fortalezas reales que salven a un asesor de MALO:
- "Hizo algunas preguntas puntuales" en medio de largos monólogos. Hacer preguntas
  esporádicas cuando el patrón dominante es el monólogo NO es una fortaleza de ritmo.
- "Fue educado" o "no fue grosero". La cortesía basal no es una fortaleza comunicativa.
- "Usó el nombre del lead una vez". Un uso aislado sin patrón de personalización
  no compensa una comunicación mecánica.
- "El vocabulario fue claro". Claridad mínima es el estándar base, no un positivo.
Si el único "positivo" que puedes citar es de estas categorías, la calificación es MALO.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ CHECKLIST PREVIO — RESPONDE ANTES DE ANALIZAR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ten presente estas 5 preguntas mientras lees. Al terminar, respóndelas SÍ/NO y
usa ese conteo como "contador_fallos_criticos" en el JSON:

  1. ¿El tono fue profesional y cercano (no mecánico ni inapropiado)?
  2. ¿El vocabulario estuvo adaptado al lead (sin jerga técnica inadecuada)?
  3. ¿Hubo al menos un momento de empatía real (incluye empatía inversa)?
  4. ¿El lead participó activamente (no lead silencioso ni asesor monopolizando)?
  5. ¿El profesionalismo fue alto (sin muletillas excesivas, seguro)?

CUENTA los NOs. Ese número es tu "contador_fallos_criticos" en el JSON.
🚨 REGLA ABSOLUTA: Si hay 3 o más NOs → la calificación es MALO. Sin excepciones.
Si no puedes identificar ni UNA fortaleza comunicativa REAL (ver lista de lo que
no cuenta arriba) → la calificación también es MALO.
No detectes múltiples fallos graves y concluyas MEJORABLE: sería incoherente.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTO DEL SPEECH Y BUENAS PRÁCTICAS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
⚠️ QUÉ NO ES UN FALLO COMUNICATIVO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Los asesores se presentan como ASESORES EDUCATIVOS, no como vendedores puros.
Su rol implica opinar, recomendar y compartir su visión. Por eso:

NO son fallos comunicativos (no penalices esto):
- Expresar una opinión personal: "Yo creo que...", "En mi experiencia...",
  "Te recomiendo este programa porque..." → es propio del rol de asesor educativo.
- Un estilo cercano, cálido o informal si conecta bien con el lead.
- Usar un tono espontáneo y humano en vez de seguir un guión al pie de la letra.
- Hablar de tú a tú con un lead de perfil similar al asesor.
- Cambiar de idioma o usar palabras en otro idioma si hay coherencia con lo que se
  habla (ej: asesor y lead alternan español/catalán/inglés de forma natural y la
  conversación tiene sentido). NO penalices el cambio de idioma coherente.
  EXCEPCIÓN: si aparecen palabras o frases en otro idioma que no encajan con el
  contexto y parecen errores de transcripción (alucinaciones del motor de STT),
  sí menciónalos explícitamente para que el equipo pueda detectarlos.

SÍ son señales negativas que debes detectar y mencionar:
- TONO ROBÓTICO O MONÓTONO: el asesor suena a guión, sin variación ni calor humano,
  encadena bloques de información sin pausas ni personalización → penaliza.
- EXCESO DE CONFIANZA: tratamiento excesivamente familiar que puede incomodar al lead
  (apodos inadecuados, chistes fuera de lugar, familiaridad brusca desde el inicio
  que el lead no ha invitado) → penaliza.
- ASESOR QUE HABLA MUY POCO: si el asesor apenas interviene durante toda la entrevista
  y el lead tiene que llenar el silencio solo → señal negativa, menciónalo.
- MULETILLAS FRECUENTES: detecta si el asesor repite constantemente palabras o frases
  colchón ("¿sabes?", "o sea", "ehhh", "bueno bueno", "vale vale", "básicamente",
  "la verdad es que"). Si aparecen de forma reiterada afectan la credibilidad → penaliza.
  Si son ocasionales y no distraen → no penalices.

⚠️ VOCABULARIO CRÍTICO — TÉRMINOS PROHIBIDOS Y NORMAS DE REDACCIÓN:
- Nunca uses el término "verborrea". Si el asesor se extiende o repite ideas, descríbelo
  como "extensión innecesaria en algunos pasajes" o "cierta redundancia en el discurso".
- Nunca inventes etiquetas técnicas o jerga de análisis del discurso para describir errores
  menores ("nombre mal situado", "auto-corrección", "disfluencia", "anclaje cognitivo", etc.).
  Si el asesor se corrigió al decir un nombre, escríbelo tal cual: "en un momento confundió
  el nombre del lead y se corrigió". Describe siempre en lenguaje llano y directo, sin jargon.
- Nunca uses términos que el usuario final (el asesor o su jefe) no entendería de inmediato.

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
{bloque_audio}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ ADVERTENCIA: MÉTRICAS DE AUDIO PUEDEN ESTAR DISTORSIONADAS POR DESCONEXIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Antes de interpretar métricas de audio, comprueba si el lead se desconectó en algún
punto de la llamada. Señales en español: el asesor dice "¿Hola?", "¿Me escuchas?",
"¿Sigues ahí?". Señales en inglés: "Hello?", "Are you there?", "Can you hear me?",
"Hello, are you still there?". También: hay un tramo donde el asesor habla varias
veces sin que el lead responda.

Si hay indicios de desconexión (parcial o definitiva):
⚠️ Las métricas de silencio y energía pueden estar infladas artificialmente:
   - ratio_silencio y n_silencios_largos_4seg incluyen el tiempo que el asesor
     esperó al vacío — no son silencios comunicativos del asesor
   - ratio_energia_final_vs_inicio puede mostrar caída porque el asesor estaba
     esperando sin hablar, no porque perdiera convicción
   - NO uses estas métricas distorsionadas para penalizar el estilo del asesor
   - En el razonamiento, indica que las métricas del final pueden estar afectadas
     por la desconexión y no son atribuibles al estilo comunicativo del asesor

Si la desconexión fue parcial (el lead volvió): evalúa solo el tramo donde sí
había conversación real. Ignora las métricas del intervalo sin lead.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ COHERENCIA OBLIGATORIA CON LOS DATOS DE AUDIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Los datos acústicos que aparecen arriba son OBJETIVOS y tienen PRIORIDAD sobre
cualquier impresión subjetiva que puedas extraer del texto de la transcripción.

⚠️ EXCEPCIÓN: Si detectaste que el lead se desconectó en algún punto de la llamada,
las métricas de silencio (ratio_silencio, n_silencios_largos_4seg) y de energía
(ratio_energia_final_vs_inicio) pueden estar INFLADAS por ese tramo sin lead y NO
reflejan el comportamiento comunicativo real del asesor. En ese caso:
- Puedes mencionarlas como contexto, pero NO las uses como argumento de penalización
- Las reglas de coherencia de abajo se aplican solo al tramo con conversación real

REGLA (cuando NO hay desconexión): Si los datos dicen algo, tu razonamiento debe
ser COHERENTE con ellos, no contradecirlos.
Ejemplos concretos de coherencia obligatoria:
- Si "ratio_energia_final_vs_inicio" es >= 0.80 → NO digas que hay "caída de energía al final"
  ni "pérdida de convicción hacia el cierre". El dato objetivo dice volumen constante o estable.
- Si "ratio_silencio" es <= 15% → NO digas que "el asesor dejó demasiados silencios".
- Si "tempo_bpm" es < 130 → NO digas que "el asesor habla demasiado rápido".
- Si "n_silencios_largos_4seg" es 0 → NO menciones "silencios largos incómodos".

Si no hay datos de audio disponibles, puedes hacer inferencias del texto, pero indica
que son impresiones del texto y no datos objetivos. Nunca presentes una inferencia
textual con la misma certeza que un dato acústico.

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
   - Lenguaje profesional vs coloquial en exceso o exceso de confianza con el lead
   - MULETILLAS: detecta si hay palabras o frases repetidas con alta frecuencia
     ("ehhh", "bueno", "vale vale", "¿sabes?", "o sea", "básicamente", "la verdad").
     Si son constantes → señal negativa. Si son esporádicas → no penalices.
   - Seguro vs dubitativo
   - ⚠️ Expresar opiniones personales o recomendaciones NO es falta de profesionalismo.
     Un asesor educativo tiene criterio y lo comparte: es parte de su valor.
   ⚠️ JERGA TÉCNICA: si el asesor usa terminología especializada que el lead no domina
   (tecnicismos del sector, siglas, conceptos académicos sin explicar) y esto genera
   distancia o falta de comprensión → señal negativa específica. Menciónalo explícitamente
   en el razonamiento y en las evidencias. Es diferente de "informal": la jerga técnica
   sin adaptar aleja al lead en vez de acercarlo.

📌 CALIBRA con los ejemplos del CONTEXTO:
Los ejemplos de buenas prácticas son el estándar de referencia — la definición concreta de BUENO.
Si lo que hizo este asesor se parece en espíritu a esos ejemplos → está en zona BUENO.
Un momento aislado NO hace BUENO el bloque completo. Evalúa el CONJUNTO.

CRITERIOS DE CALIFICACIÓN (elige UNA de las 3 etiquetas):

⚠️ DISTINCIÓN CRÍTICA — INFORMAL vs. DESORGANIZADO:
Son dos cosas completamente diferentes. NO las confundas:
- INFORMAL: tono conversacional, cercano, sin rigidez. Para perfiles de marketing,
  ventas o creativos, esto es POSITIVO. Un asesor informal que conecta bien = BUENO.
- DESORGANIZADO: no tiene hilo conductor, salta de tema sin estructura, el lead no
  sabe dónde está la conversación. Esto sí es negativo e impacta la calificación.
Un asesor puede ser informal Y estructurado a la vez. NO marques MEJORABLE o MALO
solo porque el tono es informal si la conversación tiene coherencia y orden.

🔴 MALO — el estilo no aporta nada positivo a la conversación. Dos vías posibles:
   VÍA A — Activamente dañino:
   - Tono grosero, condescendiente, o tan desorganizado que el lead no entiende la conversación
   - Tono agresivo, impaciente o que hace sentir al lead presionado
   - Genera incomodidad, distancia o rechazo visible en el lead
   VÍA B — Acumulación de fallos sin fortalezas que los compensen:
   - Múltiples problemas comunicativos (monólogos, muletillas, sin empatía, ritmo malo...)
   - Y no hay ni UNA fortaleza comunicativa real observable en toda la conversación
   - La conversación es mecánica, impersonal y no genera ninguna conexión
   ⚠️ Un asesor puede ser MALO sin ser grosero: basta con que el estilo falle en todos
   los frentes y no tenga nada que rescatar. Si el razonamiento no cita ningún aspecto
   positivo real → la calificación debe ser MALO, no MEJORABLE.

🟡 MEJORABLE — hay al menos UNA fortaleza comunicativa real, pero el conjunto es insuficiente:
   - Tono educado pero robótico en la mayoría de la conversación
   - Pocos o ningún momento de empatía o cercanía genuina
   - El lead responde pero no hay señales claras de que se sienta cómodo o escuchado
   - Profesional pero impersonal: correcto en superficie, pero no conecta
   - TONO MECÁNICO: patrón específico a detectar — el asesor encadena bloques de
     información sin pausas ni preguntas, el lead apenas tiene espacio para hablar
     y la conversación suena más a monólogo que a diálogo
   ⚠️ REQUISITO: para ser MEJORABLE debe existir al menos UNA fortaleza real (tono
   amable, momento de empatía, vocabulario bien adaptado...). Sin ninguna → es MALO.

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
  "razonamiento": "En 4-6 líneas de texto fluido, sin listas ni SÍ/NO: explica cómo fue el estilo comunicativo del asesor, qué tono usó, si conectó con el lead emocionalmente, qué funcionó y qué no. Por qué merece esa calificación. Conecta con lo que ocurrió realmente en la conversación. OBLIGATORIO si la calificación es MALO o MEJORABLE: incluye en el texto al menos una cita literal entre comillas de la conversación que muestre el fallo principal.",
  "recomendacion_accionable": "IMPORTANTE: Combina en un SOLO texto fluido: (1) Qué mejorar en estilo/comunicación, (2) UNA técnica de los libros de ventas del CONTEXTO que aplique al estilo comunicativo, explicando POR QUÉ funciona y dando 2 ejemplos de frases. Máx 6-8 líneas. NO copies texto literal de los libros.",
  "mejoras": ["Frase de acción en infinitivo máx 8 palabras (ej: Concretar fecha y hora de seguimiento). Lista vacía [] si BUENO sin fallos relevantes."],
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

⚠️ CALIBRACIÓN HONESTA — LEE ESTO ANTES DE DECIDIR:
Los modelos de lenguaje tienden a suavizar calificaciones buscando compensaciones positivas.
Si el estilo fue genuinamente cálido y generó conexión real y sostenida → di BUENO con confianza.
Si el conjunto fue mayormente mecánico o distante, no compenses eso con un momento aislado
de empatía o informalidad. Un momento positivo en una conversación robótica = MEJORABLE, no BUENO.
MEJORABLE no es un fracaso: es la evaluación honesta de un estilo correcto pero sin conexión real.

🚨 RECONOCER MALO — INSTRUCCIÓN ESPECÍFICA:
MALO no significa "el asesor fue grosero o agresivo". También es MALO cuando el estilo
falló en todos los frentes sin ninguna fortaleza real que lo rescate. Di MALO cuando los
datos lo indiquen:
  - Si el razonamiento describe una conversación mecánica, sin empatía, con ritmo
    monopolizado y sin ningún momento de conexión real, y no puedes citar ni UNA
    fortaleza comunicativa genuina → MALO, no MEJORABLE.
  - Si el único argumento para no dar MALO es "no fue descortés" o "el lead no se quejó"
    → la cortesía mínima no es una fortaleza comunicativa → MALO si el estilo no aportó nada.
PATRONES QUE SON MALO DIRECTAMENTE (sin necesidad de contar NOs del checklist):
  ▸ El asesor monopolizó más del 80% de la conversación con bloques informativos
    encadenados sin invitar al lead a participar + el lead respondió solo con
    monosílabos o silencios en toda la llamada → MALO.
  ▸ No hay ni UN momento de empatía real en toda la conversación (ni frases empáticas,
    ni uso del nombre del lead, ni adaptación de tono, ni empatía inversa) + el tono
    fue mecánico de principio a fin → MALO.
  ▸ Jerga técnica constante que el lead claramente no entiende (preguntas de aclaración,
    silencios ante términos, respuestas que no encajan) + sin adaptación de vocabulario
    en ningún momento → MALO.

⚠️ REGLAS FINALES PARA CALIFICAR:
- MALO: múltiples fallos comunicativos sin ninguna fortaleza real que los compense, O estilo activamente dañino (grosero, agresivo, condescendiente). Si el razonamiento no puede citar ni un aspecto positivo genuino → MALO.
- MEJORABLE: hay al menos UNA fortaleza comunicativa real, pero el conjunto falla. Educado pero mecánico, sin conexión real ni calidez sostenida.
- BUENO: el estilo genera conexión real y sostenida a lo largo de la conversación. No hace falta perfección, pero debe haber un patrón consistente de calidez y participación del lead — no un momento aislado.
- Si dudas entre BUENO y MEJORABLE: ¿hay un PATRÓN consistente de conexión real y el lead participó activamente? Un momento aislado de empatía en un estilo mayormente mecánico → MEJORABLE. Patrón sostenido → BUENO.
- Si dudas entre MEJORABLE y MALO: ¿puedes citar al menos UNA fortaleza comunicativa real? Si no → MALO.
- La empatía inversa (experiencia propia) cuenta como señal positiva real, pero no convierte por sí sola un estilo mecánico en BUENO.
- Si el asesor expresó opiniones personales o recomendaciones propias → NO es motivo de MEJORABLE ni MALO.
- Si el asesor fue cercano o informal pero el lead respondió bien → señal positiva hacia BUENO.
- Evidencias LITERALES (COPY-PASTE exacto).
- En "recomendacion_accionable" NO repitas lo que ya hizo bien.

REGLAS PARA RECOMENDACIÓN CON COACHING:
En el contexto tienes fragmentos de libros de ventas marcados como [COACHING: ...].
DEBES integrarlos en tu "recomendacion_accionable" de forma ORGÁNICA, pero con
una regla crítica: la técnica elegida DEBE ser coherente con el patrón detectado.

⚠️ PROHIBICIÓN ABSOLUTA — SPIN SELLING EN ESTILO:
SPIN Selling es una metodología de INVESTIGACIÓN de necesidades mediante preguntas.
NO es una técnica de comunicación ni de estilo. Para problemas de comunicación
(ritmo, muletillas, tono, empatía, claridad) NUNCA recomiendes SPIN Selling.
Si el fragmento de coaching disponible es de SPIN y el problema detectado es de
comunicación, IGNORA ese fragmento y elige otro libro del contexto.

⚠️ PROHIBICIÓN DE GUIONES PRESCRIPTIVOS:
Nunca escribas un ejemplo de frase que el asesor "debería haber dicho" con estructura
detallada y scripted (ej: "Ana, voy al grano en 3 puntos: titulación, metodología y
coste; luego me confirmas si te lo envío por email - ¿te parece?"). Ese tipo de guión:
(a) no refleja el estilo natural del asesor,
(b) no está respaldado por los manuales OBS,
(c) puede sonar mecánico o agresivo al lead.
Las frases de ejemplo deben ser ORIENTATIVAS y breves, no guiones completos.
Deben inspirarse en los manuales y buenas prácticas de OBS disponibles en el contexto,
no en técnicas externas que el asesor no conoce ni ha usado.

CONEXIÓN OBLIGATORIA PATRÓN → TÉCNICA:
- Si detectaste MULETILLAS o problemas de RITMO → elige una técnica sobre
  comunicación, pausa, ritmo o presencia vocal.
- Si detectaste falta de EMPATÍA → elige una técnica sobre conexión emocional,
  escucha activa o rapport.
- Si detectaste TONO MECÁNICO → elige una técnica sobre naturalidad, espontaneidad
  o conversación consultiva.
- Si el asesor lo hizo todo bien (BUENO) → elige la técnica más avanzada que
  podría elevar aún más su nivel, conectada con su fortaleza principal.

Si el contexto tiene variedad de libros disponibles, evita recomendar siempre
el mismo. Elige el que tenga la técnica MÁS relevante para el patrón concreto
de esta llamada, aunque sea de un libro menos prominente en el contexto.

- Explica POR QUÉ esa técnica concreta le ayudaría (conecta con la situación real)
- Da 1-2 orientaciones breves, NO guiones detallados
- Basa las sugerencias en los manuales OBS y buenas prácticas del contexto
- NO copies texto literal del libro, adapta con tus palabras
⚠️ VERIFICA ANTES DE RECOMENDAR: Comprueba si el asesor ya demostró en la conversación
el comportamiento que vas a recomendar. Si ya lo hizo (ej: si dijo "voy a ser ágil porque
estás en el trabajo"), NO lo recomiendes — elige otro aspecto donde haya margen real de
mejora. Recomendar algo que el asesor ya hizo invalida el coaching.

REGLAS CRÍTICAS:
- Evalúa TODA la conversación, no solo un momento
- Evidencias LITERALES de la transcripción
- Diferencia entre "robot profesional" (MEJORABLE) y "humano profesional" (BUENO)
- BUENO requiere que el lead se sienta realmente conectado con el asesor en algún momento
- Identifica patrones: ¿Es consistente o cambia a lo largo de la conversación?
"""
        
        bloque_ctx_usuario = self._construir_bloque_contexto_usuario(contexto_usuario)

        prompt_usuario = f"""{bloque_ctx_usuario}
ANTES DE EVALUAR: Lee la transcripción completa de principio a fin. El estilo comunicativo
se manifiesta a lo largo de toda la conversación. Presta especial atención a: (1) si el
asesor declaró que adaptaría su ritmo o profundidad a las circunstancias del lead (ej:
"voy a ser ágil porque estás en el trabajo"), y (2) momentos de empatía, conexión o
adaptación de tono que pueden estar repartidos por toda la llamada. Evalúa el CONJUNTO.

Evalúa el estilo comunicativo del [ASESOR] en esta conversación completa:

{transcripcion}

Genera la evaluación en JSON.
"""
        
        resp = consultar_gpt(prompt_sistema, prompt_usuario, "eval_estilo")
        return self._extract_json_safe(resp)