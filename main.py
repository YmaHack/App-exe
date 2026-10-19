import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
import struct, json, base64, os, shutil

APP_TITLE = "Yamaha Style Studio"
VERSION = "0.2.0"

def vlq(n):
    n=max(0,int(n)); buf=[n&127]; n >>= 7
    while n: buf.insert(0,(n&127)|128); n >>= 7
    return bytes(buf)

def read_vlq(data,pos):
    value=0
    for _ in range(4):
        if pos>=len(data): raise ValueError("אירוע MIDI קטוע")
        b=data[pos]; pos+=1; value=(value<<7)|(b&127)
        if not b&128: return value,pos
    raise ValueError("ערך MIDI לא תקין")

class MidiStyle:
    """SMF parser. Unknown non-track chunks are preserved byte-for-byte."""
    def __init__(self,raw):
        self.header=None; self.chunks=[]; self.tracks=[]; pos=0
        while pos+8<=len(raw):
            tag=raw[pos:pos+4]; size=struct.unpack(">I",raw[pos+4:pos+8])[0]; end=pos+8+size
            if end>len(raw): raise ValueError("קובץ פגום: אורך מקטע חורג מהקובץ")
            payload=raw[pos+8:end]
            if tag==b"MThd": self.header=payload
            elif tag==b"MTrk":
                self.tracks.append(self._parse_track(payload)); self.chunks.append(("track",len(self.tracks)-1))
            else: self.chunks.append(("raw",tag+struct.pack(">I",size)+payload))
            pos=end
        if pos != len(raw): raise ValueError("מבנה הקובץ אינו תקין")
        if self.header is None or not self.tracks: raise ValueError("הקובץ אינו בפורמט MIDI/SMF נתמך. חלק מקובצי Yamaha STY משתמשים במבנה אחר.")
        if len(self.header)<6: raise ValueError("כותרת MIDI לא תקינה")
    @staticmethod
    def _parse_track(data):
        events=[]; pos=0; tick=0; running=None
        while pos<len(data):
            delta,pos=read_vlq(data,pos); tick+=delta
            if pos>=len(data): break
            status=data[pos]
            if status&128:
                pos+=1
                if status<240: running=status
            else:
                if running is None: raise ValueError("אירוע MIDI לא תקין")
                status=running
            if status==255:
                if pos>=len(data): break
                typ=data[pos]; pos+=1; size,pos=read_vlq(data,pos); payload=data[pos:pos+size]; pos+=size
                if len(payload)!=size: raise ValueError("אירוע Meta קטוע")
                events.append([tick,"meta",typ,payload])
                if typ==47: break
            elif status in (240,247):
                size,pos=read_vlq(data,pos); payload=data[pos:pos+size]; pos+=size
                if len(payload)!=size: raise ValueError("אירוע SysEx קטוע")
                events.append([tick,"sysex",status,payload])
            else:
                kind=status&240; ch=status&15; n=1 if kind in (192,208) else 2
                if pos+n>len(data): raise ValueError("אירוע ערוץ MIDI קטוע")
                a=data[pos]; b=data[pos+1] if n==2 else 0; pos+=n
                events.append([tick,"channel",ch,kind,a,b])
        return events
    @staticmethod
    def _encode_track(events):
        out=bytearray(); last=0
        for e in sorted(events,key=lambda x:x[0]):
            tick=max(last,int(e[0])); out+=vlq(tick-last); last=tick
            if e[1]=="meta": out+=bytes([255,e[2]])+vlq(len(e[3]))+e[3]
            elif e[1]=="sysex": out+=bytes([e[2]])+vlq(len(e[3]))+e[3]
            else:
                _,_,ch,kind,a,b=e; out+=bytes([kind|ch,a])
                if kind not in (192,208): out+=bytes([b])
        if not any(e[1]=="meta" and e[2]==47 for e in events): out+=b"\x00\xff\x2f\x00"
        return b"MTrk"+struct.pack(">I",len(out))+out
    def encode(self):
        h=bytearray(self.header); h[2:4]=struct.pack(">H",len(self.tracks))
        out=bytearray(b"MThd"+struct.pack(">I",len(h))+h)
        for kind,val in self.chunks: out+=self._encode_track(self.tracks[val]) if kind=="track" else val
        return bytes(out)
    def track_name(self,i):
        for e in self.tracks[i]:
            if e[1]=="meta" and e[2]==3:
                return e[3].decode("utf-8",errors="replace") or f"רצועה {i+1}"
        return f"רצועה {i+1}"

KIND_NAMES={128:"Note Off",144:"Note On",160:"Poly Aftertouch",176:"Control Change",192:"Program Change",208:"Channel Pressure",224:"Pitch Bend"}
def clamp(v,lo,hi): return max(lo,min(hi,int(v)))

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("Yamaha Style Studio"); self.geometry("1280x820"); self.minsize(980,660)
        self.configure(bg="#111827"); self.stylefile=None; self.data=None; self.current_track=0; self.dirty=False; self.project_path=None
        self._style(); self._ui(); self._setup_drop()
    def _style(self):
        s=ttk.Style(self); s.theme_use("clam")
        s.configure(".",font=("Segoe UI",10),background="#111827",foreground="#e5e7eb")
        s.configure("TFrame",background="#111827"); s.configure("Card.TFrame",background="#1f2937")
        s.configure("TLabel",background="#111827",foreground="#e5e7eb")
        s.configure("Muted.TLabel",background="#111827",foreground="#9ca3af")
        s.configure("Title.TLabel",font=("Segoe UI",22,"bold"),foreground="#f9fafb")
        s.configure("Section.TLabel",font=("Segoe UI",12,"bold"),foreground="#f9fafb")
        s.configure("TButton",padding=(12,8),background="#374151",foreground="#f9fafb",borderwidth=0)
        s.map("TButton",background=[("active","#4b5563")])
        s.configure("Accent.TButton",background="#2563eb",foreground="white")
        s.map("Accent.TButton",background=[("active","#1d4ed8")])
        s.configure("Treeview",background="#111827",fieldbackground="#111827",foreground="#e5e7eb",rowheight=27,borderwidth=0)
        s.configure("Treeview.Heading",background="#374151",foreground="#f9fafb",padding=7)
        s.map("Treeview",background=[("selected","#1d4ed8")],foreground=[("selected","white")])
        s.configure("TNotebook",background="#111827",borderwidth=0); s.configure("TNotebook.Tab",background="#374151",foreground="#e5e7eb",padding=(15,9))
        s.map("TNotebook.Tab",background=[("selected","#2563eb")],foreground=[("selected","white")])
        s.configure("TScale",background="#1f2937",troughcolor="#374151")
        s.configure("TSpinbox",fieldbackground="#111827",foreground="#e5e7eb")
    def _ui(self):
        header=ttk.Frame(self,padding=(20,16)); header.pack(fill="x")
        ttk.Label(header,text="♫",font=("Segoe UI",27,"bold"),foreground="#60a5fa").pack(side="left",padx=(0,12))
        titlebox=ttk.Frame(header); titlebox.pack(side="left")
        ttk.Label(titlebox,text="Yamaha Style Studio",style="Title.TLabel").pack(anchor="w")
        ttk.Label(titlebox,text="סביבת עבודה למקצבים ולעריכת MIDI",style="Muted.TLabel").pack(anchor="w")
        self.filelabel=ttk.Label(header,text="לא נבחר קובץ",style="Muted.TLabel"); self.filelabel.pack(side="right",padx=8)
        bar=ttk.Frame(self,padding=(20,0,20,14)); bar.pack(fill="x")
        ttk.Button(bar,text="＋  פתיחת קובץ",style="Accent.TButton",command=self.open_file).pack(side="left")
        ttk.Button(bar,text="📁  פרויקט חדש / שמירת פרויקט",command=self.save_project).pack(side="left",padx=7)
        ttk.Button(bar,text="פתיחת פרויקט",command=self.open_project).pack(side="left")
        ttk.Button(bar,text="ייצוא STY / MIDI",command=self.save_as).pack(side="left",padx=7)
        self.status=ttk.Label(self,text="גרור לכאן קובץ STY או MIDI, או לחץ על פתיחת קובץ.",padding=(18,10),style="Muted.TLabel"); self.status.pack(side="bottom",fill="x")
        self.dropzone=ttk.Frame(self,style="Card.TFrame",padding=10); self.dropzone.pack(fill="x",padx=20,pady=(0,12))
        ttk.Label(self.dropzone,text="⬇  גרור קובץ ‎.STY / .MID לכאן",font=("Segoe UI",11,"bold"),background="#1f2937",foreground="#93c5fd").pack()
        nb=ttk.Notebook(self); nb.pack(fill="both",expand=True,padx=20,pady=(0,16))
        self.mix_tab=ttk.Frame(nb,padding=14); self.edit_tab=ttk.Frame(nb,padding=14); self.project_tab=ttk.Frame(nb,padding=14)
        nb.add(self.mix_tab,text="מיקסר ערוצים"); nb.add(self.edit_tab,text="עורך MIDI"); nb.add(self.project_tab,text="פרויקט וסיוע חכם")
        self._build_mixer(); self._build_editor(); self._build_project()
    def _setup_drop(self):
        try:
            from tkinterdnd2 import DND_FILES
            self.dropzone.drop_target_register(DND_FILES); self.dropzone.dnd_bind("<<Drop>>",self._drop)
            self.dropzone.winfo_children()[0].drop_target_register(DND_FILES); self.dropzone.winfo_children()[0].dnd_bind("<<Drop>>",self._drop)
        except Exception: pass
    def _drop(self,event):
        paths=self.tk.splitlist(event.data)
        if paths: self.load_path(paths[0])
    def open_file(self):
        p=filedialog.askopenfilename(filetypes=[("Yamaha STY / MIDI","*.sty *.mid *.midi"),("All files","*.*")])
        if p:self.load_path(p)
    def load_path(self,p):
        try:
            path=Path(p)
            if path.suffix.lower()==".ysproj": self._load_project_file(path); return
            data=MidiStyle(path.read_bytes())
        except Exception as e:
            messagebox.showerror("לא ניתן לפתוח",str(e)); return
        self.data=data; self.stylefile=Path(p); self.project_path=None; self.dirty=False
        self.filelabel.configure(text=self.stylefile.name); self._refresh_all()
        self.status.configure(text=f"נטענו {len(data.tracks)} רצועות MIDI • ניתן לערוך ולייצא עותק.")
    def _build_mixer(self):
        top=ttk.Frame(self.mix_tab); top.pack(fill="x")
        ttk.Label(top,text="מיקסר ערוצים",style="Section.TLabel").pack(side="left")
        ttk.Label(top,text="CC7 • 0–127",style="Muted.TLabel").pack(side="left",padx=12)
        ttk.Button(top,text="הנמך את כל הערוצים…",style="Accent.TButton",command=self.lower_all).pack(side="right")
        ttk.Button(top,text="רענן מיקסר",command=self.refresh_mixer).pack(side="right",padx=7)
        self.mixer_canvas=tk.Canvas(self.mix_tab,bg="#111827",highlightthickness=0,height=430)
        self.mixer_canvas.pack(fill="both",expand=True,pady=12)
        self.mixer_inner=ttk.Frame(self.mixer_canvas); self.mixer_window=self.mixer_canvas.create_window((0,0),window=self.mixer_inner,anchor="nw")
        self.mixer_inner.bind("<Configure>",lambda e:self.mixer_canvas.configure(scrollregion=self.mixer_canvas.bbox("all")))
        self.mixer_canvas.bind("<Configure>",lambda e:self.mixer_canvas.itemconfigure(self.mixer_window,width=e.width))
        ttk.Label(self.mix_tab,text="הערה: העוצמות נכתבות כאירועי MIDI CC7 בתחילת המקצב. תוצאתן בפועל תלויה בדגם Yamaha ובנתוני המקצב.",style="Muted.TLabel",wraplength=1000).pack(anchor="w")
    def _build_editor(self):
        head=ttk.Frame(self.edit_tab); head.pack(fill="x")
        ttk.Label(head,text="עריכת אירועי MIDI",style="Section.TLabel").pack(side="left")
        ttk.Label(head,text="בחר אירוע ולחץ עריכה כדי לשנות זמן, ערוץ ונתונים.",style="Muted.TLabel").pack(side="left",padx=10)
        self.track_var=tk.StringVar()
        self.track_combo=ttk.Combobox(head,textvariable=self.track_var,state="readonly",width=32); self.track_combo.pack(side="right")
        self.track_combo.bind("<<ComboboxSelected>>",self._track_changed)
        cols=("tick","kind","channel","a","b","details")
        self.event_tree=ttk.Treeview(self.edit_tab,columns=cols,show="headings")
        for c,t,w in [("tick","זמן (ticks)",100),("kind","אירוע",160),("channel","ערוץ",80),("a","נתון A",100),("b","נתון B",100),("details","פירוט",360)]:
            self.event_tree.heading(c,text=t); self.event_tree.column(c,width=w,anchor="w")
        self.event_tree.pack(fill="both",expand=True,pady=12)
        buttons=ttk.Frame(self.edit_tab); buttons.pack(fill="x")
        ttk.Button(buttons,text="עריכת אירוע נבחר",style="Accent.TButton",command=self.edit_event).pack(side="left")
        ttk.Button(buttons,text="מחיקת אירוע נבחר",command=self.delete_event).pack(side="left",padx=7)
        ttk.Button(buttons,text="הוסף אירוע MIDI",command=self.add_event).pack(side="left")
        ttk.Label(buttons,text="עריכת אירועי Note On/Off, בקרה, כלי נגינה ונתוני Meta.",style="Muted.TLabel").pack(side="right")
    def _build_project(self):
        ttk.Label(self.project_tab,text="פרויקטים מסודרים",style="Section.TLabel").pack(anchor="w")
        ttk.Label(self.project_tab,text="שמור פרויקט בתיקייה ייעודית: קובץ ‎.ysproj‎ כולל את מצב העבודה והאירועים. ניתן לפתוח אותו בהמשך ולהמשיך לערוך.",wraplength=900).pack(anchor="w",pady=(7,18))
        row=ttk.Frame(self.project_tab); row.pack(fill="x")
        ttk.Button(row,text="📁  שמירת פרויקט בתיקייה…",style="Accent.TButton",command=self.save_project).pack(side="left")
        ttk.Button(row,text="פתיחת פרויקט…",command=self.open_project).pack(side="left",padx=8)
        ttk.Separator(self.project_tab).pack(fill="x",pady=20)
        ttk.Label(self.project_tab,text="Smart Mix — סיוע חכם מקומי",style="Section.TLabel").pack(anchor="w")
        ttk.Label(self.project_tab,text="מנתח את הערוצים והעוצמות ומציע איזון ראשוני לפי סוג הערוץ והעוצמה הקיימת. זהו מנוע המלצות מקומי מבוסס כללים, לא מודל AI מקוון; אפשר לבדוק את ההצעות לפני החלתן.",wraplength=900).pack(anchor="w",pady=8)
        ttk.Button(self.project_tab,text="✨ נתח והצע איזון",style="Accent.TButton",command=self.smart_mix).pack(anchor="w",pady=5)
        self.ai_text=tk.Text(self.project_tab,height=12,bg="#111827",fg="#d1d5db",insertbackground="white",relief="flat",font=("Segoe UI",10),wrap="word")
        self.ai_text.pack(fill="both",expand=True,pady=10); self.ai_text.insert("1.0","פתח קובץ כדי לנתח את המיקס.")
    def _refresh_all(self):
        self.refresh_mixer(); self.refresh_editor()
    def _channels(self):
        result={}
        if not self.data:return result
        for ti,tr in enumerate(self.data.tracks):
            for e in tr:
                if e[1]=="channel":
                    ch=e[2]; result.setdefault(ch,{"tracks":set(),"volume":None,"program":None})
                    result[ch]["tracks"].add(ti)
                    if e[3]==176 and e[4]==7 and result[ch]["volume"] is None: result[ch]["volume"]=e[5]
                    if e[3]==192 and result[ch]["program"] is None: result[ch]["program"]=e[4]
        for ch,v in result.items():
            if v["volume"] is None:v["volume"]=100
        return result
    def refresh_mixer(self):
        for w in self.mixer_inner.winfo_children(): w.destroy()
        if not self.data:
            ttk.Label(self.mixer_inner,text="פתח קובץ כדי להציג את הערוצים.",style="Muted.TLabel").grid(row=0,column=0,padx=20,pady=20); return
        chans=self._channels()
        for col,ch in enumerate(sorted(chans)):
            info=chans[ch]; card=ttk.Frame(self.mixer_inner,style="Card.TFrame",padding=9); card.grid(row=0,column=col,padx=5,pady=5,sticky="ns")
            name="תופים" if ch==9 else f"ערוץ {ch+1}"
            ttk.Label(card,text=name,font=("Segoe UI",10,"bold"),background="#1f2937").pack(pady=(4,2))
            ttk.Label(card,text=f"{info['volume']}/127",background="#1f2937",foreground="#93c5fd").pack()
            var=tk.IntVar(value=info["volume"]); scale=ttk.Scale(card,from_=0,to=127,orient="vertical",length=220,command=lambda val,c=ch,v=var:self._mixer_preview(c,v,val))
            scale.set(info["volume"]); scale.pack(padx=8,pady=8)
            ttk.Label(card,text=f"CH {ch+1:02d}",background="#1f2937",foreground="#9ca3af").pack()
            ttk.Button(card,text="החל",command=lambda c=ch,v=var:self.set_channel_volume(c,v.get())).pack(fill="x",pady=(8,2))
            ttk.Button(card,text="איפוס 100",command=lambda c=ch:self.set_channel_volume(c,100)).pack(fill="x")
    def _mixer_preview(self,ch,var,val):
        var.set(int(float(val)))
    def set_channel_volume(self,ch,value):
        if not self.data:return
        self._set_cc(ch,7,clamp(value,0,127)); self.dirty=True; self.refresh_mixer(); self.refresh_editor()
        self.status.configure(text=f"עוצמת ערוץ {ch+1} הוגדרה ל־{int(value)}.")
    def _set_cc(self,ch,cc,value):
        target=None
        for tr in self.data.tracks:
            if any(e[1]=="channel" and e[2]==ch for e in tr): target=tr; break
        if target is None:
            target=self.data.tracks[0]
        for tr in self.data.tracks:
            tr[:]=[e for e in tr if not(e[1]=="channel" and e[2]==ch and e[3]==176 and e[4]==cc)]
        target.append([0,"channel",ch,176,cc,clamp(value,0,127)]); target.sort(key=lambda e:e[0])
    def lower_all(self):
        if not self.data:return
        amount=simpledialog.askinteger("הנמכת כל הערוצים","בכמה להנמיך כל ערוץ? (ערך MIDI שיופחת מכל עוצמה קיימת)",initialvalue=15,minvalue=1,maxvalue=127,parent=self)
        if amount is None:return
        chans=self._channels()
        if not chans:return
        for ch,info in chans.items(): self._set_cc(ch,7,max(0,info["volume"]-amount))
        self.dirty=True; self._refresh_all(); self.status.configure(text=f"כל {len(chans)} הערוצים הונמכו ב־{amount} יחידות MIDI (מינימום 0).")
    def smart_mix(self):
        if not self.data:return
        chans=self._channels()
        if not chans: self.ai_text.delete("1.0","end"); self.ai_text.insert("1.0","לא נמצאו ערוצי MIDI."); return
        self.suggestions={}
        lines=["הצעת Smart Mix — בדוק לפני החלה:",""]
        for ch,info in sorted(chans.items()):
            cur=info["volume"]
            if ch==9: target=min(cur,100); role="תופים (ערוץ 10)"
            elif cur>115: target=105; role="עוצמה גבוהה"
            elif cur<45: target=min(75,cur+15); role="עוצמה נמוכה"
            else: target=cur; role="ללא שינוי מוצע"
            self.suggestions[ch]=target
            lines.append(f"ערוץ {ch+1:02d} | {role}: {cur} → {target}")
        lines += ["","ההצעה מבוססת כללים פשוטים בלבד ואינה מנתחת אודיו. לחץ על 'החל הצעות' כדי לכתוב את ערכי CC7."]
        self.ai_text.delete("1.0","end"); self.ai_text.insert("1.0","\n".join(lines))
        if hasattr(self,"apply_suggestions_btn"): self.apply_suggestions_btn.destroy()
        self.apply_suggestions_btn=ttk.Button(self.project_tab,text="החל הצעות",style="Accent.TButton",command=self.apply_suggestions)
        self.apply_suggestions_btn.pack(anchor="w",pady=5)
    def apply_suggestions(self):
        if not getattr(self,"suggestions",None):return
        if not messagebox.askyesno("אישור שינוי","להחיל את הצעות העוצמה על כל הערוצים? מומלץ לשמור עותק קודם."):return
        for ch,v in self.suggestions.items(): self._set_cc(ch,7,v)
        self.dirty=True; self._refresh_all(); self.status.configure(text="הצעות Smart Mix הוחלו. ייצא לקובץ חדש כדי לשמור.")
    def _track_changed(self,_=None):
        if not self.data:return
        idx=self.track_combo.current()
        if idx>=0:self.current_track=idx; self.refresh_editor()
    def refresh_editor(self):
        self.event_tree.delete(*self.event_tree.get_children())
        if not self.data:
            self.track_combo["values"]=[]; return
        names=[self.data.track_name(i) for i in range(len(self.data.tracks))]
        self.track_combo["values"]=names
        if self.current_track>=len(names):self.current_track=0
        self.track_combo.current(self.current_track)
        for ix,e in enumerate(self.data.tracks[self.current_track]):
            if e[1]=="channel":
                _,_,ch,k,a,b=e; detail=""
                if k in (128,144): detail=f"תו MIDI {a} • מהירות {b}"
                elif k==176: detail=f"CC {a} = {b}"
                elif k==192: detail=f"Program {a}"
                self.event_tree.insert("","end",iid=str(ix),values=(e[0],KIND_NAMES.get(k,f"MIDI {k:02X}"),ch+1,a,b,detail))
            elif e[1]=="meta":
                desc={3:"שם רצועה",81:"Tempo",88:"Time Signature",47:"End of Track"}.get(e[2],f"Meta {e[2]:02X}")
                self.event_tree.insert("","end",iid=str(ix),values=(e[0],desc,"—","", "",e[3][:28].hex(" ")))
            else:self.event_tree.insert("","end",iid=str(ix),values=(e[0],"SysEx","—","","",f"{len(e[3])} bytes"))
    def edit_event(self):
        if not self.data:return
        sel=self.event_tree.selection()
        if not sel:return
        idx=int(sel[0]); e=self.data.tracks[self.current_track][idx]
        win=tk.Toplevel(self); win.title("עריכת אירוע MIDI"); win.configure(bg="#111827"); win.resizable(False,False)
        frame=ttk.Frame(win,padding=18); frame.pack(fill="both",expand=True)
        fields={}
        def add(label,key,val):
            row=ttk.Frame(frame); row.pack(fill="x",pady=5); ttk.Label(row,text=label,width=18).pack(side="left")
            ent=ttk.Entry(row,width=24); ent.insert(0,str(val)); ent.pack(side="left"); fields[key]=ent
        add("זמן (ticks)","tick",e[0])
        if e[1]=="channel":
            add("ערוץ (1–16)","channel",e[2]+1); add("סוג (hex, למשל 90)","kind",f"{e[3]:02X}"); add("נתון A","a",e[4]); add("נתון B","b",e[5])
        elif e[1]=="meta":
            add("סוג Meta (hex)","meta",f"{e[2]:02X}"); add("נתונים (hex)","payload",e[3].hex())
        else:
            add("סטטוס SysEx (hex)","sysex",f"{e[2]:02X}"); add("נתונים (hex)","payload",e[3].hex())
        def save():
            try:
                tick=max(0,int(fields["tick"].get()))
                if e[1]=="channel":
                    ch=clamp(int(fields["channel"].get())-1,0,15); kind=int(fields["kind"].get(),16)
                    if kind not in (128,144,160,176,192,208,224): raise ValueError("סוג אירוע MIDI לא תקין")
                    a=clamp(int(fields["a"].get()),0,127); b=clamp(int(fields["b"].get()),0,127)
                    ne=[tick,"channel",ch,kind,a,b]
                else:
                    typ=int(fields["meta" if e[1]=="meta" else "sysex"].get(),16); payload=bytes.fromhex(fields["payload"].get())
                    ne=[tick,"meta",typ,payload] if e[1]=="meta" else [tick,"sysex",typ,payload]
                self.data.tracks[self.current_track][idx]=ne; self.data.tracks[self.current_track].sort(key=lambda x:x[0])
                self.dirty=True; self._refresh_all(); win.destroy(); self.status.configure(text="אירוע MIDI עודכן.")
            except Exception as ex:messagebox.showerror("נתונים לא תקינים",str(ex),parent=win)
        ttk.Button(frame,text="שמור שינוי",style="Accent.TButton",command=save).pack(anchor="e",pady=(12,0))
    def add_event(self):
        if not self.data:return
        kind=simpledialog.askstring("הוספת אירוע","סוג אירוע: note_on, note_off, control, program",initialvalue="note_on",parent=self)
        if not kind:return
        mapping={"note_on":144,"note_off":128,"control":176,"program":192}
        if kind.lower() not in mapping:messagebox.showerror("סוג לא מוכר","בחר note_on, note_off, control או program.");return
        ch=simpledialog.askinteger("ערוץ","ערוץ MIDI (1–16)",initialvalue=1,minvalue=1,maxvalue=16,parent=self)
        if ch is None:return
        tick=simpledialog.askinteger("זמן","זמן באירועי ticks",initialvalue=0,minvalue=0,parent=self)
        if tick is None:return
        a=simpledialog.askinteger("נתון A","תו / בקר / מספר כלי",initialvalue=60,minvalue=0,maxvalue=127,parent=self)
        if a is None:return
        b=0
        if mapping[kind.lower()] not in (192,208):
            b=simpledialog.askinteger("נתון B","מהירות / ערך בקר",initialvalue=90,minvalue=0,maxvalue=127,parent=self)
            if b is None:return
        self.data.tracks[self.current_track].append([tick,"channel",ch-1,mapping[kind.lower()],a,b]); self.data.tracks[self.current_track].sort(key=lambda x:x[0])
        self.dirty=True; self._refresh_all()
    def delete_event(self):
        if not self.data:return
        sel=self.event_tree.selection()
        if not sel:return
        if not messagebox.askyesno("מחיקת אירוע","למחוק את אירוע ה־MIDI שנבחר?"):return
        del self.data.tracks[self.current_track][int(sel[0])]; self.dirty=True; self._refresh_all()
    def save_as(self):
        if not self.data:return
        p=filedialog.asksaveasfilename(title="ייצוא מקצב",defaultextension=".sty",initialfile=(self.stylefile.stem+"_edited.sty" if self.stylefile else "style_edited.sty"),filetypes=[("Yamaha Style","*.sty"),("MIDI","*.mid"),("All files","*.*")])
        if not p:return
        try:Path(p).write_bytes(self.data.encode())
        except Exception as e:messagebox.showerror("שגיאה בשמירה",str(e));return
        self.status.configure(text=f"הקובץ יוצא אל: {p}"); messagebox.showinfo("הייצוא הושלם","נשמר עותק חדש. בדוק אותו במקלדת/כלי Yamaha לפני שימוש בהופעה.")
    def save_project(self):
        if not self.data:return
        folder=filedialog.askdirectory(title="בחר או צור תיקיית פרויקט")
        if not folder:return
        root=Path(folder)
        name=(self.stylefile.stem if self.stylefile else "Yamaha_Project")
        project_dir=root/name
        try:
            project_dir.mkdir(parents=True,exist_ok=True)
            proj={"format":"YamahaStyleStudioProject","version":1,"source_name":self.stylefile.name if self.stylefile else "untitled.sty","data":base64.b64encode(self.data.encode()).decode("ascii")}
            target=project_dir/(name+".ysproj"); target.write_text(json.dumps(proj,ensure_ascii=False,indent=2),encoding="utf-8")
            (project_dir/"README.txt").write_text("Yamaha Style Studio project folder\nOpen the .ysproj file in the application to continue editing.\nExported files can be stored in this folder.\n",encoding="utf-8")
            self.project_path=target; self.status.configure(text=f"הפרויקט נשמר בתיקייה: {project_dir}")
            messagebox.showinfo("הפרויקט נשמר",f"נוצרה תיקיית עבודה מסודרת:\n{project_dir}\n\nפתח את קובץ ה־.ysproj כדי להמשיך בעתיד.")
        except Exception as e:messagebox.showerror("שגיאה בשמירת פרויקט",str(e))
    def open_project(self):
        p=filedialog.askopenfilename(title="פתיחת פרויקט",filetypes=[("Yamaha project","*.ysproj"),("All files","*.*")])
        if p:self._load_project_file(Path(p))
    def _load_project_file(self,path):
        try:
            obj=json.loads(path.read_text(encoding="utf-8"))
            if obj.get("format")!="YamahaStyleStudioProject":raise ValueError("קובץ פרויקט לא מוכר")
            self.data=MidiStyle(base64.b64decode(obj["data"])); self.stylefile=Path(obj.get("source_name","project.sty")); self.project_path=path; self.dirty=False
            self.filelabel.configure(text=path.name); self._refresh_all(); self.status.configure(text=f"נפתח פרויקט: {path}")
        except Exception as e:messagebox.showerror("שגיאה בפתיחת פרויקט",str(e))
if __name__=="__main__":
    try:
        from tkinterdnd2 import TkinterDnD
        class StudioApp(App, TkinterDnD.Tk):
            def __init__(self):
                TkinterDnD.Tk.__init__(self)
                self.title("Yamaha Style Studio"); self.geometry("1280x820"); self.minsize(980,660)
                self.configure(bg="#111827"); self.stylefile=None; self.data=None; self.current_track=0; self.dirty=False; self.project_path=None
                self._style(); self._ui(); self._setup_drop()
        StudioApp().mainloop()
    except ImportError:
        App().mainloop()
