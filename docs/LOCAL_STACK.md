# Local assistant stack

From the repository root, run the sequential PowerShell launcher:

```powershell
.\scripts\start_local_stack.ps1
```

It ensures local Ollama and the application services are available without
downloading models: development Aurora on `127.0.0.1:8001`, the
Matrix/Neo/Oracle manager on `127.0.0.1:8002`, and the pinned serving-only
Alpha release on `127.0.0.1:8011`. A healthy Ollama listener is left running
with its loaded models untouched; Ollama starts only when its port is unused.
Healthy Alpha is also kept running. Before stopping any service, the launcher
confirms the listener is bound only to loopback and is the expected process;
Alpha must pass readiness checks for the exact serving-only release.
The script verifies Alpha's package hashes, active release pointer, local-only
site configuration, and existing state directory before restart. Alpha's
site API key is loaded from `AURORA_SITE_API_KEY_LOCAL` when explicitly set;
otherwise the launcher creates it on first run and reuses it from
`%LOCALAPPDATA%\Aurora\staging\secrets\site-api-key.txt`. The directory and key
file ACLs are restricted to the current Windows user and SYSTEM. The key is
passed only to the Alpha child process and is never printed or stored in the
repository. This removes the interactive prompt so the single launcher can
start the full stack unattended.
The script reads the ignored
`data\local\sales-operator-key.txt` locally and does not print or persist its
contents outside the child server environment.

The script verifies readiness on all three application servers, confirms
Ollama responds locally, tests operator-key access without printing enquiry
data, and confirms the manager routes. Development logs go to the ignored
`data\local\logs` directory; Alpha logs stay in its existing private local
staging log directory. Use `-WhatIf` to perform a read-only preflight and
preview the planned stop/start actions:

```powershell
.\scripts\start_local_stack.ps1 -WhatIf
```

The development Aurora chat at `http://127.0.0.1:8001/chat` lists every
installed chat-capable local Ollama model and uses the selected model for that conversation.
Neo, Oracle, and the local family/research chat tools also discover
already-installed chat-capable models from the same loopback Ollama service.
Matrix Operations reports the full installed/resident inventory. Embedding-only
models remain available for local embedding tasks but are not offered as chat
choices.
Aurora Alpha remains serving-only and never exposes model selection or local
model calls. Development Aurora uses model phrasing only when Ollama is
available; product routing, discovery state, and retrieval remain
deterministic. During project discovery the local model may naturally rephrase
the next application-selected question using only reported project facts;
stock "I've noted" acknowledgements are omitted, and consent prompts remain
deterministic.

Open `http://127.0.0.1:8002/matrix` and select **Operations** to inspect
known service PIDs, local Ollama models, and recognized long-running scripts.
Unlock Oracle first to authorize model/process controls. Model operations never
download weights; process termination is limited to the current Windows
account and protects the dashboard, core Windows/security processes, and
serving-only Alpha.

The launcher does not change Alpha's release, site configuration, or application
data. Its pinned package and separate state directory remain under the existing
local Alpha management procedure described in
[`AURORA_MANAGEMENT.md`](AURORA_MANAGEMENT.md).
