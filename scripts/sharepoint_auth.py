#!/usr/bin/env python3
"""
sharepoint_auth.py - Autenticación inicial con Microsoft Graph (SharePoint)

Ejecutar UNA VEZ para obtener el refresh token con acceso a SharePoint
y guardarlo en .env como GRAPH_REFRESH_TOKEN.
Después, el watcher usará ese token automáticamente sin interacción.

Uso:
    cd Proyecto_Centauro
    python scripts/sharepoint_auth.py

Requisitos en .env ANTES de ejecutar:
    AZURE_CLIENT_ID=<client_id de la App Registration>
    AZURE_TENANT_ID=<tenant_id del directorio Planeta>
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    import msal
except ImportError:
    print("ERROR: msal no está instalado. Ejecuta: pip install msal")
    sys.exit(1)

try:
    from dotenv import load_dotenv, set_key
except ImportError:
    print("ERROR: python-dotenv no está instalado. Ejecuta: pip install python-dotenv")
    sys.exit(1)

ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

SCOPES = [
    "https://graph.microsoft.com/Files.Read",
]


def main():
    client_id = os.getenv("AZURE_CLIENT_ID")
    tenant_id = os.getenv("AZURE_TENANT_ID")

    errores = []
    if not client_id:
        errores.append("  - AZURE_CLIENT_ID no definido en .env")
    if not tenant_id:
        errores.append("  - AZURE_TENANT_ID no definido en .env")

    if errores:
        print("ERROR: Faltan variables en .env:\n" + "\n".join(errores))
        sys.exit(1)

    authority = f"https://login.microsoftonline.com/{tenant_id}"

    print("=" * 60)
    print("  Centauro × SharePoint — Autenticación Device Code Flow")
    print("=" * 60)
    print(f"  App (client_id) : {client_id}")
    print(f"  Tenant          : {tenant_id}")
    print(f"  Permisos        : Files.Read.All (Graph)")
    print()

    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=authority,
    )

    # Intentar reutilizar cuenta en caché primero
    accounts = app.get_accounts()
    if accounts:
        print(f"Cuenta en caché: {accounts[0]['username']}")
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            print("Token obtenido silenciosamente (sin Device Code).")
            _guardar_token(result)
            return
        print("Caché expirada, iniciando Device Code Flow...\n")

    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        print(f"ERROR al iniciar Device Code Flow:\n{flow.get('error_description', str(flow))}")
        sys.exit(1)

    print(flow["message"])
    print()
    print("Esperando que te autentiques en el navegador...")
    print("(El proceso espera hasta 15 minutos)\n")

    result = app.acquire_token_by_device_flow(flow)

    if "error" in result:
        print(f"\nERROR de autenticación: {result.get('error_description', result.get('error'))}")
        sys.exit(1)

    username = result.get("id_token_claims", {}).get("preferred_username", "N/A")
    print(f"\nAutenticado correctamente como: {username}")

    _guardar_token(result)


def _guardar_token(result: dict):
    refresh_token = result.get("refresh_token")

    if not refresh_token:
        print()
        print("ADVERTENCIA: El servidor no devolvió refresh_token.")
        print("Posibles causas:")
        print("  - El scope 'offline_access' no fue aceptado")
        print("  - Necesitas consentimiento de administrador")
        print()
        print("Comprueba en Azure Portal que 'offline_access' no requiere admin consent.")
        return

    set_key(str(ENV_PATH), "GRAPH_REFRESH_TOKEN", refresh_token)

    print()
    print("=" * 60)
    print("  GRAPH_REFRESH_TOKEN guardado en .env")
    print("=" * 60)
    print()
    print("Próximo paso: configura SP_SITE_HOSTNAME, SP_SITE_PATH")
    print("y SP_FOLDER_PATH en .env, luego ejecuta el watcher:")
    print("  python scripts/sharepoint_watcher.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
