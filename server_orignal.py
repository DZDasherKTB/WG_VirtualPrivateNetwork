


import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess, threading, time, os, sqlite3
from datetime import datetime
from collections import deque
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

BG="#1e1e1e"; BG2="#252525"; FG="#d4d4d4"
GREEN="#4ec94e"; RED="#f44747"; CYAN="#4fc1ff"
DIM="#555555"; MONO="Courier New"

HIST=60

def run(cmd):
    try: return subprocess.check_output(cmd,shell=True,stderr=subprocess.DEVNULL).decode().strip()
    except: return ""

def fmt_bytes(b):
    if b>=1e9: return f"{b/1e9:.2f} GB"
    if b>=1e6: return f"{b/1e6:.2f} MB"
    if b>=1e3: return f"{b/1e3:.1f} KB"
    return f"{b} B"

def fmt_rate(b):
    if b>=1e6: return f"{b/1e6:.2f} MB/s"
    if b>=1e3: return f"{b/1e3:.1f} KB/s"
    return f"{b:.0f} B/s"

def get_peers():
    out=run("sudo wg show wg0 dump")
    peers=[]
    for l in out.splitlines()[1:]:
        p=l.split("\t")
        if len(p)<8: continue
        peers.append({
            "key":p[0],
            "endpoint":p[2],
            "allowed":p[3],
            "rx":int(p[5]),
            "tx":int(p[6])
        })
    return peers

def get_next_ip():
    used=set()
    out=run("sudo wg show wg0 allowed-ips")
    for l in out.splitlines():
        for part in l.split()[1:]:
            ip=part.split("/")[0]
            if ip.startswith("10.8.0."):
                used.add(int(ip.split(".")[-1]))
    for i in range(2,255):
        if i not in used:
            return f"10.8.0.{i}"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WG Server")
        self.geometry("1000x700")
        self.configure(bg=BG)

        self.rx_hist=deque([0]*HIST,maxlen=HIST)
        self.tx_hist=deque([0]*HIST,maxlen=HIST)
        self.last_rx={}
        self.last_tx={}

        self.build()
        self.loop()

    def build(self):
        left=tk.Frame(self,bg=BG2,width=250)
        left.pack(side="left",fill="y")

        self.info=tk.Label(left,text="",bg=BG2,fg=FG,justify="left")
        self.info.pack(padx=10,pady=10)

        tk.Button(left,text="Start",command=self.start).pack(fill="x",padx=10)
        tk.Button(left,text="Stop",command=self.stop).pack(fill="x",padx=10)
        tk.Button(left,text="Add Peer",command=self.add_peer).pack(fill="x",padx=10)

        self.tree=ttk.Treeview(self,columns=("key","ip","rx","tx"),show="headings")
        for c in ("key","ip","rx","tx"):
            self.tree.heading(c,text=c)
        self.tree.pack(fill="both",expand=True)

        self.fig=Figure(figsize=(5,3))
        self.ax=self.fig.add_subplot(111)
        self.line_rx,=self.ax.plot([])
        self.line_tx,=self.ax.plot([])
        self.canvas=FigureCanvasTkAgg(self.fig,master=self)
        self.canvas.get_tk_widget().pack(fill="x")

    def start(self):
        threading.Thread(target=lambda:run("sudo wg-quick up wg0"),daemon=True).start()

    def stop(self):
        threading.Thread(target=lambda:run("sudo wg-quick down wg0"),daemon=True).start()

    def add_peer(self):
        priv=run("wg genkey")
        pub=run(f"echo '{priv}' | wg pubkey")
        ip=get_next_ip()

        run(f"sudo wg set wg0 peer {pub} allowed-ips {ip}/32")

        conf=f"""
[Interface]
PrivateKey = {priv}
Address = {ip}/32

[Peer]
PublicKey = {run('sudo wg show wg0 public-key')}
Endpoint = {run('curl -s ifconfig.me')}:51820
AllowedIPs = 0.0.0.0/0
"""
        print(conf)

    def loop(self):
        self.refresh()
        self.after(2000,self.loop)

    def refresh(self):
        peers=get_peers()

        total_rx=0; total_tx=0

        for r in self.tree.get_children():
            self.tree.delete(r)

        for p in peers:
            rx,tx=p["rx"],p["tx"]
            prx=self.last_rx.get(p["key"],rx)
            ptx=self.last_tx.get(p["key"],tx)

            rx_rate=max(0,rx-prx)
            tx_rate=max(0,tx-ptx)

            self.last_rx[p["key"]]=rx
            self.last_tx[p["key"]]=tx

            total_rx+=rx_rate
            total_tx+=tx_rate

            self.tree.insert("", "end", values=(
                p["key"][:10]+"…",
                p["allowed"],
                fmt_bytes(rx),
                fmt_bytes(tx)
            ))

        self.rx_hist.append(total_rx)
        self.tx_hist.append(total_tx)

        self.line_rx.set_data(range(len(self.rx_hist)),list(self.rx_hist))
        self.line_tx.set_data(range(len(self.tx_hist)),list(self.tx_hist))
        self.ax.set_xlim(0,HIST)
        self.ax.set_ylim(0,max(max(self.rx_hist),1)*1.2)
        self.canvas.draw_idle()

        self.info.config(text=f"""
Server IP: {run('curl -s ifconfig.me')}
Port: {run('sudo wg show wg0 listen-port')}
Peers: {len(peers)}
Traffic: ↓{fmt_rate(total_rx)} ↑{fmt_rate(total_tx)}
""")

if __name__=="__main__":
    if os.geteuid()!=0:
        print("Run with sudo")
        exit()
    App().mainloop()


