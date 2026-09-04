from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QPoint, QRunnable, Qt, QThreadPool, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QWidget,
)

try:
    from services.dadata_client import DaDataClient
except Exception:
    DaDataClient = None  # type: ignore


class _Popup(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SuggestPopup")
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setWordWrap(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMaximumHeight(280)

    def show_below(self, owner: QLineEdit):
        if not owner.isVisible():
            return
        width = max(owner.width(), 420)
        popup_height = min(max(self.sizeHintForRow(0) * max(self.count(), 1) + 8, 48), 280)
        point = owner.mapToGlobal(QPoint(0, owner.height()))
        self.setFixedWidth(width)
        self.resize(width, popup_height)
        self.move(point)
        self.show()


class _SuggestSignals(QtCore.QObject):
    finished = QtCore.pyqtSignal(int, str, list, str)


class _SuggestWorker(QRunnable):
    def __init__(self, request_id: int, query: str, count: int, client_factory):
        super().__init__()
        self.request_id = request_id
        self.query = query
        self.count = count
        self._client_factory = client_factory
        self.signals = _SuggestSignals()

    @staticmethod
    def _normalize_payload(item: Dict[str, Any], display: str, source: str) -> Dict[str, Any]:
        return {
            "display": display,
            "value": item.get("value") or display or source,
            "source": source or display,
            "country": item.get("country"),
            "region": item.get("region"),
            "city": item.get("city"),
            "street": item.get("street"),
            "house": item.get("house"),
            "block": item.get("block"),
            "flat": item.get("flat"),
            "postal_code": item.get("postal_code"),
            "fias_id": item.get("fias_id"),
            "kladr_id": item.get("kladr_id"),
            "geo_lat": item.get("geo_lat"),
            "geo_lon": item.get("geo_lon"),
        }

    def run(self):
        items: List[Dict[str, Any]] = []
        error = ""

        if self._client_factory is None:
            self.signals.finished.emit(self.request_id, self.query, items, error)
            return

        try:
            client = self._client_factory()
            if client is None or not getattr(client, "is_configured", False):
                self.signals.finished.emit(self.request_id, self.query, items, error)
                return

            raw_items = client.suggest(self.query, count=self.count)
            for raw in raw_items:
                display = raw.get("value") or client.format_display(raw) or ""
                source = raw.get("source") or raw.get("value") or display
                if not display and not source:
                    continue
                items.append(self._normalize_payload(raw, display, source))
        except Exception as exc:
            error = str(exc).strip() or exc.__class__.__name__

        self.signals.finished.emit(self.request_id, self.query, items, error)


class AddressWidget(QWidget):
    """
    Address field with async DaData suggestions.

    The widget stays responsive even on slow networks:
    - debounce before searching;
    - background requests outside the UI thread;
    - stale result suppression;
    - small in-memory cache for repeated queries.

    Public API stays compatible with older forms:
    - current_text()/text()/value()
    - set_value()/set_address()
    - get_address_data()
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._ed = QLineEdit(self)
        self._ed.setPlaceholderText("Начните вводить адрес...")
        self._ed.setClearButtonEnabled(True)
        self._ed.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._btn = QPushButton("Поиск", self)
        self._btn.setFixedHeight(32)
        self._btn.setMinimumWidth(82)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setProperty("accent", "secondary")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._ed, 1)
        layout.addWidget(self._btn, 0)

        self._popup = _Popup(self)
        self._popup.itemClicked.connect(self._apply_selected)

        self._debounce = QTimer(self)
        self._debounce.setInterval(350)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._do_query)

        self._thread_pool = QThreadPool.globalInstance()
        self._request_serial = 0
        self._latest_request_id = 0
        self._count = 15
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        self._selected_payload: Dict[str, Any] | None = None
        self._last_error: str = ""

        self._client_factory = None
        if DaDataClient is not None:
            try:
                probe = DaDataClient()
            except Exception:
                probe = None
            if probe is not None and getattr(probe, "is_configured", False):
                self._client_factory = DaDataClient

        self._ed.textEdited.connect(self._on_text_edited)
        self._ed.installEventFilter(self)
        self._btn.clicked.connect(self._force_query)

    # ---------- public ----------
    def current_text(self) -> str:
        return self._ed.text().strip()

    def text(self) -> str:
        return self.current_text()

    def value(self) -> str:
        return self.current_text()

    def set_value(self, text: str):
        value = (text or "").strip()
        blocker = QtCore.QSignalBlocker(self._ed)
        self._ed.setText(value)
        self._selected_payload = self._minimal_payload(value) if value else None
        self._popup.hide()
        del blocker

    def set_address(self, text: str):
        self.set_value(text)

    def get_address_data(self) -> Dict[str, Any]:
        current = self.current_text()
        if not current:
            return self._minimal_payload("")

        payload = self._selected_payload or self._find_cached_payload(current)
        if payload is None:
            payload = self._minimal_payload(current)

        payload = dict(payload)
        payload["value"] = payload.get("value") or current
        payload["source"] = payload.get("source") or current
        return payload

    # ---------- events ----------
    def eventFilter(self, obj, event):
        if obj is self._ed and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                if not self._popup.isVisible():
                    if self._popup.count() > 0:
                        self._popup.show_below(self._ed)
                else:
                    self._navigate_popup(event.key() == Qt.Key.Key_Down)
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._popup.isVisible() and self._popup.currentItem():
                    self._apply_selected(self._popup.currentItem())
                    return True
            if event.key() == Qt.Key.Key_Escape and self._popup.isVisible():
                self._popup.hide()
                return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        if self._popup.isVisible():
            self._popup.show_below(self._ed)

    def focusOutEvent(self, event: QtGui.QFocusEvent):
        super().focusOutEvent(event)
        if not self._popup.underMouse():
            self._popup.hide()

    def _navigate_popup(self, forward: bool):
        count = self._popup.count()
        if count == 0:
            return
        current = self._popup.currentRow()
        current = (current + (1 if forward else -1)) % count
        self._popup.setCurrentRow(current)

    # ---------- search ----------
    def _on_text_edited(self, _text: str):
        self._selected_payload = None
        query = self.current_text()
        if self._client_factory is None:
            self._popup.hide()
            return
        if len(query) < 3:
            self._popup.hide()
            return
        self._debounce.start()

    def _force_query(self):
        if self._client_factory is None:
            return
        self._debounce.stop()
        self._do_query()

    def _do_query(self):
        if self._client_factory is None:
            return

        query = self.current_text()
        if len(query) < 3:
            self._popup.hide()
            return

        cache_key = self._cache_key(query)
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._fill_popup(cached)
            return

        self._request_serial += 1
        self._latest_request_id = self._request_serial
        self._set_busy(True)

        worker = _SuggestWorker(
            request_id=self._request_serial,
            query=query,
            count=self._count,
            client_factory=self._client_factory,
        )
        worker.signals.finished.connect(self._on_query_finished)
        self._thread_pool.start(worker)

    def _on_query_finished(self, request_id: int, query: str, items: list, error: str):
        if request_id != self._latest_request_id:
            return

        self._set_busy(False)
        self._last_error = error

        if self.current_text() != query:
            return

        self._cache[self._cache_key(query)] = list(items)
        self._fill_popup(items)

    def _fill_popup(self, items: List[Dict[str, Any]]):
        self._popup.clear()
        for payload in items[: self._count]:
            display = payload.get("display") or payload.get("value") or payload.get("source") or ""
            if not display:
                continue
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, dict(payload))
            self._popup.addItem(item)

        if self._popup.count() > 0:
            self._popup.setCurrentRow(0)
            self._popup.show_below(self._ed)
        else:
            self._popup.hide()

    def _apply_selected(self, item: QListWidgetItem):
        payload = item.data(Qt.ItemDataRole.UserRole) or {}
        full_text = payload.get("source") or payload.get("value") or payload.get("display") or ""
        blocker = QtCore.QSignalBlocker(self._ed)
        self._ed.setText(str(full_text))
        del blocker
        self._selected_payload = dict(payload)
        self._popup.hide()

    # ---------- helpers ----------
    def _set_busy(self, busy: bool):
        self._btn.setText("Ищем..." if busy else "Поиск")

    @staticmethod
    def _cache_key(query: str) -> str:
        return query.strip().lower()

    def _find_cached_payload(self, current_text: str) -> Dict[str, Any] | None:
        cache_key = self._cache_key(current_text)
        cached = self._cache.get(cache_key) or []
        for payload in cached:
            if (payload.get("source") or payload.get("value") or "").strip() == current_text:
                return dict(payload)
        return None

    @staticmethod
    def _minimal_payload(text: str) -> Dict[str, Any]:
        cleaned = (text or "").strip()
        return {
            "display": cleaned,
            "value": cleaned,
            "source": cleaned,
            "country": None,
            "region": None,
            "city": None,
            "street": None,
            "house": None,
            "block": None,
            "flat": None,
            "postal_code": None,
            "fias_id": None,
            "kladr_id": None,
            "geo_lat": None,
            "geo_lon": None,
        }
