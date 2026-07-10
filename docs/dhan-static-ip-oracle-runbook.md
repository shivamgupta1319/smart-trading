# Dhan Static-IP Egress via Oracle Cloud Free Tier — Runbook

**Goal:** give the api container's Dhan order calls a fixed public IP so `setIP` works and
`DH-905 Invalid IP` goes away. Uses Oracle Always Free (₹0) as the static-IP egress box.

**Status:** Phase 1 (Oracle box) = USER. Phase 2 (tunnel) + Phase 3 (setIP) = Claude, on your go.

> ⚠️ `setIP` (Phase 3) **locks the IP for 7 days** and Dhan allows **one** IP per account.
> Do NOT run Phase 3 until Phase 1–2 verify the egress IP is stable.

---

## Phase 1 — Oracle account + static-IP VM  (YOU, ~20 min)

### 1. Sign up
1. Go to **https://signup.oraclecloud.com/**.
2. Country = **India**, enter email → verify the email link.
3. Account details:
   - **Cloud Account Name** (tenancy) — pick anything, e.g. `smt-egress`.
   - **Home Region** = **India West (Mumbai)** *or* **India South (Hyderabad)**.
     🔴 This is **permanent** and Always-Free VMs must live here. Pick Mumbai if offered
     (closest to Dhan); Hyderabad is fine too.
4. Verify phone via SMS.
5. **Payment verification:** enter a **debit card** (Visa/Mastercard debit works — Oracle calls it
   "a debit card that functions like a credit card"). A tiny temporary auth (~₹1–₹100) may appear and
   is auto-refunded. **Do NOT click "Upgrade to Pay As You Go"** — stay on Always Free = ₹0.
6. Accept agreement → account provisions in a few minutes → sign in to the Console.

### 2. Create the Always-Free VM
1. Console → ☰ menu → **Compute → Instances → Create instance**.
2. **Name:** `dhan-egress`.
3. **Image and shape → Edit:**
   - **Shape → Change shape → Specialty and previous generation** → **VM.Standard.E2.1.Micro**
     (AMD, "Always Free eligible", 1 OCPU / 1 GB). *Prefer this over Ampere/A1 — A1 is often
     "out of capacity" in India regions.* 1 GB is plenty for a proxy.
   - **Image → Change image → Canonical Ubuntu → Ubuntu 22.04** (Always Free eligible).
4. **Networking:** leave defaults (creates a new VCN + subnet). Ensure **Assign a public IPv4 address = Yes**.
5. **Add SSH keys:** choose **Paste public keys** and paste your key below (so I can reach it too).
   Get it with: `cat ~/.ssh/id_ed25519.pub` (or `id_rsa.pub`). Save the matching private key.
6. **Create.** Wait until state = **Running**. Note the **Public IP address** shown.

### 3. Make the IP static (reserve it)
The instance's public IP is **ephemeral** by default (changes on stop/start). Convert it:
1. Instance details → **Resources → Attached VNICs** → click the VNIC.
2. **IPv4 Addresses** → row for the primary private IP → **⋮ → Edit**.
3. Public IP type → **Reserved public IP → Create a new reserved public IP** → name it `dhan-egress-ip` → **Update**.
4. The IP is now **static** (survives reboots). Keep the instance **running** — don't stop it, so the
   reserved IP stays attached (free while attached) and the box isn't idle-reclaimed.

### 4. Open the tunnel port (two firewalls!)
Oracle blocks inbound by default in **two** places — both must allow our tunnel port (**UDP 51820**, WireGuard):
1. **Cloud firewall (Security List):** VCN → Subnet → **Security List** → **Add Ingress Rule**:
   - Source CIDR `0.0.0.0/0`, IP Protocol **UDP**, Destination Port **51820**. Save.
2. **Host firewall:** Ubuntu Oracle images ship restrictive iptables. I'll open it on the box in Phase 2
   (`iptables`/`netfilter-persistent`) — no action for you here.

### ✅ Hand-off to me — paste these:
- **Public (reserved) IP** of `dhan-egress`
- Confirmation SSH works: `ssh ubuntu@<that-ip>` logs in
- Which **home region** you chose (Mumbai/Hyderabad)

Add an SSH alias so I can reach it (I'll do this if you share the IP):
```
Host dhan-egress
  HostName <reserved-ip>
  User ubuntu
```

---

## Phase 2 — Egress tunnel  (CLAUDE, once box is reachable)
- Install WireGuard on Oracle + a peer on work-pc; open host firewall for UDP 51820.
- Scope routing so **only** the api's Dhan calls (`auth.dhan.co`, `api.dhan.co`) egress via Oracle —
  everything else on work-pc/api is untouched. (May need a ~10-line proxy tweak in
  `apps/api/src/dhan/dhan.service.ts` to bind its HTTP client to the tunnel; TBD after inspecting the client.)
- **Verify:** from inside the api container, `curl https://api.dhan.co` (or Dhan `getIP`) reports the
  **Oracle reserved IP**. Must be stable across a couple of checks before Phase 3.

## Phase 3 — Register IP + go live  (CLAUDE, with your explicit OK)
- `POST /v2/ip/setIP` with the Oracle reserved IP  ← **irreversible for 7 days**.
- Next EMA_RSI signal → real order should fill (no more `DH-905`).
- Reconcile fill vs sim; watch kill-switch. Live mode is already armed.

---

## Notes / gotchas
- **Cost:** ₹0 on Always Free. Only risk of charge = accidentally upgrading to Pay As You Go, or an
  **unattached** reserved IP. Keep the instance running with the IP attached.
- **Reliability bonus:** also fixes work-pc's flaky-broadband timeouts to Dhan.
- **Kill/rollback:** if anything misbehaves, `DHAN_TRADING_MODE=off` + `docker compose up -d api` on work-pc.
- **Do not** run Phase 3 twice / from a different IP within 7 days — the lock is per-account.
