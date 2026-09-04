# ShukCar/ui/dashboard_view.py
from __future__ import annotations

import csv
import math
import datetime as dt
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Optional, Tuple, List

from PyQt6 import QtWidgets, QtGui
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QDateEdit, QLineEdit, QComboBox,
    QPushButton, QFileDialog, QLabel, QFrame, QMessageBox, QGridLayout, QListWidget
)
from sqlalchemy import or_, func, cast, String
from sqlalchemy.orm import joinedload

# Пробуем QtCharts. Если нет — показываем плейсхолдеры без падений.
try:
    from PyQt6.QtCharts import (
        QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis,
        QPieSeries
    )
    HAS_CHARTS = True
except Exception:
    QChart = QChartView = QBarSeries = QBarSet = QBarCategoryAxis = QValueAxis = QPieSeries = None
    HAS_CHARTS = False

from db import SessionLocal
from models import Car, Brand, Model, DealStage, CarTask, Client, User
from services.crm import priority_label, priority_sort_key
from theme import theme_controller, theme_definition


PKG_ROOT = Path(__file__).resolve().parents[1]


# ---------- ВСПОМОГАТЕЛЬНЫЕ ВИДЖЕТЫ ----------
class KpiCard(QFrame):
    def __init__(self, title: str, value: str = "—", sub: str | None = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("KpiCard")
        self.setProperty("card", True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        self.lbl_title = QLabel(title); self.lbl_title.setProperty("role", "title")
        self.lbl_value = QLabel(value); self.lbl_value.setProperty("role", "value")
        self.lbl_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.lbl_title)
        lay.addWidget(self.lbl_value)
        self.lbl_sub = None
        if sub:
            self.lbl_sub = QLabel(sub); self.lbl_sub.setProperty("role", "sub")
            lay.addWidget(self.lbl_sub)

    def set_value(self, text: str):
        self.lbl_value.setText(text)

    def set_sub(self, text: str | None):
        if text is None:
            if self.lbl_sub:
                self.lbl_sub.hide()
            return
        if not self.lbl_sub:
            self.lbl_sub = QLabel(text); self.lbl_sub.setProperty("role", "sub")
            self.layout().addWidget(self.lbl_sub)
        else:
            self.lbl_sub.setText(text)
            self.lbl_sub.show()


class PlaceholderChart(QFrame):
    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("PlaceholderChart")
        self.setProperty("card", True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 18, 18, 18)
        lab = QLabel(text + "\n\nУстановите пакет 'PyQt6-Charts' для отображения графиков.")
        lab.setObjectName("SearchStatus")
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setWordWrap(True)
        v.addWidget(lab)


# ---------- ОСНОВНОЙ ВИД ----------
class DashboardView(QWidget):
    """
    Расширённая «Аналитика»:

    • Фильтры: период по дате создания, поиск (марка/модель/статусы), стадия сделки, горизонт месяцев.
    • KPI: Всего авто, В работе, Сумма (цена клиенту), Оценка маржи.
    • Графики:
        - Столбцы: Кол-во авто по стадиям сделки
        - Столбцы: Добавления по месяцам   ← безопасно, без QLineSeries
        - Пирог: Распределение по брендам
        - Столбцы: Топ-10 моделей
    • Действия: Применить, Сбросить, Экспорт CSV, Открыть в «Автомобили».
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DashboardView")

        # ===== Шапка/фильтры =====
        filters = QFormLayout()
        filters.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        filters.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.dt_from = QDateEdit(); self.dt_from.setCalendarPopup(True); self.dt_from.setDisplayFormat("dd.MM.yyyy")
        self.dt_to   = QDateEdit(); self.dt_to.setCalendarPopup(True);   self.dt_to.setDisplayFormat("dd.MM.yyyy")
        today = QDate.currentDate()
        self.dt_to.setDate(today)
        self.dt_from.setDate(today.addDays(-180))

        self.ed_search = QLineEdit(); self.ed_search.setPlaceholderText("Марка / модель / статус / свободный текст")
        self.cb_stage  = QComboBox()
        self.cb_months = QComboBox()
        for m in (6, 12, 18, 24, 36):
            self.cb_months.addItem(f"Последние {m} мес.", m)
        self.cb_months.setCurrentIndex(1)

        filters.addRow("С:", self.dt_from)
        filters.addRow("По:", self.dt_to)
        filters.addRow("Поиск:", self.ed_search)
        filters.addRow("Стадия:", self.cb_stage)
        filters.addRow("Горизонт:", self.cb_months)

        btns = QHBoxLayout()
        self.btn_apply = QPushButton("Применить")
        self.btn_reset = QPushButton("Сбросить")
        self.btn_export = QPushButton("Экспорт CSV")
        self.btn_open_cars = QPushButton("Открыть в «Автомобили»")
        for b in (self.btn_apply, self.btn_reset, self.btn_export, self.btn_open_cars):
            btns.addWidget(b)
        btns.addStretch(1)

        top = QVBoxLayout()
        top.addLayout(filters)
        top.addLayout(btns)

        # ===== KPI =====
        self.grid_kpi = QGridLayout()
        self.grid_kpi.setHorizontalSpacing(12)
        self.grid_kpi.setVerticalSpacing(12)

        self.kpi_total = KpiCard("Всего авто (по фильтру)")
        self.kpi_active = KpiCard("В работе (есть стадия)")
        self.kpi_pipeline = KpiCard("Сумма по цене клиенту", "—", "Без конвертации валют")
        self.kpi_margin = KpiCard("Оценка валовой маржи", "—", "Цена клиенту − закупка − прочее")
        self.kpi_overdue_tasks = KpiCard("Просроченные действия")
        self.kpi_due_week = KpiCard("Действия на 7 дней")
        self.grid_kpi.addWidget(self.kpi_total,   0, 0)
        self.grid_kpi.addWidget(self.kpi_active,  0, 1)
        self.grid_kpi.addWidget(self.kpi_pipeline,0, 2)
        self.grid_kpi.addWidget(self.kpi_margin,  0, 3)
        self.grid_kpi.addWidget(self.kpi_overdue_tasks, 1, 0)
        self.grid_kpi.addWidget(self.kpi_due_week, 1, 1)

        # ===== Графики =====
        charts = QGridLayout()
        charts.setHorizontalSpacing(12)
        charts.setVerticalSpacing(12)

        self.chart_stage = self._make_placeholder_or_chart("Распределение по стадиям сделки")
        charts.addWidget(self.chart_stage, 0, 0)

        self.chart_months = self._make_placeholder_or_chart("Добавления авто по месяцам")
        charts.addWidget(self.chart_months, 0, 1)

        self.chart_brands = self._make_placeholder_or_chart("Распределение по брендам")
        charts.addWidget(self.chart_brands, 1, 0)

        self.chart_models = self._make_placeholder_or_chart("Топ-10 моделей (шт.)")
        charts.addWidget(self.chart_models, 1, 1)

        self.tasks_card = QFrame(self)
        self.tasks_card.setObjectName("DashboardTasks")
        self.tasks_card.setProperty("card", True)
        tasks_layout = QVBoxLayout(self.tasks_card)
        tasks_layout.setContentsMargins(12, 12, 12, 12)
        tasks_layout.setSpacing(8)
        tasks_title = QLabel("Ближайшие действия по сделкам")
        tasks_title.setObjectName("SectionTitle")
        self.tasks_list = QListWidget()
        self.tasks_list.setSpacing(6)
        tasks_layout.addWidget(tasks_title)
        tasks_layout.addWidget(self.tasks_list)

        # ===== Корневой лэйаут =====
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)
        root.addLayout(top)
        root.addLayout(self.grid_kpi)
        root.addLayout(charts)
        root.addWidget(self.tasks_card)

        # Данные
        self._stages_index: dict[int, str] = {}
        self._load_stages()
        self._connect_signals()
        theme_controller.theme_changed.connect(self._on_theme_changed)
        self.refresh()

    # ---------- helpers ----------
    def _connect_signals(self):
        self.btn_apply.clicked.connect(self.refresh)
        self.btn_reset.clicked.connect(self._reset_filters)
        self.btn_export.clicked.connect(self._export_csv)
        self.btn_open_cars.clicked.connect(self._open_in_cars)

    def _reset_filters(self):
        today = QDate.currentDate()
        self.dt_to.setDate(today)
        self.dt_from.setDate(today.addDays(-180))
        self.ed_search.clear()
        self.cb_stage.setCurrentIndex(0)
        self.cb_months.setCurrentIndex(1)
        self.refresh()

    def _make_placeholder_or_chart(self, title: str) -> QWidget:
        if not HAS_CHARTS:
            return PlaceholderChart(title, self)
        ch = QChart(); ch.setTitle(title)
        view = QChartView(ch)
        view.setObjectName("ChartCard")
        view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        return view

    def _on_theme_changed(self, _theme_name: str):
        self.refresh()

    def _load_stages(self):
        self.cb_stage.clear()
        self.cb_stage.addItem("Все стадии", None)
        s = SessionLocal()
        try:
            rows = s.query(DealStage).filter(DealStage.is_active == True).order_by(DealStage.sort_order.asc()).all()
            for r in rows:
                self.cb_stage.addItem(r.name, r.id)
                self._stages_index[r.id] = r.name
        finally:
            s.close()

    # ---------- загрузка/агрегация ----------
    def _read_filters(self) -> Tuple[Optional[dt.date], Optional[dt.date], Optional[int], str, int]:
        dfrom = self.dt_from.date()
        dto   = self.dt_to.date()
        from_date = dt.date(dfrom.year(), dfrom.month(), dfrom.day()) if dfrom.isValid() else None
        to_date   = dt.date(dto.year(),   dto.month(),   dto.day())   if dto.isValid()   else None
        stage_id = self.cb_stage.currentData()
        q = self.ed_search.text().strip()
        months = int(self.cb_months.currentData() or 12)
        return from_date, to_date, stage_id, q, months

    def _query_cars(self) -> List[Car]:
        from_date, to_date, stage_id, q, _months = self._read_filters()
        s = SessionLocal()
        try:
            qset = (
                s.query(Car)
                .outerjoin(Brand, Brand.id == Car.brand_id)
                .outerjoin(Model, Model.id == Car.model_id)
                .outerjoin(Client, Client.id == Car.client_id)
                .outerjoin(User, User.id == Car.responsible_user_id)
                .options(
                    joinedload(Car.brand),
                    joinedload(Car.model),
                    joinedload(Car.client),
                    joinedload(Car.responsible_user),
                    joinedload(Car.tasks),
                )
            )

            # Период по created_at
            if from_date:
                qset = qset.filter(Car.created_at >= dt.datetime.combine(from_date, dt.time.min))
            if to_date:
                qset = qset.filter(Car.created_at <= dt.datetime.combine(to_date, dt.time.max))

            # Стадия
            if stage_id:
                qset = qset.filter(Car.deal_stage_id == stage_id)

            # Поиск
            if q:
                qlow = f"%{q.lower()}%"
                qset = qset.filter(or_(
                    func.lower(func.coalesce(Brand.name, "")).like(qlow),
                    func.lower(func.coalesce(Model.name, "")).like(qlow),
                    func.lower(func.coalesce(Client.full_name, "")).like(qlow),
                    func.lower(func.coalesce(Client.phone, "")).like(qlow),
                    func.lower(func.coalesce(User.full_name, "")).like(qlow),
                    func.lower(func.coalesce(User.login, "")).like(qlow),
                    func.lower(func.coalesce(Car.vin, "")).like(qlow),
                    func.lower(func.coalesce(Car.lead_source, "")).like(qlow),
                    func.lower(func.coalesce(Car.priority, "")).like(qlow),
                    func.lower(func.coalesce(Car.status, "")).like(qlow),
                    func.lower(func.coalesce(Car.deal_status, "")).like(qlow),
                    cast(Car.id, String).like(f"%{q}%")
                ))

            return qset.order_by(Car.id.desc()).all()
        finally:
            s.close()

    # ---------- обновление UI ----------
    def refresh(self):
        cars = self._query_cars()
        self._update_kpis(cars)
        self._update_charts(cars)
        self._update_tasks(cars)

    # KPI
    def _update_kpis(self, cars: List[Car]):
        total = len(cars)
        in_flow = sum(1 for c in cars if c.deal_stage_id is not None)

        def to_float(x: Optional[Decimal | float]) -> float:
            if x is None:
                return 0.0
            try:
                return float(x)
            except Exception:
                return 0.0

        sum_customer = sum(to_float(c.price_customer) for c in cars if c.price_customer is not None)
        sum_margin = 0.0
        today = dt.date.today()
        week_end = today + dt.timedelta(days=7)
        open_tasks = []
        for c in cars:
            pc = to_float(c.price_customer)
            pp = to_float(c.purchase_price)
            oc = to_float(c.other_costs)
            if pc:
                sum_margin += max(pc - pp - oc, 0.0)
            for task in getattr(c, "tasks", []):
                if not task.is_done:
                    open_tasks.append(task)

        overdue_tasks = sum(1 for task in open_tasks if task.due_date and task.due_date < today)
        due_week = sum(1 for task in open_tasks if task.due_date and today <= task.due_date <= week_end)

        self.kpi_total.set_value(f"{total:,}".replace(",", " "))
        self.kpi_active.set_value(f"{in_flow:,}".replace(",", " "))
        self.kpi_pipeline.set_value(self._fmt_money(sum_customer))
        self.kpi_margin.set_value(self._fmt_money(sum_margin))
        self.kpi_overdue_tasks.set_value(f"{overdue_tasks:,}".replace(",", " "))
        self.kpi_due_week.set_value(f"{due_week:,}".replace(",", " "))

    def _fmt_money(self, x: float) -> str:
        if x >= 1_000_000_000:
            return f"{x/1_000_000_000:.2f} млрд"
        if x >= 1_000_000:
            return f"{x/1_000_000:.2f} млн"
        if x >= 1000:
            return f"{x/1000:.1f} тыс"
        return f"{x:.0f}"

    # Графики
    def _update_charts(self, cars: List[Car]):
        if not HAS_CHARTS:
            return

        # 1) По стадиям (bar)
        by_stage = Counter(self._stages_index.get(c.deal_stage_id, "Без стадии") for c in cars)
        self._set_bar_chart(self.chart_stage, "Кол-во", list(by_stage.keys()), [float(v) for v in by_stage.values()])

        # 2) По месяцам (BAR — безопасно)
        _from, to, _sid, _q, months = self._read_filters()
        months_axis = self._build_month_axis(months, (to or dt.date.today()))
        by_month = Counter(self._month_key(c.created_at or dt.datetime.utcnow()) for c in cars)
        month_vals = [float(by_month.get(k, 0)) for k in months_axis]
        self._set_bar_chart(self.chart_months, "Добавлений", months_axis, month_vals)

        # 3) Пирог по брендам
        by_brand = Counter((c.brand.name if c.brand else "—") for c in cars)
        self._set_pie_chart(self.chart_brands, by_brand)

        # 4) Топ моделей (bar)
        by_model = Counter((
            ((c.brand.name + " " + c.model.name) if (c.brand and c.model) else (c.model.name if c.model else "—"))
        ) for c in cars)
        items = by_model.most_common(10)
        cats = [name for name, _ in items]
        vals = [float(v) for _, v in items]
        self._set_bar_chart(self.chart_models, "Кол-во", cats, vals)

    def _update_tasks(self, cars: List[Car]):
        self.tasks_list.clear()
        rows = []
        today = dt.date.today()
        for car in cars:
            for task in getattr(car, "tasks", []):
                if task.is_done:
                    continue
                rows.append((task, car))

        rows.sort(
            key=lambda item: (
                0 if item[0].due_date and item[0].due_date < today else 1,
                item[0].due_date or dt.date.max,
                priority_sort_key(item[0].priority),
                -int(item[1].id or 0),
            )
        )

        for task, car in rows[:10]:
            due = task.due_date.strftime("%d.%m.%Y") if task.due_date else "без срока"
            title = task.title
            car_label = f"{getattr(car.brand, 'name', '')} {getattr(car.model, 'name', '')}".strip() or f"Авто #{car.id}"
            manager = getattr(getattr(car, "responsible_user", None), "full_name", None) or getattr(getattr(car, "responsible_user", None), "login", None) or "без менеджера"
            text = f"{due} · {priority_label(task.priority)}\n{title}\n{car_label} · {manager}"
            self.tasks_list.addItem(text)

        if self.tasks_list.count() == 0:
            self.tasks_list.addItem("Нет активных задач по выбранным сделкам.")

    # ---- chart builders (безопасные) ----
    def _reset_chart(self, view: QChartView):
        ch: QChart = view.chart()
        ch.removeAllSeries()
        # аккуратно удаляем все оси (иначе бывает краш при повторном назначении)
        for ax in list(ch.axes(Qt.Orientation.Horizontal)) + list(ch.axes(Qt.Orientation.Vertical)):
            ch.removeAxis(ax)

    def _set_bar_chart(self, view: QChartView, label: str, categories: List[str], values: List[float]):
        self._reset_chart(view)
        ch: QChart = view.chart()
        palette = theme_definition()
        colors = palette.colors
        if not categories:
            ch.setTitle(ch.title().split(" (", 1)[0] + " (нет данных)")
            self._style_chart(ch)
            return
        series = QBarSeries()
        bar = QBarSet(label)
        accent = QtGui.QColor(palette.chart_colors[0])
        bar.setColor(accent)
        bar.setBorderColor(accent)
        for v in values:
            bar.append(v)
        series.append(bar)
        ch.addSeries(series)

        axisX = QBarCategoryAxis(); axisX.append(categories)
        axisY = QValueAxis(); axisY.setLabelFormat("%.0f"); axisY.applyNiceNumbers()

        ch.addAxis(axisX, Qt.AlignmentFlag.AlignBottom)
        ch.addAxis(axisY, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axisX)
        series.attachAxis(axisY)
        ch.legend().setVisible(False)
        self._style_axis(axisX, show_grid=False)
        self._style_axis(axisY, show_grid=True)
        self._style_chart(ch)

    def _set_pie_chart(self, view: QChartView, data: Counter):
        self._reset_chart(view)
        ch: QChart = view.chart()
        palette = theme_definition()
        total = sum(data.values())
        if total == 0:
            ch.setTitle("Распределение по брендам (нет данных)")
            self._style_chart(ch)
            return
        items = data.most_common(8)
        rest = total - sum(v for _, v in items)
        series = QPieSeries()
        for idx, (name, v) in enumerate(items):
            slice_ = series.append(f"{name} ({v})", float(v))
            slice_.setColor(QtGui.QColor(palette.chart_colors[idx % len(palette.chart_colors)]))
            slice_.setBorderColor(QtGui.QColor(palette.colors["surface"]))
        if rest > 0:
            slice_ = series.append(f"Другие ({rest})", float(rest))
            slice_.setColor(QtGui.QColor(palette.colors["surface_hover"]))
            slice_.setBorderColor(QtGui.QColor(palette.colors["surface"]))
        ch.addSeries(series)
        ch.legend().setVisible(True)
        self._style_chart(ch)

    def _style_axis(self, axis, *, show_grid: bool):
        colors = theme_definition().colors
        line_pen = QtGui.QPen(QtGui.QColor(colors["border"]))
        line_pen.setWidth(1)
        axis.setLinePen(line_pen)
        axis.setLabelsColor(QtGui.QColor(colors["muted"]))
        if hasattr(axis, "setGridLineVisible"):
            axis.setGridLineVisible(show_grid)
        if show_grid and hasattr(axis, "setGridLinePen"):
            grid_pen = QtGui.QPen(QtGui.QColor(colors["border_soft"]))
            grid_pen.setWidth(1)
            axis.setGridLinePen(grid_pen)

    def _style_chart(self, chart: QChart):
        colors = theme_definition().colors
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.setTitleBrush(QtGui.QColor(colors["text_strong"]))
        if chart.legend():
            chart.legend().setLabelColor(QtGui.QColor(colors["muted"]))

    def _build_month_axis(self, months: int, end_date: dt.date) -> List[str]:
        out = []
        y, m = end_date.year, end_date.month
        for _ in range(months):
            out.append(f"{y:04d}-{m:02d}")
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        out.reverse()
        return out

    def _month_key(self, created_at: dt.datetime) -> str:
        d = created_at.date()
        return f"{d.year:04d}-{d.month:02d}"

    # ---------- действия ----------
    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить CSV", "analytics_export.csv", "CSV (*.csv)")
        if not path:
            return
        cars = self._query_cars()
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=';')
                w.writerow([
                    "ID","Создано","Марка","Модель","Стадия","Статус","Статус сделки",
                    "Цена клиенту","Цена закупки","Прочие затраты","Маржа (грубо)"
                ])
                for c in cars:
                    created = (c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "")
                    stage = self._stages_index.get(c.deal_stage_id, "")
                    brand = c.brand.name if c.brand else ""
                    model = c.model.name if c.model else ""
                    price_cust = self._to_float(c.price_customer)
                    price_pur  = self._to_float(c.purchase_price)
                    other      = self._to_float(c.other_costs)
                    margin = max(price_cust - price_pur - other, 0.0) if price_cust else 0.0
                    w.writerow([
                        c.id, created, brand, model, stage, (c.status or ""), (c.deal_status or ""),
                        self._fmt_num(price_cust), self._fmt_num(price_pur), self._fmt_num(other), self._fmt_num(margin)
                    ])
            QMessageBox.information(self, "Экспорт", "CSV сохранён.")
        except Exception as e:
            QMessageBox.critical(self, "Экспорт", f"Не удалось сохранить: {e}")

    def _open_in_cars(self):
        parent = self.parent()
        try:
            if hasattr(parent, "show_cars"):
                parent.show_cars()
                cv = getattr(parent, "_cars_view", None)
                if cv and hasattr(cv, "ed_search") and hasattr(cv, "apply_search"):
                    cv.ed_search.setText(self.ed_search.text().strip())
                    cv.apply_search()
        except Exception:
            pass

    # ---------- утиль ----------
    def _to_float(self, x) -> float:
        if x is None:
            return 0.0
        try:
            return float(x)
        except Exception:
            return 0.0

    def _fmt_num(self, x: float | int) -> str:
        try:
            if x is None:
                return ""
            if isinstance(x, float) and (math.isinf(x) or math.isnan(x)):
                return ""
            s = f"{x:.2f}" if isinstance(x, float) else str(x)
            return s.replace(".", ",")
        except Exception:
            return ""
