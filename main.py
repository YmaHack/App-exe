import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import struct

APP_TITLE = "Yamaha Style Studio"
VERSION = "0.1.0"

def vlq(n):
    n = max(0, int(n)); buf = [n & 0x7f]; n >>= 7
    while n:
        buf.insert(0, (n & 0x7f) | 0x80); n >>= 7
    return bytes(buf)

def read_vlq(data, pos):
    value = 0
    while pos < len(data):
        b = data[pos]; pos += 1
        value = (value << 7) | (b & 0x7f)
        if not b & 0x80: break
    return value, pos

class MidiStyle:
    """Read SMF chunks and preserve unrecognized chunks byte-for-byte."""
    def __init__(self, raw):
        self.header = None; self.chunks = []; self.tracks = []
        pos = 0
        while pos + 8 <= len(raw):
            tag = raw[pos:pos+4]; size = struct.unpack(">I", raw[pos+4:pos+8])[0]
            end = pos + 8 + size
            if end > len(raw): raise ValueError("קובץ פגום: אורך מקטע חורג מהקובץ")
            payload = raw[pos+8:end]
            if tag == b"MThd": self.header = payload
            elif tag == b"MTrk":
                self.tracks.append(self._parse_track(payload)); self.chunks.append(("track", len(self.tracks)-1))
            else: self.chunks.append(("raw", tag + struct.pack(">I", size) + payload))
            pos = end
        if self.header is None or not self.tracks:
            raise ValueError("לא נמצא מבנה Standard MIDI מוכר. ייתכן שזה קובץ STY בפורמט שאינו נתמך.")
        if len(self.header) < 6: raise ValueError("כותרת MIDI לא תקינה")
    @staticmethod
    def _parse_track(data):
        events=[]; pos=0; tick=0; running=None
        while pos < len(data):
            delta,pos=read_vlq(data,pos); tick += delta
            if pos >= len(data): break
            status=data[pos]
            if status & 0x80:
                pos += 1
                if status < 0xf0: running=status
            else:
                if running is None: raise ValueError("אירוע MIDI לא תקין")
                status=running
            if status == 0xff:
                if pos >= len(data): break
                typ=data[pos]; pos+=1; size,pos=read_vlq(data,pos)
                payload=data[pos:pos+size]; pos+=size
                events.append([tick,"meta",typ,payload])
                if typ == 0x2f: break
            elif status in (0xf0,0xf7):
                size,pos=read_vlq(data,pos); payload=data[pos:pos+size]; pos+=size
                events.append([tick,"sysex",status,payload])
            else:
                kind=status & 0xf0; ch=status & 0x0f; n=1 if kind in (0xc0,0xd0) else 2
                if pos+n > len(data): break
                a=data[pos]; b=data[pos+1] if n==2 else 0; pos+=n
                events.append([tick,"channel",ch,kind,a,b])
        return events
    @staticmethod
    def _encode_track(events):
        out=bytearray(); last=0
        for e in sorted(events,key=lambda x:x[0]):
            tick=e[0]; out += vlq(tick-last); last=tick
            if e[1]=="meta": out += bytes([0xff,e[2]])+vlq(len(e[3]))+e[3]
            elif e[1]=="sysex": out += bytes([e[2]])+vlq(len(e[3]))+e[3]
            else:
                _,_,ch,kind,a,b=e; out += bytes([kind|ch,a])
                if kind not in (0xc0,0xd0): out += bytes([b])
        if not any(e[1]=="meta" and e[2]==0x2f for e in events): out += b"\x00\xff\x2f\x00"
        return b"MTrk"+struct.pack(">I",len(out))+out
    def encode(self):
        h=bytearray(self.header)
        if len(h)>=6: h[2:4]=struct.pack(">H",len(self.tracks))
        out=bytearray(b"MThd"+struct.pack(">I",len(h))+h)
        for kind,val in self.chunks: out += self._encode_track(self.tracks[val]) if kind=="track" else val
        return bytes(out)
    def track_name(self, idx):
        for e in self.tracks[idx]:
            if e[1]=="meta" and e[2]==3: return e[3].decode("utf-8",errors="replace")
        return f"רצועה {idx+1}"

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(APP_TITLE); self.geometry("1100x720"); self.minsize(850,560)
        self.stylefile=None; self.data=None; self.current_track=0; self._ui()
    def _ui(self):
        top=ttk.Frame(self,padding=12); top.pack(fill="x")
        ttk.Label(top,text="Yamaha Style Studio",font=("Segoe UI",20,"bold")).pack(side="left")
        ttk.Label(top,text="עריכת מקצבי STY • גרסת ניסוי",foreground="#526174").pack(side="left",padx=16)
        bar=ttk.Frame(self,padding=(12,0,12,10)); bar.pack(fill="x")
        ttk.Button(bar,text="פתח קובץ STY",command=self.open_file).pack(side="left")
        ttk.Button(bar,text="שמור בשם…",command=self.save_as).pack(side="left",padx=6)
        self.filelabel=ttk.Label(bar,text="לא נבחר קובץ"); self.filelabel.pack(side="left",padx=12)
        self.status=ttk.Label(self,text="פתח קובץ STY כדי להתחיל.",padding=10); self.status.pack(side="bottom",fill="x")
        panes=ttk.Panedwindow(self,orient="horizontal"); panes.pack(fill="both",expand=True,padx=12,pady=8)
        left=ttk.Frame(panes,padding=8); right=ttk.Frame(panes,padding=12); panes.add(left,weight=1); panes.add(right,weight=3)
        ttk.Label(left,text="רצועות (Tracks)",font=("Segoe UI",12,"bold")).pack(anchor="w")
        self.tracklist=tk.Listbox(left,exportselection=False,font=("Segoe UI",11),width=28)
        self.tracklist.pack(fill="both",expand=True,pady=8); self.tracklist.bind("<<ListboxSelect>>",self.select_track)
        ttk.Label(right,text="עריכת ערוץ / רצועה",font=("Segoe UI",15,"bold")).pack(anchor="w")
        self.tracktitle=ttk.Label(right,text="בחר רצועה"); self.tracktitle.pack(anchor="w",pady=(4,14))
        controls=ttk.LabelFrame(right,text="עוצמה וכלי נגינה",padding=12); controls.pack(fill="x")
        ttk.Label(controls,text="עוצמת ערוץ (MIDI CC7)").grid(row=0,column=0,sticky="w",padx=5,pady=6)
        self.volscale=ttk.Scale(controls,from_=0,to=127,command=self.vol_changed); self.volscale.set(100); self.volscale.grid(row=0,column=1,sticky="ew",padx=8)
        self.vallabel=ttk.Label(controls,text="100"); self.vallabel.grid(row=0,column=2,padx=5)
        ttk.Button(controls,text="החל עוצמה לרצועה",command=self.apply_volume).grid(row=0,column=3,padx=5)
        ttk.Label(controls,text="כלי נגינה (Program Change, 0–127)").grid(row=1,column=0,sticky="w",padx=5,pady=6)
        self.program=tk.IntVar(value=0); ttk.Spinbox(controls,from_=0,to=127,textvariable=self.program,width=8).grid(row=1,column=1,sticky="w",padx=8)
        ttk.Button(controls,text="החל כלי לרצועה",command=self.apply_program).grid(row=1,column=3,padx=5); controls.columnconfigure(1,weight=1)
        ttk.Label(right,text="אירועי MIDI מדויקים",font=("Segoe UI",12,"bold")).pack(anchor="w",pady=(18,6))
        self.events=ttk.Treeview(right,columns=("tick","type","channel","data"),show="headings",height=14)
        for c,t,w in [("tick","זמן (ticks)",100),("type","סוג אירוע",180),("channel","ערוץ",80),("data","נתונים",330)]:
            self.events.heading(c,text=t); self.events.column(c,width=w,anchor="w")
        self.events.pack(fill="both",expand=True)
        ttk.Label(right,text="זהו אב-טיפוס: קובצי STY מסוימים כוללים נתוני CASM/OTS מורכבים שעדיין לא נבדקו. שמור עותק מהמקור ובדוק את הקובץ בכלי Yamaha.",wraplength=780,foreground="#7a4b12").pack(anchor="w",pady=8)
    def vol_changed(self,v): self.vallabel.configure(text=str(int(float(v))))
    def open_file(self):
        p=filedialog.askopenfilename(title="בחר מקצב Yamaha",filetypes=[("Yamaha Style","*.sty"),("MIDI","*.mid *.midi"),("כל הקבצים","*.*")])
        if not p:return
        try: self.data=MidiStyle(Path(p).read_bytes()); self.stylefile=Path(p)
        except Exception as e: messagebox.showerror("לא ניתן לפתוח",str(e)); return
        self.filelabel.configure(text=self.stylefile.name); self.tracklist.delete(0,"end")
        for i in range(len(self.data.tracks)): self.tracklist.insert("end",self.data.track_name(i))
        self.tracklist.selection_set(0); self.show_track(0)
        self.status.configure(text=f"נטענו {len(self.data.tracks)} רצועות. שמור תמיד עותק של המקור.")
    def select_track(self,_=None):
        sel=self.tracklist.curselection()
        if sel:self.show_track(sel[0])
    def show_track(self,i):
        self.current_track=i; self.events.delete(*self.events.get_children()); self.tracktitle.configure(text=self.data.track_name(i))
        for e in self.data.tracks[i]:
            if e[1]=="channel":
                _,_,ch,k,a,b=e; typ={0x80:"Note Off",0x90:"Note On",0xa0:"Aftertouch",0xb0:"Control Change",0xc0:"Program Change",0xd0:"Channel Pressure",0xe0:"Pitch Bend"}.get(k,f"MIDI {k:02X}")
                self.events.insert("","end",values=(e[0],typ,ch+1,f"{a}" if k in (0xc0,0xd0) else f"{a}, {b}"))
            elif e[1]=="meta": self.events.insert("","end",values=(e[0],f"Meta {e[2]:02X}","—",e[3][:32].hex(" ")))
    def apply_volume(self):
        if not self.data:return
        track=self.data.tracks[self.current_track]; channels={e[2] for e in track if e[1]=="channel"}
        if not channels: messagebox.showinfo("אין ערוץ","ברצועה זו לא נמצאו אירועי ערוץ MIDI."); return
        value=int(float(self.volscale.get()))
        track[:]=[e for e in track if not(e[1]=="channel" and e[3]==0xb0 and e[4]==7)]
        for ch in channels: track.append([0,"channel",ch,0xb0,7,value])
        track.sort(key=lambda e:e[0]); self.show_track(self.current_track); self.status.configure(text=f"נוספה עוצמה {value} לרצועה {self.current_track+1}.")
    def apply_program(self):
        if not self.data:return
        track=self.data.tracks[self.current_track]; channels={e[2] for e in track if e[1]=="channel"}
        if not channels: messagebox.showinfo("אין ערוץ","ברצועה זו לא נמצאו אירועי ערוץ MIDI."); return
        value=max(0,min(127,int(self.program.get())))
        track[:]=[e for e in track if not(e[1]=="channel" and e[3]==0xc0)]
        for ch in channels: track.append([0,"channel",ch,0xc0,value,0])
        track.sort(key=lambda e:e[0]); self.show_track(self.current_track); self.status.configure(text=f"נבחר כלי MIDI מספר {value} לרצועה {self.current_track+1}.")
    def save_as(self):
        if not self.data:return
        p=filedialog.asksaveasfilename(title="שמירת מקצב",defaultextension=".sty",initialfile=(self.stylefile.stem+"_edited.sty" if self.stylefile else "style_edited.sty"),filetypes=[("Yamaha Style","*.sty"),("MIDI","*.mid"),("כל הקבצים","*.*")])
        if not p:return
        try: Path(p).write_bytes(self.data.encode())
        except Exception as e: messagebox.showerror("שגיאה בשמירה",str(e)); return
        self.status.configure(text=f"נשמר: {p}"); messagebox.showinfo("נשמר","הקובץ נשמר. בדוק אותו בכלי Yamaha.")

if __name__=="__main__": App().mainloop()
