# Codex Advisor

A configurable specialist advisor for Codex coding tasks. The main model implements and tests;
the advisor supplies a focused second opinion when the main agent gets stuck or faces an
unresolved architecture, correctness or security question. [Deutsche Anleitung](README.de.md).

Defaults: **gpt-6.1-sol / medium** as the base model, **gpt-6-astra / high** as advisor.
Choose both models and reasoning efforts during setup. There is no guaranteed cost saving.

## Install

Requires Python 3.11+, Git and Codex with native cross-model subagents.

```sh
git clone https://github.com/skillmatic87/codex-advisor.git
cd codex-advisor
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` on Windows PowerShell or
`source .venv/bin/activate` on Linux/macOS. If your system uses `python3`, use it to create the environment.

```sh
python -m pip install -r requirements.txt
python scripts/setup.py
```

The wizard offers English/Deutsch and asks for base model/effort and advisor model/effort.
It shows cached local model capabilities; account access is not guaranteed. Custom model IDs
are accepted with an availability warning. Unsupported cached reasoning levels are rejected.

Setup installs the skill, a `codex_advisor` agent role, a managed global AGENTS.md block,
and global base model defaults. Other settings, profiles and comments are retained. Open a
**new Codex session** afterward. Existing sessions and explicit project/profile/session settings
can override the global base defaults. The skill never switches your active main model.

### Install or configure through Codex chat

Ask Codex to install this repository and configure Codex Advisor. It collects the same choices
and uses the same installer with explicit arguments. If installed with a generic skill installer,
invoke `$codex-advisor` to complete setup. Copying/installing a skill alone does not run a wizard
or enable the global integration. Follow the chat's filesystem approval prompts when required.

### Explicit defaults / automation

```sh
python scripts/setup.py --defaults
python scripts/setup.py --base-model gpt-6.1-sol --base-effort medium --advisor-model gpt-6-astra --advisor-effort high --language en
python scripts/setup.py --check
```

Personal settings live in `$CODEX_HOME/codex-advisor/settings.json`, otherwise
`~/.codex/codex-advisor/settings.json`, outside the copied skill. The schema has
`schema_version: 1`, `base_model`, `base_effort`, `advisor_model`, `advisor_effort`, `language`.
Use the installer instead of editing generated roles. All setup commands accept `--codex-home PATH`.

## Use

Automatic consultation occurs for two materially different failed debugging attempts,
unresolved architecture tradeoffs, contradictory evidence or subtle correctness/security questions.
You can also explicitly request advice with `$codex-advisor`.

The main agent sends a focused context packet, including relevant Git changes/history when useful,
and asks for diagnosis, next steps, uncertainties and verification. The advisor must not edit,
take external actions or spawn agents. Main-agent commentary reports activation and completion
(including errors/cancellations), using the actual advisor name. Native model/effort selection
is required; unavailable delegation is reported rather than replaced by an API/CLI workaround.

## Update, reconfigure, recover

```sh
git pull --ff-only
python -m pip install -r requirements.txt
python scripts/setup.py
python scripts/setup.py --reconfigure
python scripts/setup.py --dry-run
```

Normal updates retain choices. `--reconfigure` reopens the wizard; `--defaults` explicitly resets
to shipped defaults. `--dry-run` previews without writes; `--check` exits 0 for a consistent
installation, 1 for drift, 2 for a configuration error.

Known original Astra instructions/role are migrated. Customized legacy content or registered
legacy roles cause a conflict instead of being overwritten. The installer does not edit unrelated
instructions. Writes use local backups and atomic file replacements. An interrupted transaction
blocks subsequent setup; run `python scripts/setup.py --recover` to roll it back. Recovery stops
if affected files have since been edited. Backups remain under `codex-advisor/backups` in Codex home.
Backups can contain personal Codex settings; keep them local. No settings or credentials belong in this repo.

## Development

```sh
python -m unittest discover -s tests -v
```

CI tests Python 3.11 and 3.13 on Windows, Linux and macOS. Tests use isolated temporary Codex homes.
A real native advisor activation must also be tested in your Codex client; configuration checks
cannot prove runtime model selection or account availability.

Configuration follows [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
and [custom subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
Inspired by the executor/advisor pattern; this is an independent Codex implementation. MIT licensed.
