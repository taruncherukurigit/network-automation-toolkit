# Architecture — Network Automation Toolkit

Design rationale for Cherwood Network Solutions' first system: an unattended nightly automation toolkit that backs up, version-controls, and drift-checks configuration across Cherwood Health's core network devices.

## Design philosophy

This is the one piece of infrastructure in the entire Cherwood Corporation portfolio holding SSH credentials to every core device in the network at once. Every design decision here starts from that fact — isolate it, scope its access narrowly, give it its own identity, and never let convenience quietly widen its reach. This mirrors how a real managed service provider is scoped into a client's environment: least-privilege, auditable, independently revocable, not blanket trust because it's operationally easier.

## Topology

```
INTERNET
    │
[FortiGate 60E]
    │
[Cisco 3560E]  ── Gi0/3 (FortiGate trunk) ── Gi0/6 (Proxmox trunk)
    │                                              │
    │                                        [Proxmox / T14]
    │                                              │
    │                                          [vmbr0]
    │                              ┌───────────────┼───────────────┐
    │                    other VLANs (30/40)          [automation-toolkit]
    │                                                   VLAN 60, 10.10.60.10
    │
[Cisco 1921]
10.10.99.2
```

VLAN 60 (`10.10.60.0/24`) rides the same physical trunk already carrying Cherwood Health's other VLANs — no new cabling, no new physical infrastructure. The isolation is entirely logical: VLAN tagging on the trunk, plus firewall policy at Layer 3.

## Firewall policy — the actual segmentation boundary

Four policies, all VLAN 60-originating (nothing routes *into* VLAN 60 except the reverse of an established session — no policy permits any other VLAN to initiate traffic toward the automation container):

| Policy | Direction | Scope |
|---|---|---|
| `NetSol_to_Switch_MGMT` | VLAN60 → VLAN10_Trusted | SSH+SNMP to the 3560E's management IP only |
| `NetSol_to_Branch_MGMT` | VLAN60 → internal2 | SSH+SNMP to the 1921 only |
| `NetSol_to_Internet` | VLAN60 → wan1 | General egress (package installs, Git) |
| `NetSol_to_Core_DENY` | VLAN60 → VLAN10_Trusted | Explicit, logged DENY — a belt-and-suspenders backstop below the narrow ACCEPT rules, not relying on implicit-deny alone for a segment this sensitive |

This matches the explicit-DENY design principle already established in Cherwood Health's own Guest VLAN policy — an explicit, logged DENY is more auditable and more resilient to a future accidental config change than relying purely on default-deny.

## Identity — svc-automation

A dedicated service account, distinct from the `admin` account Cherwood Health's own backup scripts use:

- **Independent revocation.** If this container's key is ever suspected compromised, disabling `svc-automation` doesn't touch any other identity's access.
- **Audit-trail attribution.** Every action in device logs is traceable to this one specific account, not a shared login used by humans and scripts alike.
- **RSA, not Ed25519.** The 1921's SSH stack only supports `ssh-rsa` — discovered and documented once, applied consistently.

Stated tradeoff: both the 1921/3560E (privilege 15) and the FortiGate (`super_admin`) grant this account broad platform access, since neither device has granular role-based CLI access configured in this lab. A production deployment would scope this to read-only config access specifically.

## Data flow

```
cron (2:00 AM)
    │
backup_all.py ── connects via Netmiko + ios_compat_patch.py
    │
    ├── writes timestamped permanent snapshot (full, unmodified)
    └── writes latest.txt (FortiGate output normalized for drift comparison)
    │
git commit (baseline, if changed)
    │
cron (2:15 AM)
    │
drift_check.py ── git diff latest.txt vs. last commit
    │
    ├── OK → logged, no commit
    └── ALERT → logged with diff, committed as new baseline
    │
dashboard.py ── reads drift_check.log, serves live status on :5000
```

## Why Git, not just a diff log

Cherwood Health's original bash scripts compared each pull only against the single most recent one. This toolkit's use of a real Git repository means every historical state is preserved and queryable — `git diff` between *any* two points in time, not just "now vs. yesterday." A structurally stronger record for exactly the same operational cost.
