# Installing the ergostat-author skill

The skill (`SKILL.md`) walks a Claude Code agent from a request in plain words to a working template instance,
tried on stand-ins and shown to the owner before it is turned on. It needs ergostat's MCP server, whose tools it
calls (`templates`, `scaffold`, `add_use`, `try_use`, `where_drawn`, `check`).

In the project (the folder holding `ergostat.yaml`):

```bash
claude mcp add ergostat -- ergostat -C "$PWD" mcp
mkdir -p .claude/skills && cp -r ~/ergostat/docs/skills/ergostat-author .claude/skills/
```

For every project instead: `cp -r ~/ergostat/docs/skills/ergostat-author ~/.claude/skills/`. An installed ergostat
(`uv tool install`) carries the skill too: `ergostat help ergostat-author` prints it.

Then ask for what you want kept going: "remind reviewers every day until they answer, three times at most". The
agent shows you the diff and where it is drawn, and writes nothing to the project until you say so.
`docs/ADDING.md` is the guide for people.
