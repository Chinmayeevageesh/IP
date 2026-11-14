
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from controller import (
    NODES,
    RESOURCE_ID,
    REQUIRED_QUORUM,
    node_status,
    holders,
    send_file,
)

from quorum_recovery import (
    calculate_quorum,
    select_recovery_devices,
)

app = FastAPI(title="Campus Resource Network - Admin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

EXPECTED_VERSION = 1


def get_node_details():
    result = []

    for node_id in NODES:
        status = node_status(node_id)

        result.append({
            "node_id": node_id,
            "online": status.get("online", False),
            "version": status.get("version", "N/A"),
            "resources": status.get("resources", []),
            "reachable": status.get("online", False),
        })

    return result


def get_quorum_details():
    try:
        verified_holders = holders()
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not verify resource holders: {error}"
        )

    quorum = calculate_quorum(
        REQUIRED_QUORUM,
        verified_holders
    )

    return {
        "resource_id": RESOURCE_ID,
        "verified_holders": verified_holders,
        **quorum
    }


@app.get("/")
def home():
    return {
        "message": "Campus Resource Network Admin API is running"
    }


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
        "online_nodes": sum(
            1 for node in nodes if node["online"]
        ),
        "offline_nodes": sum(
            1 for node in nodes if not node["online"]
        ),
    }


@app.post("/api/recovery")
def perform_recovery():
    # Step 1: Verify current resource holders
    current_holders = holders()

    quorum_before = calculate_quorum(
        REQUIRED_QUORUM,
        current_holders
    )

    if quorum_before["deficit"] == 0:
        return {
            "message": "Quorum is already satisfied. Recovery not required.",
            "before": quorum_before,
            "selected_devices": [],
            "after": quorum_before,
        }

    # Step 2: Find online nodes that do not have the resource
    eligible_devices = []

    for node_id in NODES:
        if node_id in current_holders:
            continue

        status = node_status(node_id)

        if (
            status.get("online")
            and RESOURCE_ID not in status.get("resources", [])
        ):
            eligible_devices.append(node_id)

    # Step 3: Select healthy recovery candidates
    selection = select_recovery_devices(
        REQUIRED_QUORUM,
        current_holders,
        eligible_devices,
        node_urls=NODES,
        expected_version=EXPECTED_VERSION,
    )

    # Step 4: Transfer the resource to selected nodes
    successful_transfers = []
    failed_transfers = {}

    for node_id in selection["selected_devices"]:
        try:
            send_file(node_id)
            successful_transfers.append(node_id)

        except Exception as error:
            failed_transfers[node_id] = str(error)

    # Step 5: Verify the replicas again using SHA-256
    final_holders = holders()

    quorum_after = calculate_quorum(
        REQUIRED_QUORUM,
        final_holders
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
