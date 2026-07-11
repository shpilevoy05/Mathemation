from django import forms

from apps.practice.models import MistakeBacklogItem

from .models import ExpertReviewRequest


class FinishExpertReviewForm(forms.ModelForm):
    error_tags = forms.MultipleChoiceField(
        label="Типы ошибок",
        choices=MistakeBacklogItem.ErrorType.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    needs_resubmission = forms.BooleanField(
        label="Нужна повторная отправка", required=False
    )
    finish_review = forms.BooleanField(
        label="Завершить проверку через полный пайплайн", required=False
    )

    class Meta:
        model = ExpertReviewRequest
        fields = [
            "student", "assignment", "attempt", "mock_result", "solution_file",
            "sla_hours", "score_by_criteria", "comment", "error_tags", "related_nodes",
        ]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("finish_review"):
            scores = cleaned.get("score_by_criteria") or {}
            if not scores:
                self.add_error("score_by_criteria", "Укажите баллы по критериям ФИПИ.")
            elif any(not isinstance(score, int) or score < 0 for score in scores.values()):
                self.add_error("score_by_criteria", "Баллы должны быть целыми и неотрицательными.")
            elif self.instance.assignment_id and sum(scores.values()) > self.instance.assignment.max_score:
                self.add_error("score_by_criteria", "Сумма превышает максимальный балл задачи.")
        return cleaned
