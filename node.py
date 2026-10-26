from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from threading import Lock
import hashlib
import json
import os
import re
import tempfile

app = FastAPI(title="Campus Offline Node - Member 2")

NODE_ID = os.getenv("NODE_ID", "NODE")
BASE = Path(os.getenv("NODE_STORAGE", f"./storage_{NODE_ID}")).resolve()
BASE.mkdir(parents=True, exist_ok=True)
REGISTRY_FILE = BASE / "_node_registry.json"
ONLINE = True
METADATA = {}
PEERS = {}
LOCK = Lock()
RESOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_resource_id(resource_id: str) -> bool:
    return bool(RESOURCE_ID_PATTERN.fullmatch(resource_id)) and resource_id not in {".", ".."}


def load_metadata():
    for path in BASE.iterdir():
        if not path.is_file() or path.name == REGISTRY_FILE.name or path.name.startswith("."):
            continue
        try:
            METADATA[path.name] = {
                "filename": path.name,
                "sha256": file_hash(path),
                "size": path.stat().st_size,
            }
        except OSError:
            continue


def load_registry():
    global PEERS
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        PEERS = {k: v for k, v in data.items() if isinstance(v, dict) and "url" in v}
    except (OSError, json.JSONDecodeError):
        PEERS = {}


def save_registry():
    REGISTRY_FILE.write_text(json.dumps(PEERS, indent=2), encoding="utf-8")


load_metadata()
load_registry()


@app.get("/status")
def status():
    return {
        "node_id": NODE_ID,
        "online": ONLINE,
        "resources": sorted(METADATA.keys()),
        "free_storage_mb": 1024,
        "registered_peers": sorted(PEERS.keys()),
    }


@app.post("/availability")
def availability(online: bool):
    global ONLINE
    ONLINE = online
    return {"node_id": NODE_ID, "online": ONLINE}


@app.get("/has/{resource_id}")
def has_resource(resource_id: str):
    if not valid_resource_id(resource_id):
        raise HTTPException(status_code=400, detail="Invalid resource ID")
    return {
        "node_id": NODE_ID,
        "has": resource_id in METADATA and (BASE / resource_id).is_file(),
        "online": ONLINE,
        "sha256": METADATA.get(resource_id, {}).get("sha256"),
    }


@app.get("/peers")
def list_peers():
    return {"node_id": NODE_ID, "peers": PEERS}


@app.post("/register")
def register_peer(peer_id: str, url: str):
    peer_id = peer_id.strip()
    url = url.strip().rstrip("/")
    if not peer_id or peer_id == NODE_ID:
        raise HTTPException(status_code=400, detail="Invalid peer ID")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Peer URL must use HTTP or HTTPS")
    with LOCK:
        PEERS[peer_id] = {"url": url}
        save_registry()
    return {"node_id": NODE_ID, "registered_peer": peer_id, "url": url}


@app.delete("/register/{peer_id}")
def unregister_peer(peer_id: str):
    with LOCK:
        if peer_id not in PEERS:
            raise HTTPException(status_code=404, detail="Peer not registered")
        del PEERS[peer_id]
        save_registry()
    return {"node_id": NODE_ID, "removed_peer": peer_id}


@app.post("/resource/{resource_id}")
async def receive_resource(resource_id: str, upload: UploadFile = File(...)):
    if not ONLINE:
        raise HTTPException(status_code=503, detail="Node is offline")
    if not valid_resource_id(resource_id):
        raise HTTPException(status_code=400, detail="Invalid resource ID")

    data = await upload.read()
    digest = hashlib.sha256(data).hexdigest()
    target = BASE / resource_id

    try:
        with LOCK:
            if target.exists():
                existing_digest = file_hash(target)
                if existing_digest == digest:
                    METADATA[resource_id] = {
                        "filename": upload.filename or resource_id,
                        "sha256": digest,
                        "size": target.stat().st_size,
                    }
                    return {
                        "node_id": NODE_ID,
                        "resource_id": resource_id,
                        "sha256": digest,
                        "size": len(data),
                        "status": "duplicate_unchanged",
                    }
                raise HTTPException(
                    status_code=409,
                    detail="Resource ID already exists with different content",
                )

            # Write to a temporary file first, then atomically rename into place.
            fd, temp_name = tempfile.mkstemp(prefix=".upload_", dir=str(BASE))
            try:
                with os.fdopen(fd, "wb") as temp_file:
                    temp_file.write(data)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())
                Path(temp_name).replace(target)
            except Exception:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    pass
                raise

            METADATA[resource_id] = {
                "filename": upload.filename or resource_id,
                "sha256": digest,
                "size": len(data),
            }

        return {
            "node_id": NODE_ID,
            "resource_id": resource_id,
            "sha256": digest,
            "size": len(data),
            "status": "stored",
        }
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not store resource: {exc}") from exc
    finally:
        await upload.close()


@app.get("/resource/{resource_id}")
def download_resource(resource_id: str):
    if not ONLINE:
        raise HTTPException(status_code=503, detail="Node is offline")
    if not valid_resource_id(resource_id):
        raise HTTPException(status_code=400, detail="Invalid resource ID")
    target = BASE / resource_id
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Resource not found")
    expected = METADATA.get(resource_id, {}).get("sha256")
    actual = file_hash(target)
    if expected and actual != expected:
        raise HTTPException(status_code=500, detail="Stored resource failed integrity check")
    return FileResponse(target, filename=target.name, headers={"X-Content-SHA256": actual})
