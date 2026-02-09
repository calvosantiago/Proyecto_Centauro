"""
SCRIPT: evaluar_rendimiento.py
===============================

DESCRIPCIÓN:
    Herramienta para evaluar el rendimiento del sistema Centauro en dos dimensiones:

    1. BENCHMARK MANUAL: Compara evaluaciones de Centauro vs criterio humano experto
    2. TEST RAG: Verifica que las búsquedas devuelven contenido relevante

USO:
    python -m centauro.tools.evaluar_rendimiento --test-rag
    python -m centauro.tools.evaluar_rendimiento --benchmark
    python -m centauro.tools.evaluar_rendimiento --all

AUTOR: Centauro Team
FECHA: 2025-02
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# Configurar path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from centauro.config import settings, centauro_config


# ============================================================
# TEST RAG - Verificar calidad de búsquedas
# ============================================================

def test_rag_buenas_practicas():
    """
    Prueba la búsqueda en la colección de buenas prácticas.
    Verifica que devuelve contenido relevante por sección.
    """
    from centauro.core.rag_dynamic import buscar_contexto_dinamico

    print("\n" + "="*70)
    print("🔍 TEST RAG: BUENAS PRÁCTICAS")
    print("="*70)

    # Consultas de prueba por sección
    consultas_test = {
        "Investigación": [
            "cómo hacer preguntas abiertas para conocer al lead",
            "técnicas de escucha activa en ventas",
            "explorar objetivos profesionales del alumno"
        ],
        "Propuesta de valor": [
            "cómo presentar beneficios del máster",
            "conectar programa con objetivos del alumno",
            "diferenciación frente a competencia"
        ],
        "Admisión y propuesta económica": [
            "cómo presentar el precio y financiación",
            "manejar objeciones sobre el costo",
            "explicar proceso de admisión"
        ],
        "Cierre y próximos pasos": [
            "técnicas de cierre de ventas",
            "definir próximos pasos concretos",
            "generar compromiso del alumno"
        ],
        "Objeciones": [
            "manejar objeción de precio alto",
            "responder a necesito pensarlo",
            "objeción de falta de tiempo"
        ]
    }

    resultados = {}
    total_consultas = 0
    consultas_con_resultado = 0

    for seccion, consultas in consultas_test.items():
        print(f"\n📁 Sección: {seccion}")
        print("-" * 50)

        resultados[seccion] = []

        for consulta in consultas:
            total_consultas += 1

            # Buscar con filtro de sección
            try:
                docs = buscar_contexto_dinamico(
                    query=consulta,
                    collection_name=centauro_config.COLLECTION_BUENAS_PRACTICAS,
                    k=2,
                    filtro_seccion=seccion
                )

                tiene_resultados = len(docs) > 0
                if tiene_resultados:
                    consultas_con_resultado += 1

                # Mostrar resultado resumido
                status = "✅" if tiene_resultados else "❌"
                print(f"  {status} \"{consulta[:40]}...\"")

                if tiene_resultados and docs[0].get('documento'):
                    preview = docs[0]['documento'][:100].replace('\n', ' ')
                    print(f"      → {preview}...")

                resultados[seccion].append({
                    "consulta": consulta,
                    "encontrado": tiene_resultados,
                    "num_resultados": len(docs),
                    "relevancia_estimada": "alta" if tiene_resultados else "ninguna"
                })

            except Exception as e:
                print(f"  ❌ Error: {e}")
                resultados[seccion].append({
                    "consulta": consulta,
                    "error": str(e)
                })

    # Resumen
    tasa_exito = (consultas_con_resultado / total_consultas * 100) if total_consultas > 0 else 0

    print("\n" + "="*70)
    print("📊 RESUMEN TEST RAG BUENAS PRÁCTICAS")
    print("="*70)
    print(f"  Total consultas: {total_consultas}")
    print(f"  Con resultados:  {consultas_con_resultado}")
    print(f"  Tasa de éxito:   {tasa_exito:.1f}%")

    return resultados, tasa_exito


def test_rag_coaching():
    """
    Prueba la búsqueda en la colección de coaching/libros de ventas.
    """
    from centauro.core.rag_dynamic import buscar_contexto_dinamico

    print("\n" + "="*70)
    print("🔍 TEST RAG: COACHING (Libros de Ventas)")
    print("="*70)

    consultas_test = [
        "técnicas de persuasión de Cialdini",
        "principio de reciprocidad en ventas",
        "cómo generar compromiso del cliente",
        "autoridad y credibilidad en ventas",
        "escasez y urgencia como técnica de cierre",
        "prueba social para convencer",
        "pre-suasión preparar al cliente"
    ]

    resultados = []
    consultas_con_resultado = 0

    for consulta in consultas_test:
        try:
            docs = buscar_contexto_dinamico(
                query=consulta,
                collection_name=centauro_config.COLLECTION_COACHING,
                k=2
            )

            tiene_resultados = len(docs) > 0
            if tiene_resultados:
                consultas_con_resultado += 1

            status = "✅" if tiene_resultados else "❌"
            print(f"  {status} \"{consulta}\"")

            if tiene_resultados and docs[0].get('documento'):
                preview = docs[0]['documento'][:100].replace('\n', ' ')
                print(f"      → {preview}...")

            resultados.append({
                "consulta": consulta,
                "encontrado": tiene_resultados,
                "num_resultados": len(docs)
            })

        except Exception as e:
            print(f"  ❌ Error: {e}")

    tasa_exito = (consultas_con_resultado / len(consultas_test) * 100)

    print(f"\n  Tasa de éxito: {tasa_exito:.1f}%")

    return resultados, tasa_exito


def test_rag_manuales():
    """
    Prueba la búsqueda en la colección de manuales.
    """
    from centauro.core.rag_dynamic import buscar_contexto_dinamico

    print("\n" + "="*70)
    print("🔍 TEST RAG: MANUALES OBS")
    print("="*70)

    consultas_test = [
        "criterios de evaluación fase investigación",
        "qué evaluar en propuesta de valor",
        "rúbrica de puntuación del asesor",
        "cómo manejar objeciones según manual",
        "proceso de cierre de ventas OBS"
    ]

    resultados = []
    consultas_con_resultado = 0

    for consulta in consultas_test:
        try:
            docs = buscar_contexto_dinamico(
                query=consulta,
                collection_name=centauro_config.COLLECTION_MANUALES,
                k=2
            )

            tiene_resultados = len(docs) > 0
            if tiene_resultados:
                consultas_con_resultado += 1

            status = "✅" if tiene_resultados else "❌"
            print(f"  {status} \"{consulta}\"")

            resultados.append({
                "consulta": consulta,
                "encontrado": tiene_resultados,
                "num_resultados": len(docs)
            })

        except Exception as e:
            print(f"  ❌ Error: {e}")

    tasa_exito = (consultas_con_resultado / len(consultas_test) * 100)

    print(f"\n  Tasa de éxito: {tasa_exito:.1f}%")

    return resultados, tasa_exito


# ============================================================
# BENCHMARK MANUAL - Comparar con evaluación humana
# ============================================================

def crear_plantilla_benchmark():
    """
    Crea una plantilla JSON para que el experto registre sus evaluaciones.
    """
    plantilla = {
        "instrucciones": """
INSTRUCCIONES PARA BENCHMARK MANUAL
====================================

1. Selecciona 5-10 transcripciones de llamadas variadas (buenas, regulares, malas)
2. Evalúa cada una manualmente según los criterios de OBS (1-5)
3. Registra tus notas en la sección 'evaluaciones_humano'
4. Ejecuta Centauro sobre las mismas llamadas
5. Registra las notas de Centauro en 'evaluaciones_centauro'
6. Ejecuta el análisis de comparación

CRITERIOS DE EVALUACIÓN (1-5):
- 1: Muy deficiente
- 2: Deficiente
- 3: Aceptable
- 4: Bueno
- 5: Excelente
        """,
        "fecha_creacion": datetime.now().isoformat(),
        "evaluaciones": [
            {
                "id": "llamada_001",
                "archivo": "nombre_del_archivo.txt",
                "descripcion": "Breve descripción de la llamada",
                "evaluacion_humano": {
                    "Investigación": None,
                    "Propuesta de valor": None,
                    "Admisión y propuesta económica": None,
                    "Cierre y próximos pasos": None,
                    "Objeciones": None,
                    "Estilo comunicativo": None,
                    "nota_global": None,
                    "comentarios": ""
                },
                "evaluacion_centauro": {
                    "Investigación": None,
                    "Propuesta de valor": None,
                    "Admisión y propuesta económica": None,
                    "Cierre y próximos pasos": None,
                    "Objeciones": None,
                    "Estilo comunicativo": None,
                    "nota_global": None
                }
            }
        ]
    }

    # Guardar plantilla
    output_path = settings.OUTPUTS_DIR / "benchmark" / "plantilla_benchmark.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(plantilla, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Plantilla creada en: {output_path}")
    print("\nPasos siguientes:")
    print("1. Abre el archivo JSON y añade más entradas según necesites")
    print("2. Evalúa las llamadas manualmente y registra en 'evaluacion_humano'")
    print("3. Procesa con Centauro y registra en 'evaluacion_centauro'")
    print("4. Ejecuta: python -m centauro.tools.evaluar_rendimiento --analizar-benchmark")

    return output_path


def analizar_benchmark(benchmark_path: Optional[str] = None):
    """
    Analiza los resultados del benchmark comparando humano vs Centauro.
    """
    if benchmark_path is None:
        benchmark_path = settings.OUTPUTS_DIR / "benchmark" / "plantilla_benchmark.json"

    benchmark_path = Path(benchmark_path)

    if not benchmark_path.exists():
        print(f"❌ No se encontró el archivo: {benchmark_path}")
        print("   Ejecuta primero: --crear-plantilla-benchmark")
        return

    with open(benchmark_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("\n" + "="*70)
    print("📊 ANÁLISIS DE BENCHMARK: CENTAURO vs EXPERTO HUMANO")
    print("="*70)

    secciones = [
        "Investigación", "Propuesta de valor", "Admisión y propuesta económica",
        "Cierre y próximos pasos", "Objeciones", "Estilo comunicativo"
    ]

    diferencias_por_seccion = {s: [] for s in secciones}
    diferencias_globales = []

    evaluaciones_completas = 0

    for eval_item in data.get("evaluaciones", []):
        humano = eval_item.get("evaluacion_humano", {})
        centauro = eval_item.get("evaluacion_centauro", {})

        # Verificar que ambas evaluaciones están completas
        if humano.get("nota_global") is None or centauro.get("nota_global") is None:
            continue

        evaluaciones_completas += 1

        # Calcular diferencias por sección
        for seccion in secciones:
            nota_h = humano.get(seccion)
            nota_c = centauro.get(seccion)

            if nota_h is not None and nota_c is not None:
                diff = nota_c - nota_h
                diferencias_por_seccion[seccion].append(diff)

        # Diferencia global
        diff_global = centauro["nota_global"] - humano["nota_global"]
        diferencias_globales.append(diff_global)

        print(f"\n📄 {eval_item.get('archivo', eval_item['id'])}")
        print(f"   Humano: {humano['nota_global']:.1f} | Centauro: {centauro['nota_global']:.1f} | Diff: {diff_global:+.2f}")

    if evaluaciones_completas == 0:
        print("\n⚠️ No hay evaluaciones completas para analizar.")
        print("   Completa las evaluaciones en el archivo JSON.")
        return

    # Estadísticas
    print("\n" + "-"*70)
    print("📈 ESTADÍSTICAS POR SECCIÓN")
    print("-"*70)

    for seccion, diffs in diferencias_por_seccion.items():
        if diffs:
            media = sum(diffs) / len(diffs)
            abs_media = sum(abs(d) for d in diffs) / len(diffs)
            print(f"  {seccion:35} | Sesgo: {media:+.2f} | Error medio: {abs_media:.2f}")

    # Resumen global
    if diferencias_globales:
        media_global = sum(diferencias_globales) / len(diferencias_globales)
        error_medio_global = sum(abs(d) for d in diferencias_globales) / len(diferencias_globales)
        max_error = max(abs(d) for d in diferencias_globales)

        print("\n" + "-"*70)
        print("📊 RESUMEN GLOBAL")
        print("-"*70)
        print(f"  Evaluaciones analizadas: {evaluaciones_completas}")
        print(f"  Sesgo medio (Centauro - Humano): {media_global:+.2f}")
        print(f"  Error absoluto medio: {error_medio_global:.2f}")
        print(f"  Error máximo: {max_error:.2f}")

        # Interpretación
        print("\n💡 INTERPRETACIÓN:")
        if abs(media_global) < 0.3:
            print("  ✅ Sesgo bajo - Centauro no sobrevalora ni infravalora sistemáticamente")
        elif media_global > 0.3:
            print("  ⚠️ Centauro tiende a SOBREVALOR las llamadas")
        else:
            print("  ⚠️ Centauro tiende a INFRAVALOR las llamadas")

        if error_medio_global < 0.5:
            print("  ✅ Error bajo - Las notas son consistentes con el criterio humano")
        elif error_medio_global < 1.0:
            print("  ⚠️ Error moderado - Hay margen de mejora en la calibración")
        else:
            print("  ❌ Error alto - Revisar criterios de evaluación")


# ============================================================
# RESUMEN DE ESTADO DEL SISTEMA
# ============================================================

def mostrar_estado_sistema():
    """
    Muestra el estado actual del sistema RAG.
    """
    from centauro.rag import (
        collection_manuales, collection_buenas_practicas,
        collection_coaching, collection_evaluaciones, collection_dossiers
    )

    print("\n" + "="*70)
    print("📊 ESTADO DEL SISTEMA RAG")
    print("="*70)

    colecciones = [
        ("Manuales generales", collection_manuales),
        ("Buenas prácticas", collection_buenas_practicas),
        ("Coaching/Libros", collection_coaching),
        ("Evaluaciones históricas", collection_evaluaciones),
        ("Dossiers programas", collection_dossiers),
    ]

    total = 0
    for nombre, col in colecciones:
        count = col.count()
        total += count
        status = "✅" if count > 0 else "⚠️ (vacío)"
        print(f"  {nombre:30} {count:6} fragmentos  {status}")

    print("-"*70)
    print(f"  {'TOTAL':30} {total:6} fragmentos")


# ============================================================
# MAIN
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Evaluar rendimiento de Centauro")
    parser.add_argument("--test-rag", action="store_true", help="Ejecutar tests de RAG")
    parser.add_argument("--estado", action="store_true", help="Mostrar estado del sistema")
    parser.add_argument("--crear-plantilla-benchmark", action="store_true", help="Crear plantilla para benchmark manual")
    parser.add_argument("--analizar-benchmark", action="store_true", help="Analizar resultados del benchmark")
    parser.add_argument("--benchmark-file", type=str, help="Ruta al archivo de benchmark")
    parser.add_argument("--all", action="store_true", help="Ejecutar todo")

    args = parser.parse_args()

    # Si no se especifica nada, mostrar ayuda
    if not any([args.test_rag, args.estado, args.crear_plantilla_benchmark,
                args.analizar_benchmark, args.all]):
        parser.print_help()
        return

    if args.estado or args.all:
        mostrar_estado_sistema()

    if args.test_rag or args.all:
        test_rag_manuales()
        test_rag_buenas_practicas()
        test_rag_coaching()

    if args.crear_plantilla_benchmark:
        crear_plantilla_benchmark()

    if args.analizar_benchmark:
        analizar_benchmark(args.benchmark_file)


if __name__ == "__main__":
    # Configurar UTF-8 para Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
    main()
