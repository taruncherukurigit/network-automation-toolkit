# Topology Discovery — Build Notes & Troubleshooting Log

Real issues encountered building the Automated Topology Discovery pipeline, documented honestly as they occurred — including the ones that were genuine design gaps, not just bugs.

---

### 1. FortiGate has no equivalent to `show lldp neighbors detail`

**Problem**
The Netmiko script worked immediately against both Cisco devices but returned nothing usable from the FortiGate — not an error, just data the parser couldn't make sense of.

**Diagnosis**
FortiOS doesn't expose LLDP neighbor data through a `show` command at all. It's a `diagnose` command instead — `diagnose lldprx neighbor details` — and the output format is completely different from Cisco's: flat, namespaced `key: value` pairs (`lldprx.neighbor.1.system.name.data: ...`) rather than Cisco's human-readable block format. Assuming "LLDP output" would look the same across vendors was the actual mistake here, not a code bug.

**Fix**
Built a per-device-type command lookup and two separate parser functions — one for Cisco's block format, one for FortiGate's key-value format — feeding into the same normalized data structure downstream. The rest of the pipeline never needs to know which vendor produced the data.

**Why it matters**
This is the difference between a script that works on the lab you tested it on and a tool that's actually vendor-agnostic. Any real network automation role touches a mixed-vendor environment eventually.

---

### 2. The same physical link was rendering as two separate edges

**Problem**
A network with exactly 3 real physical links was producing 5 edges after parsing — a clear sign of a deduplication bug, since a link between Device A and Device B should only ever be one edge, no matter which side reports it.

**Diagnosis**
Each end of a link identifies its neighbor differently. The FortiGate reported the switch simply as `"FortiGate-60E"` — which matched cleanly — but the switch's own LLDP advertisement included its full FQDN, `"Cherwood-3560E.cherwoodhq.local"`, which didn't match the canonical device name (`"3560E"`) used everywhere else in the toolkit. The deduplication logic was comparing these mismatched strings directly and never found the overlap.

**Fix**
Added a normalization step that matches any LLDP-reported hostname against the actual inventory device names (case-insensitive substring match) before deduplication runs. Both ends of a link now always resolve to the same canonical identity regardless of what each device happens to call itself.

**Why it matters**
Real network data is messy — hostnames, FQDNs, and self-reported identities rarely agree cleanly across vendors. Normalizing against a single source of truth (the inventory) rather than trusting device-reported strings is the correct pattern, not a one-off patch.

---

### 3. Cisco's LLDP detail output is missing the local interface entirely

**Problem**
After parsing, every neighbor entry had rich detail — chassis ID, system name, remote port — except the one field the entire topology diagram actually depends on: which *local* port the link was on.

**Diagnosis**
`show lldp neighbors detail` on this IOS version only reports information about the remote device — it never states which local interface received the advertisement. Without that, "the FortiGate is a neighbor" is true but useless; the diagram can't draw a specific edge.

**Fix**
Pulled a second command, `show lldp neighbors` (the summary table), which does include a `Local Intf` column, and cross-referenced the two outputs by the remote device's Port ID to reconstruct the missing local-side mapping.

**Why it matters**
A genuinely common pattern in network automation: no single `show` command gives you the complete picture, and building reliable tooling means knowing to cross-reference multiple data sources rather than assuming one output is authoritative.

---

### 4. Recurring `nano` saves silently not persisting

**Problem**
Multiple times during this build, a script was edited in `nano`, saved with the standard Ctrl+O / Enter / Ctrl+X sequence, and then re-run — only to execute the *old* version, with no error or warning that the edit hadn't landed.

**Diagnosis**
Root cause unconfirmed — likely a terminal/keystroke timing issue specific to this SSH session rather than a `nano` defect — but it happened often enough across the session to be a real, recurring pattern rather than a one-off mistake.

**Fix**
Switched to writing files via heredoc (`cat << 'EOF' > file.py ... EOF`) for any edit beyond a single trivial line. This writes the entire file atomically in one shell command, with no interactive editor state and no save step that can silently fail.

**Why it matters**
Verifying that a change actually took effect — rather than assuming a save succeeded — is a habit worth having generally, especially when troubleshooting "why isn't my fix working" turns out to be "my fix was never actually applied."

---

*Part of the [Automated Topology Discovery](./TOPOLOGY-DISCOVERY-README.md) build, under [Cherwood Network Solutions](https://networksolutions.tarunc.com).*