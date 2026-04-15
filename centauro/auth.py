"""
Módulo de autenticación para Centauro v5.0

Sistema de autenticación basado en usuario/contraseña con:
- Contraseñas hasheadas con PBKDF2-SHA256 (estándar NIST 2024)
- Usuarios almacenados en Supabase (tabla `usuarios_auth`)
- Roles: "asesor" | "admin"
- Mapeo username → nombre completo del asesor (para perfiles automáticos)
"""
import hashlib
import secrets
from typing import Optional

from .config import settings

AUTH_USERS_TABLE = "usuarios_auth"
_supabase_client = None


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


def _get_supabase_client():
    """
    Crea (lazy) y devuelve el cliente de Supabase para autenticación.

    Retorna None si faltan credenciales o si el cliente no se puede inicializar.
    """
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    url = getattr(settings, "SUPABASE_URL", "") or ""
    key = getattr(settings, "SUPABASE_KEY", "") or ""
    if not url or not key:
        print("⚠️ AUTH: SUPABASE_URL/SUPABASE_KEY no configurados.")
        return None

    try:
        from supabase import create_client
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception as e:
        print(f"⚠️ AUTH: Error inicializando cliente Supabase: {e}")
        return None


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

    username_normalizado = username.strip().lower()
    client = _get_supabase_client()
    if client is None:
        return None

    try:
        result = (
            client.table(AUTH_USERS_TABLE)
            .select("username,nombre_completo,rol,password_hash,activo")
            .eq("username", username_normalizado)
            .limit(1)
            .execute()
        )
    except Exception as e:
        print(f"⚠️ AUTH: Error consultando usuarios en Supabase: {e}")
        return None

    if not result.data:
        return None

    usuario = result.data[0]
    if usuario.get("activo") is False:
        return None

    if not verificar_password(password, usuario.get("password_hash", "")):
        return None

    return usuario
