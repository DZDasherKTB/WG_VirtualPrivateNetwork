<div align="center">

# WireGuard VPN : Self-Hosted Secure Network Tunnel

**A fully self-hosted, peer-to-peer VPN built on [WireGuard](https://www.wireguard.com/) : featuring automated setup, custom Python GUIs for both server and client, live traffic monitoring, and dynamic peer management.**

![WireGuard](https://img.shields.io/badge/WireGuard-88171A?style=for-the-badge&logo=wireguard&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)
![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

</div>

---

## Overview

This project sets up a secure, encrypted tunnel between a **server** and one or more **clients** using WireGuard : one of the fastest and most modern VPN protocols available. Unlike heavier solutions (OpenVPN, IPSec), WireGuard lives inside the Linux kernel, uses state-of-the-art cryptography (Curve25519, ChaCha20, BLAKE2), and can establish a handshake in milliseconds.

On top of the core tunnel, this project ships:

- **`server_GUI.py`** : A Tkinter dashboard that shows all connected peers, live RX/TX rates, and lets you add new peers dynamically with one click.
- **`client_GUI.py`** : A Tkinter client panel that shows connection status, handshake age, per-peer stats, latency, and a rolling 60-second traffic graph. Session history is logged to a local SQLite database.
- **Config templates** for both server (`server_wg0.conf`) and client (`client_wg0.conf`) with sane defaults and multi-peer support baked in.

---

## 📁 Repository Structure

```
WG_VirtualPrivateNetwork/
│
├── server_wg0.conf       # WireGuard config for the server machine
├── client_wg0.conf       # WireGuard config for the client machine
│
├── server_GUI.py         # Python GUI : server side (peer table, traffic graph, add peer)
├── client_GUI.py         # Python GUI : client side (status, stats, session history)
│
└── README.md
```

---

## How WireGuard Works (The Short Version)

WireGuard works differently from traditional VPNs. There are no certificates, no complex handshake protocols, and no persistent connection state to manage. Instead:

1. Each machine generates a **public/private keypair**.
2. Peers exchange **public keys** and configure each other as trusted endpoints.
3. WireGuard creates a virtual network interface (`wg0`) on each machine.
4. All traffic through that interface is **encrypted end-to-end** using the keypair.
5. The server routes packets between peers using kernel-level IP forwarding and `iptables` NAT rules.

The result: a fast, silent tunnel. If no packets are being sent, WireGuard is invisible on the network.

---

## Prerequisites

- Two or more **Linux machines** (Ubuntu/Debian recommended)
- Python 3.8+ on both machines (for the GUIs)
- `sudo` / root access
- The following Python packages:

```bash
pip install matplotlib
# tkinter is usually included with Python; if not:
sudo apt install python3-tk -y
```

---

##  Setup Guide

### Step 1 : Install WireGuard (Both Machines)

```bash
sudo apt update
sudo apt install wireguard -y
```

Verify the install:

```bash
wg --version
# Expected: wireguard-tools vX.X.X
```

---

### Step 2 : Generate Keypairs

Each machine needs its own **private key** (kept secret) and a **public key** (shared with peers).

**On the Server:**

```bash
wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key
sudo chmod 600 /etc/wireguard/server_private.key
```

**On the Client:**

```bash
wg genkey | tee /etc/wireguard/client_private.key | wg pubkey > /etc/wireguard/client_public.key
sudo chmod 600 /etc/wireguard/client_private.key
```

Read back the keys you'll need shortly:

```bash
# Server : read public key to share with clients
cat /etc/wireguard/server_public.key

# Client : read public key to register on server
cat /etc/wireguard/client_public.key
```

>  Never share your private key. The `.key` files should only be readable by root (`chmod 600`).

---

### Step 3 : Configure the Server

Create `/etc/wireguard/wg0.conf` on the server:

```ini
[Interface]
Address = 10.8.0.1/24
ListenPort = 51820
PrivateKey = <Server_Private_Key>

# iptables rules : applied on tunnel up/down
# Replace wlp4s0 with your actual outbound interface (check with: ip route | grep default)
PostUp   = iptables -A FORWARD -i wg0 -j ACCEPT; \
           iptables -A FORWARD -o wg0 -j ACCEPT; \
           iptables -t nat -A POSTROUTING -o wlp4s0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; \
           iptables -D FORWARD -o wg0 -j ACCEPT; \
           iptables -t nat -D POSTROUTING -o wlp4s0 -j MASQUERADE

# --- Peers ---

[Peer]
PublicKey = <Client_Public_Key>
AllowedIPs = 10.8.0.2/32
```

**To add more clients**, append additional `[Peer]` blocks:

```ini
[Peer]
PublicKey = <Client2_Public_Key>
AllowedIPs = 10.8.0.3/32

[Peer]
PublicKey = <Client3_Public_Key>
AllowedIPs = 10.8.0.4/32
```

Each peer gets a unique `/32` IP in the `10.8.0.0/24` range. The server holds `.1`, clients start from `.2`.

---

### Step 4 : Configure the Client

Create `/etc/wireguard/wg0.conf` on the client:

```ini
[Interface]
PrivateKey = <Client_Private_Key>
Address = 10.8.0.2/32
DNS = 1.1.1.1

[Peer]
PublicKey = <Server_Public_Key>
Endpoint = <Server_IP>:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
```

Key options explained:

| Option | Purpose |
|---|---|
| `Address` | The client's IP on the VPN (`10.8.0.2/32`) |
| `DNS` | DNS server to use when tunneled (Cloudflare here) |
| `Endpoint` | Server's IP and WireGuard port |
| `AllowedIPs = 0.0.0.0/0` | Route **all traffic** through the tunnel (full tunnel mode) |
| `PersistentKeepalive = 25` | Send a keepalive every 25s to maintain the connection through NAT |

---

### Step 5 : Enable IP Forwarding (Server Only)

The server needs to forward packets between the VPN interface and the internet:

```bash
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

Confirm it took effect:

```bash
sysctl net.ipv4.ip_forward
# Expected: net.ipv4.ip_forward = 1
```

---

### Step 6 : Set Permissions and Start WireGuard

**On both machines:**

```bash
sudo chmod 600 /etc/wireguard/wg0.conf
sudo wg-quick up wg0
```

**To start automatically on boot:**

```bash
sudo systemctl enable wg-quick@wg0
```

**To stop the tunnel:**

```bash
sudo wg-quick down wg0
```

---

### Step 7 : Open the Firewall Port (Server Only)

If UFW is active:

```bash
sudo ufw allow 51820/udp
sudo ufw reload
```

Verify the port is listening:

```bash
sudo ss -ulnp | grep 51820
# Expected output: UNCONN  0  0  0.0.0.0:51820  ...  users:(("wg",pid=...,fd=...))
```

---

## Verification Commands

Once both sides are up, run these to confirm everything is working:

### Check the tunnel interface

```bash
ip a | grep wg0 -A 3
```

You should see the `wg0` interface with the assigned VPN IP (`10.8.0.1` on server, `10.8.0.2` on client).

### Check WireGuard status

```bash
sudo wg show
```

A healthy output looks like:

```
interface: wg0
  public key: <your-public-key>
  private key: (hidden)
  listening port: 51820

peer: <client-public-key>
  endpoint: 192.168.x.x:XXXXX
  allowed ips: 10.8.0.2/32
  latest handshake: 5 seconds ago
  transfer: 1.23 MiB received, 456 KiB sent
```

If `latest handshake` shows a recent time, the tunnel is live.

### Live monitoring (refreshes every second)

```bash
watch -n 1 sudo wg
```

### Ping across the tunnel

```bash
# From client, ping server's VPN IP
ping 10.8.0.1

# From server, ping client's VPN IP
ping 10.8.0.2
```

### Verify your traffic is routed through the server

```bash
curl ifconfig.me
```

If the returned IP matches the **server's** public IP, your traffic is correctly tunneling through.

### Check your machine's IPs

```bash
hostname -I
```

You should see both your physical IP and the WireGuard VPN IP (`10.8.0.x`).

### Check NAT rules are active (Server)

```bash
sudo iptables -t nat -L -n -v
```

Look for a `MASQUERADE` rule on the `POSTROUTING` chain. This is what allows the server to forward client traffic to the internet.

### Read the running config

```bash
sudo cat /etc/wireguard/wg0.conf
```

---

## 🦈 Verification with Wireshark

Wireshark lets you visually confirm that WireGuard is encrypting your traffic correctly.

### Install Wireshark

```bash
sudo apt install wireshark -y
sudo usermod -aG wireshark $USER
# Log out and back in for group change to take effect
```

### Capture on the physical interface (e.g., `wlp4s0`)

Open Wireshark, select your physical interface, and apply this filter:

```
udp.port == 51820
```

You will see WireGuard UDP packets. The payload will be **completely opaque** : raw encrypted bytes. You cannot read the contents. This is correct and expected : it proves your tunnel is encrypting everything.

### Capture on the `wg0` interface

Switch Wireshark to capture on the `wg0` interface. Now filter for:

```
icmp
```

Then run `ping 10.8.0.1` from the client. You will see **plaintext ICMP** packets here : because you're looking at traffic *before* it gets encrypted by WireGuard. This confirms the tunnel is decapsulating and delivering packets correctly to the VPN layer.

### What to look for : summary

| Capture Interface | Filter | What You See | What it Means |
|---|---|---|---|
| `wlp4s0` (physical) | `udp.port == 51820` | Encrypted WireGuard UDP | Tunnel is encrypting traffic |
| `wg0` (virtual) | `icmp` | Plaintext ping packets | Tunnel is delivering decrypted traffic |
| `wlp4s0` (physical) | `icmp` | Nothing | ICMP is inside the tunnel : not exposed |

---

## The GUIs

Both GUIs are standalone Python scripts using Tkinter + Matplotlib. No web server, no browser required.

### Server GUI : `server_GUI.py`

Run on the server machine:

```bash
sudo python3 server_GUI.py
```

> Must be run as root (it calls `sudo wg` internally).

**What it does:**

- **Peer table** : lists every connected peer with their VPN IP (`AllowedIPs`), total bytes received, and total bytes sent. Updates every 2 seconds.
- **Traffic graph** : a rolling 60-second plot of aggregate RX/TX rates across all peers.
- **Start / Stop buttons** : brings `wg0` up or down via `wg-quick`.
- **Add Peer button** : generates a fresh keypair, auto-assigns the next available IP in `10.8.0.0/24`, registers the peer live with `wg set`, and prints the complete client config to stdout. No restart required : WireGuard handles this hot.

**How peer auto-assignment works:**

The script reads currently registered `AllowedIPs` from `wg show wg0 allowed-ips`, builds a set of used IPs in `10.8.0.x`, and picks the next integer. So if `.2`, `.3`, `.5` are taken, it will assign `.4`.

---

### Client GUI : `client_GUI.py`

Run on the client machine:

```bash
python3 client_GUI.py
```

**What it does:**

- **Interface selector** : auto-detects available WireGuard configs from `/etc/wireguard/*.conf` and active interfaces.
- **Connect / Disconnect** : runs `wg-quick up/down` in a background thread so the UI stays responsive.
- **Live stats panel** : shows peer endpoint, handshake age, cumulative RX/TX, current RX/TX rates, and latency (live ping to the server endpoint).
- **60-second rolling traffic graph** : RX and TX plotted over time.
- **Session history** : every connect/disconnect is logged to `~/.wg_client_history.db` (SQLite). Click the History button to see the last 20 sessions with timestamps and total bytes.

**How handshake status works:**

The client reads `wg show <iface> dump` and interprets the handshake timestamp:

| Handshake Age | Status Shown |
|---|---|
| < 3 minutes | `Connected` |
| 3–10 minutes | `Idle` |
| > 10 minutes | `Stale` |
| No handshake | `Disconnected` |

---

##  Adding a New Client (Manual)

If you prefer doing it by hand instead of using the GUI button:

**1. Generate keys on the new client:**

```bash
wg genkey | tee /etc/wireguard/client_private.key | wg pubkey > /etc/wireguard/client_public.key
cat /etc/wireguard/client_public.key
```

**2. Register the peer on the server (hot : no restart needed):**

```bash
sudo wg set wg0 peer <NEW_CLIENT_PUBLIC_KEY> allowed-ips 10.8.0.X/32
```

**3. Persist it by adding a `[Peer]` block to `/etc/wireguard/wg0.conf` on the server:**

```ini
[Peer]
PublicKey = <NEW_CLIENT_PUBLIC_KEY>
AllowedIPs = 10.8.0.X/32
```

**4. Create the client's `wg0.conf`:**

```ini
[Interface]
PrivateKey = <NEW_CLIENT_PRIVATE_KEY>
Address = 10.8.0.X/32
DNS = 1.1.1.1

[Peer]
PublicKey = <SERVER_PUBLIC_KEY>
Endpoint = <SERVER_IP>:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
```

---

## Troubleshooting

**Tunnel comes up but no ping across it**
- Check `sudo wg show` : if there's no `latest handshake`, the two sides haven't spoken. Usually a firewall issue.
- Confirm UDP 51820 is open: `sudo ss -ulnp | grep 51820`
- Check the client's `Endpoint` IP is correct and reachable.

**`wg-quick up wg0` fails with "RTNETLINK answers: Operation not supported"**
- WireGuard kernel module isn't loaded: `sudo modprobe wireguard`

**Traffic goes through the tunnel but internet doesn't work**
- IP forwarding is likely off on the server: `sysctl net.ipv4.ip_forward` should return `1`.
- NAT rules may not have applied: `sudo iptables -t nat -L -n -v` : look for `MASQUERADE`.
- Make sure `PostUp` in the server config references the correct outbound interface (`ip route | grep default` to find it).

**Handshake shows "Stale" in client GUI**
- The server may have rebooted or the peer entry was removed. Re-run `wg-quick up wg0` on the client.
- Check that `PersistentKeepalive = 25` is set in the client config if you're behind NAT.

**GUI won't launch : "No module named matplotlib"**
```bash
pip install matplotlib
```

---

## Further Reading

- [WireGuard Official Docs](https://www.wireguard.com/)
- [WireGuard Whitepaper](https://www.wireguard.com/papers/wireguard.pdf)
- [Linux `ip` command reference](https://man7.org/linux/man-pages/man8/ip.8.html)
- [Wireshark User Guide](https://www.wireshark.org/docs/wsug_html/)

---

## License

MIT : do whatever you want with it.

---

<div align="center">
Built with WireGuard, Python, and too many <code>sudo wg show</code> commands.
</div>
