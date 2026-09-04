# ShukCar/ui/cars_view.py
import os
import csv
import shutil
from pathlib import Path
from typing import Optional

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QMessageBox, QLineEdit, QFileDialog, QFrame, QComboBox
)
from PyQt6.QtCore import Qt, QSize, QTimer
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import joinedload

from db import SessionLocal
from models import Brand, Car, CarMedia, Client, Model, User, UserRole
from services.crm import priority_label
from services.deal_sync import remove_deal_for_car, set_car_archive_state
from audit import log_action
from .car_form import CarFormDialog
from .car_details import CarDetailsWindow
from utils.pdf_export import export_car_pdf

PKG_ROOT = Path(__file__).resolve().parents[1]
IMG_ROOT = PKG_ROOT / "img" / "cars"


# ===== Безопасная загрузка изображений =====
def safe_load_pixmap(path: Path, target_size: QSize) -> Optional[QtGui.QPixmap]:
    """
    Безопасно читает картинку через QImageReader, ограничивает размер для экономии памяти
    и возвращает QPixmap. Любые ошибки проглатываются (вернёт None).
    """
    try:
        if not path.exists() or not path.is_file():
            return None

        reader = QtGui.QImageReader(str(path))
        # автоориентация по EXIF
        reader.setAutoTransform(True)

        # Ограничим целевой размер — не больше целевого виджета (с небольшим запасом)
        w = max(1, target_size.width())
        h = max(1, target_size.height())
        reader.setScaledSize(QtCore.QSize(w, h))

        image = reader.read()
        if image.isNull():
            return None

        # В PyQt6 QPixmap лучше делать уже из QImage
        pm = QtGui.QPixmap.fromImage(image)
        if pm.isNull():
            return None

        # Доп. аккуратное масштабирование до конца (на случай, если пропорции гуляют)
        pm = pm.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio,
                       QtCore.Qt.TransformationMode.SmoothTransformation)
        return pm
    except Exception:
        return None


class CarCard(QFrame):
    """Карточка авто. Подсвечивается рамкой при выборе и отдаёт клик/двойной клик наружу."""
    COVER_SIZE = QSize(240, 160)
    clicked = QtCore.pyqtSignal()
    double_clicked = QtCore.pyqtSignal()

    def __init__(self, car: Car, parent=None):
        super().__init__(parent)
        self.car = car
        self.setObjectName("CarCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.cover = QLabel()
        self.cover.setObjectName("CardCover")
        self.cover.setFixedSize(self.COVER_SIZE)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setText("Загрузка...")
        self.cover.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(self.cover)

        self.info = QLabel(self._build_info_text())
        self.info.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.info.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(self.info)

        self.setProperty("selected", "false")
        self.setToolTip(self._build_tooltip())

        # Лениво грузим обложку после создания виджета (чтобы не блокировать UI)
        QTimer.singleShot(0, self.refresh_cover)

    def set_selected(self, on: bool):
        self.setProperty("selected", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _build_info_text(self) -> str:
        try:
            year = self.car.build_date.strftime("%Y") if getattr(self.car, "build_date", None) else "—"
        except Exception:
            year = "—"
        brand = (getattr(self.car.brand, "name", None) or "—")
        model = (getattr(self.car.model, "name", None) or "—")
        trim = (getattr(self.car.trim, "name", None) or "—")
        mileage = f"{(self.car.mileage_km or 0):,}".replace(",", " ") if getattr(self.car, "mileage_km", None) else "—"
        manager = getattr(getattr(self.car, "responsible_user", None), "full_name", None) or getattr(getattr(self.car, "responsible_user", None), "login", None) or "—"
        priority = priority_label(getattr(self.car, "priority", None))
        return (
            f"<b>{year}</b> | {brand} {model}<br>"
            f"Комплектация: {trim}<br>"
            f"Пробег: {mileage} км<br>"
            f"Менеджер: {manager} · Приоритет: {priority}"
        )

    def _build_tooltip(self) -> str:
        vin = getattr(self.car, "vin", None) or "—"
        drive = getattr(self.car, "drive", None) or "—"
        market = getattr(self.car, "market", None) or "—"
        stage = getattr(getattr(self.car, "deal_stage", None), "name", None) or "—"
        city = getattr(self.car, "location_city", None) or getattr(self.car, "location_country", None) or "—"
        manager = getattr(getattr(self.car, "responsible_user", None), "full_name", None) or getattr(getattr(self.car, "responsible_user", None), "login", None) or "—"
        client = getattr(getattr(self.car, "client", None), "full_name", None) or "—"
        priority = priority_label(getattr(self.car, "priority", None))
        next_action = getattr(self.car, "next_action_note", None) or "—"
        price = str(self.car.price_to_vladivostok) if getattr(self.car, "price_to_vladivostok", None) is not None else "—"
        return (f"VIN: {vin}\n"
                f"Привод: {drive}\n"
                f"Рынок: {market}\n"
                f"Стадия: {stage}\n"
                f"Клиент: {client}\n"
                f"Менеджер: {manager}\n"
                f"Приоритет: {priority}\n"
                f"Следующий шаг: {next_action}\n"
                f"Локация: {city}\n"
                f"Цена до Владивостока: {price}")

    def refresh_cover(self):
        """
        Ищем первую картинку и пытаемся очень безопасно её показать.
        Любая ошибка — не падаем, пишем 'Нет фото'.
        """
        try:
            session = SessionLocal()
            try:
                media = session.query(CarMedia).filter(
                    CarMedia.car_id == self.car.id, CarMedia.media_type == "image"
                ).order_by(CarMedia.id.asc()).first()
            finally:
                session.close()

            if not media:
                self.cover.setText("Нет фото")
                return

            p = (PKG_ROOT / media.file_path).resolve()
            pm = safe_load_pixmap(p, self.cover.size())
            if pm is None:
                self.cover.setText("Нет фото")
                return
            self.cover.setPixmap(pm)
        except Exception:
            self.cover.setText("Нет фото")


class CarsView(QWidget):
    def __init__(self, parent=None, current_role: UserRole = UserRole.user):
        super().__init__(parent)
        self.setObjectName("CarsView")
        self.current_role = current_role

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        # Поиск / кнопки
        search_row = QHBoxLayout()
        self.ed_search = QLineEdit(); self.ed_search.setPlaceholderText("VIN / клиент / менеджер / марка / модель / источник / статус ...")
        self.lbl_scope = QLabel("Показывать:")
        self.cb_scope = QComboBox()
        self.cb_scope.addItem("В работе", "active")
        self.cb_scope.addItem("Архив", "archived")
        self.cb_scope.addItem("Все авто", "all")
        self.btn_search = QPushButton("Найти")
        self.btn_clear = QPushButton("Сброс")
        search_row.addWidget(self.ed_search, 1)
        search_row.addWidget(self.lbl_scope)
        search_row.addWidget(self.cb_scope)
        search_row.addWidget(self.btn_search)
        search_row.addWidget(self.btn_clear)
        v.addLayout(search_row)

        btns = QHBoxLayout()
        self.btn_add = QPushButton("Добавить")
        self.btn_edit = QPushButton("Изменить")
        self.btn_archive = QPushButton("В архив")
        self.btn_del = QPushButton("Удалить")
        self.btn_pdf = QPushButton("PDF отчёт")
        self.btn_export = QPushButton("Экспорт CSV")
        self.btn_refresh = QPushButton("Обновить")
        self.btn_media = QPushButton("Открыть медиа-папку")
        self.btn_clear.setProperty("accent", "secondary")
        self.btn_edit.setProperty("accent", "secondary")
        self.btn_archive.setProperty("accent", "secondary")
        self.btn_del.setProperty("accent", "danger-secondary")
        self.btn_pdf.setProperty("accent", "secondary")
        self.btn_export.setProperty("accent", "secondary")
        self.btn_refresh.setProperty("accent", "secondary")
        self.btn_media.setProperty("accent", "secondary")
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_edit)
        btns.addWidget(self.btn_archive)
        btns.addWidget(self.btn_del)
        btns.addStretch(1)
        btns.addWidget(self.btn_pdf)
        btns.addWidget(self.btn_export)
        btns.addWidget(self.btn_media)
        btns.addWidget(self.btn_refresh)
        v.addLayout(btns)

        # Ограничения по ролям: стажёр — без CRUD
        if self.current_role == UserRole.trainee:
            self.btn_add.setEnabled(False)
            self.btn_edit.setEnabled(False)
            self.btn_archive.setEnabled(False)
            self.btn_del.setEnabled(False)

        # Список
        self.listw = QListWidget()
        self.listw.setViewMode(QListWidget.ViewMode.IconMode)
        self.listw.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.listw.setMovement(QListWidget.Movement.Static)
        self.listw.setSpacing(12)
        self.listw.setIconSize(QSize(260, 180))
        self.listw.setUniformItemSizes(False)
        self.listw.setWordWrap(True)
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        v.addWidget(self.listw)

        # Сигналы
        self.btn_add.clicked.connect(self.on_add)
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_archive.clicked.connect(self.on_toggle_archive)
        self.btn_del.clicked.connect(self.on_delete)
        self.btn_refresh.clicked.connect(self.load_data)
        self.btn_media.clicked.connect(self.open_media_dir)
        self.btn_export.clicked.connect(self.export_csv)
        self.btn_search.clicked.connect(self.apply_search)
        self.btn_clear.clicked.connect(self.clear_search)
        self.btn_pdf.clicked.connect(self.export_pdf_selected)
        self.cb_scope.currentIndexChanged.connect(lambda *_: self.load_data(self._last_query))

        # Открытие с клавиатуры/списка + клики с самой карточки
        self.listw.itemActivated.connect(self._on_item_open)
        self.listw.itemDoubleClicked.connect(self._on_item_open)

        self.listw.currentItemChanged.connect(self._on_current_changed)

        # защита: одно окно деталей на один автомобиль
        self._details_windows: dict[int, CarDetailsWindow] = {}

        self._last_query = None
        self.load_data()

    # ===== включение/отключение кнопок по выбору =====
    def _update_actions(self):
        has_sel = self.listw.currentItem() is not None
        self.btn_edit.setEnabled(has_sel and self.current_role != UserRole.trainee)
        self.btn_archive.setEnabled(has_sel and self.current_role != UserRole.trainee)
        self.btn_del.setEnabled(has_sel and self.current_role != UserRole.trainee)
        self.btn_pdf.setEnabled(has_sel)
        self.btn_media.setEnabled(has_sel)
        car = self._current_car()
        self.btn_archive.setText("Вернуть в работу" if car and getattr(car, "is_archived", False) else "В архив")

    # ===== выделение карточек =====
    def _on_current_changed(self, cur: Optional[QListWidgetItem], prev: Optional[QListWidgetItem]):
        if prev is not None:
            w_prev = self.listw.itemWidget(prev)
            if isinstance(w_prev, CarCard):
                w_prev.set_selected(False)
        if cur is not None:
            w_cur = self.listw.itemWidget(cur)
            if isinstance(w_cur, CarCard):
                w_cur.set_selected(True)
        self._update_actions()

    def _select_item(self, item: QListWidgetItem):
        if item:
            self.listw.setCurrentItem(item)

    def _open_item(self, item: QListWidgetItem):
        if item:
            self.listw.setCurrentItem(item)
            self._on_item_open(item)

    # ===== загрузка =====
    def _filtered_query(self, session, query: str | None = None):
        q = (
            session.query(Car)
            .outerjoin(Brand, Brand.id == Car.brand_id)
            .outerjoin(Model, Model.id == Car.model_id)
            .outerjoin(Client, Client.id == Car.client_id)
            .outerjoin(User, User.id == Car.responsible_user_id)
            .options(
                joinedload(Car.brand),
                joinedload(Car.model),
                joinedload(Car.trim),
                joinedload(Car.deal_stage),
                joinedload(Car.client),
                joinedload(Car.responsible_user),
            )
        )
        scope = self.cb_scope.currentData()
        if scope == "active":
            q = q.filter(or_(Car.is_archived.is_(False), Car.is_archived.is_(None)))
        elif scope == "archived":
            q = q.filter(Car.is_archived.is_(True))
        if query:
            qtext = f"%{query.lower()}%"
            q = q.filter(or_(
                func.lower(func.coalesce(Brand.name, "")).like(qtext),
                func.lower(func.coalesce(Model.name, "")).like(qtext),
                func.lower(func.coalesce(Client.full_name, "")).like(qtext),
                func.lower(func.coalesce(Client.phone, "")).like(qtext),
                func.lower(func.coalesce(User.full_name, "")).like(qtext),
                func.lower(func.coalesce(User.login, "")).like(qtext),
                func.lower(func.coalesce(Car.vin, "")).like(qtext),
                func.lower(func.coalesce(Car.lead_source, "")).like(qtext),
                func.lower(func.coalesce(Car.priority, "")).like(qtext),
                func.lower(func.coalesce(Car.next_action_note, "")).like(qtext),
                func.lower(func.coalesce(Car.status, "")).like(qtext),
                func.lower(func.coalesce(Car.deal_status, "")).like(qtext),
                cast(Car.id, String).like(f"%{query}%"),
            ))
        return q

    def load_data(self, query: str | None = None):
        self.listw.clear()
        self._last_query = query
        session = SessionLocal()
        try:
            cars = self._filtered_query(session, query).order_by(Car.id.desc()).all()

            for c in cars:
                try:
                    w = CarCard(c)
                    item = QListWidgetItem()
                    item.setSizeHint(QSize(280, 260))
                    # элемент должен быть выбираемым
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    self.listw.addItem(item)
                    self.listw.setItemWidget(item, w)
                    w.clicked.connect(lambda it=item: self._select_item(it))
                    w.double_clicked.connect(lambda it=item: self._open_item(it))
                except Exception:
                    # Если какая-то конкретная карточка ломает UI — пропускаем её
                    continue
        finally:
            session.close()
        self._update_actions()

    def apply_search(self):
        self.load_data(self.ed_search.text().strip() or None)

    def clear_search(self):
        self.ed_search.clear()
        self.load_data(None)

    def on_toggle_archive(self):
        if self.current_role == UserRole.trainee:
            QMessageBox.information(self, "Доступ", "Архивация недоступна для стажёра.")
            return
        car = self._current_car()
        if not car:
            QMessageBox.information(self, "Выбор", "Выберите автомобиль в списке.")
            return

        try:
            session = SessionLocal()
            try:
                obj = session.get(Car, car.id)
                if not obj:
                    QMessageBox.warning(self, "Авто", "Автомобиль не найден.")
                    return
                target_archived = not bool(obj.is_archived)
                action_text = "отправить в архив" if target_archived else "вернуть в работу"
                res = QMessageBox.question(self, "Подтверждение", f"Вы действительно хотите {action_text} автомобиль #{obj.id}?")
                if res != QMessageBox.StandardButton.Yes:
                    return
                set_car_archive_state(session, obj, target_archived)
                session.commit()
            finally:
                session.close()

            self.load_data(self._last_query)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка архивации", str(e))

    # ===== открытие карточки (только itemActivated) =====
    def _on_item_open(self, item: QListWidgetItem):
        if not item:
            return
        self.listw.setCurrentItem(item)
        w = self.listw.itemWidget(item)
        car = w.car if isinstance(w, CarCard) else None
        if not car:
            return

        # если уже открыто окно деталей для этого авто — просто активируем его
        wnd = self._details_windows.get(car.id)
        if wnd is not None:
            try:
                if wnd.isVisible():
                    wnd.raise_()
                    wnd.activateWindow()
                    return
            except Exception:
                pass
            self._details_windows.pop(car.id, None)

        try:
            wnd = CarDetailsWindow(car_id=car.id, parent=self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть карточку: {e}")
            return

        # Удаляем окно при закрытии, чтобы следующая попытка открытия
        # всегда создавала свежий экземпляр.
        try:
            wnd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            wnd.destroyed.connect(lambda *_: self._details_windows.pop(car.id, None))
        except Exception:
            pass

        self._details_windows[car.id] = wnd
        wnd.show()

    # ===== CRUD =====
    def _current_car(self) -> Optional[Car]:
        item = self.listw.currentItem()
        if not item:
            return None
        w = self.listw.itemWidget(item)
        return w.car if isinstance(w, CarCard) else None

    def on_add(self):
        if self.current_role == UserRole.trainee:
            return
        dlg = CarFormDialog(self)
        if dlg.exec():
            self.load_data(self._last_query)

    def on_edit(self):
        if self.current_role == UserRole.trainee:
            return
        car = self._current_car()
        if not car:
            QMessageBox.information(self, "Выбор", "Выберите автомобиль в списке.")
            return
        dlg = CarFormDialog(self, car_id=car.id)
        if dlg.exec():
            self.load_data(self._last_query)

    def on_delete(self):
        if self.current_role == UserRole.trainee:
            QMessageBox.information(self, "Доступ", "Удаление недоступно для стажёра.")
            return
        car = self._current_car()
        if not car:
            QMessageBox.information(self, "Выбор", "Выберите автомобиль в списке.")
            return

        res = QMessageBox.question(self, "Подтверждение", f"Удалить автомобиль #{car.id}?")
        if res != QMessageBox.StandardButton.Yes:
            return

        try:
            # Удаление из БД
            session = SessionLocal()
            try:
                obj = session.get(Car, car.id)
                if obj:
                    remove_deal_for_car(session, obj.id)
                    session.delete(obj)
                    session.commit()
                    log_action(session, user_id=None, action="delete", entity="car", entity_id=car.id)
            finally:
                session.close()

            # Удаление каталога медиа (если есть)
            car_dir = IMG_ROOT / str(car.id)
            if car_dir.exists():
                shutil.rmtree(car_dir, ignore_errors=True)

            # Обновить список
            self.load_data(self._last_query)
            QMessageBox.information(self, "Готово", f"Автомобиль #{car.id} удалён.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка удаления", str(e))

    def open_media_dir(self):
        car = self._current_car()
        if not car:
            QMessageBox.information(self, "Выбор", "Выберите автомобиль.")
            return
        car_dir = IMG_ROOT / str(car.id)
        car_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(car_dir))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить CSV", "cars_export.csv", "CSV (*.csv)")
        if not path:
            return
        session = SessionLocal()
        try:
            cars = self._filtered_query(session, self._last_query).order_by(Car.id.desc()).all()
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=';')
                w.writerow([
                    "ID",
                    "Год",
                    "Марка",
                    "Модель",
                    "Комплектация",
                    "Пробег (км)",
                    "Клиент",
                    "Менеджер",
                    "Источник",
                    "Приоритет",
                    "Статус",
                    "Статус сделки",
                    "Цена до Владивостока",
                ])
                for c in cars:
                    year = c.build_date.year if c.build_date else ""
                    w.writerow([
                        c.id,
                        year,
                        (c.brand.name if c.brand else ""),
                        (c.model.name if c.model else ""),
                        (c.trim.name if c.trim else ""),
                        (c.mileage_km or ""),
                        (c.client.full_name if c.client else ""),
                        (getattr(c.responsible_user, "full_name", None) or getattr(c.responsible_user, "login", None) or ""),
                        (c.lead_source or ""),
                        priority_label(getattr(c, "priority", None)),
                        (c.status or ""),
                        (c.deal_status or ""),
                        (str(c.price_to_vladivostok) if c.price_to_vladivostok is not None else "")
                    ])
            QMessageBox.information(self, "Экспорт", "Файл сохранён.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка экспорта", str(e))
        finally:
            session.close()

    def export_pdf_selected(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить PDF", "car_report.pdf", "PDF (*.pdf)")
        if not path:
            return
        car = self._current_car()
        if not car:
            QMessageBox.information(self, "Выбор", "Выберите автомобиль.")
            return
        try:
            export_car_pdf(car.id, path)
            QMessageBox.information(self, "PDF", "PDF документ сформирован.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка PDF", str(e))
