import subprocess
from datetime import datetime
from inventory import devices

BACKUP_ROOT = "/root/automation-toolkit/backups"
LOG_FILE = f"{BACKUP_ROOT}/drift_check.log"


def run_git(args):
    return subprocess.run(
        ["git"] + args, cwd=BACKUP_ROOT, capture_output=True, text=True
    )


with open(LOG_FILE, "a") as log:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for device in devices:
        device_name = device["device_name"]
        latest_path = f"{device_name}/latest.txt"

        diff = run_git(["diff", "--", latest_path])

        if diff.stdout.strip():
            message = f"{timestamp} - ALERT: {device_name} config CHANGED"
            print(message)
            log.write(message + "\n")
            log.write(diff.stdout + "\n")

            run_git(["add", latest_path])
            run_git(["commit", "-m", f"{device_name} config change - {timestamp}"])
        else:
            message = f"{timestamp} - OK: {device_name} - no changes detected"
            print(message)
            log.write(message + "\n")
