import requests
from unittest.mock import patch


def calculate_quorum(required_quorum, verified_holders):
    """
    Calculates whether verified online holders meet the quorum requirement.
    """
    available = len(set(verified_holders))
    deficit = max(0, required_quorum - available)

    if deficit == 0:
        status = "QUORUM SATISFIED"
    else:
        status = "QUORUM DEFICIT"

    return {
        "required_quorum": required_quorum,
        "available_holders": available,
        "deficit": deficit,
        "status": status
    }


def validate_candidate(node_url, expected_version=1):
    """
    Checks whether a recovery candidate is online and version-compatible.
    """
    try:
        response = requests.get(f"{node_url}/status", timeout=2)

        if response.status_code == 200:
            data = response.json()
            is_online = data.get("online", False)
            node_version = data.get("version", expected_version)

            if is_online and node_version >= expected_version:
                return {
                    "valid": True,
                    "reason": "Node is healthy, online, and version compatible."
                }

            return {
                "valid": False,
                "reason": f"Node validation failed. Online: {is_online}, Version: {node_version}"
            }

        return {
            "valid": False,
            "reason": f"Node returned unhealthy HTTP status: {response.status_code}"
        }

    except requests.exceptions.RequestException as e:
        return {
            "valid": False,
            "reason": f"Connection timeout or node unreachable: {str(e)}"
        }


def select_recovery_devices(
    required_quorum,
    verified_holders,
    eligible_devices,
    node_urls=None,
    expected_version=1
):
    """
    Selects healthy recovery devices and tracks validation failures.
    """
    verified_set = set(verified_holders)
    available = len(verified_set)
    deficit = max(0, required_quorum - available)

    selected_devices = []
    failed_devices = {}

    if not node_urls:
        node_urls = {
            "A": "http://127.0.0.1:8001",
            "B": "http://127.0.0.1:8002",
            "C": "http://127.0.0.1:8003",
            "D": "http://127.0.0.1:8004"
        }

    for device in eligible_devices:
        if len(selected_devices) >= deficit:
            break

        if device not in verified_set and device not in selected_devices:
            url = node_urls.get(device)

            if url:
                validation = validate_candidate(url, expected_version)

                if validation["valid"]:
                    selected_devices.append(device)
                else:
                    failed_devices[device] = validation["reason"]
            else:
                failed_devices[device] = "Unknown device endpoint configuration URL."

    actual_selected = len(selected_devices)

    if actual_selected >= deficit:
        recovery_status = "RECOVERY CAPACITY SUFFICIENT"
    elif actual_selected > 0:
        recovery_status = "PARTIAL RECOVERY POSSIBLE BUT INSUFFICIENT"
    else:
        recovery_status = "INSUFFICIENT RECOVERY DEVICES"

    return {
        "selected_devices": selected_devices,
        "required_recoveries": deficit,
        "selected_count": actual_selected,
        "recovery_status": recovery_status,
        "failed_validations": failed_devices
    }


def run_recovery_simulation_tests():
    """
    Runs quorum and recovery simulation tests.
    """

    print("\n" + "=" * 50)
    print("RUNNING BHAVANA'S RECOVERY LOGIC UNIT TESTS")
    print("=" * 50)

    # TEST 1: Quorum satisfied
    print("\n[TEST 1] Scenario: 3 Nodes Online out of 3 Quorum")

    res1 = calculate_quorum(
        required_quorum=3,
        verified_holders=["A", "B", "C"]
    )

    print(f"Result Status: {res1['status']} (Deficit: {res1['deficit']})")

    assert res1["status"] == "QUORUM SATISFIED"
    assert res1["deficit"] == 0

    print("TEST 1 PASSED")

    # TEST 2: Quorum deficit
    print("\n[TEST 2] Scenario: Node C goes offline")

    res2 = calculate_quorum(
        required_quorum=3,
        verified_holders=["A", "B"]
    )

    print(f"Result Status: {res2['status']} (Deficit: {res2['deficit']})")

    assert res2["status"] == "QUORUM DEFICIT"
    assert res2["deficit"] == 1

    print("TEST 2 PASSED")

    # TEST 3: Healthy candidate selection
    print("\n[TEST 3] Scenario: Healthy candidate selected for recovery")

    mock_urls = {
        "A": "http://127.0.0.1:8001",
        "B": "http://127.0.0.1:8002",
        "C": "http://127.0.0.1:8003",
        "D": "http://127.0.0.1:8004"
    }

    mock_validation = {
        "valid": True,
        "reason": "Mock node is healthy and version-compatible."
    }

    with patch(
    __name__ + ".validate_candidate",
    return_value=mock_validation
):
        rec_res = select_recovery_devices(
            required_quorum=3,
            verified_holders=["A", "B"],
            eligible_devices=["A", "B", "C", "D"],
            node_urls=mock_urls
        )

    print("Recovery Selection Details:", rec_res)

    assert rec_res["selected_devices"] == ["C"]
    assert rec_res["selected_count"] == 1
    assert rec_res["recovery_status"] == "RECOVERY CAPACITY SUFFICIENT"

    print("TEST 3 PASSED")

    # TEST 4: Candidate validation failure
    print("\n[TEST 4] Scenario: Candidate validation failure")

    failed_validation = {
        "valid": False,
        "reason": "Mock candidate is offline."
    }

    with patch(
        "quorum_recovery.validate_candidate",
        return_value=failed_validation
    ):
        failure_res = select_recovery_devices(
            required_quorum=3,
            verified_holders=["A", "B"],
            eligible_devices=["A", "B", "C", "D"],
            node_urls=mock_urls
        )

    print("Failure Handling Details:", failure_res)

    assert failure_res["selected_count"] == 0
    assert failure_res["recovery_status"] == "INSUFFICIENT RECOVERY DEVICES"
    assert "C" in failure_res["failed_validations"]

    print("TEST 4 PASSED")

    print("\n" + "=" * 50)
    print("ALL 4 RECOVERY TESTS PASSED SUCCESSFULLY!")
    print("=" * 50)


if __name__ == "__main__":
    run_recovery_simulation_tests()
