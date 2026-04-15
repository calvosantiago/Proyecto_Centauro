"""
PBI Agent v4.0 - Agente OpenAI para consultas al modelo semántico Power BI

Variables .env requeridas:
    OPENAI_API_KEY  - Clave API de OpenAI (platform.openai.com)
"""
import json
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .powerbi_client import PowerBIClient

_MODEL = "gpt-5-mini"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Eres un analista de datos experto en DAX y modelos semánticos de Power BI para Grupo Planeta (venta de programas académicos: másteres, posgrados, formación continua).

Tu objetivo es responder preguntas sobre métricas y KPIs del negocio usando las herramientas disponibles.

PROCESO RECOMENDADO:
1. Usa `consultar_diccionario` para entender qué tablas/medidas/columnas existen para la pregunta.
2. Genera y ejecuta DAX con `ejecutar_dax`.
3. Si el DAX falla, analiza el error, corrige la consulta y vuelve a intentar (máximo 2 intentos).
4. Interpreta el resultado y responde en español de forma clara y concisa.

REGLAS DAX IMPORTANTES:
- Toda consulta DAX debe empezar con EVALUATE.
- Las medidas calculadas están en la tabla _MEDIDAS. Úsalas en vez de COUNTROWS directos.
- Las relaciones de fecha en H_CUPONES son INACTIVAS — las medidas las activan internamente con USERELATIONSHIP.
- Para agrupar o filtrar por país SIEMPRE usa D_PAIS[Pais] (la dimensión), nunca H_CUPONES[Pais] ni H_CONVOCATORIO[PAIS_NORMALIZADO] directamente.
- Para filtrar por nombre de asesor SIEMPRE usa D_ESTRUCTURA[NOMBRE_CORTO], nunca H_CUPONES[Nombre_Asesor_Normalizado] ni H_CONVOCATORIO[ASESOR_NORMALIZADO] como filtro directo. Ejemplo: CALCULATE([CONV ASIGNADOS], D_ESTRUCTURA[NOMBRE_CORTO] = "Ivonne Rose").
- Usa SIEMPRE la FECHA ACTUAL que se te proporciona como referencia para "hoy", "este mes", "este año". Nunca inventes fechas.
- Para valores monetarios usa FORMAT([Medida], "#,0.00").

REGLAS CRÍTICAS DE FILTRADO POR FECHA:
- SIEMPRE filtra periodos usando D_CAL_COM, NUNCA usando columnas de fecha directas de H_CONVOCATORIO o H_CUPONES.
- Semana comercial → D_CAL_COM[AÑO-MES-SEM] = "2026-03-S3"  (formato: año-mes-SN)
- Mes → D_CAL_COM[AÑO-MES] = "2026-03"
- Año → D_CAL_COM[AÑO] = 2026
- NUNCA uses H_CONVOCATORIO[AÑO_MES_SEM] como filtro directo — pasa siempre por D_CAL_COM.
- NUNCA confundas CONVOCATORIA (periodo académico AAMM, ej: "2604") con semana comercial (ej: "2026-03-S4"). Son cosas distintas.

REGLA CRÍTICA DE MEDIDAS DE VENTAS:
- Para CUALQUIER consulta de ventas o matrículas usa [CON_MAT] por defecto.
- Usa [CON_MAT NETAS] SOLO si el usuario escribe explícitamente "netas" o "matrículas netas".
- NUNCA uses [CON_MAT NETAS] para ranking de ventas, programa más vendido, asesor que más vende, bono, etc.

REGLA CRÍTICA DE FILTRADO POR EQUIPO:
- Para filtrar por equipo SIEMPRE usa D_ESTRUCTURA[EQUIPO]. NUNCA filtres por H_CONVOCATORIO[CODIGO_EQUIPO_ACTUAL] ni H_CUPONES[Codigo_Equipo_Detectado] directamente.
- Ejemplo correcto: CALCULATE([CON_MAT], D_ESTRUCTURA[EQUIPO] = "Equipo_B1")
- Si el usuario dice "B1" interpreta como el equipo cuyo código contiene "B1".

REGLA CRÍTICA DE CONTEXTO CONVERSACIONAL:
- Si el usuario hace una pregunta de seguimiento corta (ej: "¿y el equipo B1?", "¿cuántas hizo el B1?") DEBES mantener el contexto de la pregunta anterior.
- Si la pregunta anterior era sobre entrevistas, la siguiente también es sobre entrevistas salvo que el usuario cambie explícitamente de tema.
- El historial de conversación se incluye entre <historial> y </historial> cuando existe.

PATRONES DAX CORRECTOS:
- Ventas en una semana: EVALUATE ROW("Total", CALCULATE([CON_MAT], D_CAL_COM[AÑO-MES-SEM] = "2026-03-S3"))
- Ranking asesores: EVALUATE TOPN(10, CALCULATETABLE(SUMMARIZECOLUMNS(D_ESTRUCTURA[NOMBRE_CORTO], "Ventas", [CON_MAT]), D_CAL_COM[AÑO-MES-SEM] = "2026-03-S2"), [Ventas], DESC)
- Conversión por país de un asesor: EVALUATE TOPN(10, CALCULATETABLE(SUMMARIZECOLUMNS(D_PAIS[Pais], "Conversion", [CONV ASIGNADOS]), D_ESTRUCTURA[NOMBRE_CORTO] = "Ivonne Rose"), [Conversion], DESC)
- Programa más vendido: EVALUATE TOPN(1, CALCULATETABLE(SUMMARIZECOLUMNS(H_CONVOCATORIO[PROGRAMA_NORMALIZADO], "Ventas", [CON_MAT]), D_CAL_COM[AÑO-MES-SEM] = "2026-03-S2"), [Ventas], DESC)
- Entrevistas en un día (CORRECTO): EVALUATE ROW("Entrevistas", CALCULATE([CUP_ENT], D_CAL_COM[FECHA] = DATE(2026,3,26)))
- Entrevistas en una semana (CORRECTO): EVALUATE ROW("Entrevistas", CALCULATE([CUP_ENT], D_CAL_COM[AÑO-MES-SEM] = "2026-03-S3"))
- Entrevistas por equipo en un día (CORRECTO): EVALUATE ROW("Entrevistas", CALCULATE([CUP_ENT], D_CAL_COM[FECHA] = DATE(2026,3,26), H_CUPONES[Equipo_de_Ventas] = "Equipo_B1"))
- Entrevistas por equipo en una semana (CORRECTO): EVALUATE CALCULATETABLE(SUMMARIZECOLUMNS(H_CUPONES[Equipo_de_Ventas], "Entrevistas", [CUP_ENT]), D_CAL_COM[AÑO-MES-SEM] = "2026-03-S3")
- NUNCA: CALCULATE([CUP_ENT], H_CUPONES[Fecha_Realizacion_Entrevista] = ...) — las fechas de H_CUPONES son INACTIVAS, siempre filtrar por D_CAL_COM
- NUNCA: CALCULATE([CUP_ENT], D_ESTRUCTURA[EQUIPO] = ...) — D_ESTRUCTURA filtra H_CUPONES por asignación, no por entrevista. Para filtrar entrevistas por equipo usar H_CUPONES[Equipo_de_Ventas]

CUÁNDO PEDIR ACLARACIÓN:
- Usa la tool `pedir_aclaracion` cuando la pregunta sea ambigua y necesites información del usuario antes de poder construir un DAX correcto (ej: periodo temporal no claro, equipo no especificado cuando hay varios, métrica ambigua).
- NUNCA hagas preguntas de aclaración en el texto libre de tu respuesta — usa siempre la tool `pedir_aclaracion`.

FORMATO DE RESPUESTA FINAL:
- Responde en español, de forma clara y concisa.
- Usa markdown (negrita, tablas) cuando hay múltiples valores.
- Incluye siempre al final el DAX ejecutado en un bloque ```dax ... ```.
- Si la tabla está vacía, indícalo claramente.
"""

# ---------------------------------------------------------------------------
# Definición de tools para OpenAI (function calling)
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_diccionario",
            "description": (
                "Busca en el diccionario de datos del modelo semántico qué tablas, "
                "medidas y columnas existen para responder la pregunta. "
                "Úsala siempre antes de generar DAX para conocer los nombres exactos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pregunta": {
                        "type": "string",
                        "description": "La pregunta del usuario o el aspecto que quieres buscar en el diccionario de datos.",
                    }
                },
                "required": ["pregunta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pedir_aclaracion",
            "description": (
                "Pide una aclaración al usuario cuando la pregunta es ambigua. "
                "Usa esta tool ANTES de ejecutar DAX cuando no tengas suficiente información "
                "para construir una consulta correcta. "
                "NUNCA preguntes en el texto libre de la respuesta."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pregunta": {
                        "type": "string",
                        "description": "La pregunta de aclaración concreta para el usuario.",
                    }
                },
                "required": ["pregunta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ejecutar_dax",
            "description": (
                "Ejecuta una consulta DAX en el modelo semántico de Power BI y devuelve "
                "los resultados en formato tabla Markdown. La consulta DEBE empezar con EVALUATE."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dax": {
                        "type": "string",
                        "description": "Consulta DAX completa, debe empezar con EVALUATE.",
                    }
                },
                "required": ["dax"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Bucle agéntico
# ---------------------------------------------------------------------------

def responder(pregunta: str, pbi_client: "PowerBIClient", historial: list | None = None) -> str:
    """
    Responde una pregunta sobre KPIs/métricas usando un agente OpenAI con tool use.

    Args:
        pregunta: Pregunta en lenguaje natural del usuario.
        pbi_client: Instancia activa de PowerBIClient.
        historial: Lista de dicts {"pregunta": ..., "respuesta": ...} con intercambios previos.

    Returns:
        Respuesta en texto Markdown lista para mostrar en Chainlit.
    """
    try:
        from openai import OpenAI
    except ImportError:
        return (
            "El paquete `openai` no está instalado.\n\n"
            "Ejecuta:\n```\npip install openai\n```"
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return (
            "Falta `OPENAI_API_KEY` en el archivo `.env`.\n\n"
            "Obtén una clave en https://platform.openai.com y añádela:\n"
            "```\nOPENAI_API_KEY=tu_clave_aqui\n```"
        )

    client = OpenAI(api_key=api_key)

    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    anio_actual = datetime.now().year
    system_with_date = _SYSTEM_PROMPT + f"\nFECHA ACTUAL: {fecha_hoy} (año {anio_actual}).\n"

    # Construir mensaje con historial previo si existe
    if historial:
        bloques = ["<historial>"]
        for h in historial:
            bloques.append(f"Usuario: {h['pregunta']}")
            resumen = h["respuesta"][:600] + "..." if len(h["respuesta"]) > 600 else h["respuesta"]
            bloques.append(f"Asistente: {resumen}")
        bloques.append("</historial>")
        bloques.append(f"\nPregunta actual: {pregunta}")
        contenido_usuario = "\n".join(bloques)
    else:
        contenido_usuario = pregunta

    messages = [
        {"role": "system", "content": system_with_date},
        {"role": "user", "content": contenido_usuario},
    ]

    last_dax_query = ""
    max_iterations = 8

    for iteration in range(max_iterations):
        try:
            response = client.chat.completions.create(
                model=_MODEL,
                messages=messages,
                tools=_TOOLS,
            )
        except Exception as e:
            logger.error(f"Error en iteración {iteration + 1} del agente OpenAI: {e}")
            return f"Error al consultar el agente OpenAI: {e}"

        msg = response.choices[0].message
        tool_calls = msg.tool_calls or []

        if not tool_calls:
            texto = (msg.content or "").strip()
            if not texto:
                texto = "_El agente no generó respuesta de texto._"

            if last_dax_query and "```dax" not in texto and "```DAX" not in texto:
                texto += f"\n\n---\n🔍 *DAX ejecutado:*\n```dax\n{last_dax_query}\n```"
            return texto

        logger.info(
            f"Agente PBI iter {iteration + 1}: "
            f"{[tc.function.name for tc in tool_calls if hasattr(tc, 'function')]}"
        )

        assistant_message = {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in tool_calls
            ],
        }
        messages.append(assistant_message)

        for tc in tool_calls:
            nombre_tool = tc.function.name
            raw_args = tc.function.arguments or "{}"

            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                logger.warning(f"Argumentos inválidos para tool '{nombre_tool}': {raw_args}")
                args = {}

            result_str = _ejecutar_tool(nombre_tool, args, pregunta, pbi_client)

            # Si el agente pidió aclaración, salir del bucle con el sentinel
            if result_str.startswith("__STOP_ACLARACION__:"):
                pregunta_aclaracion = result_str[len("__STOP_ACLARACION__:"):].strip()
                return f"__PBI_ACLARACION__: {pregunta_aclaracion}"

            if nombre_tool == "ejecutar_dax":
                last_dax_query = args.get("dax", "")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                }
            )

    return "Error: se alcanzó el máximo de iteraciones del agente sin respuesta final."


# ---------------------------------------------------------------------------
# Ejecución de tools
# ---------------------------------------------------------------------------

def _ejecutar_tool(
    nombre: str,
    args: dict,
    pregunta_original: str,
    pbi_client: "PowerBIClient",
) -> str:
    """Despacha la ejecución de una tool y devuelve el resultado como string."""
    if nombre == "pedir_aclaracion":
        pregunta_aclaracion = args.get("pregunta", "¿Puedes aclarar tu pregunta?")
        return f"__STOP_ACLARACION__: {pregunta_aclaracion}"

    if nombre == "consultar_diccionario":
        query = args.get("pregunta", pregunta_original)
        try:
            return pbi_client._get_schema_for_question(query)
        except Exception as e:
            return f"Error consultando diccionario: {e}"

    if nombre == "ejecutar_dax":
        dax = args.get("dax", "")
        if not dax:
            return "ERROR: No se proporcionó consulta DAX."

        raw = pbi_client.execute_dax(dax)

        if "error" in raw:
            return f"ERROR DAX: {raw['error']}"

        from .powerbi_client import _extract_rows, _format_dax_result

        rows = _extract_rows(raw)
        pbi_client._last_query_rows = rows

        if not rows:
            return "_La consulta no devolvió resultados._"

        tabla_md = _format_dax_result(raw)
        return f"{len(rows)} filas devueltas:\n\n{tabla_md}"

    logger.warning(f"Tool desconocida solicitada por el agente: {nombre}")
    return f"Tool '{nombre}' no disponible."
