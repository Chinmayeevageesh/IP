# Demo scenarios

## Scenario 1 — Normal state
A, B, C hold `Assignment 2.pdf`.
Required quorum = 3.
Expected: QUORUM SATISFIED.

## Scenario 2 — Replica disappears
Mark C offline.
Expected: QUORUM DEFICIT.

## Scenario 3 — Selective recovery
D is online and does not hold the file.
Expected: only the missing replica is transferred to D.

## Scenario 4 — Recovery complete
A, B, D are available.
Expected: QUORUM RESTORED and replication stops.

## What to show the professor
Do not say "this proves the patent is novel."
Say:
"This prototype demonstrates the proposed technical workflow. We are separately conducting prior-art analysis to determine which specific mechanism, if any, can support a patent claim."
