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

        # 2. Buscar por prefijo: "Ivan Canale" debe encontrar "Ivan Canale García"
        # Se usa ilike para que Supabase filtre en el servidor antes de traer todos.
        result_prefix = (
            self._client.table("asesores")
            .select("*")
            .ilike("nombre_normalizado", f"{nombre_norm}%")
            .execute()
        )
        tokens_entrada = nombre_norm.split()
        for row in (result_prefix.data or []):
            tokens_conocido = (row.get("nombre_normalizado") or "").split()
            n_e, n_c = len(tokens_entrada), len(tokens_conocido)
            if n_c >= n_e >= 2 and tokens_conocido[:n_e] == tokens_entrada:
                return row

        # 3. Buscar en aliases: traer todos y comparar
        # (Supabase no soporta búsqueda dentro de strings en JSONB array fácilmente
        # sin RPC, así que traemos todos y filtramos en Python)
        todos = self.listar_asesores()
        for asesor in todos:
            aliases = asesor.get("aliases") or []
            for alias in aliases:
                if _normalizar_nombre(alias) == nombre_norm:
                    return asesor
            # También comprobar prefijo en aliases
            for alias in aliases:
                alias_norm = _normalizar_nombre(alias)
                tokens_alias = alias_norm.split()
                n_a = len(tokens_alias)
                if n_a >= len(tokens_entrada) >= 2 and tokens_alias[:len(tokens_entrada)] == tokens_entrada:
                    return asesor

        return None

    def registrar_asesor(self, nombre: str) -> Optional[int]:
        """
        Devuelve el ID del asesor si existe (por nombre o alias).
        NO crea asesores nuevos — la tabla de asesores se gestiona
        exclusivamente desde el Excel TTAA vía el notebook de Fabric.

        Returns:
            ID del asesor en Supabase, None si no encontrado o no disponible.
        """
        if not self._disponible:
            return None

        asesor = self.buscar_asesor(nombre)
        if asesor:
            return asesor["id"]

        # Asesor no reconocido → NO crear, devolver None
        print(f"   ⚠️ Asesor no reconocido en Supabase (no se crea): '{nombre}'")
        return None

    def obtener_id_asesor_desconocido(self) -> int:
        """
        Devuelve el ID fijo del asesor 'Asesor Desconocido' (id=68).
        Usado para evaluaciones de asesores no reconocidos.
        """
        return 68

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
        storage_path: Optional[str] = None,
        stats: Optional[Dict] = None,
        realizado_por: Optional[str] = None,
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
            "barreras_principales": " | ".join(barreras) if barreras else None,
            "fecha_seguimiento": resumen.get("fecha_seguimiento"),
            "reporte_pdf_path": reporte_pdf_path,
            "storage_path": storage_path,
            "email_enviado": False,
        }

        if stats:
            eval_data["llamadas_api"] = stats.get("llamadas_api")
            eval_data["tiempo_analisis_seg"] = stats.get("tiempo_analisis_seg")

        if realizado_por:
            eval_data["realizado_por"] = realizado_por

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
                    "razonamiento": bloque.get("razonamiento"),
                    "mejoras": bloque.get("mejoras", ""),
                })

        if bloques_data:
            try:
                self._client.table("calificaciones_bloque").insert(bloques_data).execute()
            except Exception as e:
                logger.error(f"Error insertando calificaciones_bloque (evaluacion_id={evaluacion_id}): {e}")

        return evaluacion_id

    def buscar_evaluacion_por_oportunidad(self, opportunity_id: str) -> Optional[dict]:
        """
        Busca si ya existe una evaluación para un opportunity_id dado.

        Returns:
            Dict con los datos de la evaluación más reciente, o None si no existe.
        """
        if not self._disponible or not opportunity_id:
            return None

        result = (
            self._client.table("evaluaciones")
            .select("*")
            .eq("opportunity_id", opportunity_id)
            .order("fecha", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def actualizar_evaluacion(
        self,
        evaluacion_id: int,
        asesor_id: int,
        resultado_evaluacion: Dict,
        opportunity_id: Optional[str] = None,
        archivo_origen: Optional[str] = None,
        reporte_pdf_path: Optional[str] = None,
        stats: Optional[Dict] = None
    ) -> bool:
        """
        Sobreescribe una evaluación existente (UPDATE) y reemplaza sus calificaciones_bloque.

        Returns:
            True si la actualización fue exitosa.
        """
        if not self._disponible:
            return False

        resumen = resultado_evaluacion.get("resumen_contextual", {})
        barreras = resumen.get("barreras_principales", [])

        eval_data = {
            "asesor_id": asesor_id,
            "opportunity_id": opportunity_id,
            "fecha": datetime.now().isoformat(),
            "calificacion_global": resultado_evaluacion.get("calificacion_global"),
            "archivo_origen": archivo_origen,
            "perfil_lead": resumen.get("perfil_lead"),
            "objetivo_del_lead": resumen.get("objetivo_del_lead"),
            "factor_determinante_compra": resumen.get("factor_determinante_compra"),
            "barreras_principales": " | ".join(barreras) if barreras else None,
            "fecha_seguimiento": resumen.get("fecha_seguimiento"),
            "reporte_pdf_path": reporte_pdf_path,
        }

        if stats:
            eval_data["llamadas_api"] = stats.get("llamadas_api")
            eval_data["tiempo_analisis_seg"] = stats.get("tiempo_analisis_seg")

        try:
            self._client.table("evaluaciones").update(eval_data).eq("id", evaluacion_id).execute()
        except Exception as e:
            logger.error(f"Error actualizando evaluacion (id={evaluacion_id}): {e}")
            return False

        # Reemplazar calificaciones_bloque: borrar las viejas e insertar las nuevas
        try:
            self._client.table("calificaciones_bloque").delete().eq("evaluacion_id", evaluacion_id).execute()
        except Exception as e:
            logger.error(f"Error borrando calificaciones_bloque antiguas (evaluacion_id={evaluacion_id}): {e}")

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
                    "razonamiento": bloque.get("razonamiento"),
                    "mejoras": bloque.get("mejoras", ""),
                })

        if bloques_data:
            try:
                self._client.table("calificaciones_bloque").insert(bloques_data).execute()
            except Exception as e:
                logger.error(f"Error reinsertando calificaciones_bloque (evaluacion_id={evaluacion_id}): {e}")

        return True

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

    def obtener_evaluacion_por_opp_id(self, opp_id: str) -> Optional[dict]:
        """
        Devuelve la evaluación más reciente asociada a un opportunity_id,
        incluyendo calificaciones por bloque y nombre del asesor.
        """
        if not self._disponible:
            return None

        result = (
            self._client.table("evaluaciones")
            .select("*, asesores(nombre)")
            .eq("opportunity_id", opp_id)
            .order("fecha", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None

        ev = dict(result.data[0])
        ev["calificaciones_bloque"] = self.obtener_calificaciones_bloque(ev["id"])
        asesor_join = ev.pop("asesores", None)
        if isinstance(asesor_join, dict):
            ev["nombre_asesor"] = asesor_join.get("nombre")
        return ev

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

    def obtener_asesor_por_opp_id(self, opportunity_id: str) -> Optional[dict]:
        """
        Busca el asesor asociado a una evaluación previa del mismo opportunity_id.
        Útil para identificar al asesor cuando el nombre dado no está registrado.

        Returns:
            Dict del asesor si existe una evaluación previa, None en caso contrario.
        """
        if not self._disponible:
            return None

        result = (
            self._client.table("evaluaciones")
            .select("asesor_id, asesores(id, nombre)")
            .eq("opportunity_id", opportunity_id)
            .neq("asesor_id", self.obtener_id_asesor_desconocido())
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            # Supabase devuelve el join como row["asesores"]
            asesor_join = row.get("asesores")
            if asesor_join and isinstance(asesor_join, dict):
                return asesor_join
        return None

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

    def obtener_stats_semana_asesor(self, asesor_id: int, dias: int = 7) -> dict:
        """
        Estadísticas del asesor en los últimos N días.

        Returns:
            {
                "total_entrevistas": int,
                "evaluaciones": [...],  # cada una con "_bloques" añadido
                "bloques_frecuencia": {bloque: {"BUENO": n, "MEJORABLE": n, "MALO": n}},
                "bloques_debiles": [(bloque, pct_debil, conteo), ...],
            }
        """
        if not self._disponible:
            return {
                "total_entrevistas": 0,
                "evaluaciones": [],
                "bloques_frecuencia": {},
                "bloques_debiles": [],
            }

        desde = (datetime.now() - timedelta(days=dias)).isoformat()
        evaluaciones = self.obtener_evaluaciones(asesor_id, desde=desde)

        frecuencia: dict = {}
        for ev in evaluaciones:
            bloques = self.obtener_calificaciones_bloque(ev["id"])
            ev["_bloques"] = bloques
            for b in bloques:
                bloque = b.get("bloque", "")
                cal = b.get("calificacion")
                if bloque and cal in ("BUENO", "MEJORABLE", "MALO"):
                    if bloque not in frecuencia:
                        frecuencia[bloque] = {"BUENO": 0, "MEJORABLE": 0, "MALO": 0}
                    frecuencia[bloque][cal] += 1

        bloques_debiles = []
        for bloque, conteo in frecuencia.items():
            total_b = sum(conteo.values())
            pct_debil = (conteo["MEJORABLE"] + conteo["MALO"]) / total_b if total_b > 0 else 0
            bloques_debiles.append((bloque, pct_debil, conteo))
        bloques_debiles.sort(key=lambda x: x[1], reverse=True)

        return {
            "total_entrevistas": len(evaluaciones),
            "evaluaciones": evaluaciones,
            "bloques_frecuencia": frecuencia,
            "bloques_debiles": bloques_debiles,
        }


# Instancia global (lazy init)
_db_instance = None


def get_database() -> DatabaseManager:
    """Obtiene la instancia global de DatabaseManager (singleton lazy)."""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance
