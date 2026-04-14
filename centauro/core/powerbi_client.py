"""
PowerBI Client v1.0 - Integración con modelo semántico vía Power BI REST API

Autenticación: MSAL + Device Code Flow (delegado, usuario Planeta)
El refresh token se guarda en .env como PBI_REFRESH_TOKEN.
En runtime se usa el refresh token para obtener access tokens sin interacción.

Variables .env requeridas:
    AZURE_CLIENT_ID       - Client ID de la App Registration en Entra ID
    AZURE_TENANT_ID       - Tenant ID del directorio de Planeta
    AZURE_CLIENT_SECRET   - Client Secret (opcional, mejora seguridad)
    PBI_WORKSPACE_ID      - ID del workspace (Group ID) en Power BI / Fabric
    PBI_DATASET_ID        - ID del dataset / modelo semántico
    PBI_REFRESH_TOKEN     - Generado por scripts/pbi_auth.py (una sola vez)
    PBI_SCHEMA_HINT       - Descripción libre del esquema (tablas, medidas clave)
                           Si está vacío, se auto-descubre vía DAX INFO()
"""
import os
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dotenv import load_dotenv, set_key

load_dotenv()
logger = logging.getLogger(__name__)

PBI_API_BASE = "https://api.powerbi.com/v1.0/myorg"


class PowerBIClient:
    """
    Cliente para consultar el modelo semántico de Power BI (Fabric).

    Flujo en runtime:
      1. get_access_token() → intercambia PBI_REFRESH_TOKEN por access token
      2. execute_dax(query) → POST executeQueries con Bearer token
      3. query_nl(pregunta) → GPT genera DAX → execute_dax → GPT interpreta → respuesta

    El refresh token se rota automáticamente si el servidor devuelve uno nuevo.
    """

    def __init__(self):
        self.client_id = os.getenv("AZURE_CLIENT_ID")
        self.tenant_id = os.getenv("AZURE_TENANT_ID")
        self.client_secret = os.getenv("AZURE_CLIENT_SECRET")
        self.workspace_id = os.getenv("PBI_WORKSPACE_ID")
        self.dataset_id = os.getenv("PBI_DATASET_ID")
        self.schema_hint = os.getenv("PBI_SCHEMA_HINT", "")

        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._schema_cache: Optional[str] = None
        self._query_cache: Dict[str, str] = {}  # caché de resultados por pregunta
        self._last_query_rows: list = []         # filas del último resultado (para gráficos)

        if not self.client_id or not self.tenant_id:
            raise ValueError("Faltan AZURE_CLIENT_ID o AZURE_TENANT_ID en .env")
        if not self.workspace_id or not self.dataset_id:
            raise ValueError("Faltan PBI_WORKSPACE_ID o PBI_DATASET_ID en .env")

    @property
    def disponible(self) -> bool:
        """True si hay refresh token guardado y la config básica está completa."""
        return bool(
            self.client_id and self.tenant_id
            and self.workspace_id and self.dataset_id
            and os.getenv("PBI_REFRESH_TOKEN")
        )

    # ------------------------------------------------------------------
    # Autenticación
    # ------------------------------------------------------------------

    def get_access_token(self) -> str:
        """
        Devuelve un access token válido, renovándolo con el refresh token si hace falta.
        Reutiliza el token en caché mientras queden más de 5 minutos de vida.
        """
        if (
            self._access_token
            and self._token_expiry
            and datetime.now() < self._token_expiry - timedelta(minutes=5)
        ):
            return self._access_token

        refresh_token = os.getenv("PBI_REFRESH_TOKEN")
        if not refresh_token:
            raise RuntimeError(
                "No hay PBI_REFRESH_TOKEN en .env. "
                "Ejecuta `python scripts/pbi_auth.py` para autenticarte."
            )

        token_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        )
        # Cliente público (Allow public client flows activado en Azure):
        # NO se envía client_secret — Azure lo rechaza con AADSTS700025
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": refresh_token,
            "scope": "https://analysis.windows.net/powerbi/api/Dataset.Read.All",
        }

        resp = requests.post(token_url, data=payload, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Error renovando token Power BI [{resp.status_code}]: {resp.text}"
            )

        data = resp.json()
        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._token_expiry = datetime.now() + timedelta(seconds=expires_in)

        # Rotar refresh token si el servidor devuelve uno nuevo
        new_rt = data.get("refresh_token")
        if new_rt and new_rt != refresh_token:
            env_path = _find_env_path()
            set_key(env_path, "PBI_REFRESH_TOKEN", new_rt)
            os.environ["PBI_REFRESH_TOKEN"] = new_rt
            logger.info("Refresh token rotado y guardado en .env")

        return self._access_token

    # ------------------------------------------------------------------
    # Ejecución DAX
    # ------------------------------------------------------------------

    def execute_dax(self, dax_query: str) -> Dict[str, Any]:
        """
        Ejecuta una consulta DAX en el dataset configurado vía REST API.

        Args:
            dax_query: Consulta DAX completa (debe empezar con EVALUATE)

        Returns:
            dict con 'results' (lista de tablas) o 'error' (mensaje de error)
        """
        token = self.get_access_token()
        url = (
            f"{PBI_API_BASE}/groups/{self.workspace_id}"
            f"/datasets/{self.dataset_id}/executeQueries"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {
            "queries": [{"query": dax_query}],
            "serializerSettings": {"includeNulls": True},
        }

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=30)
        except requests.Timeout:
            return {"error": "Timeout: el modelo semántico tardó más de 30 segundos en responder."}
        except requests.RequestException as e:
            return {"error": f"Error de red: {e}"}

        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:500]}"}

        return resp.json()

    # ------------------------------------------------------------------
    # Descubrimiento de esquema
    # ------------------------------------------------------------------

    def _get_schema_for_question(self, pregunta: str) -> str:
        """
        Devuelve contexto del modelo semántico relevante para la pregunta,
        consultando la colección RAG 'diccionario_datos' en ChromaDB.

        Fallback: PBI_SCHEMA_HINT del .env si ChromaDB no tiene datos.
        """
        # Intentar búsqueda RAG en el diccionario de datos
        try:
            from ..rag import collection_diccionario_datos
            n_docs = collection_diccionario_datos.count()
            if n_docs > 0:
                # Recuperar entradas más relevantes para la pregunta
                n_results = min(4, n_docs)
                results = collection_diccionario_datos.query(
                    query_texts=[pregunta],
                    n_results=n_results,
                )
                docs = results.get("documents", [[]])[0]
                if docs:
                    contexto_rag = "\n\n---\n\n".join(docs)
                    logger.info(
                        f"RAG diccionario: {len(docs)} entradas recuperadas para: "
                        f"{pregunta[:60]}..."
                    )
                    return contexto_rag
        except Exception as e:
            logger.warning(f"Error consultando RAG diccionario datos: {e}")

        # Fallback: hint estático del .env
        if self.schema_hint:
            return self.schema_hint

        return "Esquema no disponible. Indexa el diccionario de datos o define PBI_SCHEMA_HINT en .env."

    def discover_columns(self, table_name: str) -> str:
        """
        Devuelve las columnas de una tabla leyendo 1 fila y extrayendo las claves.
        No requiere permisos de admin (no usa INFO.COLUMNS).
        """
        # Probar con el nombre tal cual y en mayúsculas
        for name in [table_name, table_name.upper()]:
            result = self.execute_dax(f"EVALUATE TOPN(1, {name})")
            if "error" not in result:
                rows = _extract_rows(result)
                # Si hay filas, extraer columnas de las claves
                # Si no hay filas, intentar con una tabla vacía igualmente
                try:
                    raw_cols = list(result["results"][0]["tables"][0].get("rows", [{}])[0].keys()) \
                        if rows else []
                    if not raw_cols:
                        # Sin filas: hacer SUMMARIZECOLUMNS para forzar al menos una fila
                        r2 = self.execute_dax(
                            f"EVALUATE SELECTCOLUMNS(TOPN(1,{name}), "
                            + ", ".join([f'"col{i}", [{c}]' for i, c in enumerate(raw_cols)])
                            + ")"
                        )
                except Exception:
                    raw_cols = []

                if not raw_cols:
                    return (
                        f"La tabla `{name}` existe pero no tiene filas o no se pudieron leer columnas.\n"
                        f"Añade las columnas manualmente en `PBI_SCHEMA_HINT`."
                    )

                # Limpiar nombres: "Tabla[Columna]" → "Columna"
                clean = []
                for c in raw_cols:
                    if "[" in c:
                        c = c.split("[")[-1].rstrip("]")
                    clean.append(c)

                lines = [f"**Columnas de `{name}`** ({len(clean)} columnas):\n"]
                lines += [f"- `{c}`" for c in clean]
                lines.append(
                    f"\n💡 Copia esto en `PBI_SCHEMA_HINT`:\n"
                    f"`Tabla: {name} ({', '.join(clean[:15])}{'...' if len(clean)>15 else ''})`"
                )
                return "\n".join(lines)

        return (
            f"No se encontró la tabla `{table_name}`. "
            f"Usa `@pbi schema` para ver los nombres exactos de las tablas."
        )

    # ------------------------------------------------------------------
    # Consulta en lenguaje natural
    # ------------------------------------------------------------------

    def query_nl(self, pregunta: str) -> str:
        """
        Pipeline completo: pregunta en NL → DAX → resultado → respuesta en NL.

        Pasos:
          1. GPT genera la consulta DAX a partir del esquema + pregunta
          2. Se ejecuta el DAX en Power BI
          3. GPT interpreta el resultado y lo convierte en respuesta legible
        """
        import re as _re
        from ..llm_client import consultar_gpt

        # ── Sandbox DAX directo ───────────────────────────────────────────
        # Si el usuario escribe DAX crudo (EVALUATE / DEFINE), lo ejecutamos
        # directamente sin pasar por el paso NL→DAX.
        # Comandos: "@pbi EVALUATE ..." o "@pbi dax: EVALUATE ..."
        pregunta_stripped = pregunta.strip()
        # Limpiar prefijo "dax:" opcional
        _dax_raw = _re.sub(r"^dax\s*:\s*", "", pregunta_stripped, flags=_re.IGNORECASE)
        if _dax_raw.upper().startswith(("EVALUATE", "DEFINE")):
            self._last_query_rows = []
            raw_result = self.execute_dax(_dax_raw)
            if "error" in raw_result:
                return (
                    f"⚠️ **Error ejecutando DAX:**\n```\n{raw_result['error']}\n```\n\n"
                    f"*Consulta enviada:*\n```dax\n{_dax_raw}\n```"
                )
            rows = _extract_rows(raw_result)
            self._last_query_rows = rows
            tabla_md = _format_dax_result(raw_result)
            n = len(rows)
            return (
                f"✅ **DAX ejecutado directamente** — {n} {'fila' if n == 1 else 'filas'}\n\n"
                f"{tabla_md}\n\n"
                f"---\n🔍 *DAX ejecutado:*\n```dax\n{_dax_raw}\n```"
            )

        # Resetear filas anteriores al comienzo de una nueva consulta
        self._last_query_rows = []

        # ── Caché: devolver resultado previo si la pregunta es idéntica ──
        cache_key = pregunta.strip().lower()
        if cache_key in self._query_cache:
            logger.info("Resultado devuelto desde caché")
            return f"*(resultado en caché)*\n\n{self._query_cache[cache_key]}"

        # ── Comandos directos (sin GPT) ──────────────────────────────────
        # @pbi columnas <NombreTabla>
        m = _re.match(r"(?:columnas?|columns?)\s+(\S+)", pregunta.strip(), _re.IGNORECASE)
        if m:
            return self.discover_columns(m.group(1))

        # @pbi schema → muestra el diccionario indexado o el hint
        if pregunta.strip().lower() in ("schema", "esquema", "tablas", "tables"):
            try:
                from ..rag import collection_diccionario_datos
                n = collection_diccionario_datos.count()
                if n > 0:
                    return (
                        f"**Diccionario de datos indexado en RAG:** {n} entradas\n\n"
                        f"Las entradas se recuperan automáticamente según tu pregunta.\n"
                        f"Archivo fuente: `inputs/docs/diccionario_datos/diccionario_modelo_semantico.txt`"
                    )
            except Exception:
                pass
            if self.schema_hint:
                return f"**Schema configurado en PBI_SCHEMA_HINT:**\n\n{self.schema_hint}"
            return (
                "No hay diccionario de datos ni `PBI_SCHEMA_HINT` configurado.\n\n"
                "Usa `@pbi columnas <NombreTabla>` para ver las columnas de una tabla concreta.\n"
                "Ejemplo: `@pbi columnas H_Convocatorio`"
            )

        schema = self._get_schema_for_question(pregunta)

        # Fecha actual para que GPT no invente fechas
        from datetime import datetime as _dt
        fecha_hoy = _dt.now().strftime("%Y-%m-%d")
        anio_actual = _dt.now().year
        mes_actual = _dt.now().strftime("%Y-%m")

        # ── Contexto de negocio ──────────────────────────────────────────
        # Reglas base compactas (siempre incluidas) + contexto dinámico del RAG
        BUSINESS_CONTEXT = f"""CONTEXTO DE NEGOCIO:
FECHA ACTUAL: {fecha_hoy} (año {anio_actual}, mes {mes_actual}). USA SIEMPRE ESTA FECHA como referencia para "hoy", "este mes", "esta semana", "este año". NUNCA uses fechas de tu entrenamiento.
Modelo comercial de venta de programas académicos (másteres, posgrados, formación continua) del Grupo Planeta.
Las medidas calculadas están en la tabla _MEDIDAS. SIEMPRE usar medidas de _MEDIDAS en vez de COUNTROWS directos, especialmente para H_CUPONES (las relaciones de fecha son INACTIVAS y las medidas activan USERELATIONSHIP internamente).

DICCIONARIO DE DATOS (medidas, tablas, relaciones y patrones DAX relevantes para esta pregunta):
{schema}"""

        # ── Paso 1: NL → DAX ────────────────────────────────────────────
        prompt_nl_to_dax = f"""Eres un experto en DAX y modelos semánticos de Power BI.
Tu tarea es convertir preguntas en lenguaje natural en consultas DAX válidas.

{BUSINESS_CONTEXT}

REGLAS:
- Responde ÚNICAMENTE con la consulta DAX, sin explicaciones ni bloques de código markdown.
- La consulta SIEMPRE debe empezar con EVALUATE.
- Usa SUMMARIZECOLUMNS, TOPN, CALCULATE, COUNTROWS, FORMAT según corresponda.
- Usa los nombres exactos de tablas y medidas del esquema.
- Para valores monetarios, usa FORMAT([Medida], "#,0.00").
- Solo responde DAX_NO_POSIBLE si la tabla o medida mencionada NO existe en el esquema.

PATRONES COMUNES (úsalos directamente):
- Contar filas de una tabla:
    EVALUATE ROW("Total filas", COUNTROWS(NombreTabla))
- Contar filas con filtro:
    EVALUATE ROW("Total", COUNTROWS(FILTER(NombreTabla, NombreTabla[Columna] = "Valor")))
- Usar una medida con filtro:
    EVALUATE ROW("Total", CALCULATE([MedidaKPI], Tabla[Columna] = "Valor"))
- Ranking por columna:
    EVALUATE TOPN(10, SUMMARIZECOLUMNS(NombreTabla[Columna], "Total", COUNTROWS(NombreTabla)), [Total], DESC)
- Agrupar por país: usa H_CUPONES[Pais] o H_Convocatorio[PAIS_NORMALIZADO] directamente desde la tabla de hechos. Si necesitas usar D_PAIS, agrupa por D_PAIS[ID_Pais] (es la clave única), NUNCA por D_PAIS[Pais] que tiene valores duplicados.
- Si la pregunta no puede responderse con el esquema, responde exactamente:
  DAX_NO_POSIBLE: <motivo en una línea>"""

        prompt_pregunta = f"""ESQUEMA DEL MODELO SEMÁNTICO:
{schema}

PREGUNTA:
{pregunta}

Genera la consulta DAX:"""

        dax_query = consultar_gpt(
            prompt_nl_to_dax, prompt_pregunta, "pbi_nl_to_dax", force_json=False
        ).strip()

        # Limpiar bloques markdown que GPT pueda añadir
        if "```" in dax_query:
            lines = dax_query.split("\n")
            dax_query = "\n".join(
                l for l in lines if not l.strip().startswith("```")
            ).strip()

        if dax_query.upper().startswith("DAX_NO_POSIBLE"):
            motivo = dax_query.split(":", 1)[-1].strip()
            return (
                f"No puedo responder esa pregunta con el modelo semántico configurado.\n\n"
                f"**Motivo:** {motivo}\n\n"
                f"Si falta contexto de esquema, añade `PBI_SCHEMA_HINT` en `.env` "
                f"con los nombres de tus tablas y medidas."
            )

        # ── Paso 2: Ejecutar DAX (con auto-retry si falla) ───────────────
        raw_result = self.execute_dax(dax_query)

        if "error" in raw_result:
            logger.warning(f"DAX falló en intento 1: {raw_result['error'][:200]}")
            # Auto-retry: devolver el error a GPT para que se corrija
            prompt_retry = f"""La siguiente consulta DAX falló con este error:

ERROR: {raw_result['error']}

CONSULTA QUE FALLÓ:
{dax_query}

Corrige la consulta DAX para resolver el error. Devuelve SOLO la consulta DAX corregida, sin explicaciones."""

            dax_query_v2 = consultar_gpt(
                prompt_nl_to_dax, prompt_retry, "pbi_dax_retry", force_json=False
            ).strip()

            # Limpiar markdown de la versión corregida
            if "```" in dax_query_v2:
                lines = dax_query_v2.split("\n")
                dax_query_v2 = "\n".join(
                    l for l in lines if not l.strip().startswith("```")
                ).strip()

            raw_result = self.execute_dax(dax_query_v2)

            if "error" in raw_result:
                # Ambos intentos fallaron → mostrar error con ambas consultas
                return (
                    f"⚠️ No pude ejecutar la consulta tras 2 intentos.\n\n"
                    f"**Error:** `{raw_result['error'][:300]}`\n\n"
                    f"**Intento 1:**\n```dax\n{dax_query}\n```\n\n"
                    f"**Intento 2 (corregido):**\n```dax\n{dax_query_v2}\n```\n\n"
                    f"💡 Revisa que los nombres de tabla/columna en `PBI_SCHEMA_HINT` sean exactos."
                )

            dax_query = dax_query_v2  # usar la versión corregida para el log

        tabla_md = _format_dax_result(raw_result)
        rows = _extract_rows(raw_result)
        self._last_query_rows = rows  # expuesto para generación de gráficos en app.py

        # ── Caché de consultas (punto 3) ─────────────────────────────────
        self._query_cache[pregunta.strip().lower()] = tabla_md

        # Bloque DAX para mostrar siempre al final (transparencia)
        dax_detalle = f"\n\n---\n🔍 *DAX ejecutado:*\n```dax\n{dax_query}\n```"

        # ── Paso 3: Interpretar resultado ────────────────────────────────
        # Optimización (punto 1): si el resultado es un único valor numérico
        # lo formateamos directamente sin llamar a GPT (ahorra 3-5 seg)
        if len(rows) == 1 and len(rows[0]) == 1:
            val = _first_value(rows[0])
            col = list(rows[0].keys())[0]
            # Limpiar nombre de columna
            if "][" in col:
                col = col.split("][")[-1].rstrip("]")
            elif col.startswith("["):
                col = col[1:].rstrip("]")
            # Formatear número si es numérico
            if isinstance(val, (int, float)):
                val_fmt = f"{val:,.0f}" if isinstance(val, int) or val == int(val) else f"{val:,.2f}"
            else:
                val_fmt = str(val)
            return f"**{col}:** {val_fmt}{dax_detalle}"

        prompt_interpreta = """Eres un analista de datos que presenta resultados de Power BI de forma clara.
Responde la pregunta original del usuario en español, interpretando los datos de la tabla.
- Destaca los valores más relevantes.
- Usa formato markdown (negrita, tablas) si hay múltiples valores.
- Si la tabla está vacía, indícalo claramente.
- Sé conciso pero completo."""

        prompt_datos = f"""PREGUNTA: {pregunta}

DATOS OBTENIDOS DEL MODELO SEMÁNTICO:
{tabla_md}

Responde la pregunta interpretando estos datos:"""

        interpretacion = consultar_gpt(
            prompt_interpreta, prompt_datos, "pbi_interpret_result", force_json=False
        )
        return f"{interpretacion}{dax_detalle}"


# ------------------------------------------------------------------
# Helpers internos
# ------------------------------------------------------------------

def _extract_rows(api_response: dict) -> list:
    """Extrae las filas del primer resultado de executeQueries."""
    try:
        return api_response["results"][0]["tables"][0].get("rows", [])
    except (KeyError, IndexError):
        return []


def _first_value(row: dict):
    """Devuelve el primer valor de una fila de resultado DAX."""
    for v in row.values():
        return v
    return None


def _format_dax_result(api_response: dict) -> str:
    """Convierte la respuesta JSON de executeQueries a tabla Markdown."""
    try:
        rows = _extract_rows(api_response)
        if not rows:
            return "_La consulta no devolvió resultados._"

        # Limpiar nombres de columna: "[Tabla][Columna]" → "Columna"
        raw_cols = list(rows[0].keys())
        clean_cols = []
        for c in raw_cols:
            if "][" in c:
                c = c.split("][")[-1].rstrip("]")
            elif c.startswith("["):
                c = c[1:].rstrip("]")
            clean_cols.append(c)

        header = " | ".join(clean_cols)
        sep = " | ".join(["---"] * len(clean_cols))
        data_lines = []
        for row in rows[:100]:
            vals = []
            for v in row.values():
                if v is None:
                    vals.append("—")
                elif isinstance(v, float):
                    vals.append(f"{v:,.2f}" if v != int(v) else f"{int(v):,}")
                else:
                    vals.append(str(v))
            data_lines.append(" | ".join(vals))

        result = f"| {header} |\n| {sep} |\n"
        result += "\n".join(f"| {l} |" for l in data_lines)

        if len(rows) > 100:
            result += f"\n\n_(Mostrando 100 de {len(rows)} filas)_"

        return result

    except Exception as e:
        return f"_(Error formateando resultado: {e})_"


def _find_env_path() -> str:
    """Busca el .env en el directorio raíz del proyecto."""
    here = os.path.dirname(__file__)
    # core/ → centauro/ → raíz
    candidate = os.path.normpath(os.path.join(here, "..", "..", ".env"))
    if os.path.exists(candidate):
        return candidate
    return ".env"


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_pbi_client: Optional[PowerBIClient] = None


def get_powerbi_client() -> Optional[PowerBIClient]:
    """
    Devuelve el cliente Power BI singleton.
    Retorna None (sin lanzar excepción) si Power BI no está configurado.
    """
    global _pbi_client
    if _pbi_client is None:
        try:
            _pbi_client = PowerBIClient()
        except ValueError as e:
            logger.debug(f"PowerBI no configurado: {e}")
            return None
    return _pbi_client
