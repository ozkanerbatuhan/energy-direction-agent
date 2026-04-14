"""
storage.py — data.json dosyası üzerinde okuma/yazma işlemleri.

• Dosya yoksa veya bozuksa güvenli bir şekilde boş dict döndürür.
• Yazma işleminde atomik güncelleme yapar (önce temp, sonra rename).
"""

import json
import logging
import time
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

def _history_dir() -> Path:
    """Geçmiş verilerin kaydedileceği dizini döndürür."""
    path = Path("data/history")
    path.mkdir(parents=True, exist_ok=True)
    return path

def _history_path(date_str: str) -> Path:
    return _history_dir() / f"history_{date_str}.json"

async def read_history_cache(date_str: str) -> dict | None:
    """
    Belirtilen güne ait önbellek dosyasını okur.
    Bulunursa last_accessed güncelleyerek payload'u döner.
    """
    path = _history_path(date_str)
    if not path.exists():
        return None

    try:
        text = path.read_text(encoding="utf-8")
        wrapper = json.loads(text)
        
        # Erişim zamanını güncelle
        wrapper["last_accessed"] = time.time()
        path.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")
        
        return wrapper.get("payload")
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Geçmiş önbellek ({date_str}) okunamadı: {exc}")
        return None

async def write_history_cache(date_str: str, raw_data: dict) -> None:
    """
    Belirtilen güne ait API yanıtını önbelleğe yazar. (Hatalı/boş verileri filtrele)
    Eğer çekilen veriler boş değilse kaydeder.
    """
    # Basit güvenlik filtresi: eğer RT Generation veya RT Consumption boşsa arıza veya 429 oluşmuş olabilir!
    if not raw_data.get("realtime_generation") or not raw_data.get("realtime_consumption"):
        logger.warning(f"{date_str} için veriler eksik (Muhtemel 429 hatası) — Önbelleğe alınmıyor.")
        return

    path = _history_path(date_str)
    wrapper = {
        "last_accessed": time.time(),
        "payload": raw_data
    }
    
    tmp_path = path.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(
            json.dumps(wrapper, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_path.replace(path)
        logger.info(f"{date_str} için API uç noktası önbelleğe alındı.")
    except OSError:
        logger.exception(f"{date_str} önbelleğe yazılamadı.")

def cleanup_old_history(days: int = 3) -> None:
    """
    Belirtilen günden daha eski 'last_accessed' süresine sahip önbellek dosyalarını siler.
    """
    history_dir = _history_dir()
    cutoff_time = time.time() - (days * 86400)
    
    deleted_count = 0
    for file_path in history_dir.glob("history_*.json"):
        try:
            wrapper = json.loads(file_path.read_text(encoding="utf-8"))
            last_accessed = wrapper.get("last_accessed", 0)
            if last_accessed < cutoff_time:
                file_path.unlink()
                deleted_count += 1
        except Exception:
            # Bozuksa direkt sil
            try:
                file_path.unlink()
                deleted_count += 1
            except:
                pass
                
    if deleted_count > 0:
        logger.info(f"{deleted_count} adet eski önbellek dosyası temizlendi.")
