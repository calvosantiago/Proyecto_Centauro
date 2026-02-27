"""
Módulo de autenticación para Centauro v4.0

Sistema de autenticación basado en usuario/contraseña con:
- Contraseñas hasheadas con PBKDF2-SHA256 (estándar NIST 2024)
- Base de datos de usuarios en JSON externo al código fuente
- Roles: "asesor" | "admin"
- Mapeo username → nombre completo del asesor (para perfiles automáticos)
"""
import json
import hashlib
import secrets
from pathlib import Path
from typing import Optional, Dict

# Archivo de usuarios: DEBE estar en .gitignore / fuera de control de versiones
USERS_FILE = Path(__file__).resolve().parent.parent / "centauro_users.json"


def hash_password(password: str, salt: str = None) -> str:
    """
    Genera hash seguro de contraseña usando PBKDF2-SHA256.

    Args:
        password: Contraseña en texto plano
        salt: Salt opcional (se genera automáticamente si no se proporciona)

    Returns:
        String con formato "pbkdf2:sha256:<salt>:<hash_hex>"
    """
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        iterations=260_000  # Recomendación NIST 2024
    )
    return f"pbkdf2:sha256:{salt}:{dk.hex()}"


def verificar_password(password: str, stored_hash: str) -> bool:
    """
    Verifica una contraseña contra su hash almacenado de forma segura.

    Usa secrets.compare_digest para evitar timing attacks.
    """
    try:
        partes = stored_hash.split(":")
        if len(partes) != 4 or partes[0] != "pbkdf2":
            return False
        _, algo, salt, dk_hex = partes
        dk = hashlib.pbkdf2_hmac(
            algo,
            password.encode('utf-8'),
            salt.encode('utf-8'),
            iterations=260_000
        )
        return secrets.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def cargar_usuarios() -> Dict[str, dict]:
    """Carga la base de datos de usuarios desde el archivo JSON."""
    if not USERS_FILE.exists():
        return {}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Error cargando usuarios de Centauro: {e}")
        return {}


def autenticar(username: str, password: str) -> Optional[dict]:
    """
    Autentica un usuario contra la base de datos.

    Args:
        username: Nombre de usuario (case-insensitive, se normaliza a minúsculas)
        password: Contraseña en texto plano

    Returns:
        Dict con datos del usuario si las credenciales son válidas:
            {"nombre_completo": str, "rol": str, "password_hash": str}
        None si las credenciales son incorrectas
    """
    if not username or not password:
        return None

    usuarios = cargar_usuarios()
    username_normalizado = username.strip().lower()

    if username_normalizado not in usuarios:
        return None

    usuario = usuarios[username_normalizado]

    if not verificar_password(password, usuario.get("password_hash", "")):
        return None

    return usuario
