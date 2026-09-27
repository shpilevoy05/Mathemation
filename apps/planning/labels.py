"""Human-readable labels for study-plan items."""

from .models import StudyPlanItem


STUDY_PLAN_ITEM_TYPE_LABELS = {
    StudyPlanItem.ItemType.LESSON: "Урок",
    StudyPlanItem.ItemType.PRACTICE: "Практика",
    StudyPlanItem.ItemType.REVIEW: "Отработка",
    StudyPlanItem.ItemType.MOCK: "Пробник",
}
