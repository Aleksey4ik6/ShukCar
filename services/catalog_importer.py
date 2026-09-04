# ShukCar/services/catalog_importer.py
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterable

from sqlalchemy.orm import Session

from db import SessionLocal
from models import Brand, Model, Trim


@dataclass
class ImportStats:
    brands_created: int = 0
    models_created: int = 0
    trims_created: int = 0
    rows_total: int = 0
    rows_skipped: int = 0


class CatalogImporter:
    """
    Импорт справочников из CSV вида:
      brand,model,trim
      Toyota,Corolla,1.6 Comfort
      Toyota,Corolla,1.8 Style
      BMW,3 Series,320i
    """

    def __init__(self, session: Optional[Session] = None):
        self._own_session = False
        if session is None:
            self.session = SessionLocal()
            self._own_session = True
        else:
            self.session = session

    def close(self):
        if self._own_session and self.session:
            self.session.close()

    def _ensure_brand(self, name: str) -> Optional[Brand]:
        name = (name or "").strip()
        if not name:
            return None
        s = self.session
        row = s.query(Brand).filter(Brand.name == name).first()
        if row:
            return row
        row = Brand(name=name)
        s.add(row)
        s.flush()
        return row

    def _ensure_model(self, brand: Brand, name: str) -> Optional[Model]:
        name = (name or "").strip()
        if not name or not brand:
            return None
        s = self.session
        row = s.query(Model).filter(Model.brand_id == brand.id, Model.name == name).first()
        if row:
            return row
        row = Model(brand_id=brand.id, name=name)
        s.add(row)
        s.flush()
        return row

    def _ensure_trim(self, model: Model, name: str) -> Optional[Trim]:
        name = (name or "").strip()
        if not name or not model:
            return None
        s = self.session
        row = s.query(Trim).filter(Trim.model_id == model.id, Trim.name == name).first()
        if row:
            return row
        row = Trim(model_id=model.id, name=name)
        s.add(row)
        s.flush()
        return row

    def _iter_csv(self, path: Path) -> Iterable[tuple[str, str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            # нормализуем имена колонок
            field_map = {k.lower().strip(): k for k in reader.fieldnames or []}
            req = ["brand", "model", "trim"]
            for r in req:
                if r not in field_map:
                    # допускаем отсутствие trim (создадим б/к)
                    if r == "trim":
                        continue
            for row in reader:
                brand = row.get(field_map.get("brand", ""), "") if field_map.get("brand") else ""
                model = row.get(field_map.get("model", ""), "") if field_map.get("model") else ""
                trim  = row.get(field_map.get("trim", ""), "") if field_map.get("trim") else ""
                yield (brand or "", model or "", trim or "")

    def dry_run(self, csv_path: Path) -> ImportStats:
        """
        Подсчёт сколько будет создано, без записи.
        """
        s = self.session
        stats = ImportStats()

        for brand_name, model_name, trim_name in self._iter_csv(csv_path):
            stats.rows_total += 1
            bn = (brand_name or "").strip()
            mn = (model_name or "").strip()
            tn = (trim_name or "").strip()

            if not bn and not mn and not tn:
                stats.rows_skipped += 1
                continue

            brand = s.query(Brand).filter(Brand.name == bn).first() if bn else None
            if not brand and bn:
                stats.brands_created += 1

            model = None
            if bn and mn:
                if brand:
                    model = s.query(Model).filter(Model.brand_id == brand.id, Model.name == mn).first()
                if not model:
                    # если бренда нет в БД, всё равно считаем, что модель создастся после бренда
                    stats.models_created += 1

            if bn and mn and tn:
                # посмотрим, есть ли уже такая комплектация
                if brand and model:
                    trim = s.query(Trim).filter(Trim.model_id == model.id, Trim.name == tn).first()
                    if not trim:
                        stats.trims_created += 1
                else:
                    # модели пока нет, но будет создана — засчитаем и trim
                    stats.trims_created += 1

        return stats

    def import_csv(self, csv_path: Path) -> ImportStats:
        """
        Импорт с записью в БД.
        """
        stats = ImportStats()
        try:
            for brand_name, model_name, trim_name in self._iter_csv(csv_path):
                stats.rows_total += 1
                bn = (brand_name or "").strip()
                mn = (model_name or "").strip()
                tn = (trim_name or "").strip()

                if not (bn or mn or tn):
                    stats.rows_skipped += 1
                    continue

                brand = self._ensure_brand(bn) if bn else None
                if brand and brand.id is not None:
                    # если только что создали — посчитаем
                    if self.session.is_modified(brand) is False:
                        # SQLAlchemy может не считать new объект "modified", поэтому считаем иначе:
                        pass
                # точный подсчёт: если бренда не было — _ensure_brand создала; проверим по факту наличия в БД до
                # упростим: повторно проверим существование
                if bn:
                    was = self.session.query(Brand).filter(Brand.name == bn).count()
                    if was == 1:
                        # мог быть создан ранее в этой итерации — не увеличиваем лишний раз
                        pass

                model = self._ensure_model(brand, mn) if (brand and mn) else None

                if tn and model:
                    existed_trim = self.session.query(Trim).filter(Trim.model_id == model.id, Trim.name == tn).first()
                    if not existed_trim:
                        self._ensure_trim(model, tn)
                        stats.trims_created += 1

                # статистика брендов/моделей считаем честно вне коротких путей
                # бренды
                if bn:
                    # если ты хочешь строгую точность — можно было сначала собрать сеты существующих
                    pass
                # модели
                if bn and mn:
                    pass

            # Для честной статистики (сколько реально новых брендов/моделей) —
            # пересчитаем по уникальным значениям из файла и текущему состоянию БД:
            file_brands = set()
            file_models = set()
            for brand_name, model_name, trim_name in self._iter_csv(csv_path):
                if brand_name.strip():
                    file_brands.add(brand_name.strip())
                if brand_name.strip() and model_name.strip():
                    file_models.add((brand_name.strip(), model_name.strip()))

            # посчитаем сколько из них уже было в БД до импорта
            existing_brands = {b.name for b in self.session.query(Brand).all()}
            stats.brands_created = len([b for b in file_brands if b not in existing_brands])

            # для моделей чуть сложнее: сверим по парам (brand_id, model_name)
            brand_map = {b.name: b.id for b in self.session.query(Brand).all()}
            existing_models_pairs = set()
            for m in self.session.query(Model).all():
                # найдём имя бренда по id
                bn = None
                for name, bid in brand_map.items():
                    if bid == m.brand_id:
                        bn = name
                        break
                if bn:
                    existing_models_pairs.add((bn, m.name))
            stats.models_created = len([p for p in file_models if p not in existing_models_pairs])

            self.session.commit()
            return stats
        except Exception:
            self.session.rollback()
            raise
        finally:
            self.close()
