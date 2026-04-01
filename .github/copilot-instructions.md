# Project Guidelines

## Source Of Truth
- Use [guide01.md](guide01.md) as the primary project policy document.
- Keep this file minimal; do not duplicate long process docs.

## Repository Workflow
- Use GitHub Flow only.
- Never commit directly to main.
- Create feature branches with pattern: type/name-task.
- Open a PR for all merges to main.

## Commit And PR Conventions
- Use Conventional Commit prefixes: feat, fix, docs, refactor.
- PR title format: [Feat] OOO 기능 추가.
- In PR description, include:
  - What problem is solved
  - How to test
  - Related issue (if any)

## Project Structure
- Follow monorepo structure defined in [guide01.md](guide01.md):
  - adf for ADF pipeline JSON
  - src/utils and src/models for shared Python modules
  - notebooks for EDA and experiments
  - docs for architecture, schema, and meeting notes

## Data And Security Rules
- Do not commit data files such as csv/parquet to Git.
- Do not commit secrets or env files.
- Ensure gitignore blocks local data and secret files.

## Tool-Specific Collaboration Notes
- Azure Data Factory:
  - Switch to your feature branch before editing.
  - Coordinate in chat before touching the same pipeline to avoid JSON merge conflicts.
  - After merge to main, publish from ADF main branch.
- Databricks Repos:
  - Work on feature branches and sync frequently with Pull.
- ML Studio:
  - Use terminal Git workflow.
  - Track Git commit hash in MLflow tags for experiment traceability.

## Build And Test
- This repository is in bootstrap stage.
- If build/test commands are introduced later, add them to README and keep this file linked to README instead of duplicating command details.