from fastapi import FastAPI, UploadFile, File, HTTPException
from pathlib import Path
import hashlib
import os

app = FastAPI(title="Campus Offline Node")

BASE = Path(os.getenv("NODE_STORAGE", "./storage"))
BASE.mkdir(parents=True, exist_ok=True)

NODE_ID = os.getenv("NODE_ID", "NODE")
ONLINE = True
METADATA = {}

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
    return {"node_id": NODE_ID, "online": ONLINE}

@app.get("/has/{resource_id}")
def has_resource(resource_id: str):
    return {
        "node_id": NODE_ID,
        "has": resource_id in METADATA,
        "online": ONLINE
    }

@app.post("/resource/{resource_id}")
async def receive_resource(resource_id: str, upload: UploadFile = File(...)):
    if not ONLINE:
        raise HTTPException(status_code=503, detail="Node is offline")

    data = await upload.read()
    digest = hashlib.sha256(data).hexdigest()

    target = BASE / resource_id
    target.write_bytes(data)

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
    from fastapi.responses import FileResponse
    if not ONLINE:
        raise HTTPException(status_code=503, detail="Node is offline")

    target = BASE / resource_id
    if not target.exists():
        raise HTTPException(status_code=404, detail="Resource not found")

    return FileResponse(target)
