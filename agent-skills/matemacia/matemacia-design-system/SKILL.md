---
name: matemacia-design-system
description: Use when creating or changing Mathemation UI styles, components, templates, colors, typography, branding, logos, or product wording.
metadata:
  owner: ux
  version: 1.0.0
  status: active
  last_reviewed: 2026-07-19
  criticality: medium
activation_examples:
  positive:
    - "Собери новую карточку кабинета на существующих токенах дизайн-системы Матемации"
    - "Обнови логотип и продуктовую лексику, сохранив бренд и локальные стили"
  negative:
    - "Измени ORM-блокировку начисления XP"
    - "Проверь временной leakage в ML-датасете"
conflicts_with: [frontend-design, frontend-app-builder, figma-design-to-code]
precedence:
  - "Product invariants first (matemacia-product-invariants)"
  - "Then this domain skill"
  - "Then vendor best practices"
  - "Then generic engineering advice"
---

# Дизайн-система Матемации

Используй существующие токены из `static/css/app.css`.
Не вводи CSS-фреймворк и не дублируй палитру в шаблонах.

## Базовые токены

- Используй фон `#C3CFF5` через `--bg`.
- Используй primary `#3D6BE5` через `--primary`.
- Используй основной текст `#16181F` через `--ink`.
- Используй белый `--card` для поверхностей.
- Используй `--muted`, `--success`, `--warning`, `--danger` по назначению.
- Используй радиус карточек `--radius: 16px`.
- Используй тень `--shadow: 0 8px 24px rgba(22,24,31,.08)`.
- Используй `--radius-sm` для малых controls, а `--shadow-lift` только для интерактивного подъёма.

## Компоненты

- Переиспользуй `.card`, `.button`, `.button-primary`, chips и progress patterns.
- Не создавай новый визуальный вариант, если существующий семантически подходит.
- Сохраняй ясную иерархию hero → секция → карточка → действие.
- Не кодируй состояние только цветом; добавляй текст или знак.
- Не вставляй inline hex, если цвет уже представлен token.
- Сохраняй системный локальный font stack из `static/css/app.css`.

## Бренд

- Используй логотип только через `templates/partials/logo.html`.
- Сохраняй знак «пламя + Σ» и доступное имя «Матемация».
- Не перерисовывай логотип emoji, текстовым символом или сторонней иконкой.
- Не изменяй градиенты знака без отдельного бренд-решения.
- Проверяй уникальность SVG gradient id при многократном включении partial.

## Язык

- Пиши продуктовую лексику по-русски в UI.
- Пиши код, CSS-классы и идентификаторы по-английски.
- Не смешивай транслит и русский в именах кода.
- Используй «пробник», «отработка», «траектория», «подзабылось», «при текущем темпе».
- Сохраняй нейтральный поддерживающий тон.

## Запреты

- Не подключай Bootstrap, Tailwind или UI-kit без одобрения.
- Не подключай внешний шрифт или CDN.
- Не создавай параллельный файл токенов.

## Проверка

- Сверь цвета, радиусы, тени и logo partial.
- Проверь UI на desktop и mobile breakpoint.
- Проверь русскую лексику и английские идентификаторы.
