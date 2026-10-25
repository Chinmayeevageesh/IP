from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import hashlib
import os
import re

app = FastAPI(title="Campus Offline Node")

BASE = Path(os.getenv("NODE_STORAGE", "./storage")).resolve()
BASE.mkdir(parents=True, exist_ok=True)

NODE_ID = os.getenv("NODE_ID", "NODE")
ONLINE = True
METADATA = {}

# Resource IDs: letters, numbers, underscores and hyphens only.
RESOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def validate_resource_id(resource_id: str) -> Path:
    """Validate resource ID and return its safe storage path."""
    if not RESOURCE_ID_PATTERN.fullmatch(resource_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid resource ID"
        )

    target = (BASE / resource_id).resolve()

    # Defense-in-depth: ensure the target stays directly inside BASE.
    if target.parent != BASE:
        raise HTTPException(
            status_code=400,
            detail="Invalid resource path"
        )

    return target


@app.get("/status")
def status():
    return {
        "node_id": NODE_ID,
        "online": ONLINE,
        "resources": list(METADATA.keys()),
        "free_storage_mb": 1024
    }


@app.post("/availability")
def availability(online: bool):
    global ONLINE
    ONLINE = online

    return {
        "node_id": NODE_ID,
        "online": ONLINE
    }


@app.get("/has/{resource_id}")
def has_resource(resource_id: str):
    validate_resource_id(resource_id)

    return {
        "node_id": NODE_ID,
        "has": resource_id in METADATA,
        "online": ONLINE
    }


@app.post("/resource/{resource_id}")
async def receive_resource(
    resource_id: str,
    upload: UploadFile = File(...)
):
    if not ONLINE:
        raise HTTPException(
            status_code=503,
            detail="Node is offline"
        )

    target = validate_resource_id(resource_id)

    data = await upload.read()
    digest = hashlib.sha256(data).hexdigest()

    try:
        target.write_bytes(data)
    except OSError:
        raise HTTPException(
            status_code=500,
            detail="Could not store resource"
        )

    METADATA[resource_id] = {
        "filename": upload.filename,
        "sha256": digest,
        "size": len(data)
    }

    return {
        "node_id": NODE_ID,
        "resource_id": resource_id,
        "sha256": digest,
        "size": len(data)
    }


@app.get("/resource/{resource_id}")
def download_resource(resource_id: str):
    if not ONLINE:
        raise HTTPException(
            status_code=503,
            detail="Node is offline"
        )

    target = validate_resource_id(resource_id)

    if resource_id not in METADATA or not target.is_file():
        raise HTTPException(
            status_code=404,
            detail="Resource not found"
        )

    return FileResponse(target)
