# Setup in Codex chat

Use Python 3.11+ and install requirements.txt in an isolated environment when necessary.
Resolve script paths relative to this skill. Run scripts/setup.py --list-models to inspect the
local cache; it describes cached capabilities, not guaranteed account access. Offer custom IDs
and report unverified availability rather than substituting models.

Ask for base model, base effort, advisor model, advisor effort, and language (en/de).
Defaults are gpt-6.1-sol / medium and gpt-6-astra / high. Explain that setup changes global
defaults for future sessions and installs automatic advisor instructions. Once the user has
chosen and authorized setup, run the same engine as terminal setup with explicit arguments:

```text
python scripts/setup.py --base-model gpt-6.1-sol --base-effort medium --advisor-model gpt-6-astra --advisor-effort high --language de
```

Use absolute script paths when working outside the skill directory. Respect normal filesystem
approvals. Do not rewrite config manually or change current-session model settings. Then run
--check and explain that a fresh session is needed for defaults and newly discovered agent roles.
Updates preserve personal settings; --reconfigure runs the terminal wizard again. A chat
reconfiguration collects choices in chat and supplies all four explicit flags instead.
--defaults is an explicit request to reset to shipped defaults. --dry-run writes nothing.
--recover rolls back an interrupted installation using retained local backups, stopping if
someone edited affected files afterward. Customized legacy instructions/roles require resolving
the reported conflict; do not delete them blindly.
