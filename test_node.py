import hashlib
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
import node


def test_upload_and_duplicate():
    client = TestClient(node.app)
    resource_id = "pytest_resource"
    payload = b"academic resource test"
    target = node.BASE / resource_id
    target.unlink(missing_ok=True)
    node.METADATA.pop(resource_id, None)

    first = client.post(
        f"/resource/{resource_id}",
        files={"upload": ("test.txt", payload, "text/plain")},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "stored"
    assert first.json()["sha256"] == hashlib.sha256(payload).hexdigest()

    second = client.post(
        f"/resource/{resource_id}",
        files={"upload": ("test.txt", payload, "text/plain")},
    )
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate_unchanged"

    conflict = client.post(
        f"/resource/{resource_id}",
        files={"upload": ("different.txt", b"different", "text/plain")},
    )
    assert conflict.status_code == 409

    target.unlink(missing_ok=True)
    node.METADATA.pop(resource_id, None)


def test_offline_rejects_upload_and_restore():
    client = TestClient(node.app)
    node.ONLINE = False
    try:
        response = client.post(
            "/resource/offline_pytest",
            files={"upload": ("test.txt", b"content", "text/plain")},
        )
        assert response.status_code == 503
    finally:
        node.ONLINE = True
