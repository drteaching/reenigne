# Feedback pipeline

Users report bugs and suggest improvements from the desktop app, the CLI or
the website. Each submission is triaged automatically by an LLM and, when
configured, filed as a structured GitHub issue. A maintainer can then escalate
an issue to a full codebase investigation.

```
desktop / CLI / web
        │  POST /v1/feedback   (free, rate limited, secrets rejected)
        ▼
   feedback (received)
        │  enqueue
        ▼
 feedback_triage_jobs ──► runner ──► one text-only LLM call
        │                                    │
        │                              schema validation
        │                              ┌─────┴─────┐
        │                          invalid       valid
        │                             │             │
        ▼                             ▼             ▼
   status=triaged            triaged + error   GitHub issue
                                               status=filed
                                                     │
                                       maintainer adds "claude-investigate"
                                                     ▼
                                          full investigation comment
```

## Cost

| Stage | When | Rough cost |
|-------|------|------------|
| Triage | Every submission | One text call, ~2–4k input tokens, a fraction of a cent on `gpt-4o-mini` |
| Investigation | Only when a human adds `claude-investigate` | A full agent run over the repo — **dollars, not cents**, and highly variable with repo size |

The gap between those two rows is why the investigation is never automatic.
Inbound feedback volume is chosen by whoever is submitting; if a stranger
could trigger a repo-wide agent run per report, they would control the bill.

## Configuration

Everything below is optional. With none of it set, feedback is still accepted,
stored and triaged — only the filing and escalation stop.

### API (`apps/api` environment)

| Var | Purpose |
|-----|---------|
| `TRIAGE_MODEL` | Classification model. Default `gpt-4o-mini` — text only, cheapest capable. |
| `GITHUB_FEEDBACK_TOKEN` | Fine-grained PAT, **Issues: read and write on this repo only**. |
| `GITHUB_FEEDBACK_REPO` | `owner/name`. |
| `FEEDBACK_MAX_PER_USER_PER_DAY` | Default 5. |
| `FEEDBACK_MAX_PER_IP_PER_DAY` | Default 3, anonymous submissions. |

The PAT must not carry Contents, Pull requests or Actions permissions. The
service calls only the issues endpoints, and a test asserts it never touches
`/contents`, `/git/` or `/pulls` — if that ever changes, it should fail in CI
rather than as a 403 in production.

### Repository secret

`ANTHROPIC_API_KEY` — used only by `.github/workflows/claude-investigate.yml`.
Settings → Secrets and variables → Actions → New repository secret.

### Labels

Create these once: `bug`, `improvement`, `severity:critical`, `severity:high`,
`severity:medium`, `severity:low`, `ai-triaged`, `needs-human`,
`claude-investigate`.

## Escalation

Add the `claude-investigate` label to an issue. The workflow checks out the
repo, investigates, and posts its findings as a comment.

It never runs on `ai-triaged`, and never when the label is applied by a bot
account. Both guards exist because issue bodies contain text written by
anonymous members of the public and filed automatically — requiring a
maintainer to apply the label puts a person between that text and an agent
with repository access. The workflow's permissions are `contents: read` and
`issues: write`: it can read the code and comment, and cannot push, merge or
deploy.

## What is and is not sent

Attached, only with the user's explicit consent in the client:

- App version, platform, OS.
- Behind a **second** checkbox, the last 100 lines of the worker log.

Never attached, by any path: recordings, extracted frames, transcripts,
session manifests or generated reports.

Before anything reaches GitHub it passes through a sanitiser that strips
credential patterns and email addresses, then truncates. That runs regardless
of what the triage model returns — the caps are the server's, not a suggestion
the model can raise.

## Safety properties worth preserving

If you change this pipeline, these are the invariants the tests defend:

1. **Triage never touches quota, credits or refunds.** `feedback_triage_jobs`
   deliberately has no billing columns, so this is structural rather than a
   rule to remember.
2. **The model's output is untrusted.** It is schema-validated; a malformed or
   out-of-enum payload marks the feedback triaged with an error and files
   nothing.
3. **The model cannot widen its own blast radius.** Labels are built
   server-side from validated enums, `duplicate_of` is used only as an integer
   against the configured repo, and no model-supplied URL is ever fetched.
4. **The feedback body is attacker-controlled.** It is fenced and labelled as
   data in the prompt, but the containment that matters is (2) and (3).
5. **GitHub is optional.** Unconfigured or failing, triage still completes and
   stores its classification.
