"""
Mapeo entre carpetas de buenas prácticas y agentes evaluadores.

Este archivo define EXPLÍCITAMENTE qué carpeta corresponde a qué agente,
asegurando que los ejemplos se usen en el contexto correcto.
"""

# Mapeo oficial: carpeta → nombre de bloque del agente
MAPEO_CARPETA_A_AGENTE = {
    "investigacion": "Investigación",
    "admision_economica": "Admisión y propuesta económica",
    "objeciones": "Manejo de objeciones",
    "cierre_proximos_pasos": "Cierre y próximos pasos",
    "propuesta_valor": "Propuesta de valor",
    "estilo_comunicacion": "Estilo y comunicación"
}

# Mapeo inverso: nombre de bloque → carpeta
MAPEO_AGENTE_A_CARPETA = {v: k for k, v in MAPEO_CARPETA_A_AGENTE.items()}

# Alias para soportar variaciones en nombres
ALIAS_BLOQUES = {
    # Si un agente se llama ligeramente diferente
    "Admisión y económica": "Admisión y propuesta económica",
    "Admision economica": "Admisión y propuesta económica",
    "Propuesta económica": "Admisión y propuesta económica",

    "Objeciones": "Manejo de objeciones",
    "Manejo objeciones": "Manejo de objeciones",

    "Cierre": "Cierre y próximos pasos",
    "Proximos pasos": "Cierre y próximos pasos",
    "Próximos pasos": "Cierre y próximos pasos",

    "Propuesta de valor institución": "Propuesta de valor",
    "Propuesta de valor programa": "Propuesta de valor",
    "Presentación programa": "Propuesta de valor",

    "Estilo": "Estilo y comunicación",
    "Comunicación": "Estilo y comunicación",
}

def obtener_carpeta_para_agente(nombre_bloque: str) -> str:
    """
    Obtiene el nombre de carpeta correcto para un agente.

    Args:
        nombre_bloque: Nombre del bloque del agente (ej: "Investigación")

    Returns:
        Nombre de carpeta (ej: "investigacion")

    Raises:
        ValueError: Si el nombre del bloque no está mapeado
    """
    # Normalizar: resolver alias primero
    nombre_normalizado = ALIAS_BLOQUES.get(nombre_bloque, nombre_bloque)

    # Buscar carpeta
    carpeta = MAPEO_AGENTE_A_CARPETA.get(nombre_normalizado)

    if not carpeta:
        raise ValueError(
            f"Bloque '{nombre_bloque}' no tiene carpeta mapeada. "
            f"Bloques válidos: {list(MAPEO_AGENTE_A_CARPETA.keys())}"
        )

    return carpeta

def obtener_agente_para_carpeta(nombre_carpeta: str) -> str:
    """
    Obtiene el nombre del bloque del agente para una carpeta.

    Args:
        nombre_carpeta: Nombre de carpeta (ej: "investigacion")

    Returns:
        Nombre del bloque (ej: "Investigación")

    Raises:
        ValueError: Si la carpeta no está mapeada
    """
    agente = MAPEO_CARPETA_A_AGENTE.get(nombre_carpeta)

    if not agente:
        raise ValueError(
            f"Carpeta '{nombre_carpeta}' no está mapeada a ningún agente. "
            f"Carpetas válidas: {list(MAPEO_CARPETA_A_AGENTE.keys())}"
        )

    return agente

def validar_estructura_carpetas(ruta_base):
    """
    Valida que existan todas las carpetas necesarias.

    Args:
        ruta_base: Path a inputs/buenas_practicas/

    Returns:
        Tuple (bool, List[str]): (todas_ok, carpetas_faltantes)
    """
    from pathlib import Path

    ruta = Path(ruta_base)
    carpetas_faltantes = []

    for carpeta in MAPEO_CARPETA_A_AGENTE.keys():
        ruta_carpeta = ruta / carpeta
        if not ruta_carpeta.exists():
            carpetas_faltantes.append(carpeta)

    return len(carpetas_faltantes) == 0, carpetas_faltantes

def crear_carpetas_faltantes(ruta_base):
    """
    Crea todas las carpetas necesarias si no existen.

    Args:
        ruta_base: Path a inputs/buenas_practicas/
    """
    from pathlib import Path

    ruta = Path(ruta_base)
    ruta.mkdir(parents=True, exist_ok=True)

    for carpeta, bloque in MAPEO_CARPETA_A_AGENTE.items():
        ruta_carpeta = ruta / carpeta
        ruta_carpeta.mkdir(exist_ok=True)

        # Crear archivo README en cada carpeta
        readme = ruta_carpeta / "README.md"
        if not readme.exists():
            with open(readme, 'w', encoding='utf-8') as f:
                f.write(f"# {bloque}\n\n")
                f.write(f"Coloca aquí archivos .vtt con ejemplos de buenas prácticas para: **{bloque}**\n\n")
                f.write("Los ejemplos deben:\n")
                f.write("- ✓ Haber obtenido 5/5 en evaluaciones previas\n")
                f.write("- ✓ Mostrar técnicas específicas y replicables\n")
                f.write("- ✓ Ser conversaciones reales de 5-15 minutos\n")

# Para debugging
if __name__ == "__main__":
    print("=== MAPEO DE SECCIONES ===\n")
    print("Carpeta -> Agente:")
    for carpeta, agente in MAPEO_CARPETA_A_AGENTE.items():
        print(f"  {carpeta:25} -> {agente}")

    print("\n\nAgente -> Carpeta:")
    for agente, carpeta in MAPEO_AGENTE_A_CARPETA.items():
        print(f"  {agente:35} -> {carpeta}")

    print("\n\nAlias soportados:")
    for alias, oficial in ALIAS_BLOQUES.items():
        carpeta = MAPEO_AGENTE_A_CARPETA[oficial]
        print(f"  '{alias}' -> '{oficial}' -> {carpeta}")
