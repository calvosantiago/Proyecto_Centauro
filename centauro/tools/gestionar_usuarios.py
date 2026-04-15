"""
Script CLI para gestionar usuarios de Centauro en Supabase.

Uso:
    python -m centauro.tools.gestionar_usuarios crear <username> "<Nombre Apellido>" <password> [rol]
    python -m centauro.tools.gestionar_usuarios listar
    python -m centauro.tools.gestionar_usuarios eliminar <username>
    python -m centauro.tools.gestionar_usuarios cambiar_password <username> <nueva_password>
    python -m centauro.tools.gestionar_usuarios migrar_json [ruta_json]

Roles disponibles:
    asesor  - Acceso normal (por defecto)
    admin   - Acceso completo

Ejemplos:
    python -m centauro.tools.gestionar_usuarios crear esther.lopez "Esther Lopez" MiPassword123 asesor
    python -m centauro.tools.gestionar_usuarios listar
    python -m centauro.tools.gestionar_usuarios cambiar_password esther.lopez NuevaPass
    python -m centauro.tools.gestionar_usuarios eliminar esther.lopez
    python -m centauro.tools.gestionar_usuarios migrar_json

Requisitos:
    - SUPABASE_URL y SUPABASE_KEY en .env
    - Tabla usuarios_auth creada en Supabase
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from centauro.auth import hash_password
from centauro.config import settings

AUTH_USERS_TABLE = "usuarios_auth"
DEFAULT_USERS_JSON = PROJECT_ROOT / "centauro_users.json"


def _normalizar_rol(rol: str) -> str:
    rol_norm = (rol or "asesor").strip().lower()
    if rol_norm == "jefe":
        rol_norm = "admin"
    if rol_norm not in ("asesor", "admin"):
        raise ValueError(f"Rol inválido: '{rol}'. Usa 'asesor', 'admin' o 'jefe'.")
    return rol_norm


def _get_client():
    url = getattr(settings, "SUPABASE_URL", "") or ""
    key = getattr(settings, "SUPABASE_KEY", "") or ""
    if not url or not key:
        print("❌ Falta SUPABASE_URL/SUPABASE_KEY en .env")
        sys.exit(1)
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as e:
        print(f"❌ No se pudo crear cliente de Supabase: {e}")
        sys.exit(1)


def _buscar_usuario(client, username: str) -> dict | None:
    result = (
        client.table(AUTH_USERS_TABLE)
        .select("*")
        .eq("username", username)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def cmd_crear(args):
    """Crea o actualiza un usuario en Supabase."""
    if len(args) < 3:
        print("❌ Uso: crear <username> \"<Nombre Completo>\" <password> [rol]")
        sys.exit(1)

    username = args[0].strip().lower()
    nombre_completo = args[1].strip()
    password = args[2]
    rol = _normalizar_rol(args[3] if len(args) > 3 else "asesor")

    if len(password) < 8:
        print("❌ La contraseña debe tener al menos 8 caracteres.")
        sys.exit(1)

    client = _get_client()
    existe = _buscar_usuario(client, username) is not None

    payload = {
        "username": username,
        "nombre_completo": nombre_completo,
        "rol": rol,
        "password_hash": hash_password(password),
        "activo": True,
    }
    client.table(AUTH_USERS_TABLE).upsert(payload, on_conflict="username").execute()

    accion = "actualizado" if existe else "creado"
    icono = "👑" if rol == "admin" else "👤"
    print(f"\n✅ Usuario {icono} '{username}' ({nombre_completo}) {accion} con rol '{rol}'")


def cmd_listar(args):
    """Lista usuarios de Supabase."""
    client = _get_client()
    result = (
        client.table(AUTH_USERS_TABLE)
        .select("username,nombre_completo,rol,activo,created_at,updated_at")
        .order("username")
        .execute()
    )
    usuarios = result.data or []

    if not usuarios:
        print("\n📭 No hay usuarios en Supabase.")
        print("   Crea el primero con: python -m centauro.tools.gestionar_usuarios crear <user> \"<Nombre>\" <pass>")
        return

    print(f"\n👥 Usuarios de Centauro en Supabase ({len(usuarios)} total):")
    print("─" * 85)
    for u in usuarios:
        rol = u.get("rol", "asesor")
        nombre = u.get("nombre_completo", "?")
        username = u.get("username", "?")
        activo = "activo" if u.get("activo", True) else "inactivo"
        icono = "👑" if rol == "admin" else "👤"
        print(f"  {icono}  {username:<25} {nombre:<28} [{rol}] ({activo})")
    print()


def cmd_eliminar(args):
    """Elimina un usuario de Supabase (hard delete)."""
    if not args:
        print("❌ Uso: eliminar <username>")
        sys.exit(1)

    username = args[0].strip().lower()
    client = _get_client()
    usuario = _buscar_usuario(client, username)
    if not usuario:
        print(f"❌ Usuario '{username}' no encontrado.")
        sys.exit(1)

    client.table(AUTH_USERS_TABLE).delete().eq("username", username).execute()
    print(f"\n🗑️  Usuario '{username}' eliminado.")


def cmd_cambiar_password(args):
    """Cambia la contraseña de un usuario en Supabase."""
    if len(args) < 2:
        print("❌ Uso: cambiar_password <username> <nueva_password>")
        sys.exit(1)

    username = args[0].strip().lower()
    nueva_password = args[1]

    if len(nueva_password) < 8:
        print("❌ La contraseña debe tener al menos 8 caracteres.")
        sys.exit(1)

    client = _get_client()
    usuario = _buscar_usuario(client, username)
    if not usuario:
        print(f"❌ Usuario '{username}' no encontrado.")
        sys.exit(1)

    client.table(AUTH_USERS_TABLE).update(
        {"password_hash": hash_password(nueva_password), "activo": True}
    ).eq("username", username).execute()
    print(f"\n✅ Contraseña de '{username}' actualizada correctamente.")


def cmd_migrar_json(args):
    """
    Migra usuarios desde centauro_users.json hacia Supabase.
    Conserva los password_hash existentes (no re-hashea).
    """
    json_path = Path(args[0]) if args else DEFAULT_USERS_JSON
    if not json_path.is_absolute():
        json_path = PROJECT_ROOT / json_path

    if not json_path.exists():
        print(f"❌ No existe el archivo JSON: {json_path}")
        sys.exit(1)

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            usuarios = json.load(f)
    except Exception as e:
        print(f"❌ Error leyendo JSON de usuarios: {e}")
        sys.exit(1)

    if not isinstance(usuarios, dict) or not usuarios:
        print("ℹ️ El JSON no contiene usuarios para migrar.")
        return

    client = _get_client()
    creados = 0
    actualizados = 0

    for username, data in usuarios.items():
        username_norm = (username or "").strip().lower()
        if not username_norm:
            continue
        nombre = (data.get("nombre_completo") or username_norm).strip()
        rol = _normalizar_rol(data.get("rol", "asesor"))
        password_hash = (data.get("password_hash") or "").strip()
        if not password_hash:
            print(f"⚠️ Saltando '{username_norm}': no tiene password_hash")
            continue

        existe = _buscar_usuario(client, username_norm) is not None
        payload = {
            "username": username_norm,
            "nombre_completo": nombre,
            "rol": rol,
            "password_hash": password_hash,
            "activo": True,
        }
        client.table(AUTH_USERS_TABLE).upsert(payload, on_conflict="username").execute()
        if existe:
            actualizados += 1
        else:
            creados += 1

    print(
        f"\n✅ Migración completada. Creados: {creados}, actualizados: {actualizados}, "
        f"origen: {json_path}"
    )


COMANDOS = {
    "crear": cmd_crear,
    "listar": cmd_listar,
    "eliminar": cmd_eliminar,
    "cambiar_password": cmd_cambiar_password,
    "migrar_json": cmd_migrar_json,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMANDOS:
        print(__doc__)
        print("Comandos disponibles:", ", ".join(COMANDOS.keys()))
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]
    COMANDOS[cmd](args)


if __name__ == "__main__":
    main()
