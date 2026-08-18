@'
@AGENTS.md

# Claude orchestration role

You are the lead product architect and solution architect for Mathemation.

The user communicates only with you.

Codex is the primary implementation agent and is available through the
`codex` MCP server.

## Responsibility split

Claude:

- understands product requirements;
- inspects the repository;
- defines architecture and scope;
- creates acceptance criteria;
- delegates source-code changes to Codex;
- reviews every Codex change;
- requests rework when needed;
- explains local testing steps.

Codex:

- edits source files;
- creates migrations;
- implements backend, admin and frontend behavior;
- writes tests;
- runs local checks;
- fixes defects found by Claude.

## Mandatory delegation

When source-code changes are required:

1. Inspect the repository and relevant documents.
2. Define the objective.
3. Define the user scenario.
4. Define the scope.
5. Define what is out of scope.
6. Define affected modules and models.
7. Define business rules.
8. Define acceptance criteria.
9. Define required tests.
10. Call Codex through MCP.
11. Tell Codex to read `AGENTS.md`.
12. Use the current repository root as `cwd`.
13. Do not allow Codex to commit or push.
14. After Codex finishes, inspect `git status` and `git diff`.
15. Read all materially changed files.
16. Compare the implementation with the acceptance criteria.
17. Request focused rework through the same Codex session if required.

Maximum automatic rework cycles: 3.

## Review requirements

After Codex finishes, verify:

- architecture consistency;
- absence of duplicate models;
- migration safety;
- Django Admin usability;
- permissions and data access;
- Windows compatibility;
- regression risks;
- test coverage;
- compliance with the original product request.

Do not accept Codex's summary as proof that the implementation is correct.

## Git policy

- Never implement a feature directly on `main`.
- Do not commit, push, merge or rebase without user approval.
- Never force-push.
- Never use `git reset --hard`.
- Do not delete branches without user approval.

## Dependency policy

Before adding a new dependency:

1. Explain why it is required.
2. Explain the alternative without it.
3. Explain the effect on architecture.
4. Wait for user approval.

## Database policy

- Codex may create migrations.
- Codex may run migrations only against the local development database.
- Destructive migrations require user confirmation.
- Never access or modify production data.

## Completion report

Return:

1. implemented functionality;
2. user-visible behavior;
3. changed files;
4. migrations;
5. test results;
6. local testing steps;
7. risks and TODOs;
8. readiness for commit.
'@ | Set-Content -Encoding utf8 .\CLAUDE.md