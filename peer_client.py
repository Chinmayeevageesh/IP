"""
Member 2 helper client:
- peer registration
- upload with retry and fallback to alternate nodes
- download with SHA-256 verification
- independent testable functions

Run examples from the project directory:
  python peer_client.py register-all
  python peer_client.py distribute sample_assignment.pdf assignment2 A
  python peer_client.py download assignment2 B downloaded_assignment.bin
"""
import argparse
import hashlib
import time
from pathlib import Path
import requests

NODES = {
    "A": "http://127.0.0.1:8001",
    "B": "http://127.0.0.1:8002",
    "C": "http://127.0.0.1:8003",
    "D": "http://127.0.0.1:8004",
}
TIMEOUT = (2, 8)
MAX_ATTEMPTS_PER_NODE = 2


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def register_all():
    for node_id, base_url in NODES.items():
        for peer_id, peer_url in NODES.items():
            if peer_id == node_id:
                continue
            try:
                response = requests.post(
                    f"{base_url}/register",
                    params={"peer_id": peer_id, "url": peer_url},
                    timeout=TIMEOUT,
                )
                response.raise_for_status()
                print(f"{node_id}: registered peer {peer_id}")
            except requests.RequestException as exc:
                print(f"{node_id}: registration of {peer_id} failed: {exc}")


def transfer_to_node(file_path: Path, resource_id: str, node_id: str) -> dict:
    data = file_path.read_bytes()
    expected = sha256_bytes(data)
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS_PER_NODE + 1):
        try:
            with file_path.open("rb") as stream:
                response = requests.post(
                    f"{NODES[node_id]}/resource/{resource_id}",
                    files={"upload": (file_path.name, stream, "application/octet-stream")},
                    timeout=TIMEOUT,
                )

            if response.status_code == 409:
                raise RuntimeError(
                    f"Resource ID conflict at node {node_id}; refusing to overwrite different content"
                )
            response.raise_for_status()
            result = response.json()

            if result.get("sha256") != expected:
                raise RuntimeError(f"SHA-256 mismatch in upload response from node {node_id}")

            # Verify by downloading the resource from the target node.
            check = requests.get(f"{NODES[node_id]}/resource/{resource_id}", timeout=TIMEOUT)
            check.raise_for_status()
            actual = sha256_bytes(check.content)
            if actual != expected:
                raise RuntimeError(f"Downloaded copy from node {node_id} failed SHA-256 verification")

            return {
                "node_id": node_id,
                "status": result.get("status", "stored"),
                "sha256": actual,
                "verified": True,
            }
        except (requests.RequestException, RuntimeError) as exc:
            last_error = exc
            print(f"{node_id}: attempt {attempt}/{MAX_ATTEMPTS_PER_NODE} failed: {exc}")
            if attempt < MAX_ATTEMPTS_PER_NODE:
                time.sleep(0.5 * attempt)

    raise RuntimeError(f"Transfer to node {node_id} failed after retries: {last_error}")


def distribute(file_path: Path, resource_id: str, preferred_node: str):
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    order = [preferred_node] + [n for n in NODES if n != preferred_node]
    failures = []
    for node_id in order:
        try:
            result = transfer_to_node(file_path, resource_id, node_id)
            print(f"SUCCESS: {result}")
            return result
        except Exception as exc:
            failures.append(f"{node_id}: {exc}")
            print(f"Fallback: trying another node after {node_id} failed.")
    raise RuntimeError("All node transfers failed:\n" + "\n".join(failures))


def download_verified(resource_id: str, node_id: str, destination: Path):
    response = requests.get(f"{NODES[node_id]}/resource/{resource_id}", timeout=TIMEOUT)
    response.raise_for_status()
    data = response.content
    header_hash = response.headers.get("X-Content-SHA256")
    actual_hash = sha256_bytes(data)
    if header_hash and header_hash.lower() != actual_hash:
        raise RuntimeError("Download failed SHA-256 verification")
    destination.write_bytes(data)
    print(f"Downloaded {len(data)} bytes from {node_id}")
    print(f"SHA-256: {actual_hash}")
    print(f"Saved to: {destination.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Offline Campus Member 2 peer client")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("register-all")

    dist = sub.add_parser("distribute")
    dist.add_argument("file", type=Path)
    dist.add_argument("resource_id")
    dist.add_argument("preferred_node", choices=NODES.keys())

    down = sub.add_parser("download")
    down.add_argument("resource_id")
    down.add_argument("node_id", choices=NODES.keys())
    down.add_argument("destination", type=Path)

    args = parser.parse_args()
    if args.command == "register-all":
        register_all()
    elif args.command == "distribute":
        distribute(args.file, args.resource_id, args.preferred_node)
    elif args.command == "download":
        download_verified(args.resource_id, args.node_id, args.destination)


if __name__ == "__main__":
    main()
