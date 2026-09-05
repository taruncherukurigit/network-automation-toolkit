import re
import json
import os
from inventory import devices

RAW_DIR = "topology_raw"
CANONICAL_NAMES = [d["device_name"] for d in devices]

def normalize_name(raw_name):
    if not raw_name:
        return raw_name
    for canon in CANONICAL_NAMES:
        if canon.lower() in raw_name.lower():
            return canon
    return raw_name

def parse_cisco_detail(text):
    blocks = text.split("------------------------------------------------")
    neighbors = []
    for block in blocks:
        block = block.strip()
        if not block or block.startswith("Total entries"):
            continue
        entry = {}
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("Chassis id:"):
                entry["chassis_id"] = line.split(":", 1)[1].strip()
            elif line.startswith("Port id:"):
                entry["remote_port"] = line.split(":", 1)[1].strip()
            elif line.startswith("System Name:"):
                entry["system_name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Device type:"):
                entry["is_endpoint"] = True
        if entry:
            neighbors.append(entry)
    return neighbors

def parse_cisco_summary(text):
    lines = text.splitlines()
    started = False
    by_port_id = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Device ID"):
            started = True
            continue
        if not started or not stripped or stripped.startswith("Total entries"):
            continue
        fields = re.split(r"\s{2,}", stripped)
        if len(fields) == 5:
            _, local_intf, _, _, port_id = fields
        elif len(fields) == 4:
            _, local_intf, _, port_id = fields
        else:
            continue
        by_port_id[port_id] = local_intf
    return by_port_id

def parse_cisco_file(text):
    detail_text = text.split("=== SUMMARY ===")[0].replace("=== DETAIL ===", "")
    summary_text = text.split("=== SUMMARY ===")[1] if "=== SUMMARY ===" in text else ""
    details = parse_cisco_detail(detail_text)
    local_intf_by_port = parse_cisco_summary(summary_text)
    neighbors = []
    for d in details:
        neighbors.append({
            "remote_name": normalize_name(d.get("system_name", d.get("chassis_id"))),
            "remote_port": d.get("remote_port"),
            "local_intf": local_intf_by_port.get(d.get("remote_port")),
            "is_endpoint": d.get("is_endpoint", False),
        })
    return neighbors

def parse_fortigate_file(text):
    raw = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("lldprx.neighbor."):
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        parts = key.split(".")
        idx, field = parts[2], ".".join(parts[3:])
        raw.setdefault(idx, {})[field] = value

    neighbors = []
    for data in raw.values():
        neighbors.append({
            "remote_name": normalize_name(data.get("system.name.data")),
            "remote_port": data.get("port.id.data"),
            "local_intf": data.get("port.txt"),
            "is_endpoint": False,
        })
    return neighbors

def load_and_parse(device_name, parser_func):
    path = f"{RAW_DIR}/{device_name}.txt"
    if not os.path.exists(path):
        print(f"  SKIPPED — no raw data for {device_name} (device may have been unreachable)")
        return []
    with open(path) as f:
        return parser_func(f.read())

per_device = {
    "3560E": load_and_parse("3560E", parse_cisco_file),
    "1921": load_and_parse("1921", parse_cisco_file),
    "FortiGate": load_and_parse("FortiGate", parse_fortigate_file),
}

edges = []
for local_device, neighbors in per_device.items():
    for n in neighbors:
        if n["is_endpoint"]:
            continue
        edges.append({
            "device_a": local_device,
            "port_a": n["local_intf"],
            "device_b": n["remote_name"],
            "port_b": n["remote_port"],
        })

seen = set()
unique_edges = []
for e in edges:
    key = frozenset([(e["device_a"], e["port_a"]), (e["device_b"], e["port_b"])])
    if key in seen:
        continue
    seen.add(key)
    unique_edges.append(e)

print(json.dumps(unique_edges, indent=2))

with open("topology.json", "w") as f:
    json.dump(unique_edges, f, indent=2)