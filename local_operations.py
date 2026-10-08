"""Local Ollama and Windows process controls for the Matrix operations panel."""
from __future__ import annotations

import ipaddress
import json
import os
import shutil
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from local_model import installed_models, loopback_ollama_base


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _ollama_request(path: str, *, payload: dict | None = None, timeout: float = 5.0) -> dict:
    base = loopback_ollama_base()
    parsed = urlsplit(base)
    try:
        loopback = parsed.hostname.casefold() == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = False
    if parsed.scheme != "http" or not loopback or parsed.username or parsed.password:
        raise RuntimeError("Operations dashboard permits only loopback Ollama")

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{base}{path}",
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Local Ollama request failed: {type(exc).__name__}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Local Ollama returned an invalid response")
    return result


def resident_models(timeout: float = 5.0) -> list[dict]:
    payload = _ollama_request("/api/ps", timeout=timeout)
    rows = payload.get("models")
    if not isinstance(rows, list):
        raise RuntimeError("Local Ollama returned an invalid resident model list")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"]:
            continue
        result.append({
            "name": row["name"],
            "size_bytes": row.get("size") if isinstance(row.get("size"), int) else None,
            "size_vram_bytes": row.get("size_vram") if isinstance(row.get("size_vram"), int) else None,
            "expires_at": row.get("expires_at") if isinstance(row.get("expires_at"), str) else None,
        })
    return result


def load_model(model: str, minutes: int) -> None:
    if minutes not in {1, 5, 30}:
        raise ValueError("Model residency must be 1, 5, or 30 minutes")
    if model not in installed_models():
        raise ValueError("Select an installed local model")
    _ollama_request("/api/generate", payload={
        "model": model,
        "prompt": "",
        "stream": False,
        "keep_alive": f"{minutes}m",
        "options": {"num_predict": 0},
    }, timeout=180.0)


def unload_model(model: str) -> None:
    resident = {row["name"] for row in resident_models()}
    if model not in resident:
        raise ValueError("Select a model that is currently resident")
    _ollama_request("/api/generate", payload={
        "model": model,
        "prompt": "",
        "stream": False,
        "keep_alive": 0,
        "options": {"num_predict": 0},
    }, timeout=180.0)


def _powershell(script: str, *, env: dict[str, str], timeout: float = 12.0):
    if os.name != "nt":
        raise RuntimeError("Windows process controls are available only on Windows")
    executable = shutil.which("powershell.exe")
    if not executable:
        raise RuntimeError("Windows PowerShell is not available")
    inherited = {
        "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE",
        "HOMEDRIVE", "HOMEPATH", "PSMODULEPATH", "COMSPEC",
    }
    process_env = {
        key: value for key, value in os.environ.items() if key.upper() in inherited
    }
    process_env.update(env)
    try:
        result = subprocess.run(
            [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
            env=process_env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Windows process inspection failed: {type(exc).__name__}") from exc
    if result.returncode != 0:
        raise RuntimeError("Windows process inspection failed")
    try:
        return json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError as exc:
        raise RuntimeError("Windows process inspection returned invalid data") from exc


_PROCESS_INVENTORY_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$currentPid = [int]$env:LOCAL_OPS_CURRENT_PID
$managerPort = [int]$env:LOCAL_OPS_MANAGER_PORT
$ports = @($env:LOCAL_OPS_PORTS -split ',' | ForEach-Object { [int]$_ })
$scriptNames = @(
  'run_local_maintenance.py','tds_research_agent.py','audit_family_gaps.py',
  'local_tds_code_task.py','review_unassigned_tds.py','resolve_tds_from_page.py',
  'validate_research_accuracy.py','validate_product_sheet.py',
  'review_full_suite_local.py','generate_eval_scenarios.py'
)
$protected = @(
  'csrss.exe','dwm.exe','fontdrvhost.exe','lsass.exe','lsm.exe','registry',
  'securityhealthservice.exe','securityhealthhost.exe','services.exe','smss.exe','system',
  'system idle process','trustedinstaller.exe','wininit.exe','winlogon.exe',
  'svchost.exe','mpssvc.exe','msmpeng.exe','nissrv.exe','msense.exe',
  'smartscreen.exe','powershell.exe','pwsh.exe'
)
$listeners = @{}
try {
  foreach ($listener in @(Get-NetTCPConnection -State Listen -LocalPort $ports -ErrorAction Stop)) {
    $listeners[[int]$listener.OwningProcess] = @($listeners[[int]$listener.OwningProcess]) + [int]$listener.LocalPort
  }
} catch {
  [Console]::Error.WriteLine('Could not inspect local listening ports')
  exit 2
}
$rows = @()
foreach ($proc in @(Get-CimInstance Win32_Process)) {
  $cmd = [string]$proc.CommandLine
  $scriptName = $null
  foreach ($name in $scriptNames) {
    if ($proc.Name -notin @('powershell.exe','pwsh.exe') -and
        $cmd -match "(?i)(^|[\\/\s`"'])$([regex]::Escape($name))([`"'\s]|$)") {
      $scriptName = $name
      break
    }
  }
  $pidValue = [int]$proc.ProcessId
  if (-not $listeners.ContainsKey($pidValue) -and -not $scriptName) { continue }
  $ownerSid = $null
  try {
    $owner = Invoke-CimMethod -InputObject $proc -MethodName GetOwnerSid -ErrorAction Stop
    if ($owner.ReturnValue -eq 0) { $ownerSid = [string]$owner.Sid }
  } catch { }
  $name = [string]$proc.Name
  $portsForProcess = @($listeners[$pidValue])
  $label = $null
  if ($portsForProcess.Count) {
    $label = (@($portsForProcess | Sort-Object -Unique | ForEach-Object {
      switch ($_ ) {
        8001 { 'Aurora development' }
        8002 { 'Matrix / Neo / Oracle' }
        8011 { 'Aurora Alpha (serving-only)' }
        11434 { 'Ollama' }
        default { "Local listener :$_" }
      }
    }) -join ', ')
  } elseif ($scriptName) {
    $label = $scriptName
  }
  $isProtected = ($protected -contains $name.ToLowerInvariant()) -or
                 ($pidValue -in @(0,4)) -or ($pidValue -eq $currentPid) -or
                 (8011 -in $portsForProcess) -or ($managerPort -in $portsForProcess)
  $startedAt = if ($proc.CreationDate) { $proc.CreationDate.ToUniversalTime().ToString('o') } else { $null }
  $rows += [pscustomobject]@{
    pid = $pidValue
    name = $name
    label = $label
    ports = @($portsForProcess | Sort-Object -Unique)
    started_at = $startedAt
    owned_by_current_user = ($ownerSid -and $ownerSid -eq $currentSid)
    stop_allowed = [bool](($ownerSid -and $ownerSid -eq $currentSid) -and
                          -not $isProtected -and $startedAt)
  }
}
ConvertTo-Json -InputObject @($rows) -Depth 4 -Compress
"""

_INSPECT_PROCESS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$pidValue = [int]$env:LOCAL_OPS_PID
$currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$currentPid = [int]$env:LOCAL_OPS_CURRENT_PID
$managerPort = [int]$env:LOCAL_OPS_MANAGER_PORT
$protected = @(
  'csrss.exe','dwm.exe','fontdrvhost.exe','lsass.exe','lsm.exe','registry',
  'securityhealthservice.exe','securityhealthhost.exe','services.exe','smss.exe','system',
  'system idle process','trustedinstaller.exe','wininit.exe','winlogon.exe',
  'svchost.exe','mpssvc.exe','msmpeng.exe','nissrv.exe','msense.exe',
  'smartscreen.exe','powershell.exe','pwsh.exe'
)
$proc = Get-CimInstance Win32_Process | Where-Object { [int]$_.ProcessId -eq $pidValue } | Select-Object -First 1
if (-not $proc) { ConvertTo-Json -InputObject @{ exists = $false } -Compress; exit 0 }
$ownerSid = $null
try {
  $owner = Invoke-CimMethod -InputObject $proc -MethodName GetOwnerSid -ErrorAction Stop
  if ($owner.ReturnValue -eq 0) { $ownerSid = [string]$owner.Sid }
} catch { }
$processPorts = @()
try {
  $processPorts = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
                    Where-Object { [int]$_.OwningProcess -eq $pidValue } |
                    Select-Object -ExpandProperty LocalPort -Unique)
} catch {
  [Console]::Error.WriteLine('Could not validate protected listener ports')
  exit 2
}
$name = [string]$proc.Name
$startedAt = if ($proc.CreationDate) { $proc.CreationDate.ToUniversalTime().ToString('o') } else { $null }
$protectedProcess = ($protected -contains $name.ToLowerInvariant()) -or
                    ($pidValue -in @(0,4)) -or ($pidValue -eq $currentPid) -or
                    (8011 -in $processPorts) -or ($managerPort -in $processPorts)
ConvertTo-Json -InputObject @{
  exists = $true
  pid = $pidValue
  name = $name
  started_at = $startedAt
  owned_by_current_user = [bool]($ownerSid -and $ownerSid -eq $currentSid)
  protected = [bool]$protectedProcess
  stop_allowed = [bool](($ownerSid -and $ownerSid -eq $currentSid) -and
                        -not $protectedProcess -and $startedAt)
} -Compress
"""

_STOP_PROCESS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$pidValue = [int]$env:LOCAL_OPS_PID
$expectedName = [string]$env:LOCAL_OPS_PROCESS_NAME
$expectedStartedAt = [string]$env:LOCAL_OPS_STARTED_AT
$currentPid = [int]$env:LOCAL_OPS_CURRENT_PID
$currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$protected = @(
  'csrss.exe','dwm.exe','fontdrvhost.exe','lsass.exe','lsm.exe','registry',
  'securityhealthservice.exe','securityhealthhost.exe','services.exe','smss.exe','system',
  'system idle process','trustedinstaller.exe','wininit.exe','winlogon.exe',
  'svchost.exe','mpssvc.exe','msmpeng.exe','nissrv.exe','msense.exe',
  'smartscreen.exe','powershell.exe','pwsh.exe'
)
$managerPort = [int]$env:LOCAL_OPS_MANAGER_PORT
$proc = Get-CimInstance Win32_Process | Where-Object { [int]$_.ProcessId -eq $pidValue } | Select-Object -First 1
if (-not $proc) { ConvertTo-Json -InputObject @{ result = 'not_found' } -Compress; exit 0 }
if ([string]$proc.Name -ine $expectedName) {
  ConvertTo-Json -InputObject @{ result = 'identity_changed' } -Compress; exit 0
}
$startedAt = if ($proc.CreationDate) { $proc.CreationDate.ToUniversalTime().ToString('o') } else { $null }
if (-not $startedAt -or $startedAt -cne $expectedStartedAt) {
  ConvertTo-Json -InputObject @{ result = 'identity_changed' } -Compress; exit 0
}
$ownerSid = $null
try {
  $owner = Invoke-CimMethod -InputObject $proc -MethodName GetOwnerSid -ErrorAction Stop
  if ($owner.ReturnValue -eq 0) { $ownerSid = [string]$owner.Sid }
} catch { }
if (-not $ownerSid -or $ownerSid -ne $currentSid) {
  ConvertTo-Json -InputObject @{ result = 'ownership_denied' } -Compress; exit 0
}
$processPorts = @()
try {
  $processPorts = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
                    Where-Object { [int]$_.OwningProcess -eq $pidValue } |
                    Select-Object -ExpandProperty LocalPort -Unique)
} catch {
  [Console]::Error.WriteLine('Could not validate protected listener ports')
  exit 2
}
if (($protected -contains ([string]$proc.Name).ToLowerInvariant()) -or
    ($pidValue -in @(0,4)) -or ($pidValue -eq $currentPid) -or
    (8011 -in $processPorts) -or ($managerPort -in $processPorts)) {
  ConvertTo-Json -InputObject @{ result = 'protected' } -Compress; exit 0
}
try {
  Stop-Process -Id $pidValue -Force -ErrorAction Stop
  ConvertTo-Json -InputObject @{ result = 'stopped'; pid = $pidValue; name = [string]$proc.Name } -Compress
} catch {
  ConvertTo-Json -InputObject @{ result = 'stop_failed' } -Compress
}
"""


def _ports(manager_port: int) -> list[int]:
    if not 1 <= manager_port <= 65535:
        raise ValueError("Invalid local manager port")
    return sorted({8001, 8011, 11434, manager_port})


def _process_payload(data, *, current_pid: int) -> dict | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise RuntimeError("Windows process inspection returned an invalid record")
    return {
        "pid": data.get("pid"),
        "name": data.get("name") or "",
        "label": data.get("label") or data.get("name") or "Local process",
        "ports": data.get("ports") if isinstance(data.get("ports"), list) else [],
        "started_at": data.get("started_at"),
        "owned_by_current_user": data.get("owned_by_current_user") is True,
        "stop_allowed": data.get("stop_allowed") is True and data.get("pid") != current_pid,
    }


def process_inventory(*, current_pid: int, manager_port: int) -> list[dict]:
    ports = _ports(manager_port)
    result = _powershell(_PROCESS_INVENTORY_SCRIPT, env={
        "LOCAL_OPS_CURRENT_PID": str(current_pid),
        "LOCAL_OPS_PORTS": ",".join(str(port) for port in ports),
        "LOCAL_OPS_MANAGER_PORT": str(manager_port),
    })
    if result is None:
        return []
    rows = result if isinstance(result, list) else [result]
    return [item for row in rows if (item := _process_payload(row, current_pid=current_pid))]


def inspect_process(pid: int, *, current_pid: int, manager_port: int) -> dict | None:
    if not 1 <= pid <= 2_147_483_647:
        raise ValueError("PID must be a positive Windows process ID")
    result = _powershell(_INSPECT_PROCESS_SCRIPT, env={
        "LOCAL_OPS_PID": str(pid),
        "LOCAL_OPS_CURRENT_PID": str(current_pid),
        "LOCAL_OPS_PORTS": ",".join(str(port) for port in _ports(manager_port)),
        "LOCAL_OPS_MANAGER_PORT": str(manager_port),
    })
    if not isinstance(result, dict):
        raise RuntimeError("Windows process inspection returned an invalid record")
    if result.get("exists") is not True:
        return None
    return {
        "pid": pid,
        "name": result.get("name") or "",
        "started_at": result.get("started_at"),
        "owned_by_current_user": result.get("owned_by_current_user") is True,
        "protected": result.get("protected") is True,
        "stop_allowed": result.get("stop_allowed") is True and pid != current_pid,
    }


def stop_process(
    pid: int,
    expected_name: str,
    expected_started_at: str,
    *,
    current_pid: int,
    manager_port: int,
) -> str:
    if not 1 <= pid <= 2_147_483_647:
        raise ValueError("PID must be a positive Windows process ID")
    if not expected_name or len(expected_name) > 256:
        raise ValueError("A valid process name is required")
    if not expected_started_at or len(expected_started_at) > 80:
        raise ValueError("A verified process start time is required")
    result = _powershell(_STOP_PROCESS_SCRIPT, env={
        "LOCAL_OPS_PID": str(pid),
        "LOCAL_OPS_PROCESS_NAME": expected_name,
        "LOCAL_OPS_STARTED_AT": expected_started_at,
        "LOCAL_OPS_CURRENT_PID": str(current_pid),
        "LOCAL_OPS_MANAGER_PORT": str(manager_port),
    })
    if not isinstance(result, dict) or not isinstance(result.get("result"), str):
        raise RuntimeError("Windows process stop returned an invalid result")
    return result["result"]
