# Troubleshooting Log — Network Automation Toolkit

Real bugs, root causes, dead ends, and fixes — documented as they actually happened, not cleaned up to look flawless. This is the part of the project that's actually interesting.

---

## Bug #1 — `Illegal info request from server` (a 12-year-old, still-open Paramiko/Cisco IOS bug)

### Symptom

`backup_all.py` connected cleanly to the FortiGate on the first attempt. Every connection attempt to the Cisco 1921 and 3560E failed identically:

```
Exception (client): Illegal info request from server
paramiko.ssh_exception.SSHException: Illegal info request from server
```

The failure happened *after* successful authentication — debug logs showed `userauth is OK` immediately before the crash. Manual `ssh` with compatibility flags (`-oKexAlgorithms=+diffie-hellman-group14-sha1 -c aes256-cbc -oHostKeyAlgorithms=+ssh-rsa -oPubkeyAcceptedKeyTypes=+ssh-rsa`) worked flawlessly against the exact same devices, every time — proof the credentials, key, and account setup were all correct.

### What didn't work (documented honestly, not hidden)

- **Adding `disabled_algorithms` and `disable_sha2_fix` to the Netmiko connection** — no change, same error.
- **Downgrading Paramiko** (tried 2.12.0, then correctly-pinned 3.5.1) — no change. This ruled out the "recent Paramiko version regression" theory entirely.
- **Converting the SSH key from OpenSSH format to classic PEM format** — fixed a *different*, real problem (Paramiko was misidentifying the key type during auto-detection) but did not fix the underlying `Illegal info request` error.
- **A silent-ignore patch** (intercept the unexpected message and do nothing) — stopped the *error*, but caused the connection to hang until timeout instead, since the device was left waiting for a reply that never came.
- **An incorrect "send an empty INFO_RESPONSE" patch** — the device rejected it outright: `Protocol error: expected packet type 50, got 61`. Wrong guess at what the device actually wanted.

### Root cause — found via research, not guessing

Enabled full Paramiko debug logging and searched for the exact error signature. Found the same error, same log pattern (`userauth is OK` → `Illegal info request from server`), reported against Paramiko and Cisco IOS devices in open GitHub issues dating back to **December 2012** (`paramiko/paramiko#122`), recurring through 2014, 2016, 2017, 2018, and 2019 across `netmiko`, `ansible`, and raw `paramiko` issue trackers — never fully resolved by the maintainers, who stated plainly that reproducing device-specific SSH quirks without physical access to the hardware is genuinely difficult for a volunteer-maintained library.

The actual protocol-level explanation, from a maintainer's analysis in one of those threads: SSH public-key authentication is a two-step handshake per RFC 4252 — a client *may* send an unsigned "would this key work?" probe first, get a `PK_OK` reply, then send the signed proof. Paramiko takes a valid shortcut: it sends the signed proof immediately in one message, skipping the probe step. **Legacy Cisco IOS SSH servers don't handle that shortcut correctly** — they respond with `PK_OK` anyway, as if only the unsigned probe had arrived, effectively asking for the signature a second time even though it was already sent. Paramiko has no handler for receiving `PK_OK` at that point in the flow (it never sent a probe to warrant one) and throws a protocol error.

### The fix

A targeted compatibility patch, `ios_compat_patch.py`, that:
1. Caches the last signed public-key auth message Paramiko sends
2. If the server responds with the unexpected info-request message during public-key auth, resends that exact cached message instead of raising an error

This satisfies the device's redundant, non-standard request instead of trying to reinterpret or ignore it. Verified via debug logging showing `Authentication (publickey) successful!` followed by a real `show version` command executing and returning genuine device output.

### Why this wasn't routed around instead

An earlier, working alternative existed (calling the system `ssh` binary via `subprocess` for just the Cisco devices, keeping Netmiko only for the FortiGate). That would have worked immediately. It was deliberately set aside in favor of finding the real fix, since the actual research is the more valuable outcome — a subprocess workaround would have hidden a genuine, well-documented protocol-level bug rather than resolving it, and Netmiko/Paramiko now works cleanly and consistently across all three devices with one shared code path.

---

## Bug #2 — FortiGate reporting a false "change" on every single run

### Symptom

`drift_check.py` worked correctly and immediately for the 1921 and 3560E. The FortiGate reported `ALERT: FortiGate config CHANGED` on *every single run*, including consecutive runs with zero human-made changes in between.

### Diagnosis

Ran `git diff` against the flagged file directly rather than trusting the alert at face value. The diff showed genuine differences — but every single changed line matched one pattern:

```
-        set password ENC q205aLTmKPFpHxTzm0LTUGb...
+        set password ENC GINZc/E7OvTZnyFbL908oGA...
```

Every changed line was an encrypted `ENC` password/secret field. Nothing else in the config — no policies, no interfaces, no VLANs — had actually changed.

**Isolated the variable further:** connected to the FortiGate once and pulled `show full-configuration` twice in a row, in the same session, with nothing happening in between. The two pulls still differed, in exactly the same `ENC` fields.

### Root cause

FortiGate's `ENC` fields use encryption with a random salt component. The underlying secret value doesn't change, but the salt — and therefore the resulting ciphertext string — is regenerated fresh on every single config export. This is genuinely correct, secure encryption behavior on FortiGate's part; it just happens to be structurally incompatible with a naive text-diff-based drift check.

A second instance of the same problem was found later: PEM-format `ENCRYPTED PRIVATE KEY` blocks (SSL certificates) and `OPENSSH PRIVATE KEY` blocks (SSH host keys) exhibited the identical randomized-on-every-pull behavior, in a different text format the first fix didn't cover.

### Why this mattered enough to stop and fix properly

Left unaddressed, this is a genuinely dangerous failure mode for a monitoring tool — not because it's loud, but because it's *quietly* useless. A drift check that cries wolf every single night trains its operator to stop reading the alerts at all, which means the one night a real, meaningful change happens, it looks identical to every other night and gets ignored. A monitoring system that's wrong 100% of the time is worse than no monitoring system, because it creates false confidence that something is being watched.

### The fix

A normalization function, applied only to the FortiGate's `latest.txt` (the file used for drift comparison — never to the permanent timestamped backup, which always retains full real output):

```python
def normalize_fortigate_output(output):
    output = re.sub(r'(ENC\s+)\S+', r'\1[normalized]', output)
    output = re.sub(
        r'-----BEGIN ENCRYPTED PRIVATE KEY-----.*?-----END ENCRYPTED PRIVATE KEY-----',
        '-----BEGIN ENCRYPTED PRIVATE KEY-----\n[normalized]\n-----END ENCRYPTED PRIVATE KEY-----',
        output, flags=re.DOTALL,
    )
    output = re.sub(
        r'-----BEGIN OPENSSH PRIVATE KEY-----.*?-----END OPENSSH PRIVATE KEY-----',
        '-----BEGIN OPENSSH PRIVATE KEY-----\n[normalized]\n-----END OPENSSH PRIVATE KEY-----',
        output, flags=re.DOTALL,
    )
    return output
```

Verified by pulling the FortiGate twice consecutively after the fix and confirming a completely empty `git diff` — the same test that first proved the bug existed, now proving it's resolved.

### Stated tradeoff

This normalization means the drift check can no longer report *which specific* encrypted field changed on the FortiGate, only that a real, non-encryption-related config change occurred elsewhere. The full real encrypted values remain completely intact and unaffected in every permanent timestamped backup — this tradeoff applies only to the drift-comparison copy, and only reduces field-level specificity, not the underlying security or completeness of the backup itself.

---

## Bug #3 — Site silently served the wrong content (IPv6/IPv4 loopback mismatch)

### Symptom

After deploying `networksolutions.tarunc.com` (new nginx server block on the existing DMZ container, one new Cloudflare Tunnel ingress line — the same pattern used for every other Cherwood site on this container), the public URL intermittently served **Cherwood Health's** content instead of the new site's. No error, no failed request — just the wrong page, and inconsistently: some requests returned the correct site, others didn't, with no obvious pattern.

### What didn't work, checked in order with real evidence at each step

- **DNS resolution** — confirmed correct against both the local resolver and an external one (`nslookup ... 8.8.8.8`), returning real Cloudflare IPs.
- **Cloudflare's edge cache** — `cf-cache-status` header returned `DYNAMIC`, meaning Cloudflare wasn't caching the response at all; every request was reaching the origin fresh.
- **The file on disk** — `grep "<title>"` and `wc -l` against the actual file confirmed the correct content was sitting at the expected path, byte-for-byte.
- **nginx's config syntax and the enabled-sites symlink** — both confirmed correct via `nginx -t` and directly reading the config file.
- **The Cloudflare Tunnel's own ingress rule matching** — `cloudflared tunnel ingress rule <url>` (a built-in validator) confirmed the tunnel was correctly routing the hostname to `http://localhost:80`, the intended target.

Every individual layer checked out clean. The bug wasn't hiding behind a wrong answer anywhere — each component was doing exactly what it was told.

### Root cause

**`localhost` is not one fixed address.** It can resolve to `127.0.0.1` (IPv4) or `::1` (IPv6), and which one gets used depends on the connecting process's resolver behavior — not something visible in any of the configs above. The existing `default` nginx server block (serving Cherwood Health) had explicit listeners on both:
```nginx
listen 80;
listen [::]:80;
```
The newly-added `itsolutions` server block only had:
```nginx
listen 80;
```
When `cloudflared` connected over the IPv4 loopback path, it correctly reached `itsolutions`. When it connected over `::1` instead, there was no server block listening on that address for port 80 at all — so nginx fell through to `default`, the one block that *did* have an IPv6 listener, silently serving the wrong site with a normal `200 OK`.

This is why the symptom looked random: it wasn't a stable failure, it was a coin-flip on which loopback address the connecting process happened to use for any given request.

### The fix

Add the missing IPv6 listener to the new site's config:
```nginx
server {
    listen 80;
    listen [::]:80;
    server_name networksolutions.tarunc.com;
    root /var/www/itsolutions;
    index index.html;
}
```
Reload nginx. Verified by testing both loopback paths explicitly and independently:
```bash
curl -s -4 https://networksolutions.tarunc.com | grep "<title>"
curl -s -6 https://networksolutions.tarunc.com | grep "<title>"
```

The identical bug then recurred on a second, unrelated port (`8081`, serving `tarunc.com`) — a pre-existing server block that had been running correctly for weeks, apparently because whichever loopback path it was getting hit on had simply never surfaced the gap until this session's more careful dual-stack testing. Same fix applied: add `listen [::]:8081;` alongside the existing `listen 8081;`.

### Lesson

A `curl` test against `http://localhost:<port>` from the same host is not equivalent to testing the real public URL — it silently defaults to one address family and can report success while the actual internet-facing path is broken. Any server block fronted by a reverse proxy or tunnel needs both `listen` directives, even in a single-stack-looking environment, since the *connecting* process's address family isn't something the server side controls or can assume.

---

## Bug #4 — FortiGuard DNS filtering blocked new and existing subdomains, unpredictably

### Symptom

While diagnosing Bug #3, `nslookup networksolutions.tarunc.com` returned `208.91.112.55` — not a Cloudflare IP. That address turned out to be the FortiGate's own internal DNS-filter block page IP (a signature already known from an earlier Cherwood Health incident involving DuckDNS and `api.cloudflare.com`). Static domain-filter allow entries were added for `networksolutions.tarunc.com` via the GUI twice; both times, a CLI `show` immediately after confirmed neither entry had actually saved — the same silent GUI-save failure pattern observed earlier in the build with crontab and a dashboard screenshot filename. Adding the entries directly via CLI, then verifying with `show`, resolved it correctly.

Later in the same session, `tarunc.com` itself — a domain that had been live and unblocked for weeks — also began resolving to the same block-page IP, with no corresponding change made to it. It required its own static allow entries (`tarunc.com` and `*.tarunc.com`), added via CLI directly this time rather than the GUI.

### What this rules out, and what remains genuinely uncertain

A same-second test against a throwaway hostname created purely to test the theory (`netsoltest.tarunc.com`) hit the identical block despite having no history at all — which rules out anything specific to the string "networksolutions" (an earlier working theory, since that string resembles a real domain registrar's brand). The FortiGate's category-based DNS filter grid was checked directly and does **not** include a "Newly Observed/Registered Domain" category on this build (only "Potentially Liable" and "Security Risk" groups are configured) — ruling out that theory too, which had seemed like the natural explanation for age-correlated blocking.

**What's confirmed:** DNS resolution for names under `tarunc.com` can be intercepted by the FortiGate and redirected to its own block page, and static domain-filter allow-list entries reliably fix it once they're confirmed to have actually saved via CLI.

**What's not yet confirmed:** the exact trigger. It doesn't appear to be a static keyword match, a domain-age category, or anything visible in the currently-configured category groups. Given `tarunc.com` itself was affected with no config change made to it, live FortiGuard cloud-reputation lookups (rather than a local, static rule) are the most likely explanation — but this wasn't independently proven and would need further investigation if it recurs.

### The fix, and why CLI over GUI

```
config dnsfilter domain-filter
    edit 1
        config entries
            edit <next-id>
                set domain "<domain>"
                set action allow
            next
        end
    next
end
```
Followed immediately by:
```
config dnsfilter domain-filter
    edit 1
        show
    next
end
```
The `show` step isn't optional — this session's GUI "Create New" silently failed to persist the entry on two separate occasions, something a GUI success message gave no indication of. Every fix in this session that stuck was verified with a direct CLI read-back immediately after writing it.

### Lesson

On this FortiGate, GUI edits to DNS filter profiles cannot be trusted to have saved without an independent CLI verification step — this was true for the domain-filter static list at least three separate times across two nights of work. Treat any GUI "success" on this profile as unconfirmed until `show`'d back from the CLI.

---

## Cross-cutting lesson

Both of the first two bugs were found the same way: **isolate the variable, look at real evidence (debug logs, direct diffs), don't trust the first plausible-looking explanation.** The first patch attempt for Bug #1 was wrong. The first assumption about Bug #2 ("the FortiGate config actually changed") was wrong. The deployment bugs (#3 and #4) extended the same discipline into a different layer — network and DNS rather than code — and needed the same thing: rule out each real component one at a time with direct evidence, rather than assume the most familiar-looking suspect (caching, in both cases) was the actual cause. In every case, the fix that actually worked only became clear after generating real, direct evidence and reading it carefully — the same discipline Cherwood Health's own troubleshooting log describes as *"a check that has never been proven to fail against a real fault is not trustworthy."*
