[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [int]$StartupTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StateDirectory = Join-Path $RepositoryRoot "data\local"
$KeyFile = Join-Path $StateDirectory "sales-operator-key.txt"
$LogDirectory = Join-Path $StateDirectory "logs"
$AlphaPackage = Join-Path $StateDirectory "distribution\aurora-chat-fix-20261006"
$ExpectedAlphaRelease = "1134bcd195cba93072f0f7190219b0a572d6c7dc899ac27cbbbaf11c5eae72f6"
$AlphaRuntimeState = Join-Path $env:LOCALAPPDATA "Aurora\staging\state-1134bcd1"
$AlphaSecretDirectory = Join-Path $env:LOCALAPPDATA "Aurora\staging\secrets"
$AlphaSiteKeyFile = Join-Path $AlphaSecretDirectory "site-api-key.txt"
$AlphaLog = Join-Path $env:LOCALAPPDATA "Aurora\staging\logs\aurora-alpha-managed.log"
$Python = (Get-Command python.exe -ErrorAction Stop).Source

function Get-LoopbackListeners {
    param([int]$Port)

    return @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Get-ProcessCommandLine {
    param([int]$ProcessId)

    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId"
    if (-not $process) {
        throw "Could not inspect listener process $ProcessId."
    }
    return [string]$process.CommandLine
}

function Assert-ExpectedLocalApp {
    param(
        [int]$Port,
        [switch]$RequireSingleWorker
    )

    $listeners = Get-LoopbackListeners -Port $Port
    if (-not $listeners.Count) {
        return
    }
    if (@($listeners | Where-Object { $_.LocalAddress -ne "127.0.0.1" }).Count) {
        throw "Port $Port has a listener outside 127.0.0.1; refusing to stop it."
    }
    $pids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($processId in $pids) {
        $command = Get-ProcessCommandLine -ProcessId $processId
        $matchesApp = $command -match '(?i)-m\s+uvicorn\s+web_agent:app(?:\s|$)'
        $matchesHost = $command -match '(?i)--host\s+127\.0\.0\.1(?:\s|$)'
        $matchesPort = $command -match "(?i)--port\s+$Port(?:\s|$)"
        $workerMatch = [regex]::Match($command, '(?i)--workers\s+(\d+)(?:\s|$)')
        $matchesWorkers = -not $RequireSingleWorker -or
            -not $workerMatch.Success -or [int]$workerMatch.Groups[1].Value -eq 1
        if (-not ($matchesApp -and $matchesHost -and $matchesPort -and $matchesWorkers)) {
            throw "Port $Port is occupied by PID $processId, which does not match the expected local Aurora app. No process was stopped."
        }
    }
}

function Wait-PortReleased {
    param([int]$Port)

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (-not (Get-LoopbackListeners -Port $Port).Count) {
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Port $Port did not become available after stopping its verified process."
}

function Restart-LocalOllama {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue)
    if (@($listeners | Where-Object { $_.LocalAddress -ne "127.0.0.1" }).Count) {
        throw "Ollama port 11434 has a listener outside 127.0.0.1; refusing to stop it."
    }
    $pids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($pids.Count -gt 1) {
        throw "Ollama port 11434 has multiple listener processes; inspect them before restart."
    }
    foreach ($processId in $pids) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
        if (-not $process -or $process.Name -ne "ollama.exe" -or
            $process.CommandLine -notmatch '(?i)ollama\.exe"\s+serve(?:\s|$)') {
            throw "Port 11434 is occupied by PID $processId, which is not the expected local Ollama server. No process was stopped."
        }
        try {
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
            Write-Host "Ollama is already ready on 127.0.0.1:11434; leaving its process and loaded models untouched."
            return
        } catch {
            throw "The verified Ollama process on port 11434 is not responding to its local API. It was left running; inspect it before retrying."
        }
    }
    if ($WhatIfPreference) {
        $null = $PSCmdlet.ShouldProcess("127.0.0.1:11434", "Start local Ollama server without downloading models")
        return
    }

    $ollama = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if (-not $ollama) {
        throw "Local ollama.exe was not found; no cloud fallback is used."
    }
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
    $stdout = Join-Path $LogDirectory "ollama.stdout.log"
    $stderr = Join-Path $LogDirectory "ollama.stderr.log"
    if ($PSCmdlet.ShouldProcess("127.0.0.1:11434", "Start local Ollama server without downloading models")) {
        $process = Start-Process -FilePath $ollama.Source -ArgumentList "serve" `
            -WorkingDirectory $RepositoryRoot -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -PassThru
        Write-Host "Started local Ollama (PID $($process.Id)); no models were downloaded."
        $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
        do {
            try {
                $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
                Write-Host "Ollama is ready on 127.0.0.1:11434."
                return
            } catch {
                Start-Sleep -Seconds 1
            }
        } while ((Get-Date) -lt $deadline)
        throw "Ollama did not become ready within $StartupTimeoutSeconds seconds. Inspect data\local\logs\ollama.stderr.log."
    }
}

function Wait-Ready {
    param(
        [int]$Port,
        [bool]$ServingOnly,
        [string]$ReleaseId = ""
    )

    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    do {
        try {
            $ready = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health/ready" -TimeoutSec 3
            if ($ready.status -eq "ready" -and
                [bool]$ready.serving_only -eq $ServingOnly -and
                (-not $ReleaseId -or $ready.release_id -eq $ReleaseId)) {
                return $ready
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    } while ((Get-Date) -lt $deadline)
    throw "Aurora on port $Port did not pass readiness checks within $StartupTimeoutSeconds seconds."
}

function Get-AlphaSiteKey {
    if ($WhatIfPreference) {
        Write-Host "Alpha restart preview: a per-user site key will be loaded or generated in the protected local staging secrets directory."
        return ""
    }

    $siteKey = [string]$env:AURORA_SITE_API_KEY_LOCAL
    if ($siteKey) {
        if ($siteKey.Trim().Length -lt 32) {
            throw "AURORA_SITE_API_KEY_LOCAL must contain at least 32 characters."
        }
        return $siteKey.Trim()
    }

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $userSid = $identity.User
    if (-not $userSid) {
        throw "Could not determine the current Windows user; Alpha's local key was not loaded or created."
    }
    $systemSid = [Security.Principal.SecurityIdentifier]::new("S-1-5-18")
    $fullControl = [Security.AccessControl.FileSystemRights]::FullControl
    $allow = [Security.AccessControl.AccessControlType]::Allow

    if (-not (Test-Path -LiteralPath $AlphaSecretDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $AlphaSecretDirectory | Out-Null
    }
    if ((Get-Item -LiteralPath $AlphaSecretDirectory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Alpha's local secrets directory is a reparse point; refusing to use it."
    }
    $directoryAcl = Get-Acl -LiteralPath $AlphaSecretDirectory
    $directoryAcl.SetAccessRuleProtection($true, $false)
    $directoryAcl.SetOwner($userSid)
    foreach ($accessRule in @($directoryAcl.Access)) {
        $directoryAcl.RemoveAccessRuleAll($accessRule)
    }
    $directoryAcl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $userSid, $fullControl,
        [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit,
        [Security.AccessControl.PropagationFlags]::None, $allow))
    $directoryAcl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $systemSid, $fullControl,
        [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit,
        [Security.AccessControl.PropagationFlags]::None, $allow))
    Set-Acl -LiteralPath $AlphaSecretDirectory -AclObject $directoryAcl

    if (Test-Path -LiteralPath $AlphaSiteKeyFile) {
        if ((Get-Item -LiteralPath $AlphaSiteKeyFile -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Alpha's local site key is a reparse point; refusing to read it."
        }
        $siteKey = [IO.File]::ReadAllText($AlphaSiteKeyFile).Trim()
        if ($siteKey.Length -lt 32) {
            throw "Alpha's local site key file is empty or shorter than 32 characters; replace it securely before restarting."
        }
    } else {
        $randomBytes = [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
        try {
            $siteKey = [Convert]::ToBase64String($randomBytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
        } finally {
            [Array]::Clear($randomBytes, 0, $randomBytes.Length)
        }
        [IO.File]::WriteAllText($AlphaSiteKeyFile, $siteKey, [Text.UTF8Encoding]::new($false))
        Write-Host "Created a per-user Alpha site key in the protected local staging secrets directory."
    }

    $fileAcl = Get-Acl -LiteralPath $AlphaSiteKeyFile
    $fileAcl.SetAccessRuleProtection($true, $false)
    $fileAcl.SetOwner($userSid)
    foreach ($accessRule in @($fileAcl.Access)) {
        $fileAcl.RemoveAccessRuleAll($accessRule)
    }
    $fileAcl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $userSid, $fullControl, [Security.AccessControl.AccessControlType]::Allow))
    $fileAcl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $systemSid, $fullControl, [Security.AccessControl.AccessControlType]::Allow))
    Set-Acl -LiteralPath $AlphaSiteKeyFile -AclObject $fileAcl
    return $siteKey
}

function Assert-AlphaPackage {
    if (-not (Test-Path -LiteralPath (Join-Path $AlphaPackage "package_manifest.json") -PathType Leaf)) {
        throw "The expected local Alpha package is missing; refusing to restart the serving-only process."
    }
    $manifest = Get-Content -LiteralPath (Join-Path $AlphaPackage "package_manifest.json") -Raw | ConvertFrom-Json
    if ($manifest.default_profile -ne "serving-only" -or $manifest.release_id -ne $ExpectedAlphaRelease) {
        throw "The Alpha package does not match the explicitly expected serving-only release."
    }
    $active = Get-Content -LiteralPath (Join-Path $AlphaPackage "releases\active.json") -Raw | ConvertFrom-Json
    if ($active.release_id -ne $ExpectedAlphaRelease) {
        throw "The Alpha package's active release pointer does not match the expected release."
    }
    $packageRoot = [IO.Path]::GetFullPath($AlphaPackage).TrimEnd("\") + "\"
    foreach ($entry in $manifest.files.PSObject.Properties) {
        $relative = [string]$entry.Name -replace "/", "\"
        $file = [IO.Path]::GetFullPath((Join-Path $AlphaPackage $relative))
        if (-not $file.StartsWith($packageRoot, [StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "The Alpha manifest contains an absent or out-of-package file: $relative"
        }
        $actualHash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne ([string]$entry.Value).ToLowerInvariant()) {
            throw "The Alpha package checksum does not match: $relative"
        }
    }
    if (-not (Test-Path -LiteralPath $AlphaRuntimeState -PathType Container)) {
        throw "The existing Alpha state directory is missing; refusing to create or redirect it."
    }
    $siteConfig = Get-Content -LiteralPath (Join-Path $AlphaPackage "config\sites\local.json") -Raw | ConvertFrom-Json
    if ($siteConfig.site_id -ne "local" -or $siteConfig.api_key -or
        @($siteConfig.allowed_origins).Count -ne 1 -or
        $siteConfig.allowed_origins[0] -ne "http://127.0.0.1:8011") {
        throw "The Alpha demo site config is not limited to the expected loopback origin."
    }
}

function Restart-Alpha {
    Assert-AlphaPackage
    Assert-ExpectedLocalApp -Port 8011 -RequireSingleWorker
    $listeners = Get-LoopbackListeners -Port 8011
    if ($listeners.Count) {
        $ready = Invoke-RestMethod -Uri "http://127.0.0.1:8011/health/ready" -TimeoutSec 5
        if ($ready.status -ne "ready" -or $ready.serving_only -ne $true -or
            $ready.release_id -ne $ExpectedAlphaRelease) {
            throw "The current Alpha listener is not the verified serving-only release; refusing to stop it."
        }
        Write-Host "The pinned serving-only Alpha release is already ready; leaving it and its runtime state untouched."
        return
    }
    $siteKey = Get-AlphaSiteKey
    if ($listeners.Count) {
        $pids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
        foreach ($processId in $pids) {
            if ($PSCmdlet.ShouldProcess("PID $processId on 127.0.0.1:8011", "Stop verified serving-only Alpha process")) {
                Stop-Process -Id $processId -ErrorAction Stop
            }
        }
        if (-not $WhatIfPreference) {
            Wait-PortReleased -Port 8011
        }
    }

    if ($WhatIfPreference) {
        $null = $PSCmdlet.ShouldProcess("127.0.0.1:8011", "Start verified serving-only Alpha service")
        return
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $AlphaLog) | Out-Null
    $alphaStdout = Join-Path (Split-Path -Parent $AlphaLog) "aurora-alpha-managed.stdout.log"
    $alphaStderr = Join-Path (Split-Path -Parent $AlphaLog) "aurora-alpha-managed.stderr.log"
    $environment = @{
        AURORA_ENV = "production"
        AURORA_SERVING_ONLY = "true"
        AURORA_RELEASE_DIR = Join-Path $AlphaPackage "releases"
        AURORA_STATE_DIR = $AlphaRuntimeState
        AURORA_SITES_DIR = Join-Path $AlphaPackage "config\sites"
        AURORA_SESSION_BACKEND = "sqlite"
        AURORA_RATE_LIMIT_BACKEND = "sqlite"
        AURORA_SITE_API_KEY_LOCAL = $siteKey
        AGENT_USE_LLM = "false"
        USE_HYBRID_RANKING = "false"
    }
    $arguments = @(
        "-m", "uvicorn", "web_agent:app", "--app-dir", $AlphaPackage,
        "--host", "127.0.0.1", "--port", "8011", "--workers", "1"
    )
    if ($PSCmdlet.ShouldProcess("127.0.0.1:8011", "Start verified serving-only Alpha service")) {
        $process = Start-Process -FilePath $Python -ArgumentList $arguments `
            -WorkingDirectory $AlphaPackage -Environment $environment `
            -RedirectStandardOutput $alphaStdout -RedirectStandardError $alphaStderr -PassThru
        Write-Host "Started serving-only Alpha on port 8011 (PID $($process.Id)); logs are in the private local staging directory."
        $alphaReady = Wait-Ready -Port 8011 -ServingOnly $true -ReleaseId $ExpectedAlphaRelease
        Write-Host "Port 8011 is ready (serving_only=$($alphaReady.serving_only), pinned release verified)."
    }
    $siteKey = $null
}

function Start-LocalApp {
    param(
        [int]$Port,
        [hashtable]$Environment
    )

    $stdout = Join-Path $LogDirectory "aurora-$Port.stdout.log"
    $stderr = Join-Path $LogDirectory "aurora-$Port.stderr.log"
    $arguments = @(
        "-m", "uvicorn", "web_agent:app",
        "--host", "127.0.0.1", "--port", [string]$Port, "--workers", "1"
    )
    if (-not $PSCmdlet.ShouldProcess("127.0.0.1:$Port", "Start local Aurora service")) {
        return
    }
    $process = Start-Process -FilePath $Python -ArgumentList $arguments `
        -WorkingDirectory $RepositoryRoot -Environment $Environment `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Write-Host "Started local service on port $Port (PID $($process.Id)); logs are in data\local\logs."
}

if ($StartupTimeoutSeconds -lt 5 -or $StartupTimeoutSeconds -gt 300) {
    throw "StartupTimeoutSeconds must be between 5 and 300."
}
if (-not (Test-Path -LiteralPath $KeyFile -PathType Leaf)) {
    throw "Private operator key file is missing: data\local\sales-operator-key.txt"
}
$OperatorKey = (Get-Content -LiteralPath $KeyFile -Raw).Trim()
if (-not $OperatorKey) {
    throw "Private operator key file is empty."
}

$LocalEnv = @{
    AURORA_ENV = "development"
    AURORA_SERVING_ONLY = "false"
    AURORA_STATE_DIR = $StateDirectory
    AURORA_SESSION_BACKEND = "sqlite"
    AURORA_RATE_LIMIT_BACKEND = "sqlite"
    AURORA_LEAD_ADMIN_KEY = $OperatorKey
    USE_HYBRID_RANKING = "false"
    OLLAMA_HOST = "http://127.0.0.1:11434"
}
$AuroraEnv = $LocalEnv.Clone()
$AuroraEnv.MATRIX_ENABLED = "false"
$AuroraEnv.ORACLE_ENABLED = "false"
$ManagerEnv = $LocalEnv.Clone()
$ManagerEnv.MATRIX_ENABLED = "true"
$ManagerEnv.ORACLE_ENABLED = "true"

if (-not $WhatIfPreference) {
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
}

# Restart Ollama only after confirming its exact loopback listener and process.
Restart-LocalOllama

Restart-Alpha

foreach ($service in @(
    @{ Port = 8001; Environment = $AuroraEnv },
    @{ Port = 8002; Environment = $ManagerEnv }
)) {
    $port = [int]$service.Port
    Assert-ExpectedLocalApp -Port $port -RequireSingleWorker
    $listeners = Get-LoopbackListeners -Port $port
    if ($listeners.Count) {
        $pids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
        foreach ($processId in $pids) {
            if ($PSCmdlet.ShouldProcess("PID $processId on 127.0.0.1:$port", "Stop verified local Aurora process")) {
                Stop-Process -Id $processId -ErrorAction Stop
            }
        }
        if (-not $WhatIfPreference) {
            Wait-PortReleased -Port $port
        }
    }
    Start-LocalApp -Port $port -Environment $service.Environment
    if (-not $WhatIfPreference) {
        $ready = Wait-Ready -Port $port -ServingOnly $false
        Write-Host "Port $port is ready (serving_only=$($ready.serving_only))."
    }
}

if (-not $WhatIfPreference) {
    foreach ($port in @(8001, 8002)) {
        $headers = @{ "X-Aurora-Lead-Admin-Key" = $OperatorKey }
        $briefs = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/admin/briefs?site_id=local" `
            -Headers $headers -TimeoutSec 10
        Write-Host "Port $port operator access verified; local brief count: $(@($briefs).Count)."
    }
    $schema = Invoke-RestMethod -Uri "http://127.0.0.1:8002/openapi.json" -TimeoutSec 10
    foreach ($path in @("/matrix", "/neo", "/oracle")) {
        if ($schema.paths.PSObject.Properties.Name -notcontains $path) {
            throw "Manager route $path is missing from port 8002."
        }
    }
    Write-Host "Matrix, Neo, and Oracle routes are present on port 8002."
    Write-Host "Aurora development: http://127.0.0.1:8001"
    Write-Host "Matrix/Neo/Oracle manager: http://127.0.0.1:8002"
    Write-Host "Operations dashboard: http://127.0.0.1:8002/matrix?tab=operations"
    Write-Host "Aurora Alpha (serving-only): http://127.0.0.1:8011"
    Write-Host "Local Ollama API: http://127.0.0.1:11434 (port 8003 is not used)."
    Write-Host "Local stack startup and checks completed. No cloud services or model downloads were used."
}
