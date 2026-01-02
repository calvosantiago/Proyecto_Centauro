import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    
    # Directorios
    INPUTS_DIR: Path = BASE_DIR / "inputs"
    OUTPUTS_DIR: Path = BASE_DIR / "outputs"
    
    # Base de Datos Vectorial (Usamos el nombre de tu código: CHROMA_PATH)
    CHROMA_PATH: Path = BASE_DIR / "chroma_db"
    
    # Configuración OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    MODEL_NAME: str = "gpt-4o-mini"
    
    # IMPORTANTE: El modelo de embeddings que requiere tu código RAG original
    MODELO_EMBEDDING: str = "text-embedding-3-small" 

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Crear directorios
settings.INPUTS_DIR.mkdir(parents=True, exist_ok=True)
(settings.INPUTS_DIR / "docs").mkdir(parents=True, exist_ok=True) # Crear subcarpeta docs
settings.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
settings.CHROMA_PATH.mkdir(parents=True, exist_ok=True)