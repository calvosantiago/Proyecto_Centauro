#!/usr/bin/env python3
"""
pbi_auth.py - Autenticación inicial con Power BI vía Device Code Flow

Ejecutar UNA VEZ para obtener el refresh token de tu cuenta de Planeta
y guardarlo en .env. Después, Chainlit usará ese token automáticamente
sin necesidad de interacción del usuario.

Uso:
    cd Proyecto_Centauro
    python scripts/pbi_auth.py

Requisitos en .env ANTES de ejecutar:
    AZURE_CLIENT_ID=<client_id de la App Registration>
    AZURE_TENANT_ID=<tenant_id del directorio Planeta>
    AZURE_CLIENT_SECRET=<client_secret (opcional pero recomendado)>
    PBI_WORKSPACE_ID=<ID del workspace en Power BI / Fabric>
    PBI_DATASET_ID=<ID del modelo semántico>
    PBI_SCHEMA_HINT=<descripción libre del esquema (opcional)>
"""
import os
import sys
from pathlib import Path

# Añadir raíz del proyecto al path para importar módulos de centauro
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    import msal
except ImportError:
    print("ERROR: msal no está instalado.")
    print("Ejecuta: pip install msal")
    sys.exit(1)

try:
    from dotenv import load_dotenv, set_key
except ImportError:
    print("ERROR: python-dotenv no está instalado.")
    print("Ejecuta: pip install python-dotenv")
    sys.exit(1)

ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

# Scope: Dataset.Read.All (delegado) + offline_access para refresh token
SCOPES = [
    "https://analysis.windows.net/powerbi/api/Dataset.Read.All",
]


def main():
    client_id = os.getenv("AZURE_CLIENT_ID")
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")

    # ── Validación de prerequisitos ──────────────────────────────────────
    errores = []
    if not client_id:
        errores.append("  - AZURE_CLIENT_ID no definido en .env")
    if not tenant_id:
        errores.append("  - AZURE_TENANT_ID no definido en .env")
    if not os.getenv("PBI_WORKSPACE_ID"):
        errores.append("  - PBI_WORKSPACE_ID no definido en .env")
    if not os.getenv("PBI_DATASET_ID"):
        errores.append("  - PBI_DATASET_ID no definido en .env")

    if errores:
        print("ERROR: Faltan variables en .env:\n" + "\n".join(errores))
        print(f"\nEdita el archivo: {ENV_PATH}")
        sys.exit(1)

    authority = f"https://login.microsoftonline.com/{tenant_id}"

    print("=" * 60)
    print("  Centauro × Power BI — Autenticación Device Code Flow")
    print("=" * 60)
    print(f"  App (client_id) : {client_id}")
    print(f"  Tenant          : {tenant_id}")
    print(f"  Secret          : {'sí' if client_secret else 'no (público)'}")
    print()

    # ── Crear cliente MSAL ───────────────────────────────────────────────
    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=authority,
    )

    # ── Intentar reutilizar cuenta en caché ──────────────────────────────
    accounts = app.get_accounts()
    if accounts:
        print(f"Cuenta en caché: {accounts[0]['username']}")
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            print("Token obtenido silenciosamente (sin Device Code).")
            _guardar_tokens(result)
            return
        else:
            print("Caché expirada, iniciando Device Code Flow...\n")

    # ── Device Code Flow ─────────────────────────────────────────────────
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        error_desc = flow.get("error_description", str(flow))
        print(f"ERROR al iniciar Device Code Flow:\n{error_desc}")
        sys.exit(1)

    # Mostrar instrucciones al usuario
    print(flow["message"])
    print()
    print("Esperando que te autentiques en el navegador...")
    print("(El proceso espera hasta 15 minutos)\n")

    # Bloquea hasta que el usuario complete la autenticación en el navegador
    result = app.acquire_token_by_device_flow(flow)

    if "error" in result:
        error_desc = result.get("error_description", result.get("error", "Error desconocido"))
        print(f"\nERROR de autenticación: {error_desc}")
        sys.exit(1)

    username = result.get("id_token_claims", {}).get("preferred_username", "N/A")
    print(f"\nAutenticado correctamente como: {username}")

    _guardar_tokens(result)


def _guardar_tokens(result: dict):
    """Guarda el refresh token (y metadatos útiles) en .env."""
    refresh_token = result.get("refresh_token")

    if not refresh_token:
        print()
        print("ADVERTENCIA: El servidor no devolvió refresh_token.")
        print("Posibles causas:")
        print("  - El scope 'offline_access' no fue aceptado")
        print("  - La App Registration requiere consentimiento de admin para offline_access")
        print()
        print("Puedes usar el access_token directamente, pero expirará en ~1 hora")
        print("y necesitarás re-ejecutar este script.")

        # Guardar access token como fallback temporal
        access_token = result.get("access_token", "")
        if access_token:
            set_key(str(ENV_PATH), "PBI_ACCESS_TOKEN", access_token)
            print(f"\nPBI_ACCESS_TOKEN guardado en {ENV_PATH} (temporal, ~1h)")
        return

    set_key(str(ENV_PATH), "PBI_REFRESH_TOKEN", refresh_token)
    print(f"PBI_REFRESH_TOKEN guardado en {ENV_PATH}")

    # Limpiar access token temporal si existía
    if os.getenv("PBI_ACCESS_TOKEN"):
        set_key(str(ENV_PATH), "PBI_ACCESS_TOKEN", "")

    _mostrar_resumen_configuracion()


def _mostrar_resumen_configuracion():
    """Muestra un resumen del estado de configuración."""
    workspace_id = os.getenv("PBI_WORKSPACE_ID", "")
    dataset_id = os.getenv("PBI_DATASET_ID", "")
    schema_hint = os.getenv("PBI_SCHEMA_HINT", "")

    print()
    print("=" * 60)
    print("  Configuración completada")
    print("=" * 60)
    print()
    print("Estado de variables Power BI en .env:")
    print(f"  AZURE_CLIENT_ID     : {'✓' if os.getenv('AZURE_CLIENT_ID') else '✗'}")
    print(f"  AZURE_TENANT_ID     : {'✓' if os.getenv('AZURE_TENANT_ID') else '✗'}")
    print(f"  AZURE_CLIENT_SECRET : {'✓' if os.getenv('AZURE_CLIENT_SECRET') else '- (opcional)'}")
    print(f"  PBI_WORKSPACE_ID    : {'✓ ' + workspace_id[:8] + '...' if workspace_id else '✗ NO DEFINIDO'}")
    print(f"  PBI_DATASET_ID      : {'✓ ' + dataset_id[:8] + '...' if dataset_id else '✗ NO DEFINIDO'}")
    print(f"  PBI_REFRESH_TOKEN   : ✓ guardado")
    print(f"  PBI_SCHEMA_HINT     : {'✓ definido' if schema_hint else '- vacío (se auto-descubrirá)'}")
    print()

    if not workspace_id or not dataset_id:
        print("ATENCIÓN: Faltan PBI_WORKSPACE_ID y/o PBI_DATASET_ID.")
        print("Para obtenerlos:")
        print("  1. Abre app.powerbi.com")
        print("  2. Navega a tu workspace y dataset")
        print("  3. La URL tiene el formato:")
        print("     .../groups/<WORKSPACE_ID>/datasets/<DATASET_ID>/...")
        print()

    if not schema_hint:
        print("CONSEJO: Añade PBI_SCHEMA_HINT en .env con una descripción de tu modelo,")
        print("  por ejemplo:")
        print('  PBI_SCHEMA_HINT="Tabla: Ventas (columnas: Fecha, Importe, Asesor, Programa).')
        print('  Medidas: [Total Ventas], [Leads Activos], [Tasa Conversion]"')
        print()
        print("  Si no lo defines, se intentará auto-descubrir el esquema via DAX INFO().")
        print()

    print("Próximo paso: reinicia Chainlit y prueba con una pregunta como:")
    print('  "¿Cuántos leads activos hay este mes?"')
    print('  "Dame el ranking de asesores por ventas"')
    print("=" * 60)


if __name__ == "__main__":
    main()
