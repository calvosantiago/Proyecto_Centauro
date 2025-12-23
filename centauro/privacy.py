import re
from dataclasses import dataclass
from typing import Dict

# --- Patrones de Detección (España) ---
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:(?:\+|00)\s?34[\s-]?)?(?:\b\d[\s-]?){8,12}\b")
DNI_RE = re.compile(r"\b(\d{8})\s?([A-Z])\b", re.IGNORECASE)
NIE_RE = re.compile(r"\b([XYZ])\s?(\d{7})\s?([A-Z])\b", re.IGNORECASE)
IBAN_ES_RE = re.compile(r"\bES\d{2}(?:\s?\d{4}){5}\b", re.IGNORECASE)

@dataclass
class RedactionResult:
    text: str
    stats: Dict[str, int]

def redact_pii(text: str) -> RedactionResult:
    """
    Busca patrones de datos personales y los reemplaza por etiquetas [REDACTED_X].
    """
    stats = {"EMAIL": 0, "PHONE": 0, "DNI": 0, "NIE": 0, "IBAN_ES": 0}

    def _sub(pattern: re.Pattern, label: str, t: str) -> str:
        # Función auxiliar para reemplazar y contar
        def repl(match: re.Match) -> str:
            stats[label] += 1
            return f"[REDACTED_{label}]"
        return pattern.sub(repl, t)

    out = text

    # Orden recomendado: Emails e IBAN primero (son inconfundibles)
    out = _sub(EMAIL_RE, "EMAIL", out)
    out = _sub(IBAN_ES_RE, "IBAN_ES", out)
    
    # Identificadores (NIE antes que DNI por si acaso, aunque tienen letras distintas)
    out = _sub(NIE_RE, "NIE", out)
    out = _sub(DNI_RE, "DNI", out)

    # Teléfonos al final (para evitar romper números largos que sean parte de otros datos)
    out = _sub(PHONE_RE, "PHONE", out)

    return RedactionResult(text=out, stats=stats)