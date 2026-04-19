---
name: clawhub
description: Search and install agent skills from ClawHub, the public skill registry.
homepage: https://clawhub.ai
metadata: {"sun_agent":{"emoji":"🪃"}}
---

# ClawHub

Public skill registry for AI agents. Search by natural language and install directly into the TokenMind workspace.

## When to use

Use this skill when the user asks to:
- find a skill
- search for skills
- install a skill
- list available skills
- update installed skills

## Search

```bash
npx --yes clawhub@latest search "web scraping" --limit 5
```

## Install

```bash
npx --yes clawhub@latest install <slug> --workdir ~/.tokenmind/workspace
```

Replace `<slug>` with the skill name from search results. This installs the skill into `~/.tokenmind/workspace/skills/`, where TokenMind loads workspace skills from.

## Update

```bash
npx --yes clawhub@latest update --all --workdir ~/.tokenmind/workspace
```

## List installed

```bash
npx --yes clawhub@latest list --workdir ~/.tokenmind/workspace
```

## Notes

- Requires Node.js (`npx` comes with it).
- No API key is needed for search or install.
- Login (`npx --yes clawhub@latest login`) is only required for publishing.
- `--workdir ~/.tokenmind/workspace` is critical. Without it, skills install into the current directory instead of the TokenMind workspace.
- After install, remind the user to start a new session to load the skill.
