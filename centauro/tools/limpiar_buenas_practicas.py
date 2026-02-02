"""
SCRIPT: limpiar_buenas_practicas.py
=====================================

DESCRIPCIÓN:
    Este script limpia y organiza los archivos de ejemplos de buenas prácticas
    para optimizar su uso en el sistema RAG de Centauro.

FUNCIONES:
    1. Elimina la sección "--- CONVERSACIÓN COMPLETA ---" de cada archivo
       (esta transcripción entera añade ruido al RAG y no es necesaria)

    2. Renombra archivos con formato consistente:
       {seccion}_ejemplo_{numero:03d}.txt
       Ejemplo: investigacion_ejemplo_001.txt

    3. Elimina archivos duplicados (detecta por contenido similar)

    4. Genera un reporte de los cambios realizados

ESTRUCTURA ESPERADA:
    inputs/docs/buenas_practicas/
    ├── investigacion/
    ├── propuesta_valor/
    ├── admision_economica/
    ├── cierre/
    └── objeciones/

USO:
    python tools/limpiar_buenas_practicas.py

    Opciones:
        --dry-run    Muestra los cambios sin ejecutarlos
        --verbose    Muestra información detallada

AUTOR: Centauro Team
FECHA: 2025-01
"""

import os
import re
import hashlib
from pathlib import Path
from collections import defaultdict
import argparse
import shutil

# Configuración
BASE_DIR = Path(__file__).parent.parent
BUENAS_PRACTICAS_DIR = BASE_DIR / "inputs" / "docs" / "buenas_practicas"
BACKUP_DIR = BASE_DIR / "inputs" / "docs" / "buenas_practicas_backup"

# Mapeo de nombres de carpeta a prefijo de archivo
SECCION_PREFIJOS = {
    "investigacion": "investigacion",
    "propuesta_valor": "propuesta_valor",
    "admision_economica": "admision_economica",
    "cierre": "cierre_proximos_pasos",
    "objeciones": "objeciones"
}


def calcular_hash_contenido(contenido: str) -> str:
    """Calcula hash MD5 del contenido limpio (sin espacios extras)."""
    contenido_normalizado = re.sub(r'\s+', ' ', contenido.strip().lower())
    return hashlib.md5(contenido_normalizado.encode()).hexdigest()[:16]


def limpiar_contenido(contenido: str) -> str:
    """
    Elimina la sección '--- CONVERSACIÓN COMPLETA ---' y todo lo que sigue.
    Mantiene solo los metadatos útiles para el RAG.
    """
    # Buscar el marcador de conversación completa
    marcadores = [
        "--- CONVERSACIÓN COMPLETA ---",
        "---CONVERSACIÓN COMPLETA---",
        "--- CONVERSACION COMPLETA ---",
        "---CONVERSACION COMPLETA---",
        "=== CONVERSACIÓN COMPLETA ===",
        "=== CONVERSACION COMPLETA ==="
    ]

    contenido_limpio = contenido

    for marcador in marcadores:
        if marcador in contenido_limpio:
            # Cortar todo desde el marcador
            idx = contenido_limpio.find(marcador)
            contenido_limpio = contenido_limpio[:idx].strip()
            break

    # Asegurar que termina con salto de línea
    if contenido_limpio and not contenido_limpio.endswith('\n'):
        contenido_limpio += '\n'

    return contenido_limpio


def extraer_seccion_de_contenido(contenido: str) -> str:
    """Intenta extraer la sección del encabezado del archivo."""
    match = re.search(r'EJEMPLO DE BUENA PRÁCTICA:\s*(\w+(?:\s+\w+)*)', contenido, re.IGNORECASE)
    if match:
        seccion = match.group(1).lower().strip()
        # Normalizar nombres
        if "investigacion" in seccion or "investigación" in seccion:
            return "investigacion"
        elif "propuesta" in seccion and "valor" in seccion:
            return "propuesta_valor"
        elif "admision" in seccion or "admisión" in seccion or "economica" in seccion or "económica" in seccion:
            return "admision_economica"
        elif "cierre" in seccion:
            return "cierre"
        elif "objeciones" in seccion or "objecion" in seccion:
            return "objeciones"
    return None


def procesar_carpeta(carpeta: Path, prefijo: str, dry_run: bool = False, verbose: bool = False) -> dict:
    """
    Procesa todos los archivos de una carpeta.

    Returns:
        dict con estadísticas: archivos_procesados, eliminados, renombrados, bytes_ahorrados
    """
    stats = {
        "archivos_procesados": 0,
        "archivos_limpiados": 0,
        "archivos_renombrados": 0,
        "duplicados_eliminados": 0,
        "bytes_antes": 0,
        "bytes_despues": 0
    }

    if not carpeta.exists():
        print(f"  ⚠️  Carpeta no existe: {carpeta}")
        return stats

    archivos = list(carpeta.glob("*.txt"))
    if not archivos:
        print(f"  ℹ️  Sin archivos .txt en: {carpeta.name}")
        return stats

    # Detectar duplicados por hash de contenido útil
    hash_to_files = defaultdict(list)
    archivos_limpios = {}

    for archivo in archivos:
        try:
            contenido_original = archivo.read_text(encoding='utf-8')
            stats["bytes_antes"] += len(contenido_original.encode('utf-8'))

            contenido_limpio = limpiar_contenido(contenido_original)
            hash_contenido = calcular_hash_contenido(contenido_limpio)

            hash_to_files[hash_contenido].append(archivo)
            archivos_limpios[archivo] = contenido_limpio

        except Exception as e:
            print(f"  ❌ Error leyendo {archivo.name}: {e}")

    # Procesar: mantener uno de cada duplicado, renombrar con formato consistente
    contador = 1
    archivos_a_mantener = []
    archivos_a_eliminar = []

    for hash_val, archivos_dup in hash_to_files.items():
        # Si hay duplicados, mantener el que tiene nombre más limpio o el primero
        archivos_ordenados = sorted(archivos_dup, key=lambda x: (
            0 if re.match(r'^[a-z_]+_ejemplo_\d+\.txt$', x.name) else 1,
            len(x.name)
        ))

        archivos_a_mantener.append(archivos_ordenados[0])
        archivos_a_eliminar.extend(archivos_ordenados[1:])

    # Eliminar duplicados
    for archivo in archivos_a_eliminar:
        stats["duplicados_eliminados"] += 1
        if verbose:
            print(f"    🗑️  Duplicado: {archivo.name}")
        if not dry_run:
            archivo.unlink()

    # Renombrar y limpiar archivos restantes
    for archivo in sorted(archivos_a_mantener, key=lambda x: x.name):
        stats["archivos_procesados"] += 1
        contenido_limpio = archivos_limpios[archivo]

        # Verificar si necesita limpieza
        contenido_original = archivo.read_text(encoding='utf-8') if archivo.exists() else ""
        necesita_limpieza = len(contenido_limpio) < len(contenido_original) * 0.95

        # Generar nuevo nombre
        nuevo_nombre = f"{prefijo}_ejemplo_{contador:03d}.txt"
        nuevo_path = carpeta / nuevo_nombre

        necesita_renombrar = archivo.name != nuevo_nombre

        if verbose:
            if necesita_limpieza:
                ahorro = len(contenido_original) - len(contenido_limpio)
                print(f"    ✂️  Limpiando: {archivo.name} (-{ahorro:,} bytes)")
            if necesita_renombrar:
                print(f"    📝 Renombrar: {archivo.name} → {nuevo_nombre}")

        if not dry_run:
            # Escribir contenido limpio
            if necesita_limpieza:
                archivo.write_text(contenido_limpio, encoding='utf-8')
                stats["archivos_limpiados"] += 1

            # Renombrar si es necesario
            if necesita_renombrar and archivo.exists():
                # Si el destino ya existe y es diferente, eliminar origen
                if nuevo_path.exists() and nuevo_path != archivo:
                    archivo.unlink()
                else:
                    archivo.rename(nuevo_path)
                stats["archivos_renombrados"] += 1

        stats["bytes_despues"] += len(contenido_limpio.encode('utf-8'))
        contador += 1

    return stats


def crear_backup(dry_run: bool = False, verbose: bool = False):
    """Crea una copia de seguridad antes de modificar."""
    if BACKUP_DIR.exists():
        if verbose:
            print(f"ℹ️  Backup existente en: {BACKUP_DIR}")
        return True

    if not dry_run:
        try:
            # Usar ignore_errors para saltar archivos problemáticos (nombres muy largos en Windows)
            def ignorar_errores(func, path, exc_info):
                print(f"  ⚠️  No se pudo copiar (nombre muy largo): {Path(path).name[:50]}...")

            shutil.copytree(BUENAS_PRACTICAS_DIR, BACKUP_DIR, ignore_dangling_symlinks=True)
            print(f"✅ Backup creado en: {BACKUP_DIR}")
        except shutil.Error as e:
            # Intentar backup manual solo de archivos que se pueden copiar
            print(f"⚠️  Backup parcial (algunos archivos tienen nombres muy largos para Windows)")
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            for subcarpeta in SECCION_PREFIJOS.keys():
                src = BUENAS_PRACTICAS_DIR / subcarpeta
                dst = BACKUP_DIR / subcarpeta
                if src.exists():
                    dst.mkdir(exist_ok=True)
                    for archivo in src.glob("*.txt"):
                        try:
                            shutil.copy2(archivo, dst / archivo.name)
                        except OSError:
                            print(f"  ⚠️  Saltando: {archivo.name[:40]}...")
            print(f"✅ Backup parcial creado en: {BACKUP_DIR}")
    else:
        print(f"🔍 [DRY-RUN] Se crearía backup en: {BACKUP_DIR}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Limpia y organiza archivos de buenas prácticas para RAG"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra los cambios sin ejecutarlos"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Muestra información detallada"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="No crear backup (usar con precaución)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("🧹 LIMPIADOR DE BUENAS PRÁCTICAS - Centauro")
    print("=" * 60)

    if args.dry_run:
        print("🔍 MODO DRY-RUN: No se realizarán cambios\n")

    # Verificar que existe la carpeta
    if not BUENAS_PRACTICAS_DIR.exists():
        print(f"❌ No se encontró la carpeta: {BUENAS_PRACTICAS_DIR}")
        return

    # Crear backup
    if not args.no_backup:
        crear_backup(args.dry_run, args.verbose)

    # Estadísticas globales
    stats_total = {
        "archivos_procesados": 0,
        "archivos_limpiados": 0,
        "archivos_renombrados": 0,
        "duplicados_eliminados": 0,
        "bytes_antes": 0,
        "bytes_despues": 0
    }

    # Procesar cada subcarpeta
    print(f"\n📂 Procesando: {BUENAS_PRACTICAS_DIR}\n")

    for carpeta_nombre, prefijo in SECCION_PREFIJOS.items():
        carpeta_path = BUENAS_PRACTICAS_DIR / carpeta_nombre
        print(f"📁 {carpeta_nombre}/")

        stats = procesar_carpeta(
            carpeta_path,
            prefijo,
            dry_run=args.dry_run,
            verbose=args.verbose
        )

        # Acumular estadísticas
        for key in stats_total:
            stats_total[key] += stats[key]

        if stats["archivos_procesados"] > 0:
            print(f"   └─ {stats['archivos_procesados']} archivos procesados")

    # Resumen final
    print("\n" + "=" * 60)
    print("📊 RESUMEN")
    print("=" * 60)
    print(f"  Archivos procesados:    {stats_total['archivos_procesados']}")
    print(f"  Archivos limpiados:     {stats_total['archivos_limpiados']}")
    print(f"  Archivos renombrados:   {stats_total['archivos_renombrados']}")
    print(f"  Duplicados eliminados:  {stats_total['duplicados_eliminados']}")

    if stats_total['bytes_antes'] > 0:
        ahorro = stats_total['bytes_antes'] - stats_total['bytes_despues']
        porcentaje = (ahorro / stats_total['bytes_antes']) * 100
        print(f"\n  Tamaño antes:  {stats_total['bytes_antes']:,} bytes")
        print(f"  Tamaño después: {stats_total['bytes_despues']:,} bytes")
        print(f"  Ahorro:        {ahorro:,} bytes ({porcentaje:.1f}%)")

    if args.dry_run:
        print("\n🔍 Esto fue un DRY-RUN. Ejecuta sin --dry-run para aplicar cambios.")
    else:
        print("\n✅ Limpieza completada.")
        print("💡 Recuerda re-indexar la colección de buenas_practicas en ChromaDB.")


if __name__ == "__main__":
    # Configurar codificación UTF-8 para Windows
    import sys
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
    main()
