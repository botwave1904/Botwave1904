#!/usr/bin/env python3
"""
Botwave VIP System Overhaul — Cross-Platform Edition
=====================================================
Production-grade system cleanup, file organization, and bot deployment prep.
Works on Linux, macOS, and Windows via Python 3.10+.

Usage:
    python3 botwave-overhaul.py --confirm
    python3 botwave-overhaul.py --dry-run
    python3 botwave-overhaul.py --skip-cleanup --skip-malware --confirm

Version : 2.0.0
Author  : Botwave Engineering
License : Proprietary — Botwave Inc.
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM = platform.system()  # 'Linux', 'Darwin', 'Windows'
IS_WINDOWS = SYSTEM == "Windows"
IS_MAC = SYSTEM == "Darwin"
IS_LINUX = SYSTEM == "Linux"
TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
VERSION = "2.0.0"

if IS_WINDOWS:
    BASE_DIR = Path("C:/Botwave")
    BUSINESS_DIR = Path("C:/Business")
else:
    BASE_DIR = Path.home() / "Botwave"
    BUSINESS_DIR = Path.home() / "Business"

LOG_DIR = BASE_DIR / "Logs"
BACKUP_DIR = BASE_DIR / "Backups"
READY_DIR = BASE_DIR / "Ready-For-Botwave"
REPORT_PATH = LOG_DIR / f"Overhaul-Report-{TIMESTAMP}.html"
LOG_PATH = LOG_DIR / f"Overhaul-Log-{TIMESTAMP}.txt"
INDEX_PATH = BUSINESS_DIR / "Business-File-Index.csv"

# Business file matching
BUSINESS_KEYWORDS = [
    'invoice', 'receipt', 'client', 'contract', 'tax', 'quote', 'proposal',
    'estimate', 'budget', 'payroll', 'expense', 'revenue', 'profit', 'loss',
    'balance', 'ledger', 'journal', 'account', 'billing', 'payment', 'vendor',
    'supplier', 'customer', 'employee', 'hr', 'policy', 'agreement', 'nda',
    'sow', 'scope', 'deliverable', 'milestone', 'timesheet', 'inventory',
    'purchase', 'order', 'shipping', 'logistics', 'marketing', 'sales',
    'report', 'memo', 'meeting', 'minutes', 'agenda', 'presentation',
    'quickbooks', 'xero', 'freshbooks', 'w2', 'w9', '1099', 'schedule-c',
]

BUSINESS_EXTENSIONS = {
    '.xlsx', '.xls', '.docx', '.doc', '.pdf', '.csv', '.pptx', '.ppt',
    '.rtf', '.txt', '.qbw', '.qbb', '.qbx', '.iif',
}

CATEGORY_MAP = {
    'Invoices-Receipts': ['invoice', 'receipt', 'billing', 'payment'],
    'Contracts-Legal':   ['contract', 'agreement', 'nda', 'sow', 'scope', 'legal', 'terms'],
    'Tax-Accounting':    ['tax', 'w2', 'w9', '1099', 'schedule-c', 'ledger', 'journal', 'quickbooks', 'xero'],
    'Clients-CRM':      ['client', 'customer', 'crm', 'lead', 'prospect'],
    'Proposals-Quotes':  ['quote', 'proposal', 'estimate', 'bid'],
    'Financial-Reports': ['budget', 'revenue', 'profit', 'loss', 'balance', 'expense', 'payroll', 'financial'],
    'HR-Employees':      ['employee', 'hr', 'policy', 'timesheet', 'onboarding', 'handbook'],
    'Marketing-Sales':   ['marketing', 'sales', 'campaign', 'brochure', 'flyer'],
    'Operations':        ['inventory', 'purchase', 'order', 'shipping', 'logistics', 'vendor', 'supplier'],
    'Meetings-Notes':    ['meeting', 'minutes', 'agenda', 'notes', 'memo'],
    'Presentations':     ['presentation', 'deck', 'pitch', 'slides'],
}

ALL_CATEGORIES = list(CATEGORY_MAP.keys()) + ['Uncategorized']

# Linux/macOS cleanup paths
LINUX_TEMP_PATHS = [
    '/tmp/*', '/var/tmp/*',
]
MAC_CACHE_PATHS_PATTERNS = [
    '~/Library/Caches/*',
    '~/Library/Logs/*',
]
BROWSER_CACHE_PATTERNS = {
    'chrome': [
        '~/.cache/google-chrome/Default/Cache/*',
        '~/.cache/google-chrome/Default/Code Cache/*',
        '~/Library/Caches/Google/Chrome/Default/Cache/*',
    ],
    'firefox': [
        '~/.cache/mozilla/firefox/*.default*/cache2/*',
        '~/Library/Caches/Firefox/Profiles/*.default*/cache2/*',
    ],
    'edge': [
        '~/.cache/microsoft-edge/Default/Cache/*',
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ActionRecord:
    time: str
    category: str
    detail: str
    status: str = "Done"

@dataclass
class FileRecord:
    filename: str
    category: str
    original_path: str
    new_path: str
    size_kb: float
    last_modified: str

@dataclass
class LargeFile:
    path: str
    size: str
    size_raw: int
    modified: str

@dataclass
class Report:
    start_time: datetime = field(default_factory=datetime.now)
    disk_before: int = 0
    disk_after: int = 0
    files_organized: int = 0
    files_moved: list = field(default_factory=list)
    temp_deleted: int = 0
    space_reclaimed: int = 0
    bloatware_removed: list = field(default_factory=list)
    startup_disabled: list = field(default_factory=list)
    services_disabled: list = field(default_factory=list)
    threats_found: list = field(default_factory=list)
    largest_files: list = field(default_factory=list)
    installed_apps: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    actions: list = field(default_factory=list)

# ─────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

report = Report()
dry_run = False

# Color codes for terminal
class C:
    RESET  = "\033[0m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    MAGENTA= "\033[95m"
    WHITE  = "\033[97m"
    BOLD   = "\033[1m"


def log(msg: str, level: str = "info"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix_map = {
        'info':     (f"{C.CYAN}[*]{C.RESET}", "INFO"),
        'success':  (f"{C.GREEN}[+]{C.RESET}", "OK"),
        'warning':  (f"{C.YELLOW}[!]{C.RESET}", "WARN"),
        'error':    (f"{C.RED}[X]{C.RESET}", "ERR"),
        'header':   (f"{C.MAGENTA}[=]{C.RESET}", "==="),
        'progress': (f"{C.WHITE}[>]{C.RESET}", "..."),
    }
    prefix, _ = prefix_map.get(level, prefix_map['info'])
    line = f"{ts} {prefix} {msg}"
    print(line)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f"{ts} [{level.upper()}] {msg}\n")
    except Exception:
        pass


def add_action(category: str, detail: str, status: str = "Done"):
    report.actions.append(ActionRecord(
        time=datetime.now().strftime("%H:%M:%S"),
        category=category, detail=detail, status=status
    ))


def friendly_size(b: int) -> str:
    if b >= 1_073_741_824:
        return f"{b / 1_073_741_824:.2f} GB"
    if b >= 1_048_576:
        return f"{b / 1_048_576:.2f} MB"
    if b >= 1024:
        return f"{b / 1024:.2f} KB"
    return f"{b} B"


def get_disk_free(path: str = "/") -> int:
    try:
        st = shutil.disk_usage(path if not IS_WINDOWS else "C:\\")
        return st.free
    except Exception:
        return 0


def ensure_dir(p: Path):
    if not p.exists():
        if not dry_run:
            p.mkdir(parents=True, exist_ok=True)
        log(f"Created directory: {p}", "progress")


def run_cmd(cmd: list[str] | str, shell: bool = False, timeout: int = 300) -> tuple[int, str, str]:
    """Run a subprocess command safely. Returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, shell=shell, capture_output=True, text=True,
            timeout=timeout, errors='replace'
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def is_root() -> bool:
    if IS_WINDOWS:
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    return os.geteuid() == 0


def expand_path(pattern: str) -> list[Path]:
    expanded = os.path.expanduser(pattern)
    return [Path(p) for p in glob.glob(expanded, recursive=False)]

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 0: INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def initialize(args):
    global dry_run
    dry_run = args.dry_run

    print()
    print(f"  {C.CYAN}╔══════════════════════════════════════════════════════════════╗{C.RESET}")
    print(f"  {C.CYAN}║       BOTWAVE VIP SYSTEM OVERHAUL v{VERSION}  (Python)        ║{C.RESET}")
    print(f"  {C.CYAN}║       Professional IT Cleanup & Bot Deployment              ║{C.RESET}")
    print(f"  {C.CYAN}║       Platform: {SYSTEM:<44s} ║{C.RESET}")
    print(f"  {C.CYAN}╚══════════════════════════════════════════════════════════════╝{C.RESET}")
    print()

    if dry_run:
        log("DRY RUN MODE — No changes will be made.", "warning")

    if not args.confirm and not dry_run:
        log("ERROR: --confirm flag required for unattended execution.", "error")
        log("Use --dry-run to preview, or add --confirm to proceed.", "info")
        sys.exit(1)

    # Check privileges
    if not is_root() and not dry_run:
        log("WARNING: Not running as root/admin. Some operations may fail.", "warning")
        report.warnings.append("Running without elevated privileges")

    # Create directories
    for d in [BASE_DIR, LOG_DIR, BACKUP_DIR, READY_DIR, BUSINESS_DIR]:
        ensure_dir(d)

    report.disk_before = get_disk_free()
    hostname = socket.gethostname()
    username = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    log(f"Machine: {hostname} | User: {username} | OS: {SYSTEM} {platform.release()}", "info")
    log(f"Disk free: {friendly_size(report.disk_before)}", "info")
    log(f"Report will be saved to: {REPORT_PATH}", "info")
    print()

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1: BUSINESS FILE DISCOVERY & ORGANIZATION
# ─────────────────────────────────────────────────────────────────────────────

def classify_file(filename: str) -> str:
    name_lower = filename.lower()
    for category, keywords in CATEGORY_MAP.items():
        for kw in keywords:
            if kw in name_lower:
                return category
    return "Uncategorized"


def is_business_file(filepath: Path) -> bool:
    # Check extension
    if filepath.suffix.lower() in BUSINESS_EXTENSIONS:
        return True
    # Check keywords
    name_lower = filepath.stem.lower()
    return any(kw in name_lower for kw in BUSINESS_KEYWORDS)


def phase_file_organization():
    log("═══ PHASE 1: Business File Discovery & Organization ═══", "header")

    home = Path.home()
    scan_paths = []

    candidates = [
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
        home / "OneDrive",
    ]

    # Add platform-specific paths
    if IS_MAC:
        candidates.append(Path("/Volumes"))
    elif IS_LINUX:
        candidates.append(Path("/media") / os.getenv("USER", ""))
        candidates.append(Path("/mnt"))
    elif IS_WINDOWS:
        for letter in "DEFGH":
            candidates.append(Path(f"{letter}:\\"))

    for c in candidates:
        if c.exists() and c.is_dir():
            scan_paths.append(c)

    log(f"Scanning {len(scan_paths)} locations for business files...", "progress")

    # Create category folders
    for cat in ALL_CATEGORIES:
        ensure_dir(BUSINESS_DIR / cat)

    backup_original = BACKUP_DIR / f"OriginalFiles-{TIMESTAMP}"
    ensure_dir(backup_original)

    # Scan
    business_files = []
    for scan_path in scan_paths:
        log(f"  Scanning: {scan_path}", "progress")
        try:
            for root, dirs, files in os.walk(scan_path, followlinks=False):
                root_path = Path(root)
                # Skip Botwave/Business own dirs and hidden dirs
                if str(root_path).startswith(str(BASE_DIR)) or str(root_path).startswith(str(BUSINESS_DIR)):
                    continue
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]

                for fname in files:
                    fpath = root_path / fname
                    try:
                        if not fpath.is_file():
                            continue
                        fsize = fpath.stat().st_size
                        if fsize == 0 or fsize > 500_000_000:
                            continue
                        if is_business_file(fpath):
                            category = classify_file(fname)
                            business_files.append((fpath, category))
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError) as e:
            log(f"  Warning: Could not fully scan {scan_path}: {e}", "warning")
            report.warnings.append(f"Scan error: {scan_path}")

    log(f"Found {len(business_files)} business-related files.", "success")

    # Deduplicate
    seen = set()
    unique_files = []
    for fpath, cat in business_files:
        try:
            key = (fpath.name, fpath.stat().st_size)
        except OSError:
            continue
        if key not in seen:
            seen.add(key)
            unique_files.append((fpath, cat))
    log(f"{len(unique_files)} unique files after deduplication.", "info")

    # Move/copy files
    file_index = []
    moved_count = 0
    for fpath, cat in unique_files:
        dest_dir = BUSINESS_DIR / cat
        dest_path = dest_dir / fpath.name

        # Handle collisions
        counter = 1
        while dest_path.exists():
            dest_path = dest_dir / f"{fpath.stem}_{counter}{fpath.suffix}"
            counter += 1

        if not dry_run:
            try:
                shutil.copy2(str(fpath), str(backup_original / fpath.name))
                shutil.copy2(str(fpath), str(dest_path))
                moved_count += 1
            except (PermissionError, OSError, shutil.Error) as e:
                log(f"  Could not process: {fpath}: {e}", "warning")
                continue
        else:
            moved_count += 1

        try:
            stat = fpath.stat()
            file_index.append(FileRecord(
                filename=fpath.name,
                category=cat,
                original_path=str(fpath),
                new_path=str(dest_path),
                size_kb=round(stat.st_size / 1024, 2),
                last_modified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            ))
        except OSError:
            pass

    # Export CSV index
    if file_index and not dry_run:
        try:
            with open(INDEX_PATH, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['FileName', 'Category', 'OriginalPath', 'NewPath', 'SizeKB', 'LastModified'])
                for rec in file_index:
                    writer.writerow([rec.filename, rec.category, rec.original_path,
                                     rec.new_path, rec.size_kb, rec.last_modified])
            log(f"Master index saved: {INDEX_PATH}", "success")
        except Exception as e:
            log(f"Could not save index: {e}", "warning")

    report.files_organized = moved_count
    report.files_moved = file_index
    add_action("File Organization", f"Organized {moved_count} files into {len(ALL_CATEGORIES)} categories")
    log(f"Phase 1 complete: {moved_count} files organized.", "success")
    print()

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2: SYSTEM CLEANUP & OPTIMIZATION
# ─────────────────────────────────────────────────────────────────────────────

def delete_path_contents(pattern: str) -> int:
    """Delete files matching a glob pattern. Returns count deleted."""
    count = 0
    for p in expand_path(pattern):
        try:
            if p.is_file():
                if not dry_run:
                    p.unlink()
                count += 1
            elif p.is_dir():
                if not dry_run:
                    shutil.rmtree(str(p), ignore_errors=True)
                count += 1
        except (PermissionError, OSError):
            pass
    return count


def phase_system_cleanup():
    log("═══ PHASE 2: System Cleanup & Optimization ═══", "header")

    space_before = get_disk_free()
    total_deleted = 0

    # ── Temp files ──
    log("Clearing temporary files...", "progress")
    if IS_WINDOWS:
        temp_patterns = [
            os.path.expandvars(r'%TEMP%\*'),
            os.path.expandvars(r'%WINDIR%\Temp\*'),
            os.path.expandvars(r'%LOCALAPPDATA%\Temp\*'),
        ]
    elif IS_MAC:
        temp_patterns = ['/tmp/*', '~/Library/Caches/*', '~/Library/Logs/*']
    else:
        temp_patterns = ['/tmp/*', '/var/tmp/*']
        # User cache
        temp_patterns.append(os.path.expanduser('~/.cache/*'))

    for pat in temp_patterns:
        total_deleted += delete_path_contents(pat)
    log(f"  Removed {total_deleted} temp items.", "success")
    report.temp_deleted = total_deleted
    add_action("Cleanup", f"Deleted {total_deleted} temporary files/folders")

    # ── Browser caches ──
    log("Clearing browser caches...", "progress")
    for browser, patterns in BROWSER_CACHE_PATTERNS.items():
        for pat in patterns:
            delete_path_contents(pat)
    # Windows-specific browser paths
    if IS_WINDOWS:
        win_browser = [
            os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cache\*'),
            os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Cache\*'),
        ]
        for pat in win_browser:
            delete_path_contents(pat)
    add_action("Cleanup", "Cleared browser caches (Chrome, Edge, Firefox)")

    # ── Trash / Recycle Bin ──
    log("Emptying trash...", "progress")
    if not dry_run:
        if IS_MAC:
            run_cmd(['rm', '-rf', os.path.expanduser('~/.Trash/*')], shell=True)
        elif IS_LINUX:
            trash_paths = [
                os.path.expanduser('~/.local/share/Trash/files/*'),
                os.path.expanduser('~/.local/share/Trash/info/*'),
            ]
            for tp in trash_paths:
                delete_path_contents(tp)
        elif IS_WINDOWS:
            run_cmd(['powershell', '-Command', 'Clear-RecycleBin -Force -ErrorAction SilentlyContinue'])
    add_action("Cleanup", "Emptied trash/recycle bin")

    # ── Platform-specific cleanup ──
    if IS_LINUX:
        log("Running apt cleanup...", "progress")
        if not dry_run and is_root():
            run_cmd(['apt-get', 'autoremove', '-y'], timeout=120)
            run_cmd(['apt-get', 'autoclean', '-y'], timeout=60)
            run_cmd(['journalctl', '--vacuum-time=3d'], timeout=30)
        add_action("Cleanup", "apt autoremove/autoclean, journal vacuum")

    elif IS_MAC:
        log("Running macOS maintenance...", "progress")
        if not dry_run:
            # Purge inactive memory
            run_cmd(['purge'], timeout=30)
            # Clear DNS cache
            run_cmd(['dscacheutil', '-flushcache'], timeout=10)
            # Remove .DS_Store files from common locations
            run_cmd(['find', str(Path.home()), '-name', '.DS_Store', '-maxdepth', '4', '-delete'], timeout=30)
        add_action("Cleanup", "macOS purge, DNS flush, DS_Store cleanup")

    elif IS_WINDOWS:
        log("Running Windows-specific cleanup...", "progress")
        if not dry_run:
            # DISM cleanup
            run_cmd(['dism.exe', '/online', '/Cleanup-Image', '/StartComponentCleanup', '/ResetBase'], timeout=600)
            # Disk cleanup
            run_cmd(['cleanmgr.exe', '/sagerun:1'], timeout=300)
            # Clear event logs
            run_cmd('wevtutil el | ForEach-Object { wevtutil cl $_ }', shell=True, timeout=60)
        add_action("Cleanup", "DISM cleanup, Disk Cleanup, event logs cleared")

    # ── Bloatware (Linux: snap remove unused; macOS: brew cleanup) ──
    removed_apps = []
    if IS_LINUX:
        log("Checking for unused snap packages...", "progress")
        if not dry_run and shutil.which('snap'):
            ret, out, _ = run_cmd(['snap', 'list', '--all'])
            if ret == 0:
                for line in out.strip().split('\n')[1:]:
                    parts = line.split()
                    if len(parts) >= 6 and 'disabled' in parts[5]:
                        snap_name = parts[0]
                        rev = parts[2]
                        run_cmd(['snap', 'remove', snap_name, '--revision', rev], timeout=60)
                        removed_apps.append(f"{snap_name} (rev {rev})")
        add_action("Bloatware", f"Removed {len(removed_apps)} unused snap revisions")

    elif IS_MAC:
        log("Running Homebrew cleanup...", "progress")
        if not dry_run and shutil.which('brew'):
            run_cmd(['brew', 'cleanup', '--prune=7'], timeout=120)
        add_action("Cleanup", "Homebrew cleanup")

    elif IS_WINDOWS:
        log("Bloatware removal handled by PowerShell script for Windows.", "info")
        add_action("Bloatware", "See PowerShell script for Windows bloatware removal")

    report.bloatware_removed = removed_apps

    # ── Services optimization (Linux: systemd) ──
    disabled_services = []
    if IS_LINUX and is_root():
        log("Optimizing services...", "progress")
        optional_services = [
            ('bluetooth.service', 'Bluetooth'),
            ('cups.service', 'Printing (CUPS)'),
            ('avahi-daemon.service', 'mDNS/Avahi'),
            ('ModemManager.service', 'Modem Manager'),
        ]
        for svc, desc in optional_services:
            ret, _, _ = run_cmd(['systemctl', 'is-enabled', svc])
            if ret == 0:
                if not dry_run:
                    run_cmd(['systemctl', 'disable', '--now', svc])
                disabled_services.append(f"{desc} ({svc})")
        add_action("Services", f"Disabled {len(disabled_services)} optional services")
    report.services_disabled = disabled_services

    space_after = get_disk_free()
    report.space_reclaimed = max(0, space_after - space_before)
    log(f"Space reclaimed this phase: {friendly_size(report.space_reclaimed)}", "success")
    print()

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3: MALWARE & SECURITY SCAN
# ─────────────────────────────────────────────────────────────────────────────

def phase_malware_scan():
    log("═══ PHASE 3: Malware & Security Scan ═══", "header")

    if IS_WINDOWS:
        # Windows Defender
        log("Running Windows Defender scan...", "progress")
        if not dry_run:
            # Update definitions
            run_cmd(['powershell', '-Command', 'Update-MpSignature -ErrorAction SilentlyContinue'], timeout=120)
            add_action("Security", "Updated Windows Defender signatures")

            # Enable real-time protection
            run_cmd(['powershell', '-Command',
                     'Set-MpPreference -DisableRealtimeMonitoring $false -ErrorAction SilentlyContinue'])
            add_action("Security", "Ensured real-time protection enabled")

            # Quick scan
            ret, out, err = run_cmd(
                ['powershell', '-Command', 'Start-MpScan -ScanType QuickScan'],
                timeout=600
            )
            if ret == 0:
                log("  Quick scan completed.", "success")
                # Check threats
                ret2, threats_out, _ = run_cmd(
                    ['powershell', '-Command',
                     'Get-MpThreatDetection | Select-Object -Property ThreatName,ActionSuccess | ConvertTo-Json']
                )
                if threats_out.strip() and threats_out.strip() != '[]':
                    report.threats_found.append(f"Threats detected (check Defender): {threats_out[:200]}")
                    add_action("Security", "Threats found — check Windows Defender", "Warning")
                else:
                    add_action("Security", "Quick scan clean — no threats")
            else:
                log("  Scan had issues — check manually.", "warning")
        else:
            add_action("Security", "Malware scan (DRY RUN — skipped)")

    elif IS_LINUX:
        # ClamAV if available
        log("Checking for ClamAV...", "progress")
        if shutil.which('clamscan'):
            log("Running ClamAV scan on home directory...", "progress")
            if not dry_run:
                ret, out, _ = run_cmd(
                    ['clamscan', '-r', '--infected', '--remove=no', str(Path.home())],
                    timeout=600
                )
                infected_lines = [l for l in out.split('\n') if 'FOUND' in l]
                if infected_lines:
                    for line in infected_lines[:10]:
                        report.threats_found.append(line.strip())
                    add_action("Security", f"ClamAV found {len(infected_lines)} issue(s)", "Warning")
                else:
                    add_action("Security", "ClamAV scan clean")
                log(f"  Scan complete. {len(infected_lines)} findings.", "success" if not infected_lines else "warning")
            else:
                add_action("Security", "ClamAV scan (DRY RUN — skipped)")
        else:
            log("  ClamAV not installed. Consider: sudo apt install clamav", "warning")
            add_action("Security", "ClamAV not available — install recommended")

    elif IS_MAC:
        # macOS XProtect runs automatically; check Gatekeeper
        log("Checking macOS security status...", "progress")
        if not dry_run:
            ret, out, _ = run_cmd(['spctl', '--status'])
            if 'enabled' in out.lower():
                log("  Gatekeeper is enabled.", "success")
                add_action("Security", "Gatekeeper enabled")
            else:
                log("  Gatekeeper is DISABLED — enabling...", "warning")
                run_cmd(['sudo', 'spctl', '--master-enable'])
                add_action("Security", "Enabled Gatekeeper")

            # Check firewall
            ret, out, _ = run_cmd(['/usr/libexec/ApplicationFirewall/socketfilterfw', '--getglobalstate'])
            if 'enabled' in out.lower():
                log("  Firewall is enabled.", "success")
                add_action("Security", "macOS firewall enabled")
            else:
                log("  Firewall is DISABLED — enabling...", "warning")
                run_cmd(['sudo', '/usr/libexec/ApplicationFirewall/socketfilterfw', '--setglobalstate', 'on'])
                add_action("Security", "Enabled macOS firewall")
        else:
            add_action("Security", "Security checks (DRY RUN — skipped)")

    # Cross-platform: check for suspicious cron/scheduled tasks
    log("Checking for suspicious scheduled tasks...", "progress")
    if IS_LINUX or IS_MAC:
        ret, out, _ = run_cmd(['crontab', '-l'])
        if ret == 0 and out.strip():
            suspicious = [l for l in out.split('\n')
                          if l.strip() and not l.startswith('#')
                          and any(s in l.lower() for s in ['curl ', 'wget ', 'base64', '/dev/tcp'])]
            if suspicious:
                for s in suspicious:
                    report.threats_found.append(f"Suspicious cron: {s[:100]}")
                add_action("Security", f"Found {len(suspicious)} suspicious cron entries", "Warning")
            else:
                add_action("Security", "Cron jobs look clean")
        else:
            add_action("Security", "No user cron jobs found")
    print()

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4: PERFORMANCE ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def phase_performance_analysis():
    log("═══ PHASE 4: Performance Analysis ═══", "header")

    # ── Largest files ──
    log("Finding largest files...", "progress")
    scan_root = Path.home() if not IS_WINDOWS else Path("C:\\")
    large_files = []
    try:
        for root, dirs, files in os.walk(scan_root, followlinks=False):
            # Skip system dirs
            root_lower = root.lower()
            skip_dirs = ['winsxs', 'installer', '.git', 'node_modules', '__pycache__',
                         'system volume information', '$recycle.bin']
            if any(sd in root_lower for sd in skip_dirs):
                dirs.clear()
                continue
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for fname in files:
                fpath = Path(root) / fname
                try:
                    sz = fpath.stat().st_size
                    if sz > 100_000_000:  # 100 MB
                        large_files.append((fpath, sz))
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        pass

    large_files.sort(key=lambda x: x[1], reverse=True)
    report.largest_files = [
        LargeFile(
            path=str(f[0]),
            size=friendly_size(f[1]),
            size_raw=f[1],
            modified=datetime.fromtimestamp(f[0].stat().st_mtime).strftime("%Y-%m-%d")
        )
        for f in large_files[:10]
    ]
    log(f"  Found {len(report.largest_files)} files over 100 MB.", "info")

    # ── Installed apps ──
    log("Enumerating installed applications...", "progress")
    apps = []
    if IS_LINUX:
        if shutil.which('dpkg'):
            ret, out, _ = run_cmd(['dpkg', '--get-selections'])
            if ret == 0:
                for line in out.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == 'install':
                        apps.append({'name': parts[0], 'version': '', 'publisher': '', 'size': ''})
        elif shutil.which('rpm'):
            ret, out, _ = run_cmd(['rpm', '-qa', '--queryformat', '%{NAME}|%{VERSION}|%{VENDOR}|%{SIZE}\n'])
            if ret == 0:
                for line in out.strip().split('\n'):
                    parts = line.split('|')
                    if len(parts) >= 4:
                        apps.append({'name': parts[0], 'version': parts[1],
                                     'publisher': parts[2], 'size': friendly_size(int(parts[3])) if parts[3].isdigit() else ''})
    elif IS_MAC:
        apps_dir = Path("/Applications")
        if apps_dir.exists():
            for app in apps_dir.iterdir():
                if app.suffix == '.app':
                    apps.append({'name': app.stem, 'version': '', 'publisher': '', 'size': ''})
        # Also check brew
        if shutil.which('brew'):
            ret, out, _ = run_cmd(['brew', 'list', '--formula'])
            if ret == 0:
                for name in out.strip().split('\n'):
                    if name.strip():
                        apps.append({'name': f"{name.strip()} (brew)", 'version': '', 'publisher': '', 'size': ''})
    elif IS_WINDOWS:
        ret, out, _ = run_cmd([
            'powershell', '-Command',
            'Get-ItemProperty HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | '
            'Select-Object DisplayName,DisplayVersion,Publisher | ConvertTo-Json'
        ])
        if ret == 0 and out.strip():
            try:
                data = json.loads(out)
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    name = item.get('DisplayName', '')
                    if name:
                        apps.append({
                            'name': name,
                            'version': item.get('DisplayVersion', ''),
                            'publisher': item.get('Publisher', ''),
                            'size': ''
                        })
            except json.JSONDecodeError:
                pass

    report.installed_apps = apps
    log(f"  Found {len(apps)} installed applications.", "info")
    add_action("Analysis", f"Catalogued {len(apps)} installed applications")

    # Final disk state
    report.disk_after = get_disk_free()
    total_reclaimed = max(0, report.disk_after - report.disk_before)
    log(f"Total disk space recovered: {friendly_size(total_reclaimed)}", "success")
    print()

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5: BOTWAVE DEPLOYMENT PREPARATION
# ─────────────────────────────────────────────────────────────────────────────

def phase_botwave_prep():
    log("═══ PHASE 5: Botwave Deployment Preparation ═══", "header")

    ensure_dir(READY_DIR)
    biz_copy = READY_DIR / "Business-Files"
    ensure_dir(biz_copy)

    # Copy business files
    log("Copying organized business files to ready folder...", "progress")
    if not dry_run and BUSINESS_DIR.exists():
        try:
            # Copy contents, not the dir itself
            for item in BUSINESS_DIR.iterdir():
                dest = biz_copy / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(str(dest))
                    shutil.copytree(str(item), str(dest), dirs_exist_ok=True)
                else:
                    shutil.copy2(str(item), str(dest))
        except Exception as e:
            log(f"  Copy warning: {e}", "warning")
    add_action("Botwave Prep", "Copied business files to Ready-For-Botwave")

    # Generate bot-config.json
    log("Generating bot-config.json...", "progress")
    bot_config = {
        "botwave_version": "1.0",
        "generated": datetime.now().isoformat(),
        "machine": {
            "hostname": socket.gethostname(),
            "os": f"{SYSTEM} {platform.release()}",
            "user": os.getenv("USER") or os.getenv("USERNAME") or "unknown",
            "platform": SYSTEM.lower(),
        },
        "file_paths": {
            "business_root": str(BUSINESS_DIR),
            "invoices": str(BUSINESS_DIR / "Invoices-Receipts"),
            "contracts": str(BUSINESS_DIR / "Contracts-Legal"),
            "tax": str(BUSINESS_DIR / "Tax-Accounting"),
            "clients": str(BUSINESS_DIR / "Clients-CRM"),
            "proposals": str(BUSINESS_DIR / "Proposals-Quotes"),
            "financial": str(BUSINESS_DIR / "Financial-Reports"),
            "hr": str(BUSINESS_DIR / "HR-Employees"),
            "marketing": str(BUSINESS_DIR / "Marketing-Sales"),
            "operations": str(BUSINESS_DIR / "Operations"),
            "meetings": str(BUSINESS_DIR / "Meetings-Notes"),
            "presentations": str(BUSINESS_DIR / "Presentations"),
            "file_index": str(INDEX_PATH),
        },
        "bot_settings": {
            "auto_scan_interval": "24h",
            "file_watch_enabled": True,
            "notification_email": "",
            "backup_schedule": "weekly",
            "language": "en",
        },
    }
    config_path = READY_DIR / "bot-config.json"
    if not dry_run:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(bot_config, f, indent=2)
    add_action("Botwave Prep", "Generated bot-config.json")

    # Create launcher script
    log("Creating launcher script...", "progress")
    if IS_WINDOWS:
        launcher = READY_DIR / "START-HERE.bat"
        content = '@echo off\necho ======================================\necho    BOTWAVE - Your AI Business Assistant\necho    Machine is primed and ready!\necho ======================================\necho.\necho Business files: C:\\Business\\\necho Bot config: %~dp0bot-config.json\necho.\npause\n'
    else:
        launcher = READY_DIR / "start-here.sh"
        content = '#!/usr/bin/env bash\necho "======================================"\necho "  BOTWAVE - Your AI Business Assistant"\necho "  Machine is primed and ready!"\necho "======================================"\necho ""\necho "Business files: ~/Business/"\necho "Bot config: $(dirname "$0")/bot-config.json"\necho ""\necho "Press Enter to continue..."\nread\n'

    if not dry_run:
        with open(launcher, 'w', encoding='utf-8') as f:
            f.write(content)
        if not IS_WINDOWS:
            os.chmod(str(launcher), 0o755)
    add_action("Botwave Prep", f"Created {launcher.name}")

    # Customer README
    log("Creating customer README...", "progress")
    readme_path = READY_DIR / "README.txt"
    readme = f"""================================================================================
  BOTWAVE VIP ONBOARDING — SYSTEM READY
================================================================================

Congratulations! Your machine has been professionally optimized and prepared
for Botwave AI deployment.

WHAT WAS DONE:
  - All business files were discovered and organized into {BUSINESS_DIR}/
  - System was cleaned of temporary files, caches, and performance issues
  - Security scan was performed
  - Machine optimized for peak performance

YOUR FILES:
  - Organized business files: {BUSINESS_DIR}/
  - File index (CSV):        {INDEX_PATH}
  - Original file backups:   {BACKUP_DIR}/

BOTWAVE SETUP:
  - Bot configuration:  {config_path}
  - Quick launch:       {launcher}
  - Full report:        {REPORT_PATH}

NEXT STEPS:
  1. Review the organized files to ensure everything is correct.
  2. Your Botwave technician will complete the bot installation remotely.
  3. Check your email for the Botwave dashboard login credentials.

SUPPORT:
  support@botwave.ai | (555) 123-4567

Report generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}
Machine: {socket.gethostname()}
================================================================================
"""
    if not dry_run:
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme)
    add_action("Botwave Prep", "Created customer README")

    log(f"Botwave ready folder prepared at: {READY_DIR}", "success")
    print()

# ─────────────────────────────────────────────────────────────────────────────
# HTML REPORT GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_html_report():
    log("═══ Generating HTML Report ═══", "header")

    total_reclaimed = max(0, report.disk_after - report.disk_before)
    duration = datetime.now() - report.start_time
    hours, rem = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(rem, 60)
    duration_str = f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

    hostname = socket.gethostname()
    username = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    # Build action rows
    action_rows = ""
    for a in report.actions:
        color = {"Done": "#22c55e", "Warning": "#f59e0b", "Error": "#ef4444"}.get(a.status, "#22c55e")
        icon = {"Done": "&#10004;", "Warning": "&#9888;", "Error": "&#10008;"}.get(a.status, "&#10004;")
        action_rows += f"""
        <tr>
            <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:13px;">{a.time}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;font-weight:600;color:#1e293b;">{a.category}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;color:#475569;">{a.detail}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;text-align:center;">
                <span style="color:{color};font-weight:700;">{icon} {a.status}</span>
            </td>
        </tr>"""

    # Build largest files
    largest_rows = ""
    for lf in report.largest_files:
        largest_rows += f"""
        <tr>
            <td style="padding:8px 14px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#475569;word-break:break-all;">{lf.path}</td>
            <td style="padding:8px 14px;border-bottom:1px solid #e2e8f0;font-weight:600;text-align:right;">{lf.size}</td>
            <td style="padding:8px 14px;border-bottom:1px solid #e2e8f0;color:#64748b;text-align:center;">{lf.modified}</td>
        </tr>"""

    # Threats
    threat_color = "#22c55e"
    threat_status = "&#10004; Clean"
    threat_items = "<li style='color:#22c55e;'>No threats detected.</li>"
    if report.threats_found:
        threat_color = "#ef4444"
        threat_status = "&#9888; Threats Found"
        threat_items = "\n".join(f"<li style='padding:4px 0;color:#ef4444;'>{t}</li>" for t in report.threats_found)

    # Bloatware
    bloat_items = "<li style='color:#64748b;'>No bloatware detected.</li>"
    if report.bloatware_removed:
        bloat_items = "\n".join(f"<li style='padding:4px 0;color:#475569;'>{b}</li>" for b in report.bloatware_removed)

    # Services
    svc_items = "<li style='color:#64748b;'>No services were modified.</li>"
    if report.services_disabled:
        svc_items = "\n".join(f"<li style='padding:4px 0;'>&#10004; {s}</li>" for s in report.services_disabled)

    # Apps (top 30)
    app_rows = ""
    for app in report.installed_apps[:30]:
        app_rows += f"""
        <tr>
            <td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;">{app.get('name','')}</td>
            <td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;color:#64748b;">{app.get('version','')}</td>
            <td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;color:#64748b;">{app.get('publisher','')}</td>
            <td style="padding:6px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;text-align:right;">{app.get('size','')}</td>
        </tr>"""

    dry_run_banner = ""
    if dry_run:
        dry_run_banner = '<div style="background:#fef3c7;border:2px solid #f59e0b;border-radius:8px;padding:16px;margin-bottom:24px;text-align:center;font-weight:700;color:#92400e;font-size:18px;">&#9888; DRY RUN — No changes were made to this system</div>'

    threat_count_class = 'red' if report.threats_found else 'green'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Botwave Overhaul Report — {hostname}</title>
<style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f8fafc; color:#1e293b; line-height:1.6; }}
    .container {{ max-width:960px; margin:0 auto; padding:32px 24px; }}
    .header {{ background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%); color:white; padding:48px 40px; border-radius:16px; margin-bottom:32px; }}
    .header h1 {{ font-size:28px; margin-bottom:8px; }}
    .header p {{ color:#94a3b8; font-size:14px; }}
    .card {{ background:white; border-radius:12px; padding:28px; margin-bottom:24px; box-shadow:0 1px 3px rgba(0,0,0,0.08); }}
    .card h2 {{ font-size:18px; margin-bottom:16px; color:#0f172a; border-bottom:2px solid #e2e8f0; padding-bottom:10px; }}
    .stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; margin-bottom:24px; }}
    .stat {{ background:#f1f5f9; border-radius:10px; padding:20px; text-align:center; }}
    .stat .value {{ font-size:28px; font-weight:800; color:#0f172a; }}
    .stat .label {{ font-size:12px; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; margin-top:4px; }}
    .stat.green .value {{ color:#16a34a; }}
    .stat.red .value {{ color:#ef4444; }}
    .stat.blue .value {{ color:#2563eb; }}
    table {{ width:100%; border-collapse:collapse; }}
    th {{ padding:10px 14px; text-align:left; background:#f8fafc; color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:0.5px; border-bottom:2px solid #e2e8f0; }}
    .footer {{ text-align:center; padding:32px; color:#94a3b8; font-size:12px; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>&#x1F916; Botwave VIP System Overhaul Report</h1>
        <p>Machine: {hostname} &nbsp;|&nbsp; User: {username} &nbsp;|&nbsp; Platform: {SYSTEM} {platform.release()}</p>
        <p>Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")} &nbsp;|&nbsp; Duration: {duration_str}</p>
    </div>

    {dry_run_banner}

    <div class="stats">
        <div class="stat green">
            <div class="value">{friendly_size(total_reclaimed)}</div>
            <div class="label">Disk Space Reclaimed</div>
        </div>
        <div class="stat blue">
            <div class="value">{report.files_organized}</div>
            <div class="label">Files Organized</div>
        </div>
        <div class="stat">
            <div class="value">{len(report.bloatware_removed)}</div>
            <div class="label">Bloatware Removed</div>
        </div>
        <div class="stat {threat_count_class}">
            <div class="value">{len(report.threats_found)}</div>
            <div class="label">Threats Found</div>
        </div>
    </div>

    <div class="card">
        <h2>Disk Space</h2>
        <div class="stats">
            <div class="stat"><div class="value">{friendly_size(report.disk_before)}</div><div class="label">Free Before</div></div>
            <div class="stat green"><div class="value">{friendly_size(report.disk_after)}</div><div class="label">Free After</div></div>
        </div>
    </div>

    <div class="card">
        <h2>Actions Performed</h2>
        <table>
            <thead><tr><th>Time</th><th>Category</th><th>Detail</th><th>Status</th></tr></thead>
            <tbody>{action_rows}</tbody>
        </table>
    </div>

    <div class="card">
        <h2>Security Status</h2>
        <p style="font-size:20px;font-weight:700;color:{threat_color};margin-bottom:12px;">{threat_status}</p>
        <ul style="list-style:none;padding:0;">{threat_items}</ul>
    </div>

    <div class="card">
        <h2>Bloatware / Unused Packages Removed</h2>
        <ul style="list-style:none;padding:0;">{bloat_items}</ul>
    </div>

    <div class="card">
        <h2>Top 10 Largest Files (over 100 MB)</h2>
        <table>
            <thead><tr><th>Path</th><th style="text-align:right;">Size</th><th style="text-align:center;">Modified</th></tr></thead>
            <tbody>{largest_rows}</tbody>
        </table>
    </div>

    <div class="card">
        <h2>Installed Applications (Top 30 of {len(report.installed_apps)})</h2>
        <table>
            <thead><tr><th>Name</th><th>Version</th><th>Publisher</th><th style="text-align:right;">Size</th></tr></thead>
            <tbody>{app_rows}</tbody>
        </table>
    </div>

    <div class="card">
        <h2>Services Disabled</h2>
        <ul style="list-style:none;padding:0;">{svc_items}</ul>
    </div>

    <div class="card" style="background:linear-gradient(135deg,#0f172a,#1e3a5f);color:white;">
        <h2 style="color:white;border-color:rgba(255,255,255,0.2);">Botwave Deployment Status</h2>
        <p style="font-size:20px;font-weight:700;color:#4ade80;margin-bottom:8px;">&#10004; Machine Primed &amp; Ready</p>
        <p style="color:#94a3b8;">Business files organized at: <strong style="color:white;">{BUSINESS_DIR}</strong></p>
        <p style="color:#94a3b8;">Bot config ready at: <strong style="color:white;">{READY_DIR / 'bot-config.json'}</strong></p>
    </div>

    <div class="footer">
        <p>Botwave VIP System Overhaul &copy; {datetime.now().year} Botwave Inc. &mdash; All rights reserved.</p>
        <p>This report was auto-generated. Questions? Contact support@botwave.ai</p>
    </div>
</div>
</body>
</html>"""

    try:
        with open(REPORT_PATH, 'w', encoding='utf-8') as f:
            f.write(html)
        log(f"Report saved to: {REPORT_PATH}", "success")
    except Exception as e:
        log(f"Could not save report: {e}", "error")
    print()

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Botwave VIP System Overhaul — Cross-Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  python3 botwave-overhaul.py --dry-run\n  python3 botwave-overhaul.py --confirm\n  python3 botwave-overhaul.py --skip-cleanup --confirm"
    )
    parser.add_argument('--dry-run', action='store_true', help='Simulate without making changes')
    parser.add_argument('--confirm', action='store_true', help='Required for unattended execution')
    parser.add_argument('--skip-file-organization', action='store_true', help='Skip file org phase')
    parser.add_argument('--skip-cleanup', action='store_true', help='Skip system cleanup phase')
    parser.add_argument('--skip-malware', action='store_true', help='Skip malware scan phase')
    args = parser.parse_args()

    try:
        initialize(args)

        if not args.skip_file_organization:
            phase_file_organization()
        else:
            log("Skipping file organization (flag set).", "warning")

        if not args.skip_cleanup:
            phase_system_cleanup()
        else:
            log("Skipping system cleanup (flag set).", "warning")

        if not args.skip_malware:
            phase_malware_scan()
        else:
            log("Skipping malware scan (flag set).", "warning")

        phase_performance_analysis()
        phase_botwave_prep()
        generate_html_report()

        print()
        print(f"  {C.GREEN}╔══════════════════════════════════════════════════════════════════════╗{C.RESET}")
        print(f"  {C.GREEN}║  ✅ Botwave Overhaul Complete — Machine is now primed and ready     ║{C.RESET}")
        print(f"  {C.GREEN}║     for bot deployment.                                             ║{C.RESET}")
        print(f"  {C.GREEN}╚══════════════════════════════════════════════════════════════════════╝{C.RESET}")
        print()
        log(f"Report: {REPORT_PATH}", "success")
        log(f"Ready folder: {READY_DIR}", "success")
        log(f"Total runtime: {datetime.now() - report.start_time}", "info")

    except KeyboardInterrupt:
        log("Interrupted by user.", "warning")
        generate_html_report()
        sys.exit(130)
    except Exception as e:
        log(f"FATAL ERROR: {e}", "error")
        import traceback
        log(traceback.format_exc(), "error")
        report.errors.append(str(e))
        generate_html_report()
        sys.exit(1)


if __name__ == "__main__":
    main()
