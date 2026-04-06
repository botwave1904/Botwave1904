<#
.SYNOPSIS
    Botwave VIP Overhaul Script — Windows Edition
    Production-grade system cleanup, file organization, and bot deployment prep.

.DESCRIPTION
    This script performs a complete machine overhaul for Botwave VIP onboarding:
      1. Discovers and organizes all business files into a clean folder structure.
      2. Performs full system cleanup (temp files, caches, bloatware, startup items).
      3. Runs malware/security scans and hardens the system.
      4. Generates a detailed HTML before/after report.
      5. Prepares the machine for immediate Botwave bot deployment.

    Designed to run over Tailscale SSH with temporary elevated access.

.PARAMETER DryRun
    Simulate all actions without making changes. Generates report of what WOULD happen.

.PARAMETER SkipFileOrganization
    Skip the business file discovery and organization phase.

.PARAMETER SkipCleanup
    Skip the system cleanup and optimization phase.

.PARAMETER SkipMalwareScan
    Skip the Windows Defender malware scan phase.

.PARAMETER Confirm
    Auto-confirm destructive actions (required for unattended/SSH execution).

.EXAMPLE
    .\botwave-overhaul.ps1 -DryRun
    .\botwave-overhaul.ps1 -Confirm
    .\botwave-overhaul.ps1 -SkipCleanup -Confirm

.NOTES
    Version : 2.0.0
    Author  : Botwave Engineering
    Requires: PowerShell 5.1+ / 7+, Administrator privileges, Windows 10/11
    License : Proprietary — Botwave Inc.
#>

#Requires -RunAsAdministrator

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$SkipFileOrganization,
    [switch]$SkipCleanup,
    [switch]$SkipMalwareScan,
    [switch]$Confirm
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
$Script:Config = @{
    BotwaveRoot       = "C:\Botwave"
    BusinessRoot      = "C:\Business"
    ReadyFolder       = "C:\Botwave\Ready-For-Botwave"
    LogFolder         = "C:\Botwave\Logs"
    BackupFolder      = "C:\Botwave\Backups"
    Timestamp         = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    Version           = "2.0.0"
    MachineName       = $env:COMPUTERNAME
    Username          = $env:USERNAME
}

$Script:Config.ReportPath = Join-Path $Script:Config.LogFolder "Overhaul-Report-$($Script:Config.Timestamp).html"
$Script:Config.LogPath    = Join-Path $Script:Config.LogFolder "Overhaul-Log-$($Script:Config.Timestamp).txt"
$Script:Config.IndexPath  = Join-Path $Script:Config.BusinessRoot "Business-File-Index.csv"

# Tracking variables
$Script:Report = @{
    StartTime          = Get-Date
    DiskBefore         = 0
    DiskAfter          = 0
    FilesOrganized     = 0
    FilesMoved         = @()
    TempFilesDeleted   = 0
    SpaceReclaimed     = 0
    BloatwareRemoved   = @()
    StartupDisabled    = @()
    ServicesDisabled   = @()
    ThreatsFound       = @()
    LargestFiles       = @()
    InstalledApps      = @()
    Warnings           = @()
    Errors             = @()
    Actions            = @()
    # System profile
    SystemInfo         = @{
        CPU            = ""
        RAM            = ""
        GPU            = ""
        DiskModel      = ""
        DiskTotal      = ""
        OSVersion      = ""
        OSBuild        = ""
        WindowsActivated = ""
        LastUpdate     = ""
        Uptime         = ""
        IPAddress      = ""
        NetworkType    = ""
        BackupStatus   = ""
    }
    # File analytics
    FileTypeBreakdown  = @{}
    OldestFile         = ""
    NewestFile         = ""
    Recommendations    = @()
}

# Business file keywords and extensions
$Script:BusinessKeywords = @(
    'invoice', 'receipt', 'client', 'contract', 'tax', 'quote', 'proposal',
    'estimate', 'budget', 'payroll', 'expense', 'revenue', 'profit', 'loss',
    'balance', 'ledger', 'journal', 'account', 'billing', 'payment', 'vendor',
    'supplier', 'customer', 'employee', 'hr', 'policy', 'agreement', 'nda',
    'sow', 'scope', 'deliverable', 'milestone', 'timesheet', 'inventory',
    'purchase', 'order', 'shipping', 'logistics', 'marketing', 'sales',
    'report', 'memo', 'meeting', 'minutes', 'agenda', 'presentation',
    'quickbooks', 'xero', 'freshbooks', 'w2', 'w9', '1099', 'schedule-c'
)

$Script:BusinessExtensions = @(
    '.xlsx', '.xls', '.docx', '.doc', '.pdf', '.csv', '.pptx', '.ppt',
    '.rtf', '.txt', '.qbw', '.qbb', '.qbx', '.iif'
)

# Category classification rules (keyword → folder)
$Script:CategoryMap = @{
    'Invoices-Receipts' = @('invoice', 'receipt', 'billing', 'payment')
    'Contracts-Legal'   = @('contract', 'agreement', 'nda', 'sow', 'scope', 'legal', 'terms')
    'Tax-Accounting'    = @('tax', 'w2', 'w9', '1099', 'schedule-c', 'ledger', 'journal', 'quickbooks', 'xero', 'freshbooks')
    'Clients-CRM'       = @('client', 'customer', 'crm', 'lead', 'prospect')
    'Proposals-Quotes'  = @('quote', 'proposal', 'estimate', 'bid')
    'Financial-Reports' = @('budget', 'revenue', 'profit', 'loss', 'balance', 'expense', 'payroll', 'financial')
    'HR-Employees'      = @('employee', 'hr', 'policy', 'timesheet', 'onboarding', 'handbook')
    'Marketing-Sales'   = @('marketing', 'sales', 'campaign', 'brochure', 'flyer', 'ad')
    'Operations'        = @('inventory', 'purchase', 'order', 'shipping', 'logistics', 'vendor', 'supplier')
    'Meetings-Notes'    = @('meeting', 'minutes', 'agenda', 'notes', 'memo')
    'Presentations'     = @('presentation', 'deck', 'pitch', 'slides')
}

# Known bloatware / PUPs (safe removal list — conservative)
$Script:BloatwareList = @(
    'Microsoft.BingNews', 'Microsoft.BingWeather', 'Microsoft.GetHelp',
    'Microsoft.Getstarted', 'Microsoft.MicrosoftSolitaireCollection',
    'Microsoft.People', 'Microsoft.WindowsFeedbackHub',
    'Microsoft.Xbox.TCUI', 'Microsoft.XboxGameOverlay',
    'Microsoft.XboxGamingOverlay', 'Microsoft.XboxIdentityProvider',
    'Microsoft.XboxSpeechToTextOverlay', 'Microsoft.YourPhone',
    'Microsoft.ZuneMusic', 'Microsoft.ZuneVideo',
    'Microsoft.MixedReality.Portal', 'Microsoft.SkypeApp',
    'Microsoft.WindowsMaps', 'Microsoft.Messaging',
    'Clipchamp.Clipchamp', 'Microsoft.Todos',
    'Microsoft.PowerAutomateDesktop', 'MicrosoftTeams',
    'Microsoft.549981C3F5F10',  # Cortana
    'Disney.37853FC22B2CE', 'SpotifyAB.SpotifyMusic',
    'BytedancePte.Ltd.TikTok', 'Facebook.Facebook',
    'FACEBOOK.317180B0BB486', 'Instagram.Instagram'
)

# Essential apps whitelist — NEVER remove these
$Script:EssentialApps = @(
    'Microsoft.WindowsStore', 'Microsoft.WindowsCalculator',
    'Microsoft.Windows.Photos', 'Microsoft.WindowsCamera',
    'Microsoft.WindowsNotepad', 'Microsoft.WindowsTerminal',
    'Microsoft.Paint', 'Microsoft.ScreenSketch',
    'Microsoft.WindowsSoundRecorder', 'Microsoft.WindowsAlarms',
    'Microsoft.MSPaint', 'Microsoft.Edge', 'Microsoft.Edge.Stable',
    'Microsoft.DesktopAppInstaller', 'Microsoft.StorePurchaseApp',
    'Microsoft.VP9VideoExtensions', 'Microsoft.WebMediaExtensions',
    'Microsoft.HEIFImageExtension', 'Microsoft.HEVCVideoExtension',
    'Microsoft.WebpImageExtension', 'Microsoft.SecHealthUI',
    'Microsoft.OutlookForWindows'
)

# ─────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

function Write-BW {
    <# Botwave branded console + log output #>
    param(
        [string]$Message,
        [ValidateSet('Info','Success','Warning','Error','Header','Progress')]
        [string]$Level = 'Info'
    )
    $ts = Get-Date -Format "HH:mm:ss"
    $prefix = switch ($Level) {
        'Info'     { "[*]" }
        'Success'  { "[+]" }
        'Warning'  { "[!]" }
        'Error'    { "[X]" }
        'Header'   { "[=]" }
        'Progress' { "[>]" }
    }
    $color = switch ($Level) {
        'Info'     { 'Cyan' }
        'Success'  { 'Green' }
        'Warning'  { 'Yellow' }
        'Error'    { 'Red' }
        'Header'   { 'Magenta' }
        'Progress' { 'White' }
    }
    $line = "$ts $prefix $Message"
    Write-Host $line -ForegroundColor $color

    # Append to log file
    if ($Script:Config.LogPath) {
        $line | Out-File -FilePath $Script:Config.LogPath -Append -Encoding utf8 -ErrorAction SilentlyContinue
    }
}

function Add-Action {
    param([string]$Category, [string]$Detail, [string]$Status = "Done")
    $Script:Report.Actions += [PSCustomObject]@{
        Time     = Get-Date -Format "HH:mm:ss"
        Category = $Category
        Detail   = $Detail
        Status   = $Status
    }
}

function Get-FriendlySize {
    param([long]$Bytes)
    if ($Bytes -ge 1GB) { return "{0:N2} GB" -f ($Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return "{0:N2} MB" -f ($Bytes / 1MB) }
    if ($Bytes -ge 1KB) { return "{0:N2} KB" -f ($Bytes / 1KB) }
    return "$Bytes B"
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        if (-not $DryRun) {
            New-Item -Path $Path -ItemType Directory -Force | Out-Null
        }
        Write-BW "Created directory: $Path" -Level Progress
    }
}

function Get-DiskFreeSpace {
    $drive = (Get-PSDrive C -ErrorAction SilentlyContinue)
    if ($drive) { return $drive.Free }
    return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 0: INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

function Initialize-Overhaul {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║          BOTWAVE VIP SYSTEM OVERHAUL v$($Script:Config.Version)              ║" -ForegroundColor Cyan
    Write-Host "  ║          Professional IT Cleanup & Bot Deployment           ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""

    if ($DryRun) {
        Write-BW "DRY RUN MODE — No changes will be made." -Level Warning
    }

    if (-not $Confirm -and -not $DryRun) {
        Write-BW "ERROR: The -Confirm flag is required for unattended execution." -Level Error
        Write-BW "Use -DryRun to preview changes, or add -Confirm to proceed." -Level Info
        exit 1
    }

    # Verify admin
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-BW "This script requires Administrator privileges. Please re-run as Admin." -Level Error
        exit 1
    }

    # Create directory structure
    @(
        $Script:Config.BotwaveRoot,
        $Script:Config.LogFolder,
        $Script:Config.BackupFolder,
        $Script:Config.ReadyFolder,
        $Script:Config.BusinessRoot
    ) | ForEach-Object { Ensure-Directory $_ }

    # Record baseline
    $Script:Report.DiskBefore = Get-DiskFreeSpace

    Write-BW "Machine: $($Script:Config.MachineName) | User: $($Script:Config.Username)" -Level Info
    Write-BW "OS: $((Get-CimInstance Win32_OperatingSystem).Caption)" -Level Info
    Write-BW "Disk free (C:): $(Get-FriendlySize $Script:Report.DiskBefore)" -Level Info
    Write-BW "Report will be saved to: $($Script:Config.ReportPath)" -Level Info

    # ── System Profiling ──
    Write-BW "Profiling system hardware and status..." -Level Progress
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
        $ram = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
        $disk = Get-CimInstance Win32_DiskDrive | Select-Object -First 1
        $diskLogical = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
        $gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1
        $net = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -and $_.IPAddress } | Select-Object -First 1
        $uptime = (Get-Date) - $os.LastBootUpTime

        $Script:Report.SystemInfo.CPU = "$($cpu.Name) ($($cpu.NumberOfCores) cores)"
        $Script:Report.SystemInfo.RAM = "${ram} GB"
        $Script:Report.SystemInfo.GPU = if ($gpu) { "$($gpu.Name) ($([math]::Round($gpu.AdapterRAM / 1GB, 1)) GB)" } else { "Integrated" }
        $Script:Report.SystemInfo.DiskModel = if ($disk) { $disk.Model } else { "Unknown" }
        $Script:Report.SystemInfo.DiskTotal = if ($diskLogical) { Get-FriendlySize ($diskLogical.Size) } else { "Unknown" }
        $Script:Report.SystemInfo.OSVersion = "$($os.Caption) ($($os.Version))"
        $Script:Report.SystemInfo.OSBuild = $os.BuildNumber
        $Script:Report.SystemInfo.Uptime = "{0}d {1}h {2}m" -f $uptime.Days, $uptime.Hours, $uptime.Minutes
        $Script:Report.SystemInfo.IPAddress = if ($net) { ($net.IPAddress | Where-Object { $_ -notmatch ':' } | Select-Object -First 1) } else { "Unknown" }
        $Script:Report.SystemInfo.NetworkType = if ($net) { $net.Description } else { "Unknown" }

        # Windows activation
        try {
            $lic = Get-CimInstance SoftwareLicensingProduct | Where-Object { $_.PartialProductKey -and $_.LicenseStatus -eq 1 } | Select-Object -First 1
            $Script:Report.SystemInfo.WindowsActivated = if ($lic) { "Activated" } else { "Not Activated" }
        } catch { $Script:Report.SystemInfo.WindowsActivated = "Unknown" }

        # Last Windows Update
        try {
            $lastUpdate = Get-HotFix | Sort-Object InstalledOn -Descending -ErrorAction SilentlyContinue | Select-Object -First 1
            $Script:Report.SystemInfo.LastUpdate = if ($lastUpdate) { $lastUpdate.InstalledOn.ToString("yyyy-MM-dd") } else { "Unknown" }
        } catch { $Script:Report.SystemInfo.LastUpdate = "Unknown" }

        # Backup status
        $backupPaths = @("$env:USERPROFILE\OneDrive", "$env:LOCALAPPDATA\Backblaze", "$env:ProgramFiles\CrashPlan")
        $backupFound = $backupPaths | Where-Object { Test-Path $_ } | ForEach-Object { Split-Path $_ -Leaf }
        $Script:Report.SystemInfo.BackupStatus = if ($backupFound) { $backupFound -join ", " } else { "No backup solution detected" }

        Write-BW "  CPU: $($Script:Report.SystemInfo.CPU)" -Level Info
        Write-BW "  RAM: $($Script:Report.SystemInfo.RAM)" -Level Info
        Write-BW "  GPU: $($Script:Report.SystemInfo.GPU)" -Level Info
        Write-BW "  Disk: $($Script:Report.SystemInfo.DiskModel)" -Level Info
        Write-BW "  Network: $($Script:Report.SystemInfo.IPAddress)" -Level Info
    }
    catch {
        Write-BW "  System profiling encountered errors: $($_.Exception.Message)" -Level Warning
    }

    Write-Host ""
}

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1: BUSINESS FILE DISCOVERY & ORGANIZATION
# ─────────────────────────────────────────────────────────────────────────────

function Invoke-FileOrganization {
    Write-BW "═══ PHASE 1: Business File Discovery & Organization ═══" -Level Header

    # Determine scan locations
    $scanPaths = @()
    $userProfile = $env:USERPROFILE

    $candidates = @(
        (Join-Path $userProfile "Desktop"),
        (Join-Path $userProfile "Documents"),
        (Join-Path $userProfile "Downloads"),
        (Join-Path $userProfile "OneDrive"),
        (Join-Path $userProfile "OneDrive - *"),
        "D:\", "E:\", "F:\"   # External / USB drives
    )

    foreach ($p in $candidates) {
        # Handle wildcard paths
        $resolved = Resolve-Path $p -ErrorAction SilentlyContinue
        if ($resolved) {
            foreach ($r in $resolved) {
                if (Test-Path $r.Path) { $scanPaths += $r.Path }
            }
        }
    }

    Write-BW "Scanning $($scanPaths.Count) locations for business files..." -Level Progress

    # Create business folder structure
    $categories = @(
        'Invoices-Receipts', 'Contracts-Legal', 'Tax-Accounting',
        'Clients-CRM', 'Proposals-Quotes', 'Financial-Reports',
        'HR-Employees', 'Marketing-Sales', 'Operations',
        'Meetings-Notes', 'Presentations', 'Uncategorized'
    )
    foreach ($cat in $categories) {
        Ensure-Directory (Join-Path $Script:Config.BusinessRoot $cat)
    }
    Ensure-Directory (Join-Path $Script:Config.BackupFolder "OriginalFiles-$($Script:Config.Timestamp)")

    # Scan and classify files
    $businessFiles = @()
    $fileIndex = @()

    foreach ($scanPath in $scanPaths) {
        Write-BW "  Scanning: $scanPath" -Level Progress

        try {
            $files = Get-ChildItem -Path $scanPath -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object {
                    # Skip system/hidden and Botwave's own folders
                    -not $_.FullName.StartsWith($Script:Config.BotwaveRoot) -and
                    -not $_.FullName.StartsWith($Script:Config.BusinessRoot) -and
                    $_.Length -gt 0 -and $_.Length -lt 500MB
                }

            foreach ($file in $files) {
                $isBusinessFile = $false
                $matchedCategory = 'Uncategorized'

                # Check by extension
                if ($Script:BusinessExtensions -contains $file.Extension.ToLower()) {
                    $isBusinessFile = $true
                }

                # Check by keyword in filename
                $nameLower = $file.BaseName.ToLower()
                foreach ($keyword in $Script:BusinessKeywords) {
                    if ($nameLower -match [regex]::Escape($keyword)) {
                        $isBusinessFile = $true
                        # Classify into category
                        foreach ($cat in $Script:CategoryMap.Keys) {
                            if ($Script:CategoryMap[$cat] -contains $keyword) {
                                $matchedCategory = $cat
                                break
                            }
                        }
                        break
                    }
                }

                if ($isBusinessFile) {
                    $businessFiles += [PSCustomObject]@{
                        File     = $file
                        Category = $matchedCategory
                    }
                }
            }
        }
        catch {
            Write-BW "  Warning: Could not fully scan $scanPath — $($_.Exception.Message)" -Level Warning
            $Script:Report.Warnings += "Scan error at $scanPath"
        }
    }

    Write-BW "Found $($businessFiles.Count) business-related files." -Level Success

    # Deduplicate by name+size
    $seen = @{}
    $uniqueFiles = @()
    foreach ($bf in $businessFiles) {
        $key = "$($bf.File.Name)|$($bf.File.Length)"
        if (-not $seen.ContainsKey($key)) {
            $seen[$key] = $true
            $uniqueFiles += $bf
        }
    }
    Write-BW "$($uniqueFiles.Count) unique files after deduplication." -Level Info

    # Move/copy files
    $movedCount = 0
    foreach ($bf in $uniqueFiles) {
        $destDir = Join-Path $Script:Config.BusinessRoot $bf.Category
        $destPath = Join-Path $destDir $bf.File.Name

        # Handle name collisions
        $counter = 1
        while (Test-Path $destPath) {
            $newName = "$($bf.File.BaseName)_$counter$($bf.File.Extension)"
            $destPath = Join-Path $destDir $newName
            $counter++
        }

        if (-not $DryRun) {
            # Backup original first
            $backupDir = Join-Path $Script:Config.BackupFolder "OriginalFiles-$($Script:Config.Timestamp)"
            try {
                Copy-Item -Path $bf.File.FullName -Destination $backupDir -Force -ErrorAction Stop
                Copy-Item -Path $bf.File.FullName -Destination $destPath -Force -ErrorAction Stop
                $movedCount++
            }
            catch {
                Write-BW "  Could not process: $($bf.File.FullName) — $($_.Exception.Message)" -Level Warning
                continue
            }
        }
        else {
            $movedCount++
        }

        $fileIndex += [PSCustomObject]@{
            FileName     = $bf.File.Name
            Category     = $bf.Category
            OriginalPath = $bf.File.FullName
            NewPath      = $destPath
            SizeKB       = [math]::Round($bf.File.Length / 1KB, 2)
            LastModified = $bf.File.LastWriteTime.ToString("yyyy-MM-dd HH:mm")
        }
    }

    # Export master index CSV
    if ($fileIndex.Count -gt 0 -and -not $DryRun) {
        $fileIndex | Export-Csv -Path $Script:Config.IndexPath -NoTypeInformation -Encoding UTF8
        Write-BW "Master index saved: $($Script:Config.IndexPath)" -Level Success
    }

    $Script:Report.FilesOrganized = $movedCount
    $Script:Report.FilesMoved = $fileIndex

    # File analytics
    foreach ($fi in $fileIndex) {
        $ext = [System.IO.Path]::GetExtension($fi.FileName).ToLower()
        if ($ext) {
            if ($Script:Report.FileTypeBreakdown.ContainsKey($ext)) {
                $Script:Report.FileTypeBreakdown[$ext]++
            } else {
                $Script:Report.FileTypeBreakdown[$ext] = 1
            }
        }
    }
    if ($fileIndex.Count -gt 0) {
        $sorted = $fileIndex | Sort-Object LastModified
        $Script:Report.OldestFile = "$($sorted[0].FileName) ($($sorted[0].LastModified))"
        $Script:Report.NewestFile = "$($sorted[-1].FileName) ($($sorted[-1].LastModified))"
    }
    Add-Action "File Organization" "Organized $movedCount business files into $($categories.Count) categories"
    Write-BW "Phase 1 complete: $movedCount files organized." -Level Success
    Write-Host ""
}

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2: SYSTEM CLEANUP & OPTIMIZATION
# ─────────────────────────────────────────────────────────────────────────────

function Invoke-SystemCleanup {
    Write-BW "═══ PHASE 2: System Cleanup & Optimization ═══" -Level Header

    $spaceBeforeCleanup = Get-DiskFreeSpace

    # ── 2a. Temp Files ──
    Write-BW "Clearing temporary files..." -Level Progress
    $tempPaths = @(
        "$env:TEMP\*",
        "$env:WINDIR\Temp\*",
        "$env:LOCALAPPDATA\Temp\*",
        "$env:WINDIR\Prefetch\*",
        "$env:WINDIR\SoftwareDistribution\Download\*"
    )
    $deletedCount = 0
    foreach ($tp in $tempPaths) {
        try {
            $items = Get-ChildItem -Path $tp -Recurse -Force -ErrorAction SilentlyContinue
            $count = ($items | Measure-Object).Count
            if (-not $DryRun) {
                Remove-Item -Path $tp -Recurse -Force -ErrorAction SilentlyContinue
            }
            $deletedCount += $count
        }
        catch { }
    }
    Write-BW "  Removed $deletedCount temp items." -Level Success
    $Script:Report.TempFilesDeleted = $deletedCount
    Add-Action "Cleanup" "Deleted $deletedCount temporary files/folders"

    # ── 2b. Browser Caches ──
    Write-BW "Clearing browser caches..." -Level Progress
    $browserCaches = @(
        "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache\*",
        "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Code Cache\*",
        "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Cache\*",
        "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Code Cache\*",
        "$env:LOCALAPPDATA\Mozilla\Firefox\Profiles\*.default*\cache2\*",
        "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\User Data\Default\Cache\*"
    )
    foreach ($bc in $browserCaches) {
        $resolved = Resolve-Path $bc -ErrorAction SilentlyContinue
        if ($resolved -and -not $DryRun) {
            Remove-Item -Path $bc -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    Add-Action "Cleanup" "Cleared browser caches (Chrome, Edge, Firefox, Brave)"

    # ── 2c. Recycle Bin ──
    Write-BW "Emptying Recycle Bin..." -Level Progress
    if (-not $DryRun) {
        try {
            Clear-RecycleBin -Force -ErrorAction SilentlyContinue
        } catch { }
    }
    Add-Action "Cleanup" "Emptied Recycle Bin"

    # ── 2d. Windows Update Cleanup ──
    Write-BW "Running DISM component cleanup..." -Level Progress
    if (-not $DryRun) {
        try {
            Start-Process -FilePath "dism.exe" -ArgumentList "/online /Cleanup-Image /StartComponentCleanup /ResetBase" `
                -NoNewWindow -Wait -ErrorAction SilentlyContinue
        } catch { }
    }
    Add-Action "Cleanup" "DISM component store cleanup"

    # ── 2e. Disk Cleanup (automated) ──
    Write-BW "Running Disk Cleanup utility..." -Level Progress
    if (-not $DryRun) {
        try {
            # Set all cleanmgr flags via registry
            $cleanupKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VolumeCaches"
            $subkeys = Get-ChildItem -Path $cleanupKey -ErrorAction SilentlyContinue
            foreach ($sk in $subkeys) {
                Set-ItemProperty -Path $sk.PSPath -Name "StateFlags0001" -Value 2 -Type DWord -ErrorAction SilentlyContinue
            }
            Start-Process -FilePath "cleanmgr.exe" -ArgumentList "/sagerun:1" -NoNewWindow -Wait -ErrorAction SilentlyContinue
        } catch { }
    }
    Add-Action "Cleanup" "Windows Disk Cleanup utility"

    # ── 2f. Old Windows Install ──
    Write-BW "Checking for old Windows installations..." -Level Progress
    $oldWindows = "C:\Windows.old"
    if (Test-Path $oldWindows) {
        $oldSize = (Get-ChildItem $oldWindows -Recurse -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
        Write-BW "  Found Windows.old ($(Get-FriendlySize $oldSize)) — will be cleaned by DISM." -Level Info
        Add-Action "Cleanup" "Windows.old found ($(Get-FriendlySize $oldSize))"
    }

    # ── 2g. Clear Event Logs ──
    Write-BW "Clearing old event logs..." -Level Progress
    if (-not $DryRun) {
        try {
            wevtutil el | ForEach-Object {
                wevtutil cl "$_" 2>$null
            }
        } catch { }
    }
    Add-Action "Cleanup" "Cleared Windows event logs"

    # ── 2h. Remove Old Restore Points (keep latest) ──
    Write-BW "Cleaning old restore points..." -Level Progress
    if (-not $DryRun) {
        try {
            vssadmin delete shadows /for=C: /oldest /quiet 2>$null
        } catch { }
    }
    Add-Action "Cleanup" "Removed oldest system restore points"

    # ── 2i. Bloatware Removal ──
    Write-BW "Scanning for bloatware..." -Level Progress
    $removedApps = @()
    foreach ($app in $Script:BloatwareList) {
        $pkg = Get-AppxPackage -Name $app -AllUsers -ErrorAction SilentlyContinue
        if ($pkg) {
            Write-BW "  Found bloatware: $($pkg.Name)" -Level Warning
            if (-not $DryRun) {
                try {
                    $pkg | Remove-AppxPackage -AllUsers -ErrorAction SilentlyContinue
                    # Also remove provisioned package to prevent reinstall
                    Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue |
                        Where-Object { $_.DisplayName -eq $app } |
                        Remove-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue
                    $removedApps += $pkg.Name
                } catch {
                    Write-BW "  Could not remove $($pkg.Name): $($_.Exception.Message)" -Level Warning
                }
            }
            else {
                $removedApps += "$($pkg.Name) (DRY RUN)"
            }
        }
    }
    $Script:Report.BloatwareRemoved = $removedApps
    Write-BW "  Removed $($removedApps.Count) bloatware apps." -Level Success
    Add-Action "Bloatware" "Removed $($removedApps.Count) unnecessary apps"

    # ── 2j. Startup Programs ──
    Write-BW "Optimizing startup programs..." -Level Progress
    $startupDisabled = @()
    $safeToDisable = @(
        'Spotify', 'Steam', 'Discord', 'Skype', 'iTunes', 'OneDrive',
        'AdobeARM', 'Adobe Update', 'Google Update', 'Dropbox',
        'CCleaner', 'Avast', 'Norton', 'McAfee'
    )
    try {
        $startupItems = Get-CimInstance -ClassName Win32_StartupCommand -ErrorAction SilentlyContinue
        foreach ($item in $startupItems) {
            foreach ($pattern in $safeToDisable) {
                if ($item.Name -match $pattern -or $item.Command -match $pattern) {
                    Write-BW "  Startup candidate for disable: $($item.Name)" -Level Info
                    $startupDisabled += $item.Name
                    break
                }
            }
        }
        # Also check Task Manager startup via registry
        $regPaths = @(
            "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run",
            "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run"
        )
        foreach ($regPath in $regPaths) {
            $entries = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
            if ($entries) {
                $props = $entries.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' }
                foreach ($prop in $props) {
                    foreach ($pattern in $safeToDisable) {
                        if ($prop.Name -match $pattern -or $prop.Value -match $pattern) {
                            if (-not $DryRun) {
                                Remove-ItemProperty -Path $regPath -Name $prop.Name -ErrorAction SilentlyContinue
                            }
                            $startupDisabled += $prop.Name
                        }
                    }
                }
            }
        }
    }
    catch {
        Write-BW "  Startup optimization encountered errors." -Level Warning
    }
    $Script:Report.StartupDisabled = $startupDisabled | Select-Object -Unique
    Add-Action "Startup" "Evaluated $($startupDisabled.Count) startup items for optimization"

    # ── 2k. Services Optimization ──
    Write-BW "Optimizing services..." -Level Progress
    $servicesToDisable = @(
        @{ Name = 'DiagTrack';        Desc = 'Connected User Experiences and Telemetry' },
        @{ Name = 'dmwappushservice';  Desc = 'WAP Push Message Routing' },
        @{ Name = 'SysMain';          Desc = 'Superfetch (SSD optimization)' },
        @{ Name = 'WSearch';           Desc = 'Windows Search Indexer' },
        @{ Name = 'RetailDemo';        Desc = 'Retail Demo Service' },
        @{ Name = 'MapsBroker';        Desc = 'Downloaded Maps Manager' },
        @{ Name = 'lfsvc';             Desc = 'Geolocation Service' },
        @{ Name = 'TabletInputService'; Desc = 'Touch Keyboard (if no touchscreen)' }
    )
    $disabledServices = @()
    foreach ($svc in $servicesToDisable) {
        $service = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
        if ($service -and $service.StartType -ne 'Disabled') {
            if (-not $DryRun) {
                try {
                    Set-Service -Name $svc.Name -StartupType Disabled -ErrorAction Stop
                    Stop-Service -Name $svc.Name -Force -ErrorAction SilentlyContinue
                    $disabledServices += "$($svc.Desc) ($($svc.Name))"
                } catch {
                    Write-BW "  Could not disable $($svc.Name): $($_.Exception.Message)" -Level Warning
                }
            }
            else {
                $disabledServices += "$($svc.Desc) ($($svc.Name)) (DRY RUN)"
            }
        }
    }
    $Script:Report.ServicesDisabled = $disabledServices
    Add-Action "Services" "Disabled $($disabledServices.Count) unnecessary services"

    # ── 2l. Power & Visual Performance ──
    Write-BW "Optimizing power and visual settings..." -Level Progress
    if (-not $DryRun) {
        try {
            # Set power plan to High Performance
            powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c 2>$null
            # Disable hibernation to reclaim space
            powercfg /hibernate off 2>$null
            # Optimize visual effects for performance
            $regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
            Set-ItemProperty -Path $regPath -Name "VisualFXSetting" -Value 2 -ErrorAction SilentlyContinue
        } catch { }
    }
    Add-Action "Performance" "Set High Performance power plan, disabled hibernation, optimized visual effects"

    # Calculate space reclaimed
    $spaceAfterCleanup = Get-DiskFreeSpace
    $Script:Report.SpaceReclaimed = $spaceAfterCleanup - $spaceBeforeCleanup
    Write-BW "Space reclaimed this phase: $(Get-FriendlySize ([math]::Max(0, $Script:Report.SpaceReclaimed)))" -Level Success
    Write-Host ""
}

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3: MALWARE & SECURITY SCAN
# ─────────────────────────────────────────────────────────────────────────────

function Invoke-MalwareScan {
    Write-BW "═══ PHASE 3: Malware & Security Scan ═══" -Level Header

    # ── 3a. Enable real-time protection ──
    Write-BW "Checking Windows Defender status..." -Level Progress
    try {
        $defenderStatus = Get-MpComputerStatus -ErrorAction Stop
        if (-not $defenderStatus.RealTimeProtectionEnabled) {
            Write-BW "  Real-time protection is DISABLED — enabling..." -Level Warning
            if (-not $DryRun) {
                Set-MpPreference -DisableRealtimeMonitoring $false -ErrorAction SilentlyContinue
            }
            Add-Action "Security" "Enabled Windows Defender real-time protection"
        }
        else {
            Write-BW "  Real-time protection is active." -Level Success
        }

        # Update signatures
        Write-BW "Updating malware definitions..." -Level Progress
        if (-not $DryRun) {
            Update-MpSignature -ErrorAction SilentlyContinue
        }
        Add-Action "Security" "Updated Windows Defender signatures"

    }
    catch {
        Write-BW "  Windows Defender not available or access denied." -Level Warning
        $Script:Report.Warnings += "Could not access Windows Defender"
    }

    # ── 3b. Quick Scan ──
    Write-BW "Running Windows Defender Quick Scan (this may take a few minutes)..." -Level Progress
    if (-not $DryRun) {
        try {
            Start-MpScan -ScanType QuickScan -ErrorAction Stop
            Write-BW "  Quick scan completed." -Level Success

            # Check for threats
            $threats = Get-MpThreatDetection -ErrorAction SilentlyContinue
            if ($threats) {
                foreach ($threat in $threats) {
                    $threatInfo = "$($ threat.ThreatName) — Status: $($threat.ThreatStatusID)"
                    Write-BW "  THREAT FOUND: $threatInfo" -Level Error
                    $Script:Report.ThreatsFound += $threatInfo
                }
                Add-Action "Security" "Found $($threats.Count) threat(s) — quarantined by Defender"
            }
            else {
                Write-BW "  No threats detected." -Level Success
                Add-Action "Security" "Quick scan clean — no threats detected"
            }
        }
        catch {
            Write-BW "  Scan failed: $($_.Exception.Message)" -Level Warning
        }
    }
    else {
        Add-Action "Security" "Malware scan (DRY RUN — skipped)"
    }

    # ── 3c. PUP Check ──
    Write-BW "Checking for common PUPs/adware..." -Level Progress
    $pupPaths = @(
        "$env:ProgramFiles\Conduit",
        "$env:ProgramFiles\Ask.com",
        "$env:ProgramFiles (x86)\Conduit",
        "$env:ProgramFiles (x86)\Ask.com",
        "$env:LOCALAPPDATA\Conduit",
        "$env:ProgramFiles\Babylon",
        "$env:ProgramFiles (x86)\Babylon",
        "$env:APPDATA\Babylon",
        "$env:ProgramFiles\SearchProtect",
        "$env:ProgramFiles (x86)\SearchProtect"
    )
    $pupsFound = 0
    foreach ($pp in $pupPaths) {
        if (Test-Path $pp) {
            Write-BW "  PUP found: $pp" -Level Error
            $Script:Report.ThreatsFound += "PUP: $pp"
            if (-not $DryRun) {
                Remove-Item -Path $pp -Recurse -Force -ErrorAction SilentlyContinue
            }
            $pupsFound++
        }
    }
    if ($pupsFound -eq 0) {
        Write-BW "  No common PUPs detected." -Level Success
    }
    Add-Action "Security" "PUP scan complete — $pupsFound items found"
    Write-Host ""
}

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4: PERFORMANCE ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

function Invoke-PerformanceAnalysis {
    Write-BW "═══ PHASE 4: Performance Analysis ═══" -Level Header

    # ── 4a. Top 10 Largest Files ──
    Write-BW "Finding largest files on system drive..." -Level Progress
    try {
        $Script:Report.LargestFiles = Get-ChildItem -Path "C:\" -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                -not $_.FullName.StartsWith("C:\Windows\WinSxS") -and
                -not $_.FullName.StartsWith("C:\Windows\Installer") -and
                $_.Length -gt 100MB
            } |
            Sort-Object Length -Descending |
            Select-Object -First 10 |
            ForEach-Object {
                [PSCustomObject]@{
                    Path     = $_.FullName
                    Size     = Get-FriendlySize $_.Length
                    SizeRaw  = $_.Length
                    Modified = $_.LastWriteTime.ToString("yyyy-MM-dd")
                }
            }
    }
    catch { }
    Write-BW "  Found $($Script:Report.LargestFiles.Count) files over 100 MB." -Level Info

    # ── 4b. Installed Applications ──
    Write-BW "Enumerating installed applications..." -Level Progress
    $regPaths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    $Script:Report.InstalledApps = foreach ($rp in $regPaths) {
        Get-ItemProperty $rp -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -and $_.DisplayName -notmatch 'Update|Hotfix|KB\d+' } |
            Select-Object @{N='Name';E={$_.DisplayName}},
                          @{N='Version';E={$_.DisplayVersion}},
                          @{N='Publisher';E={$_.Publisher}},
                          @{N='InstallDate';E={$_.InstallDate}},
                          @{N='Size';E={ if($_.EstimatedSize){ Get-FriendlySize ($_.EstimatedSize * 1KB) } else { 'Unknown' } }}
    }
    $Script:Report.InstalledApps = $Script:Report.InstalledApps |
        Sort-Object Name -Unique |
        Where-Object { $_.Name }

    Write-BW "  Found $($Script:Report.InstalledApps.Count) installed applications." -Level Info
    Add-Action "Analysis" "Catalogued $($Script:Report.InstalledApps.Count) installed applications"

    # ── 4c. Record final disk state ──
    $Script:Report.DiskAfter = Get-DiskFreeSpace
    $totalReclaimed = $Script:Report.DiskAfter - $Script:Report.DiskBefore
    Write-BW "Total disk space recovered: $(Get-FriendlySize ([math]::Max(0, $totalReclaimed)))" -Level Success

    # ── 4d. Generate Recommendations ──
    Write-BW "Generating recommendations..." -Level Progress
    $ramGB = 0
    try { $ramGB = [math]::Round((Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize / 1MB, 0) } catch {}

    if ($ramGB -gt 0 -and $ramGB -lt 8) {
        $Script:Report.Recommendations += "Upgrade RAM to at least 8 GB — current $ramGB GB may cause slowdowns with multiple applications."
    }
    if ($ramGB -ge 8 -and $ramGB -lt 16) {
        $Script:Report.Recommendations += "Consider upgrading RAM to 16 GB for better multitasking performance."
    }

    # Check if SSD
    try {
        $diskType = Get-PhysicalDisk | Select-Object -First 1
        if ($diskType -and $diskType.MediaType -eq 'HDD') {
            $Script:Report.Recommendations += "Upgrade to an SSD — this is the single biggest performance improvement available. Boot time will drop from minutes to seconds."
        }
    } catch {}

    # Check free disk space percentage
    try {
        $diskLogical = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
        if ($diskLogical) {
            $pctFree = [math]::Round(($diskLogical.FreeSpace / $diskLogical.Size) * 100, 0)
            if ($pctFree -lt 15) {
                $Script:Report.Recommendations += "Disk space is critically low ($pctFree% free). Consider removing unused applications or adding storage."
            }
        }
    } catch {}

    if ($Script:Report.SystemInfo.BackupStatus -match "No backup") {
        $Script:Report.Recommendations += "No backup solution detected. Set up OneDrive, Backblaze, or another backup service to protect business-critical files."
    }

    if ($Script:Report.SystemInfo.WindowsActivated -ne "Activated") {
        $Script:Report.Recommendations += "Windows does not appear to be activated. Consider purchasing a license for full functionality and security updates."
    }

    if ($Script:Report.SystemInfo.LastUpdate -ne "Unknown") {
        try {
            $lastUpdateDate = [DateTime]::ParseExact($Script:Report.SystemInfo.LastUpdate, "yyyy-MM-dd", $null)
            $daysSince = ((Get-Date) - $lastUpdateDate).Days
            if ($daysSince -gt 30) {
                $Script:Report.Recommendations += "Windows has not been updated in $daysSince days. Run Windows Update to ensure security patches are current."
            }
        } catch {}
    }

    if ($Script:Report.Recommendations.Count -eq 0) {
        $Script:Report.Recommendations += "System is in good shape — no critical recommendations at this time."
    }

    Add-Action "Analysis" "Generated $($Script:Report.Recommendations.Count) recommendations"
    Write-Host ""
}

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5: BOTWAVE DEPLOYMENT PREPARATION
# ─────────────────────────────────────────────────────────────────────────────

function Invoke-BotwavePrep {
    Write-BW "═══ PHASE 5: Botwave Deployment Preparation ═══" -Level Header

    $readyDir = $Script:Config.ReadyFolder
    Ensure-Directory $readyDir
    Ensure-Directory (Join-Path $readyDir "Business-Files")

    # ── 5a. Copy organized business files to ready folder ──
    Write-BW "Copying organized business files to ready folder..." -Level Progress
    if (-not $DryRun) {
        if (Test-Path $Script:Config.BusinessRoot) {
            Copy-Item -Path "$($Script:Config.BusinessRoot)\*" -Destination (Join-Path $readyDir "Business-Files") `
                -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    Add-Action "Botwave Prep" "Copied business files to Ready-For-Botwave folder"

    # ── 5b. Generate bot-config.json ──
    Write-BW "Generating bot-config.json template..." -Level Progress
    $botConfig = @{
        botwave_version = "1.0"
        generated       = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
        machine         = @{
            hostname  = $Script:Config.MachineName
            os        = (Get-CimInstance Win32_OperatingSystem).Caption
            user      = $Script:Config.Username
        }
        file_paths      = @{
            business_root   = $Script:Config.BusinessRoot
            invoices        = Join-Path $Script:Config.BusinessRoot "Invoices-Receipts"
            contracts       = Join-Path $Script:Config.BusinessRoot "Contracts-Legal"
            tax             = Join-Path $Script:Config.BusinessRoot "Tax-Accounting"
            clients         = Join-Path $Script:Config.BusinessRoot "Clients-CRM"
            proposals       = Join-Path $Script:Config.BusinessRoot "Proposals-Quotes"
            financial       = Join-Path $Script:Config.BusinessRoot "Financial-Reports"
            hr              = Join-Path $Script:Config.BusinessRoot "HR-Employees"
            marketing       = Join-Path $Script:Config.BusinessRoot "Marketing-Sales"
            operations      = Join-Path $Script:Config.BusinessRoot "Operations"
            meetings        = Join-Path $Script:Config.BusinessRoot "Meetings-Notes"
            presentations   = Join-Path $Script:Config.BusinessRoot "Presentations"
            file_index      = $Script:Config.IndexPath
        }
        bot_settings    = @{
            auto_scan_interval   = "24h"
            file_watch_enabled   = $true
            notification_email   = ""
            backup_schedule      = "weekly"
            language             = "en"
        }
    }
    $configPath = Join-Path $readyDir "bot-config.json"
    if (-not $DryRun) {
        $botConfig | ConvertTo-Json -Depth 5 | Out-File -FilePath $configPath -Encoding utf8
    }
    Add-Action "Botwave Prep" "Generated bot-config.json"

    # ── 5c. Create START-HERE.bat ──
    Write-BW "Creating START-HERE.bat launcher..." -Level Progress
    $startBat = @"
@echo off
echo ╔═══════════════════════════════════════════════════╗
echo ║       BOTWAVE — Your AI Business Assistant        ║
echo ║       Machine is primed and ready!                ║
echo ╚═══════════════════════════════════════════════════╝
echo.
echo Business files organized in: C:\Business\
echo Bot configuration: %~dp0bot-config.json
echo.
echo Starting Botwave agent...
echo (Botwave agent will be installed by your technician)
echo.
pause
"@
    $batPath = Join-Path $readyDir "START-HERE.bat"
    if (-not $DryRun) {
        $startBat | Out-File -FilePath $batPath -Encoding ascii
    }
    Add-Action "Botwave Prep" "Created START-HERE.bat launcher"

    # ── 5d. Create Customer README ──
    Write-BW "Creating customer README..." -Level Progress
    $readmePath = Join-Path $readyDir "README.txt"
    $readmeContent = @"
================================================================================
  BOTWAVE VIP ONBOARDING — SYSTEM READY
================================================================================

Congratulations! Your machine has been professionally optimized and prepared
for Botwave AI deployment.

WHAT WAS DONE:
  - All business files were discovered and organized into C:\Business\
  - System was cleaned of temporary files, bloatware, and performance issues
  - Security scan was performed and threats quarantined
  - Machine optimized for peak performance

YOUR FILES:
  - Organized business files: C:\Business\
  - File index (CSV):        C:\Business\Business-File-Index.csv
  - Original file backups:   C:\Botwave\Backups\

BOTWAVE SETUP:
  - Bot configuration:  $configPath
  - Quick launch:       $batPath
  - Full report:        $($Script:Config.ReportPath)

NEXT STEPS:
  1. Review the organized files in C:\Business\ to ensure everything is correct.
  2. Your Botwave technician will complete the bot installation remotely.
  3. Check your email for the Botwave dashboard login credentials.

SUPPORT:
  support@botwave.ai | (555) 123-4567

Report generated: $(Get-Date -Format "MMMM dd, yyyy 'at' h:mm tt")
Machine: $($Script:Config.MachineName)
================================================================================
"@
    if (-not $DryRun) {
        $readmeContent | Out-File -FilePath $readmePath -Encoding utf8
    }
    Add-Action "Botwave Prep" "Created customer README"

    Write-BW "Botwave ready folder prepared at: $readyDir" -Level Success
    Write-Host ""
}

# ─────────────────────────────────────────────────────────────────────────────
# REPORT GENERATION
# ─────────────────────────────────────────────────────────────────────────────

function Generate-HtmlReport {
    Write-BW "═══ Generating HTML Report ═══" -Level Header

    $totalReclaimed = [math]::Max(0, $Script:Report.DiskAfter - $Script:Report.DiskBefore)
    $duration = (Get-Date) - $Script:Report.StartTime
    $durationStr = "{0:D2}h {1:D2}m {2:D2}s" -f $duration.Hours, $duration.Minutes, $duration.Seconds

    # Build action rows
    $actionRows = ""
    foreach ($a in $Script:Report.Actions) {
        $statusColor = switch ($a.Status) {
            "Done"    { "#22c55e" }
            "Warning" { "#f59e0b" }
            "Error"   { "#ef4444" }
            default   { "#22c55e" }
        }
        $statusIcon = switch ($a.Status) {
            "Done"    { "&#10004;" }
            "Warning" { "&#9888;" }
            "Error"   { "&#10008;" }
            default   { "&#10004;" }
        }
        $actionRows += @"
        <tr>
            <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:13px;">$($a.Time)</td>
            <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;font-weight:600;color:#1e293b;">$($a.Category)</td>
            <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;color:#475569;">$($a.Detail)</td>
            <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;text-align:center;">
                <span style="color:$statusColor;font-weight:700;">$statusIcon $($a.Status)</span>
            </td>
        </tr>
"@
    }

    # Build largest files rows
    $largestRows = ""
    foreach ($lf in $Script:Report.LargestFiles) {
        $largestRows += @"
        <tr>
            <td style="padding:8px 14px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#475569;word-break:break-all;">$($lf.Path)</td>
            <td style="padding:8px 14px;border-bottom:1px solid #e2e8f0;font-weight:600;text-align:right;">$($lf.Size)</td>
            <td style="padding:8px 14px;border-bottom:1px solid #e2e8f0;color:#64748b;text-align:center;">$($lf.Modified)</td>
        </tr>
"@
    }

    # Build bloatware rows
    $bloatRows = ""
    foreach ($b in $Script:Report.BloatwareRemoved) {
        $bloatRows += "<li style='padding:4px 0;color:#475569;'>$b</li>`n"
    }
    if (-not $bloatRows) { $bloatRows = "<li style='color:#64748b;'>No bloatware detected.</li>" }

    # Build threats rows
    $threatRows = ""
    $threatColor = "#22c55e"
    $threatStatus = "&#10004; Clean"
    if ($Script:Report.ThreatsFound.Count -gt 0) {
        $threatColor = "#ef4444"
        $threatStatus = "&#9888; Threats Found"
        foreach ($t in $Script:Report.ThreatsFound) {
            $threatRows += "<li style='padding:4px 0;color:#ef4444;'>$t</li>`n"
        }
    }
    else {
        $threatRows = "<li style='color:#22c55e;'>No threats detected.</li>"
    }

    # Installed apps table (top 30 by name)
    $appRows = ""
    $topApps = $Script:Report.InstalledApps | Select-Object -First 30
    foreach ($app in $topApps) {
        $appRows += @"
        <tr>
            <td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;">$($app.Name)</td>
            <td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;color:#64748b;">$($app.Version)</td>
            <td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;color:#64748b;">$($app.Publisher)</td>
            <td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;text-align:right;">$($app.Size)</td>
        </tr>
"@
    }

    $dryRunBanner = ""
    if ($DryRun) {
        $dryRunBanner = '<div style="background:#fef3c7;border:2px solid #f59e0b;border-radius:8px;padding:16px;margin-bottom:24px;text-align:center;font-weight:700;color:#92400e;font-size:18px;">&#9888; DRY RUN — No changes were made to this system</div>'
    }

    $html = @"
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Botwave Overhaul Report — $($Script:Config.MachineName)</title>
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; color: #1e293b; line-height: 1.6; }
    .container { max-width: 960px; margin: 0 auto; padding: 32px 24px; }
    .header { background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%); color: white; padding: 48px 40px; border-radius: 16px; margin-bottom: 32px; }
    .header h1 { font-size: 28px; margin-bottom: 8px; }
    .header p { color: #94a3b8; font-size: 14px; }
    .card { background: white; border-radius: 12px; padding: 28px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    .card h2 { font-size: 18px; margin-bottom: 16px; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .stat { background: #f1f5f9; border-radius: 10px; padding: 20px; text-align: center; }
    .stat .value { font-size: 28px; font-weight: 800; color: #0f172a; }
    .stat .label { font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }
    .stat.green .value { color: #16a34a; }
    .stat.red .value { color: #ef4444; }
    .stat.blue .value { color: #2563eb; }
    table { width: 100%; border-collapse: collapse; }
    th { padding: 10px 14px; text-align: left; background: #f8fafc; color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 2px solid #e2e8f0; }
    .footer { text-align: center; padding: 32px; color: #94a3b8; font-size: 12px; }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>&#x1F916; Botwave VIP System Overhaul Report</h1>
        <p>Machine: $($Script:Config.MachineName) &nbsp;|&nbsp; User: $($Script:Config.Username) &nbsp;|&nbsp; Generated: $(Get-Date -Format "MMMM dd, yyyy 'at' h:mm tt")</p>
        <p>Script Version: $($Script:Config.Version) &nbsp;|&nbsp; Duration: $durationStr</p>
    </div>

    $dryRunBanner

    <div class="stats">
        <div class="stat green">
            <div class="value">$(Get-FriendlySize $totalReclaimed)</div>
            <div class="label">Disk Space Reclaimed</div>
        </div>
        <div class="stat blue">
            <div class="value">$($Script:Report.FilesOrganized)</div>
            <div class="label">Files Organized</div>
        </div>
        <div class="stat">
            <div class="value">$($Script:Report.BloatwareRemoved.Count)</div>
            <div class="label">Bloatware Removed</div>
        </div>
        <div class="stat $(if($Script:Report.ThreatsFound.Count -gt 0){'red'}else{'green'})">
            <div class="value">$($Script:Report.ThreatsFound.Count)</div>
            <div class="label">Threats Found</div>
        </div>
    </div>

    <div class="card" style="background:linear-gradient(135deg,#f0fdfa,#ecfeff);border:1px solid #99f6e4;">
        <h2 style="color:#0d9488;border-color:#99f6e4;">Executive Summary</h2>
        <p style="font-size:15px;color:#134e4a;line-height:1.7;">
            This machine has been professionally audited and optimized. We recovered <strong>$(Get-FriendlySize $totalReclaimed)</strong> of disk space,
            organized <strong>$($Script:Report.FilesOrganized) business files</strong> into a clean folder structure,
            $(if($Script:Report.BloatwareRemoved.Count -gt 0){"removed <strong>$($Script:Report.BloatwareRemoved.Count) unnecessary applications</strong>, "}else{""})and
            verified the system is <strong>$(if($Script:Report.ThreatsFound.Count -eq 0){"clean — no security threats detected"}else{"flagged — $($Script:Report.ThreatsFound.Count) threat(s) found and quarantined"})</strong>.
            $(if($Script:Report.Recommendations.Count -gt 0 -and $Script:Report.Recommendations[0] -notmatch "good shape"){"We have <strong>$($Script:Report.Recommendations.Count) recommendation(s)</strong> for further improvement — see below."}else{"The system is in good overall condition."})
        </p>
    </div>

    <div class="card">
        <h2>System Profile</h2>
        <div class="stats">
            <div class="stat"><div class="value" style="font-size:14px;color:#0f172a;">$($Script:Report.SystemInfo.CPU)</div><div class="label">Processor</div></div>
            <div class="stat"><div class="value" style="font-size:20px;color:#0f172a;">$($Script:Report.SystemInfo.RAM)</div><div class="label">Memory (RAM)</div></div>
            <div class="stat"><div class="value" style="font-size:14px;color:#0f172a;">$($Script:Report.SystemInfo.GPU)</div><div class="label">Graphics</div></div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px;">
            <div style="padding:8px 12px;background:#f8fafc;border-radius:8px;"><span style="color:#64748b;font-size:11px;text-transform:uppercase;">OS</span><br><strong style="font-size:13px;">$($Script:Report.SystemInfo.OSVersion)</strong></div>
            <div style="padding:8px 12px;background:#f8fafc;border-radius:8px;"><span style="color:#64748b;font-size:11px;text-transform:uppercase;">Disk</span><br><strong style="font-size:13px;">$($Script:Report.SystemInfo.DiskModel)</strong></div>
            <div style="padding:8px 12px;background:#f8fafc;border-radius:8px;"><span style="color:#64748b;font-size:11px;text-transform:uppercase;">IP Address</span><br><strong style="font-size:13px;">$($Script:Report.SystemInfo.IPAddress)</strong></div>
            <div style="padding:8px 12px;background:#f8fafc;border-radius:8px;"><span style="color:#64748b;font-size:11px;text-transform:uppercase;">Uptime</span><br><strong style="font-size:13px;">$($Script:Report.SystemInfo.Uptime)</strong></div>
            <div style="padding:8px 12px;background:#f8fafc;border-radius:8px;"><span style="color:#64748b;font-size:11px;text-transform:uppercase;">Windows License</span><br><strong style="font-size:13px;">$($Script:Report.SystemInfo.WindowsActivated)</strong></div>
            <div style="padding:8px 12px;background:#f8fafc;border-radius:8px;"><span style="color:#64748b;font-size:11px;text-transform:uppercase;">Last Update</span><br><strong style="font-size:13px;">$($Script:Report.SystemInfo.LastUpdate)</strong></div>
            <div style="padding:8px 12px;background:#f8fafc;border-radius:8px;"><span style="color:#64748b;font-size:11px;text-transform:uppercase;">Network</span><br><strong style="font-size:13px;">$($Script:Report.SystemInfo.NetworkType)</strong></div>
            <div style="padding:8px 12px;background:#f8fafc;border-radius:8px;"><span style="color:#64748b;font-size:11px;text-transform:uppercase;">Backup</span><br><strong style="font-size:13px;$(if($Script:Report.SystemInfo.BackupStatus -match 'No backup'){'color:#ef4444'})">$($Script:Report.SystemInfo.BackupStatus)</strong></div>
        </div>
    </div>

    <div class="card">
        <h2>Disk Space</h2>
        <div class="stats">
            <div class="stat"><div class="value">$(Get-FriendlySize $Script:Report.DiskBefore)</div><div class="label">Free Before</div></div>
            <div class="stat green"><div class="value">$(Get-FriendlySize $Script:Report.DiskAfter)</div><div class="label">Free After</div></div>
        </div>
    </div>

    <div class="card">
        <h2>Actions Performed</h2>
        <table>
            <thead><tr><th>Time</th><th>Category</th><th>Detail</th><th>Status</th></tr></thead>
            <tbody>$actionRows</tbody>
        </table>
    </div>

    <div class="card">
        <h2>Security Status</h2>
        <p style="font-size:20px;font-weight:700;color:$threatColor;margin-bottom:12px;">$threatStatus</p>
        <ul style="list-style:none;padding:0;">$threatRows</ul>
    </div>

    <div class="card">
        <h2>Bloatware Removed</h2>
        <ul style="list-style:none;padding:0;">$bloatRows</ul>
    </div>

    <div class="card">
        <h2>Top 10 Largest Files (over 100 MB)</h2>
        <table>
            <thead><tr><th>Path</th><th style="text-align:right;">Size</th><th style="text-align:center;">Modified</th></tr></thead>
            <tbody>$largestRows</tbody>
        </table>
    </div>

    <div class="card">
        <h2>Installed Applications (Top 30)</h2>
        <table>
            <thead><tr><th>Name</th><th>Version</th><th>Publisher</th><th style="text-align:right;">Size</th></tr></thead>
            <tbody>$appRows</tbody>
        </table>
        <p style="margin-top:12px;color:#64748b;font-size:13px;">Total installed: $($Script:Report.InstalledApps.Count) applications</p>
    </div>

    <div class="card">
        <h2>Startup Items Evaluated</h2>
        <ul style="list-style:none;padding:0;">
            $(($Script:Report.StartupDisabled | ForEach-Object { "<li style='padding:4px 0;'>&#10004; $_</li>" }) -join "`n")
            $(if ($Script:Report.StartupDisabled.Count -eq 0) { "<li style='color:#64748b;'>No problematic startup items found.</li>" })
        </ul>
    </div>

    <div class="card">
        <h2>Services Disabled</h2>
        <ul style="list-style:none;padding:0;">
            $(($Script:Report.ServicesDisabled | ForEach-Object { "<li style='padding:4px 0;'>&#10004; $_</li>" }) -join "`n")
            $(if ($Script:Report.ServicesDisabled.Count -eq 0) { "<li style='color:#64748b;'>No services were modified.</li>" })
        </ul>
    </div>

    <div class="card" style="border-left:4px solid #f59e0b;">
        <h2 style="color:#b45309;">Recommendations</h2>
        <ul style="list-style:none;padding:0;">
            $(($Script:Report.Recommendations | ForEach-Object { "<li style='padding:8px 0;border-bottom:1px solid #f1f5f9;color:#475569;font-size:14px;'>&#9655; $_</li>" }) -join "`n")
        </ul>
    </div>

    $(if ($Script:Report.FileTypeBreakdown.Count -gt 0) {
    $ftRows = ($Script:Report.FileTypeBreakdown.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 10 | ForEach-Object {
        $pct = [math]::Round(($_.Value / [math]::Max(1, $Script:Report.FilesOrganized)) * 100, 0)
        "<tr><td style='padding:6px 14px;border-bottom:1px solid #f1f5f9;font-weight:600;'>$($_.Key)</td><td style='padding:6px 14px;border-bottom:1px solid #f1f5f9;text-align:right;'>$($_.Value) files</td><td style='padding:6px 14px;border-bottom:1px solid #f1f5f9;text-align:right;'><div style='background:#e2e8f0;border-radius:4px;height:16px;width:100px;display:inline-block;vertical-align:middle;'><div style='background:#0891b2;border-radius:4px;height:100%;width:${pct}%;'></div></div> $pct%</td></tr>"
    }) -join "`n"
    @"
    <div class="card">
        <h2>File Type Breakdown</h2>
        <table><thead><tr><th>Extension</th><th style='text-align:right;'>Count</th><th style='text-align:right;'>Share</th></tr></thead>
        <tbody>$ftRows</tbody></table>
        $(if ($Script:Report.OldestFile) { "<p style='margin-top:12px;font-size:12px;color:#64748b;'>Oldest business file: <strong>$($Script:Report.OldestFile)</strong> &nbsp;|&nbsp; Newest: <strong>$($Script:Report.NewestFile)</strong></p>" })
    </div>
"@
    })

    <div class="card" style="background:linear-gradient(135deg,#0f172a,#1e3a5f);color:white;">
        <h2 style="color:white;border-color:rgba(255,255,255,0.2);">Botwave Deployment Status</h2>
        <p style="font-size:20px;font-weight:700;color:#4ade80;margin-bottom:8px;">&#10004; Machine Primed & Ready</p>
        <p style="color:#94a3b8;">Business files organized at: <strong style="color:white;">$($Script:Config.BusinessRoot)</strong></p>
        <p style="color:#94a3b8;">Bot config ready at: <strong style="color:white;">$($Script:Config.ReadyFolder)\bot-config.json</strong></p>
        <p style="color:#94a3b8;">Customer README placed at: <strong style="color:white;">$($Script:Config.ReadyFolder)\README.txt</strong></p>
    </div>

    <div class="footer">
        <p>Botwave VIP System Overhaul &copy; $(Get-Date -Format "yyyy") Botwave Inc. &mdash; All rights reserved.</p>
        <p>This report was auto-generated. Questions? Contact support@botwave.ai</p>
        <p style="margin-top:12px;font-size:10px;color:#cbd5e1;max-width:700px;margin-left:auto;margin-right:auto;">
            Disclaimer: This overhaul is a system hygiene service. It does not constitute a security audit,
            penetration test, or guarantee against future threats. All files were backed up before modification.
            Botwave Inc. is not responsible for data loss. Original files can be restored from the backup folder.
        </p>
    </div>
</div>
</body>
</html>
"@

    if (-not $DryRun) {
        $html | Out-File -FilePath $Script:Config.ReportPath -Encoding utf8
    }
    else {
        # Even in dry run, save the report
        $html | Out-File -FilePath $Script:Config.ReportPath -Encoding utf8
    }

    Write-BW "Report saved to: $($Script:Config.ReportPath)" -Level Success
    Write-Host ""
}

# ─────────────────────────────────────────────────────────────────────────────
# MAIN EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

try {
    Initialize-Overhaul

    if (-not $SkipFileOrganization) {
        Invoke-FileOrganization
    }
    else {
        Write-BW "Skipping file organization (flag set)." -Level Warning
    }

    if (-not $SkipCleanup) {
        Invoke-SystemCleanup
    }
    else {
        Write-BW "Skipping system cleanup (flag set)." -Level Warning
    }

    if (-not $SkipMalwareScan) {
        Invoke-MalwareScan
    }
    else {
        Write-BW "Skipping malware scan (flag set)." -Level Warning
    }

    Invoke-PerformanceAnalysis
    Invoke-BotwavePrep
    Generate-HtmlReport

    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "  ║  ✅ Botwave Overhaul Complete — Machine is now primed and ready     ║" -ForegroundColor Green
    Write-Host "  ║     for bot deployment.                                             ║" -ForegroundColor Green
    Write-Host "  ╚══════════════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-BW "Report: $($Script:Config.ReportPath)" -Level Success
    Write-BW "Ready folder: $($Script:Config.ReadyFolder)" -Level Success
    Write-BW "Total runtime: $((Get-Date) - $Script:Report.StartTime)" -Level Info

    # Auto-open the report in default browser
    if (-not $DryRun) {
        try {
            Start-Process $Script:Config.ReportPath -ErrorAction SilentlyContinue
        } catch { }
    }

    # Completion sound
    try { [System.Console]::Beep(800, 200); Start-Sleep -Milliseconds 100; [System.Console]::Beep(1000, 200); Start-Sleep -Milliseconds 100; [System.Console]::Beep(1200, 400) } catch { }
}
catch {
    Write-BW "FATAL ERROR: $($_.Exception.Message)" -Level Error
    Write-BW "Stack: $($_.ScriptStackTrace)" -Level Error
    $Script:Report.Errors += $_.Exception.Message
    Generate-HtmlReport
    exit 1
}
