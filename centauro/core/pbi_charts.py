"""
Generación automática de gráficos para resultados de consultas Power BI.

Lógica de selección de tipo de gráfico:
- Columna de etiqueta con palabras temporales (mes, año, semana...) → línea
- Resto → barras horizontales si hay muchas etiquetas, verticales si pocas
- Resultado escalar (1 fila) → no se grafica
"""
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Palabras que indican dimensión temporal → gráfico de líneas
_TEMPORAL_KW = [
    "mes", "año", "anio", "ano", "fecha", "semana", "periodo", "ejercicio",
    "trimestre", "año_mes", "ano_mes", "año-mes", "ano-mes", "aaaa",
    "month", "year", "week", "date", "quarter", "sem",
]

# Paleta oscura coherente con el estilo del proyecto
_BG_FIGURE = "#1a1a2e"
_BG_AXES   = "#16213e"
_COLOR_BAR = "#4cc9f0"
_COLOR_LINE = "#f72585"
_COLOR_TEXT = "#e0e0e0"
_COLOR_AXIS = "#888888"


def _clean_col(raw: str) -> str:
    """'[Tabla][Columna]' → 'Columna'."""
    if "][" in raw:
        raw = raw.split("][")[-1].rstrip("]")
    elif raw.startswith("["):
        raw = raw[1:].rstrip("]")
    return raw


def _es_temporal(col_name: str, pregunta: str) -> bool:
    combined = (col_name + " " + pregunta).lower()
    return any(kw in combined for kw in _TEMPORAL_KW)


def _detectar_columnas(rows: list):
    """
    Devuelve (label_idx, value_idx) o (None, None) si no aplica.
    label_idx: índice de la primera columna no-numérica (cadena de texto).
    value_idx: índice de la primera columna numérica.
    """
    raw_cols = list(rows[0].keys())
    label_idx = None
    value_idx = None

    for i, col in enumerate(raw_cols):
        # Tomar una muestra ignorando nulos
        sample = [r[col] for r in rows[:10] if r.get(col) is not None]
        if not sample:
            continue
        es_num = all(isinstance(v, (int, float)) for v in sample)
        if es_num and value_idx is None:
            value_idx = i
        elif not es_num and label_idx is None:
            label_idx = i

    return label_idx, value_idx


def generar_grafico_desde_rows(
    rows: list,
    pregunta: str,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Genera un gráfico PNG a partir de las filas de resultado DAX.

    Args:
        rows: Lista de dicts tal como los devuelve _extract_rows() de powerbi_client.
        pregunta: Pregunta original del usuario (para inferir tipo de gráfico).
        output_dir: Directorio donde guardar el PNG. Si es None, usa tempfile.

    Returns:
        Path al PNG generado, o None si no procede generar gráfico.
    """
    # Necesitamos al menos 2 filas para que tenga sentido un gráfico
    if not rows or len(rows) < 2:
        return None

    try:
        import matplotlib
        matplotlib.use("Agg")          # sin ventana interactiva
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mtick
    except ImportError:
        logger.warning("matplotlib no instalado — ejecuta: pip install matplotlib")
        return None

    raw_cols = list(rows[0].keys())
    clean_cols = [_clean_col(c) for c in raw_cols]

    label_idx, value_idx = _detectar_columnas(rows)
    if label_idx is None or value_idx is None:
        logger.debug("No se encontraron columnas label+value adecuadas para graficar")
        return None

    label_col_raw = raw_cols[label_idx]
    value_col_raw = raw_cols[value_idx]
    label_col_name = clean_cols[label_idx]
    value_col_name = clean_cols[value_idx]

    # Extraer datos, reemplazando nulos por 0
    try:
        labels = [str(r.get(label_col_raw) or "") for r in rows]
        values = [float(r.get(value_col_raw) or 0) for r in rows]
    except (TypeError, ValueError) as e:
        logger.debug(f"Error convirtiendo datos del gráfico: {e}")
        return None

    tipo = "line" if _es_temporal(label_col_name, pregunta) else "bar"
    muchas_etiquetas = len(labels) > 12

    fig, ax = plt.subplots(figsize=(11, 5))
    fig.patch.set_facecolor(_BG_FIGURE)
    ax.set_facecolor(_BG_AXES)

    if tipo == "line":
        ax.plot(range(len(labels)), values,
                color=_COLOR_LINE, linewidth=2.5, marker="o", markersize=5,
                markerfacecolor=_COLOR_LINE, markeredgewidth=0)
        ax.fill_between(range(len(labels)), values, alpha=0.12, color=_COLOR_LINE)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45 if muchas_etiquetas else 0,
                           ha="right" if muchas_etiquetas else "center",
                           fontsize=8, color=_COLOR_TEXT)

    elif muchas_etiquetas:
        # Barras horizontales cuando hay muchas categorías
        y_pos = range(len(labels))
        bars = ax.barh(y_pos, values, color=_COLOR_BAR, edgecolor="none", height=0.6)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=8, color=_COLOR_TEXT)
        ax.invert_yaxis()
        # Valor al lado de cada barra
        for bar, val in zip(bars, values):
            ax.text(bar.get_width() * 1.01, bar.get_y() + bar.get_height() / 2,
                    _fmt_val(val), va="center", fontsize=7.5, color=_COLOR_TEXT)

    else:
        bars = ax.bar(range(len(labels)), values,
                      color=_COLOR_BAR, edgecolor="none", width=0.6)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30 if len(labels) > 6 else 0,
                           ha="right" if len(labels) > 6 else "center",
                           fontsize=9, color=_COLOR_TEXT)
        # Valor encima de cada barra
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.015,
                    _fmt_val(val), ha="center", va="bottom",
                    fontsize=8, color=_COLOR_TEXT)

    # Estilo general
    ax.tick_params(colors=_COLOR_AXIS, labelsize=9)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: _fmt_val(x)))
    ax.set_xlabel(label_col_name if tipo != "line" else "", color=_COLOR_AXIS, fontsize=9)
    ax.set_ylabel(value_col_name, color=_COLOR_AXIS, fontsize=9)
    ax.set_title(
        f"{value_col_name}  ·  por  {label_col_name}",
        color=_COLOR_TEXT, fontsize=11, pad=12, fontweight="bold"
    )
    ax.tick_params(axis="x", colors=_COLOR_AXIS)
    ax.tick_params(axis="y", colors=_COLOR_AXIS)

    plt.tight_layout(pad=1.5)

    # Determinar ruta de salida
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / "pbi_chart_last.png"
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix="pbi_chart_")
        out_path = Path(tmp.name)
        tmp.close()

    fig.savefig(out_path, dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    logger.info(f"Gráfico PBI generado: {out_path} ({len(rows)} filas, tipo={tipo})")
    return out_path


def _fmt_val(v: float) -> str:
    """Formatea un número para mostrar en el gráfico."""
    if v == 0:
        return "0"
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"{v:,.0f}"
    return f"{v:,.1f}" if v != int(v) else f"{int(v):,}"
