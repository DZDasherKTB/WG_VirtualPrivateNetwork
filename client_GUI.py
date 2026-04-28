import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
import subprocess, threading, time, os, sqlite3
from datetime import datetime
from collections import deque
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.ticker as ticker

BG="#1e1e1e"; BG2="#252525"; BG3="#2d2d2d"
FG="#d4d4d4"; GREEN="#4ec94e"; RED="#f44747"
YELLOW="#dcdcaa"; BLUE="#569cd6"; CYAN="#4fc1ff"
DIMGRAY="#555555"; MONO="Courier New"

HIST=60
DB_FILE=os.path.expanduser("~/.wg_client_history.db")

def run(cmd):
    try: return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except: return ""

def init_db():
    con=sqlite3.connect(DB_FILE)
    con.execute("CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY,iface TEXT,connected_at INTEGER,disconnected_at INTEGER,rx_total INTEGER,tx_total INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS traffic(ts INTEGER,iface TEXT,rx INTEGER,tx INTEGER)")
    con.commit(); con.close()

def db_start_session(iface):
    con=sqlite3.connect(DB_FILE)
    cur=con.execute("INSERT INTO sessions (iface,connected_at,rx_total,tx_total) VALUES (?,?,0,0)",(iface,int(time.time())))
    sid=cur.lastrowid; con.commit(); con.close()
    return sid

def db_end_session(sid,rx,tx):
    con=sqlite3.connect(DB_FILE)
    con.execute("UPDATE sessions SET disconnected_at=?,rx_total=?,tx_total=? WHERE id=?",(int(time.time()),rx,tx,sid))
    con.commit(); con.close()

def db_log_traffic(iface,rx,tx):
    con=sqlite3.connect(DB_FILE)
    con.execute("INSERT INTO traffic VALUES (?,?,?,?)",(int(time.time()),iface,rx,tx))
    con.commit(); con.close()

def db_get_sessions():
    con=sqlite3.connect(DB_FILE)
    rows=con.execute("SELECT iface,connected_at,disconnected_at,rx_total,tx_total FROM sessions ORDER BY id DESC LIMIT 20").fetchall()
    con.close(); return rows

def list_configs():
    out=run("ls /etc/wireguard/*.conf 2>/dev/null")
    return [os.path.basename(f).replace(".conf","") for f in out.splitlines()] if out else []

def get_active_ifaces():
    out=run("sudo wg show interfaces")
    return out.split() if out else []

def get_wg_dump(iface):
    out=run(f"sudo wg show {iface} dump")
    lines=out.splitlines()
    result={"pubkey":"—","port":"—","peers":[]}
    if not lines: return result

    parts=lines[0].split("\t")
    result["pubkey"]=parts[1] if len(parts)>1 else "—"

    for line in lines[1:]:
        p=line.split("\t")
        if len(p)<8: continue
        hs=int(p[4]) if p[4].isdigit() else 0
        rx=int(p[5]) if p[5].isdigit() else 0
        tx=int(p[6]) if p[6].isdigit() else 0

        if hs==0: status,seen="Disconnected","Never"
        else:
            ago=int(time.time())-hs
            if ago<180: status,seen="Connected",f"{ago}s ago"
            elif ago<600: status,seen="Idle",f"{ago//60}m ago"
            else: status,seen="Stale",f"{ago//60}m ago"

        result["peers"].append({
            "pubkey":p[0],"endpoint":p[2] if p[2]!="(none)" else "—",
            "allowed":p[3],"seen":seen,"status":status,"rx":rx,"tx":tx
        })
    return result

def fmt_bytes(b):
    if b>=1_073_741_824: return f"{b/1_073_741_824:.2f} GiB"
    if b>=1_048_576: return f"{b/1_048_576:.2f} MiB"
    if b>=1024: return f"{b/1024:.1f} KiB"
    return f"{b} B"

def fmt_rate(b):
    if b>=1_000_000: return f"{b/1_000_000:.2f} MB/s"
    if b>=1000: return f"{b/1000:.1f} KB/s"
    return f"{b:.0f} B/s"

def get_dns():
    return run("grep nameserver /etc/resolv.conf | head -1").replace("nameserver","").strip() or "—"

def get_latency(endpoint):
    host=endpoint.split(":")[0] if endpoint and endpoint!="—" else None
    if not host: return "—"
    out=run(f"ping -c 1 -W 1 {host} | grep 'time=' | awk -F'time=' '{{print $2}}' | awk '{{print $1}}'")
    return f"{out} ms" if out else "—"

def get_local_wg_ip(iface):
    return run(f"ip addr show {iface} | grep 'inet ' | awk '{{print $2}}'") or "—"

class SessionHistoryDialog(tk.Toplevel):
    def __init__(self,parent):
        super().__init__(parent)
        self.title("History"); self.geometry("700x380"); self.configure(bg=BG)

        tree=ttk.Treeview(self,columns=("i","c","d","dur","rx","tx"),show="headings")
        for col in ("i","c","d","dur","rx","tx"): tree.heading(col,text=col)

        for row in db_get_sessions():
            iface,conn,dis,rx,tx=row
            conn=datetime.fromtimestamp(conn).strftime("%H:%M:%S") if conn else "—"
            dis=datetime.fromtimestamp(dis).strftime("%H:%M:%S") if dis else "Active"
            tree.insert("", "end", values=(iface,conn,dis,"—",fmt_bytes(rx),fmt_bytes(tx)))

        tree.pack(fill="both",expand=True)

class ClientApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WireGuard Client")
        self.geometry("1000x700"); self.configure(bg=BG)

        self.iface=tk.StringVar()
        self.rx_hist=deque([0]*HIST,maxlen=HIST)
        self.tx_hist=deque([0]*HIST,maxlen=HIST)
        self.lat_hist=deque([0]*HIST,maxlen=HIST)

        self.last_rx=0; self.last_tx=0
        self.session_id=None

        init_db()
        self.build_ui()
        self.refresh_loop()

    def build_ui(self):
        top=tk.Frame(self,bg=BG2); top.pack(fill="x")
        tk.Label(top,text="WireGuard Client",bg=BG2,fg=FG,font=(MONO,12,"bold")).pack(side="left")
        self.status=tk.Label(top,text="DISCONNECTED",fg=RED,bg=BG2)
        self.status.pack(side="right")

        left=tk.Frame(self,bg=BG2,width=250); left.pack(side="left",fill="y")
        right=tk.Frame(self,bg=BG); right.pack(side="left",fill="both",expand=True)

        self.iface_menu=ttk.Combobox(left,textvariable=self.iface,state="readonly")
        self.iface_menu.pack(fill="x",padx=10,pady=5)

        tk.Button(left,text="Connect",command=self.connect).pack(fill="x",padx=10)
        tk.Button(left,text="Disconnect",command=self.disconnect).pack(fill="x",padx=10)
        tk.Button(left,text="History",command=self.show_history).pack(fill="x",padx=10)

        self.info=tk.Label(left,text="",bg=BG2,fg=FG,justify="left")
        self.info.pack(fill="x",padx=10,pady=10)

        self.fig=Figure(figsize=(5,3),facecolor=BG)
        self.ax=self.fig.add_subplot(111,facecolor=BG2)
        self.line_rx,=self.ax.plot([],[])
        self.line_tx,=self.ax.plot([],[])

        self.canvas=FigureCanvasTkAgg(self.fig,master=right)
        self.canvas.get_tk_widget().pack(fill="both",expand=True)

        self.populate_ifaces()

    def populate_ifaces(self):
        vals=list_configs()+get_active_ifaces()
        vals=list(dict.fromkeys(vals)) or ["wg0"]
        self.iface_menu["values"]=vals
        self.iface.set(vals[0])

    def connect(self):
        iface=self.iface.get()
        threading.Thread(target=lambda:run(f"sudo wg-quick up {iface}"),daemon=True).start()
        self.session_id=db_start_session(iface)

    def disconnect(self):
        iface=self.iface.get()
        threading.Thread(target=lambda:run(f"sudo wg-quick down {iface}"),daemon=True).start()

    def show_history(self):
        SessionHistoryDialog(self)

    def refresh_loop(self):
        self.refresh()
        self.after(2000,self.refresh_loop)

    def refresh(self):
        iface=self.iface.get()
        active=get_active_ifaces()
        connected=iface in active

        self.status.config(text="CONNECTED" if connected else "DISCONNECTED",
                           fg=GREEN if connected else RED)

        if not connected: return

        dump=get_wg_dump(iface)
        if dump["peers"]:
            p=dump["peers"][0]
            rx,tx=p["rx"],p["tx"]

            rx_rate=max(0,rx-self.last_rx)
            tx_rate=max(0,tx-self.last_tx)

            self.last_rx=rx; self.last_tx=tx

            self.rx_hist.append(rx_rate)
            self.tx_hist.append(tx_rate)

            lat=get_latency(p["endpoint"])
            try: lat_val=float(lat.replace(" ms",""))
            except: lat_val=0
            self.lat_hist.append(lat_val)

            self.info.config(text=f"""
Peer: {p['endpoint']}
Handshake: {p['seen']}
RX: {fmt_bytes(rx)}
TX: {fmt_bytes(tx)}
Rate: ↓{fmt_rate(rx_rate)} ↑{fmt_rate(tx_rate)}
Latency: {lat}
""")

            self.update_graph()

    def update_graph(self):
        x=list(range(len(self.rx_hist)))
        self.line_rx.set_data(x,list(self.rx_hist))
        self.line_tx.set_data(x,list(self.tx_hist))
        self.ax.set_xlim(0,HIST)
        self.ax.set_ylim(0,max(max(self.rx_hist),max(self.tx_hist),1)*1.2)
        self.canvas.draw_idle()

if __name__=="__main__":
    ClientApp().mainloop()
