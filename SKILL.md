---
name: codex-advisor
description: Consult a configurable specialist model automatically for difficult coding decisions, unresolved bugs or conflicting evidence. Also handles advisor setup and on-demand local advisor usage/token statistics. The main agent implements and validates.
---

# Codex Advisor

Use the configured advisor without changing the active main model or its reasoning effort.
This workflow applies only to the main agent; advisors must not invoke advisors recursively.

## Setup and configuration

Resolve Codex home from CODEX_HOME, otherwise ~/.codex. Read codex-advisor/settings.json
there before consultation. It holds schema_version (1), base_model, base_effort,
advisor_model, advisor_effort, and language. Personal configuration stays outside the skill.

When settings are absent, explain that copying a skill does not configure global automation.
On an explicit first invocation, or when asked to configure/reconfigure, read
[setup instructions](references/setup.md). Collect the four model/effort choices with defaults
gpt-6.1-sol medium and gpt-6-astra high. Do not silently install defaults during ordinary work.
Installation sets future global defaults; running sessions and explicit overrides remain intact.

## When to consult

Evaluate before implementation and when new evidence changes the situation. Consult automatically
when a focused second opinion could change the next decision:

- A bug remains unexplained after two materially different evidence-based attempts.
- A consequential architecture choice has unresolved tradeoffs.
- Code, tests, or runtime evidence conflict and you cannot resolve the contradiction.
- A subtle correctness, concurrency, or security question remains unresolved.
- The user explicitly requests advice.

Consult earlier when another failed attempt would be costly. Routine tasks need no consultation.
These instructions explicitly authorize native advisor delegation for the focused question.

## Context packet

Give the advisor the user's objective and constraints, one precise question, relevant paths,
code/errors/runtime observations, previous approaches and actual results. Include an appropriate
git diff --stat and git log -5 --oneline when useful; omit Git context outside a repository.
Inspect relevant diffs rather than sending unrelated or sensitive material. Request diagnosis,
recommended next step, uncertainties and a way to verify it. Instruct the advisor to inspect
files if needed but not edit files, take external actions or spawn agents.

## Native consultation

Use advisor_model and advisor_effort from settings with fresh context. For collaboration.spawn_agent,
pass fork_turns="none", model=advisor_model, reasoning_effort=advisor_effort and a task_name starting
with `codex_advisor_` (for example `codex_advisor_schema_review`). Reserve this prefix exclusively
for advisor consultations so the statistics can identify them without examining prompts. Do not use a fixed
Astra role for a different configured model. Alternatively use the generated codex_advisor role
only after checking its model/effort match settings; report divergence and request reconfiguration.
Never change all other subagent defaults. If the runtime cannot select the requested model/effort,
report that limitation; do not silently substitute or launch an API/CLI workaround.

Start one advisor per unresolved decision; reuse it for focused follow-ups. Wait when the next
step depends on advice. Evaluate the recommendation against evidence, implement and verify it.
Do not treat advice alone as proof. Mention material advice and its verification in the result.
Do not promise cost savings without measured usage.

## Notifications

The main agent sends short commentary notifications for every advisory turn, including follow-ups.
Use the user's language and the actual advisor name (Astra for gpt-6-astra):

- After successful activation: `Astra aktiviert: <Anlass>.`
- Immediately upon observing completion: `Astra beendet: <Ergebnis>.`

Use equivalent wording for other configured advisors. If activation fails, say it could not be
activated and why. If a started consultation fails or is cancelled, send the end notification
with that outcome. An idle advisor is not an active consultation. Activity cards do not replace
these messages. Never describe an unverified recommendation as a validated fix.

## Usage statistics on request

When asked how often the advisor ran or how many tokens it used, read
[statistics instructions](references/statistics.md) and run scripts/stats.py. Default to all
locally recorded confirmed advisor threads, unless the user specifies a period/chat/model.
Do not add token statistics to routine start/end notifications. The statistics command only reads
local logs; no setup, network access or advisor consultation is needed merely to display usage.
