import ios_compat_patch  # must be imported first, before Netmiko/Paramiko connect

from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
from datetime import datetime
import os
import re
from inventory import devices

BACKUP_ROOT = "/root/automation-toolkit/backups"


def normalize_fortigate_output(output):
    """
    FortiGate re-encrypts password/secret fields AND embedded private-key
    blocks (both ENCRYPTED PRIVATE KEY and OPENSSH PRIVATE KEY formats)
    with a random salt on every single config pull, even when the
    underlying value hasn't changed. Left as-is, this makes
    drift_check.py falsely report a change every single run. This
    function replaces all three kinds of random ciphertext with a fixed
    placeholder before the output is used for drift comparison, so only
    real config changes are flagged.

    See docs/TROUBLESHOOTING-LOG.md for the full diagnostic story.
    """
    output = re.sub(r'(ENC\s+)\S+', r'\1[normalized]', output)
    output = re.sub(
        r'-----BEGIN ENCRYPTED PRIVATE KEY-----.*?-----END ENCRYPTED PRIVATE KEY-----',
        '-----BEGIN ENCRYPTED PRIVATE KEY-----\n[normalized]\n-----END ENCRYPTED PRIVATE KEY-----',
        output,
        flags=re.DOTALL,
    )
    output = re.sub(
        r'-----BEGIN OPENSSH PRIVATE KEY-----.*?-----END OPENSSH PRIVATE KEY-----',
        '-----BEGIN OPENSSH PRIVATE KEY-----\n[normalized]\n-----END OPENSSH PRIVATE KEY-----',
        output,
        flags=re.DOTALL,
    )
    return output


for device in devices:
    device_name = device["device_name"]
    connect_params = {k: v for k, v in device.items() if k != "device_name"}
    device_dir = f"{BACKUP_ROOT}/{device_name}"
    os.makedirs(device_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_file = f"{device_dir}/{device_name}-{timestamp}.txt"

    print(f"Connecting to {device_name} ({device['host']})...")

    try:
        conn = ConnectHandler(**connect_params)

        if device["device_type"] == "fortinet":
            conn.send_config_set(["config system console", "set output standard", "end"])
            output = conn.send_command("show full-configuration", read_timeout=30)
        else:
            output = conn.send_command("show running-config")

        conn.disconnect()

        # Full, real output always goes to the permanent timestamped record
        with open(backup_file, "w") as f:
            f.write(output)

        # Normalized output (FortiGate only) goes to latest.txt for drift comparison
        if device["device_type"] == "fortinet":
            drift_output = normalize_fortigate_output(output)
        else:
            drift_output = output

        latest_file = f"{device_dir}/latest.txt"
        with open(latest_file, "w") as f:
            f.write(drift_output)

        print(f"  Success — saved to {backup_file}")

    except NetmikoTimeoutException:
        print(f"  FAILED — {device_name} unreachable (timeout)")
    except NetmikoAuthenticationException:
        print(f"  FAILED — {device_name} authentication failed")
    except Exception as e:
        print(f"  FAILED — {device_name} unexpected error: {e}")
