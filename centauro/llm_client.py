import csv
import os
import datetime
from openai import OpenAI
from .config import settings
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- TARIFAS GPT-4o-mini (Actualizado Dic 2025) ---
# Precios por token (USD)
# Input: $0.15 por 1 millón
# Output: $0.60 por 1 millón
COST_PER_INPUT_TOKEN = 0.15 / 1_000_000
COST_PER_OUTPUT_TOKEN = 0.60 / 1_000_000

def registrar_gasto(referencia, uso):
    """
    Registra el consumo de tokens y el coste en un archivo CSV.
    Si el archivo no existe, lo crea con cabeceras.
    """
    archivo_csv = settings.OUTPUTS_DIR / "control_gastos.csv"
    archivo_existe = os.path.isfile(archivo_csv)
    
    # Extraer datos de uso
    tokens_in = uso.prompt_tokens
    tokens_out = uso.completion_tokens
    total_tokens = uso.total_tokens
    
    # Calcular coste
    coste_usd = (tokens_in * COST_PER_INPUT_TOKEN) + (tokens_out * COST_PER_OUTPUT_TOKEN)
    
    try:
        with open(archivo_csv, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Escribir cabecera si es nuevo
            if not archivo_existe:
                writer.writerow([
                    "Fecha", 
                    "Hora", 
                    "Archivo/Referencia", 
                    "Tokens Entrada (Prompt)", 
                    "Tokens Salida (Completion)", 
                    "Total Tokens", 
                    "Coste Estimado (USD)"
                ])
                
            # Escribir la línea de gasto
            writer.writerow([
                datetime.datetime.now().strftime("%d/%m/%Y"),
                datetime.datetime.now().strftime("%H:%M:%S"),
                referencia,
                tokens_in,
                tokens_out,
                total_tokens,
                f"{coste_usd:.6f}" # 6 decimales para ver los micro-centavos
            ])
    except Exception as e:
        print(f"⚠️ Aviso: No se pudo guardar el registro de gastos: {e}")

def obtener_embedding(texto):
    text = texto.replace("\n", " ")
    return client.embeddings.create(input=[text], model=settings.EMBEDDING_MODEL).data[0].embedding

def consultar_gpt(prompt_sistema, prompt_usuario, referencia_log="Desconocido"):
    """
    Envía la consulta a OpenAI y registra el gasto asociado al archivo 'referencia_log'.
    """
    response = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario}
        ],
        temperature=0.0,
        seed=42,
        response_format={"type": "json_object"}
    )
    
    # --- REGISTRO AUTOMÁTICO DE GASTOS ---
    if response.usage:
        registrar_gasto(referencia_log, response.usage)
    # -------------------------------------
    
    return response.choices[0].message.content