"""
Script CLI para gestionar usuarios de Centauro.

Uso:
    python scripts/gestionar_usuarios.py crear <username> "<Nombre Apellido>" <password> [rol]
    python scripts/gestionar_usuarios.py listar
    python scripts/gestionar_usuarios.py eliminar <username>
    python scripts/gestionar_usuarios.py cambiar_password <username> <nueva_password>

Roles disponibles:
    asesor  - Acceso normal (por defecto)
    admin   - Acceso completo

Ejemplos:
    python scripts/gestionar_usuarios.py crear esther.lopez "Esther Lopez" MiPassword123 asesor
    python scripts/gestionar_usuarios.py crear ivan.canale "Iván Canale" OtraPass456 asesor
    python scripts/gestionar_usuarios.py crear admin "Administrador" AdminPass789 admin
    python scripts/gestionar_usuarios.py listar
    python scripts/gestionar_usuarios.py cambiar_password esther.lopez NuevaPass
    python scripts/gestionar_usuarios.py eliminar esther.lopez

IMPORTANTE:
    - El archivo centauro_users.json generado debe protegerse y NO subirse a Git
    - Los usernames se normalizan a minúsculas automáticamente
    - Las contraseñas se hashean con PBKDF2-SHA256 (nunca se guardan en texto plano)
"""
import sys
import json
import hashlib
import secrets
from pathlib import Path

# Ruta al archivo de usuarios (relativa a la raíz del proyecto)
USERS_FILE = Path(__file__).resolve().parent.parent / "centauro_users.json"


# ─────────────────────────────────────────────
# Utilidades internas
# ─────────────────────────────────────────────

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 260_000)
    return f"pbkdf2:sha256:{salt}:{dk.hex()}"


def _cargar() -> dict:
    if USERS_FILE.exists():
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _guardar(usuarios: dict):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(usuarios, f, indent=2, ensure_ascii=False)
    print(f"   💾 Guardado en: {USERS_FILE}")


# ─────────────────────────────────────────────
# Comandos
# ─────────────────────────────────────────────

def cmd_crear(args):
    """Crea o actualiza un usuario."""
    if len(args) < 3:
        print("❌ Uso: crear <username> \"<Nombre Completo>\" <password> [rol]")
        sys.exit(1)

    username = args[0].strip().lower()
    nombre_completo = args[1].strip()
    password = args[2]
    rol = args[3].strip().lower() if len(args) > 3 else "asesor"

    # Normalizar alias de rol
    if rol == "jefe":
        rol = "admin"
    if rol not in ("asesor", "admin"):
        print(f"❌ Rol inválido: '{rol}'. Usa 'asesor', 'admin' o 'jefe'.")
        sys.exit(1)

    if len(password) < 8:
        print("❌ La contraseña debe tener al menos 8 caracteres.")
        sys.exit(1)

    usuarios = _cargar()
    accion = "actualizado" if username in usuarios else "creado"

    usuarios[username] = {
        "nombre_completo": nombre_completo,
        "rol": rol,
        "password_hash": _hash_password(password)
    }

    _guardar(usuarios)
    icono = "👑" if rol == "admin" else "👤"
    print(f"\n✅ Usuario {icono} '{username}' ({nombre_completo}) {accion} con rol '{rol}'")


def cmd_listar(args):
    """Lista todos los usuarios registrados."""
    usuarios = _cargar()

    if not usuarios:
        print("\n📭 No hay usuarios registrados en Centauro.")
        print(f"   Crea el primero con: python scripts/gestionar_usuarios.py crear <user> \"<Nombre>\" <pass>")
        return

    print(f"\n👥 Usuarios de Centauro ({len(usuarios)} total):")
    print("─" * 55)
    for username, datos in sorted(usuarios.items()):
        rol = datos.get('rol', 'asesor')
        nombre = datos.get('nombre_completo', '?')
        icono = "👑" if rol == "admin" else "👤"
        print(f"  {icono}  {username:<25} {nombre}  [{rol}]")
    print()


def cmd_eliminar(args):
    """Elimina un usuario."""
    if not args:
        print("❌ Uso: eliminar <username>")
        sys.exit(1)

    username = args[0].strip().lower()
    usuarios = _cargar()

    if username not in usuarios:
        print(f"❌ Usuario '{username}' no encontrado.")
        sys.exit(1)

    nombre = usuarios[username].get('nombre_completo', username)
    del usuarios[username]
    _guardar(usuarios)
    print(f"\n🗑️  Usuario '{username}' ({nombre}) eliminado.")


def cmd_cambiar_password(args):
    """Cambia la contraseña de un usuario."""
    if len(args) < 2:
        print("❌ Uso: cambiar_password <username> <nueva_password>")
        sys.exit(1)

    username = args[0].strip().lower()
    nueva_password = args[1]

    if len(nueva_password) < 8:
        print("❌ La contraseña debe tener al menos 8 caracteres.")
        sys.exit(1)

    usuarios = _cargar()

    if username not in usuarios:
        print(f"❌ Usuario '{username}' no encontrado.")
        sys.exit(1)

    usuarios[username]["password_hash"] = _hash_password(nueva_password)
    _guardar(usuarios)
    print(f"\n✅ Contraseña de '{username}' actualizada correctamente.")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

COMANDOS = {
    "crear": cmd_crear,
    "listar": cmd_listar,
    "eliminar": cmd_eliminar,
    "cambiar_password": cmd_cambiar_password,
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
