import os
from pathlib import Path

# --- DEFINICIÓN DE CONTENIDOS ---

CODE_REQUIREMENTS = """openai
chromadb
pydantic
python-docx
pypdf
python-dotenv
tiktoken
"""

CODE_ENV = """# RENUEVA ESTO CON TU API KEY REAL"""

CODE_CONFIG = """import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Rutas
    BASE_DIR = Path(__file__).parent.parent
    DOCS_DIR = BASE_DIR / "inputs" / "docs"
    TRANSCRIPTS_DIR = BASE_DIR / "inputs" / "transcripts"
    OUTPUTS_DIR = BASE_DIR / "outputs"
    CHROMA_DIR = BASE_DIR / ".chroma_db"
    
    # Configuración del Modelo
    MODEL_NAME = "gpt-4o-mini"
    EMBEDDING_MODEL = "text-embedding-3-small"
    
    # Parámetros RAG
    CHUNK_SIZE = 1000
    TOP_K_RETRIEVAL = 5

settings = Settings()
"""

CODE_SCHEMA = """from pydantic import BaseModel, Field
from typing import List, Optional

class Hallazgo(BaseModel):
    criterio: str = Field(..., description="Nombre del criterio evaluado según el manual")
    cumple: bool = Field(..., description="True si lo hizo bien, False si falló")
    cita_evidencia: str = Field(..., description="Frase exacta dicha por el asesor en la transcripción")
    referencia_manual: str = Field(..., description="Nombre del documento o sección del manual que justifica esto")
    feedback: str = Field(..., description="Consejo constructivo para el asesor")

class ReporteCalidad(BaseModel):
    asesor: str = Field(..., description="Nombre del asesor si se detecta")
    resumen_ejecutivo: str
    puntos_fuertes: List[Hallazgo]
    areas_mejora: List[Hallazgo]
    nota_final_0_10: int
"""

CODE_LLM_CLIENT = """from openai import OpenAI
from .config import settings

client = OpenAI()

def obtener_embedding(texto):
    text = texto.replace("\\n", " ")
    return client.embeddings.create(input=[text], model=settings.EMBEDDING_MODEL).data[0].embedding

def consultar_gpt(prompt_sistema, prompt_usuario):
    response = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario}
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )
    return response.choices[0].message.content
"""

CODE_RAG = """import chromadb
from pathlib import Path
from .config import settings
from .llm_client import obtener_embedding

# Inicializar ChromaDB
chroma_client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
collection = chroma_client.get_or_create_collection(name="manual_conocimiento")

def leer_archivo(ruta: Path):
    try:
        return ruta.read_text(encoding="utf-8")
    except:
        return ""

def indexar_documentacion():
    print("--- Indexando Documentación ---")
    archivos = list(settings.DOCS_DIR.glob("*.txt"))
    
    if not archivos:
        print("¡OJO! No hay manuales en inputs/docs/")
        return

    for archivo in archivos:
        texto = leer_archivo(archivo)
        chunks = [texto[i:i+settings.CHUNK_SIZE] for i in range(0, len(texto), settings.CHUNK_SIZE)]
        
        if not chunks: continue

        ids = [f"{archivo.name}_{i}" for i in range(len(chunks))]
        embeddings = [obtener_embedding(chunk) for chunk in chunks]
        
        collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=[{"fuente": archivo.name} for _ in chunks]
        )
        print(f"Procesado: {archivo.name}")

def buscar_contexto(query):
    query_emb = obtener_embedding(query)
    resultados = collection.query(query_embeddings=[query_emb], n_results=settings.TOP_K_RETRIEVAL)
    # Manejo simple de resultados vacíos
    if not results['documents'] or not results['documents'][0]:
        return ""
    return "\\n\\n".join(resultados['documents'][0])
"""

CODE_ANALYZE = """import json
from .config import settings
from .rag import buscar_contexto
from .llm_client import consultar_gpt
from .schema import ReporteCalidad

def analizar_entrevista(nombre_archivo, texto_transcripcion):
    print(f"🔍 Buscando reglas para: {nombre_archivo}")
    contexto_manual = buscar_contexto("Criterios de evaluación calidad saludo cierre objeciones")
    
    sistema = f\"\"\"
    Eres CENTAURO, un auditor de calidad estricto.
    Tu trabajo es evaluar una transcripción de venta basándote EXCLUSIVAMENTE en el MANUAL proporcionado.
    
    MANUAL DE CRITERIOS:
    {contexto_manual}
    
    INSTRUCCIONES:
    1. Si el asesor hace algo que no está en el manual, ignóralo.
    2. Devuelve JSON estricto cumpliendo el esquema solicitado.
    \"\"\"
    
    usuario = f\"\"\"
    Analiza esta transcripción:
    {texto_transcripcion}
    
    Genera el JSON con el esquema de ReporteCalidad.
    \"\"\"
    
    print("🧠 Consultando a GPT-4o-mini...")
    respuesta_json_str = consultar_gpt(sistema, usuario)
    
    try:
        datos = json.loads(respuesta_json_str)
        reporte = ReporteCalidad(**datos) 
        
        output_path = settings.OUTPUTS_DIR / f"{nombre_archivo}_reporte.json"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(reporte.model_dump_json(indent=2))
            
        print(f"✅ Reporte generado: {output_path}")
        return reporte
        
    except Exception as e:
        print(f"❌ Error procesando {nombre_archivo}: {e}")
        return None
"""

CODE_MAIN = """from pathlib import Path
from centauro.config import settings
from centauro.rag import indexar_documentacion
from centauro.analyze import analizar_entrevista

def main():
    settings.OUTPUTS_DIR.mkdir(exist_ok=True)
    
    # 1. Indexar manuales
    indexar_documentacion()
    
    # 2. Procesar entrevistas
    entrevistas = list(settings.TRANSCRIPTS_DIR.glob("*.txt"))
    
    if not entrevistas:
        print("No hay entrevistas en inputs/transcripts/ para procesar.")
        return

    print(f"--- Procesando {len(entrevistas)} entrevistas ---")
    for entrevista in entrevistas:
        print(f"Analizando: {entrevista.name}...")
        texto = entrevista.read_text(encoding="utf-8")
        analizar_entrevista(entrevista.name, texto)

if __name__ == "__main__":
    main()
"""

# Datos de prueba
DUMMY_MANUAL = """El asesor debe iniciar la llamada saludando con su nombre y el de la empresa.
Es obligatorio informar que la llamada está siendo grabada por calidad.
Ante una objeción de precio, el asesor nunca debe bajar el precio inmediatamente, debe resaltar el valor del servicio primero.
El cierre debe incluir una confirmación explícita de los datos del cliente."""

DUMMY_TRANSCRIPT = """Asesor: Hola, buenos días. Hablo con María?
Cliente: Sí, dime.
Asesor: Le llamo para ofrecerle nuestro nuevo plan de fibra.
Cliente: Es muy caro.
Asesor: Bueno, se lo dejo a mitad de precio si firma ya.
Cliente: Ah, vale.
Asesor: Perfecto, adiós."""

# --- LÓGICA DE CREACIÓN ---

def create_structure():
    base = Path(".")
    
    # 1. Definir directorios
    dirs = [
        base / "inputs" / "docs",
        base / "inputs" / "transcripts",
        base / "outputs",
        base / "centauro"
    ]
    
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"📂 Carpeta creada: {d}")

    # 2. Definir Archivos y su contenido
    files = {
        base / "requirements.txt": CODE_REQUIREMENTS,
        base / ".env": CODE_ENV,
        base / "main.py": CODE_MAIN,
        base / "centauro" / "__init__.py": "", # Archivo vacío
        base / "centauro" / "config.py": CODE_CONFIG,
        base / "centauro" / "schema.py": CODE_SCHEMA,
        base / "centauro" / "llm_client.py": CODE_LLM_CLIENT,
        base / "centauro" / "rag.py": CODE_RAG,
        base / "centauro" / "analyze.py": CODE_ANALYZE,
        # Datos de prueba
        base / "inputs" / "docs" / "manual_calidad.txt": DUMMY_MANUAL,
        base / "inputs" / "transcripts" / "entrevista_juan.txt": DUMMY_TRANSCRIPT
    }

    for path, content in files.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"📄 Archivo creado: {path}")

    print("\n✅ ¡INSTALACIÓN COMPLETADA!")
    print("------------------------------------------------")
    print("Siguientes pasos:")
    print("1. Abre la terminal.")
    print("2. Ejecuta: python -m venv .venv")
    print("3. Ejecuta: .venv\\Scripts\\activate (Windows) o source .venv/bin/activate (Mac/Linux)")
    print("4. Ejecuta: pip install -r requirements.txt")
    print("5. EDITA el archivo .env y pon tu API Key real de OpenAI.")
    print("6. Ejecuta: python main.py")

if __name__ == "__main__":
    create_structure()