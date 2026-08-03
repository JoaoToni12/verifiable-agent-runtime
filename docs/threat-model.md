# Threat model

## Assets

- Integrity of tool policy and runtime mode.
- Binding between an approval and its proposed payload.
- Uniqueness of side effects under retries.
- Integrity and availability of the action ledger.

## Trust boundaries

The agent proposal is untrusted. The API validates it before policy evaluation.
The policy engine is deterministic and does not consume model output. Approval
is trusted only for the exact SHA-256 payload digest submitted by the reviewer.
The synthetic executor has no external credentials.

## Covered threats

| Threat | Control |
|---|---|
| Agent invokes an unknown tool | Fail-closed policy maps it to critical and denies |
| Payload changes after review | Approval must match the stored canonical payload hash |
| Retry creates a duplicate action | Unique idempotency key returns the original action |
| Autonomous execution is unsafe | Shadow is the default mode; off is a kill switch |
| Ledger row is modified | Per-action hash chain fails verification |
| Container privilege escalation | Non-root user, read-only root filesystem, dropped capabilities |

## Not covered in v0.1

- User authentication and approver authorization.
- Confidentiality of stored payloads.
- A malicious database administrator replacing the database and all hashes.
- Distributed locking and multi-region availability.
- Real tool execution, compensation, or rollback.
- Denial-of-service protection.

## Production extensions

Export signed event digests to an independently controlled store, use a
transactional shared database, authenticate workload and approver identities,
encrypt sensitive payloads, and enforce destination-specific tool scopes.
