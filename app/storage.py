"""
storage.py — data.json dosyası üzerinde okuma/yazma işlemleri.

• Dosya yoksa veya bozuksa güvenli bir şekilde boş dict döndürür.
• Yazma işleminde atomik güncelleme yapar (önce temp, sonra rename).
"""

import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _data_path() -> Path:
    """data.json yolunu Path nesnesi olarak döndürür."""
    return Path(settings.DATA_FILE)


async def read_data() -> dict:
    """
    data.json dosyasını okur ve dict olarak döndürür.
    Dosya yoksa veya parse edilemezse boş dict döndürür.
    """
    path = _data_path()
    if not path.exists():
        logger.info("data.json henüz oluşturulmamış — boş dict dönülüyor.")
        return {}

    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("data.json okunamadı: %s — boş dict dönülüyor.", exc)
        return {}


async def write_data(data: dict) -> None:
    """
    data dict'ini data.json dosyasına yazar.
    Atomik yazma: önce .tmp dosyasına yazar, sonra rename eder.
    """
    path = _data_path()
    tmp_path = path.with_suffix(".json.tmp")

    try:
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)
        logger.info("data.json güncellendi.")
    except OSError:
        logger.exception("data.json yazılamadı.")
