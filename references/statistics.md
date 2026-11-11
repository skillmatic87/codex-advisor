# On-demand statistics

Run `python scripts/stats.py` relative to the skill (or use its absolute path). Python 3.11+
standard library is sufficient; statistics do not require the installer's tomlkit dependency.
The command reads CODEX_HOME, otherwise ~/.codex, and accepts `--codex-home PATH`.
It does not change logs/settings or contact a service.

For chat answers prefer `--json`, read the result and present a short summary/table. Do not echo
the whole JSON. Resolve the current chat's actual thread ID when the user asks for this chat;
never guess an ID or use a sidebar number. All-chat statistics need no thread ID.

```text
python scripts/stats.py --group-by model
python scripts/stats.py --since 2026-11-01 --until 2026-11-30 --group-by day
python scripts/stats.py --chat THREAD-ID --json
python scripts/stats.py --model gpt-6-astra --language de
```

Dates use local system calendar days (including historical DST). Both boundary dates are inclusive.
Tokens belong to their usage event's date; rounds belong to their recorded start date. A round
that crosses midnight can therefore contribute tokens on a day with zero started rounds.
The model is the active logged turn-context model, not the currently configured advisor model.
A round that uses multiple models can appear in more than one model group; grouped round counts
need not add up to the deduplicated overall round count.

Explain that the source is local JSONL session logs, not global account/billing data. Only exact
known advisor roles and the reserved codex_advisor_ task prefix are confirmed. Other historical
advisor-like names appear separately and are excluded. Do not reclassify by model name alone.

Input, cached input, output, reasoning output and totals are reported as logged. Cached input
and reasoning output are subsets, not extra tokens to add to the total. Counts are advisor
threads and recorded started rounds, not individual underlying model requests.

Repeated cumulative snapshots are differenced, copied histories deduplicated, inherited fork
prefixes excluded where identifiable. Unknown baselines and counter discontinuities exclude
unquantifiable intervals. Missing usage is null / `?`, never zero. On partial coverage label the
numbers **observed usage**, mention the gaps and the diagnostics. Thread-level coverage warnings
can refer to gaps outside the selected period. A completed zero-token snapshot is a real zero.
Running rounds contain only observations available at the time of reading.

JSON schema_version 1 contains filters/timezone/attribution, summary, groups, confirmed threads,
ambiguous threads and diagnostics. It contains no prompts/tool contents. All diagnostic keys are
machine-readable English; terminal labels follow `--language` or the installed language, else en.
Exit status: 0 on a produced report (including partial/no data); 2 on invalid arguments/fatal I/O.
The script never writes a statistics file; explicitly redirect `--json` output if an export is wanted.
No estimated cost, plan percentage, background watcher, hook or statistics database is provided.
