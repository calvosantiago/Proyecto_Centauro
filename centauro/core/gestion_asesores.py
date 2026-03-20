"""
Sistema de Gestión de Asesores v4.0

Responsabilidades:
1. Detección inteligente de nombres de asesores
2. Normalización de nombres (con/sin acentos, abreviaturas)
3. Fuzzy matching para evitar duplicados
4. Sugerencias de nombres similares
"""
import re
from typing import Optional, List, Tuple
from pathlib import Path
from rapidfuzz import fuzz, process


class GestionAsesores:
    """
    Gestiona la identificación y normalización de nombres de asesores.

    Características:
    - Fuzzy matching con umbral configurable
    - Normalización de acentos y mayúsculas
    - Detección de duplicados potenciales
    - Base de datos de asesores conocidos
    """

    def __init__(self, umbral_similitud: int = 85):
        """
        Args:
            umbral_similitud: Umbral para considerar nombres similares (0-100)
                             85 = suficientemente similar para alertar
        """
        self.umbral_similitud = umbral_similitud
        self.asesores_conocidos: List[str] = []
        self._cargar_asesores_conocidos()

    def _cargar_asesores_conocidos(self):
        """Carga lista de asesores desde Supabase (o JSON como fallback)."""
        import json
        try:
            # Intentar Supabase primero
            from .database import get_database
            db = get_database()

            if db.disponible:
                asesores = db.listar_asesores()
                for asesor in asesores:
                    nombre = asesor.get('nombre', '').strip()
                    if nombre and self._es_nombre_valido(nombre):
                        self.asesores_conocidos.append(nombre)
                if self.asesores_conocidos:
                    return

            # Fallback: JSON local
            from .memoria import memory_manager

            perfiles_dir = memory_manager.perfiles_dir

            if perfiles_dir.exists():
                for archivo in perfiles_dir.glob("*.json"):
                    try:
                        with open(archivo, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        nombre = data.get('nombre', '').strip()
                        if nombre and self._es_nombre_valido(nombre):
                            self.asesores_conocidos.append(nombre)
                    except Exception:
                        nombre_legible = archivo.stem.replace('_', ' ').title()
                        self.asesores_conocidos.append(nombre_legible)
        except Exception as e:
            print(f"   ⚠️ No se pudieron cargar asesores conocidos: {e}")

    def normalizar_nombre(self, nombre: str) -> str:
        """
        Normaliza un nombre para comparación.

        Ejemplo:
            "Juan Pérez" → "juan perez"
            "MARÍA LÓPEZ" → "maria lopez"
        """
        # Quitar acentos
        import unicodedata
        nombre_sin_acentos = ''.join(
            c for c in unicodedata.normalize('NFD', nombre)
            if unicodedata.category(c) != 'Mn'
        )

        # Minúsculas y espacios normalizados
        nombre_normalizado = ' '.join(nombre_sin_acentos.lower().split())

        return nombre_normalizado

    def extraer_nombre_de_transcripcion(self, transcripcion: str) -> Optional[str]:
        """
        Intenta extraer el nombre del asesor de la transcripción.

        Busca patrones como:
        - "Mi nombre es Juan Pérez"
        - "Soy María López"
        - "[ASESOR]: Juan Pérez habla..."
        """
        # Solo buscar en los primeros 2000 caracteres (apertura)
        inicio = transcripcion[:2000]

        patrones = [
            # "Mi nombre es Juan Pérez"
            r'[Mm]i nombre es ([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?: [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)',

            # "Soy Juan Pérez"
            r'[Ss]oy ([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?: [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)',

            # "Me llamo Juan Pérez"
            r'[Mm]e llamo ([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?: [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)',

            # "[ASESOR]: Juan" o "[Juan Pérez]:"
            r'\[(?:ASESOR|([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?: [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+))\]:',
        ]

        for patron in patrones:
            matches = re.findall(patron, inicio)
            if matches:
                # Tomar primer match que sea un nombre válido
                for match in matches:
                    nombre = match if isinstance(match, str) else match[0]
                    if self._es_nombre_valido(nombre):
                        return nombre.strip()

        return None

    def _es_nombre_valido(self, nombre: str) -> bool:
        """
        Verifica si un string parece un nombre real.

        Criterios:
        - Al menos 2 palabras (nombre + apellido)
        - No contiene números
        - Primera letra mayúscula
        - Longitud razonable (5-50 chars)
        """
        if not nombre:
            return False

        # Longitud
        if len(nombre) < 5 or len(nombre) > 50:
            return False

        # Al menos 2 palabras
        palabras = nombre.split()
        if len(palabras) < 2:
            return False

        # No números
        if any(char.isdigit() for char in nombre):
            return False

        # Primera letra mayúscula en cada palabra
        # Excepción: partículas de apellidos compuestos pueden ir en minúscula
        # Ejemplos: "de la Torre", "del Valle", "van der Berg"
        PARTICULAS = {'de', 'del', 'la', 'los', 'las', 'el', 'van', 'von', 'y'}
        if not all(p[0].isupper() for p in palabras if p and p.lower() not in PARTICULAS):
            return False

        # No palabras sospechosas
        palabras_invalidas = {'llamada', 'entrevista', 'reunion', 'obs', 'master', 'mba', 'zoom', 'teams'}
        if any(p.lower() in palabras_invalidas for p in palabras):
            return False

        return True

    def buscar_asesor_similar(self, nombre: str) -> Optional[Tuple[str, int]]:
        """
        Busca si existe un asesor con nombre similar en la base.

        Args:
            nombre: Nombre a buscar

        Returns:
            Tupla (nombre_encontrado, score_similitud) si hay match
            None si no hay match suficientemente similar
        """
        if not self.asesores_conocidos:
            return None

        nombre_norm = self.normalizar_nombre(nombre)
        norms_conocidos = [self.normalizar_nombre(a) for a in self.asesores_conocidos]

        # ── Búsqueda 1: fuzzy ratio estándar (acentos, typos) ────────────────
        mejor_match = process.extractOne(
            nombre_norm,
            norms_conocidos,
            scorer=fuzz.ratio
        )
        if mejor_match and mejor_match[1] >= self.umbral_similitud:
            idx = norms_conocidos.index(mejor_match[0])
            return (self.asesores_conocidos[idx], mejor_match[1])

        # ── Búsqueda 2: prefijo de tokens ────────────────────────────────────
        # Detecta que "Aleix Ribas" es el mismo que "Aleix Ribas Canadell"
        # porque los primeros N tokens coinciden en orden.
        # NO confunde "Juan García" con "Juan Pérez García" (token 2 difiere).
        tokens_entrada = nombre_norm.split()
        n_entrada = len(tokens_entrada)
        for idx, norm_conocido in enumerate(norms_conocidos):
            tokens_conocido = norm_conocido.split()
            n_conocido = len(tokens_conocido)
            # El nombre de entrada es prefijo del conocido (sin segundo apellido)
            if n_conocido > n_entrada >= 2 and tokens_conocido[:n_entrada] == tokens_entrada:
                return (self.asesores_conocidos[idx], 95)
            # El conocido es prefijo del nombre de entrada (nombre completo nuevo)
            if n_entrada > n_conocido >= 2 and tokens_entrada[:n_conocido] == tokens_conocido:
                return (self.asesores_conocidos[idx], 95)

        return None

    def sugerir_nombres_similares(self, nombre: str, top_n: int = 3) -> List[Tuple[str, int]]:
        """
        Devuelve los N nombres más similares de la base.

        Útil para mostrar sugerencias al usuario.
        """
        if not self.asesores_conocidos:
            return []

        nombre_norm = self.normalizar_nombre(nombre)

        matches = process.extract(
            nombre_norm,
            [self.normalizar_nombre(a) for a in self.asesores_conocidos],
            scorer=fuzz.ratio,
            limit=top_n
        )

        resultados = []
        for match_norm, score in matches:
            if score >= 70:  # Umbral mínimo para sugerir
                # Encontrar nombre original
                idx = [self.normalizar_nombre(a) for a in self.asesores_conocidos].index(match_norm)
                nombre_original = self.asesores_conocidos[idx]
                resultados.append((nombre_original, score))

        return resultados

    def validar_y_normalizar(self, nombre: str) -> Tuple[str, Optional[str], Optional[int]]:
        """
        Valida un nombre y busca si ya existe uno similar.

        Returns:
            Tupla (nombre_normalizado, nombre_existente_similar, score_similitud)

        Ejemplos:
            "Juan Perez" → ("Juan Perez", "Juan Pérez", 95)  # Existe similar
            "María Nueva" → ("María Nueva", None, None)       # Nueva
        """
        # Validar formato
        if not self._es_nombre_valido(nombre):
            raise ValueError(f"Nombre inválido: '{nombre}'")

        # Normalizar formato (Title Case)
        nombre_normalizado = ' '.join(p.capitalize() for p in nombre.split())

        # Buscar similar
        similar = self.buscar_asesor_similar(nombre_normalizado)

        if similar:
            return (nombre_normalizado, similar[0], similar[1])
        else:
            return (nombre_normalizado, None, None)

    def es_mismo_asesor(self, nombre1: str, nombre2: str) -> bool:
        """
        Determina si dos nombres se refieren al mismo asesor.

        Casos manejados:
        - "Juan Pérez" vs "Juan Perez" → True (sin acentos)
        - "Juan Pérez López" vs "Juan Pérez" → True (nombre completo vs abreviado)
        - "Juan Pérez" vs "María López" → False (diferentes personas)
        - "Juan Pérez" vs "Juan García" → False (mismo nombre, diferente apellido)
        """
        norm1 = self.normalizar_nombre(nombre1)
        norm2 = self.normalizar_nombre(nombre2)

        # Similitud alta = mismo asesor
        similitud = fuzz.ratio(norm1, norm2)

        if similitud >= self.umbral_similitud:
            return True

        # Caso especial: uno contiene al otro (nombre completo vs abreviado)
        # "Juan Pérez" está contenido en "Juan Pérez López"
        palabras1 = set(norm1.split())
        palabras2 = set(norm2.split())

        # Si todas las palabras del más corto están en el más largo
        if palabras1.issubset(palabras2) or palabras2.issubset(palabras1):
            # Pero NO si solo comparten el nombre de pila
            # "Juan Pérez" y "Juan García" comparten "Juan" pero NO son la misma persona
            if len(palabras1.intersection(palabras2)) >= 2:
                return True

        return False

    def obtener_nombre_canonico(self, nombre: str) -> str:
        """
        Devuelve la versión "canónica" del nombre para usar en perfiles.

        Si existe un asesor similar, devuelve ese nombre.
        Si no, devuelve el nombre normalizado.
        """
        resultado = self.validar_y_normalizar(nombre)
        nombre_normalizado, nombre_existente, score = resultado

        if nombre_existente and score >= self.umbral_similitud:
            return nombre_existente
        else:
            return nombre_normalizado


# Instancia global
gestion_asesores = GestionAsesores()
