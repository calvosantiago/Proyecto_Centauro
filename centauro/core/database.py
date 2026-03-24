"""
Gestor de Base de Datos con Supabase v1.0

Encapsula todas las operaciones CRUD contra Supabase (PostgreSQL hosted).
Reemplaza el almacenamiento JSON de perfiles de asesores.

Si SUPABASE_URL no está configurado, todas las operaciones retornan None
y el sistema usa el fallback JSON en memoria.py.
"""
import json
import unicodedata
import statistics
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from ..config import settings, centauro_config


def _normalizar_nombre(nombre: str) -> str:
    """Quita acentos y pasa a minúsculas para comparación."""
    sin_acentos = ''.join(
        c for c in unicodedata.normalize('NFD', nombre)
        if unicodedata.category(c) != 'Mn'
    )
    return ' '.join(sin_acentos.lower().split())


class DatabaseManager:
    """
    Gestor de operaciones con Supabase.

    Uso:
        db = DatabaseManager()
        if db.disponible:
            db.registrar_asesor("Juan Pérez")
        else:
            # fallback a JSON
    """

    def __init__(self):
        self._client = None
        self._disponible = False
        self._inicializar()

    def _inicializar(self):
        """Intenta conectar a Supabase. Si falla, marca como no disponible."""
        url = getattr(settings, 'SUPABASE_URL', '')
        key = getattr(settings, 'SUPABASE_KEY', '')

        if not url or not key:
            print("   ℹ️ Supabase no configurado. Usando almacenamiento JSON local.")
            return

        try:
            from supabase import create_client
            self._client = create_client(url, key)
            self._disponible = True
            print("   ✅ Conectado a Supabase.")
        except ImportError:
            print("   ⚠️ Paquete 'supabase' no instalado. pip install supabase")
        except Exception as e:
            print(f"   ⚠️ Error conectando a Supabase: {e}")

    @property
    def disponible(self) -> bool:
        return self._disponible

    # ===================== ASESORES =====================

    def buscar_asesor(self, nombre: str) -> Optional[dict]:
        """
        Busca un asesor por nombre canónico normalizado O por alias.

        Estrategia:
        1. Busca coincidencia exacta en nombre_normalizado
        2. Si no encuentra, busca en el array aliases (contains)

        Returns:
            Dict del asesor si se encuentra, None si no existe.
        """
        if not self._disponible:
            return None

        nombre_norm = _normalizar_nombre(nombre)

        # 1. Buscar por nombre canónico
        result = (
            self._client.table("asesores")
            .select("*")
            .eq("nombre_normalizado", nombre_norm)
            .execute()
        )
        if result.data:
            return result.data[0]

        # 2. Buscar en aliases: traer todos y comparar
        # (Supabase no soporta búsqueda dentro de strings en JSONB array fácilmente
        # sin RPC, así que traemos todos y filtramos en Python)
        todos = self.listar_asesores()
        for asesor in todos:
            aliases = asesor.get("aliases") or []
            for alias in aliases:
                if _normalizar_nombre(alias) == nombre_norm:
                    return asesor

        return None

    def registrar_asesor(self, nombre: str) -> Optional[int]:
        """
        Devuelve el ID del asesor si existe (por nombre o alias).
        Si no existe, crea uno nuevo.

        Returns:
            ID del asesor en Supabase, o None si no disponible.
        """
        if not self._disponible:
            return None

        asesor = self.buscar_asesor(nombre)
        if asesor:
            return asesor["id"]

        # Crear nuevo
        nombre_norm = _normalizar_nombre(nombre)
        result = (
            self._client.table("asesores")
            .insert({
                "nombre": nombre,
                "nombre_normalizado": nombre_norm,
                "fecha_creacion": datetime.now().isoformat(),
                "activo": True,
                "aliases": []
            })
            .execute()
        )
        if result.data:
            print(f"   ➕ Nuevo asesor creado en Supabase: {nombre}")
        return result.data[0]["id"] if result.data else None

    def obtener_asesor_por_nombre(self, nombre: str) -> Optional[dict]:
        """Busca un asesor por nombre o alias. Alias de buscar_asesor para compatibilidad."""
        return self.buscar_asesor(nombre)

    def listar_asesores(self) -> List[dict]:
        """Devuelve todos los asesores activos."""
        if not self._disponible:
            return []

        result = (
            self._client.table("asesores")
            .select("*")
            .eq("activo", True)
            .execute()
        )

        return result.data or []

    # ===================== EVALUACIONES =====================

    def registrar_evaluacion(
        self,
        asesor_id: int,
        resultado_evaluacion: Dict,
        opportunity_id: Optional[str] = None,
        archivo_origen: Optional[str] = None,
        reporte_pdf_path: Optional[str] = None,
        stats: Optional[Dict] = None
    ) -> Optional[int]:
        """
        Registra una evaluación completa (evaluacion + calificaciones_bloque).

        Args:
            asesor_id: ID del asesor en Supabase
            resultado_evaluacion: Dict del reporte (output del orquestador)
            opportunity_id: ID de oportunidad (del nombre de archivo)
            archivo_origen: Nombre del archivo original
            reporte_pdf_path: Path al PDF del reporte
            stats: Dict con llamadas_api, tiempo_analisis_seg

        Returns:
            ID de la evaluación, o None si no disponible.
        """
        if not self._disponible:
            return None

        # Extraer resumen contextual
        resumen = resultado_evaluacion.get("resumen_contextual", {})
        barreras = resumen.get("barreras_principales", [])

        # Datos de la evaluación
        eval_data = {
            "asesor_id": asesor_id,
            "opportunity_id": opportunity_id,
            "fecha": datetime.now().isoformat(),
            "calificacion_global": resultado_evaluacion.get("calificacion_global"),
            "archivo_origen": archivo_origen,
            "perfil_lead": resumen.get("perfil_lead"),
            "objetivo_del_lead": resumen.get("objetivo_del_lead"),
            "factor_determinante_compra": resumen.get("factor_determinante_compra"),
            "barreras_principales": json.dumps(barreras) if barreras else "[]",
            "fecha_seguimiento": resumen.get("fecha_seguimiento"),
            "reporte_pdf_path": reporte_pdf_path,
        }

        if stats:
            eval_data["llamadas_api"] = stats.get("llamadas_api")
            eval_data["tiempo_analisis_seg"] = stats.get("tiempo_analisis_seg")

        # Insertar evaluación
        result = (
            self._client.table("evaluaciones")
            .insert(eval_data)
            .execute()
        )

        if not result.data:
            return None

        evaluacion_id = result.data[0]["id"]

        # Insertar calificaciones por bloque
        bloques = resultado_evaluacion.get("evaluacion_por_bloques", [])
        bloques_data = []
        for bloque in bloques:
            if isinstance(bloque, dict):
                bloques_data.append({
                    "evaluacion_id": evaluacion_id,
                    "bloque": bloque.get("bloque", ""),
                    "calificacion": bloque.get("calificacion"),
                    "observabilidad": bloque.get("observabilidad"),
                    "confianza": bloque.get("confianza"),
                    "evidencia_principal": bloque.get("evidencia_principal"),
                    "razonamiento": bloque.get("razonamiento"),
                    "recomendacion_accionable": bloque.get("recomendacion_accionable"),
                })

        if bloques_data:
            self._client.table("calificaciones_bloque").insert(bloques_data).execute()

        return evaluacion_id

    def obtener_evaluaciones(
        self,
        asesor_id: int,
        desde: Optional[str] = None,
        hasta: Optional[str] = None
    ) -> List[dict]:
        """
        Obtiene evaluaciones de un asesor, opcionalmente filtradas por fecha.

        Returns:
            Lista de dicts con datos de evaluación (sin calificaciones_bloque).
        """
        if not self._disponible:
            return []

        query = (
            self._client.table("evaluaciones")
            .select("*")
            .eq("asesor_id", asesor_id)
            .order("fecha", desc=False)
        )

        if desde:
            query = query.gte("fecha", desde)
        if hasta:
            query = query.lte("fecha", hasta)

        result = query.execute()
        return result.data or []

    def obtener_calificaciones_bloque(self, evaluacion_id: int) -> List[dict]:
        """Obtiene las calificaciones por bloque de una evaluación."""
        if not self._disponible:
            return []

        result = (
            self._client.table("calificaciones_bloque")
            .select("*")
            .eq("evaluacion_id", evaluacion_id)
            .execute()
        )

        return result.data or []

    # ===================== PERFILES (reconstruye AsesorProfile) =====================

    def obtener_perfil(self, nombre: str):
        """
        Reconstruye un AsesorProfile desde Supabase.

        Returns:
            AsesorProfile con historial completo, o None si no disponible/no existe.
        """
        if not self._disponible:
            return None

        # Importar aquí para evitar circular
        from .memoria import AsesorProfile, EvaluacionHistorica

        asesor = self.obtener_asesor_por_nombre(nombre)
        if not asesor:
            return None

        # Obtener todas las evaluaciones
        evaluaciones_raw = self.obtener_evaluaciones(asesor["id"])

        evaluaciones = []
        for eval_raw in evaluaciones_raw:
            # Obtener calificaciones por bloque
            bloques_raw = self.obtener_calificaciones_bloque(eval_raw["id"])

            calificaciones_por_bloque = {}
            fortalezas = []
            areas_mejora = []

            for bloque in bloques_raw:
                nombre_bloque = bloque["bloque"]
                cal = bloque["calificacion"]
                calificaciones_por_bloque[nombre_bloque] = cal

                if cal == "BUENO":
                    fortalezas.append(nombre_bloque)
                elif cal == "MALO":
                    areas_mejora.append(nombre_bloque)

            evaluacion = EvaluacionHistorica(
                fecha=eval_raw["fecha"],
                asesor=nombre,
                calificacion_global=eval_raw.get("calificacion_global"),
                calificaciones_por_bloque=calificaciones_por_bloque,
                fortalezas=fortalezas,
                areas_mejora=areas_mejora,
            )
            evaluaciones.append(evaluacion)

        # Construir perfil
        perfil = AsesorProfile(nombre=nombre, evaluaciones=evaluaciones)
        perfil.actualizar_estadisticas()

        return perfil

    # ===================== ESTADÍSTICAS =====================

    def obtener_estadisticas_globales(self) -> Optional[Dict]:
        """Genera estadísticas del sistema completo desde Supabase."""
        if not self._disponible:
            return None

        asesores = self.listar_asesores()
        total_asesores = len(asesores)

        # Contar evaluaciones
        result = (
            self._client.table("evaluaciones")
            .select("id", count="exact")
            .execute()
        )
        total_evaluaciones = result.count or 0

        # Calcular tendencias (simplificado: cuenta mejorando/empeorando)
        asesores_mejorando = 0
        asesores_empeorando = 0

        ORDEN = {"MALO": 0, "MEJORABLE": 1, "BUENO": 2}

        for asesor in asesores:
            evals = self.obtener_evaluaciones(asesor["id"])
            if len(evals) >= 5:
                n = min(centauro_config.EVALUACIONES_PARA_TENDENCIA // 2, len(evals) // 2)
                primeras = evals[:n]
                ultimas = evals[-n:]

                prom_ini = statistics.mean([ORDEN.get(e.get("calificacion_global", "MEJORABLE"), 1) for e in primeras])
                prom_rec = statistics.mean([ORDEN.get(e.get("calificacion_global", "MEJORABLE"), 1) for e in ultimas])

                cambio = prom_rec - prom_ini
                if cambio > centauro_config.THRESHOLD_CAMBIO_SIGNIFICATIVO:
                    asesores_mejorando += 1
                elif cambio < -centauro_config.THRESHOLD_CAMBIO_SIGNIFICATIVO:
                    asesores_empeorando += 1

        return {
            "total_asesores": total_asesores,
            "total_evaluaciones": total_evaluaciones,
            "asesores_mejorando": asesores_mejorando,
            "asesores_empeorando": asesores_empeorando,
        }

    # ===================== OPORTUNIDADES =====================

    def guardar_oportunidad(self, data: dict) -> None:
        """Guarda o actualiza una oportunidad en la cache local."""
        if not self._disponible:
            return

        opp_id = data.get("opportunity_id")
        if not opp_id:
            return

        data["fecha_sync"] = datetime.now().isoformat()

        # Upsert
        self._client.table("oportunidades").upsert(
            data, on_conflict="opportunity_id"
        ).execute()

    def obtener_oportunidad(self, opportunity_id: str) -> Optional[dict]:
        """Busca una oportunidad por su ID."""
        if not self._disponible:
            return None

        result = (
            self._client.table("oportunidades")
            .select("*")
            .eq("opportunity_id", opportunity_id)
            .execute()
        )

        return result.data[0] if result.data else None

    def obtener_oportunidades_filtradas(self, filtros: dict = None, limit: int = 5000) -> list:
        """
        Obtiene oportunidades con filtros opcionales (pais, pilar, programa...).
        Usado para estadísticas de pipeline desde el chat.
        """
        if not self._disponible:
            return []

        query = self._client.table("oportunidades").select(
            "opportunity_id, nombre_lead, pilar, pais, edad, programa, fecha_creacion"
        )

        if filtros:
            for key, value in filtros.items():
                if value is not None:
                    query = query.eq(key, value)

        result = query.limit(limit).execute()
        return result.data if result.data else []


# Instancia global (lazy init)
_db_instance = None


def get_database() -> DatabaseManager:
    """Obtiene la instancia global de DatabaseManager (singleton lazy)."""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance
