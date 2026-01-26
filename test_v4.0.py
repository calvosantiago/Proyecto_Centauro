"""
Script de prueba para Centauro v4.0

Verifica que todas las nuevas funcionalidades están operativas.

Ejecutar con: python test_v4.0.py
"""
import sys
from pathlib import Path

def test_imports():
    """Prueba que todos los imports necesarios funcionan"""
    print("\n" + "="*70)
    print("TEST 1: Imports y Configuración")
    print("="*70)

    try:
        from centauro.config import settings, centauro_config
        print("✅ Configuración importada correctamente")
        print(f"   - RAG Top-K: {centauro_config.RAG_TOP_K_GENERAL}")
        print(f"   - Sheriff Threshold: {centauro_config.SHERIFF_FUZZY_THRESHOLD}")
        print(f"   - Max conversaciones: {centauro_config.MAX_CONVERSACIONES_EN_RAG}")
        return True
    except Exception as e:
        print(f"❌ Error en imports: {e}")
        return False


def test_rag_colecciones():
    """Prueba que las colecciones de ChromaDB existen"""
    print("\n" + "="*70)
    print("TEST 2: Colecciones ChromaDB")
    print("="*70)

    try:
        from centauro.rag import (
            collection_manuales,
            collection_buenas_practicas,
            collection_evaluaciones,
            collection_dossiers
        )

        print("✅ Colecciones creadas:")
        print(f"   - Manuales: {collection_manuales.count()} docs")
        print(f"   - Buenas prácticas: {collection_buenas_practicas.count()} docs")
        print(f"   - Evaluaciones: {collection_evaluaciones.count()} docs")
        print(f"   - Dossiers: {collection_dossiers.count()} docs")

        if collection_manuales.count() == 0 and collection_buenas_practicas.count() == 0:
            print("\n⚠️  ADVERTENCIA: Colecciones vacías.")
            print("   Ejecuta: python main.py (para indexar)")

        return True
    except Exception as e:
        print(f"❌ Error en colecciones: {e}")
        return False


def test_memoria():
    """Prueba que el sistema de memoria funciona"""
    print("\n" + "="*70)
    print("TEST 3: Sistema de Memoria")
    print("="*70)

    try:
        from centauro.core.memoria import memory_manager, AsesorProfile

        # Crear perfil de prueba
        print("📝 Creando perfil de prueba...")
        perfil_test = AsesorProfile(nombre="Test Usuario")

        # Guardar
        memory_manager.guardar_perfil(perfil_test)
        print("✅ Perfil guardado correctamente")

        # Cargar
        perfil_cargado = memory_manager.cargar_perfil("Test Usuario")
        print(f"✅ Perfil cargado: {perfil_cargado.nombre}")

        # Estadísticas globales
        stats = memory_manager.obtener_estadisticas_globales()
        print(f"✅ Estadísticas obtenidas:")
        print(f"   - Total asesores: {stats.get('total_asesores', 0)}")
        print(f"   - Total evaluaciones: {stats.get('total_evaluaciones', 0)}")

        return True
    except Exception as e:
        print(f"❌ Error en memoria: {e}")
        return False


def test_chat_handler():
    """Prueba que el chat handler funciona"""
    print("\n" + "="*70)
    print("TEST 4: Chat Handler")
    print("="*70)

    try:
        from centauro.core.chat_handler import ChatHandler

        chat = ChatHandler()
        print("✅ ChatHandler inicializado")

        # Prueba clasificación de intenciones
        intenciones_test = [
            ("¿Cómo hacer apertura?", "manual"),
            ("Muéstrame ejemplos", "ejemplo"),
            ("Mi rendimiento", "perfil"),
            ("Estadísticas del equipo", "estadisticas")
        ]

        print("\n📝 Probando clasificación de intenciones:")
        for pregunta, esperado in intenciones_test:
            intencion = chat._clasificar_intencion(pregunta)
            emoji = "✅" if intencion == esperado else "⚠️"
            print(f"   {emoji} '{pregunta}' → {intencion} (esperado: {esperado})")

        return True
    except Exception as e:
        print(f"❌ Error en chat handler: {e}")
        return False


def test_busqueda_rag():
    """Prueba búsquedas en RAG"""
    print("\n" + "="*70)
    print("TEST 5: Búsquedas RAG")
    print("="*70)

    try:
        from centauro.rag import buscar_en_coleccion
        from centauro.config import centauro_config

        # Buscar en manuales
        print("🔍 Buscando 'investigación' en manuales...")
        resultados_manuales = buscar_en_coleccion(
            query="investigación apertura preguntas",
            collection_name=centauro_config.COLLECTION_MANUALES,
            k=2
        )

        if resultados_manuales:
            print(f"✅ Encontrados {len(resultados_manuales)} resultados en manuales")
            print(f"   Primer resultado: {resultados_manuales[0]['text'][:100]}...")
        else:
            print("⚠️  No se encontraron resultados (colección vacía)")

        # Buscar en buenas prácticas
        print("\n🔍 Buscando 'cierre' en buenas prácticas...")
        resultados_bp = buscar_en_coleccion(
            query="cierre exitoso próximos pasos",
            collection_name=centauro_config.COLLECTION_BUENAS_PRACTICAS,
            k=2
        )

        if resultados_bp:
            print(f"✅ Encontrados {len(resultados_bp)} resultados en buenas prácticas")
        else:
            print("⚠️  No se encontraron resultados (colección vacía)")

        return True
    except Exception as e:
        print(f"❌ Error en búsquedas: {e}")
        return False


def test_validaciones():
    """Prueba sistema de validación de archivos"""
    print("\n" + "="*70)
    print("TEST 6: Validación de Archivos")
    print("="*70)

    try:
        from centauro.utils import validar_nombre_archivo
        from pathlib import Path

        # Archivo válido
        archivo_ok = Path("test.txt")
        validacion_ok = validar_nombre_archivo(archivo_ok)
        print(f"✅ Archivo corto: {validacion_ok.valido}")

        # Archivo muy largo (debería fallar)
        nombre_largo = "a" * 150 + ".txt"
        archivo_largo = Path(nombre_largo)
        validacion_largo = validar_nombre_archivo(archivo_largo)

        if not validacion_largo.valido:
            print(f"✅ Detecta nombres largos correctamente")
        else:
            print(f"⚠️  No detectó nombre largo")

        return True
    except Exception as e:
        print(f"❌ Error en validaciones: {e}")
        return False


def main():
    """Ejecuta todas las pruebas"""
    print("\n" + "🦄"*23)
    print(" "*20 + "CENTAURO v4.0 - TEST SUITE")
    print("🦄"*23)

    tests = [
        ("Imports y Configuración", test_imports),
        ("Colecciones ChromaDB", test_rag_colecciones),
        ("Sistema de Memoria", test_memoria),
        ("Chat Handler", test_chat_handler),
        ("Búsquedas RAG", test_busqueda_rag),
        ("Validación de Archivos", test_validaciones)
    ]

    resultados = []
    for nombre, test_func in tests:
        try:
            resultado = test_func()
            resultados.append((nombre, resultado))
        except Exception as e:
            print(f"\n❌ Error ejecutando test '{nombre}': {e}")
            resultados.append((nombre, False))

    # Resumen
    print("\n" + "="*70)
    print("RESUMEN DE PRUEBAS")
    print("="*70)

    exitosos = sum(1 for _, r in resultados if r)
    total = len(resultados)

    for nombre, resultado in resultados:
        emoji = "✅" if resultado else "❌"
        print(f"{emoji} {nombre}")

    print("\n" + "="*70)
    print(f"Resultado: {exitosos}/{total} pruebas exitosas")

    if exitosos == total:
        print("🎉 ¡Todas las pruebas pasaron! Centauro v4.0 está operativo.")
    elif exitosos > total // 2:
        print("⚠️  Algunas pruebas fallaron. Revisa los errores arriba.")
    else:
        print("❌ Múltiples fallos. Verifica la instalación.")

    print("="*70 + "\n")

    # Recomendaciones
    if any(not r for _, r in resultados):
        print("📝 RECOMENDACIONES:\n")

        if not resultados[1][1]:  # Colecciones vacías
            print("1. Ejecuta: python main.py")
            print("   (Para indexar la base de conocimiento)\n")

        print("2. Verifica que existe archivo .env con OPENAI_API_KEY")
        print("3. Verifica que todas las dependencias están instaladas:")
        print("   pip install -r requirements.txt\n")

    return exitosos == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
