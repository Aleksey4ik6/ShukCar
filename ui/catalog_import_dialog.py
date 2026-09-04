# ShukCar/ui/catalog_import_dialog.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt

from services.catalog_importer import CatalogImporter


class CatalogImportDialog(QDialog):
    """
    Диалог импорта справочников (марки/модели/комплектации) из CSV.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Импорт справочников из CSV")
        self.resize(560, 220)

        self.ed_path = QLineEdit(self)
        self.ed_path.setPlaceholderText("Выберите CSV-файл (brand,model,trim)")
        self.btn_browse = QPushButton("Выбрать…", self)
        self.btn_browse.setProperty("accent", "secondary")
        self.btn_browse.clicked.connect(self._browse)

        top = QHBoxLayout()
        top.addWidget(self.ed_path, 1)
        top.addWidget(self.btn_browse)

        self.lbl_info = QLabel("Формат CSV: brand,model,trim\nПример: Toyota,Corolla,1.6 Comfort", self)
        self.lbl_info.setObjectName("MutedLabel")

        self.frame_stats = QFrame(self)
        self.frame_stats.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_stats.setProperty("card", True)
        stats_layout = QVBoxLayout(self.frame_stats)
        self.lbl_preview = QLabel("Предпросмотр: —", self)
        stats_layout.addWidget(self.lbl_preview)

        self.btn_dry = QPushButton("Проверить файл", self)
        self.btn_import = QPushButton("Импортировать", self)
        self.btn_dry.setProperty("accent", "secondary")
        self.btn_import.setEnabled(False)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.btn_dry)
        buttons.addWidget(self.btn_import)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.lbl_info)
        root.addWidget(self.frame_stats)
        root.addLayout(buttons)

        self.btn_dry.clicked.connect(self._do_dry_run)
        self.btn_import.clicked.connect(self._do_import)

        self._last_csv: Optional[Path] = None
        self._last_stats = None

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать CSV-файл", "", "CSV (*.csv)")
        if not path:
            return
        self.ed_path.setText(path)
        self._last_csv = Path(path)
        self.lbl_preview.setText("Предпросмотр: —")
        self.btn_import.setEnabled(False)

    def _do_dry_run(self):
        if not self._validate_path():
            return
        try:
            imp = CatalogImporter()
            stats = imp.dry_run(self._last_csv)
            self._last_stats = stats
            self.lbl_preview.setText(
                f"Строк всего: {stats.rows_total}\n"
                f"Создаст брендов: {stats.brands_created} · моделей: {stats.models_created} · комплектаций: {stats.trims_created}\n"
                f"Пропущено пустых строк: {stats.rows_skipped}"
            )
            self.btn_import.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Проверка файла", f"Ошибка: {e}")
            self.btn_import.setEnabled(False)

    def _do_import(self):
        if not self._validate_path():
            return
        try:
            imp = CatalogImporter()
            stats = imp.import_csv(self._last_csv)
            QMessageBox.information(
                self, "Готово",
                f"Импорт завершён.\n"
                f"Создано брендов: {stats.brands_created}\n"
                f"Создано моделей: {stats.models_created}\n"
                f"Создано комплектаций: {stats.trims_created}"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Импорт", f"Ошибка импорта: {e}")

    def _validate_path(self) -> bool:
        path = self.ed_path.text().strip()
        if not path:
            QMessageBox.information(self, "Импорт", "Выберите CSV-файл.")
            return False
        p = Path(path)
        if not p.exists():
            QMessageBox.warning(self, "Импорт", f"Файл не найден:\n{p}")
            return False
        self._last_csv = p
        return True
