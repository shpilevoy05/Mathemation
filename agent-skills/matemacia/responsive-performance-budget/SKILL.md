---
name: responsive-performance-budget
description: Use when adding frontend assets, scripts, fonts, video, images, responsive layouts, or measuring page weight and load performance.
metadata:
  owner: ux
  version: 1.0.0
  status: active
  last_reviewed: 2026-07-19
  criticality: medium
activation_examples:
  positive:
    - "Проверь вес кабинета и загрузку страницы на медленном мобильном соединении"
    - "Добавь адаптивное изображение решения без выхода за performance budget"
  negative:
    - "Исправь проверку object permission для родителя"
    - "Измени критерии экспертной проверки части 2"
conflicts_with: [react-best-practices]
precedence:
  - "Product invariants first (matemacia-product-invariants)"
  - "Then this domain skill"
  - "Then vendor best practices"
  - "Then generic engineering advice"
---

# Responsive и performance budget

Сохраняй кабинет лёгким, локальным и пригодным для школьного мобильного интернета.
Используй существующие `static/css/app.css` и `static/js/app.js`.

## Бюджет

- Держи страницу кабинета без данных меньше 200 KB перед gzip как целевой бюджет.
- Считай HTML, CSS, JS, SVG и критические встроенные assets.
- Не включай видео и пользовательские изображения в shell-бюджет, но измеряй их отдельно.
- Зафиксируй способ измерения и повторяй его перед релизом.
- Останавливай добавление декоративного asset, если бюджет превышен.
- Предпочитай CSS и простой SVG тяжёлым растровым фонам.

## Зависимости

- Не используй CDN.
- Не подключай внешние шрифты; сохраняй системный stack из `static/css/app.css`.
- Используй vanilla JS.
- Не добавляй frontend framework ради локального взаимодействия.
- Не загружай сторонний analytics blocking-скриптом.
- Не вводи новую зависимость без одобрения.

## Видео и изображения

- Добавляй `loading="lazy"` к iframe видео, как в `templates/lesson.html`.
- Не загружай iframe до появления релевантного урока.
- Давай iframe содержательный title.
- Ограничивай изображения решений `max-width: 100%`/`width: 100%` без выхода из контейнера.
- Используй подходящий размер и формат изображения.
- Не встраивай base64-сканы в HTML.

## Responsive

- Используй существующие breakpoints и mobile bottom navigation.
- Проверяй 320 px, средний mobile, tablet и desktop.
- Не допускай горизонтального scroll из-за формул, таблиц и изображений.
- Переноси длинные математические строки или давай локальный scroll контейнеру.
- Сохраняй цели управления ≥44 px на mobile.
- Не скрывай критическое действие только hover-состоянием.

## JavaScript

- Загружай скрипт с defer и инициализируй только нужные элементы.
- Не делай сетевой запрос до пользовательского действия без продуктовой причины.
- Отменяй повторную отправку формы и показывай состояние загрузки.
- Не блокируй main thread тяжёлым клиентским расчётом прогноза.

## Проверка

- Измерь shell страницы и сравни с 200 KB.
- Проверь lazy iframe и размеры изображений.
- Проверь responsive layout и отсутствие внешних запросов шрифтов/CDN.
- Пройди задачу на throttled mobile profile.
