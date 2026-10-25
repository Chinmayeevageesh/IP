# Patent research notes — do not treat as a patent filing

## Current product concept
Offline-First Campus Academic Resource Network.

## Broad concept that is NOT safe to claim as novel
Offline mesh communication + distributed file replication + quorum-based recovery.

Prior-art examples found during the initial search include:
- US7500020B1: coherency of replicas for a distributed file sharing system; discusses quorum thresholds and creating new replicas after failures.
- US7822711B1: conflict resolution in distributed file sharing; discusses creating replacement replicas after node failure.
- US20180165343A1: quorum-based replication of data records.
- US10521403: fault-tolerant file replication with predetermined quorum.
- 2026 SSRN paper: resilient offline-first campus mesh network feasibility study.

## Direction for further invention work
Keep the campus/offline setting as the application context, but identify a specific technical mechanism that is not simply:
- "use a mesh"
- "copy files to peers"
- "maintain N replicas"
- "detect quorum loss"
- "create a replacement replica"

Potential research dimensions:
- resource-specific availability policies
- disconnected-device state uncertainty
- version-integrity handling during recovery
- constrained local resources
- trust/authentication of academic resources
- topology-aware recovery
- conflict-free recovery after an offline node returns

Any final patent claim must be checked against current prior art by a patent professional.
