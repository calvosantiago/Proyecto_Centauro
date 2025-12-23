import os
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