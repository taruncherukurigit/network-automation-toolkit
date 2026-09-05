## Automated Topology Discovery

**Automatically discovers and visualizes the live physical network topology using LLDP — no manual documentation, no static Visio diagrams to maintain by hand.**

Extends the Network Automation Toolkit with a nightly-scheduled pipeline that pulls Layer 2 neighbor data from every managed device, normalizes it across two completely different vendor implementations, and renders it as a live diagram served directly from the existing dashboard.

`Python` `Netmiko` `LLDP` `Graphviz` `Flask` `Cron` `Multi-vendor parsing`

---

### Why this exists

Network diagrams rot. The moment someone moves a cable, the Visio file on a shared drive is wrong, and nobody updates it until the next audit. This tool treats the topology diagram as a **generated artifact of the network's actual state**, not a document someone maintains by hand — every night, it re-asks the network what it's connected to and redraws itself accordingly.

### Architecture
┌─────────────┐ ┌──────────────────┐ ┌────────────────────┐ ┌─────────────────┐
│ topology.py │ --> │ parse_topology.py│ --> │ render_topology.py │ --> │ Flask /topology │
│ (LLDP pull) │ │ (normalize + │ │ (Graphviz SVG) │ │ (live diagram) │
│ │ │ dedupe edges) │ │ │ │ │
└─────────────┘ └──────────────────┘ └────────────────────┘ └─────────────────┘


| Stage | Script | What it does |
|---|---|---|
| 1. Collect | `topology.py` | Connects to every device via Netmiko and pulls LLDP neighbor data, using the correct command for each platform |
| 2. Normalize | `parse_topology.py` | Parses two structurally different vendor output formats into one clean edge list, deduplicates links reported from both ends, and filters out non-infrastructure endpoints |
| 3. Render | `render_topology.py` | Generates a styled SVG diagram from the normalized data using Graphviz |
| 4. Serve | `dashboard.py` (`/topology` route) | Serves the current diagram live, alongside the existing device-status dashboard |

### Multi-vendor LLDP handling

This is the core engineering problem the project solves: **Cisco and Fortinet expose LLDP data through entirely different commands and formats**, and neither gives you everything you need in a single call.

| | Cisco IOS (3560E, 1921) | FortiGate |
|---|---|---|
| Command | `show lldp neighbors detail` | `diagnose lldprx neighbor details` |
| Format | Human-readable text blocks | Flat `key: value` pairs |
| Local interface included? | ❌ No — requires a second command (`show lldp neighbors`) cross-referenced by port ID | ✅ Yes, directly in output |

The script abstracts this behind a single per-device-type command lookup and two dedicated parsers, so the rest of the pipeline works against one normalized data structure regardless of vendor.

### Automation

Runs nightly via cron, immediately after the existing backup and drift-check jobs, so the diagram always reflects the current LLDP state without any manual step:

```cron
0  21 * * * cd /root/automation-toolkit && python3 backup_all.py       >> backups/cron.log 2>&1
15 21 * * * cd /root/automation-toolkit && python3 drift_check.py      >> backups/cron.log 2>&1
30 21 * * * cd /root/automation-toolkit && python3 topology.py && python3 parse_topology.py && python3 render_topology.py >> backups/cron.log 2>&1
```

### Design decisions

- **Config-driven, not hardcoded.** Devices come from the same `inventory.py` used by every other tool in the toolkit — adding a new device to the topology map is a one-line addition, not a rewrite.
- **Endpoints are filtered, not just infrastructure.** LLDP-MED endpoints (laptops, workstations, anything without a proper system identity) are intentionally excluded from the diagram — a topology map should represent the network, not whoever happens to be plugged in that day.
- **Resilient to partial failure.** If a device is unreachable during collection, the parser skips it gracefully rather than crashing the whole pipeline — a partial topology is more useful than no topology.

### Running manually

```bash
cd /root/automation-toolkit
python3 topology.py
python3 parse_topology.py
python3 render_topology.py
```

### Viewing

| Page | URL |
|---|---|
| Device status | `http://<host>:5000/` |
| Live topology diagram | `http://<host>:5000/topology` |

---

*Part of [Cherwood Network Solutions](https://networksolutions.tarunc.com) — Division 03 of the Cherwood Corporation portfolio.*