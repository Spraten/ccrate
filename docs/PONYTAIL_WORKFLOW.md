# Ponytail project workflow

Installed from the official https://github.com/DietrichGebert/ponytail repository
using Codex's skill-installer. The exact source commit and installed checksum are
recorded in ponytail-install.json. The skill is installed at
/home/user/.codex/skills/ponytail/SKILL.md. Mode: full.

Ponytail is an agent ruleset, not a server or daemon. Run it by reading and applying
the installed skill during a coding workflow. AGENTS.md makes this persistent for
future project sessions; the installed skill is also available to Codex on the
next turn. No separate background service is required.

For this queue it is active: device reconnection reuses the existing SUPVAN probe
and browser media APIs; avatars use local SVG; nesting uses Homebox's entity
parents. Keep required functionality and recovery intact. Before finishing,
review the diff for duplicate helpers and unnecessary dependencies, and run the
checks appropriate to the change.

Validate installation with:

```sh
python3 deploy/verify-ponytail.py
```

To update, review the official source and its skill before installing a new pinned
revision. Do not overwrite the project AGENTS.md with upstream example rules.
