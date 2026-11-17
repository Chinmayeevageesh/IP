import hashlib
import json

import requests
from fastapi.testclient import TestClient

import admin_api
import quorum_recovery


client = TestClient(admin_api.app)


def test_admin_dashboard_and_health_routes():
    dashboard = client.get("/dashboard")
    student_home = client.get("/")
    student_portal = client.get("/portal/upload.html")

    assert dashboard.status_code == 200
    assert "Admin Dashboard" in dashboard.text
    assert 'href="/static/css/sb-admin-2.min.css"' in dashboard.text
    assert 'fetch(endpoint, options)' in dashboard.text
    assert "127.0.0.1:8010" not in dashboard.text
    assert student_home.status_code == 200
    assert "Student Dashboard" in student_home.text
    assert student_portal.status_code == 200
    assert "Upload Academic Resource" in student_portal.text
    assert client.get("/api/health").json() == {"status": "running"}


def test_dashboard_stylesheet_and_font_assets_are_served():
    stylesheet = client.get("/static/css/sb-admin-2.min.css")
    icons = client.get("/static/vendor/fontawesome-free/css/all.min.css")
    font = client.get(
        "/static/vendor/fontawesome-free/webfonts/fa-solid-900.woff2"
    )

    assert stylesheet.status_code == 200
    assert icons.status_code == 200
    assert font.status_code == 200
    assert font.content


def test_nodes_quorum_and_overview_match_dashboard_contract(monkeypatch):
    def fake_node_status(node_id):
        return {
            "node_id": node_id,
            "online": node_id != "C",
            "version": 1,
            "resources": ["assignment2"] if node_id in ("A", "B") else [],
        }

    monkeypatch.setattr(admin_api, "node_status", fake_node_status)
    monkeypatch.setattr(admin_api, "holders", lambda *args: ["A", "B"])

    nodes = client.get("/api/nodes").json()
    quorum = client.get("/api/quorum").json()
    overview = client.get("/api/overview").json()

    assert [node["node_id"] for node in nodes] == ["A", "B", "C", "D"]
    assert nodes[2]["online"] is False
    assert quorum == {
        "resource_id": "assignment2",
        "verified_holders": ["A", "B"],
        "required_quorum": 3,
        "available_holders": 2,
        "deficit": 1,
        "status": "QUORUM DEFICIT",
    }
    assert overview["online_nodes"] == 3
    assert overview["offline_nodes"] == 1
    assert overview["quorum"] == quorum


def test_recovery_uses_existing_selector_and_reports_verified_replica(monkeypatch):
    holder_results = iter((["A", "B"], ["A", "B", "D"]))
    monkeypatch.setattr(admin_api, "holders", lambda *args: next(holder_results))
    monkeypatch.setattr(
        admin_api,
        "node_status",
        lambda node_id: {
            "online": node_id != "C",
            "resources": ["assignment2"] if node_id in ("A", "B") else [],
        },
    )
    validation_calls = []

    def fake_validate_candidate(node_url, expected_version):
        validation_calls.append((node_url, expected_version))
        return {"valid": True, "reason": "Node is healthy."}

    monkeypatch.setattr(
        quorum_recovery,
        "validate_candidate",
        fake_validate_candidate,
    )
    transfers = []
    monkeypatch.setattr(
        admin_api,
        "replicate_from_node",
        lambda source, target, resource_id, digest: transfers.append(target),
    )

    response = client.post("/api/recovery")

    assert response.status_code == 200
    data = response.json()
    assert transfers == ["D"]
    assert validation_calls == [("http://127.0.0.1:8004", 1)]
    assert data["selection"]["selected_devices"] == ["D"]
    assert data["successful_transfers"] == ["D"]
    assert data["after"]["available_holders"] == 3
    assert data["message"] == "QUORUM RESTORED"


def test_recovery_does_not_claim_unverified_transfer_as_success(monkeypatch):
    holder_results = iter((["A", "B"], ["A", "B"]))
    monkeypatch.setattr(admin_api, "holders", lambda *args: next(holder_results))
    monkeypatch.setattr(
        admin_api,
        "node_status",
        lambda node_id: {"online": True, "resources": []},
    )
    monkeypatch.setattr(
        admin_api,
        "select_recovery_devices",
        lambda *args, **kwargs: {"selected_devices": ["C"]},
    )
    monkeypatch.setattr(
        admin_api,
        "replicate_from_node",
        lambda *args: {"status": "stored"},
    )

    response = client.post("/api/recovery")

    assert response.status_code == 200
    data = response.json()
    assert data["successful_transfers"] == []
    assert "SHA-256 verified" in data["failed_transfers"]["C"]
    assert data["after"]["deficit"] == 1
    assert data["message"] == "QUORUM NOT RESTORED"


def test_recovery_skips_replication_when_quorum_is_already_met(monkeypatch):
    monkeypatch.setattr(admin_api, "holders", lambda *args: ["A", "B", "C"])
    monkeypatch.setattr(
        admin_api,
        "select_recovery_devices",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("selector should not run when quorum is satisfied")
        ),
    )
    monkeypatch.setattr(
        admin_api,
        "replicate_from_node",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("no replica should be sent")
        ),
    )

    response = client.post("/api/recovery")

    assert response.status_code == 200
    data = response.json()
    assert data["before"]["deficit"] == 0
    assert data["after"] == data["before"]
    assert data["successful_transfers"] == []


def test_recovery_reports_insufficient_eligible_nodes(monkeypatch):
    monkeypatch.setattr(admin_api, "holders", lambda *args: ["A", "B"])
    monkeypatch.setattr(
        admin_api,
        "node_status",
        lambda node_id: {"online": False, "resources": []},
    )
    monkeypatch.setattr(
        admin_api,
        "replicate_from_node",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("an offline node must not receive a replica")
        ),
    )

    response = client.post("/api/recovery")

    assert response.status_code == 200
    data = response.json()
    assert data["selection"]["selected_devices"] == []
    assert data["successful_transfers"] == []
    assert data["after"]["deficit"] == 1
    assert data["message"] == "QUORUM NOT RESTORED"


def test_student_upload_reaches_verified_replica_quorum(monkeypatch, tmp_path):
    payload = b"student PDF payload"
    digest = hashlib.sha256(payload).hexdigest()

    def response(status_code, content, headers=None):
        result = requests.Response()
        result.status_code = status_code
        result._content = content
        result.headers.update(headers or {})
        return result

    monkeypatch.setattr(
        admin_api,
        "node_status",
        lambda node_id: {"online": True, "resources": []},
    )
    monkeypatch.setattr(
        admin_api.requests,
        "post",
        lambda *args, **kwargs: response(
            200,
            json.dumps({"sha256": digest, "status": "stored"}).encode(),
        ),
    )
    monkeypatch.setattr(
        admin_api.requests,
        "get",
        lambda *args, **kwargs: response(200, payload),
    )
    monkeypatch.setattr(admin_api, "ADMIN_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        admin_api,
        "RESOURCE_REGISTRY",
        tmp_path / "resources.json",
    )

    result = client.post(
        "/api/resources/assignment2",
        files={"upload": ("class_notes.pdf", payload, "application/pdf")},
    )

    assert result.status_code == 200
    data = result.json()
    assert data["verified_nodes"] == ["A", "B", "C"]
    assert data["verified_replica_count"] == 3
    assert data["sha256"] == digest
    assert json.loads((tmp_path / "resources.json").read_text())["assignment2"] == {
        "filename": "class_notes.pdf",
        "sha256": digest,
    }


def test_student_upload_does_not_claim_quorum_with_only_two_online_nodes(
    monkeypatch,
    tmp_path,
):
    payload = b"partial quorum resource"
    digest = hashlib.sha256(payload).hexdigest()

    def response(status_code, content):
        result = requests.Response()
        result.status_code = status_code
        result._content = content
        return result

    monkeypatch.setattr(
        admin_api,
        "node_status",
        lambda node_id: {"online": node_id in ("A", "B"), "resources": []},
    )
    monkeypatch.setattr(
        admin_api.requests,
        "post",
        lambda *args, **kwargs: response(
            200,
            json.dumps({"sha256": digest, "status": "stored"}).encode(),
        ),
    )
    monkeypatch.setattr(
        admin_api.requests,
        "get",
        lambda *args, **kwargs: response(200, payload),
    )
    monkeypatch.setattr(admin_api, "ADMIN_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        admin_api,
        "RESOURCE_REGISTRY",
        tmp_path / "resources.json",
    )

    result = client.post(
        "/api/resources/partial_resource",
        files={"upload": ("partial.pdf", payload, "application/pdf")},
    )

    assert result.status_code == 503
    detail = result.json()["detail"]
    assert detail["required_quorum"] == 3
    assert detail["verified_replica_count"] == 2
    assert detail["verified_nodes"] == ["A", "B"]


def test_student_upload_rejects_bad_id_empty_and_oversized_files():
    assert client.post(
        "/api/resources/../escape",
        files={"upload": ("notes.pdf", b"data", "application/pdf")},
    ).status_code in (400, 404)

    empty = client.post(
        "/api/resources/empty_resource",
        files={"upload": ("empty.pdf", b"", "application/pdf")},
    )
    assert empty.status_code == 400

    oversized = client.post(
        "/api/resources/large_resource",
        files={
            "upload": (
                "large.pdf",
                b"x" * (admin_api.MAX_FILE_SIZE + 1),
                "application/pdf",
            )
        },
    )
    assert oversized.status_code == 413


def test_student_download_returns_verified_content_hash(monkeypatch, tmp_path):
    payload = b"known student file"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(
        admin_api,
        "RESOURCE_REGISTRY",
        tmp_path / "resources.json",
    )
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "resources.json").write_text(
        json.dumps(
            {
                "assignment2": {
                    "filename": "notes.pdf",
                    "sha256": digest,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        admin_api,
        "node_status",
        lambda node_id: {
            "online": node_id == "A",
            "resources": ["assignment2"] if node_id == "A" else [],
        },
    )

    def fake_get(*args, **kwargs):
        result = requests.Response()
        result.status_code = 200
        result._content = payload
        result.headers["content-type"] = "application/pdf"
        return result

    monkeypatch.setattr(admin_api.requests, "get", fake_get)

    response = client.get("/api/resources/assignment2")

    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["x-content-sha256"] == digest
    assert "notes.pdf" in response.headers["content-disposition"]
