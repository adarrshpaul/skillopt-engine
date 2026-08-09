#!/usr/bin/env python3
import os
import time
import argparse
import psutil
import signal
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

def kill_process(proc: psutil.Process):
    """Safely kills a process with SIGTERM fallback to SIGKILL."""
    current_uid = os.getuid()
    try:
        if proc.uids().real != current_uid:
            print(f"Skipping {proc.pid}: Not owned by current user.")
            return False
            
        print(f"Terminating PID {proc.pid} ({proc.name()})...")
        proc.terminate() # SIGTERM
        
        # Wait up to 3 seconds for graceful exit
        try:
            proc.wait(timeout=3)
            print(f"PID {proc.pid} gracefully terminated.")
            return True
        except psutil.TimeoutExpired:
            print(f"PID {proc.pid} didn't exit in 3s. Sending SIGKILL...")
            proc.kill() # SIGKILL
            proc.wait(timeout=1)
            print(f"PID {proc.pid} forcefully killed.")
            return True
            
    except psutil.NoSuchProcess:
        print(f"PID {proc.pid} no longer exists.")
        return True
    except psutil.AccessDenied:
        print(f"Access denied to PID {proc.pid}.")
        return False
    except Exception as e:
        print(f"Error killing PID {proc.pid}: {e}")
        return False

def kill_by_port(port: int):
    """Kills any process listening on the specified port owned by the current user."""
    killed_any = False
    current_uid = os.getuid()
    for proc in psutil.process_iter(['pid', 'name', 'uids']):
        try:
            if proc.info['uids'] and proc.info['uids'].real == current_uid:
                for conn in proc.connections(kind='inet'):
                    if conn.laddr.port == port and conn.status == 'LISTEN':
                        if kill_process(proc):
                            killed_any = True
                        break # process is killed, no need to check other connections
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if not killed_any:
        print(f"No active user-owned processes found listening on port {port}.")
    return killed_any

def kill_by_name(name: str):
    """Kills any process matching the specified name owned by the current user."""
    killed_any = False
    current_uid = os.getuid()
    for proc in psutil.process_iter(['pid', 'name', 'uids', 'cmdline']):
        try:
            if proc.info['uids'] and proc.info['uids'].real == current_uid:
                # Match against process name or command line arguments
                proc_name = proc.info['name'] or ""
                cmdline = " ".join(proc.info['cmdline'] or [])
                if name in proc_name or name in cmdline:
                    if kill_process(proc):
                        killed_any = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if not killed_any:
        print(f"No active user-owned processes found matching '{name}'.")
    return killed_any

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Safe Resource Manager")
    parser.add_argument("--port", type=int, help="Kill process listening on this port")
    parser.add_argument("--name", type=str, help="Kill process matching this name or cmdline")
    
    args = parser.parse_args()
    
    if args.port:
        kill_by_port(args.port)
    elif args.name:
        kill_by_name(args.name)
    else:
        print("Must specify --port or --name")
