"""
Sistema de Memoria y Aprendizaje Continuo v4.0

Este módulo implementa:
1. Perfiles de asesores con historial de evaluaciones
2. Detección de tendencias (mejora/empeoramiento)
3. Aprendizaje continuo: conversaciones excelentes → RAG
4. Rolling window: solo últimos 6 meses relevantes
5. Feedback personalizado basado en historial

Filosofía: "Cada uso de Centauro mejora a Centauro"
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path
import statistics

from ..config import centauro_config
from ..rag import collection_evaluaciones


@dataclass
class EvaluacionHistorica:
    """Registro de una evaluación pasada (simplificado)"""
    fecha: str  # ISO format: "2025-01-26T14:30:00"
    asesor: str
    calificacion_global: Optional[str]  # MALO | MEJORABLE | BUENO
    calificaciones_por_bloque: Dict[str, Optional[str]]  # {"Investigación": "BUENO", ...}
    fortalezas: List[str]  # Bloques con BUENO
    areas_mejora: List[str]  # Bloques con MALO
    transcripcion_path: Optional[str] = None  # Path al archivo original


@dataclass
class AsesorProfile:
    """Perfil de un asesor con su historial y análisis"""
    nombre: str
    evaluaciones: List[EvaluacionHistorica] = field(default_factory=list)

    # Estadísticas agregadas (calculadas automáticamente)
    total_evaluaciones: int = 0
    fecha_primera_evaluacion: Optional[str] = None
    fecha_ultima_evaluacion: Optional[str] = None

    # Análisis por bloque (calculado automáticamente)
    fortalezas_consistentes: List[str] = field(default_factory=list)  # Bloques mayoritariamente BUENO
    areas_mejora_consistentes: List[str] = field(default_factory=list)  # Bloques mayoritariamente MALO

    # Tendencias recientes (en escala ordinal: MALO=0, MEJORABLE=1, BUENO=2)
    tendencia_global: str = "estable"  # "mejorando" | "empeorando" | "estable"
    cambio_reciente: float = 0.0  # Diferencia últimas 5 vs primeras 5 (escala 0-2)

    def actualizar_estadisticas(self):
        """Recalcula todas las estadísticas basadas en evaluaciones"""
        if not self.evaluaciones:
            return

        # Ordenar por fecha
        self.evaluaciones.sort(key=lambda e: e.fecha)

        # Básicas
        self.total_evaluaciones = len(self.evaluaciones)
        self.fecha_primera_evaluacion = self.evaluaciones[0].fecha
        self.fecha_ultima_evaluacion = self.evaluaciones[-1].fecha

        # Análisis por bloque
        self._calcular_fortalezas_debilidades()

        # Tendencias
        self._calcular_tendencia()

    def _calcular_fortalezas_debilidades(self):
        """Identifica bloques consistentemente BUENOS o MALOS"""
        from collections import Counter

        bloques_calificaciones: Dict[str, List[str]] = {}

        for evaluacion in self.evaluaciones:
            for bloque, cal in evaluacion.calificaciones_por_bloque.items():
                if cal is not None:
                    if bloque not in bloques_calificaciones:
                        bloques_calificaciones[bloque] = []
                    bloques_calificaciones[bloque].append(cal)

        self.fortalezas_consistentes = []
        self.areas_mejora_consistentes = []

        for bloque, calificaciones in bloques_calificaciones.items():
            if len(calificaciones) >= 3:  # Mínimo 3 evaluaciones
                conteo = Counter(calificaciones)
                mayoria = conteo.most_common(1)[0][0]
                if mayoria == "BUENO":
                    self.fortalezas_consistentes.append(bloque)
                elif mayoria == "MALO":
                    self.areas_mejora_consistentes.append(bloque)

    def _calcular_tendencia(self):
        """Detecta si el asesor está mejorando o empeorando (escala ordinal MALO=0, MEJORABLE=1, BUENO=2)"""
        ORDEN = {"MALO": 0, "MEJORABLE": 1, "BUENO": 2}

        if len(self.evaluaciones) < 5:
            self.tendencia_global = "datos_insuficientes"
            return

        n = min(centauro_config.EVALUACIONES_PARA_TENDENCIA // 2, len(self.evaluaciones) // 2)

        primeras = self.evaluaciones[:n]
        ultimas = self.evaluaciones[-n:]

        def valor_cal(e):
            return ORDEN.get(e.calificacion_global, 1)  # MEJORABLE como default

        promedio_inicial = statistics.mean([valor_cal(e) for e in primeras])
        promedio_reciente = statistics.mean([valor_cal(e) for e in ultimas])

        self.cambio_reciente = promedio_reciente - promedio_inicial

        if abs(self.cambio_reciente) < centauro_config.THRESHOLD_CAMBIO_SIGNIFICATIVO:
            self.tendencia_global = "estable"
        elif self.cambio_reciente > 0:
            self.tendencia_global = "mejorando"
        else:
            self.tendencia_global = "empeorando"

    def obtener_feedback_personalizado(self) -> str:
        """Genera feedback contextualizado basado en historial"""
        if self.total_evaluaciones == 0:
            return "Primera evaluación de este asesor."

        feedback = []

        # Tendencia
        if self.tendencia_global == "mejorando":
            feedback.append(f"📈 **Progreso detectado**: Tendencia de mejora en las últimas {self.total_evaluaciones} llamadas.")
        elif self.tendencia_global == "empeorando":
            feedback.append(f"📉 **Alerta**: Se detectó tendencia de empeoramiento. Revisa las áreas de mejora.")
        else:
            feedback.append(f"➡️ **Desempeño consistente**: Nivel estable en las últimas evaluaciones.")

        # Fortalezas
        if self.fortalezas_consistentes:
            bloques_str = ", ".join(self.fortalezas_consistentes)
            feedback.append(f"✅ **Fortalezas consolidadas**: {bloques_str}")

        # Áreas de mejora
        if self.areas_mejora_consistentes:
            bloques_str = ", ".join(self.areas_mejora_consistentes)
            feedback.append(f"🎯 **Foco recomendado**: {bloques_str} (área recurrente de mejora)")

        # Contexto histórico
        feedback.append(f"📊 Evaluación #{self.total_evaluaciones}")

        return "\n".join(feedback)

    def to_dict(self) -> Dict:
        """Serializa perfil a diccionario"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'AsesorProfile':
        """Deserializa perfil desde diccionario"""
        # Reconstruir evaluaciones
        evaluaciones = [EvaluacionHistorica(**e) for e in data.get('evaluaciones', [])]

        # Crear perfil
        perfil = cls(
            nombre=data['nombre'],
            evaluaciones=evaluaciones,
            total_evaluaciones=data.get('total_evaluaciones', 0),
            fecha_primera_evaluacion=data.get('fecha_primera_evaluacion'),
            fecha_ultima_evaluacion=data.get('fecha_ultima_evaluacion'),
            fortalezas_consistentes=data.get('fortalezas_consistentes', []),
            areas_mejora_consistentes=data.get('areas_mejora_consistentes', []),
            tendencia_global=data.get('tendencia_global', 'estable'),
            cambio_reciente=data.get('cambio_reciente', 0.0)
        )

        return perfil


class MemoryManager:
    """
    Gestor de memoria del sistema.

    Responsabilidades:
    1. Persistir perfiles de asesores (Supabase o JSON fallback)
    2. Añadir nuevas evaluaciones y actualizar perfiles
    3. Agregar conversaciones excelentes al RAG
    4. Limpiar datos obsoletos (rolling window)
    """

    def __init__(self):
        self.perfiles_cache: Dict[str, AsesorProfile] = {}

        # Inicializar conexión a Supabase (lazy)
        self._db = None

    @property
    def db(self):
        """Acceso lazy al DatabaseManager."""
        if self._db is None:
            from .database import get_database
            self._db = get_database()
        return self._db

    def cargar_perfil(self, nombre_asesor: str) -> AsesorProfile:
        """Carga perfil de asesor desde Supabase."""
        if self.db.disponible:
            perfil = self.db.obtener_perfil(nombre_asesor)
            if perfil:
                self.perfiles_cache[nombre_asesor] = perfil
                return perfil

        # Asesor sin datos aún (o Supabase no disponible)
        perfil = AsesorProfile(nombre=nombre_asesor)
        self.perfiles_cache[nombre_asesor] = perfil
        return perfil

    def registrar_evaluacion(
        self,
        nombre_asesor: str,
        resultado_evaluacion: Dict,
        transcripcion_path: Optional[str] = None,
        opportunity_id: Optional[str] = None,
        archivo_origen: Optional[str] = None,
        reporte_pdf_path: Optional[str] = None,
        stats: Optional[Dict] = None
    ):
        """
        Registra una nueva evaluación en el perfil del asesor.

        Args:
            nombre_asesor: Nombre del asesor evaluado
            resultado_evaluacion: Dict con resultados de CentauroOrchestrator
            transcripcion_path: Path al archivo de transcripción (solo para RAG, no se persiste en Supabase)
            opportunity_id: ID de oportunidad extraído del nombre de archivo
            archivo_origen: Nombre del archivo original
            reporte_pdf_path: Path al PDF del reporte generado
            stats: Dict con estadísticas de procesamiento
        """
        # ── Guardar en Supabase ──
        if self.db.disponible:
            asesor_id = self.db.registrar_asesor(nombre_asesor)
            if asesor_id:
                self.db.registrar_evaluacion(
                    asesor_id=asesor_id,
                    resultado_evaluacion=resultado_evaluacion,
                    opportunity_id=opportunity_id,
                    archivo_origen=archivo_origen,
                    reporte_pdf_path=reporte_pdf_path,
                    stats=stats
                )

        # Si es BUENO, indexar en RAG histórico como ejemplo de aprendizaje
        cal_global = resultado_evaluacion.get("calificacion_global")
        if cal_global == centauro_config.MIN_CALIFICACION_PARA_APRENDIZAJE:
            calificaciones_por_bloque = {}
            fortalezas = []
            areas_mejora = []
            for bloque_data in resultado_evaluacion.get("evaluacion_por_bloques", []):
                if isinstance(bloque_data, dict):
                    nombre_bloque = bloque_data.get("bloque", "")
                    cal = bloque_data.get("calificacion")
                    calificaciones_por_bloque[nombre_bloque] = cal
                    if cal == "BUENO":
                        fortalezas.append(nombre_bloque)
                    elif cal == "MALO":
                        areas_mejora.append(nombre_bloque)

            evaluacion = EvaluacionHistorica(
                fecha=datetime.now().isoformat(),
                asesor=nombre_asesor,
                calificacion_global=cal_global,
                calificaciones_por_bloque=calificaciones_por_bloque,
                fortalezas=fortalezas,
                areas_mejora=areas_mejora,
                transcripcion_path=transcripcion_path
            )
            self._agregar_a_rag_historico(evaluacion, transcripcion_path)

    def _agregar_a_rag_historico(self, evaluacion: EvaluacionHistorica, transcripcion_path: Optional[str]):
        """
        Añade conversación excelente al RAG de evaluaciones históricas.

        Solo se agregan conversaciones 4/5 o 5/5 para evitar saturación.
        """
        if not transcripcion_path or not Path(transcripcion_path).exists():
            return

        try:
            # Leer transcripción
            with open(transcripcion_path, 'r', encoding='utf-8') as f:
                transcripcion = f.read()

            # Chunking
            chunk_size = centauro_config.RAG_CHUNK_SIZE
            overlap = centauro_config.RAG_CHUNK_OVERLAP
            chunks = []

            for i in range(0, len(transcripcion), chunk_size - overlap):
                chunks.append(transcripcion[i : i + chunk_size])

            if not chunks:
                return

            # Verificar límite de conversaciones
            if collection_evaluaciones.count() >= centauro_config.MAX_CONVERSACIONES_EN_RAG:
                print(f"   ⚠️ RAG histórico lleno ({centauro_config.MAX_CONVERSACIONES_EN_RAG} conversaciones). Considerar limpieza.")
                return

            # Metadatos enriquecidos
            ids = [f"eval_{evaluacion.asesor}_{evaluacion.fecha}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "fuente": f"evaluacion_{evaluacion.asesor}",
                    "chunk_id": i,
                    "tipo": "evaluacion_historica",
                    "asesor": evaluacion.asesor,
                    "fecha": evaluacion.fecha,
                    "calificacion_global": evaluacion.calificacion_global or "BUENO",
                    "fortalezas": ",".join(evaluacion.fortalezas)
                }
                for i in range(len(chunks))
            ]

            # Añadir a colección
            collection_evaluaciones.upsert(
                ids=ids,
                documents=chunks,
                metadatas=metadatas
            )

            print(f"   ✅ Conversación excelente añadida al RAG histórico ({len(chunks)} fragmentos)")

        except Exception as e:
            print(f"   ⚠️ Error añadiendo conversación al RAG: {e}")

    def limpiar_datos_obsoletos(self):
        """
        Limpieza de datos obsoletos.
        Los datos viven en Supabase; la política de retención se gestiona allí.
        """
        pass

    def obtener_estadisticas_globales(self) -> Dict:
        """Genera estadísticas del sistema completo."""
        # Intentar Supabase primero
        if self.db.disponible:
            stats = self.db.obtener_estadisticas_globales()
            if stats:
                stats["conversaciones_en_rag"] = collection_evaluaciones.count()
                return stats

        return {"total_asesores": 0, "conversaciones_en_rag": collection_evaluaciones.count()}


# Instancia global
memory_manager = MemoryManager()
