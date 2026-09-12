import os
import subprocess
import requests
from datetime import datetime
from inventory import devices

BACKUP_ROOT = "/root/automation-toolkit/backups"
LOG_FILE = f"{BACKUP_ROOT}/drift_check.log"

SERVICENOW_INSTANCE = "https://dev408639.service-now.com"
SERVICENOW_USER = "admin"
SERVICENOW_PASSWORD = os.environ.get("SERVICENOW_PASSWORD", "")

HIGH_SEVERITY_KEYWORDS = ["access-list", "permit", "deny", "firewall", "acl", "ip route"]


def run_git(args):
    return subprocess.run(
        ["git"] + args, cwd=BACKUP_ROOT, capture_output=True, text=True
    )


def determine_urgency(diff_text):
    lowered = diff_text.lower()
    for keyword in HIGH_SEVERITY_KEYWORDS:
        if keyword in lowered:
            return "1"  # High - security/routing relevant change
    return "3"  # Moderate - default for other config drift


def post_incident(device_name, diff_text, timestamp):
    urgency = determine_urgency(diff_text)

    payload = {
        "short_description": f"Config drift detected on {device_name}",
        "description": (
            f"Automated drift_check.py detected an unauthorized/unreviewed "
            f"configuration change on {device_name} at {timestamp}.\n\n"
            f"Diff:\n{diff_text}"
        ),
        "category": "network",
        "urgency": urgency,
        "impact": urgency,
    }

    try:
        response = requests.post(
            f"{SERVICENOW_INSTANCE}/api/now/table/incident",
            auth=(SERVICENOW_USER, SERVICENOW_PASSWORD),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json=payload,
            timeout=15,
        )
        if response.status_code == 201:
            number = response.json()["result"]["number"]
            return f"  ServiceNow Incident created: {number} (urgency {urgency})"
        else:
            return f"  ServiceNow POST failed: HTTP {response.status_code} - {response.text[:200]}"
    except requests.exceptions.RequestException as e:
        return f"  ServiceNow POST failed: {e}"


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

            incident_result = post_incident(device_name, diff.stdout, timestamp)
            print(incident_result)
            log.write(incident_result + "\n")

            run_git(["add", latest_path])
            run_git(["commit", "-m", f"{device_name} config change - {timestamp}"])
        else:
            message = f"{timestamp} - OK: {device_name} - no changes detected"
            print(message)
            log.write(message + "\n")