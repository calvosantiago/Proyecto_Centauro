"""
Procesador de Buenas Prácticas v1.0

Este script procesa ejemplos de conversaciones exitosas (.vtt)
y las prepara para que el Sheriff las use como REFERENCIA,
no como reglas rígidas.

FILOSOFÍA:
- Los ejemplos son INSPIRACIÓN, no plantillas obligatorias
- Detecta PATRONES de éxito (preguntas abiertas, escucha activa, etc.)
- El Sheriff puede citar ejemplos en el feedback: "Mira cómo lo hizo aquí..."

ESTRUCTURA ESPERADA:
    inputs/buenas_practicas/
    ├── investigacion/
    │   ├── ejemplo_001.vtt
    │   ├── ejemplo_002.vtt
    │   └── ...
    ├── cierre/
    ├── proximos_pasos/
    └── ...

USO:
    python -m centauro.tools.procesar_buenas_practicas
"""
import os
import re
import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

# Importaciones del proyecto
try:
    from ..llm_client import consultar_gpt
    from ..config import settings
    from .mapeo_secciones import obtener_agente_para_carpeta, validar_estructura_carpetas, crear_carpetas_faltantes
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from centauro.llm_client import consultar_gpt
    from centauro.config import settings
    from centauro.tools.mapeo_secciones import obtener_agente_para_carpeta, validar_estructura_carpetas, crear_carpetas_faltantes


@dataclass
class EjemploConversacion:
    """Representa un ejemplo de buena práctica"""
    seccion: str  # investigacion, cierre, proximos_pasos, etc.
    nombre_archivo: str

    # Conversación
    transcripcion_completa: str
    turnos_conversacion: List[Dict]  # [{"speaker": "agente", "texto": "..."}]

    # Análisis automático
    patrones_detectados: List[str]  # ["pregunta_abierta", "escucha_activa", ...]
    tecnicas_usadas: List[str]  # ["exploracion_contexto", "personalizacion", ...]
    fragmentos_destacados: List[Dict]  # [{"texto": "...", "por_que": "..."}]

    # Metadatos
    duracion_aproximada: str  # "5 min"
    puntuacion_estimada: str  # "5/5" (si está disponible)

    def to_texto_indexable(self) -> str:
        """
        Convierte el ejemplo en texto optimizado para RAG.

        El Sheriff buscará ejemplos similares cuando analice conversaciones.
        """
        secciones = []

        # Cabecera
        secciones.append(f"=== EJEMPLO DE BUENA PRÁCTICA: {self.seccion.upper()} ===")
        secciones.append(f"Archivo: {self.nombre_archivo}")
        if self.duracion_aproximada:
            secciones.append(f"Duración: {self.duracion_aproximada}")
        if self.puntuacion_estimada:
            secciones.append(f"Puntuación: {self.puntuacion_estimada}")
        secciones.append("")

        # Patrones clave (para búsqueda semántica)
        if self.patrones_detectados:
            secciones.append("PATRONES DETECTADOS:")
            for patron in self.patrones_detectados:
                secciones.append(f"  ✓ {patron}")
            secciones.append("")

        # Técnicas usadas
        if self.tecnicas_usadas:
            secciones.append("TÉCNICAS USADAS:")
            for tecnica in self.tecnicas_usadas:
                secciones.append(f"  • {tecnica}")
            secciones.append("")

        # Fragmentos destacados (lo más importante)
        if self.fragmentos_destacados:
            secciones.append("FRAGMENTOS DESTACADOS:")
            for i, fragmento in enumerate(self.fragmentos_destacados, 1):
                secciones.append(f"\n  [{i}] {fragmento['texto']}")
                secciones.append(f"      → Por qué funciona: {fragmento['por_que']}")
            secciones.append("")

        # Conversación completa (para contexto)
        secciones.append("--- CONVERSACIÓN COMPLETA ---")
        for turno in self.turnos_conversacion[:20]:  # Max 20 turnos para no saturar
            speaker = turno['speaker'].upper()
            texto = turno['texto']
            secciones.append(f"{speaker}: {texto}")

        if len(self.turnos_conversacion) > 20:
            secciones.append(f"\n[... {len(self.turnos_conversacion) - 20} turnos más ...]")

        return "\n".join(secciones)


class BuenasPracticasProcessor:
    """
    Procesador de ejemplos de buenas prácticas desde archivos .vtt
    """

    def __init__(self, carpeta_base: Path):
        self.carpeta_base = Path(carpeta_base)
        self.ejemplos_procesados: List[EjemploConversacion] = []

    def procesar_todos(self) -> List[EjemploConversacion]:
        """
        Procesa todos los .vtt en las subcarpetas (por sección).

        Estructura esperada:
            buenas_practicas/
            ├── investigacion/*.vtt
            ├── admision_economica/*.vtt
            ├── objeciones/*.vtt
            ├── cierre_proximos_pasos/*.vtt
            ├── propuesta_valor/*.vtt
            └── estilo_comunicacion/*.vtt
        """
        if not self.carpeta_base.exists():
            print(f"⚠️ Carpeta no existe: {self.carpeta_base}")
            print(f"   Creándola con estructura oficial...")
            crear_carpetas_faltantes(self.carpeta_base)
            print(f"✅ Estructura creada. Coloca tus archivos .vtt en las carpetas")
            return []

        # Validar que existan todas las carpetas necesarias
        todas_ok, faltantes = validar_estructura_carpetas(self.carpeta_base)
        if not todas_ok:
            print(f"⚠️ Carpetas faltantes: {', '.join(faltantes)}")
            print(f"   Creándolas...")
            crear_carpetas_faltantes(self.carpeta_base)
            print(f"✅ Estructura completada")

        # Buscar todos los .vtt en subcarpetas
        archivos_vtt = list(self.carpeta_base.rglob("*.vtt"))

        if not archivos_vtt:
            print(f"⚠️ No se encontraron archivos .vtt en {self.carpeta_base}")
            return []

        print(f"📚 Encontrados {len(archivos_vtt)} ejemplos para procesar")
        print("="*60)

        for archivo_vtt in archivos_vtt:
            try:
                # VALIDACIÓN 1: Verificar longitud del nombre de archivo
                nombre_archivo = archivo_vtt.name
                longitud_path = len(str(archivo_vtt))

                if len(nombre_archivo) > 100:
                    print(f"\n❌ ERROR: Nombre de archivo demasiado largo")
                    print(f"   Archivo: {nombre_archivo[:80]}...")
                    print(f"   Longitud: {len(nombre_archivo)} caracteres")
                    print(f"   Máximo recomendado: 100 caracteres")
                    print(f"   Acción: Renombra el archivo a algo más corto")
                    print(f"   Ejemplo: {nombre_archivo[:30].split()[0]}_ejemplo.vtt")
                    continue

                if longitud_path > 240:
                    print(f"\n❌ ERROR: Path completo demasiado largo")
                    print(f"   Archivo: {nombre_archivo}")
                    print(f"   Path completo: {longitud_path} caracteres")
                    print(f"   Límite Windows: 260 caracteres")
                    print(f"   Acción: Renombra el archivo o mueve la carpeta a un path más corto")
                    continue

                # VALIDACIÓN 2: Determinar sección por carpeta padre usando el mapeo oficial
                nombre_carpeta = archivo_vtt.parent.name

                try:
                    seccion_oficial = obtener_agente_para_carpeta(nombre_carpeta)
                except ValueError as e:
                    print(f"\n⚠️ {archivo_vtt.name}: Carpeta '{nombre_carpeta}' no reconocida. Ignorando.")
                    continue

                print(f"\n📄 Procesando: {archivo_vtt.name} [{seccion_oficial}]")
                ejemplo = self.procesar_vtt(archivo_vtt, seccion_oficial)

                if ejemplo:
                    self.ejemplos_procesados.append(ejemplo)
                    print(f"   ✅ Procesado: {len(ejemplo.patrones_detectados)} patrones detectados")

            except Exception as e:
                print(f"   ❌ Error: {e}")

        print(f"\n{'='*60}")
        print(f"✅ Procesados {len(self.ejemplos_procesados)} ejemplos")

        return self.ejemplos_procesados

    def procesar_vtt(self, ruta_vtt: Path, seccion: str) -> Optional[EjemploConversacion]:
        """
        Procesa un archivo .vtt individual.

        1. Parse del .vtt → transcripción limpia
        2. Análisis con LLM → patrones y técnicas
        3. Extracción de fragmentos destacados
        """
        # 1. Parsear VTT
        transcripcion, turnos = self._parse_vtt(ruta_vtt)

        if not transcripcion:
            print(f"   ⚠️ Archivo vacío o mal formateado")
            return None

        # 2. Analizar con LLM para detectar patrones
        analisis = self._analizar_con_llm(transcripcion, seccion)

        if not analisis:
            print(f"   ⚠️ Error en análisis LLM")
            return None

        # 3. Crear objeto EjemploConversacion
        return EjemploConversacion(
            seccion=seccion,
            nombre_archivo=ruta_vtt.name,
            transcripcion_completa=transcripcion,
            turnos_conversacion=turnos,
            patrones_detectados=analisis.get("patrones", []),
            tecnicas_usadas=analisis.get("tecnicas", []),
            fragmentos_destacados=analisis.get("fragmentos", []),
            duracion_aproximada=analisis.get("duracion", ""),
            puntuacion_estimada=analisis.get("puntuacion", "5/5")
        )

    def _parse_vtt(self, ruta: Path) -> tuple[str, List[Dict]]:
        """
        Parsea archivo .vtt y extrae la conversación.

        Formato VTT típico:
            WEBVTT

            00:00:05.000 --> 00:00:08.000
            Agente: Hola, ¿en qué puedo ayudarte?

            00:00:08.000 --> 00:00:12.000
            Alumno: Estoy buscando información sobre el MBA...
        """
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                contenido = f.read()
        except UnicodeDecodeError:
            # Probar con latin-1 si utf-8 falla
            with open(ruta, 'r', encoding='latin-1') as f:
                contenido = f.read()

        # Eliminar encabezado WEBVTT y timestamps
        lineas = contenido.split('\n')
        texto_limpio = []
        turnos = []

        for linea in lineas:
            linea = linea.strip()

            # Saltar líneas vacías, timestamps y WEBVTT
            if not linea or linea.startswith('WEBVTT') or '-->' in linea:
                continue

            # Saltar números de secuencia
            if linea.isdigit():
                continue

            texto_limpio.append(linea)

            # Detectar speaker si está en formato "Speaker: texto"
            if ':' in linea and len(linea.split(':', 1)[0].split()) <= 2:
                partes = linea.split(':', 1)
                speaker = partes[0].strip().lower()
                texto = partes[1].strip()

                # Normalizar nombres de speakers
                if 'agente' in speaker or 'comercial' in speaker or 'asesor' in speaker:
                    speaker = 'agente'
                elif 'alumno' in speaker or 'estudiante' in speaker or 'cliente' in speaker:
                    speaker = 'alumno'
                else:
                    speaker = 'desconocido'

                turnos.append({"speaker": speaker, "texto": texto})
            else:
                # Si no hay speaker explícito, añadir como continuación
                if turnos:
                    turnos[-1]["texto"] += " " + linea
                else:
                    turnos.append({"speaker": "desconocido", "texto": linea})

        transcripcion = '\n'.join(texto_limpio)
        return transcripcion, turnos

    def _analizar_con_llm(self, transcripcion: str, seccion: str) -> Optional[Dict]:
        """
        Usa LLM para analizar la conversación y detectar patrones de éxito.
        """
        # Truncar si es muy largo
        if len(transcripcion) > 8000:
            transcripcion = transcripcion[:8000] + "\n\n[... conversación truncada ...]"

        prompt_sistema = f"""
Eres un experto en analizar conversaciones comerciales de programas educativos.

Analiza esta conversación de la sección "{seccion}" e identifica:

1. PATRONES de comunicación exitosa (3-5 patrones):
   - Ejemplos: "pregunta_abierta", "escucha_activa", "reformulacion", "empatia",
     "exploracion_profunda", "personalizacion", "vincular_con_objetivos"

2. TÉCNICAS específicas usadas (3-5 técnicas):
   - Ejemplos: "Preguntó sobre experiencia laboral actual",
     "Exploró objetivos profesionales a 2-3 años",
     "Conectó programa con aspiraciones del alumno",
     "Usó ejemplos concretos de otros alumnos"

3. FRAGMENTOS destacados (2-4 fragmentos):
   - Cita textual del agente que ejemplifica buena práctica
   - Explicación breve de por qué funciona

4. DURACIÓN aproximada: "5 min", "10 min", etc.

5. PUNTUACIÓN estimada: "5/5", "4/5", etc. (asume que es buena práctica)

FORMATO JSON OBLIGATORIO:
{{
  "patrones": ["patron1", "patron2", ...],
  "tecnicas": ["tecnica1", "tecnica2", ...],
  "fragmentos": [
    {{"texto": "cita textual del agente", "por_que": "explicación"}},
    ...
  ],
  "duracion": "X min",
  "puntuacion": "5/5"
}}

Sé ESPECÍFICO y CONCRETO. Los patrones y técnicas deben ser accionables.
"""

        try:
            resp = consultar_gpt(
                prompt_sistema,
                f"CONVERSACIÓN [{seccion.upper()}]:\n\n{transcripcion}",
                f"buena_practica_{seccion}"
            )

            # Extraer JSON de la respuesta
            # A veces GPT envuelve el JSON en ```json ... ```
            if "```json" in resp:
                resp = resp.split("```json")[1].split("```")[0].strip()
            elif "```" in resp:
                resp = resp.split("```")[1].split("```")[0].strip()

            data = json.loads(resp)
            return data

        except Exception as e:
            print(f"   ⚠️ Error LLM: {e}")
            return None

    def exportar_para_rag(self, ruta_salida: Path = None):
        """
        Exporta ejemplos procesados para que el Sheriff los pueda consultar.

        Los ejemplos se guardan en: inputs/docs/buenas_practicas/
        """
        if ruta_salida is None:
            ruta_salida = settings.INPUTS_DIR / "docs" / "buenas_practicas"

        ruta_salida.mkdir(parents=True, exist_ok=True)

        print(f"\n📤 Exportando {len(self.ejemplos_procesados)} ejemplos para RAG...")

        for idx, ejemplo in enumerate(self.ejemplos_procesados, 1):
            # Obtener carpeta segura desde el mapeo
            from .mapeo_secciones import MAPEO_AGENTE_A_CARPETA
            carpeta_safe = MAPEO_AGENTE_A_CARPETA.get(ejemplo.seccion, "otros")

            # Nombre de archivo CORTO (para evitar límite de 260 chars de Windows)
            # Formato: carpeta_ejemplo_001.txt
            nombre_archivo_corto = f"{carpeta_safe}_ejemplo_{idx:03d}.txt"
            ruta_archivo = ruta_salida / nombre_archivo_corto

            # Verificar longitud del path completo
            if len(str(ruta_archivo)) > 250:
                # Fallback: nombre ultra-corto
                nombre_archivo_corto = f"{carpeta_safe}_{idx:03d}.txt"
                ruta_archivo = ruta_salida / nombre_archivo_corto

            try:
                with open(ruta_archivo, 'w', encoding='utf-8') as f:
                    f.write(ejemplo.to_texto_indexable())
                print(f"   💾 {nombre_archivo_corto}")
            except OSError as e:
                print(f"   ❌ Error guardando {nombre_archivo_corto}: {e}")
                # Intentar con nombre aún más corto
                nombre_ultra_corto = f"{carpeta_safe[:3]}_{idx:03d}.txt"
                ruta_archivo = ruta_salida / nombre_ultra_corto
                try:
                    with open(ruta_archivo, 'w', encoding='utf-8') as f:
                        f.write(ejemplo.to_texto_indexable())
                    print(f"   💾 {nombre_ultra_corto} (nombre acortado)")
                except OSError as e2:
                    print(f"   ❌ No se pudo guardar: {e2}")

        print(f"\n✅ Exportación completada en: {ruta_salida}")
        print("   Ejecuta 'python main.py' para re-indexar el RAG")
        print("\n💡 El Sheriff ahora podrá citar estos ejemplos en su feedback")


def main():
    """
    Punto de entrada del script.

    Uso:
        python -m centauro.tools.procesar_buenas_practicas
        python -m centauro.tools.procesar_buenas_practicas --carpeta /ruta/
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Procesa ejemplos de buenas prácticas (.vtt) para RAG"
    )
    parser.add_argument(
        "--carpeta",
        type=str,
        default="inputs/buenas_practicas",
        help="Carpeta con los ejemplos (default: inputs/buenas_practicas)"
    )
    parser.add_argument(
        "--salida",
        type=str,
        default=None,
        help="Carpeta de salida (default: inputs/docs/buenas_practicas)"
    )

    args = parser.parse_args()

    # Procesar
    carpeta = Path(args.carpeta)
    processor = BuenasPracticasProcessor(carpeta)
    ejemplos = processor.procesar_todos()

    if ejemplos:
        salida = Path(args.salida) if args.salida else None
        processor.exportar_para_rag(salida)
    else:
        print("\n💡 PRÓXIMOS PASOS:")
        print(f"   1. Coloca tus archivos .vtt en: {carpeta}")
        print(f"   2. Organízalos en subcarpetas: investigacion/, cierre/, etc.")
        print(f"   3. Vuelve a ejecutar este script")


if __name__ == "__main__":
    main()
