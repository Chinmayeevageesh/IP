
def calculate_quorum(required_quorum, verified_holders):
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



def select_recovery_devices(required_quorum, verified_holders, eligible_devices):
    available = len(set(verified_holders))
    deficit = max(0, required_quorum - available)

    selected_devices = []

    for device in eligible_devices:
        if len(selected_devices) >= deficit:
            break

        if device not in verified_holders and device not in selected_devices:
            selected_devices.append(device)

    recovery_status = (
        "RECOVERY CAPACITY SUFFICIENT"
        if len(selected_devices) >= deficit
        else "INSUFFICIENT RECOVERY DEVICES"
    )

    return {
        "selected_devices": selected_devices,
        "required_recoveries": deficit,
        "selected_count": len(selected_devices),
        "recovery_status": recovery_status
    }



if __name__ == "__main__":
    required_quorum = 3
    verified_holders = ["A"]
    eligible_devices = ["A", "B","C","D"]

    result = calculate_quorum(
        required_quorum,
        verified_holders
    )

    recovery_devices = select_recovery_devices(
        required_quorum,
        verified_holders,
        eligible_devices
    )

    print("Quorum Result:", result)
print("Recovery Result:", recovery_devices)

if result["deficit"] == 0:
    print("Next Action: No recovery needed.")
elif recovery_devices["selected_count"] >= recovery_devices["required_recoveries"]:
    print("Next Action: Recovery can be initiated.")
else:
    print("Next Action: More eligible devices are needed.")