"""
Interactive Desktop Launcher for ScaleUp Godot 4 Simulation.
Spawns Godot GUI onto the interactive desktop (WinSta0\\default) and brings it to foreground.
"""

import os
import sys
import time
import subprocess
import ctypes
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def find_godot():
    candidates = [
        Path(r"D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe"),
        Path(r"D:\Godot\Godot_v4.7.2-stable_win64.exe"),
        Path(r"D:\Godot\Godot.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None

def launch_interactive_godot(scene_path="res://doorbell_sim.tscn"):
    godot = find_godot()
    if not godot:
        print("ERROR: Godot binary not found!", file=sys.stderr)
        return False

    cmd = [
        godot,
        "--path",
        str(ROOT),
        "--scene",
        scene_path,
    ]

    print(f"Launching interactive Godot: {' '.join(cmd)}")

    if os.name == "nt":
        class _STARTUPINFOW(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class _PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        si = _STARTUPINFOW()
        si.cb = ctypes.sizeof(_STARTUPINFOW)
        si.lpDesktop = r"WinSta0\default"
        si.dwFlags = 0x00000001  # STARTF_USESHOWWINDOW
        si.wShowWindow = 1       # SW_SHOWNORMAL
        pi = _PROCESS_INFORMATION()

        cmd_line = subprocess.list2cmdline(cmd)
        ret = ctypes.windll.kernel32.CreateProcessW(
            None,
            cmd_line,
            None,
            None,
            False,
            0x00000010 | 0x00000200,  # CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP
            None,
            str(ROOT),
            ctypes.byref(si),
            ctypes.byref(pi),
        )

        if ret:
            target_pid = pi.dwProcessId
            ctypes.windll.kernel32.CloseHandle(pi.hProcess)
            ctypes.windll.kernel32.CloseHandle(pi.hThread)
            print(f"Spawned Godot interactive process (PID: {target_pid}) on WinSta0\\default")

            # Bring to foreground
            try:
                h_desk = ctypes.windll.user32.OpenDesktopW("default", 0, False, 0x01FF)
                if h_desk:
                    ctypes.windll.user32.SetThreadDesktop(h_desk)

                for _ in range(15):
                    time.sleep(0.2)
                    found_hwnd = [0]

                    def _enum_cb(h, _lp):
                        if ctypes.windll.user32.IsWindowVisible(h):
                            cur_pid = wintypes.DWORD()
                            ctypes.windll.user32.GetWindowThreadProcessId(h, ctypes.byref(cur_pid))
                            if cur_pid.value == target_pid:
                                found_hwnd[0] = h
                                return False
                        return True

                    cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_enum_cb)
                    ctypes.windll.user32.EnumDesktopWindows(h_desk if h_desk else None, cb, 0)
                    if found_hwnd[0]:
                        h_wnd = found_hwnd[0]
                        ctypes.windll.user32.ShowWindow(h_wnd, 9)  # SW_RESTORE
                        ctypes.windll.user32.SetWindowPos(h_wnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
                        ctypes.windll.user32.SetWindowPos(h_wnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
                        ctypes.windll.user32.SetForegroundWindow(h_wnd)
                        print(f"Window (HWND: {h_wnd}) brought to foreground.")
                        break
            except Exception as e:
                print(f"Foreground window adjustment exception: {e}")
            return True
        else:
            err = ctypes.GetLastError()
            print(f"CreateProcessW failed with error code: {err}")

    # Fallback
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        close_fds=True,
    )
    print(f"Fallback spawned Godot process (PID: {proc.pid})")
    return True

if __name__ == "__main__":
    launch_interactive_godot()
