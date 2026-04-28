# WireGuard VPN Setup Guide

This guide provides the steps to establish a secure point-to-point connection between a Server and a Client (both Linux machines).

## 1. Installation (Both Machines)

Run the following commands on both the Server and the Client:

```bash
sudo apt update
sudo apt install wireguard -y
```

## 2. Generate Keys

Each machine needs its own pair of keys.

**On the Server:**

```bash
wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key
```

**On the Client:**

```bash
wg genkey | tee /etc/wireguard/client_private.key | wg pubkey > /etc/wireguard/client_public.key
```

## 3. Server Configuration

Create `/etc/wireguard/wg0.conf` on the Server.

## 4. Client Configuration

Create `/etc/wireguard/wg0.conf` on the Client.

## 5. Enable and Start

Perform these steps on both machines to start the VPN:

**a) Set permissions:**

```bash
sudo chmod 600 /etc/wireguard/wg0.conf
```

**b) Enable IP Forwarding (Server Only):**

```bash
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/conf.d/99-sysctl.conf
sudo sysctl -p
```

**c) Start WireGuard:**

```bash
sudo wg-quick up wg0
```

## 6. Verification

Check the connection status:

```bash
sudo wg show
ping 10.8.0.1
```

> **Note:** Ensure that UDP port 51820 is open on the Server's firewall (e.g., `ufw allow 51820/udp`).
