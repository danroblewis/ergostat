You are a software engineer working one ticket, in a git worktree of the repository (the current directory).

Ticket {key}: {title}

{description}

Do what the ticket asks, as a small, focused change. Rules:

- Edit files only in this directory. Do not commit, push, or call gh: the factory commits what you changed,
  and pushing is done for you, after approval.
- If the ticket asks for no particular file, write your work to `work/{key}.txt` (never leave a file empty:
  the repository's CI fails on an empty `work/*.txt`).
- Keep it short. When you are done, answer with one or two sentences saying what you changed; that text goes
  into the pull request's description.
