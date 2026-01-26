"""
Procesador de Dossiers de Programas v1.0

Este script procesa los dossiers de los ~30 programas de OBS
y los prepara para el RAG de forma optimizada.

PROBLEMA: 30 programas × 50 páginas = 1,500 páginas
SOLUCIÓN: Extraer solo lo ÚNICO de cada programa (~5-10 págs útiles)

METÁFORA: Es como hacer un "resumen ejecutivo" de cada programa,
eliminando toda la información genérica de OBS que ya está en
los manuales principales.

USO:
    python -m centauro.tools.procesar_dossiers --carpeta inputs/dossiers/

ESTRUCTURA ESPERADA:
    inputs/dossiers/
    ├── MBA_Executive.pdf
    ├── Master_Marketing_Digital.pdf
    ├── Master_Project_Management.pdf
    └── ...
"""
import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

# Importaciones del proyecto
try:
    from ..llm_client import consultar_gpt
    from ..config import settings
except ImportError:
    # Si se ejecuta como script independiente
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from centauro.llm_client import consultar_gpt
    from centauro.config import settings


@dataclass
class ProgramaInfo:
    """Información estructurada de un programa"""
    nombre_programa: str
    tipo: str  # MBA | Master | Postgrado
    area: str  # Marketing | Finanzas | Tech | etc.
    
    # Contenido único
    plan_estudios: List[str]  # Lista de módulos
    duracion: str
    creditos_ects: int
    
    # Diferenciadores
    certificaciones_incluidas: List[str]
    herramientas_software: List[str]
    salidas_profesionales: List[str]
    
    # Profesorado destacado (solo del programa)
    profesores_clave: List[Dict]
    
    # Alumni destacados (solo del programa)
    casos_exito: List[str]
    
    # Precio (si es específico)
    precio_aproximado: str
    
    def to_texto_indexable(self) -> str:
        """
        Convierte la info del programa a texto optimizado para indexar en RAG.
        
        Este texto se dividirá en chunks y se añadirá a ChromaDB.
        """
        secciones = []
        
        # Cabecera con metadatos
        secciones.append(f"=== PROGRAMA: {self.nombre_programa} ===")
        secciones.append(f"Tipo: {self.tipo} | Área: {self.area}")
        secciones.append(f"Duración: {self.duracion} | Créditos: {self.creditos_ects} ECTS")
        secciones.append("")
        
        # Plan de estudios
        if self.plan_estudios:
            secciones.append("PLAN DE ESTUDIOS:")
            for i, modulo in enumerate(self.plan_estudios, 1):
                secciones.append(f"  Módulo {i}: {modulo}")
            secciones.append("")
        
        # Certificaciones
        if self.certificaciones_incluidas:
            secciones.append("CERTIFICACIONES INCLUIDAS:")
            for cert in self.certificaciones_incluidas:
                secciones.append(f"  • {cert}")
            secciones.append("")
        
        # Herramientas
        if self.herramientas_software:
            secciones.append("HERRAMIENTAS Y SOFTWARE:")
            secciones.append(f"  {', '.join(self.herramientas_software)}")
            secciones.append("")
        
        # Salidas profesionales
        if self.salidas_profesionales:
            secciones.append("SALIDAS PROFESIONALES:")
            for salida in self.salidas_profesionales:
                secciones.append(f"  • {salida}")
            secciones.append("")
        
        # Profesorado
        if self.profesores_clave:
            secciones.append("PROFESORADO DESTACADO:")
            for prof in self.profesores_clave[:5]:  # Max 5
                nombre = prof.get("nombre", "")
                cargo = prof.get("cargo", "")
                empresa = prof.get("empresa", "")
                secciones.append(f"  • {nombre} - {cargo} en {empresa}")
            secciones.append("")
        
        # Casos de éxito
        if self.casos_exito:
            secciones.append("CASOS DE ÉXITO / ALUMNI:")
            for caso in self.casos_exito[:3]:  # Max 3
                secciones.append(f"  • {caso}")
            secciones.append("")
        
        # Precio
        if self.precio_aproximado:
            secciones.append(f"INVERSIÓN: {self.precio_aproximado}")
        
        return "\n".join(secciones)


class DossierProcessor:
    """
    Procesador de dossiers que extrae solo la información ÚNICA de cada programa.
    
    Filtra automáticamente:
    - Información genérica de OBS (ya está en manuales)
    - Portadas y diseño
    - Rankings repetidos
    - Metodología (es igual para todos)
    """
    
    # Secciones a IGNORAR (ya están en los manuales generales)
    SECCIONES_IGNORAR = [
        "sobre obs",
        "nuestra metodología",
        "metodología online",
        "universidad de barcelona",
        "grupo planeta",
        "rankings",
        "acreditaciones",
        "campus virtual",
        "blackboard",
        "alumni obs",
        "comunidad alumni",
        "programa de becas",  # Genérico
        "formas de pago",  # Genérico
        "proceso de admisión",  # Genérico
    ]
    
    # Secciones a EXTRAER (únicas por programa)
    SECCIONES_EXTRAER = [
        "plan de estudios",
        "módulos",
        "temario",
        "objetivos del programa",
        "competencias",
        "salidas profesionales",
        "perfil del alumno",
        "certificaciones",
        "herramientas",
        "software",
        "profesorado",
        "claustro",
        "director del programa",
        "testimonios",
        "casos de éxito",
    ]
    
    def __init__(self, carpeta_dossiers: Path):
        self.carpeta_dossiers = Path(carpeta_dossiers)
        self.programas_procesados: List[ProgramaInfo] = []
        
    def procesar_todos(self) -> List[ProgramaInfo]:
        """
        Procesa todos los dossiers en la carpeta.
        
        Soporta: .pdf, .docx, .txt
        """
        archivos = (
            list(self.carpeta_dossiers.glob("*.pdf")) +
            list(self.carpeta_dossiers.glob("*.docx")) +
            list(self.carpeta_dossiers.glob("*.txt"))
        )
        
        if not archivos:
            print(f"⚠️ No se encontraron dossiers en {self.carpeta_dossiers}")
            return []
        
        print(f"📚 Encontrados {len(archivos)} dossiers para procesar")
        print("="*60)
        
        for archivo in archivos:
            try:
                print(f"\n📄 Procesando: {archivo.name}")
                programa = self.procesar_dossier(archivo)
                if programa:
                    self.programas_procesados.append(programa)
                    print(f"   ✅ Extraído: {programa.nombre_programa}")
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        print(f"\n{'='*60}")
        print(f"✅ Procesados {len(self.programas_procesados)} programas")
        
        return self.programas_procesados
    
    def procesar_dossier(self, ruta_archivo: Path) -> Optional[ProgramaInfo]:
        """
        Procesa un dossier individual y extrae la información única.
        """
        # 1. Extraer texto del archivo
        texto = self._extraer_texto(ruta_archivo)
        if not texto or len(texto) < 500:
            print(f"   ⚠️ Archivo vacío o muy corto")
            return None
        
        # 2. Filtrar secciones irrelevantes
        texto_filtrado = self._filtrar_secciones(texto)
        
        # 3. Extraer información estructurada con LLM
        info = self._extraer_con_llm(texto_filtrado, ruta_archivo.stem)
        
        return info
    
    def _extraer_texto(self, ruta: Path) -> str:
        """Extrae texto de PDF, DOCX o TXT"""
        ext = ruta.suffix.lower()
        
        if ext == ".txt":
            with open(ruta, 'r', encoding='utf-8') as f:
                return f.read()
        
        elif ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(str(ruta))
                texto = ""
                for page in reader.pages:
                    texto += page.extract_text() + "\n"
                return texto
            except ImportError:
                print("   ⚠️ Instala pypdf: pip install pypdf")
                return ""
            except Exception as e:
                print(f"   ⚠️ Error leyendo PDF: {e}")
                return ""
        
        elif ext == ".docx":
            try:
                from docx import Document
                doc = Document(str(ruta))
                return "\n".join([p.text for p in doc.paragraphs])
            except ImportError:
                print("   ⚠️ Instala python-docx: pip install python-docx")
                return ""
            except Exception as e:
                print(f"   ⚠️ Error leyendo DOCX: {e}")
                return ""
        
        return ""
    
    def _filtrar_secciones(self, texto: str) -> str:
        """
        Elimina secciones que ya están en los manuales generales.
        
        Usa detección por palabras clave para identificar y saltar
        bloques de texto genérico.
        """
        lineas = texto.split('\n')
        lineas_filtradas = []
        
        saltando_seccion = False
        seccion_actual = ""
        
        for linea in lineas:
            linea_lower = linea.lower().strip()
            
            # Detectar inicio de sección a ignorar
            for seccion_ignorar in self.SECCIONES_IGNORAR:
                if seccion_ignorar in linea_lower and len(linea) < 100:
                    saltando_seccion = True
                    seccion_actual = seccion_ignorar
                    break
            
            # Detectar inicio de sección a extraer (termina el salto)
            for seccion_extraer in self.SECCIONES_EXTRAER:
                if seccion_extraer in linea_lower and len(linea) < 100:
                    saltando_seccion = False
                    break
            
            if not saltando_seccion:
                lineas_filtradas.append(linea)
        
        return "\n".join(lineas_filtradas)
    
    def _extraer_con_llm(self, texto: str, nombre_archivo: str) -> Optional[ProgramaInfo]:
        """
        Usa LLM para extraer información estructurada del dossier filtrado.
        """
        # Truncar si es muy largo
        if len(texto) > 15000:
            # Tomar inicio + final
            texto = texto[:8000] + "\n\n[...]\n\n" + texto[-7000:]
        
        prompt_sistema = """
Eres un experto en programas de máster ejecutivo.

Extrae SOLO la información ÚNICA y ESPECÍFICA de este programa.
NO incluyas información genérica sobre OBS, metodología online, rankings, etc.

FORMATO JSON OBLIGATORIO:
{
  "nombre_programa": "Nombre completo del programa",
  "tipo": "MBA | Máster | Postgrado",
  "area": "Marketing | Finanzas | Tech | RRHH | Operaciones | Legal | etc",
  
  "plan_estudios": ["Módulo 1: Nombre", "Módulo 2: Nombre", "..."],
  "duracion": "12 meses",
  "creditos_ects": 60,
  
  "certificaciones_incluidas": ["PMP", "Google Analytics", "etc"],
  "herramientas_software": ["SAP", "Tableau", "Python", "etc"],
  "salidas_profesionales": ["Director de Marketing", "CMO", "etc"],
  
  "profesores_clave": [
    {"nombre": "Juan García", "cargo": "Director", "empresa": "Google"}
  ],
  
  "casos_exito": ["Alumni X pasó de Y a Z", "..."],
  
  "precio_aproximado": "7.500€" 
}

Si algún dato no está disponible, usa "" para strings, 0 para números, [] para listas.
Sé ESPECÍFICO al programa, no pongas información genérica.
"""
        
        try:
            resp = consultar_gpt(
                prompt_sistema, 
                f"DOSSIER DE: {nombre_archivo}\n\n{texto}",
                f"dossier_{nombre_archivo}"
            )
            data = json.loads(resp)
            
            return ProgramaInfo(
                nombre_programa=data.get("nombre_programa", nombre_archivo),
                tipo=data.get("tipo", "Máster"),
                area=data.get("area", "General"),
                plan_estudios=data.get("plan_estudios", []),
                duracion=data.get("duracion", "12 meses"),
                creditos_ects=data.get("creditos_ects", 60),
                certificaciones_incluidas=data.get("certificaciones_incluidas", []),
                herramientas_software=data.get("herramientas_software", []),
                salidas_profesionales=data.get("salidas_profesionales", []),
                profesores_clave=data.get("profesores_clave", []),
                casos_exito=data.get("casos_exito", []),
                precio_aproximado=data.get("precio_aproximado", "")
            )
            
        except Exception as e:
            print(f"   ⚠️ Error LLM: {e}")
            return None
    
    def exportar_para_rag(self, ruta_salida: Path = None):
        """
        Exporta todos los programas procesados en formato TXT para indexar en RAG.
        
        Genera un archivo por programa en inputs/docs/programas/
        """
        if ruta_salida is None:
            ruta_salida = settings.INPUTS_DIR / "docs" / "programas"
        
        ruta_salida.mkdir(parents=True, exist_ok=True)
        
        print(f"\n📤 Exportando {len(self.programas_procesados)} programas para RAG...")
        
        for programa in self.programas_procesados:
            # Nombre de archivo seguro
            nombre_safe = re.sub(r'[^\w\-_]', '_', programa.nombre_programa)
            ruta_archivo = ruta_salida / f"programa_{nombre_safe}.txt"
            
            with open(ruta_archivo, 'w', encoding='utf-8') as f:
                f.write(programa.to_texto_indexable())
            
            print(f"   💾 {ruta_archivo.name}")
        
        print(f"\n✅ Exportación completada en: {ruta_salida}")
        print("   Ejecuta 'python main.py' para re-indexar el RAG")


def main():
    """
    Punto de entrada cuando se ejecuta como script.
    
    Uso:
        python -m centauro.tools.procesar_dossiers
        python -m centauro.tools.procesar_dossiers --carpeta /ruta/a/dossiers
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Procesa dossiers de programas para RAG")
    parser.add_argument(
        "--carpeta",
        type=str,
        default="inputs/dossiers",
        help="Carpeta con los dossiers (default: inputs/dossiers)"
    )
    parser.add_argument(
        "--salida",
        type=str,
        default=None,
        help="Carpeta de salida (default: inputs/docs/programas)"
    )
    
    args = parser.parse_args()
    
    # Crear carpeta de dossiers si no existe
    carpeta = Path(args.carpeta)
    if not carpeta.exists():
        print(f"📁 Creando carpeta: {carpeta}")
        carpeta.mkdir(parents=True, exist_ok=True)
        print(f"   Coloca tus dossiers (.pdf, .docx, .txt) en esta carpeta")
        print(f"   y vuelve a ejecutar este script.")
        return
    
    # Procesar
    processor = DossierProcessor(carpeta)
    programas = processor.procesar_todos()
    
    if programas:
        salida = Path(args.salida) if args.salida else None
        processor.exportar_para_rag(salida)


if __name__ == "__main__":
    main()
