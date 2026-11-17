import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from threading import Lock
from urllib.parse import quote

import requests
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from controller import (
    FILE,
    NODES,
    RESOURCE_ID,
    REQUIRED_QUORUM,
    holders,
    node_status,
    replicate_from_node,
)
from quorum_recovery import calculate_quorum, select_recovery_devices


app = FastAPI(title="Campus Resource Network - Admin API")
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
ADMIN_DATA_DIR = Path(
    os.getenv("CAMPUS_ADMIN_DATA_DIR", "./storage_admin")
).resolve()
RESOURCE_REGISTRY = ADMIN_DATA_DIR / "resources.json"
EXPECTED_VERSION = 1
MAX_FILE_SIZE = 10 * 1024 * 1024
RESOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
REGISTRY_LOCK = Lock()

app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIR),
    name="static",
)
app.mount(
    "/portal",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="portal",
)


def valid_resource_id(resource_id):
    return bool(RESOURCE_ID_PATTERN.fullmatch(resource_id)) and resource_id not in {
        ".",
        "..",
    }


def read_resource_registry():
    if not RESOURCE_REGISTRY.exists():
        return {}
    try:
        registry = json.loads(RESOURCE_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read the resource registry: {error}",
        ) from error
    if not isinstance(registry, dict):
        raise HTTPException(
            status_code=500,
            detail="The resource registry has an invalid format.",
        )
    return registry


def save_resource_metadata(resource_id, filename, digest):
    with REGISTRY_LOCK:
        registry = read_resource_registry()
        existing = registry.get(resource_id)
        if existing and existing.get("sha256") != digest:
            raise HTTPException(
                status_code=409,
                detail="Resource ID already exists with different content.",
            )
        registry[resource_id] = {
            "filename": filename,
            "sha256": digest,
        }
        ADMIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=ADMIN_DATA_DIR,
                prefix=".resources_",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                json.dump(registry, temp_file, indent=2)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            temp_path.replace(RESOURCE_REGISTRY)
        except OSError as error:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=500,
                detail=f"Could not save resource metadata: {error}",
            ) from error


def get_verified_holders():
    try:
        record = read_resource_registry().get(RESOURCE_ID)
        if record:
            return holders(RESOURCE_ID, record["sha256"])
        return holders()
    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not verify resource holders: {error}",
        ) from error


def get_node_details():
    result = []

    for node_id in NODES:
        status = node_status(node_id)
        online = status.get("online", False)
        result.append(
            {
                "node_id": node_id,
                "online": online,
                "version": status.get("version", "N/A"),
                "resources": status.get("resources", []),
                "reachable": online,
            }
        )

    return result


def get_quorum_details():
    verified_holders = get_verified_holders()
    quorum = calculate_quorum(REQUIRED_QUORUM, verified_holders)

    return {
        "resource_id": RESOURCE_ID,
        "verified_holders": verified_holders,
        **quorum,
    }


@app.get("/")
def home():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(FRONTEND_DIR / "network-status.html")


@app.get("/api/portal/health")
def portal_health():
    return {"status": "running"}


@app.get("/api/health")
def health():
    return {"status": "running"}


@app.get("/api/nodes")
def get_nodes():
    return get_node_details()


@app.get("/api/quorum")
def get_quorum():
    return get_quorum_details()


@app.get("/api/overview")
def get_overview():
    nodes = get_node_details()
    quorum = get_quorum_details()

    return {
        "nodes": nodes,
        "quorum": quorum,
        "online_nodes": sum(1 for node in nodes if node["online"]),
        "offline_nodes": sum(1 for node in nodes if not node["online"]),
    }


@app.get("/api/resources")
def list_resources():
    registry = read_resource_registry()
    discovered = {}
    nodes = get_node_details()

    for node in nodes:
        if not node["online"]:
            continue
        for resource_id in node["resources"]:
            if valid_resource_id(resource_id):
                discovered.setdefault(resource_id, []).append(node["node_id"])

    resources = []
    for resource_id, listed_holders in sorted(discovered.items()):
        record = registry.get(resource_id, {})
        expected_hash = record.get("sha256")
        verified_holders = []
        discovered_hash = expected_hash
        for node_id in listed_holders:
            try:
                response = requests.get(
                    f"{NODES[node_id]}/resource/{resource_id}",
                    timeout=3,
                )
                response.raise_for_status()
            except requests.RequestException:
                continue
            actual_hash = hashlib.sha256(response.content).hexdigest()
            if discovered_hash is None:
                discovered_hash = actual_hash
            if actual_hash == discovered_hash:
                verified_holders.append(node_id)

        resources.append(
            {
                "resource_id": resource_id,
                "filename": record.get("filename", resource_id),
                "sha256": discovered_hash,
                "holders": listed_holders,
                "verified_holders": verified_holders,
                "replica_count": len(verified_holders),
                "required_quorum": REQUIRED_QUORUM,
                "quorum_satisfied": len(verified_holders) >= REQUIRED_QUORUM,
            }
        )

    return {"resources": resources, "nodes": nodes}


@app.post("/api/resources/{resource_id}")
async def upload_resource(resource_id: str, upload: UploadFile = File(...)):
    if not valid_resource_id(resource_id):
        raise HTTPException(status_code=400, detail="Invalid resource ID")

    try:
        content = await upload.read(MAX_FILE_SIZE + 1)
        if not content:
            raise HTTPException(
                status_code=400,
                detail="Empty files are not allowed.",
            )
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="File exceeds maximum size of 10 MB.",
            )

        digest = hashlib.sha256(content).hexdigest()
        filename = upload.filename or resource_id
        record = read_resource_registry().get(resource_id)
        if record and record.get("sha256") != digest:
            raise HTTPException(
                status_code=409,
                detail="Resource ID already exists with different content.",
            )

        verified_nodes = []
        failed_nodes = {}
        upload_statuses = []
        for node_id, base_url in NODES.items():
            if len(verified_nodes) >= REQUIRED_QUORUM:
                break
            status = node_status(node_id)
            if not status.get("online"):
                failed_nodes[node_id] = "Node is offline or unreachable."
                continue
            try:
                response = requests.post(
                    f"{base_url}/resource/{resource_id}",
                    files={
                        "upload": (
                            filename,
                            content,
                            upload.content_type or "application/octet-stream",
                        )
                    },
                    timeout=10,
                )
                response.raise_for_status()
                result = response.json()
                if result.get("sha256") != digest:
                    raise ValueError("Node upload response SHA-256 did not match.")

                verification = requests.get(
                    f"{base_url}/resource/{resource_id}",
                    timeout=5,
                )
                verification.raise_for_status()
                if hashlib.sha256(verification.content).hexdigest() != digest:
                    raise ValueError("Stored replica failed SHA-256 verification.")

                verified_nodes.append(node_id)
                upload_statuses.append(result.get("status", "stored"))
            except (requests.RequestException, ValueError) as error:
                failed_nodes[node_id] = str(error)

        if verified_nodes:
            save_resource_metadata(resource_id, filename, digest)

        if len(verified_nodes) < REQUIRED_QUORUM:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Upload did not reach the required verified replica quorum.",
                    "required_quorum": REQUIRED_QUORUM,
                    "verified_replica_count": len(verified_nodes),
                    "verified_nodes": verified_nodes,
                    "failed_nodes": failed_nodes,
                    "sha256": digest,
                },
            )

        return {
            "resource_id": resource_id,
            "filename": filename,
            "sha256": digest,
            "required_quorum": REQUIRED_QUORUM,
            "verified_replica_count": len(verified_nodes),
            "verified_nodes": verified_nodes,
            "failed_nodes": failed_nodes,
            "status": (
                "duplicate_unchanged"
                if all(status == "duplicate_unchanged" for status in upload_statuses)
                else "stored"
            ),
        }
    finally:
        await upload.close()


@app.get("/api/resources/{resource_id}")
def download_resource(resource_id: str):
    if not valid_resource_id(resource_id):
        raise HTTPException(status_code=400, detail="Invalid resource ID")

    record = read_resource_registry().get(resource_id, {})
    expected_hash = record.get("sha256")
    filename = record.get("filename", resource_id)
    found_copy = False

    for node_id, base_url in NODES.items():
        status = node_status(node_id)
        if not status.get("online") or resource_id not in status.get("resources", []):
            continue
        found_copy = True
        try:
            response = requests.get(
                f"{base_url}/resource/{resource_id}",
                timeout=5,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue
        digest = hashlib.sha256(response.content).hexdigest()
        if expected_hash is None:
            expected_hash = digest
        if digest != expected_hash:
            continue
        return Response(
            content=response.content,
            media_type=response.headers.get(
                "content-type", "application/octet-stream"
            ),
            headers={
                "X-Content-SHA256": digest,
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
                ),
            },
        )

    if found_copy:
        raise HTTPException(
            status_code=500,
            detail="No online copy passed SHA-256 integrity verification.",
        )
    raise HTTPException(status_code=404, detail="Resource not found.")


@app.post("/api/recovery")
def perform_recovery(resource_id: str = RESOURCE_ID):
    if not valid_resource_id(resource_id):
        raise HTTPException(status_code=400, detail="Invalid resource ID")

    record = read_resource_registry().get(resource_id)
    if record:
        expected_hash = record["sha256"]
        current_holders = holders(resource_id, expected_hash)
    elif resource_id == RESOURCE_ID:
        expected_hash = hashlib.sha256(FILE.read_bytes()).hexdigest()
        current_holders = holders()
    else:
        raise HTTPException(
            status_code=404,
            detail="Resource has no registered SHA-256 metadata.",
        )
    quorum_before = calculate_quorum(REQUIRED_QUORUM, current_holders)

    if quorum_before["deficit"] == 0:
        return {
            "message": "Quorum is already satisfied. Recovery not required.",
            "before": quorum_before,
            "selection": {"selected_devices": []},
            "successful_transfers": [],
            "failed_transfers": {},
            "after": quorum_before,
        }

    eligible_devices = []

    for node_id in NODES:
        if node_id in current_holders:
            continue

        status = node_status(node_id)
        if status.get("online") and resource_id not in status.get("resources", []):
            eligible_devices.append(node_id)

    selection = select_recovery_devices(
        REQUIRED_QUORUM,
        current_holders,
        eligible_devices,
        node_urls=NODES,
        expected_version=EXPECTED_VERSION,
    )

    if not current_holders:
        raise HTTPException(
            status_code=503,
            detail="No online SHA-256 verified source replica is available.",
        )

    attempted_transfers = []
    failed_transfers = {}
    for node_id in selection["selected_devices"]:
        try:
            replicate_from_node(
                current_holders[0],
                node_id,
                resource_id,
                expected_hash,
            )
            attempted_transfers.append(node_id)
        except Exception as error:
            failed_transfers[node_id] = str(error)

    final_holders = holders(resource_id, expected_hash)
    quorum_after = calculate_quorum(REQUIRED_QUORUM, final_holders)
    successful_transfers = [
        node_id for node_id in attempted_transfers if node_id in final_holders
    ]

    for node_id in attempted_transfers:
        if node_id not in final_holders:
            failed_transfers[node_id] = (
                "Replica was not present among SHA-256 verified holders after transfer."
            )

    return {
        "message": (
            "QUORUM RESTORED"
            if quorum_after["deficit"] == 0
            else "QUORUM NOT RESTORED"
        ),
        "before": quorum_before,
        "selection": selection,
        "successful_transfers": successful_transfers,
        "failed_transfers": failed_transfers,
        "after": quorum_after,
    }
