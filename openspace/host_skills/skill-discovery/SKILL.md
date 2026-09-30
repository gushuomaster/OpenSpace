---
name: skill-discovery
description: Search reusable OpenSpace skills locally, and browse cloud packages step by step when a cloud skill may help. Reusing proven skills saves tokens, improves reliability, and extends your capabilities beyond built-in tools.
---

# Skill Discovery

Discover and browse skills from OpenSpace's local registry and cloud skill library.

## When to use

- User asks "what skills are available?" or "is there a skill for X?"
- You encounter an unfamiliar task — a proven skill can save significant tokens over trial-and-error
- You need to decide: handle a task yourself, or delegate to OpenSpace

## Cloud access

`search_skills` is local-only. If the user wants cloud results, or a cloud operation reports a missing/invalid key, set up cloud access first and use `cloud_browse_skills`.

Ask for `email` and `agent_name`. Ask for `password` only through secure secret input; it must be 8 to 72 characters. Do not ask for passcode/OTP because `cloud_auth_flow` does not accept one.

```
cloud_auth_flow(action="bootstrap_agent_key", email="user@example.com", password="<secure-password>", agent_name="openspace-local-agent")
```

If secure password input is not available, ask the user to run:

```bash
openspace-cloud-auth bootstrap-agent-key --email user@example.com --agent-name openspace-local-agent
```

After setup, use `cloud_browse_skills`.

## search_skills

```
search_skills(query="automated deployment with rollback")
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | yes | — | Natural language or keywords |
| `limit` | no | `20` | Max results |

## cloud_browse_skills

Use this single cloud tool when local search is not enough. Continue calling
the same tool with the returned `next_actions[].action`.

```
cloud_browse_skills(action="search_skills", query="automated deployment with rollback")
cloud_browse_skills(action="local_placement", query="automated deployment with rollback")
cloud_browse_skills(action="local_placement", local_category_path="technology/computing/deployment")
cloud_browse_skills(action="import_skill", cloud_skill_id="<cloud_skill_id>", local_category_path="technology/computing/deployment/rollback")
```

`import_skill` stops at Acquisition → Quarantine and returns `candidate_id`,
`candidate_path`, and `candidate_digest`; it does not make the Skill locally
available. Run the existing skill-engineering `inspect → validate → confirm`
workflow externally against that exact `candidate_path`. The confirmation must
be a real Codex semantic confirmation. Then pass the complete serialized
Governance outcome—not a PASS flag or receipt alone—to the explicit continuation:

```
cloud_browse_skills(
  action="install_candidate",
  candidate_id="<candidate_id>",
  governance_outcome=<complete_serialized_governance_outcome>
)
```

Use `recall` and `pull_projection` only when you need package discovery or
package outlines before choosing a skill. Concrete skill search should start
with `search_skills`.

Choose `local_category_path` for the user's local package taxonomy. It uses the
same shape as cloud package paths, but is stored independently and may be more
specific than the current cloud tree. Use `local_placement` to inspect existing
paths and create a nearby child path before importing.

## After search

Results are returned to you (not executed). A cloud acquisition returns a
quarantined `candidate_path`. Only a successful `install_candidate` result
returns `installed_path` and makes the Skill eligible for local retrieval.

```
Found a matching skill?
├── YES, Governance passed and installation succeeded
│     → read SKILL.md at installed_path, follow the instructions
├── YES, but it is only quarantined
│     → complete external Governance; do not use it as an installed Skill
├── YES, but I lack the capability
│     → delegate via execute_task (see delegate-task skill)
└── NO match
      → handle it yourself, or delegate via execute_task
```

## Notes

- This is for **discovery** — you see results and decide. For direct execution, use `execute_task` from the `delegate-task` skill.
- Cloud skills have been evolved through real use — more reliable than skills written from scratch.
- Always tell the user what you found (or didn't find) and what you recommend.
