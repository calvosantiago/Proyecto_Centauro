"""
Validaciones de archivos y paths para el sistema v4.0

Incluye validaciones específicas para:
- Longitud de nombres de archivo (límites de Windows)
- Caracteres especiales en nombres
- Paths demasiado largos

ACTUALIZADO v4.0: Usa configuración centralizada
"""
import re
from pathlib import Path
from typing import Tuple, Optional
from centauro.config import centauro_config


class ValidacionArchivo:
    """Resultado de validación de archivo"""
    def __init__(self, valido: bool, mensaje: str = "", sugerencia: str = ""):
        self.valido = valido
        self.mensaje = mensaje
        self.sugerencia = sugerencia

    def __bool__(self):
        return self.valido


def validar_nombre_archivo(
    ruta: Path,
    max_nombre: int = None,
    max_path: int = None
) -> ValidacionArchivo:
    """
    Valida que un archivo tenga nombre y path dentro de los límites seguros.

    Args:
        ruta: Path al archivo
        max_nombre: Longitud máxima del nombre (None = usar config)
        max_path: Longitud máxima del path (None = usar config)

    Returns:
        ValidacionArchivo con el resultado

    Ejemplos:
        >>> validacion = validar_nombre_archivo(Path("archivo.txt"))
        >>> if not validacion:
        ...     print(validacion.mensaje)
        ...     print(validacion.sugerencia)
    """
    # Usar valores de configuración si no se especifican
    if max_nombre is None:
        max_nombre = centauro_config.MAX_FILENAME_LENGTH
    if max_path is None:
        max_path = centauro_config.MAX_PATH_LENGTH
    nombre_archivo = ruta.name
    path_completo = str(ruta.absolute())

    # Validación 1: Nombre de archivo demasiado largo
    if len(nombre_archivo) > max_nombre:
        mensaje = (
            f"❌ ERROR: Nombre de archivo demasiado largo\n"
            f"   Archivo: {nombre_archivo[:80]}{'...' if len(nombre_archivo) > 80 else ''}\n"
            f"   Longitud: {len(nombre_archivo)} caracteres\n"
            f"   Máximo permitido: {max_nombre} caracteres"
        )

        # Sugerir nombre más corto
        palabras = nombre_archivo.replace('.vtt', '').replace('.txt', '').split()
        if len(palabras) > 3:
            nombre_sugerido = '_'.join(palabras[:3]) + ruta.suffix
        else:
            nombre_sugerido = nombre_archivo[:max_nombre-10] + ruta.suffix

        sugerencia = (
            f"💡 Sugerencia: Renombra el archivo a algo más corto\n"
            f"   Ejemplo: {nombre_sugerido}"
        )

        return ValidacionArchivo(False, mensaje, sugerencia)

    # Validación 2: Path completo demasiado largo (límite Windows)
    if len(path_completo) > max_path:
        mensaje = (
            f"❌ ERROR: Path completo demasiado largo\n"
            f"   Archivo: {nombre_archivo}\n"
            f"   Path: {path_completo[:100]}...\n"
            f"   Longitud: {len(path_completo)} caracteres\n"
            f"   Límite Windows: 260 caracteres"
        )

        sugerencia = (
            f"💡 Sugerencia: Renombra el archivo O mueve la carpeta del proyecto\n"
            f"   - Opción 1: Renombrar archivo más corto\n"
            f"   - Opción 2: Mover proyecto a C:\\Centauro\\ (path más corto)"
        )

        return ValidacionArchivo(False, mensaje, sugerencia)

    # Todo OK
    return ValidacionArchivo(True)


def validar_archivo_para_procesamiento(ruta: Path) -> ValidacionArchivo:
    """
    Validación específica para archivos que se van a procesar.

    Incluye validaciones adicionales como:
    - Extensión válida (.vtt, .txt, .docx)
    - Archivo existe
    - Archivo no está vacío
    """
    # Validar que existe
    if not ruta.exists():
        return ValidacionArchivo(
            False,
            f"❌ ERROR: El archivo no existe\n   Path: {ruta}",
            "💡 Verifica que el archivo esté en la ubicación correcta"
        )

    # Validar extensión
    extensiones_validas = {'.vtt', '.txt', '.docx', '.mp3', '.mp4'}
    if ruta.suffix.lower() not in extensiones_validas:
        return ValidacionArchivo(
            False,
            f"❌ ERROR: Extensión no soportada: {ruta.suffix}\n   Archivo: {ruta.name}",
            f"💡 Extensiones válidas: {', '.join(sorted(extensiones_validas))}"
        )

    # Validar que no esté vacío
    try:
        if ruta.stat().st_size == 0:
            return ValidacionArchivo(
                False,
                f"❌ ERROR: El archivo está vacío\n   Archivo: {ruta.name}",
                "💡 Verifica que el archivo tenga contenido"
            )
    except OSError:
        pass  # Si no se puede leer el tamaño, continuar

    # Validar longitud de nombre y path
    return validar_nombre_archivo(ruta)


def extraer_opportunity_id(filename: str) -> Optional[str]:
    """
    Extrae el ID de oportunidad del prefijo del nombre de archivo.

    Formato esperado: 2021-002579270_descripcion.ext
    El ID tiene el patrón: 4 dígitos de año, guión, 6-12 dígitos.
    Separadores aceptados tras el ID: "_", "-" o ".".

    Args:
        filename: Nombre del archivo (con o sin path)

    Returns:
        El ID de oportunidad (ej: "2021-002579270") o None si no tiene prefijo válido.

    Ejemplos:
        >>> extraer_opportunity_id("2021-002579270_entrevista_MBA.mp4")
        '2021-002579270'
        >>> extraer_opportunity_id("2021-002586934-entrevista.mp4")
        '2021-002586934'
        >>> extraer_opportunity_id("2021-002586934.entrevista.mp4")
        '2021-002586934'
        >>> extraer_opportunity_id("entrevista_sin_id.mp4")
        None
    """
    stem = Path(filename).stem
    match = re.match(r'^(\d{4}-\d{6,12})(?:[_\-.]|$)', stem)
    return match.group(1) if match else None


def generar_mensaje_error_usuario(validacion: ValidacionArchivo, contexto: str = "procesamiento") -> str:
    """
    Genera un mensaje de error amigable para mostrar al usuario (ej: en Chainlit).

    Args:
        validacion: Resultado de la validación
        contexto: Contexto del error ("procesamiento", "analisis", etc.)

    Returns:
        Mensaje formateado para mostrar al usuario
    """
    if validacion.valido:
        return ""

    mensaje_completo = f"⚠️ **Error en {contexto}**\n\n"
    mensaje_completo += validacion.mensaje + "\n\n"

    if validacion.sugerencia:
        mensaje_completo += validacion.sugerencia + "\n\n"

    mensaje_completo += (
        "---\n"
        "**¿Necesitas ayuda?**\n"
        "Contacta al equipo técnico si el problema persiste."
    )

    return mensaje_completo


# Ejemplos de uso
if __name__ == "__main__":
    # Test con nombre corto (válido)
    archivo_corto = Path("ejemplo.vtt")
    validacion = validar_nombre_archivo(archivo_corto)
    print(f"Archivo corto: {'✅ Válido' if validacion else '❌ Inválido'}")

    # Test con nombre largo (inválido)
    nombre_largo = "OBS Business School - Máster Executive MBA - Entrevista a Geraldine Manríquez Plaza sobre programa de formación.vtt"
    archivo_largo = Path(nombre_largo)
    validacion = validar_nombre_archivo(archivo_largo, max_nombre=100)

    if not validacion:
        print("\n" + validacion.mensaje)
        print(validacion.sugerencia)
