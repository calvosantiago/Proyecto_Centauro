import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

class Settings:
    # 1. Rutas Base
    BASE_DIR = Path(__file__).resolve().parent.parent
    
    # 2. Directorios de Datos
    INPUTS_DIR = BASE_DIR / "inputs"
    OUTPUTS_DIR = BASE_DIR / "outputs"
    
    # 3. Ruta de ChromaDB (Coincide con rag.py)
    CHROMA_PATH = BASE_DIR / ".chroma_db"
    
    # 4. Configuración OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # --- CAMBIO AQUÍ ---
    # Renombrado de MODELO_LLM a MODEL_NAME para que coincida con llm_client.py
    MODEL_NAME = "gpt-4o-mini"
    
    # Modelo de Embeddings
    MODELO_EMBEDDING = "text-embedding-3-small"

# Instanciamos la clase
settings = Settings()