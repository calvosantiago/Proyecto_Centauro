"""
sharepoint_watcher.py - Monitor de OneDrive para Centauro

Vigila la carpeta /Centauro/Pendientes/ en el OneDrive personal del usuario.
Power Automate copia ahí automáticamente las grabaciones de Teams desde SharePoint.

Nombre de archivo esperado (lo pone Power Automate):
  {Asesor}_{nombre_original}.mp4
  Ejemplo: Ivonne Rose_Grabacion Teams 2026-04-28.mp4

Cuando detecta un archivo nuevo:
  1. Extrae el asesor del nombre del archivo
  2. Descarga a inputs/batch/
  3. Lanza BatchProcessor (mismos agentes que Chainlit)
  4. Marca el archivo como procesado en outputs/watcher_state.json

Deduplicación: por OneDrive item ID — nunca descarga el mismo archivo dos veces.

Diseñado para correr 24/7 como servicio systemd en Hetzner.
"""
import os
import sys
import json
import time
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv, set_key
load_dotenv(ROOT / ".env")

from centauro.config import settings

# ── Configuración ─────────────────────────────────────────────────────────────
ONEDRIVE_FOLDER  = os.getenv("ONEDRIVE_FOLDER", "Centauro/Pendientes")
SP_POLL_INTERVAL = int(os.getenv("SP_POLL_INTERVAL", "300"))

# Ventana horaria en la que el watcher NO procesa entrevistas.
# Durante ese bloque sigue comprobando OneDrive (para no perder el delta),
# pero deja los archivos sin procesar hasta que salga del horario de trabajo.
# Formato: hora entera (0-23). Por defecto: bloquear de 8 a 19 (8:00 → 19:00).
# Para desactivar el bloqueo: poner WATCHER_HORA_INICIO=0 y WATCHER_HORA_FIN=0
WATCHER_HORA_INICIO = int(os.getenv("WATCHER_HORA_INICIO", "8"))   # incluido
WATCHER_HORA_FIN    = int(os.getenv("WATCHER_HORA_FIN",    "19"))  # excluido

SUPPORTED_EXTENSIONS = {".mp4", ".mp3", ".vtt", ".docx", ".txt"}
STATE_FILE      = settings.OUTPUTS_DIR / "watcher_state.json"
BATCH_INPUT_DIR = settings.INPUTS_DIR / "batch"
GRAPH_BASE      = "https://graph.microsoft.com/v1.0"


def _en_horario_trabajo() -> bool:
    """Devuelve True si ahora mismo estamos dentro de la ventana bloqueada."""
    if WATCHER_HORA_INICIO == 0 and WATCHER_HORA_FIN == 0:
        return False  # bloqueo desactivado
    hora = datetime.now().hour
    if WATCHER_HORA_INICIO < WATCHER_HORA_FIN:
        # Ventana normal: ej. 8 → 19
        return WATCHER_HORA_INICIO <= hora < WATCHER_HORA_FIN
    else:
        # Ventana invertida (cruza medianoche): ej. 22 → 6
        return hora >= WATCHER_HORA_INICIO or hora < WATCHER_HORA_FIN


# ── Logging ───────────────────────────────────────────────────────────────────
def _setup_logging() -> logging.Logger:
    log_file = settings.OUTPUTS_DIR / "watcher_log.txt"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    logger = logging.getLogger("centauro_watcher")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


# ── GraphClient ───────────────────────────────────────────────────────────────
class GraphClient:
    """
    Cliente Microsoft Graph API.
    Usa GRAPH_REFRESH_TOKEN con scope Files.Read para acceder al OneDrive personal.
    """

    def __init__(self):
        self.client_id     = os.getenv("AZURE_CLIENT_ID")
        self.tenant_id     = os.getenv("AZURE_TENANT_ID")
        self._access_token: Optional[str]      = None
        self._token_expiry: Optional[datetime] = None

    def get_access_token(self) -> str:
        if (
            self._access_token
            and self._token_expiry
            and datetime.now() < self._token_expiry - timedelta(minutes=5)
        ):
            return self._access_token

        refresh_token = os.getenv("GRAPH_REFRESH_TOKEN")
        if not refresh_token:
            raise RuntimeError(
                "No hay GRAPH_REFRESH_TOKEN en .env. "
                "Ejecuta: python scripts/sharepoint_auth.py"
            )

        token_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        )
        resp = requests.post(
            token_url,
            data={
                "grant_type":    "refresh_token",
                "client_id":     self.client_id,
                "refresh_token": refresh_token,
                "scope":         "https://graph.microsoft.com/Files.Read",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Error renovando token [{resp.status_code}]: {resp.text[:300]}"
            )

        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expiry = datetime.now() + timedelta(
            seconds=int(data.get("expires_in", 3600))
        )

        new_rt = data.get("refresh_token")
        if new_rt and new_rt != refresh_token:
            set_key(str(ROOT / ".env"), "GRAPH_REFRESH_TOKEN", new_rt)
            os.environ["GRAPH_REFRESH_TOKEN"] = new_rt

        return self._access_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_access_token()}"}

    def get_delta(self, delta_url: Optional[str] = None) -> tuple[list, str]:
        """
        Devuelve (items_nuevos_o_modificados, nueva_delta_url).
        Primera llamada: devuelve todos los archivos actuales.
        Siguientes: solo los cambios desde la última vez.
        """
        url = (
            delta_url
            or f"{GRAPH_BASE}/me/drive/root:/{ONEDRIVE_FOLDER}:/delta"
        )
        items:         list = []
        next_delta_url: str = ""

        while url:
            resp = requests.get(url, headers=self._headers(), timeout=60)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("value", []))
            url            = data.get("@odata.nextLink")
            next_delta_url = data.get("@odata.deltaLink", next_delta_url)

        return items, next_delta_url

    def download_file(self, item_id: str, dest: Path) -> bool:
        token = self.get_access_token()
        url   = f"{GRAPH_BASE}/me/drive/items/{item_id}/content"
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                stream=True,
                timeout=600,
            )
            if resp.status_code != 200:
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            return True
        except Exception:
            return False


# ── WatcherState ──────────────────────────────────────────────────────────────
class WatcherState:
    """Persiste qué item IDs ya se procesaron y el delta_url para el próximo ciclo."""

    def __init__(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"processed": {}, "delta_url": None}

    def _save(self):
        STATE_FILE.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def is_processed(self, item_id: str) -> bool:
        return item_id in self._data["processed"]

    def mark_processed(self, item_id: str, filename: str):
        self._data["processed"][item_id] = {
            "filename": filename,
            "at":       datetime.now().isoformat(),
        }
        self._save()

    @property
    def delta_url(self) -> Optional[str]:
        return self._data.get("delta_url") or None

    @delta_url.setter
    def delta_url(self, value: str):
        self._data["delta_url"] = value
        self._save()


# ── Watcher ───────────────────────────────────────────────────────────────────
class OneDriveWatcher:

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.graph  = GraphClient()
        self.state  = WatcherState()

    def _procesar_item(self, item: dict) -> bool:
        item_id  = item["id"]
        filename = item.get("name", "")

        if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False
        if self.state.is_processed(item_id):
            return False

        dest = BATCH_INPUT_DIR / filename
        self.logger.info(f"Nuevo archivo: {filename}")
        self.logger.info(f"  → Descargando a inputs/batch/")

        ok = self.graph.download_file(item_id, dest)
        if not ok:
            self.logger.error(f"  Fallo al descargar {filename}")
            return False

        self.logger.info(f"  Descargado ({dest.stat().st_size // 1024} KB)")

        try:
            from batch_processor import BatchProcessor
            processor = BatchProcessor()
            processor.procesar_archivo(dest)
        except Exception as e:
            self.logger.error(f"  Error en batch_processor: {e}")
            self.state.mark_processed(item_id, filename)
            return False

        self.state.mark_processed(item_id, filename)
        return True

    def ciclo(self):
        try:
            items, new_delta_url = self.graph.get_delta(self.state.delta_url)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 410:
                self.logger.warning("Delta token expirado — reiniciando escaneo completo")
                self.state.delta_url = None
                items, new_delta_url = self.graph.get_delta(None)
            else:
                self.logger.error(f"Error HTTP en delta: {e}")
                return
        except Exception as e:
            self.logger.error(f"Error obteniendo delta de OneDrive: {e}")
            return

        if new_delta_url:
            self.state.delta_url = new_delta_url

        archivos = [i for i in items if "file" in i and not i.get("deleted")]
        nuevos   = [i for i in archivos if not self.state.is_processed(i["id"])]

        if not nuevos:
            self.logger.info("Sin archivos nuevos en OneDrive.")
            return

        # ── Ventana horaria: no procesar durante el horario de trabajo ────────
        # Se detectan los archivos y se guarda el delta_url, pero se pospone
        # la descarga y evaluación hasta fuera del horario configurado.
        if _en_horario_trabajo():
            self.logger.info(
                f"{len(nuevos)} archivo(s) pendiente(s) — "
                f"horario de trabajo ({WATCHER_HORA_INICIO}:00-{WATCHER_HORA_FIN}:00), "
                f"procesamiento pospuesto hasta las {WATCHER_HORA_FIN}:00."
            )
            return

        self.logger.info(f"{len(nuevos)} archivo(s) nuevo(s) detectado(s).")
        for item in nuevos:
            try:
                self._procesar_item(item)
            except Exception as e:
                self.logger.error(f"Error procesando {item.get('name', '?')}: {e}")

    def ejecutar(self):
        SEP = "=" * 60
        self.logger.info(SEP)
        self.logger.info("CENTAURO ONEDRIVE WATCHER")
        self.logger.info(f"Carpeta OneDrive : {ONEDRIVE_FOLDER}")
        self.logger.info(f"Intervalo        : {SP_POLL_INTERVAL}s ({SP_POLL_INTERVAL // 60} min)")
        self.logger.info(SEP)

        while True:
            self.logger.info(f"Ciclo — {datetime.now().strftime('%H:%M:%S')}")
            try:
                self.ciclo()
            except Exception as e:
                self.logger.error(f"Error inesperado: {e}")
            self.logger.info(f"Próxima comprobación en {SP_POLL_INTERVAL}s...")
            time.sleep(SP_POLL_INTERVAL)


# ── Punto de entrada ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger = _setup_logging()
    watcher = OneDriveWatcher(logger)
    watcher.ejecutar()
