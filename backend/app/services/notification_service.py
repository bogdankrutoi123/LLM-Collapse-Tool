from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import logging
import threading
from app.models.database import Notification, AlertThreshold, NotificationStatus, PromptMetric, Prompt, ModelVersion, CollapseEvent, AlertRule, AlertRuleItem
from app.schemas.schemas import NotificationCreate, NotificationUpdate
import aiosmtplib
from email.message import EmailMessage
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class NotificationService:
    """Service for notification management."""
    
    @staticmethod
    def get_notification_by_id(db: Session, notification_id: int) -> Optional[Notification]:
        """Get notification by ID."""
        return db.query(Notification).filter(Notification.id == notification_id).first()
    
    @staticmethod
    def get_notifications(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[NotificationStatus] = None,
        severity: Optional[str] = None
    ) -> List[Notification]:
        """Get list of notifications with filters."""
        query = db.query(Notification)
        
        if status:
            query = query.filter(Notification.status == status)
        if severity:
            query = query.filter(Notification.severity == severity)
        
        return query.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def create_notification(
        db: Session,
        notification: NotificationCreate,
        created_by_id: Optional[int] = None
    ) -> Notification:
        """Create new notification."""
        recipients = notification.recipients
        if not recipients and settings.ALERT_EMAIL_RECIPIENTS:
            recipients = settings.ALERT_EMAIL_RECIPIENTS

        db_notification = Notification(
            model_version_id=notification.model_version_id,
            prompt_id=notification.prompt_id,
            alert_threshold_id=notification.alert_threshold_id,
            title=notification.title,
            message=notification.message,
            severity=notification.severity,
            recipients=recipients,
            created_by_id=created_by_id
        )
        db.add(db_notification)
        db.commit()
        db.refresh(db_notification)

        sent = NotificationService.send_email_notification_sync(db_notification)
        if sent:
            db_notification.email_sent = True
            db_notification.email_sent_at = datetime.utcnow()
            db.commit()
            db.refresh(db_notification)
        return db_notification
    
    @staticmethod
    def update_notification(
        db: Session,
        notification_id: int,
        notification_update: NotificationUpdate,
        acknowledged_by: Optional[int] = None
    ) -> Optional[Notification]:
        """Update notification."""
        db_notification = db.query(Notification).filter(
            Notification.id == notification_id
        ).first()
        
        if not db_notification:
            return None
        
        update_data = notification_update.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(db_notification, field, value)
        
        if notification_update.status and notification_update.status != NotificationStatus.PENDING:
            if not db_notification.acknowledged_at:
                db_notification.acknowledged_at = datetime.utcnow()
                db_notification.acknowledged_by = acknowledged_by
        
        db.commit()
        db.refresh(db_notification)
        return db_notification
    
    @staticmethod
    def delete_notification(db: Session, notification_id: int) -> bool:
        """Delete notification."""
        db_notification = db.query(Notification).filter(
            Notification.id == notification_id
        ).first()
        
        if not db_notification:
            return False
        
        db.delete(db_notification)
        db.commit()
        return True
    
    @staticmethod
    async def send_email_notification(notification: Notification) -> bool:
        """Send email notification."""
        if not notification.recipients or not settings.SMTP_USER:
            return False
        
        try:
            message = EmailMessage()
            message["From"] = settings.SMTP_FROM
            message["To"] = ", ".join(notification.recipients)
            message["Subject"] = f"[{notification.severity.upper()}] {notification.title}"
            
            body = f"""
            LLM Collapse Detector Alert
            
            Severity: {notification.severity.upper()}
            Time: {notification.created_at}
            
            {notification.message}
            
            ---
            This is an automated message from LLM Collapse Detector.
            """
            
            message.set_content(body)
            
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=settings.SMTP_PORT == 465,
                start_tls=settings.SMTP_PORT != 465,
                timeout=15
            )
            
            return True
        except Exception as e:
            logger.warning("Email notification send failed: %s", e)
            return False

    @staticmethod
    def send_email_notification_sync(notification: Notification) -> bool:
        """Sync wrapper for sending email notifications."""
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                result_holder = {"ok": False}

                def _runner() -> None:
                    try:
                        result_holder["ok"] = asyncio.run(
                            NotificationService.send_email_notification(notification)
                        )
                    except Exception:
                        result_holder["ok"] = False

                thread = threading.Thread(target=_runner, daemon=True)
                thread.start()
                thread.join(timeout=20)
                if thread.is_alive():
                    logger.warning("Email send timed out in background thread")
                    return False
                return bool(result_holder["ok"])

            return asyncio.run(NotificationService.send_email_notification(notification))
        except Exception:
            return False


class AlertThresholdService:
    """Service for alert threshold management."""
    
    @staticmethod
    def get_threshold_by_id(db: Session, threshold_id: int) -> Optional[AlertThreshold]:
        """Get alert threshold by ID."""
        return db.query(AlertThreshold).filter(AlertThreshold.id == threshold_id).first()
    
    @staticmethod
    def get_thresholds(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None
    ) -> List[AlertThreshold]:
        """Get list of alert thresholds."""
        query = db.query(AlertThreshold)
        
        if is_active is not None:
            query = query.filter(AlertThreshold.is_active == is_active)
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_active_thresholds(db: Session) -> List[AlertThreshold]:
        """Get all active alert thresholds."""
        return db.query(AlertThreshold).filter(AlertThreshold.is_active == True).all()
    
    @staticmethod
    def create_threshold(db: Session, threshold_data: dict) -> AlertThreshold:
        """Create new alert threshold."""
        db_threshold = AlertThreshold(**threshold_data)
        db.add(db_threshold)
        db.commit()
        db.refresh(db_threshold)
        return db_threshold
    
    @staticmethod
    def update_threshold(
        db: Session,
        threshold_id: int,
        threshold_update: dict
    ) -> Optional[AlertThreshold]:
        """Update alert threshold."""
        db_threshold = db.query(AlertThreshold).filter(
            AlertThreshold.id == threshold_id
        ).first()
        
        if not db_threshold:
            return None
        
        for field, value in threshold_update.items():
            if value is not None:
                setattr(db_threshold, field, value)
        
        db.commit()
        db.refresh(db_threshold)
        return db_threshold
    
    @staticmethod
    def delete_threshold(db: Session, threshold_id: int) -> bool:
        """Delete alert threshold."""
        db_threshold = db.query(AlertThreshold).filter(
            AlertThreshold.id == threshold_id
        ).first()
        
        if not db_threshold:
            return False
        
        db.delete(db_threshold)
        db.commit()
        return True

    @staticmethod
    def evaluate_thresholds_for_metric(
        db: Session,
        prompt_metric: PromptMetric
    ) -> List[Notification]:
        """Evaluate active thresholds for a metric and emit notifications/events."""
        notifications: List[Notification] = []
        if not prompt_metric:
            return notifications

        prompt = db.query(Prompt).filter(Prompt.id == prompt_metric.prompt_id).first()
        if not prompt:
            return notifications

        thresholds = AlertThresholdService.get_active_thresholds(db)
        if not thresholds:
            return notifications

        from app.services.metrics_calculator import MetricsCalculator

        def resolve_metric_value(m: PromptMetric, p: Prompt, metric_name: str) -> Optional[float]:
            if metric_name in {
                "entropy",
                "kl_divergence",
                "js_divergence",
                "wasserstein_distance",
                "ngram_drift",
                "embedding_drift",
            }:
                return getattr(m, metric_name, None)
            if metric_name == "output_length":
                return p.output_length
            if metric_name == "generation_time_ms":
                return p.generation_time_ms
            if metric_name == "cpu_time_ms":
                return p.cpu_time_ms
            if metric_name == "gpu_time_ms":
                return p.gpu_time_ms
            return None

        now = datetime.utcnow()

        def threshold_is_met(threshold: AlertThreshold) -> tuple[bool, Optional[float]]:
            value = resolve_metric_value(prompt_metric, prompt, threshold.metric_name)
            if value is None:
                return False, None

            if not MetricsCalculator.detect_anomaly(value, threshold.threshold_value, threshold.comparison_operator):
                return False, value

            if threshold.persistence_count and threshold.persistence_count > 1:
                recent_metrics = db.query(PromptMetric).join(Prompt).filter(
                    Prompt.model_version_id == prompt.model_version_id,
                    PromptMetric.id <= prompt_metric.id,
                ).order_by(PromptMetric.id.desc()).limit(threshold.persistence_count).all()
                if len(recent_metrics) < threshold.persistence_count:
                    return False, value

                for metric_row in recent_metrics:
                    metric_prompt = db.query(Prompt).filter(Prompt.id == metric_row.prompt_id).first()
                    if not metric_prompt:
                        return False, value
                    metric_value = resolve_metric_value(metric_row, metric_prompt, threshold.metric_name)
                    if metric_value is None or not MetricsCalculator.detect_anomaly(
                        metric_value,
                        threshold.threshold_value,
                        threshold.comparison_operator,
                    ):
                        return False, value

            if threshold.persistence_window_minutes and threshold.persistence_window_minutes > 0:
                window_start = now - timedelta(minutes=threshold.persistence_window_minutes)
                window_metrics = db.query(PromptMetric).join(Prompt).filter(
                    Prompt.model_version_id == prompt.model_version_id,
                    PromptMetric.calculated_at >= window_start,
                ).all()
                if not window_metrics:
                    return False, value

                for metric_row in window_metrics:
                    metric_prompt = db.query(Prompt).filter(Prompt.id == metric_row.prompt_id).first()
                    if not metric_prompt:
                        return False, value
                    metric_value = resolve_metric_value(metric_row, metric_prompt, threshold.metric_name)
                    if metric_value is None or not MetricsCalculator.detect_anomaly(
                        metric_value,
                        threshold.threshold_value,
                        threshold.comparison_operator,
                    ):
                        return False, value

            return True, value

        def create_threshold_notification(triggered_entries: list[dict], source_threshold: AlertThreshold) -> Notification:
            metric_parts = [
                f"{entry['metric_name']}={entry['value']} {entry['operator']} {entry['threshold']}"
                for entry in triggered_entries
            ]
            return NotificationService.create_notification(
                db,
                notification=NotificationCreate(
                    model_version_id=prompt.model_version_id,
                    prompt_id=prompt.id,
                    alert_threshold_id=source_threshold.id,
                    title=f"Threshold exceeded: {source_threshold.name}",
                    message="Triggered metrics: " + "; ".join(metric_parts),
                    severity="warning",
                    recipients=None,
                ),
            )

        grouped_thresholds: dict[str, list[AlertThreshold]] = {}
        ungrouped_thresholds: list[AlertThreshold] = []
        for threshold in thresholds:
            if threshold.group_key:
                grouped_thresholds.setdefault(threshold.group_key, []).append(threshold)
            else:
                ungrouped_thresholds.append(threshold)

        for threshold in ungrouped_thresholds:
            is_met, value = threshold_is_met(threshold)
            if not is_met or value is None:
                continue

            triggered = [{
                "metric_name": threshold.metric_name,
                "threshold": threshold.threshold_value,
                "operator": threshold.comparison_operator,
                "value": value,
                "threshold_id": threshold.id,
            }]

            notifications.append(create_threshold_notification(triggered, threshold))

            db.add(CollapseEvent(
                model_version_id=prompt.model_version_id,
                prompt_id=prompt.id,
                triggered_metrics=triggered,
                baseline_metadata=getattr(prompt_metric, "baseline_metadata", None),
                persistence_metadata={
                    "persistence_count": threshold.persistence_count,
                    "persistence_window_minutes": threshold.persistence_window_minutes,
                    "group_key": None,
                    "require_all_in_group": False,
                },
            ))
            db.commit()

        for group_key, group in grouped_thresholds.items():
            evaluated_entries: list[dict] = []
            for threshold in group:
                is_met, value = threshold_is_met(threshold)
                evaluated_entries.append({
                    "threshold": threshold,
                    "is_met": is_met,
                    "value": value,
                })

            require_all = any(t.require_all_in_group for t in group)
            if require_all:
                group_met = all(entry["is_met"] for entry in evaluated_entries)
                triggered_entries = evaluated_entries if group_met else []
            else:
                triggered_entries = [entry for entry in evaluated_entries if entry["is_met"]]
                group_met = len(triggered_entries) > 0

            if not group_met:
                continue

            triggered = [{
                "metric_name": entry["threshold"].metric_name,
                "threshold": entry["threshold"].threshold_value,
                "operator": entry["threshold"].comparison_operator,
                "value": entry["value"],
                "threshold_id": entry["threshold"].id,
            } for entry in triggered_entries]

            notifications.append(create_threshold_notification(triggered, group[0]))

            db.add(CollapseEvent(
                model_version_id=prompt.model_version_id,
                prompt_id=prompt.id,
                triggered_metrics=triggered,
                baseline_metadata=getattr(prompt_metric, "baseline_metadata", None),
                persistence_metadata={
                    "persistence_count": None,
                    "persistence_window_minutes": None,
                    "group_key": group_key,
                    "require_all_in_group": require_all,
                },
            ))
            db.commit()

        notifications.extend(AlertThresholdService.evaluate_rules_for_metric(db, prompt_metric))
        return notifications

    @staticmethod
    def evaluate_rules_for_metric(
        db: Session,
        prompt_metric: PromptMetric
    ) -> List[Notification]:
        notifications: List[Notification] = []
        if not prompt_metric:
            return notifications

        prompt = db.query(Prompt).filter(Prompt.id == prompt_metric.prompt_id).first()
        if not prompt:
            return notifications

        rules = db.query(AlertRule).filter(AlertRule.is_active == True).all()
        if not rules:
            return notifications

        from app.services.metrics_calculator import MetricsCalculator

        def resolve_metric_value(m: PromptMetric, p: Prompt, metric_name: str) -> Optional[float]:
            if metric_name in {
                "entropy",
                "kl_divergence",
                "js_divergence",
                "wasserstein_distance",
                "ngram_drift",
                "embedding_drift"
            }:
                return getattr(m, metric_name, None)
            if metric_name == "output_length":
                return p.output_length
            if metric_name == "generation_time_ms":
                return p.generation_time_ms
            if metric_name == "cpu_time_ms":
                return p.cpu_time_ms
            if metric_name == "gpu_time_ms":
                return p.gpu_time_ms
            return None

        def item_persistence_ok(item: AlertRuleItem) -> bool:
            if item.persistence_count and item.persistence_count > 1:
                recent_metrics = db.query(PromptMetric).join(Prompt).filter(
                    Prompt.model_version_id == prompt.model_version_id,
                    PromptMetric.id <= prompt_metric.id
                ).order_by(PromptMetric.id.desc()).limit(item.persistence_count).all()

                if len(recent_metrics) < item.persistence_count:
                    return False

                for m in recent_metrics:
                    p = db.query(Prompt).filter(Prompt.id == m.prompt_id).first()
                    if not p:
                        return False
                    v = resolve_metric_value(m, p, item.metric_name)
                    if v is None or not MetricsCalculator.detect_anomaly(v, item.threshold_value, item.comparison_operator):
                        return False

            if item.persistence_window_minutes and item.persistence_window_minutes > 0:
                window_start = datetime.utcnow() - timedelta(minutes=item.persistence_window_minutes)
                window_metrics = db.query(PromptMetric).join(Prompt).filter(
                    Prompt.model_version_id == prompt.model_version_id,
                    PromptMetric.calculated_at >= window_start
                ).all()
                if not window_metrics:
                    return False
                for m in window_metrics:
                    p = db.query(Prompt).filter(Prompt.id == m.prompt_id).first()
                    if not p:
                        return False
                    v = resolve_metric_value(m, p, item.metric_name)
                    if v is None or not MetricsCalculator.detect_anomaly(v, item.threshold_value, item.comparison_operator):
                        return False

            return True

        for rule in rules:
            items = db.query(AlertRuleItem).filter(AlertRuleItem.rule_id == rule.id).all()
            if not items:
                continue

            results = []
            triggered = []
            for item in items:
                value = resolve_metric_value(prompt_metric, prompt, item.metric_name)
                current_met = value is not None and MetricsCalculator.detect_anomaly(
                    value, item.threshold_value, item.comparison_operator
                )
                if current_met and item_persistence_ok(item):
                    results.append(True)
                    triggered.append({
                        "metric_name": item.metric_name,
                        "threshold": item.threshold_value,
                        "operator": item.comparison_operator,
                        "value": value,
                        "rule_id": rule.id,
                        "rule_item_id": item.id
                    })
                else:
                    results.append(False)

            is_met = any(results) if rule.operator == "any" else all(results)
            if not is_met:
                continue

            notification = NotificationService.create_notification(
                db,
                notification=NotificationCreate(
                    model_version_id=prompt.model_version_id,
                    prompt_id=prompt.id,
                    alert_threshold_id=None,
                    title=f"Rule triggered: {rule.name}",
                    message=f"Multi-signal rule '{rule.name}' satisfied.",
                    severity="warning",
                    recipients=None
                )
            )
            notifications.append(notification)

            collapse = CollapseEvent(
                model_version_id=prompt.model_version_id,
                prompt_id=prompt.id,
                triggered_metrics=triggered,
                baseline_metadata=getattr(prompt_metric, "baseline_metadata", None),
                persistence_metadata={
                    "rule_id": rule.id,
                    "operator": rule.operator
                }
            )
            db.add(collapse)
            db.commit()
            db.refresh(collapse)

        return notifications
