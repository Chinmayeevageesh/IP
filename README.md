# Offline-First Campus Resource Network — 5-Day MVP

This is a proof-of-concept for a CIE/utility-patent study.

IMPORTANT:
- This prototype demonstrates the technical workflow; it does NOT establish patentability.
- It uses localhost ports to simulate separate campus devices. The same API can later be moved to laptops on a local Wi-Fi network.
- The current prototype intentionally does not claim that quorum-based replica recovery is novel. Prior-art research is required before drafting a patent claim.

## What the MVP demonstrates

1. A resource is introduced with:
   - priority
   - required quorum
   - version
   - SHA-256 hash
2. Devices can hold replicas.
3. The controller calculates the number of currently available holders.
4. A holder can be marked OFFLINE.
5. If available holders fall below the required quorum, recovery is triggered.
6. The controller selects an eligible online device that does not already hold the resource.
7. The file is transferred to that device.
8. Holder count is recalculated.
9. Replication stops when the target quorum is reached.

## Run

Create a sample PDF/file:

    python -c "from pathlib import Path; Path('sample_assignment.pdf').write_bytes(b'DEMO ACADEMIC FILE')"

Start four simulated nodes in four terminals:

    uvicorn node:app --port 8001
    uvicorn node:app --port 8002
    uvicorn node:app --port 8003
    uvicorn node:app --port 8004

Then run the controller:

    python controller.py

The controller will:
- register nodes
- upload a resource
- replicate it to nodes 2 and 3
- simulate node 3 going offline
- detect quorum deficit
- recover a replica to node 4
- print the final state

## Moving from simulation to real local Wi-Fi

Replace localhost URLs such as http://127.0.0.1:8002 with the actual LAN IP of another laptop, for example:

    http://192.168.1.24:8002

All devices must be on the same local Wi-Fi/hotspot and have the chosen port reachable.

## Suggested demo

Required quorum = 3

A = original
B = replica
C = replica

A+B+C -> QUORUM SATISFIED

C goes offline

A+B -> QUORUM DEFICIT

D is selected

A+B+D -> QUORUM RESTORED
