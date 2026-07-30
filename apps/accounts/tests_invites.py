"""Приглашения, группы и деактивация вместо удаления."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import StudentGroup, StudentProfile, User
from .services import (
    accept_invite,
    active_students,
    create_invite,
    deactivate_student,
    reactivate_student,
)


class InviteTests(TestCase):
    def setUp(self):
        self.methodist = User.objects.create_user("inv-methodist", role=User.Role.METHODIST)
        self.group = StudentGroup.objects.create(title="Поток 2027")

    def test_invite_creates_student_with_profile_and_group(self):
        invite = create_invite(self.methodist, group=self.group)
        user = accept_invite(invite.code, username="new-student", password="s3cret-pass")
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertIn(user.student_profile, self.group.students.all())

    def test_invite_is_single_use(self):
        invite = create_invite(self.methodist)
        accept_invite(invite.code, username="first", password="s3cret-pass")
        with self.assertRaises(ValidationError):
            accept_invite(invite.code, username="second", password="s3cret-pass")

    def test_expired_invite_rejected(self):
        invite = create_invite(self.methodist)
        invite.expires_at = timezone.now() - timedelta(hours=1)
        invite.save(update_fields=["expires_at"])
        with self.assertRaises(ValidationError):
            accept_invite(invite.code, username="late", password="s3cret-pass")

    def test_taken_username_rejected(self):
        User.objects.create_user("occupied")
        invite = create_invite(self.methodist)
        with self.assertRaises(ValidationError):
            accept_invite(invite.code, username="occupied", password="s3cret-pass")


class DeactivationTests(TestCase):
    def setUp(self):
        self.student = StudentProfile.objects.create(
            user=User.objects.create_user("leaver")
        )
        self.group = StudentGroup.objects.create(title="Поток")
        self.group.students.add(self.student)

    def test_deactivation_keeps_history_and_blocks_login(self):
        deactivate_student(self.student)
        self.student.user.refresh_from_db()
        self.assertFalse(self.student.user.is_active)
        self.assertTrue(StudentProfile.objects.filter(pk=self.student.pk).exists())
        self.assertIn(self.student, self.group.students.all())

    def test_inactive_student_not_in_active_list(self):
        deactivate_student(self.student)
        self.assertNotIn(self.student, active_students(self.group))
        reactivate_student(self.student)
        self.assertIn(self.student, active_students(self.group))
