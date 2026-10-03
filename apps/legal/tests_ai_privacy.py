from django.test import TestCase

from apps.accounts.models import User
from apps.ai_mentor.models import AiOutboundRequest

from .models import DataDeletionRequest
from .services import anonymize_user, export_user_data
from .tests import make_student


class AiOutboundLegalTests(TestCase):
    def setUp(self):
        self.student = make_student("outbound-legal")
        self.audit = AiOutboundRequest.objects.create(
            student=self.student,
            pseudonym="stu_1234567890abcdef12345678",
            purpose=AiOutboundRequest.Purpose.HINT,
            provider="openai",
            model="deepseek-chat",
            redaction_counts={"email": 1},
            prompt_tokens=100,
            completion_tokens=20,
        )

    def test_export_contains_metadata_without_prompt_text(self):
        data = export_user_data(self.student.user)

        self.assertEqual(len(data["ai_outbound_requests"]), 1)
        row = data["ai_outbound_requests"][0]
        self.assertEqual(row["request_id"], self.audit.request_id)
        self.assertNotIn("text", row)
        self.assertNotIn("prompt", row)

    def test_anonymization_keeps_and_detaches_audit_row(self):
        deletion = DataDeletionRequest.objects.create(user=self.student.user)
        methodist = User.objects.create_user(
            "privacy-methodist", role=User.Role.METHODIST
        )

        anonymize_user(deletion, processed_by=methodist)

        self.audit.refresh_from_db()
        self.assertIsNone(self.audit.student)
        self.assertEqual(self.audit.pseudonym, "anonymized")
        self.assertTrue(AiOutboundRequest.objects.filter(request_id=self.audit.request_id).exists())
