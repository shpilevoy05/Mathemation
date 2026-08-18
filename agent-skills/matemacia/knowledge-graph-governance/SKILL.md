---
name: knowledge-graph-governance
description: Use when changing Mathemation knowledge nodes, prerequisite edges, mastery states, graph traversal, or methodist graph administration.
---

# Управление графом знаний

Рассматривай граф как версионируемый методический актив, а не как обычный CRUD.
Работай с `KnowledgeNode` и `KnowledgeDependency` в `apps/knowledge/models.py`.
Учитывай группировку `TopicCluster` и ученическое состояние `SkillMastery` в том же файле.

## Узлы

- Делай узел гранулярным навыком, а не широкой темой.
- Сохраняй стабильность `KnowledgeNode.code`; используй его как смысловой идентификатор.
- Проверяй `cluster`, `weight`, `exam_part`, `ege_task_numbers` и `order`.
- Не меняй смысл использованного узла на месте; создавай новую версию или новый узел.
- Не удаляй узел, если на него ссылаются попытки, mastery, задания или backlog.
- Для вывода узла из употребления сначала спроектируй миграцию истории и связей.
- Не оставляй orphan nodes: у узла должна быть методическая роль и покрытие контентом.

## Рёбра

- Храни prerequisite-связи в `KnowledgeDependency`.
- Интерпретируй `prerequisite` как предшественника поля `node`.
- Учитывай `min_mastery` на каждом ребре; не заменяй его одним глобальным порогом.
- Сохраняй диапазон `min_mastery` 0..100 и уникальность пары узлов.
- Запрещай самоссылки и циклы до публикации графа.
- Проверяй, что каждое ребро ведёт между существующими узлами.
- Не «чинить» цикл сортировкой защитного хвоста в `apps/engine/planner.py`; исправляй данные.

## Состояния узла

- Различай persistent-статусы `not_started`, `in_progress`, `practiced`, `mastered`, `decayed`.
- Для UI выводи `locked`, `available`, `in_progress`, `mastered`, `decayed` через `node_states`.
- Не путай закрытость по пререквизитам со значением `SkillMastery.status`.
- Пересчитывай доступность по всем рёбрам и их индивидуальным порогам.
- Сохраняй decay-переходы через `apps/knowledge/services.py`.

## Обходы и границы

- Для малых графов используй обычные таблицы и рекурсивные CTE.
- Не вводи Neo4j: текущий граф рассчитан примерно на 80–150 узлов.
- Передавай граф в чистый движок через `EdgeDTO` из `apps/engine/dto.py`.
- Не импортируй Django ORM в `apps/engine/`.

## Проверка

- Проверь отсутствие циклов, orphan nodes и битых ссылок.
- Проверь порядок пререквизитов тестами `apps/engine/tests/test_algorithms.py`.
- Проверь пороги рёбер в `apps/knowledge/tests.py` и `apps/planning/tests.py`.
- Проверь миграцию истории перед удалением или заменой смысла узла.
