"""
Chat Handler v4.1 - Interfaz de consulta interactiva al RAG

Permite a los usuarios hacer preguntas sobre:
- Manuales de venta (cómo hacer algo correctamente)
- Ejemplos de buenas prácticas (mostrarme ejemplos)
- Evaluaciones históricas (cómo lo han hecho otros asesores)
- Perfiles de asesores (mi rendimiento, estadísticas)

v4.1 - Mejoras:
- Detección de bloque/sección en la pregunta para filtrar RAG
- Historial de conversación incluido en el contexto del LLM
- Manejo de "mi rendimiento" sin nombre de asesor en sesión
"""
from typing import List, Dict, Optional
from ..config import centauro_config
from ..rag import buscar_en_coleccion
from ..llm_client import consultar_gpt
from .memoria import memory_manager


# Mapeo de palabras clave a seccion_key (debe coincidir con SECCION_TO_BLOQUE en rag.py)
BLOQUE_KEYWORDS: Dict[str, List[str]] = {
    "investigacion": [
        "investigación", "investigacion", "investigar", "descubrir",
        "necesidades", "preguntas abiertas", "spin", "rapport",
        "diagnóstico", "diagnostico", "sondeo", "apertura",
    ],
    "propuesta_valor": [
        "propuesta de valor", "propuesta valor", "institución", "programa",
        "diferencial", "beneficios", "presentación", "presentacion",
        "argumentario", "ventajas",
    ],
    "admision_economica": [
        "admisión", "admision", "económico", "economico", "precio", "coste",
        "coste", "pago", "financiación", "financiacion", "matrícula",
        "matricula", "inversión", "inversion", "propuesta económica",
    ],
    "cierre": [
        "cierre", "cerrar", "próximos pasos", "proximos pasos",
        "compromiso", "siguiente paso", "acuerdo", "confirmar",
        "formalizar",
    ],
    "objeciones": [
        "objeción", "objeciones", "objecion", "resistencia",
        "rechazo", "duda", "inconveniente", "pero", "aunque",
        "manejo de objeciones", "rebatir",
    ],
    "estilo": [
        "estilo", "comunicación", "comunicacion", "tono", "empatía",
        "empatia", "escucha activa", "lenguaje", "actitud",
        "profesionalismo", "confianza",
    ],
}


class ChatHandler:
    """
    Maneja consultas de texto libre del usuario al sistema de conocimiento.

    Identifica la intención, detecta el bloque temático y busca
    en la colección apropiada con filtros de metadata precisos.
    """

    def __init__(self):
        self.historial_conversacion: List[Dict] = []

    def procesar_consulta(self, pregunta_usuario: str, nombre_asesor: Optional[str] = None) -> str:
        """
        Procesa una pregunta del usuario y devuelve respuesta contextualizada.

        Args:
            pregunta_usuario: Pregunta en lenguaje natural
            nombre_asesor: Nombre del asesor (si se quiere consultar su perfil)

        Returns:
            Respuesta generada por el LLM con contexto del RAG
        """
        # Identificar intención y bloque temático
        intencion = self._clasificar_intencion(pregunta_usuario)
        bloque_detectado = self._detectar_bloque(pregunta_usuario)

        # Buscar contexto relevante
        contexto = self._buscar_contexto_relevante(
            pregunta_usuario, intencion, bloque_detectado, nombre_asesor
        )

        # Generar respuesta (incluye historial)
        respuesta = self._generar_respuesta(
            pregunta_usuario, contexto, intencion, bloque_detectado
        )

        # Guardar en historial
        self.historial_conversacion.append({
            "pregunta": pregunta_usuario,
            "respuesta": respuesta,
            "intencion": intencion,
            "bloque": bloque_detectado,
        })

        return respuesta

    # ------------------------------------------------------------------
    # Clasificación de intención
    # ------------------------------------------------------------------

    def _clasificar_intencion(self, pregunta: str) -> str:
        """
        Clasifica la intención de la pregunta del usuario.

        Returns:
            "manual" | "ejemplo" | "perfil" | "estadisticas" | "general"
        """
        pregunta_lower = pregunta.lower()

        # ── Perfil de asesor concreto (PRIORIDAD ALTA) ──────────────────────
        # Preguntas sobre un asesor específico por nombre o sobre el propio asesor
        if any(kw in pregunta_lower for kw in [
            "mi rendimiento", "mi perfil", "mis evaluaciones",
            "cómo he mejorado", "mi progreso", "cómo estoy",
            "mis resultados",
            # Preguntas sobre otro asesor concreto
            "cuántas entrevistas", "cuantas entrevistas",
            "cuántas llamadas", "cuantas llamadas",
            "cuántas evaluaciones", "cuantas evaluaciones",
            "entrevistas de", "entrevistas tiene", "entrevistas tienes",
            "evaluaciones de", "evaluaciones tiene",
            "cómo le fue", "como le fue",
            "cómo lo hizo", "como lo hizo",
            "cómo ha ido", "como ha ido",
            "cómo va ", "como va ",
            "rendimiento de", "perfil de",
            "nota de", "resultado de",
            "qué nota", "que nota",
            "cómo está ", "como esta ",
        ]):
            return "perfil"

        # Si la pregunta menciona un nombre propio Y un bloque de evaluación
        # → casi seguro es una consulta sobre el rendimiento de un asesor concreto
        import re as _re
        tiene_nombre_propio = bool(_re.search(r'\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\b', pregunta))
        if tiene_nombre_propio:
            bloques_en_pregunta = [
                "investigación", "investigacion", "cierre", "propuesta",
                "objeciones", "estilo", "admisión", "admision",
                "bloque", "calificación", "calificacion",
            ]
            if any(b in pregunta_lower for b in bloques_en_pregunta):
                return "perfil"

        # ── Estadísticas globales ────────────────────────────────────────────
        if any(kw in pregunta_lower for kw in [
            "estadísticas", "cuántos asesores", "promedio general",
            "tendencias", "el equipo", "estadisticas",
        ]):
            return "estadisticas"

        # ── Ejemplos concretos ───────────────────────────────────────────────
        if any(kw in pregunta_lower for kw in [
            "ejemplo", "ejemplos", "muéstrame", "muestrame", "muestra",
            "cómo lo haría", "cómo se haría", "cómo se hace",
            "demostración", "demostracion", "referencia", "caso",
        ]):
            return "ejemplo"

        # ── Manual (cómo hacer algo) ─────────────────────────────────────────
        if any(kw in pregunta_lower for kw in [
            "cómo", "como", "qué debo", "que debo", "procedimiento",
            "protocolo", "reglas", "pasos", "técnica", "tecnica",
            "estrategia", "consejo", "consejos",
        ]):
            return "manual"

        return "general"

    # ------------------------------------------------------------------
    # Detección de bloque temático
    # ------------------------------------------------------------------

    def _detectar_bloque(self, pregunta: str) -> Optional[str]:
        """
        Detecta qué bloque/sección menciona la pregunta.

        Returns:
            seccion_key ("cierre", "investigacion", ...) o None si no se detecta
        """
        pregunta_lower = pregunta.lower()
        for seccion_key, keywords in BLOQUE_KEYWORDS.items():
            if any(kw in pregunta_lower for kw in keywords):
                return seccion_key
        return None

    # ------------------------------------------------------------------
    # Búsqueda de contexto
    # ------------------------------------------------------------------

    def _buscar_contexto_relevante(
        self,
        pregunta: str,
        intencion: str,
        bloque_detectado: Optional[str],
        nombre_asesor: Optional[str],
    ) -> str:
        """Busca contexto en las colecciones apropiadas según intención y bloque."""

        if intencion == "perfil":
            return self._obtener_perfil_asesor(nombre_asesor, pregunta, bloque_detectado)

        elif intencion == "estadisticas":
            return self._obtener_estadisticas_globales()

        elif intencion == "ejemplo":
            return self._buscar_ejemplos(pregunta, bloque_detectado)

        elif intencion == "manual":
            return self._buscar_en_manual(pregunta, bloque_detectado)

        else:
            return self._busqueda_multicoleccion(pregunta)

    def _buscar_ejemplos(self, pregunta: str, bloque: Optional[str]) -> str:
        """Busca ejemplos en buenas prácticas, filtrando por sección si se detectó."""
        filtro = {"seccion_key": bloque} if bloque else None

        resultados = buscar_en_coleccion(
            query=pregunta,
            collection_name=centauro_config.COLLECTION_BUENAS_PRACTICAS,
            k=centauro_config.CHAT_RAG_TOP_K,
            filtro_metadata=filtro,
        )

        # Si con filtro no hay resultados, buscar sin filtro como fallback
        if not resultados and bloque:
            resultados = buscar_en_coleccion(
                query=pregunta,
                collection_name=centauro_config.COLLECTION_BUENAS_PRACTICAS,
                k=centauro_config.CHAT_RAG_TOP_K,
            )

        if resultados:
            fragmentos = [r['text'] for r in resultados]
            return "\n\n---\n\n".join(fragmentos)

        return "No se encontraron ejemplos relevantes."

    def _buscar_en_manual(self, pregunta: str, bloque: Optional[str]) -> str:
        """Busca en manuales. Si hay bloque detectado, lo incluye en la query."""
        # Los manuales no tienen metadato de sección, pero enriquecer la query
        # con el nombre del bloque mejora la búsqueda semántica
        query_enriquecida = pregunta
        if bloque:
            nombre_bloque_display = {
                "investigacion": "investigación y descubrimiento de necesidades",
                "propuesta_valor": "propuesta de valor institución y programa",
                "admision_economica": "admisión económica y propuesta de precio",
                "cierre": "cierre y próximos pasos",
                "objeciones": "manejo de objeciones",
                "estilo": "estilo y comunicación",
            }.get(bloque, bloque)
            query_enriquecida = f"{pregunta} {nombre_bloque_display}"

        resultados = buscar_en_coleccion(
            query=query_enriquecida,
            collection_name=centauro_config.COLLECTION_MANUALES,
            k=centauro_config.CHAT_RAG_TOP_K,
        )

        if resultados:
            fragmentos = [r['text'] for r in resultados]
            return "\n\n---\n\n".join(fragmentos)

        return "No se encontró información en los manuales."

    def _obtener_perfil_asesor(
        self,
        nombre_asesor: Optional[str],
        pregunta: str,
        bloque_filtro: Optional[str] = None,
    ) -> str:
        """Obtiene y formatea el perfil de un asesor, con detalle por bloque si se pide."""
        if not nombre_asesor:
            nombre_asesor = self._extraer_nombre_de_pregunta(pregunta)

        if not nombre_asesor:
            try:
                archivos = list(memory_manager.perfiles_dir.glob("*.json"))
                if not archivos:
                    return "Aún no hay evaluaciones registradas en el sistema."
                nombres = [f.stem.replace("_", " ").title() for f in archivos[:10]]
                lista = "\n".join(f"- {n}" for n in nombres)
                return (
                    f"No sé de qué asesor quieres ver el rendimiento. "
                    f"Hay {len(archivos)} asesor(es) evaluado(s):\n{lista}\n\n"
                    f"Dime el nombre y te muestro su perfil."
                )
            except Exception:
                return (
                    "No sé de qué asesor quieres ver el rendimiento. "
                    "Por favor indica el nombre del asesor."
                )

        try:
            perfil = memory_manager.cargar_perfil(nombre_asesor)

            if perfil.total_evaluaciones == 0:
                return f"No hay evaluaciones registradas para {nombre_asesor}."

            # ── Si se pregunta por un bloque concreto, mostrar historial de ese bloque ──
            if bloque_filtro:
                return self._detalle_bloque_asesor(perfil, bloque_filtro)

            # ── Perfil completo ──────────────────────────────────────────────
            # Estadísticas por bloque (todas las evaluaciones)
            from collections import Counter
            stats_bloque: dict = {}
            for ev in perfil.evaluaciones:
                for bloque, cal in ev.calificaciones_por_bloque.items():
                    if cal:
                        stats_bloque.setdefault(bloque, []).append(cal)

            lineas_bloques = []
            EMOJI = {"BUENO": "🟢", "MEJORABLE": "🟡", "MALO": "🔴"}
            for bloque, cals in stats_bloque.items():
                conteo = Counter(cals)
                ultima = cals[-1] if cals else "N/A"
                mayoria = conteo.most_common(1)[0][0]
                lineas_bloques.append(
                    f"  {EMOJI.get(ultima, '⚪')} {bloque}: {ultima} "
                    f"(última) | mayoría histórica: {mayoria} "
                    f"({conteo[mayoria]}/{len(cals)} veces)"
                )

            bloques_txt = "\n".join(lineas_bloques) if lineas_bloques else "  Sin datos de bloques"

            texto_perfil = f"""PERFIL DE {perfil.nombre.upper()}
{'='*50}

📊 RESUMEN:
- Total evaluaciones: {perfil.total_evaluaciones}
- Primera evaluación: {perfil.fecha_primera_evaluacion[:10] if perfil.fecha_primera_evaluacion else 'N/A'}
- Última evaluación: {perfil.fecha_ultima_evaluacion[:10] if perfil.fecha_ultima_evaluacion else 'N/A'}

📈 TENDENCIA GLOBAL: {perfil.tendencia_global}

📋 RENDIMIENTO POR BLOQUE (última evaluación | mayoría histórica):
{bloques_txt}

✅ FORTALEZAS CONSISTENTES:
{', '.join(perfil.fortalezas_consistentes) if perfil.fortalezas_consistentes else 'No identificadas aún (mín. 3 evaluaciones)'}

🎯 ÁREAS DE MEJORA CONSISTENTES:
{', '.join(perfil.areas_mejora_consistentes) if perfil.areas_mejora_consistentes else 'Ninguna crítica detectada'}
"""
            return texto_perfil

        except Exception as e:
            return f"Error obteniendo perfil de {nombre_asesor}: {e}"

    def _detalle_bloque_asesor(self, perfil, bloque_key: str) -> str:
        """Devuelve el historial detallado de un asesor en un bloque concreto."""
        from collections import Counter

        # Mapeo de clave de bloque (ej: "investigacion") a nombre real en el perfil
        NOMBRE_BLOQUE = {
            "investigacion": "Investigación",
            "propuesta_valor": "Propuesta de Valor",
            "admision_economica": "Admisión",
            "cierre": "Cierre",
            "objeciones": "Objeciones",
            "estilo": "Estilo",
        }
        nombre_display = NOMBRE_BLOQUE.get(bloque_key, bloque_key)

        # Buscar evaluaciones que contengan ese bloque (coincidencia parcial)
        registros = []
        for ev in perfil.evaluaciones:
            for bloque_nombre, cal in ev.calificaciones_por_bloque.items():
                if nombre_display.lower() in bloque_nombre.lower() and cal:
                    registros.append({
                        "fecha": ev.fecha[:10],
                        "cal": cal,
                        "global": ev.calificacion_global,
                    })
                    break

        if not registros:
            return (
                f"No hay datos de '{nombre_display}' para {perfil.nombre}.\n"
                f"(Total evaluaciones del asesor: {perfil.total_evaluaciones})"
            )

        conteo = Counter(r["cal"] for r in registros)
        EMOJI = {"BUENO": "🟢", "MEJORABLE": "🟡", "MALO": "🔴"}

        historial_lineas = []
        for r in registros[-10:]:  # Últimas 10
            historial_lineas.append(
                f"  {r['fecha']}  {EMOJI.get(r['cal'], '⚪')} {r['cal']}"
                f"  (global: {r['global'] or 'N/A'})"
            )

        return f"""BLOQUE '{nombre_display.upper()}' — {perfil.nombre.upper()}
{'='*50}

📊 Total evaluaciones en este bloque: {len(registros)}
🟢 BUENO: {conteo.get('BUENO', 0)} veces
🟡 MEJORABLE: {conteo.get('MEJORABLE', 0)} veces
🔴 MALO: {conteo.get('MALO', 0)} veces
📌 Última calificación: {registros[-1]['cal']}

📋 Historial (últimas {min(10, len(registros))}):
{chr(10).join(historial_lineas)}
"""

    def _extraer_nombre_de_pregunta(self, pregunta: str) -> Optional[str]:
        """
        Intenta extraer un nombre de asesor mencionado en la pregunta.
        Admite varios patrones y hace fuzzy match contra perfiles existentes.
        """
        import re

        candidatos = []

        # Patrón 1: "de Nombre Apellido" o "de Nombre"
        for m in re.finditer(
            r'\bde\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})',
            pregunta
        ):
            candidatos.append(m.group(1).strip())

        # Patrón 2: "a Nombre Apellido" o "a Nombre" (ej: "a Aleix", "a Juan García")
        for m in re.finditer(
            r'\ba\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})',
            pregunta
        ):
            candidatos.append(m.group(1).strip())

        # Patrón 3: nombre propio al inicio o aislado (ej: "Aleix Ribas, cuántas...")
        for m in re.finditer(
            r'\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\b',
            pregunta
        ):
            candidatos.append(m.group(1).strip())

        if not candidatos:
            return None

        # Resolver candidatos contra perfiles existentes (fuzzy match)
        for candidato in candidatos:
            resuelto = self._resolver_nombre_en_perfiles(candidato)
            if resuelto:
                return resuelto

        # Si ninguno matchea un perfil existente, devolver el primero como candidato
        return candidatos[0] if candidatos else None

    def _resolver_nombre_en_perfiles(self, nombre_fragmento: str) -> Optional[str]:
        """
        Busca el nombre_fragmento en los perfiles guardados.
        Prioriza coincidencia por prefijo de tokens para evitar devolver un perfil
        corto ("Aleix Ribas") cuando existe uno más completo ("Aleix Ribas Canadell").
        """
        try:
            archivos = list(memory_manager.perfiles_dir.glob("*.json"))
            tokens_fragmento = nombre_fragmento.lower().split()
            n_frag = len(tokens_fragmento)

            candidatos = []  # (nombre_perfil, longitud_tokens) — preferir el más largo
            for f in archivos:
                nombre_perfil = f.stem.replace("_", " ")
                tokens_perfil = nombre_perfil.lower().split()
                n_perfil = len(tokens_perfil)

                # Coincidencia exacta de prefijo:
                # "aleix ribas" matchea "aleix ribas canadell" (frag es prefijo del perfil)
                # "aleix ribas canadell" matchea "aleix ribas" (perfil es prefijo del frag)
                if n_frag >= 2 and n_perfil >= 2:
                    n_min = min(n_frag, n_perfil)
                    if tokens_fragmento[:n_min] == tokens_perfil[:n_min]:
                        candidatos.append((nombre_perfil.title(), n_perfil))

            if candidatos:
                # Devolver el perfil con más tokens (el nombre más completo)
                candidatos.sort(key=lambda x: x[1], reverse=True)
                return candidatos[0][0]

            # Fallback: algún token significativo en común
            for f in archivos:
                nombre_perfil = f.stem.replace("_", " ")
                tokens_perfil = nombre_perfil.lower().split()
                if any(t in tokens_perfil for t in tokens_fragmento if len(t) > 3):
                    return nombre_perfil.title()
        except Exception:
            pass
        return None

    def _obtener_estadisticas_globales(self) -> str:
        """Obtiene estadísticas del sistema completo."""
        try:
            stats = memory_manager.obtener_estadisticas_globales()

            texto_stats = f"""
ESTADÍSTICAS GLOBALES DEL SISTEMA
{'='*50}

👥 ASESORES:
- Total asesores: {stats.get('total_asesores', 0)}
- Asesores mejorando: {stats.get('asesores_mejorando', 0)}
- Asesores empeorando: {stats.get('asesores_empeorando', 0)}

📊 EVALUACIONES:
- Total evaluaciones: {stats.get('total_evaluaciones', 0)}

📚 BASE DE CONOCIMIENTO:
- Conversaciones excelentes en RAG: {stats.get('conversaciones_en_rag', 0)}
"""
            return texto_stats

        except Exception as e:
            return f"Error obteniendo estadísticas: {e}"

    def _busqueda_multicoleccion(self, pregunta: str) -> str:
        """Busca en múltiples colecciones y combina resultados."""
        resultados_todos = []

        res_manuales = buscar_en_coleccion(
            query=pregunta,
            collection_name=centauro_config.COLLECTION_MANUALES,
            k=2,
        )
        if res_manuales:
            resultados_todos.append("## DESDE MANUALES:\n" + res_manuales[0]['text'])

        res_ejemplos = buscar_en_coleccion(
            query=pregunta,
            collection_name=centauro_config.COLLECTION_BUENAS_PRACTICAS,
            k=2,
        )
        if res_ejemplos:
            resultados_todos.append("## DESDE EJEMPLOS:\n" + res_ejemplos[0]['text'])

        if resultados_todos:
            return "\n\n---\n\n".join(resultados_todos)

        return "No se encontró información relevante."

    # ------------------------------------------------------------------
    # Generación de respuesta
    # ------------------------------------------------------------------

    def _generar_respuesta(
        self,
        pregunta: str,
        contexto: str,
        intencion: str,
        bloque: Optional[str],
    ) -> str:
        """Genera respuesta usando LLM con contexto del RAG e historial de conversación."""

        nombre_bloque_display = {
            "investigacion": "Investigación y descubrimiento de necesidades",
            "propuesta_valor": "Propuesta de valor",
            "admision_economica": "Admisión y propuesta económica",
            "cierre": "Cierre y próximos pasos",
            "objeciones": "Manejo de objeciones",
            "estilo": "Estilo y comunicación",
        }.get(bloque, "") if bloque else ""

        bloque_instruccion = (
            f"\nIMPORTANTE: La pregunta es específicamente sobre el bloque "
            f"'{nombre_bloque_display}'. Centra tu respuesta exclusivamente "
            f"en ese bloque. No menciones otros bloques de venta salvo que "
            f"sea estrictamente necesario para dar contexto.\n"
        ) if bloque else ""

        if intencion == "perfil":
            prompt_sistema = f"""Eres un asistente especializado en análisis de rendimiento de asesores comerciales.
El usuario pregunta por un perfil y tienes acceso a sus estadísticas históricas REALES en el contexto.
IMPORTANTE:
- Responde SOLO con los datos que aparecen en el contexto. NO inventes evaluaciones, notas ni fechas.
- Si el contexto contiene el dato exacto que pide el usuario (ej: número de evaluaciones, nota en un bloque), cítalo directamente.
- Sé directo: responde la pregunta concreta primero, luego añade contexto si aporta valor.
- Si el contexto dice "No hay datos", dilo claramente sin adornar.
{bloque_instruccion}"""

        elif intencion == "ejemplo":
            prompt_sistema = f"""Eres un experto en ventas consultivas que proporciona ejemplos prácticos de buenas prácticas.
IMPORTANTE:
- Los ejemplos son REFERENCIAS, no reglas absolutas
- Explica el "por qué" detrás de cada técnica mostrada
- Sugiere adaptaciones según el contexto del asesor
- Mantén un tono inspirador, no prescriptivo
{bloque_instruccion}"""

        elif intencion == "manual":
            prompt_sistema = f"""Eres un instructor de ventas consultivas que explica procedimientos y mejores prácticas.
IMPORTANTE:
- Explica de forma clara y estructurada
- Usa el contexto del manual pero explícalo con tus propias palabras
- Proporciona razones detrás de cada recomendación
- Sé conciso pero completo
{bloque_instruccion}"""

        elif intencion == "estadisticas":
            prompt_sistema = """Eres un analista de datos que presenta estadísticas del sistema de forma comprensible.
IMPORTANTE:
- Presenta datos de forma clara
- Identifica tendencias y patrones
- Sugiere interpretaciones útiles
- Mantén un tono objetivo"""

        else:
            prompt_sistema = f"""Eres un asistente experto en ventas consultivas y evaluación de llamadas comerciales.
Responde preguntas usando el contexto proporcionado de nuestra base de conocimiento.
IMPORTANTE:
- Sé conciso y directo
- Cita ejemplos concretos del contexto cuando los haya
- Si no hay información suficiente, dilo claramente
{bloque_instruccion}"""

        # Incluir historial reciente en el prompt (últimas 3 interacciones)
        historial_texto = ""
        ultimas = self.historial_conversacion[-3:]
        if ultimas:
            lineas = []
            for h in ultimas:
                lineas.append(f"[Usuario]: {h['pregunta']}")
                # Truncar respuestas largas en el historial
                resp_corta = h['respuesta'][:300] + "..." if len(h['respuesta']) > 300 else h['respuesta']
                lineas.append(f"[Centauro]: {resp_corta}")
            historial_texto = "HISTORIAL RECIENTE DE LA CONVERSACIÓN:\n" + "\n".join(lineas) + "\n\n"

        prompt_usuario = f"""{historial_texto}PREGUNTA ACTUAL DEL USUARIO:
{pregunta}

CONTEXTO RELEVANTE DE LA BASE DE CONOCIMIENTO:
{contexto}

Responde la pregunta del usuario basándote en el contexto proporcionado.
Si el contexto no es suficiente para responder con precisión, indícalo claramente.
"""

        try:
            respuesta = consultar_gpt(
                prompt_sistema,
                prompt_usuario,
                "chat_interactivo",
                force_json=False,
            )
            return respuesta

        except Exception as e:
            return f"Error generando respuesta: {e}"

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def obtener_historial(self, ultimas_n: int = 5) -> List[Dict]:
        """Devuelve las últimas N interacciones del historial."""
        return self.historial_conversacion[-ultimas_n:]

    def limpiar_historial(self):
        """Limpia el historial de conversación."""
        self.historial_conversacion.clear()
