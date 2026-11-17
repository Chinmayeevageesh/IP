import os


NODES = {
    node_id: os.getenv(
        f"CAMPUS_NODE_{node_id}_URL",
        f"http://127.0.0.1:{port}",
    ).rstrip("/")
    for node_id, port in zip("ABCD", range(8001, 8005))
}
