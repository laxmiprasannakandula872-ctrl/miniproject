
import argparse
import csv
import json
import logging
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from uuid import uuid4
from collections import Counter

# ================ VALIDATION ================

import re

CATEGORIES = ["Personal", "Family", "Friend", "Work", "College", "Other"]
STATUSES = ["Active", "Inactive"]

def validate_contact(values):
    name = str(values.get("name", "")).strip()
    phone = re.sub(r"[\s().-]", "", str(values.get("phone", "")).strip())
    email = str(values.get("email", "")).strip().lower()
    company = str(values.get("company", "")).strip()
    category = str(values.get("category", "Personal")).strip()
    city = str(values.get("city", "")).strip()
    address = str(values.get("address", "")).strip()
    notes = str(values.get("notes", "")).strip()
    status = str(values.get("status", "Active")).strip()

    if not name or len(name) > 80 or not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", name):
        raise ValueError("Name is required (letters, spaces, dots, apostrophes and hyphens only; max 80).")
    if not re.fullmatch(r"\+?\d{7,15}", phone):
        raise ValueError("Phone must contain 7–15 digits, optionally starting with +.")
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email):
        raise ValueError("Enter a valid email address.")
    if category not in CATEGORIES:
        raise ValueError("Choose a valid category.")
    if status not in STATUSES:
        raise ValueError("Choose Active or Inactive.")
    if len(company) > 100 or len(city) > 80 or len(address) > 250 or len(notes) > 1000:
        raise ValueError("One or more fields exceed the allowed length.")
    return dict(name=name, phone=phone, email=email, company=company, category=category,
                city=city, address=address, notes=notes, status=status)



# ================ CONTACT MODEL AND MANAGER ================

@dataclass
class Contact:
    id: str
    name: str
    phone: str
    email: str
    company: str = ""
    category: str = "Personal"
    city: str = ""
    address: str = ""
    notes: str = ""
    status: str = "Active"
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, **values):
        now = datetime.now().isoformat(timespec="seconds")
        return cls(id=str(uuid4())[:8].upper(), created_at=now, updated_at=now, **values)

class ContactManager:
    def __init__(self, contacts=None):
        self.contacts = contacts or []

    def add(self, values):
        clean = validate_contact(values)
        if any(c.email.lower() == clean["email"].lower() for c in self.contacts):
            raise ValueError("A contact with this email already exists.")
        if any(c.phone == clean["phone"] for c in self.contacts):
            raise ValueError("A contact with this phone number already exists.")
        contact = Contact.create(**clean)
        self.contacts.append(contact)
        return contact

    def update(self, contact_id, values):
        current = self.get(contact_id)
        clean = validate_contact(values)
        for c in self.contacts:
            if c.id != contact_id and (c.email.lower() == clean["email"].lower() or c.phone == clean["phone"]):
                raise ValueError("Another contact already uses this email or phone.")
        for key, value in clean.items():
            setattr(current, key, value)
        current.updated_at = datetime.now().isoformat(timespec="seconds")
        return current

    def delete(self, contact_id):
        contact = self.get(contact_id)
        self.contacts.remove(contact)
        return contact

    def get(self, contact_id):
        for contact in self.contacts:
            if contact.id == contact_id:
                return contact
        raise ValueError("Contact ID not found.")

    def search(self, keyword="", category="All", status="All"):
        keyword = keyword.strip().lower()
        result = []
        for c in self.contacts:
            fields = [c.name, c.phone, c.email, c.company, c.city, c.address, c.notes, c.id]
            matches = not keyword or any(keyword in str(x).lower() for x in fields)
            category_ok = category == "All" or c.category == category
            status_ok = status == "All" or c.status == status
            if matches and category_ok and status_ok:
                result.append(c)
        return sorted(result, key=lambda x: x.name.lower())

    def as_dicts(self):
        return [asdict(c) for c in self.contacts]



# ================ LOCAL JSON / CSV STORAGE ================

FIELDS = ["id","name","phone","email","company","category","city","address","notes","status","created_at","updated_at"]

class Storage:
    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.json_path = self.data_dir / "contacts.json"
        self.csv_path = self.data_dir / "contacts.csv"

    def load(self, fmt="json"):
        path = self.json_path if fmt.lower() == "json" else self.csv_path
        if not path.exists():
            self.save([], fmt)
            return []
        try:
            if fmt.lower() == "json":
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, list):
                    raise ValueError("JSON root must be a list.")
            else:
                with path.open(newline="", encoding="utf-8-sig") as f:
                    raw = list(csv.DictReader(f))
            contacts = []
            for row in raw:
                if not isinstance(row, dict) or not all(k in row for k in ("id","name","phone","email")):
                    continue
                row = {k: str(row.get(k, "") or "") for k in FIELDS}
                row["category"] = row["category"] or "Personal"
                row["status"] = row["status"] or "Active"
                contacts.append(Contact(**row))
            return contacts
        except (json.JSONDecodeError, OSError, csv.Error, ValueError) as exc:
            backup = path.with_suffix(path.suffix + ".corrupt")
            try:
                path.replace(backup)
            except OSError:
                pass
            print(f"[WARNING] Could not read {path}: {exc}. Starting with an empty dataset.")
            self.save([], fmt)
            return []

    def save(self, contacts, fmt="json"):
        rows = [asdict(c) if hasattr(c, "__dataclass_fields__") else dict(c) for c in contacts]
        path = self.json_path if fmt.lower() == "json" else self.csv_path
        temp = path.with_suffix(path.suffix + ".tmp")
        if fmt.lower() == "json":
            temp.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            with temp.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
        temp.replace(path)

    def import_csv(self, filepath):
        imported, errors = [], []
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for line, row in enumerate(reader, start=2):
                try:
                    clean = validate_contact(row)
                    imported.append(clean)
                except Exception as exc:
                    errors.append(f"Row {line}: {exc}")
        return imported, errors



# ================ ANALYTICS AND REPORT EXPORTS ================

from pathlib import Path

def build_summary(contacts):
    total = len(contacts)
    active = sum(c.status == "Active" for c in contacts)
    inactive = total - active
    by_category = Counter(c.category for c in contacts)
    by_city = Counter(c.city or "Not specified" for c in contacts)
    by_company = Counter(c.company or "Not specified" for c in contacts)
    incomplete = sum(not (c.company and c.city) for c in contacts)
    duplicates = total - len({c.email.lower() for c in contacts})
    dates = []
    for c in contacts:
        try: dates.append(datetime.fromisoformat(c.created_at).date())
        except (ValueError, TypeError): pass
    recent = sum(d >= datetime.now().date() - timedelta(days=30) for d in dates)
    return {
        "total": total, "active": active, "inactive": inactive,
        "average_per_category": round(total / max(len(by_category), 1), 2),
        "by_category": by_category, "by_city": by_city, "by_company": by_company,
        "incomplete": incomplete, "duplicates": duplicates, "new_last_30_days": recent
    }

def export_markdown(summary, path):
    lines = ["# CONTACTLY Contact Book Report", "", f"Generated: {datetime.now():%Y-%m-%d %H:%M}", "",
             "## Overview", "", f"- Total contacts: {summary['total']}",
             f"- Active: {summary['active']}", f"- Inactive: {summary['inactive']}",
             f"- New in last 30 days: {summary['new_last_30_days']}",
             f"- Incomplete records: {summary['incomplete']}",
             f"- Duplicate emails: {summary['duplicates']}",
             f"- Average contacts per category: {summary['average_per_category']}", "",
             "## Contacts by category", ""]
    lines += [f"- {k}: {v}" for k, v in summary["by_category"].most_common()]
    Path(path).write_text("\n".join(lines), encoding="utf-8")

def export_text(summary, path):
    lines = ["CONTACTLY AUDIT SUMMARY", "=" * 28, f"Generated: {datetime.now():%Y-%m-%d %H:%M}",
             f"Total: {summary['total']}", f"Active: {summary['active']}",
             f"Inactive: {summary['inactive']}", f"Incomplete: {summary['incomplete']}",
             f"Duplicate emails: {summary['duplicates']}", "", "CATEGORY BREAKDOWN:"]
    lines += [f"{k}: {v}" for k, v in summary["by_category"].most_common()]
    Path(path).write_text("\n".join(lines), encoding="utf-8")

def export_summary_csv(summary, path):
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["Metric", "Value"])
        for key in ["total","active","inactive","new_last_30_days","incomplete","duplicates","average_per_category"]:
            w.writerow([key, summary[key]])
        for category, count in summary["by_category"].items():
            w.writerow([f"category:{category}", count])



# ================ CSV CONTACT EXPORT ================

def export_contacts(contacts, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for c in contacts:
            w.writerow(asdict(c))



# ================ ACTIVITY LOGGING ================

Path("reports").mkdir(exist_ok=True)
logging.basicConfig(filename="reports/activity.log", level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("CONTACTLY")



# ================ DESKTOP GUI ================

import tkinter as tk

BG = "#F5F6FB"; NAVY = "#202A44"; INDIGO = "#5965D8"; MUTED = "#68738A"

class ContactlyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CONTACTLY | Smart Contact Management")
        self.root.geometry("1180x740")
        self.root.minsize(960, 620)
        self.root.configure(bg=BG)
        self.store = Storage()
        self.format = tk.StringVar(value="json")
        self.manager = ContactManager(self.store.load("json"))
        self._add_sample_contacts_if_empty()
        self.selected_id = None
        self._style()
        self._layout()
        self.show_dashboard()

    def _add_sample_contacts_if_empty(self):
        """Add 30 fictional demo contacts only when the contact book is empty."""
        if self.manager.contacts:
            return

        sample_contacts = [
            ("Aarav Sharma", "9000000001", "aarav.sharma@example.com", "Bright Solutions", "Work", "Hyderabad"),
            ("Aditi Rao", "9000000002", "aditi.rao@example.com", "Green Valley College", "College", "Medchal"),
            ("Arjun Reddy", "9000000003", "arjun.reddy@example.com", "Personal", "Friend", "Secunderabad"),
            ("Ananya Kumar", "9000000004", "ananya.kumar@example.com", "Sunrise Technologies", "Work", "Hyderabad"),
            ("Bhavya Patel", "9000000005", "bhavya.patel@example.com", "Family", "Family", "Kompally"),
            ("Charan Teja", "9000000006", "charan.teja@example.com", "North Star College", "College", "Medchal"),
            ("Diya Singh", "9000000007", "diya.singh@example.com", "Personal", "Friend", "Hyderabad"),
            ("Devika Nair", "9000000008", "devika.nair@example.com", "Blue Sky Ltd", "Work", "Miyapur"),
            ("Eshan Verma", "9000000009", "eshan.verma@example.com", "Family", "Family", "Alwal"),
            ("Farhan Ali", "9000000010", "farhan.ali@example.com", "City Engineering College", "College", "Hyderabad"),
            ("Gauri Mehta", "9000000011", "gauri.mehta@example.com", "Personal", "Personal", "Medchal"),
            ("Harish Kumar", "9000000012", "harish.kumar@example.com", "Vertex Systems", "Work", "Secunderabad"),
            ("Ishita Das", "9000000013", "ishita.das@example.com", "Family", "Family", "Kompally"),
            ("Jai Prakash", "9000000014", "jai.prakash@example.com", "Metro College", "College", "Hyderabad"),
            ("Kavya Rani", "9000000015", "kavya.rani@example.com", "Personal", "Friend", "Alwal"),
            ("Kiran Kumar", "9000000016", "kiran.kumar@example.com", "Nova Technologies", "Work", "Miyapur"),
            ("Lakshmi Devi", "9000000017", "lakshmi.devi@example.com", "Family", "Family", "Medchal"),
            ("Manoj Kumar", "9000000018", "manoj.kumar@example.com", "City Degree College", "College", "Hyderabad"),
            ("Meera Shah", "9000000019", "meera.shah@example.com", "Personal", "Personal", "Secunderabad"),
            ("Nikhil Rao", "9000000020", "nikhil.rao@example.com", "Apex Solutions", "Work", "Kompally"),
            ("Pooja Reddy", "9000000021", "pooja.reddy@example.com", "Family", "Family", "Alwal"),
            ("Pranav Joshi", "9000000022", "pranav.joshi@example.com", "Westside College", "College", "Medchal"),
            ("Rahul Varma", "9000000023", "rahul.varma@example.com", "Personal", "Friend", "Hyderabad"),
            ("Sahana Iyer", "9000000024", "sahana.iyer@example.com", "Orbit Technologies", "Work", "Miyapur"),
            ("Sai Krishna", "9000000025", "sai.krishna@example.com", "Family", "Family", "Secunderabad"),
            ("Sneha Gupta", "9000000026", "sneha.gupta@example.com", "Central College", "College", "Kompally"),
            ("Tanvi Rao", "9000000027", "tanvi.rao@example.com", "Personal", "Personal", "Medchal"),
            ("Uday Kumar", "9000000028", "uday.kumar@example.com", "Pioneer Systems", "Work", "Hyderabad"),
            ("Varun Das", "9000000029", "varun.das@example.com", "Family", "Family", "Alwal"),
            ("Zoya Khan", "9000000030", "zoya.khan@example.com", "Personal", "Friend", "Secunderabad"),
        ]

        for name, phone, email, company, category, city in sample_contacts:
            self.manager.add({
                "name": name,
                "phone": phone,
                "email": email,
                "company": company,
                "category": category,
                "city": city,
                "address": "",
                "notes": "Sample demo contact",
                "status": "Active",
            })

        self.persist()
        logger.info("Added 30 sample demo contacts")

    def _style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="white", fieldbackground="white",
                        foreground=NAVY, rowheight=34, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#E9ECF8", foreground=NAVY,
                        font=("Segoe UI", 10, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", "#DDE2FF")], foreground=[("selected", NAVY)])
        style.configure("TCombobox", padding=7)

    def _layout(self):
        self.sidebar = tk.Frame(self.root, bg=NAVY, width=220)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text="✦ CONTACTLY", bg=NAVY, fg="white",
                 font=("Segoe UI", 19, "bold")).pack(anchor="w", padx=22, pady=(28, 4))
        tk.Label(self.sidebar, text="SMART CONTACT BOOK", bg=NAVY, fg="#AEB8D0",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=24, pady=(0, 30))
        for label, command in [
            ("▦   Dashboard", self.show_dashboard), ("♙   All Contacts", self.show_contacts),
            ("＋   Add Contact", self.add_contact), ("⌕   Search & Filter", self.search_contacts),
            ("◷   Analytics", self.show_analytics), ("⇅   Import / Export", self.import_export),
            ("⚙   Settings", self.settings)]:
            tk.Button(self.sidebar, text=label, command=command, anchor="w", relief="flat",
                      bg=NAVY, fg="#E7EAF4", activebackground="#354366",
                      activeforeground="white", font=("Segoe UI", 10), padx=22, pady=13,
                      cursor="hand2").pack(fill="x")
        tk.Label(self.sidebar, text="OFFLINE • LOCAL STORAGE", bg=NAVY, fg="#9AA7C5",
                 font=("Segoe UI", 8)).pack(side="bottom", pady=20)
        self.main = tk.Frame(self.root, bg=BG)
        self.main.pack(side="left", fill="both", expand=True)
        self.header = tk.Frame(self.main, bg=BG)
        self.header.pack(fill="x", padx=30, pady=(25, 10))
        self.page_title = tk.Label(self.header, text="", bg=BG, fg=NAVY,
                                   font=("Segoe UI", 22, "bold"))
        self.page_title.pack(side="left")
        tk.Label(self.header, text="Your contacts, organized.", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="right", pady=10)
        self.body = tk.Frame(self.main, bg=BG)
        self.body.pack(fill="both", expand=True, padx=30, pady=15)

    def clear(self, title):
        for w in self.body.winfo_children(): w.destroy()
        self.page_title.config(text=title)

    def card(self, parent, title, value, accent=INDIGO):
        f = tk.Frame(parent, bg="white", highlightbackground="#E7EAF2", highlightthickness=1)
        tk.Frame(f, bg=accent, width=4).pack(side="left", fill="y")
        inner = tk.Frame(f, bg="white"); inner.pack(fill="both", expand=True, padx=16, pady=15)
        tk.Label(inner, text=title.upper(), bg="white", fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(inner, text=str(value), bg="white", fg=NAVY,
                 font=("Segoe UI", 23, "bold")).pack(anchor="w", pady=(5,0))
        return f

    def show_dashboard(self):
        self.clear("Dashboard")
        s = build_summary(self.manager.contacts)
        row = tk.Frame(self.body, bg=BG); row.pack(fill="x", pady=5)
        for title, val, color in [("Total contacts",s["total"],INDIGO),("Active",s["active"],"#20A67A"),
                                  ("Inactive",s["inactive"],"#E49A36"),("New this month",s["new_last_30_days"],"#3D91C9")]:
            self.card(row,title,val,color).pack(side="left", fill="both", expand=True, padx=(0,12))
        tk.Label(self.body, text="Recently added contacts", bg=BG, fg=NAVY,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(28,10))
        self._table(self.body, self.manager.search()[-8:][::-1])
        warning = f"Data quality: {s['incomplete']} incomplete • {s['duplicates']} duplicate email(s)"
        tk.Label(self.body, text=warning, bg="#FFF7E8", fg="#8B641D",
                 font=("Segoe UI", 10), padx=12, pady=10).pack(fill="x", pady=15)

    def _table(self, parent, contacts):
        frame = tk.Frame(parent, bg="white"); frame.pack(fill="both", expand=True)
        cols = ("id","name","phone","email","company","category","status")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=14)
        widths = [85,145,120,205,130,95,75]
        for col,w in zip(cols,widths):
            tree.heading(col,text=col.replace("_"," ").title()); tree.column(col,width=w,anchor="w")
        y = ttk.Scrollbar(frame, orient="vertical", command=tree.yview); tree.configure(yscrollcommand=y.set)
        tree.pack(side="left",fill="both",expand=True); y.pack(side="right",fill="y")
        for c in contacts:
            tree.insert("", "end", values=(c.id,c.name,c.phone,c.email,c.company,c.category,c.status))
        tree.bind("<Double-1>", lambda e: self.edit_selected(tree))
        return tree

    def show_contacts(self):
        self.clear("All Contacts")
        top = tk.Frame(self.body,bg=BG); top.pack(fill="x",pady=(0,12))
        tk.Button(top,text="+ Add Contact",command=self.add_contact,bg=INDIGO,fg="white",
                  relief="flat",padx=16,pady=9).pack(side="left")
        tk.Button(top,text="Edit selected",command=lambda:self.edit_selected(tree),bg="white",
                  fg=NAVY,relief="flat",padx=14,pady=9).pack(side="left",padx=8)
        tk.Button(top,text="Delete selected",command=lambda:self.delete_selected(tree),bg="white",
                  fg="#B44343",relief="flat",padx=14,pady=9).pack(side="left")
        tree = self._table(self.body,self.manager.search())
        self.contact_tree = tree

    def edit_selected(self, tree):
        sel=tree.selection()
        if not sel: messagebox.showinfo("Select contact","Select a contact first."); return
        cid=tree.item(sel[0],"values")[0]; self.open_form(cid)

    def delete_selected(self, tree):
        sel=tree.selection()
        if not sel: messagebox.showinfo("Select contact","Select a contact first."); return
        cid=tree.item(sel[0],"values")[0]
        c=self.manager.get(cid)
        if messagebox.askyesno("Confirm deletion",f"Delete {c.name}?"):
            self.manager.delete(cid); self.persist(); logger.info("Deleted %s",cid); self.show_contacts()

    def add_contact(self): self.open_form()

    def open_form(self, contact_id=None):
        existing = self.manager.get(contact_id).__dict__ if contact_id else {}
        win=tk.Toplevel(self.root); win.title("Edit contact" if contact_id else "Add contact")
        win.configure(bg="white"); win.geometry("570x650"); win.transient(self.root); win.grab_set()
        tk.Label(win,text="Edit contact" if contact_id else "Create a contact",bg="white",fg=NAVY,
                 font=("Segoe UI",19,"bold")).pack(anchor="w",padx=28,pady=(22,4))
        tk.Label(win,text="Fields marked * are required.",bg="white",fg=MUTED).pack(anchor="w",padx=28,pady=(0,12))
        form=tk.Frame(win,bg="white"); form.pack(fill="both",expand=True,padx=28)
        vars={}
        fields=[("name","Full name *"),("phone","Phone *"),("email","Email *"),("company","Company"),
                ("city","City"),("address","Address"),("notes","Notes")]
        for key,label in fields:
            tk.Label(form,text=label,bg="white",fg=NAVY,font=("Segoe UI",9,"bold")).pack(anchor="w",pady=(7,2))
            v=tk.StringVar(value=existing.get(key,"")); vars[key]=v
            tk.Entry(form,textvariable=v,relief="solid",bd=1,font=("Segoe UI",10)).pack(fill="x",ipady=7)
        for key, label, options, default in [
            ("category","Category",CATEGORIES,"Personal"),("status","Status",STATUSES,"Active")]:
            tk.Label(form,text=label,bg="white",fg=NAVY,font=("Segoe UI",9,"bold")).pack(anchor="w",pady=(8,2))
            v=tk.StringVar(value=existing.get(key,default)); vars[key]=v
            ttk.Combobox(form,textvariable=v,values=options,state="readonly").pack(fill="x",ipady=4)
        def save():
            vals={k:v.get() for k,v in vars.items()}
            try:
                if contact_id: self.manager.update(contact_id,vals); logger.info("Updated %s",contact_id)
                else:
                    c=self.manager.add(vals); logger.info("Added %s",c.id)
                self.persist(); win.destroy(); self.show_contacts()
            except ValueError as e: messagebox.showerror("Please check the details",str(e),parent=win)
        tk.Button(win,text="Save contact",command=save,bg=INDIGO,fg="white",relief="flat",
                  font=("Segoe UI",10,"bold"),padx=22,pady=11).pack(anchor="e",padx=28,pady=18)

    def search_contacts(self):
        self.clear("Search & Filter")
        bar=tk.Frame(self.body,bg=BG); bar.pack(fill="x",pady=(0,12))
        term=tk.StringVar(); cat=tk.StringVar(value="All"); status=tk.StringVar(value="All")
        tk.Entry(bar,textvariable=term,font=("Segoe UI",11),relief="solid",bd=1).pack(side="left",fill="x",expand=True,ipady=9)
        ttk.Combobox(bar,textvariable=cat,values=["All"]+CATEGORIES,state="readonly",width=13).pack(side="left",padx=8)
        ttk.Combobox(bar,textvariable=status,values=["All"]+STATUSES,state="readonly",width=11).pack(side="left")
        holder=tk.Frame(self.body,bg=BG); holder.pack(fill="both",expand=True)
        def run():
            for w in holder.winfo_children(): w.destroy()
            self._table(holder,self.manager.search(term.get(),cat.get(),status.get()))
        tk.Button(bar,text="Search",command=run,bg=INDIGO,fg="white",relief="flat",padx=18,pady=8).pack(side="left",padx=8)
        run()

    def show_analytics(self):
        self.clear("Analytics & Insights")
        s=build_summary(self.manager.contacts)
        grid=tk.Frame(self.body,bg=BG); grid.pack(fill="x")
        for title,key in [("Total contacts","total"),("Active","active"),("Inactive","inactive"),
                          ("New in 30 days","new_last_30_days"),("Incomplete records","incomplete"),("Duplicate emails","duplicates")]:
            self.card(grid,title,s[key]).pack(side="left",fill="both",expand=True,padx=(0,8),pady=5)
        tk.Label(self.body,text="Contacts by category",bg=BG,fg=NAVY,font=("Segoe UI",14,"bold")).pack(anchor="w",pady=(25,8))
        for k,v in s["by_category"].most_common():
            line=tk.Frame(self.body,bg=BG); line.pack(fill="x",pady=4)
            tk.Label(line,text=k,width=16,anchor="w",bg=BG,fg=NAVY).pack(side="left")
            tk.Label(line,text=f"{v}  {'▰'*min(v,35)}",bg=BG,fg=INDIGO).pack(side="left")
        tk.Label(self.body,text=f"Average contacts per category: {s['average_per_category']}",
                 bg=BG,fg=MUTED,font=("Segoe UI",10)).pack(anchor="w",pady=15)
        tk.Button(self.body,text="Export all reports",command=self.export_reports,bg=INDIGO,fg="white",
                  relief="flat",padx=18,pady=10).pack(anchor="w")

    def export_reports(self):
        s=build_summary(self.manager.contacts)
        export_contacts(self.manager.contacts,"reports/contacts_export.csv")
        export_markdown(s,"reports/summary.md"); export_text(s,"reports/audit.txt")
        export_summary_csv(s,"reports/summary.csv")
        messagebox.showinfo("Reports exported","Reports saved in the project's reports folder.")

    def import_export(self):
        self.clear("Import & Export")
        tk.Label(self.body,text="Bring in existing contacts or export your data for review.",
                 bg=BG,fg=MUTED,font=("Segoe UI",11)).pack(anchor="w",pady=(0,20))
        tk.Button(self.body,text="Import contacts from CSV",command=self.import_csv,bg=INDIGO,fg="white",
                  relief="flat",padx=18,pady=12).pack(anchor="w",pady=6)
        tk.Button(self.body,text="Export contacts to CSV",command=lambda:self.export_csv_dialog(),
                  bg="white",fg=NAVY,relief="flat",padx=18,pady=12).pack(anchor="w",pady=6)
        tk.Button(self.body,text="Generate Markdown / TXT / CSV reports",command=self.export_reports,
                  bg="white",fg=NAVY,relief="flat",padx=18,pady=12).pack(anchor="w",pady=6)

    def import_csv(self):
        path=filedialog.askopenfilename(filetypes=[("CSV files","*.csv")])
        if not path:return
        try:
            rows,errors=self.store.import_csv(path); added=0
            for row in rows:
                try:self.manager.add(row); added+=1
                except ValueError as e:errors.append(str(e))
            self.persist()
            msg=f"Imported {added} contact(s)."
            if errors: msg+="\n\nErrors:\n"+"\n".join(errors[:15])
            messagebox.showinfo("Import result",msg); self.show_contacts()
        except Exception as e: messagebox.showerror("Import failed",str(e))

    def export_csv_dialog(self):
        path=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV files","*.csv")])
        if path:
            export_contacts(self.manager.contacts,path); messagebox.showinfo("Exported","Contacts exported successfully.")

    def settings(self):
        self.clear("Settings")
        tk.Label(self.body,text="Choose the local storage format used by CONTACTLY.",
                 bg=BG,fg=MUTED,font=("Segoe UI",11)).pack(anchor="w",pady=(0,15))
        ttk.Combobox(self.body,textvariable=self.format,values=["json","csv"],state="readonly").pack(anchor="w")
        tk.Button(self.body,text="Load selected format",command=self.switch_format,bg=INDIGO,fg="white",
                  relief="flat",padx=18,pady=10).pack(anchor="w",pady=12)
        tk.Label(self.body,text="Both contacts.json and contacts.csv are maintained in the data folder when saved.",
                 bg=BG,fg=MUTED).pack(anchor="w",pady=10)

    def switch_format(self):
        self.manager=ContactManager(self.store.load(self.format.get()))
        self.show_dashboard()

    def persist(self):
        self.store.save(self.manager.contacts,"json")
        self.store.save(self.manager.contacts,"csv")

def run_gui():
    root=tk.Tk(); ContactlyApp(root); root.mainloop()



# ================ COMMAND-LINE INTERFACE ================

def ask(label, default=""):
    value = input(f"{label}{' ['+default+']' if default else ''}: ").strip()
    return value or default

def contact_values(existing=None):
    existing = existing or {}
    values = {}
    for key, label, default in [
        ("name","Full name",""),("phone","Phone",""),("email","Email",""),
        ("company","Company",""),("category","Category","Personal"),
        ("city","City",""),("address","Address",""),("notes","Notes",""),
        ("status","Status","Active")]:
        values[key] = ask(label, existing.get(key, default))
    return values

def run_cli():
    store = Storage()
    fmt = "json"
    manager = ContactManager(store.load(fmt))
    while True:
        print("\n" + "="*54)
        print("                 CONTACTLY")
        print("          SMART CONTACT MANAGEMENT")
        print("="*54)
        print("1. View contacts   2. Add contact   3. Edit contact")
        print("4. Delete contact  5. Search/filter 6. Analytics")
        print("7. Import CSV      8. Export reports 9. Change storage")
        print("0. Exit")
        choice = input("\nSelect option: ").strip()
        try:
            if choice == "1":
                for c in manager.search():
                    print(f"{c.id:8} | {c.name:22.22} | {c.phone:16} | {c.email:28.28} | {c.category}")
            elif choice == "2":
                c = manager.add(contact_values()); store.save(manager.contacts, fmt); logger.info("Added %s", c.id)
                print("Added:", c.name)
            elif choice == "3":
                cid = ask("Contact ID"); old = manager.get(cid)
                vals = contact_values(old.__dict__); manager.update(cid, vals); store.save(manager.contacts, fmt)
                logger.info("Updated %s", cid); print("Updated.")
            elif choice == "4":
                cid = ask("Contact ID")
                if ask(f"Delete {manager.get(cid).name}? (y/N)").lower() == "y":
                    manager.delete(cid); store.save(manager.contacts, fmt); logger.info("Deleted %s", cid)
            elif choice == "5":
                term = ask("Keyword")
                cat = ask("Category (All or " + "/".join(CATEGORIES) + ")", "All")
                for c in manager.search(term, cat):
                    print(f"{c.id} | {c.name} | {c.phone} | {c.email} | {c.category}")
            elif choice == "6":
                s = build_summary(manager.contacts)
                for k in ["total","active","inactive","new_last_30_days","incomplete","duplicates","average_per_category"]:
                    print(f"{k.replace('_',' ').title():28}: {s[k]}")
                print("By category:", dict(s["by_category"]))
            elif choice == "7":
                path = ask("CSV file path")
                rows, errors = store.import_csv(path)
                added = 0
                for row in rows:
                    try: manager.add(row); added += 1
                    except ValueError as e: errors.append(str(e))
                store.save(manager.contacts, fmt); print(f"Imported {added}; errors {len(errors)}")
                for e in errors: print(" -", e)
            elif choice == "8":
                s = build_summary(manager.contacts)
                export_contacts(manager.contacts, "reports/contacts_export.csv")
                export_markdown(s, "reports/summary.md"); export_text(s, "reports/audit.txt")
                export_summary_csv(s, "reports/summary.csv")
                print("Reports saved in reports/.")
            elif choice == "9":
                fmt = ask("Storage format (json/csv)", fmt).lower()
                if fmt not in ("json","csv"): raise ValueError("Choose json or csv.")
                manager = ContactManager(store.load(fmt))
            elif choice == "0":
                store.save(manager.contacts, fmt); print("Goodbye!"); break
            else:
                print("Choose a listed menu number.")
        except (ValueError, OSError) as e:
            print("Error:", e)



# ================ PROGRAM ENTRY POINT ================

import argparse

def main():
    parser=argparse.ArgumentParser(description="CONTACTLY Smart Contact Management")
    parser.add_argument("--cli",action="store_true",help="Launch terminal interface")
    args=parser.parse_args()
    if args.cli: run_cli()
    else: run_gui()

if __name__=="__main__":
    main()
