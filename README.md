
# Offline-First Campus Resource Network — 5-Day MVP

A proof-of-concept for a CIE/utility-patent study.

> **Important:** This prototype demonstrates a technical workflow; it does **not** establish patentability. It uses localhost ports to simulate separate campus devices. Quorum-based replica recovery is not claimed as novel; prior-art research and professional review are required before making patent claims.

## 1. What the MVP Demonstrates

1. A resource is introduced with:
   - Resource ID and filename
   - Priority
   - Required quorum
   - Version
   - SHA-256 hash
2. Four simulated nodes (A, B, C and D) can store resource replicas.
3. Nodes expose status and resource endpoints over HTTP.
4. The controller registers/configures the known nodes and tracks their endpoints.
5. The controller calculates the number of currently available, verified holders.
6. A holder can be marked offline.
7. If available holders fall below the required quorum, the controller detects a quorum deficit.
8. The controller selects an eligible online node that does not already hold the resource.
9. The file is transferred to the selected node and its SHA-256 hash is verified.
10. The controller recalculates the verified holder count.
11. Replication stops when the required quorum is reached, or reports that recovery could not restore it.

**Implementation note:** Priority, version and required-quorum fields must be explicitly stored and passed by the controller to count as implemented metadata. A successful file-copy demo alone does not prove those fields are enforced.

## 2. Project Files

Example project folder: `C:\Users\Admin\IP`

- `node.py` — FastAPI node API, local storage, resource upload/download, status and online/offline simulation.
- `controller.py` — Coordinates initial replication, availability checks, quorum-deficit detection, recovery and final verification.
- `peer_client.py` — Optional Member 2 helper for peer registration, transfer retries/fallback and verified downloads, if included.
- `sample_assignment.pdf` — Demo input file.
- `storage_A`, `storage_B`, `storage_C`, `storage_D` — Separate storage directories for each simulated node.

## 3. Requirements

Open PowerShell in the project directory and install the dependencies:

```powershell
python -m pip install fastapi uvicorn requests python-multipart
```

If you use `peer_client.py` and automated tests, also install:

```powershell
python -m pip install pytest httpx
```

## 4. Create a Sample Input File

Run:

```powershell
python -c "from pathlib import Path; Path('sample_assignment.pdf').write_bytes(b'DEMO ACADEMIC FILE')"
```

**Note:** This creates plain demo data with a `.pdf` filename, not a valid PDF document. It is sufficient for file-transfer and hash testing. Use an actual PDF if you need to demonstrate opening the file in a PDF reader.

## 5. Start the Four Simulated Nodes

Open four separate terminals in VS Code. Run every command from the project directory and keep each terminal running.

### Node A — Port 8001

```powershell
$env:NODE_ID="A"
$env:NODE_STORAGE=".\storage_A"
python -m uvicorn node:app --host 127.0.0.1 --port 8001
```

### Node B — Port 8002

```powershell
$env:NODE_ID="B"
$env:NODE_STORAGE=".\storage_B"
python -m uvicorn node:app --host 127.0.0.1 --port 8002
```

### Node C — Port 8003

```powershell
$env:NODE_ID="C"
$env:NODE_STORAGE=".\storage_C"
python -m uvicorn node:app --host 127.0.0.1 --port 8003
```

### Node D — Port 8004

```powershell
$env:NODE_ID="D"
$env:NODE_STORAGE=".\storage_D"
python -m uvicorn node:app --host 127.0.0.1 --port 8004
```

Do not start two servers on the same port. If a port is already in use, find the terminal running that node, stop it with `Ctrl+C`, and then restart it.

## 6. Check Node Status

Open these URLs in your browser:

- http://127.0.0.1:8001/status
- http://127.0.0.1:8002/status
- http://127.0.0.1:8003/status
- http://127.0.0.1:8004/status

Each should return the matching node ID and `online: true`.

If your updated `node.py` supports peer registration, its status response may also include registered peer IDs. The controller must call the registration endpoint for automatic registration to be demonstrated.

## 7. Run the Quorum-Recovery Demo

Open a fifth terminal in the project directory:

```powershell
python controller.py
```

The intended workflow is:

1. Register or configure the nodes.
2. Introduce the academic resource and calculate its SHA-256 hash.
3. Replicate the resource to Nodes A, B and C.
4. Confirm that the initial verified holder count meets quorum 3.
5. Mark Node C offline.
6. Recalculate available verified holders. A and B should leave a count of 2.
7. Detect the quorum deficit.
8. Select Node D if it is online and does not already hold the resource.
9. Transfer the resource to D and verify its hash.
10. Recalculate the holder count and stop when three verified online holders are available.
11. Restore Node C online after the experiment.

### Expected Demonstration Output

The exact text may vary depending on your `controller.py`. The intended state transitions are:

```text
INITIAL
Available holders: ['A', 'B', 'C']
Count: 3
Status: QUORUM SATISFIED

AFTER C DISCONNECTS
Available holders: ['A', 'B']
Count: 2
Status: QUORUM DEFICIT

QUORUM DEFICIT DETECTED -> replication target: D

AFTER SELECTIVE RECOVERY
Available holders: ['A', 'B', 'D']
Count: 3
Status: QUORUM SATISFIED

DEMO RESULT: QUORUM RESTORED
```

**Important:** If Node D already has a verified copy before Node C disconnects, the controller may correctly find that quorum is still satisfied and skip replication. For the specific A+B+D recovery demonstration, ensure D does not already hold the resource before starting. Back up any files before changing demo storage.

## 8. Member 2: File Transfer, Duplicate and Integrity Tests

### Upload a Resource to Node B

```powershell
python -c "import requests; f=open('sample_assignment.pdf','rb'); r=requests.post('http://127.0.0.1:8002/resource/duplicate_test',files={'upload':('sample_assignment.pdf',f,'application/pdf')}); print(r.status_code,r.text); f.close()"
```

Expected on the first upload: HTTP `200` and `"status":"stored"`.

Run the same command again. Expected: HTTP `200` and `"status":"duplicate_unchanged"`.

### Test Conflicting Content

Create a different file:

```powershell
Set-Content -Path conflict.txt -Value "Different content"
```

Upload it using the same resource ID:

```powershell
python -c "import requests; f=open('conflict.txt','rb'); r=requests.post('http://127.0.0.1:8002/resource/duplicate_test',files={'upload':('conflict.txt',f,'text/plain')}); print(r.status_code,r.text); f.close()"
```

Expected: HTTP `409`, because the resource ID already contains different content.

### Test Offline Transfer Handling

Mark Node B offline:

```powershell
python -c "import requests; r=requests.post('http://127.0.0.1:8002/availability',params={'online':False}); print(r.status_code,r.text)"
```

Attempt an upload:

```powershell
python -c "import requests; f=open('sample_assignment.pdf','rb'); r=requests.post('http://127.0.0.1:8002/resource/offline_test',files={'upload':('sample_assignment.pdf',f,'application/pdf')}); print(r.status_code,r.text); f.close()"
```

Expected: HTTP `503` with an offline error.

Restore Node B:

```powershell
python -c "import requests; r=requests.post('http://127.0.0.1:8002/availability',params={'online':True}); print(r.status_code,r.text)"
```

Expected: HTTP `200` and `online: true`.

### Verify Copies Using SHA-256

After the controller has stored `assignment2` on all four nodes:

```powershell
$files = @(
    ".\storage_A\assignment2",
    ".\storage_B\assignment2",
    ".\storage_C\assignment2",
    ".\storage_D\assignment2"
)

$hashes = $files | ForEach-Object {
    (Get-FileHash $_ -Algorithm SHA256).Hash
}

$hashes | Select-Object -Unique
```

One unique hash means the successfully read files have identical contents. If any path is missing, investigate the error rather than treating the test as passed.

## 9. Optional Peer Registration and Retry/Fallback

If `peer_client.py` is present, register peers:

```powershell
python peer_client.py register-all
```

Test distribution with retries and fallback:

```powershell
python peer_client.py distribute sample_assignment.pdf member2_demo A
```

This helper attempts the preferred node, retries transfer failures and then tries other configured nodes. A `409` conflict means the resource ID already contains different content. Use a new resource ID for a new test, or upload identical content to test duplicate handling.

Test a verified download:

```powershell
python peer_client.py download member2_demo A verified_copy.bin
```

Compare the hashes:

```powershell
Get-FileHash .\verified_copy.bin -Algorithm SHA256
Get-FileHash .\sample_assignment.pdf -Algorithm SHA256
```

The hashes should match. The helper's node configuration must contain the correct node URLs. This optional helper does not automatically add priority, version or quorum metadata to the controller.

## 10. Moving from Localhost to Real Local Wi-Fi

The four-process setup simulates separate devices on one computer. To test using real laptops:

1. Connect all laptops to the same trusted Wi-Fi network or hotspot.
2. Run one node process on each laptop.
3. Start Uvicorn with `--host 0.0.0.0` on each laptop.
4. Find each laptop's LAN IPv4 address.
5. Replace URLs such as `http://127.0.0.1:8002` in the controller/client configuration with the corresponding laptop's LAN address, for example `http://192.168.1.24:8002`.
6. Allow the chosen ports through Windows Firewall only on the trusted private network.
7. Test status, upload, download and hash verification across laptops.

Do not expose this prototype directly to the public internet. It does not implement authentication, authorization or production-grade transport security. Use it only on a trusted network with non-sensitive demo files.

## 11. Suggested Demo Script

Use required quorum = 3.

- Node A stores the original resource.
- Nodes B and C store replicas.
- A + B + C → `QUORUM SATISFIED`.
- Mark C offline.
- A + B → `QUORUM DEFICIT`.
- The controller selects eligible Node D.
- The resource is transferred to D and its SHA-256 hash is verified.
- A + B + D → `QUORUM RESTORED`.
- Restore C online.

For a reliable recovery demonstration, ensure D does not already hold the resource at the beginning.

## 12. Limitations and Patent-Study Note

- This is a local proof-of-concept, not a production distributed-storage system.
- Localhost nodes are separate processes, not separate physical devices.
- Node availability is simulated; real network disconnections are not automatically detected.
- Priority, version and quorum metadata must be implemented and validated in the controller before claiming they are stored or enforced.
- Peer registration, retry/fallback and automated tests are available only if the corresponding updated files are installed and used.
- Matching SHA-256 hashes demonstrate matching content; they do not prove authenticity or protect against a malicious node.
- This prototype does not establish novelty, inventive step, patent eligibility or freedom to operate. Conduct prior-art research and seek qualified patent advice before drafting or filing claims.
