"""Database-free tests for arena rank boundaries and progress."""

from unittest import TestCase

from .ranks import rank_for_rating


class RankForRatingTests(TestCase):
    def test_silver_boundary_is_inclusive(self):
        below = rank_for_rating(1099)
        at_boundary = rank_for_rating(1100)

        self.assertEqual(below["code"], "bronze")
        self.assertEqual(below["points_to_next"], 1)
        self.assertEqual(at_boundary["code"], "silver")
        self.assertEqual(at_boundary["min_rating"], 1100)

    def test_diamond_boundary_is_inclusive(self):
        self.assertEqual(rank_for_rating(1699)["code"], "platinum")
        self.assertEqual(rank_for_rating(1700)["code"], "diamond")

    def test_diamond_has_no_next_league(self):
        league = rank_for_rating(1800)

        self.assertIsNone(league["next_code"])
        self.assertIsNone(league["next_title"])
        self.assertIsNone(league["next_min_rating"])
        self.assertIsNone(league["points_to_next"])
        self.assertEqual(league["progress_percent"], 100)

    def test_progress_is_position_inside_current_band(self):
        league = rank_for_rating(1200)

        self.assertEqual(league["progress_percent"], 50)
        self.assertEqual(league["points_to_next"], 100)

    def test_none_and_negative_rating_fall_back_to_bronze(self):
        for rating in (None, -1):
            with self.subTest(rating=rating):
                league = rank_for_rating(rating)
                self.assertEqual(league["code"], "bronze")
                self.assertEqual(league["progress_percent"], 0)
