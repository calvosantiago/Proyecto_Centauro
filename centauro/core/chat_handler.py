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
import re
import logging
from typing import List, Dict, Optional
from ..config import centauro_config
from ..rag import buscar_en_coleccion
from ..llm_client import consultar_gpt
from .memoria import memory_manager
from .database import get_database

logger = logging.getLogger(__name__)


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
        self._pbi_historial: List[Dict] = []  # Últimos intercambios PBI para contexto
        self._asesor_sesion: Optional[str] = None  # Último asesor mencionado en esta sesión

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

        # Cortocircuito para consultas al modelo semántico de Power BI
        if intencion == "kpi":
            # Limpiar prefijo @pbi antes de enviar a Power BI
            pregunta_pbi = re.sub(r"^@pbi\s*", "", pregunta_usuario, flags=re.IGNORECASE).strip()
            respuesta = self._consultar_powerbi(pregunta_pbi)
            self.historial_conversacion.append({
                "pregunta": pregunta_usuario,
                "respuesta": respuesta,
                "intencion": intencion,
                "bloque": bloque_detectado,
            })
            return respuesta

        # Buscar contexto relevante (flujo RAG normal)
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
            "manual" | "ejemplo" | "perfil" | "estadisticas" | "kpi" | "general"

        Prefijos especiales:
            /modelo <pregunta>  → fuerza routing a Power BI (kpi)
        """
        pregunta_lower = pregunta.lower()

        # ── Prefijo @pbi → fuerza Power BI siempre ──────────────────────
        if pregunta_lower.strip().startswith("@pbi"):
            return "kpi"

        # ── ID de oportunidad (ej: 2021-002570912) → buscar en Supabase ─
        if re.search(r'\b\d{4}-\d{6,12}\b', pregunta):
            return "oportunidades"

        # ── Perfil de asesor concreto (PRIORIDAD ALTA) ──────────────────────
        # Preguntas sobre un asesor específico por nombre o sobre el propio asesor
        if any(kw in pregunta_lower for kw in [
            "mi rendimiento", "mi perfil", "mis evaluaciones",
            "cómo he mejorado", "mi progreso", "cómo estoy",
            "mis resultados",
            # Consultas temporales / historial
            "últimas", "ultimas", "última entrevista", "ultima entrevista",
            "última llamada", "ultima llamada", "esta entrevista", "esta llamada",
            "en esta llamada", "en esta entrevista",
            "cómo fui", "como fui", "cómo quedé", "como quede",
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
        tiene_nombre_propio = bool(re.search(r'\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\b', pregunta))
        if tiene_nombre_propio:
            bloques_en_pregunta = [
                "investigación", "investigacion", "cierre", "propuesta",
                "objeciones", "estilo", "admisión", "admision",
                "bloque", "calificación", "calificacion",
            ]
            if any(b in pregunta_lower for b in bloques_en_pregunta):
                return "perfil"

        # ── Consultas sobre pipeline de oportunidades/leads (CRM) ───────────
        if any(kw in pregunta_lower for kw in [
            "oportunidades de", "leads de", "cuántos leads", "cuantos leads",
            "cuántas oportunidades", "cuantas oportunidades",
            "por país", "por pais", "por programa", "por pilar",
            "de qué país", "de que pais",
            "entrevistas de méx", "entrevistas de esp",
            "de méxico", "de españa", "de colombia", "de argentina", "de perú",
            "del pilar", "del programa",
        ]):
            return "oportunidades"

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

        # ── KPIs y métricas del modelo semántico Power BI ────────────────
        if any(kw in pregunta_lower for kw in [
            "kpi", "kpis", "métrica", "metrica", "métricas", "metricas",
            "dashboard", "power bi", "powerbi",
            "ventas del mes", "ventas del año", "ventas de", "total ventas",
            "objetivo de ventas", "target", "revenue",
            "tasa de conversión", "tasa de conversion", "tasa de cierre",
            "leads totales", "leads activos", "pipeline total",
            "matriculados", "matrículas", "matriculas",
            "facturación", "facturacion", "ingresos del",
            "cuánto vendió", "cuanto vendio", "cuánto se vendió",
            "ranking de asesores", "ranking por ventas",
            "mejor asesor", "top asesores",
            # consultas directas a tablas del modelo
            "tabla h_", "h_convocatorio", "h_matricula", "h_lead", "h_contacto",
            "cuántas filas", "cuantas filas", "cuántos registros", "cuantos registros",
            "cuántas ventas", "cuantas ventas", "cuántos leads", "cuantos leads",
            "cuántos matriculados", "cuantos matriculados",
            "total de filas", "número de filas", "numero de filas",
            "total de registros", "número de registros", "numero de registros",
            "modelo semántico", "modelo semantico", "consulta dax", "dax",
            "top 5", "top 10", "ranking", "promedio de", "suma de",
            "por país", "por pais", "por programa", "por asesor", "por mes", "por año",
        ]):
            return "kpi"

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

        elif intencion == "oportunidades":
            return self._consultar_oportunidades(pregunta)

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
        # Prioridad de resolución:
        # 1. nombre_asesor pasado por Chainlit (usuario logado → "mis evaluaciones")
        # 2. Nombre extraído del texto de la pregunta ("de Laura", "a Aleix")
        # 3. Último asesor mencionado en esta sesión (contexto conversacional)
        # 4. Sin asesor → listar disponibles desde Supabase y pedir nombre
        if not nombre_asesor:
            nombre_asesor = self._extraer_nombre_de_pregunta(pregunta)

        if not nombre_asesor:
            nombre_asesor = self._asesor_sesion

        if not nombre_asesor:
            db = get_database()
            if db.disponible:
                asesores = db.listar_asesores()
                if not asesores:
                    return "Aún no hay evaluaciones registradas en el sistema."
                nombres = [a["nombre"] for a in asesores[:10]]
                lista = "\n".join(f"- {n}" for n in nombres)
                return (
                    f"No sé de qué asesor quieres ver el rendimiento. "
                    f"Hay {len(asesores)} asesor(es) en el sistema:\n{lista}\n\n"
                    f"Dime el nombre y te muestro su perfil."
                )
            return (
                "No sé de qué asesor quieres ver el rendimiento. "
                "Por favor indica el nombre del asesor."
            )

        # Actualizar contexto de sesión con el asesor identificado
        self._asesor_sesion = nombre_asesor

        # ── Router: detectar si pide últimas N o esta/última entrevista ────
        pregunta_lower = pregunta.lower()

        # "últimas 5 entrevistas", "mis últimas 3 llamadas", etc.
        m_n = re.search(r'\b[uú]ltimas?\s+(\d+)\b', pregunta_lower)
        if m_n:
            n = int(m_n.group(1))
            return self._obtener_ultimas_n_evaluaciones(nombre_asesor, n, pregunta)

        # "esta entrevista", "esta llamada", "última entrevista", "última llamada"
        if any(kw in pregunta_lower for kw in [
            "esta entrevista", "esta llamada", "en esta entrevista", "en esta llamada",
            "última entrevista", "ultima entrevista", "última llamada", "ultima llamada",
        ]):
            return self._obtener_resumen_ultima_evaluacion(nombre_asesor)

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

    def _obtener_ultimas_n_evaluaciones(
        self, nombre_asesor: str, n: int, pregunta: str
    ) -> str:
        """
        Consulta las últimas N evaluaciones de un asesor directamente desde Supabase
        y devuelve un resumen estructurado con calificaciones por bloque.
        """
        db = get_database()
        EMOJI = {"BUENO": "🟢", "MEJORABLE": "🟡", "MALO": "🔴"}

        if db.disponible:
            asesor = db.buscar_asesor(nombre_asesor)
            if not asesor:
                return f"No encontré a **{nombre_asesor}** en el sistema."

            evaluaciones = db.obtener_evaluaciones(asesor["id"])
            if not evaluaciones:
                return f"No hay evaluaciones registradas para **{nombre_asesor}**."

            ultimas = evaluaciones[-n:]
            lineas = [
                f"## Últimas {len(ultimas)} evaluaciones de {nombre_asesor}\n"
            ]
            for i, ev in enumerate(reversed(ultimas), 1):
                fecha = ev.get("fecha", "")[:10]
                cal_global = ev.get("calificacion_global") or "N/A"
                opp_id = ev.get("opportunity_id")
                archivo = ev.get("archivo_origen") or "—"

                # Enriquecer con datos del lead si hay opportunity_id
                lead_linea = ""
                if opp_id:
                    opp = db.obtener_oportunidad(opp_id)
                    if opp:
                        nombre_lead = opp.get("nombre_lead") or "—"
                        is_won = opp.get("is_won")
                        if is_won is True:
                            matricula_txt = "✅ Matriculado"
                        elif is_won is False:
                            matricula_txt = "❌ No matriculado"
                        else:
                            matricula_txt = "⏳ Resultado pendiente"
                        lead_linea = f"**Lead:** {nombre_lead} | {matricula_txt}\n"

                bloques_raw = db.obtener_calificaciones_bloque(ev["id"])
                bloques_txt = "  _(sin datos de bloques)_"
                if bloques_raw:
                    bloques_txt = "\n".join(
                        f"  {EMOJI.get(b['calificacion'], '⚪')} **{b['bloque']}**: {b['calificacion'] or 'N/A'}"
                        for b in bloques_raw
                    )

                lineas.append(
                    f"### #{i} — {fecha} | Global: {EMOJI.get(cal_global, '⚪')} {cal_global}\n"
                    f"{lead_linea}"
                    f"**Oportunidad:** {opp_id or '—'} | **Archivo:** {archivo}\n"
                    f"{bloques_txt}\n"
                )
            return "\n".join(lineas)

        # Fallback a JSON si Supabase no disponible
        try:
            perfil = memory_manager.cargar_perfil(nombre_asesor)
            ultimas = perfil.evaluaciones[-n:]
            lineas = [f"## Últimas {len(ultimas)} evaluaciones de {nombre_asesor}\n"]
            for i, ev in enumerate(reversed(ultimas), 1):
                fecha = ev.fecha[:10]
                cal_global = ev.calificacion_global or "N/A"
                bloques_txt = "\n".join(
                    f"  {EMOJI.get(cal, '⚪')} **{b}**: {cal or 'N/A'}"
                    for b, cal in ev.calificaciones_por_bloque.items()
                )
                lineas.append(
                    f"### #{i} — {fecha} | Global: {EMOJI.get(cal_global, '⚪')} {cal_global}\n"
                    f"{bloques_txt}\n"
                )
            return "\n".join(lineas)
        except Exception as e:
            return f"Error consultando evaluaciones de {nombre_asesor}: {e}"

    def _obtener_resumen_ultima_evaluacion(self, nombre_asesor: str) -> str:
        """
        Devuelve el resumen de la evaluación más reciente de un asesor,
        incluyendo calificaciones por bloque, recomendaciones y resumen contextual.
        """
        db = get_database()
        EMOJI = {"BUENO": "🟢", "MEJORABLE": "🟡", "MALO": "🔴"}

        if db.disponible:
            asesor = db.buscar_asesor(nombre_asesor)
            if not asesor:
                return f"No encontré a **{nombre_asesor}** en el sistema."

            evaluaciones = db.obtener_evaluaciones(asesor["id"])
            if not evaluaciones:
                return f"No hay evaluaciones registradas para **{nombre_asesor}**."

            ev = evaluaciones[-1]
            fecha = ev.get("fecha", "")[:10]
            cal_global = ev.get("calificacion_global") or "N/A"
            opp_id = ev.get("opportunity_id")
            archivo = ev.get("archivo_origen") or "—"

            # Enriquecer con datos del lead
            nombre_lead = "—"
            matricula_txt = "⏳ Resultado pendiente"
            if opp_id:
                opp = db.obtener_oportunidad(opp_id)
                if opp:
                    nombre_lead = opp.get("nombre_lead") or "—"
                    is_won = opp.get("is_won")
                    if is_won is True:
                        matricula_txt = "✅ Matriculado"
                    elif is_won is False:
                        matricula_txt = "❌ No matriculado"

            # Contexto de la llamada
            perfil_lead = ev.get("perfil_lead") or "—"
            factor_compra = ev.get("factor_determinante_compra") or "—"
            fecha_seguimiento = ev.get("fecha_seguimiento") or "—"
            barreras = ev.get("barreras_principales")
            if isinstance(barreras, str):
                import json as _json
                try:
                    barreras = _json.loads(barreras)
                except Exception:
                    barreras = []
            barreras_txt = ", ".join(barreras) if barreras else "—"

            bloques_raw = db.obtener_calificaciones_bloque(ev["id"])
            bloques_lineas = []
            recomendaciones = []
            for b in bloques_raw:
                cal = b.get("calificacion") or "N/A"
                bloque = b.get("bloque", "")
                evidencia = b.get("evidencia_principal") or ""
                rec = b.get("recomendacion_accionable") or ""
                bloques_lineas.append(
                    f"{EMOJI.get(cal, '⚪')} **{bloque}**: {cal}"
                    + (f"\n   _{evidencia}_" if evidencia else "")
                )
                if rec:
                    recomendaciones.append(f"- **{bloque}**: {rec}")

            bloques_txt = "\n".join(bloques_lineas) or "_(sin datos)_"
            recs_txt = "\n".join(recomendaciones) or "_(ninguna)_"

            return (
                f"## Última evaluación de {nombre_asesor}\n"
                f"**Fecha:** {fecha} | **Oportunidad:** {opp_id or '—'}\n"
                f"**Lead:** {nombre_lead} | {matricula_txt}\n"
                f"**Archivo:** {archivo}\n\n"
                f"### Resultado global: {EMOJI.get(cal_global, '⚪')} {cal_global}\n\n"
                f"**Perfil lead:** {perfil_lead}\n"
                f"**Factor determinante compra:** {factor_compra}\n"
                f"**Fecha seguimiento:** {fecha_seguimiento}\n"
                f"**Barreras:** {barreras_txt}\n\n"
                f"### Calificaciones por bloque\n{bloques_txt}\n\n"
                f"### Recomendaciones accionables\n{recs_txt}"
            )

        # Fallback JSON
        try:
            perfil = memory_manager.cargar_perfil(nombre_asesor)
            if not perfil.evaluaciones:
                return f"No hay evaluaciones registradas para {nombre_asesor}."
            ev = perfil.evaluaciones[-1]
            cal_global = ev.calificacion_global or "N/A"
            bloques_txt = "\n".join(
                f"{EMOJI.get(cal, '⚪')} **{b}**: {cal or 'N/A'}"
                for b, cal in ev.calificaciones_por_bloque.items()
            )
            return (
                f"## Última evaluación de {nombre_asesor}\n"
                f"**Fecha:** {ev.fecha[:10]}\n\n"
                f"### Resultado global: {EMOJI.get(cal_global, '⚪')} {cal_global}\n\n"
                f"### Calificaciones por bloque\n{bloques_txt}"
            )
        except Exception as e:
            return f"Error consultando última evaluación de {nombre_asesor}: {e}"

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
        Busca el nombre_fragmento en los asesores de Supabase (nombre canónico + aliases).

        Prioriza coincidencia por prefijo de tokens:
        "Aleix Ribas" matchea "Aleix Ribas Canadell" y viceversa.
        También comprueba aliases para variantes de nombre.
        """
        db = get_database()
        if not db.disponible:
            return None

        try:
            asesores = db.listar_asesores()
            tokens_frag = nombre_fragmento.lower().split()
            n_frag = len(tokens_frag)

            candidatos = []  # (nombre_canonico, n_tokens) — preferir el más largo

            for asesor in asesores:
                nombres_a_probar = [asesor["nombre"]] + (asesor.get("aliases") or [])

                for nombre_candidato in nombres_a_probar:
                    tokens_c = nombre_candidato.lower().split()
                    n_c = len(tokens_c)

                    if n_frag >= 2 and n_c >= 2:
                        n_min = min(n_frag, n_c)
                        if tokens_frag[:n_min] == tokens_c[:n_min]:
                            candidatos.append((asesor["nombre"], n_c))
                            break  # un match por asesor es suficiente

            if candidatos:
                candidatos.sort(key=lambda x: x[1], reverse=True)
                return candidatos[0][0]

            # Fallback: algún token significativo en común
            for asesor in asesores:
                nombres_a_probar = [asesor["nombre"]] + (asesor.get("aliases") or [])
                for nombre_candidato in nombres_a_probar:
                    tokens_c = nombre_candidato.lower().split()
                    if any(t in tokens_c for t in tokens_frag if len(t) > 3):
                        return asesor["nombre"]

        except Exception:
            pass
        return None

    def _consultar_oportunidades(self, pregunta: str) -> str:
        """
        Consulta estadísticas de la tabla oportunidades en Supabase.
        Detecta filtros en la pregunta (país, pilar, programa) y agrega los datos.
        """
        db = get_database()
        if not db.disponible:
            return "Supabase no disponible para consultar oportunidades."

        pregunta_lower = pregunta.lower()

        # ── Búsqueda por ID concreto (ej: 2021-002570912) ───────────────
        match_id = re.search(r'\b(\d{4}-\d{6,12})\b', pregunta)
        if match_id:
            opportunity_id = match_id.group(1)
            datos = db.obtener_oportunidad(opportunity_id)
            if datos:
                campos = []
                for k, v in datos.items():
                    if k not in ("id", "fecha_sync", "datos_extra") and v is not None:
                        campos.append(f"- **{k}**: {v}")
                detalle = "\n".join(campos)
                return f"Datos de la oportunidad `{opportunity_id}` en Supabase:\n\n{detalle}"
            else:
                # No está en Supabase → fallback automático a Power BI
                logger.info(f"ID {opportunity_id} no en Supabase → consultando Power BI")
                pregunta_pbi = f"Dame los datos de la oportunidad {opportunity_id} en H_CUPONES: pilar, país, programa, estado, nombre del cliente"
                return self._consultar_powerbi(pregunta_pbi)

        # Detectar filtros en la pregunta
        filtros = {}

        PAISES = {
            "méxico": "México", "mexico": "México",
            "españa": "España", "espana": "España",
            "colombia": "Colombia",
            "argentina": "Argentina",
            "perú": "Perú", "peru": "Perú",
            "chile": "Chile",
        }
        for kw, valor in PAISES.items():
            if kw in pregunta_lower:
                filtros["pais"] = valor
                break

        PILARES = {
            "redes sociales": "Redes Sociales",
            "mba": "MBA",
            "máster": "Máster", "master": "Máster",
            "executive": "Executive Education",
            "online": "Online",
        }
        for kw, valor in PILARES.items():
            if kw in pregunta_lower:
                filtros["pilar"] = valor
                break

        oportunidades = db.obtener_oportunidades_filtradas(
            filtros=filtros if filtros else None
        )

        if not oportunidades:
            filtro_desc = ", ".join(f"{k}={v}" for k, v in filtros.items()) if filtros else "sin filtros"
            return f"No se encontraron oportunidades ({filtro_desc}) en Supabase."

        from collections import Counter
        total = len(oportunidades)
        por_pais = Counter(o.get("pais") for o in oportunidades if o.get("pais"))
        por_pilar = Counter(o.get("pilar") for o in oportunidades if o.get("pilar"))
        por_programa = Counter(o.get("programa") for o in oportunidades if o.get("programa"))

        top_paises = "\n".join(f"  - {p}: {c}" for p, c in por_pais.most_common(8))
        top_pilares = "\n".join(f"  - {p}: {c}" for p, c in por_pilar.most_common(8))
        top_programas = "\n".join(f"  - {p}: {c}" for p, c in por_programa.most_common(8))

        filtro_desc = " | ".join(f"{k}: {v}" for k, v in filtros.items()) if filtros else "todos los registros"

        return (
            f"## Oportunidades en pipeline (filtro: {filtro_desc})\n"
            f"**Total registros**: {total:,}\n\n"
            f"### Por país (top 8)\n{top_paises}\n\n"
            f"### Por pilar (top 8)\n{top_pilares}\n\n"
            f"### Por programa (top 8)\n{top_programas}"
        )

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
    # Power BI — Consultas al modelo semántico
    # ------------------------------------------------------------------

    def _consultar_powerbi(self, pregunta: str) -> str:
        """
        Consulta el modelo semántico de Power BI para responder KPIs y métricas.
        Usa un agente OpenAI (pbi_agent) que decide iterativamente qué herramientas
        llamar (consultar diccionario, ejecutar DAX, reintentar si falla).

        Los comandos DAX directos (@pbi EVALUATE ...) se ejecutan sin pasar por el agente.
        """
        try:
            from .powerbi_client import get_powerbi_client
            client = get_powerbi_client()
        except Exception as e:
            logger.error(f"Error importando PowerBIClient: {e}")
            return (
                "No se pudo cargar el cliente de Power BI. "
                f"Detalle: {e}"
            )

        if client is None:
            return (
                "El cliente de Power BI no está configurado.\n\n"
                "Asegúrate de tener en `.env`:\n"
                "- `AZURE_CLIENT_ID`\n"
                "- `AZURE_TENANT_ID`\n"
                "- `PBI_WORKSPACE_ID`\n"
                "- `PBI_DATASET_ID`\n\n"
                "Luego ejecuta `python scripts/pbi_auth.py` para autenticarte."
            )

        if not client.disponible:
            return (
                "No hay refresh token guardado para Power BI.\n\n"
                "Ejecuta en la terminal:\n"
                "```\npython scripts/pbi_auth.py\n```\n"
                "y sigue las instrucciones para autenticarte con tu cuenta de Planeta."
            )

        # Sandbox DAX directo: ejecutar sin pasar por el agente
        import re as _re
        pregunta_stripped = pregunta.strip()
        _dax_raw = _re.sub(r"^dax\s*:\s*", "", pregunta_stripped, flags=_re.IGNORECASE)
        if _dax_raw.upper().startswith(("EVALUATE", "DEFINE")):
            try:
                return client.query_nl(pregunta)
            except Exception as e:
                logger.error(f"Error en sandbox DAX: {e}")
                return f"Error ejecutando DAX: {e}"

        # Consulta en lenguaje natural → agente Claude
        try:
            from .pbi_agent import responder as agente_responder
            respuesta = agente_responder(pregunta, client, historial=self._pbi_historial)

            # Guardar intercambio en historial (máximo 3 últimos)
            self._pbi_historial.append({"pregunta": pregunta, "respuesta": respuesta})
            if len(self._pbi_historial) > 3:
                self._pbi_historial.pop(0)

            return respuesta
        except Exception as e:
            logger.error(f"Error en agente PBI: {e}")
            return f"Error al consultar el modelo semántico de Power BI: {e}"

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def obtener_historial(self, ultimas_n: int = 5) -> List[Dict]:
        """Devuelve las últimas N interacciones del historial."""
        return self.historial_conversacion[-ultimas_n:]

    def limpiar_historial(self):
        """Limpia el historial de conversación."""
        self.historial_conversacion.clear()
