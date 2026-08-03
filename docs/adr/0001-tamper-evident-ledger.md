# ADR-0001: Use a per-action hash chain

- Status: accepted
- Date: 2026-08-03

## Context

An append-only table is useful operationally but does not reveal a later direct
database edit. The demo needs a compact integrity mechanism that remains easy
to inspect and test.

## Decision

Each event stores the previous event hash for that action. The new hash covers
the action identifier, timestamp, event type, canonical event data, and previous
hash. The first event uses 64 zeroes as its previous hash.

## Consequences

- Editing or reordering an event breaks verification from that point onward.
- Independent actions can be verified separately.
- The chain is tamper-evident, not tamper-proof. An administrator who can replace
  the entire database can recompute every hash.
- A production design should periodically sign or export roots to a separately
  controlled audit system.
