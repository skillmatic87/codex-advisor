# Automatic Astra advisor

For every coding task, the main agent must load and apply the `codex-advisor` skill at `~/.codex/skills/codex-advisor/SKILL.md` automatically. The user does not need to name the skill. Preserve the selected main model and its reasoning settings.

Monitor the skill's consultation criteria throughout the task. When one applies, automatically delegate a focused advisory question to `gpt-6-astra` with reasoning effort `high`. Do not wait for an explicit request or ask for confirmation to obtain the advice. Proceed using the available native subagent tools and existing permissions.

For every Astra advisory turn, including follow-ups, send a short chat notification after successful activation (`Astra aktiviert: <Anlass>.`) and another as soon as completion is observed (`Astra beendet: <Ergebnis>.`). Send these as main-agent commentary messages, not only in the final answer or subagent activity cards. Report failed activation honestly; report cancellation or failure in the end notification when a consultation had started.

Use a fresh context and explicitly select Astra, or use the configured `astra_advisor` role. The main agent evaluates the recommendation and remains responsible for implementation and validation. Routine work can remain with the main agent.

These instructions explicitly request and authorize advisor delegation when the criteria apply. They apply to the main agent only; an advisory subagent must not recursively invoke another advisor. If Astra or cross-model delegation is unavailable, report the limitation instead of silently substituting a model.
