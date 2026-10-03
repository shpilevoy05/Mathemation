---
name: rbac-and-object-permissions
description: Use when adding endpoints, back-office pages, admin actions, parent access, expert access, role checks, or any route containing an object identifier.
---

# RBAC и object-level permissions

Используй роли из `apps/accounts/models.py` и группы «Эксперты»/«Методисты».
Сверяй seed разрешений с `apps/accounts/migrations/0004_seed_backoffice_groups.py`.
Используй общие проверки `apps/web/permissions.py`.

## Роли

- Разрешай эксперту только операции экспертного контура и просмотр нужного контекста.
- Разрешай методисту управление контентом, графом, диагностикой и траекториями.
- Не выдавай роль по названию URL или клиентскому параметру.
- Проверяй и `User.role`, и членство в группе только через общий helper.
- Сохраняй суперпользовательский доступ явным и аудируемым.
- Не расширяй permissions группы без миграции и ревью.

## Родитель

- Разрешай родителю видеть только детей из `parent.children`.
- Фильтруй отчёты, mastery, подсказки и пробники по этой связи.
- Не доверяй `student_id` из query string без проверки принадлежности.
- Не показывай заблокированные сообщения наставника.
- Не позволяй родителю изменять учебный объект через read-only маршрут.

## Эксперт

- Показывай эксперту только эскалированные mentor-сессии и заявки проверки.
- Требуй `IsExpert` для финального вердикта API.
- Проверяй допустимый статус заявки перед `finish_review`.
- Не открывай эксперту все профили учеников вне назначенного сценария.
- Аудируй reviewer в `ExpertReviewRequest`.

## IDOR

- Считай любой endpoint с `<id>` потенциальным IDOR.
- Фильтруй объект по владельцу в одном queryset `get_object_or_404`.
- Для `StudyPlanItem` используй `plan__student=student`.
- Для `ReviewSchedule` используй `backlog_item__student=student`.
- Для mock/diagnostic result используй `student=student`.
- Для родительских объектов используй связь children, не прямой primary key.
- Не выполняй lookup, а затем отдельную проверку после раскрытия данных.

## Проверка

- Напиши тест доступа владельца и чужого пользователя для каждого ID route.
- Проверь анонимного, ученика, родителя, эксперта, методиста и superuser.
- Проверь группы после миграции seed.
- Проверь, что ошибка доступа не раскрывает существование чужого объекта.
