import ios_compat_patch  # must be imported first, before Netmiko/Paramiko connect

from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
import os
from inventory import devices

RAW_DIR = "/root/automation-toolkit/topology_raw"
os.makedirs(RAW_DIR, exist_ok=True)

CISCO_DETAIL_CMD = "show lldp neighbors detail"
CISCO_SUMMARY_CMD = "show lldp neighbors"
FORTINET_CMD = "diagnose lldprx neighbor details"

for device in devices:
    device_name = device["device_name"]
    device_type = device["device_type"]
    connect_params = {k: v for k, v in device.items() if k != "device_name"}

    print(f"Connecting to {device_name} ({device['host']})...")

    try:
        conn = ConnectHandler(**connect_params)

        if device_type == "fortinet":
            output = conn.send_command(FORTINET_CMD, read_timeout=30)
        else:
            detail = conn.send_command(CISCO_DETAIL_CMD, read_timeout=30)
            summary = conn.send_command(CISCO_SUMMARY_CMD, read_timeout=30)
            output = f"=== DETAIL ===\n{detail}\n\n=== SUMMARY ===\n{summary}"

        conn.disconnect()

        raw_file = f"{RAW_DIR}/{device_name}.txt"
        with open(raw_file, "w") as f:
            f.write(output)

        print(f"  Success — saved to {raw_file}")

    except NetmikoTimeoutException:
        print(f"  FAILED — {device_name} unreachable (timeout)")
    except NetmikoAuthenticationException:
        print(f"  FAILED — {device_name} authentication failed")
    except Exception as e:
        print(f"  FAILED — {device_name} unexpected error: {e}")