from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.database import AlertRule, AlertRuleItem
from app.schemas.schemas import AlertRuleCreate, AlertRuleUpdate


class AlertRuleService:
    """Service for alert rule CRUD."""

    @staticmethod
    def get_rule_by_id(db: Session, rule_id: int) -> Optional[AlertRule]:
        return db.query(AlertRule).filter(AlertRule.id == rule_id).first()

    @staticmethod
    def get_rules(db: Session, skip: int = 0, limit: int = 100, is_active: Optional[bool] = None) -> List[AlertRule]:
        query = db.query(AlertRule)
        if is_active is not None:
            query = query.filter(AlertRule.is_active == is_active)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def create_rule(db: Session, rule: AlertRuleCreate) -> AlertRule:
        db_rule = AlertRule(
            name=rule.name,
            operator=rule.operator,
            description=rule.description,
            is_active=rule.is_active
        )
        db.add(db_rule)
        db.commit()
        db.refresh(db_rule)

        for item in rule.items:
            db_item = AlertRuleItem(
                rule_id=db_rule.id,
                metric_name=item.metric_name,
                threshold_value=item.threshold_value,
                comparison_operator=item.comparison_operator,
                persistence_count=item.persistence_count,
                persistence_window_minutes=item.persistence_window_minutes
            )
            db.add(db_item)
        db.commit()
        db.refresh(db_rule)
        return db_rule

    @staticmethod
    def update_rule(db: Session, rule_id: int, rule_update: AlertRuleUpdate) -> Optional[AlertRule]:
        db_rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
        if not db_rule:
            return None

        update_data = rule_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_rule, field, value)

        db.commit()
        db.refresh(db_rule)
        return db_rule

    @staticmethod
    def delete_rule(db: Session, rule_id: int) -> bool:
        db_rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
        if not db_rule:
            return False
        db.delete(db_rule)
        db.commit()
        return True

    @staticmethod
    def replace_rule_items(db: Session, rule_id: int, items: list[dict]) -> Optional[AlertRule]:
        db_rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
        if not db_rule:
            return None
        db.query(AlertRuleItem).filter(AlertRuleItem.rule_id == rule_id).delete()
        for item in items:
            db.add(AlertRuleItem(rule_id=rule_id, **item))
        db.commit()
        db.refresh(db_rule)
        return db_rule
