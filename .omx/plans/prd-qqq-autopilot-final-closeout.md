# PRD: QQQ autopilot final closeout

## Objective
Finish all remaining authorized QQQ project items while preserving financial safety.

## Scope
1. Verify the repo and runtime state.
2. Push the two local commits to origin/main.
3. Start the project in safe live-dry-submit mode if verification is green.
4. Record that true real-order verification is blocked pending manual order-ticket confirmation.
5. Complete Autopilot state with a clean review verdict.

## Non-goals
- No autonomous real order submission.
- No Gist upload.
- No Hermes/Weixin send.

## Acceptance criteria
- origin/main contains local commits after push.
- skill_check.py and Longbridge read-only checks pass.
- Safe runtime is either running and verified or explicitly skipped with reason.
- Autopilot state is complete.
- Real order verification is documented as not executed and why.
