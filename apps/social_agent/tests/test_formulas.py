from django.test import SimpleTestCase

from apps.social_agent.formulas import FormulaRenderError, to_telegram_text


class FormulaRenderingTests(SimpleTestCase):
    def test_common_inline_latex_is_rendered(self):
        self.assertEqual(
            to_telegram_text(r"Если $x^2 \le 4$, то $x_1 \ne \pi \cdot 2$"),
            "Если x² ≤ 4, то x₁ ≠ π · 2",
        )
        self.assertEqual(to_telegram_text(r"$\sqrt{x}+\sqrt{x+1}$"), "√x+√(x+1)")
        self.assertEqual(to_telegram_text(r"$\frac{a}{b}$ и $\frac{a+b}{2}$"), "a/b и (a+b)/2")
        self.assertEqual(to_telegram_text(r"$90^\circ$; $2\times3$"), "90°; 2×3")
        self.assertEqual(to_telegram_text(r"$x^a+y_k$"), "xᵃ+yₖ")

    def test_plain_text_is_unchanged(self):
        self.assertEqual(to_telegram_text("Обычный текст"), "Обычный текст")

    def test_complex_or_unknown_latex_fails_closed(self):
        values = (
            r"$\frac{1}{\frac{2}{3}}$",
            r"$\begin{matrix}1&2\end{matrix}$",
            r"$\int_0^1 x dx$",
            r"$\unknown{x}$",
            r"$x^q$",
            r"$x+1",
        )
        for value in values:
            with self.subTest(value=value), self.assertRaises(FormulaRenderError):
                to_telegram_text(value)
