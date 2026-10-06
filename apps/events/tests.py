from django.test import TestCase

from apps.events.models import Event
from apps.knowledge.tests import make_node, make_student
from apps.practice.models import Attempt
from apps.practice.services import submit_attempt
from apps.practice.tests import make_assignment


class EventLogTests(TestCase):
    def setUp(self):
        self.student = make_student()

    def test_attempt_creates_event_with_learning_payload(self):
        node = make_node()
        assignment = make_assignment(node, answer="42")
        submit_attempt(self.student, assignment, "42", Attempt.Context.LESSON)

        event = Event.objects.get(event_type=Event.Type.ATTEMPT_SUBMITTED)
        self.assertEqual(event.student, self.student)
        self.assertEqual(event.payload["assignment_id"], assignment.id)
        self.assertEqual(event.payload["node_ids"], [node.id])
        self.assertEqual(event.payload["context"], Attempt.Context.LESSON)
        self.assertTrue(event.payload["is_correct"])
        self.assertEqual(event.payload["submitted_answer"], "42")

    def test_existing_event_cannot_be_saved(self):
        event = Event.objects.create(event_type=Event.Type.PLAN_REBUILT)
        event.payload = {"reason": "changed"}
        with self.assertRaises(RuntimeError):
            event.save()

    def test_event_cannot_be_deleted(self):
        event = Event.objects.create(event_type=Event.Type.PLAN_REBUILT)
        with self.assertRaises(RuntimeError):
            event.delete()

