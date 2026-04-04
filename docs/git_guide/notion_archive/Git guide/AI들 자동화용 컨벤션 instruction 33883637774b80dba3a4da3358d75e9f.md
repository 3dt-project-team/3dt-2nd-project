# AI들 자동화용 컨벤션 instruction

원리는 이해해야하니 문서화했지만, 실제로 현업에서는 Agentic coding으로 이조차도 자동화로 하기 원하지 않습니까?

그래서 instruction 작성해서 공유합니다.

**✅ Codex용 Instruction (Agentic coding)**

```jsx
You are an agentic coding assistant for this repository. You MUST follow our Git conventions exactly.

Branch rules
	•	Default branch is dev. NEVER push directly to dev. Always use PRs.
	•	Create a working branch per task/issue using: type/short-description
	•	Allowed types: feat, fix, hotfix, chore, refactor
	•	Naming rules: lowercase only, use - instead of spaces, keep it short and meaningful.

Commit message rules
	•	Format: type(scope): short description
	•	Allowed types: feat, fix, hotfix, chore, refactor, docs
	•	Allowed scopes:
	•	api, function, pipeline, db, infra, ci, auth, config, refactor, docs, frontend(web), frontend(ios)
	•	Keep description concise and action-oriented.

Issue rules (when creating issues)
	•	Feature issue title must start with: feat(scope): 
	•	Description must be bullet-style (2–4 bullets) describing what changes.
	•	Bug issue title must start with: fix(scope): 
	•	Fill both sections with bullets:
	•	“What happened?”
	•	“Expected behavior”

PR rules
	•	PR title MUST be: type(scope): description (same types/scopes as above).
	•	PR body MUST follow exactly:
	•	## Summary (1 bullet)
	•	## Changes (2–5 bullets)
	•	## Test (- N/A if none)
	•	## Related (- Closes #<issue_number> when applicable)

Enforcement
	•	If any generated branch/commit/PR/issue does not comply, FIX it before proceeding.
	•	Do not invent new types/scopes.
```

**✅ Gemini용 Instruction (Agentic coding)**

```jsx
You are an automated coding agent for this repository. Strictly follow the Git conventions below.

Branch rules
	•	Default branch: dev
	•	NEVER push directly to dev
	•	Use PRs only
	•	Branch format: type/short-description
	•	Allowed types: feat, fix, hotfix, chore, refactor
	•	Lowercase only, use hyphens, concise naming.

Commit message rules
	•	Format: type(scope): short description
	•	Allowed types: feat, fix, hotfix, chore, refactor, docs
	•	Allowed scopes:
	•	api, function, pipeline, db, infra, ci, auth, config, refactor, docs, frontend(web), frontend(ios)
	•	Keep messages concise and action-oriented.

Issue rules
	•	Feature issue: feat(scope): description
	•	Bullet-style description (2–4 bullets).
	•	Bug issue: fix(scope): description
	•	Bullet lists under:
	•	What happened?
	•	Expected behavior

PR rules
	•	Title: type(scope): description
	•	Body must follow exactly:
	•	## Summary (1 bullet)
	•	## Changes (2–5 bullets)
	•	## Test (- N/A if none)
	•	## Related (- Closes #<issue_number> when applicable)

Validation
	•	Validate all Git outputs before finalizing.
	•	Do not introduce new types or scopes.
```

**✅ Claude Instruction**

```jsx
You are responsible for maintaining strict Git discipline in this repository.

Branch rules
	•	Default branch is dev
	•	Direct pushes to dev are prohibited
	•	Use PR-based workflow only
	•	Branch naming: type/short-description
	•	Allowed types: feat, fix, hotfix, chore, refactor
	•	Lowercase + hyphen formatting only

Commit rules
	•	type(scope): short description
	•	Allowed types: feat, fix, hotfix, chore, refactor, docs
	•	Allowed scopes:
	•	api, function, pipeline, db, infra, ci, auth, config, refactor, docs, frontend(web), frontend(ios)
	•	Keep concise and action-oriented.

Issue rules
	•	Feature: feat(scope):
	•	2–4 bullet points describing changes.
	•	Bug: fix(scope):
	•	Bullet points under:
	•	What happened?
	•	Expected behavior

PR rules
	•	Title: type(scope): description
	•	Body structure must match:
	•	## Summary
	•	## Changes
	•	## Test
	•	## Related

Enforcement
	•	Automatically correct any non-compliant output.
	•	Do not create undefined types or scopes.
```

**✅GitHub Copilot Instruction**

```jsx
When generating branch names, commit messages, issue titles, or PR content, you MUST follow the repository Git conventions.

Branch rules
	•	Use type/short-description
	•	Allowed types: feat, fix, hotfix, chore, refactor
	•	Never suggest direct push to dev.

Commit rules
	•	Format: type(scope): short description
	•	Allowed types: feat, fix, hotfix, chore, refactor, docs
	•	Allowed scopes:
	•	api, function, pipeline, db, infra, ci, auth, config, refactor, docs, frontend(web), frontend(ios)

Issue rules
	•	Feature: feat(scope):
	•	Bug: fix(scope):
	•	Use bullet-style descriptions.

PR rules
	•	Title must be type(scope): description
	•	Body must include:
	•	## Summary
	•	## Changes
	•	## Test
	•	## Related

Compliance
	•	Do not generate outputs that violate the defined types or scopes.
```