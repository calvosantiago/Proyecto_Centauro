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
import json
import statistics

from ..config import settings, centauro_config
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
    1. Persistir perfiles de asesores
    2. Añadir nuevas evaluaciones y actualizar perfiles
    3. Agregar conversaciones excelentes al RAG
    4. Limpiar datos obsoletos (rolling window)
    """

    def __init__(self):
        self.perfiles_dir = settings.OUTPUTS_DIR / "perfiles_asesores"
        self.perfiles_dir.mkdir(parents=True, exist_ok=True)
        self.perfiles_cache: Dict[str, AsesorProfile] = {}

    def cargar_perfil(self, nombre_asesor: str) -> AsesorProfile:
        """Carga perfil de asesor desde disco (o crea uno nuevo)"""
        # Normalizar nombre para archivo
        nombre_safe = nombre_asesor.replace(" ", "_").lower()
        perfil_path = self.perfiles_dir / f"{nombre_safe}.json"

        if perfil_path.exists():
            try:
                with open(perfil_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                perfil = AsesorProfile.from_dict(data)
                self.perfiles_cache[nombre_asesor] = perfil
                return perfil
            except Exception as e:
                print(f"⚠️ Error cargando perfil de {nombre_asesor}: {e}")

        # Crear nuevo perfil
        perfil = AsesorProfile(nombre=nombre_asesor)
        self.perfiles_cache[nombre_asesor] = perfil
        return perfil

    def guardar_perfil(self, perfil: AsesorProfile):
        """Persiste perfil a disco"""
        nombre_safe = perfil.nombre.replace(" ", "_").lower()
        perfil_path = self.perfiles_dir / f"{nombre_safe}.json"

        try:
            with open(perfil_path, 'w', encoding='utf-8') as f:
                json.dump(perfil.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error guardando perfil de {perfil.nombre}: {e}")

    def registrar_evaluacion(
        self,
        nombre_asesor: str,
        resultado_evaluacion: Dict,
        transcripcion_path: Optional[str] = None
    ):
        """
        Registra una nueva evaluación en el perfil del asesor.

        Args:
            nombre_asesor: Nombre del asesor evaluado
            resultado_evaluacion: Dict con resultados de CentauroOrchestrator
            transcripcion_path: Path al archivo de transcripción original
        """
        # Cargar perfil
        perfil = self.cargar_perfil(nombre_asesor)

        # Extraer datos de evaluación
        calificaciones_por_bloque = {}
        fortalezas = []
        areas_mejora = []

        # Iterar sobre los bloques en evaluacion_por_bloques
        bloques = resultado_evaluacion.get("evaluacion_por_bloques", [])
        for bloque_data in bloques:
            if isinstance(bloque_data, dict):
                nombre_bloque = bloque_data.get("bloque", "")
                cal = bloque_data.get("calificacion")
                calificaciones_por_bloque[nombre_bloque] = cal

                if cal == "BUENO":
                    fortalezas.append(nombre_bloque)
                elif cal == "MALO":
                    areas_mejora.append(nombre_bloque)

        # Calificación global del reporte
        cal_global = resultado_evaluacion.get("calificacion_global")

        # Crear registro histórico
        evaluacion = EvaluacionHistorica(
            fecha=datetime.now().isoformat(),
            asesor=nombre_asesor,
            calificacion_global=cal_global,
            calificaciones_por_bloque=calificaciones_por_bloque,
            fortalezas=fortalezas,
            areas_mejora=areas_mejora,
            transcripcion_path=transcripcion_path
        )

        # Añadir al perfil
        perfil.evaluaciones.append(evaluacion)

        # Actualizar estadísticas
        perfil.actualizar_estadisticas()

        # Guardar
        self.guardar_perfil(perfil)

        # Si es BUENO, considerar añadir al RAG como ejemplo de aprendizaje
        if cal_global == centauro_config.MIN_CALIFICACION_PARA_APRENDIZAJE:
            self._agregar_a_rag_historico(evaluacion, transcripcion_path)

        return perfil

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
        Limpia evaluaciones más antiguas que ROLLING_WINDOW_DIAS.

        Mantiene solo últimos 6 meses de datos para evitar saturación.
        """
        fecha_limite = datetime.now() - timedelta(days=centauro_config.ROLLING_WINDOW_DIAS)

        for nombre_asesor in self.perfiles_cache.keys():
            perfil = self.cargar_perfil(nombre_asesor)

            # Filtrar evaluaciones recientes
            evaluaciones_recientes = [
                e for e in perfil.evaluaciones
                if datetime.fromisoformat(e.fecha) > fecha_limite
            ]

            if len(evaluaciones_recientes) < len(perfil.evaluaciones):
                print(f"   🧹 {perfil.nombre}: {len(perfil.evaluaciones) - len(evaluaciones_recientes)} evaluaciones antiguas eliminadas")
                perfil.evaluaciones = evaluaciones_recientes
                perfil.actualizar_estadisticas()
                self.guardar_perfil(perfil)

    def obtener_estadisticas_globales(self) -> Dict:
        """Genera estadísticas del sistema completo"""
        # Cargar todos los perfiles
        perfiles = []
        for archivo in self.perfiles_dir.glob("*.json"):
            try:
                with open(archivo, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                perfil = AsesorProfile.from_dict(data)
                perfiles.append(perfil)
            except:
                continue

        if not perfiles:
            return {"total_asesores": 0}

        # Calcular estadísticas
        from collections import Counter
        total_evaluaciones = sum(p.total_evaluaciones for p in perfiles)

        mejorando = [p for p in perfiles if p.tendencia_global == "mejorando"]
        empeorando = [p for p in perfiles if p.tendencia_global == "empeorando"]

        return {
            "total_asesores": len(perfiles),
            "total_evaluaciones": total_evaluaciones,
            "asesores_mejorando": len(mejorando),
            "asesores_empeorando": len(empeorando),
            "conversaciones_en_rag": collection_evaluaciones.count()
        }


# Instancia global
memory_manager = MemoryManager()
