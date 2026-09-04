# ShukCar/services/dadata_client.py
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import os

# Пытаемся подтянуть config.py, но не требуем жёстко
try:
    import config as _cfg  # type: ignore
except Exception:
    _cfg = None


class DaDataClient:
    """
    Клиент для подсказок адресов DaData.

    Основные методы:
      - suggest(query, count=10) -> List[Dict[str, Any]]
          Возвращает «сырые» данные DaData (value, unrestricted_value и т.д.).
      - suggest_address(query, count=10) -> List[Tuple[str, str]]
          Удобная обёртка для UI: список кортежей (display, full).
          display — то, что показывать в выпадающем списке;
          full — полная строка для подстановки в поле.

    Диагностику проблем пишет в self.last_error (строка) — UI может её показать.
    """
    BASE_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"

    def __init__(self):
        token_from_cfg = getattr(_cfg, "DADATA_TOKEN", "") if _cfg else ""
        secret_from_cfg = getattr(_cfg, "DADATA_SECRET", "") if _cfg else ""
        self.token = (token_from_cfg or os.getenv("DADATA_TOKEN", "")).strip()
        self.secret = (secret_from_cfg or os.getenv("DADATA_SECRET", "")).strip()

        # Прокси (опционально)
        http_proxy = getattr(_cfg, "HTTP_PROXY", "") if _cfg else os.getenv("HTTP_PROXY", "")
        https_proxy = getattr(_cfg, "HTTPS_PROXY", "") if _cfg else os.getenv("HTTPS_PROXY", "")
        self.proxies = None
        if http_proxy or https_proxy:
            self.proxies = {
                "http": http_proxy or None,
                "https": https_proxy or None,
            }

        self.last_error: Optional[str] = None

    # ---------- сервисные ----------
    @property
    def is_configured(self) -> bool:
        """Есть ли токен — можно ли ходить в DaData."""
        return bool(self.token)

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {self.token}",
        }
        if self.secret:
            headers["X-Secret"] = self.secret
        return headers

    # ---------- низкоуровневый метод (оставлен как у тебя) ----------
    def suggest(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        """
        Возвращает «сырые» словари DaData для адресов.
        """
        self.last_error = None

        if not self.token:
            self.last_error = "Не задан DADATA_TOKEN (config.py)."
            return []

        try:
            import requests  # type: ignore
        except Exception:
            self.last_error = "Пакет 'requests' не установлен в .venv."
            return []

        # Чуть заранее отсекаем слишком короткие запросы (экономим сеть)
        if not query or len(query.strip()) < 3:
            return []

        try:
            resp = requests.post(
                self.BASE_URL,
                headers=self._headers(),
                json={"query": query.strip(), "count": count},
                timeout=8,
                proxies=self.proxies,
            )
        except Exception as e:
            self.last_error = f"Сетевая ошибка: {e!s}"
            return []

        if resp.status_code != 200:
            # Попробуем вытащить тело, чтобы понять причину (часто приходит JSON с ошибкой)
            body = ""
            try:
                body = resp.text[:300]
            except Exception:
                pass
            self.last_error = f"HTTP {resp.status_code}. {body}"
            return []

        try:
            js = resp.json()
        except Exception as e:
            self.last_error = f"Некорректный ответ от DaData: {e!s}"
            return []

        suggestions = js.get("suggestions", []) or []
        out: List[Dict[str, Any]] = []
        for s in suggestions:
            d = (s or {}).get("data", {}) or {}
            out.append({
                "value": (s or {}).get("value"),
                "source": (s or {}).get("unrestricted_value"),
                "country": d.get("country"),
                "region": d.get("region_with_type") or d.get("region"),
                "city": d.get("city_with_type") or d.get("city") or d.get("settlement_with_type"),
                "street": d.get("street_with_type"),
                "house": d.get("house"),
                "block": d.get("block"),
                "flat": d.get("flat"),
                "postal_code": d.get("postal_code"),
                "fias_id": d.get("fias_id"),
                "kladr_id": d.get("kladr_id"),
                "geo_lat": d.get("geo_lat"),
                "geo_lon": d.get("geo_lon"),
            })
        return out

    # ---------- удобный метод для UI: список (display, full) ----------
    def suggest_address(self, query: str, count: int = 10) -> List[Tuple[str, str]]:
        """
        Возвращает список кортежей (display, full) для выпадающих подсказок.
        display — человекочитаемая строка в списке;
        full    — полная строка (обычно unrestricted_value) для подстановки в поле.
        Совместим с AddressWidget.
        """
        results = self.suggest(query, count=count)
        out: List[Tuple[str, str]] = []
        for item in results:
            display = item.get("value") or self.format_display(item) or ""
            full = item.get("source") or item.get("value") or display
            if display:
                out.append((display, full))
        return out

    # ---------- форматирование строки для display (на всякий случай) ----------
    @staticmethod
    def format_display(item: Dict[str, Any]) -> str:
        """
        Подстраховка: если 'value' пуст, собираем понятную подпись из полей.
        """
        parts: List[str] = []
        for key in ("country", "region", "city", "street"):
            v = item.get(key)
            if v:
                parts.append(v)
        # дом/корпус/квартира
        house = item.get("house")
        block = item.get("block")
        flat = item.get("flat")
        tail = []
        if house:
            tail.append(f"д. {house}")
        if block:
            tail.append(f"к. {block}")
        if flat:
            tail.append(f"кв. {flat}")
        if tail:
            parts.append(", ".join(tail))
        # индекс — в конец, в скобках
        idx = item.get("postal_code")
        s = ", ".join([p for p in parts if p])
        if idx:
            s = f"{s} ({idx})" if s else idx
        return s
