# Shutdown Request

All tasks are complete. Please wrap up any remaining work and respond with a shutdown acknowledgement.

## Shutdown Ack Protocol
1. Write your decision to:
   `<team_state_root>/team/qqq-options-trading-system-fin/workers/worker-3/shutdown-ack.json`
2. Format:
   - Accept:
     `{"status":"accept","reason":"ok","updated_at":"<iso>"}`
   - Reject:
     `{"status":"reject","reason":"still working","updated_at":"<iso>"}`
3. After writing the ack, exit your Codex session.

Type `exit` or press Ctrl+C to end your Codex session.
