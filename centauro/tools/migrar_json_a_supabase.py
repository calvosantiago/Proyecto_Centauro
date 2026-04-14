"""
Migración one-time: JSON perfiles → Supabase

Uso:
    python -m centauro.tools.migrar_json_a_supabase

Lee los perfiles existentes de outputs/perfiles_asesores/*.json
y los inserta en Supabase. También cruza con outputs/Reportes_JSON/
para enriquecer evaluaciones con resumen contextual y calificaciones por bloque.

Es idempotente: usa upsert para asesores y verifica duplicados por fecha+asesor.
NO borra los JSONs originales.
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# Ajustar path para imports
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from centauro.config import settings
from centauro.core.database import DatabaseManager


def cargar_reportes_json() -> dict:
    """
    Carga todos los reportes JSON disponibles indexados por nombre de asesor.

    Returns:
        Dict[nombre_asesor_lower, List[dict]] con reportes completos.
    """
    reportes_dir = settings.OUTPUTS_DIR / "Reportes_JSON"
    reportes_por_asesor = {}

    if not reportes_dir.exists():
        return reportes_por_asesor

    for archivo in reportes_dir.glob("*.json"):
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                reporte = json.load(f)

            asesor = reporte.get("asesor", "").strip().lower()
            if asesor and asesor != "desconocido":
                if asesor not in reportes_por_asesor:
                    reportes_por_asesor[asesor] = []
                reportes_por_asesor[asesor].append({
                    "reporte": reporte,
                    "archivo": str(archivo),
                })
        except Exception:
            continue

    return reportes_por_asesor


def buscar_reporte_para_evaluacion(
    reportes_asesor: list,
    fecha_evaluacion: str,
    transcripcion_path: str
) -> dict | None:
    """
    Intenta encontrar el reporte completo que corresponde a una evaluación
    del perfil, usando el path de transcripción como pista.
    """
    if not reportes_asesor:
        return None

    # Intentar match por nombre de transcripción
    if transcripcion_path:
        trans_stem = Path(transcripcion_path).stem.lower()
        for r in reportes_asesor:
            archivo_stem = Path(r["archivo"]).stem.lower()
            # El reporte se llama {transcripcion}_v2.json o _v3.json
            if trans_stem in archivo_stem:
                return r["reporte"]

    # Si solo hay un reporte, asumirlo
    if len(reportes_asesor) == 1:
        return reportes_asesor[0]["reporte"]

    return None


def migrar():
    """Ejecuta la migración de JSONs a Supabase."""
    print("=" * 60)
    print("  MIGRACIÓN: Perfiles JSON → Supabase")
    print("=" * 60)

    db = DatabaseManager()

    if not db.disponible:
        print("\n❌ Supabase no disponible. Configura SUPABASE_URL y SUPABASE_KEY en .env")
        return

    perfiles_dir = settings.OUTPUTS_DIR / "perfiles_asesores"
    if not perfiles_dir.exists():
        print("\n❌ No se encontró directorio de perfiles:", perfiles_dir)
        return

    archivos = list(perfiles_dir.glob("*.json"))
    if not archivos:
        print("\n⚠️ No hay perfiles JSON para migrar.")
        return

    print(f"\n📂 Encontrados {len(archivos)} perfiles para migrar.")

    # Pre-cargar reportes completos
    reportes_por_asesor = cargar_reportes_json()
    print(f"📄 Encontrados reportes de {len(reportes_por_asesor)} asesores.")

    total_asesores = 0
    total_evaluaciones = 0
    total_bloques = 0
    errores = 0

    for archivo in archivos:
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                data = json.load(f)

            nombre = data.get("nombre", archivo.stem.replace("_", " ").title())
            print(f"\n👤 {nombre}...")

            # Registrar asesor
            asesor_id = db.registrar_asesor(nombre)
            if not asesor_id:
                print(f"   ❌ Error registrando asesor")
                errores += 1
                continue

            total_asesores += 1

            # Obtener reportes de este asesor
            reportes_asesor = reportes_por_asesor.get(nombre.lower(), [])

            # Migrar cada evaluación
            evaluaciones = data.get("evaluaciones", [])
            for eval_data in evaluaciones:
                fecha = eval_data.get("fecha", datetime.now().isoformat())

                # Verificar si ya existe (por fecha + asesor_id)
                existentes = db.obtener_evaluaciones(asesor_id)
                ya_existe = any(
                    e.get("fecha", "")[:19] == fecha[:19]
                    for e in existentes
                )
                if ya_existe:
                    print(f"   ⏭️ Evaluación {fecha[:10]} ya existe, saltando.")
                    continue

                # Intentar enriquecer con reporte completo
                transcripcion_path = eval_data.get("transcripcion_path", "")
                reporte_completo = buscar_reporte_para_evaluacion(
                    reportes_asesor, fecha, transcripcion_path
                )

                # Construir resultado_evaluacion compatible
                if reporte_completo:
                    resultado = reporte_completo
                else:
                    # Reconstruir desde datos del perfil
                    calificaciones = eval_data.get("calificaciones_por_bloque", {})
                    bloques_list = []
                    for bloque_nombre, cal in calificaciones.items():
                        bloques_list.append({
                            "bloque": bloque_nombre,
                            "calificacion": cal,
                            "observabilidad": "ALTA",
                            "confianza": 0.0,
                            "evidencia_principal": "",
                            "razonamiento": "",
                            "recomendacion_accionable": "",
                        })

                    resultado = {
                        "calificacion_global": eval_data.get("calificacion_global"),
                        "evaluacion_por_bloques": bloques_list,
                        "resumen_contextual": {},
                    }

                # Insertar evaluación
                eval_id = db.registrar_evaluacion(
                    asesor_id=asesor_id,
                    resultado_evaluacion=resultado,
                    transcripcion_path=transcripcion_path,
                    archivo_origen=Path(transcripcion_path).name if transcripcion_path else None,
                )

                if eval_id:
                    n_bloques = len(resultado.get("evaluacion_por_bloques", []))
                    total_evaluaciones += 1
                    total_bloques += n_bloques
                    print(f"   ✅ Evaluación {fecha[:10]} migrada ({n_bloques} bloques)")
                else:
                    print(f"   ❌ Error migrando evaluación {fecha[:10]}")
                    errores += 1

        except Exception as e:
            print(f"   ❌ Error procesando {archivo.name}: {e}")
            errores += 1

    # Resumen
    print(f"\n{'=' * 60}")
    print(f"  MIGRACIÓN COMPLETADA")
    print(f"{'=' * 60}")
    print(f"  ✅ Asesores migrados: {total_asesores}")
    print(f"  ✅ Evaluaciones migradas: {total_evaluaciones}")
    print(f"  ✅ Calificaciones por bloque: {total_bloques}")
    if errores:
        print(f"  ⚠️ Errores: {errores}")
    print(f"\n  Los JSONs originales NO se han borrado.")
    print(f"  Puedes verificar los datos en el dashboard de Supabase.")


if __name__ == "__main__":
    migrar()
