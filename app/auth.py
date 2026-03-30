"""
auth.py — EPİAŞ TGT (Ticket Granting Ticket) kimlik doğrulama modülü.

• POST ile TGT alır ve modül seviyesinde saklar.
• Scheduler tarafından her 90 dakikada bir otomatik yenilenir.
• Thread-safe erişim için asyncio.Lock kullanır.
• urllib3 kullanır (eptr2 referansıyla uyumlu).
"""

import asyncio
import logging
from urllib.parse import quote

import urllib3

from app.config import EPIAS_AUTH_URL, settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Modül seviyesinde TGT durumu
# ──────────────────────────────────────────────
_current_tgt: str | None = None
_tgt_lock = asyncio.Lock()


def _request_tgt_sync(username: str, password: str) -> str:
    """
    EPİAŞ CAS sunucusuna POST atarak yeni bir TGT alır (senkron).

    eptr2 kütüphanesiyle aynı yöntemi kullanır:
    - Content-Type: application/x-www-form-urlencoded
    - Accept: text/plain
    - Body: username=...&password=...
    - TGT, yanıt gövdesinde (body) düz metin olarak döner.
    """
    http = urllib3.PoolManager(cert_reqs="CERT_REQUIRED")

    body_str = f"username={quote(username)}&password={quote(password)}"

    res = http.request(
        method="POST",
        url=EPIAS_AUTH_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/plain",
        },
        body=body_str,
        timeout=15.0,
    )

    if res.status not in (200, 201):
        raise ValueError(
            f"TGT alınamadı — HTTP {res.status}: {res.data.decode('utf-8', errors='replace')}"
        )

    res_data = res.data.decode("utf-8").strip()

    if res_data.startswith("TGT-"):
        logger.info("TGT alındı (body): %s…", res_data[:25])
        return res_data

    # Bazı durumlarda Location header'dan dönüyor olabilir
    location = res.headers.get("Location", "")
    if location:
        tgt = location.rsplit("/", 1)[-1]
        if tgt.startswith("TGT-"):
            logger.info("TGT alındı (Location): %s…", tgt[:25])
            return tgt

    raise ValueError(f"TGT yanıttan çıkarılamadı — body: {res_data[:100]}")


async def refresh_tgt() -> None:
    """
    TGT'yi yeniler. Scheduler tarafından periyodik olarak çağrılır.
    Hata durumunda mevcut TGT korunur.
    """
    global _current_tgt

    try:
        # Senkron HTTP çağrısını event loop'u bloklamadan çalıştır
        loop = asyncio.get_event_loop()
        new_tgt = await loop.run_in_executor(
            None,
            _request_tgt_sync,
            settings.EPIAS_USERNAME,
            settings.EPIAS_PASSWORD,
        )
        async with _tgt_lock:
            _current_tgt = new_tgt
        logger.info("TGT başarıyla yenilendi.")
    except Exception:
        logger.exception("TGT yenileme başarısız oldu — mevcut token korunuyor.")


async def get_current_tgt() -> str | None:
    """Mevcut TGT'yi döndürür. Henüz alınmamışsa None döner."""
    async with _tgt_lock:
        return _current_tgt
