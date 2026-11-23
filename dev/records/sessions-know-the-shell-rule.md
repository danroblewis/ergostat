# sessions-know-the-shell-rule: build and review sessions use the shell in the form it allows

In six hours, 283 sessions had 680 commands refused, mostly because they chained commands with `&&`, `;` or pipes under the allowlist. One session concluded the shell was broken and parked top-priority work three times.

Change. The implementor and reviewer prompts state that each Bash call is one allowed command, name what to use instead, and say a refusal is never a reason to stop. Add a measure of refused commands per session so a rise is visible. Do not widen the allowlist.

Definition of done.
1. A test proves both rendered briefs contain the rule and every command the implementor prompt tells a session to run is allowed for that role.
2. Refused commands per session is a measure on the model.
3. Do not measure or change the live instance in the session.
