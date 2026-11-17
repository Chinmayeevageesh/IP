import hashlib
import mimetypes
from pathlib import Path
import requests
import time
import os

from network_config import NODES

RESOURCE_ID = os.getenv("RESOURCE_ID", "assignment2")
FILE = Path(os.getenv("RESOURCE_FILE", "sample_assignment.pdf"))
REQUIRED_QUORUM = 3

def node_status(node_id):
    try:
        r = requests.get(f"{NODES[node_id]}/status", timeout=1)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {"node_id": node_id, "online": False, "resources": []}

def holders(resource_id=RESOURCE_ID, expected_hash=None):
    result = []

    if expected_hash is None:
        if resource_id != RESOURCE_ID:
            return result
        expected_hash = hashlib.sha256(FILE.read_bytes()).hexdigest()

    for node_id in NODES:
        s = node_status(node_id)

        if not s.get("online"):
            continue

        if resource_id not in s.get("resources", []):
            continue

        try:
            r = requests.get(
                f"{NODES[node_id]}/resource/{resource_id}",
                timeout=3
            )
            r.raise_for_status()

            actual_hash = hashlib.sha256(r.content).hexdigest()

            if actual_hash == expected_hash:
                result.append(node_id)
            else:
                print(f"WARNING: Hash mismatch on Node {node_id}")

        except requests.RequestException:
            print(f"WARNING: Could not verify Node {node_id}")

    return result

def send_file(target_id):
    with FILE.open("rb") as f:
        r = requests.post(
            f"{NODES[target_id]}/resource/{RESOURCE_ID}",
            files={"upload": (FILE.name, f, "application/pdf")},
            timeout=5,
        )
    r.raise_for_status()
    return r.json()


def replicate_from_node(source_id, target_id, resource_id, expected_hash):
    source_response = requests.get(
        f"{NODES[source_id]}/resource/{resource_id}",
        timeout=3,
    )
    source_response.raise_for_status()
    content = source_response.content
    actual_hash = hashlib.sha256(content).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(f"Source node {source_id} failed SHA-256 verification")

    filename = resource_id
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    response = requests.post(
        f"{NODES[target_id]}/resource/{resource_id}",
        files={"upload": (filename, content, content_type)},
        timeout=5,
    )
    response.raise_for_status()

    verification = requests.get(
        f"{NODES[target_id]}/resource/{resource_id}",
        timeout=3,
    )
    verification.raise_for_status()
    verified_hash = hashlib.sha256(verification.content).hexdigest()
    if verified_hash != expected_hash:
        raise ValueError(f"Target node {target_id} failed SHA-256 verification")
    return response.json()


def show_state(label):
    hs = holders()
    print(f"\n=== {label} ===")
    print("Required quorum:", REQUIRED_QUORUM)
    print("Available holders:", hs)
    print("Count:", len(hs))
    print("Status:", "QUORUM SATISFIED" if len(hs) >= REQUIRED_QUORUM else "QUORUM DEFICIT")
    return hs

def main():
    if not FILE.exists():
        FILE.write_bytes(b"DEMO ACADEMIC FILE")

    digest = hashlib.sha256(FILE.read_bytes()).hexdigest()
    print("Resource:", FILE.name)
    print("SHA-256:", digest)

    try:
        # Ensure C starts online
        requests.post(
            f"{NODES['C']}/availability",
            params={"online": True},
            timeout=3
        ).raise_for_status()

        # Original and initial replicas
        send_file("A")
        send_file("B")
        send_file("C")

        show_state("INITIAL")

        # Simulate C disappearing
        requests.post(
            f"{NODES['C']}/availability",
            params={"online": False},
            timeout=3
        ).raise_for_status()

        show_state("AFTER C DISCONNECTS")

        # Selective recovery
        current = holders()
        deficit = REQUIRED_QUORUM - len(current)

        if deficit > 0:
            for candidate in NODES:
                if candidate in current:
                    continue

                s = node_status(candidate)

                if s.get("online") and RESOURCE_ID not in s.get("resources", []):
                    print(
                        f"\nQUORUM DEFICIT DETECTED "
                        f"-> replication target: {candidate}"
                    )

                    send_file(candidate)
                    deficit -= 1

                    if deficit <= 0:
                        break

        final_holders = show_state("AFTER SELECTIVE RECOVERY")

        if len(final_holders) >= REQUIRED_QUORUM:
            print("\nDEMO RESULT: QUORUM RESTORED")
        else:
            print("\nDEMO RESULT: QUORUM NOT RESTORED")

    except requests.RequestException as e:
        print(f"\nDEMO ERROR: Network/request failure: {e}")

    except Exception as e:
        print(f"\nDEMO ERROR: {type(e).__name__}: {e}")

    finally:
        # Restore C after the experiment
        try:
            r = requests.post(
                f"{NODES['C']}/availability",
                params={"online": True},
                timeout=3
            )
            r.raise_for_status()
            print("\nNode C restored online.")
        except requests.RequestException as e:
            print(f"\nWARNING: Could not restore Node C: {e}")

        print("\nDEMO FINISHED")

if __name__ == "__main__":
    main()
