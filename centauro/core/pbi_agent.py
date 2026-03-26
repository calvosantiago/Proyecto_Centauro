"""
PBI Agent v1.0 - Agente Gemini para consultas al modelo semántico Power BI

Reemplaza el pipeline lineal NL→DAX→resultado de query_nl() por un agente
que decide iterativamente qué herramientas usar para responder la pregunta.

Variables .env requeridas:
    GEMINI_API_KEY  - Clave API de Google AI Studio (aistudio.google.com)

Para cambiar a Claude en el futuro, reemplaza _run_gemini_agent() por
una implementación equivalente con anthropic.messages.create() + tool_use.
"""
import os
import logging
from datetime import datetime
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .powerbi_client import PowerBIClient


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
- Para agrupar por país usa H_CUPONES[Pais] directamente.
- NUNCA agrupes por D_PAIS[Pais] (tiene valores duplicados) — usa D_PAIS[ID_Pais].
- Usa SIEMPRE la FECHA ACTUAL que se te proporciona como referencia para "hoy", "este mes", "este año". Nunca inventes fechas.
- Para valores monetarios usa FORMAT([Medida], "#,0.00").

FORMATO DE RESPUESTA FINAL:
- Responde en español, de forma clara y concisa.
- Usa markdown (negrita, tablas) cuando hay múltiples valores.
- Incluye siempre al final el DAX ejecutado en un bloque ```dax ... ```.
- Si la tabla está vacía, indícalo claramente.
"""


# ---------------------------------------------------------------------------
# Definición de tools para Gemini
# ---------------------------------------------------------------------------

def _get_tools():
    """Retorna la lista de tools en formato Gemini FunctionDeclaration."""
    import google.generativeai as genai

    return [
        genai.protos.Tool(
            function_declarations=[
                genai.protos.FunctionDeclaration(
                    name="consultar_diccionario",
                    description=(
                        "Busca en el diccionario de datos del modelo semántico qué tablas, "
                        "medidas y columnas existen para responder la pregunta. "
                        "Úsala siempre antes de generar DAX para conocer los nombres exactos."
                    ),
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "pregunta": genai.protos.Schema(
                                type=genai.protos.Type.STRING,
                                description="La pregunta del usuario o el aspecto que quieres buscar en el diccionario de datos.",
                            )
                        },
                        required=["pregunta"],
                    ),
                ),
                genai.protos.FunctionDeclaration(
                    name="ejecutar_dax",
                    description=(
                        "Ejecuta una consulta DAX en el modelo semántico de Power BI y devuelve "
                        "los resultados en formato tabla Markdown. La consulta DEBE empezar con EVALUATE."
                    ),
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "dax": genai.protos.Schema(
                                type=genai.protos.Type.STRING,
                                description="Consulta DAX completa, debe empezar con EVALUATE.",
                            )
                        },
                        required=["dax"],
                    ),
                ),
            ]
        )
    ]


# ---------------------------------------------------------------------------
# Bucle agéntico
# ---------------------------------------------------------------------------

def responder(pregunta: str, pbi_client: "PowerBIClient") -> str:
    """
    Responde una pregunta sobre KPIs/métricas usando un agente Gemini con tools.

    El agente decide iterativamente qué herramientas llamar (consultar diccionario,
    ejecutar DAX, reintentar si falla) hasta construir una respuesta completa.

    Efectos secundarios:
        pbi_client._last_query_rows se actualiza con las filas del último DAX ejecutado,
        lo que permite a app.py generar gráficos de forma transparente.

    Args:
        pregunta: Pregunta en lenguaje natural del usuario.
        pbi_client: Instancia activa de PowerBIClient.

    Returns:
        Respuesta en texto Markdown lista para mostrar en Chainlit.
    """
    try:
        import google.generativeai as genai
    except ImportError:
        return (
            "El paquete `google-generativeai` no está instalado.\n\n"
            "Ejecuta en el entorno virtual:\n```\npip install google-generativeai\n```"
        )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return (
            "Falta `GEMINI_API_KEY` en el archivo `.env`.\n\n"
            "Obtén una clave gratuita en https://aistudio.google.com y añádela:\n"
            "```\nGEMINI_API_KEY=tu_clave_aqui\n```"
        )

    genai.configure(api_key=api_key)

    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    anio_actual = datetime.now().year
    system_with_date = _SYSTEM_PROMPT + f"\nFECHA ACTUAL: {fecha_hoy} (año {anio_actual}).\n"

    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=system_with_date,
        tools=_get_tools(),
    )

    chat = model.start_chat()
    last_dax_query = ""
    max_iterations = 8  # máximo de tool calls para evitar bucles infinitos

    try:
        response = chat.send_message(pregunta)
    except Exception as e:
        logger.error(f"Error iniciando agente Gemini: {e}")
        return f"Error al iniciar el agente: {e}"

    for iteration in range(max_iterations):
        # Extraer function calls de la respuesta
        function_calls = [
            part.function_call
            for part in response.parts
            if hasattr(part, "function_call") and part.function_call.name
        ]

        if not function_calls:
            # Sin más tool calls — el agente terminó
            break

        logger.info(f"Agente PBI iter {iteration + 1}: {[fc.name for fc in function_calls]}")

        # Ejecutar cada tool call y recoger resultados
        tool_responses = []
        for fc in function_calls:
            result_str = _ejecutar_tool(fc.name, dict(fc.args), pregunta, pbi_client)

            # Guardar la última query DAX ejecutada para añadirla a la respuesta
            if fc.name == "ejecutar_dax":
                last_dax_query = dict(fc.args).get("dax", "")

            tool_responses.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=fc.name,
                        response={"result": result_str},
                    )
                )
            )

        try:
            response = chat.send_message(tool_responses)
        except Exception as e:
            logger.error(f"Error en iteración {iteration + 1} del agente: {e}")
            return f"Error en el agente durante la consulta: {e}"

    # Extraer texto final de la respuesta
    texto = _extraer_texto(response)

    # Añadir bloque DAX al final si el agente no lo incluyó ya
    if last_dax_query and "```dax" not in texto and "```DAX" not in texto:
        texto += f"\n\n---\n🔍 *DAX ejecutado:*\n```dax\n{last_dax_query}\n```"

    return texto


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
    if nombre == "consultar_diccionario":
        query = args.get("pregunta", pregunta_original)
        try:
            return pbi_client._get_schema_for_question(query)
        except Exception as e:
            return f"Error consultando diccionario: {e}"

    elif nombre == "ejecutar_dax":
        dax = args.get("dax", "")
        if not dax:
            return "ERROR: No se proporcionó consulta DAX."

        raw = pbi_client.execute_dax(dax)

        if "error" in raw:
            return f"ERROR DAX: {raw['error']}"

        # Importar helpers del cliente original
        from .powerbi_client import _extract_rows, _format_dax_result

        rows = _extract_rows(raw)
        pbi_client._last_query_rows = rows  # expuesto para generación de gráficos en app.py

        if not rows:
            return "_La consulta no devolvió resultados._"

        tabla_md = _format_dax_result(raw)
        return f"{len(rows)} filas devueltas:\n\n{tabla_md}"

    else:
        logger.warning(f"Tool desconocida solicitada por el agente: {nombre}")
        return f"Tool '{nombre}' no disponible."


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _extraer_texto(response) -> str:
    """Extrae el texto final de una respuesta Gemini (maneja múltiples parts)."""
    try:
        return response.text
    except Exception:
        partes = [
            part.text
            for part in response.parts
            if hasattr(part, "text") and part.text
        ]
        return "\n".join(partes) if partes else "_El agente no generó respuesta de texto._"
