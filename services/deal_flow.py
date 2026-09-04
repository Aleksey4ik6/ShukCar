# ShukCar/services/deal_flow.py
from sqlalchemy.orm import Session
from models import Car, DealStage, DealStageHistory

def move_car_to_stage(s: Session, car: Car, stage: DealStage, user_id: int | None = None, note: str | None = None):
    """
    Перевод авто на этап сделки с записью истории.
    """
    if not car or not stage:
        return
    if car.deal_stage_id == stage.id:
        return
    car.deal_stage_id = stage.id
    hist = DealStageHistory(
        car_id=car.id,
        stage_id=stage.id,
        user_id=user_id,
        note=note or ""
    )
    s.add(hist)
    s.flush()
