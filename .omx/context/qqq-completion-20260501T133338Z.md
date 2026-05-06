# Context Snapshot: QQQ skill completion

## Task statement
User invoked $team and asked to continue until thoroughly complete for the QQQ 0DTE options trading system in C:\Users\Tablo\IdeaProjects\qqq-trading-system.

## Desired outcome
Make the project operationally complete for safe non-real-order use: repeatable checks, robust diagnostics, docs, and tests. Do not submit live orders or perform irreversible external writes.

## Known facts / evidence
- Repo migrated to C:\Users\Tablo\IdeaProjects\qqq-trading-system.
- Current branch main is ahead of origin/main and pushed to fork/main through commit 41f5460.
- skill_check.py exists and passed with Longbridge SDK/CLI quote checks.
- 30 unit tests passed before team launch.
- py_compile passed before team launch.
- Longbridge CLI token is valid; CN/global connectivity true.
- Hermes notification path reaches Hermes, but Weixin/iLink returns rate limited ret=-2.
- Gist publish path remains dry-run because GIST_ID and GITHUB_TOKEN are unset.
- Real submit path is intentionally unverified; requires explicit --submit-live-orders and must not be run by this team.

## Constraints
- No real Longbridge order submission.
- No Gist upload unless credentials are configured and explicit confirmation is provided; this run has no such confirmation.
- Keep diffs small, tested, and documented.
- Workers must commit their own changes if they modify files.
- Prefer deterministic scripts/tests over prose-only completion claims.

## Unknowns / open questions
- Whether runtime state.json/today.csv should be reset or preserved. Treat existing ignored runtime files as user runtime artifacts; do not delete without explicit reason.
- Whether Weixin rate limit clears during this run. Classify as external unless evidence changes.

## Likely touchpoints
- skill_check.py
- README.md
- SKILL.md
- tests/
- trade_notify.py
- watchdog.py
- update_gist.py
- runtime ignored files only for read-only diagnosis

## Suggested team lanes
1. Diagnostics lane: improve/verify skill_check.py coverage for stale lock/state, env readiness, and safe external blockers.
2. Docs/ops lane: update README/SKILL with final operational checklist and explicit external blockers.
3. Verification lane: run unit tests, py_compile, skill_check, and live-dry-submit temp smoke; report evidence.
