"""Thu thập metadata hệ thống tối thiểu cho các phép đo tái lập."""

from __future__ import annotations

import ctypes
import platform
import subprocess
from ctypes import wintypes
from pathlib import Path


def _total_physical_memory_bytes() -> int | None:
    if platform.system() != "Windows":
        return None

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullTotalPhys)


def _processor_name() -> str:
    name = platform.processor().strip()
    if platform.system() == "Windows":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                name = str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return name or "unknown"


def _git_commit(project_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def collect_system_metadata(project_root: Path) -> dict[str, object]:
    memory_bytes = _total_physical_memory_bytes()
    return {
        "processor_name": _processor_name(),
        "total_physical_memory_bytes": memory_bytes,
        "total_physical_memory_gib": (
            round(memory_bytes / (1024**3), 2) if memory_bytes is not None else None
        ),
        "source_commit": _git_commit(project_root),
    }
