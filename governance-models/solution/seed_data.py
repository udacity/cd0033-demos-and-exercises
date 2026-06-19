"""
seed_data.py — Trailhead Provisions retail platform (synthetic seed for EXERCISES).

PROVIDED FILE. Students do not edit this. It is the exercise-repo parallel of the capstone's
Cardinal Outfitters seed: the SAME table schema and the same KINDS of deliberate imperfection,
but a different company and the gaps/conflicts placed in DIFFERENT tables — so practicing on
Trailhead does not hand over the Cardinal capstone answers.

Authored in the build workspace as `trailhead_seed.py`; the build script copies it into each
exercise/demo folder AS `seed_data.py`, so `governance_toolkit.py` (which does
`import seed_data`) runs against Trailhead unchanged.

Everything is local: tables land in SQLite (the "data lake"); the metadata catalog is an
in-memory Glue-style structure with governance-tag gaps and cross-domain conflicts.
Deterministic (fixed RNG seed) so every learner and reviewer sees identical data.
"""
from __future__ import annotations

import os
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

SEED = 71
EPOCH = datetime(2025, 1, 1, 0, 0, 0)
COMPANY = "Trailhead Provisions"

# ----------------------------------------------------------------------------- #
# Metadata catalog (Glue Data Catalog analog)
# ----------------------------------------------------------------------------- #

@dataclass
class ColumnMeta:
    name: str
    type: str
    classification: Optional[str] = None   # PII | SENSITIVE | PUBLIC | None(=gap)
    description: str = ""


@dataclass
class TableMeta:
    name: str
    domain: str
    columns: list[ColumnMeta]
    owner: Optional[str] = None
    classification: Optional[str] = None
    retention: Optional[str] = None
    description: str = ""
    lf_tags: dict[str, str] = field(default_factory=dict)

    def column(self, name: str) -> Optional[ColumnMeta]:
        return next((c for c in self.columns if c.name == name), None)


@dataclass
class Catalog:
    database: str
    tables: dict[str, TableMeta]
    semantic_conflicts: list[dict] = field(default_factory=list)

    def table(self, name: str) -> TableMeta:
        return self.tables[name]


# ----------------------------------------------------------------------------- #
# Synthetic value pools (distinct from Cardinal's, so MDM/identity data differs)
# ----------------------------------------------------------------------------- #

_FIRST = ["Mara", "Theo", "Iris", "Soren", "Nadia", "Bram", "Lucia", "Ravi", "Esme",
          "Kai", "Yara", "Felix", "Anouk", "Dario", "Pia", "Hugo", "Saanvi", "Linnea",
          "Idris", "Camila", "Oskar", "Tamsin", "Zane", "Mei", "Nuno"]
_LAST = ["Vance", "Holm", "Reyes", "Pope", "Adeyemi", "Park", "Conti", "Najjar",
         "Lindqvist", "Pereira", "Sattar", "Vik", "Salas", "Roth", "Ueda", "Doyle",
         "Engel", "Saleh", "Pinto", "Falk"]
_REGIONS = ["EU", "NA", "APAC", "LATAM"]
_REGION_COUNTRY = {"EU": ["DE", "FR", "SE", "ES"], "NA": ["US", "CA"],
                   "APAC": ["JP", "AU", "IN"], "LATAM": ["BR", "MX"]}
_TIERS = ["bronze", "silver", "gold", "platinum"]
_CATEGORIES = ["tents", "footwear", "apparel", "packs", "climbing", "nutrition"]
_CARRIERS = ["DHL", "FedEx", "UPS", "GLS", "PostNord"]
_CHANNELS = ["email", "sms", "push", "social"]
_SEGMENTS = ["lapsed", "vip", "new", "seasonal", "high_value"]
_RETURN_REASONS = ["size", "defective", "changed_mind", "late_delivery", "wrong_item"]


def _phone(rng: random.Random, region: str, dirty: bool = False) -> str:
    cc = {"EU": "+49", "NA": "+1", "APAC": "+81", "LATAM": "+55"}[region]
    num = "".join(str(rng.randint(0, 9)) for _ in range(9))
    if dirty:
        return rng.choice(["", "555", num])
    return f"{cc}{num}"


# ----------------------------------------------------------------------------- #
# Build
# ----------------------------------------------------------------------------- #

def _connect(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:" and os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def build(db_path: str = "trailhead.db") -> tuple[sqlite3.Connection, Catalog]:
    """Build the Trailhead Provisions lake + catalog. Returns (sqlite_conn, Catalog)."""
    rng = random.Random(SEED)
    conn = _connect(db_path)
    cur = conn.cursor()

    # --- Customer Identity & Loyalty ------------------------------------------ #
    cur.execute("""
        CREATE TABLE customer (
            customer_id      INTEGER PRIMARY KEY,
            full_name        TEXT,
            email            TEXT,
            phone            TEXT,
            region           TEXT,
            country          TEXT,
            loyalty_tier     TEXT,
            marketing_consent INTEGER,
            created_ts       TEXT
        )""")
    n_customers = 300
    combos = [(f, l) for f in _FIRST for l in _LAST]
    rng.shuffle(combos)
    base = combos[:n_customers]
    customers = []
    clean_email_ids = []
    for cid in range(1, n_customers + 1):
        first, last = base[cid - 1]
        region = rng.choice(_REGIONS)
        country = rng.choice(_REGION_COUNTRY[region])
        dom = rng.choice(["gmail.com", "outlook.com", "proton.me", "trailmail.co"])
        dirty_email = rng.random() < 0.06
        email = ("n/a" if dirty_email else f"{first}.{last}@{dom}").lower()
        phone = _phone(rng, region, dirty=(rng.random() < 0.05))
        tier = rng.choice(_TIERS)
        consent = 1 if rng.random() < 0.6 else 0
        days_ago = rng.randint(0, 540) if rng.random() > 0.04 else rng.randint(2000, 4000)
        created = EPOCH - timedelta(days=days_ago, hours=rng.randint(0, 23))
        customers.append((cid, f"{first} {last}", email, phone, region, country,
                          tier, consent, created.isoformat()))
        if not dirty_email:
            clean_email_ids.append(cid)
    # 8 deliberate duplicate persons (2 exact -> auto-merge, 6 variant -> ambiguous)
    dup_sources = rng.sample(clean_email_ids, 8)
    for k, cid in enumerate(dup_sources):
        src = customers[cid - 1]
        new_id = n_customers + k + 1
        name, email = src[1], src[2]
        if k >= 2:
            lp, dom = email.split("@", 1)
            if k % 2 == 0:
                newdom = "outlook.com" if dom != "outlook.com" else "gmail.com"
                email = f"{lp}@{newdom}"
            else:
                email = f"{lp}{rng.randint(1, 9)}@{dom}"
            if rng.random() < 0.5:
                name = name.replace(" ", "  ")
        customers.append((new_id, name, email, src[3], src[4], src[5],
                          rng.choice(_TIERS), src[7], src[8]))
    cur.executemany("INSERT INTO customer VALUES (?,?,?,?,?,?,?,?,?)", customers)

    # --- E-commerce Orders ---------------------------------------------------- #
    cur.execute("""
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY, customer_id INTEGER, order_ts TEXT,
            status TEXT, amount REAL, currency TEXT)""")
    cur.execute("""
        CREATE TABLE order_returns (
            return_id INTEGER PRIMARY KEY, order_id INTEGER, reason TEXT, qty INTEGER)""")
    n_orders = 1200
    orders, returns, rid = [], [], 1
    for oid in range(1, n_orders + 1):
        cid = rng.randint(1, n_customers)
        ots = EPOCH - timedelta(days=rng.randint(0, 420), hours=rng.randint(0, 23))
        status = rng.choices(["delivered", "shipped", "processing", "cancelled", "returned"],
                             weights=[55, 15, 12, 8, 10])[0]
        amount = round(rng.uniform(12, 680), 2)
        if rng.random() < 0.015:
            amount = -amount
        orders.append((oid, cid, ots.isoformat(), status, amount, "USD"))
        if status == "returned":
            returns.append((rid, oid, rng.choice(_RETURN_REASONS), rng.randint(1, 3)))
            rid += 1
    cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?)", orders)
    cur.executemany("INSERT INTO order_returns VALUES (?,?,?,?)", returns)

    # --- Inventory & Fulfillment ---------------------------------------------- #
    cur.execute("""
        CREATE TABLE supplier (
            supplier_id INTEGER PRIMARY KEY, name TEXT, country TEXT, esg_rating TEXT)""")
    cur.execute("""
        CREATE TABLE product (
            product_id INTEGER PRIMARY KEY, name TEXT, category TEXT, supplier_id INTEGER,
            unit_cost REAL, sustainability_class TEXT)""")
    cur.execute("""
        CREATE TABLE shipment (
            shipment_id INTEGER PRIMARY KEY, order_id INTEGER, carrier TEXT,
            ship_ts TEXT, carbon_kg REAL)""")
    n_suppliers = 40
    for sid in range(1, n_suppliers + 1):
        cur.execute("INSERT INTO supplier VALUES (?,?,?,?)",
                    (sid, f"Supplier-{sid:02d}", rng.choice(sum(_REGION_COUNTRY.values(), [])),
                     rng.choice(["A", "B", "C", None])))
    n_products = 200
    for pid in range(1, n_products + 1):
        cat = rng.choice(_CATEGORIES)
        if rng.random() < 0.08:
            cat = None
        sustainability = rng.choice(["recycled", "organic", "standard"])
        if rng.random() < 0.45:
            sustainability = None
        cur.execute("INSERT INTO product VALUES (?,?,?,?,?,?)",
                    (pid, f"{rng.choice(_CATEGORIES).title()} Model {pid}", cat,
                     rng.randint(1, n_suppliers), round(rng.uniform(5, 240), 2), sustainability))
    sid = 1
    for (oid, cid, ots, status, amount, cur_code) in orders:
        if status == "cancelled":
            continue
        carbon = round(rng.uniform(0.4, 9.5), 3)
        if rng.random() < 0.03:
            carbon = carbon * 1000  # grams-not-kg unit error (CSRD traceability defect)
        ship_ts = (datetime.fromisoformat(ots) + timedelta(days=rng.randint(1, 5))).isoformat()
        cur.execute("INSERT INTO shipment VALUES (?,?,?,?,?)",
                    (sid, oid, rng.choice(_CARRIERS), ship_ts, carbon))
        sid += 1

    # --- Marketing & Campaigns ------------------------------------------------ #
    cur.execute("""
        CREATE TABLE campaign (
            campaign_id INTEGER PRIMARY KEY, name TEXT, channel TEXT,
            start_date TEXT, end_date TEXT)""")
    cur.execute("""
        CREATE TABLE campaign_membership (
            membership_id INTEGER PRIMARY KEY, campaign_id INTEGER, cust_ref TEXT,
            segment TEXT, mkt_consent INTEGER)""")
    n_campaigns = 20
    for cpid in range(1, n_campaigns + 1):
        start = EPOCH - timedelta(days=rng.randint(30, 400))
        end = start + timedelta(days=rng.randint(7, 60))
        cur.execute("INSERT INTO campaign VALUES (?,?,?,?,?)",
                    (cpid, f"Campaign {cpid}", rng.choice(_CHANNELS),
                     start.date().isoformat(), end.date().isoformat()))
    mid = 1
    for _ in range(800):
        cpid = rng.randint(1, n_campaigns)
        cust = customers[rng.randint(0, n_customers - 1)]
        cust_ref = cust[2]                       # marketing keys customers by EMAIL
        loyalty_consent = cust[7]
        mkt_consent = loyalty_consent if rng.random() > 0.20 else (1 - loyalty_consent)
        cur.execute("INSERT INTO campaign_membership VALUES (?,?,?,?,?)",
                    (mid, cpid, cust_ref, rng.choice(_SEGMENTS), mkt_consent))
        mid += 1

    conn.commit()
    return conn, _build_catalog()


def _build_catalog() -> Catalog:
    """Trailhead's Glue-style catalog. Governance gaps placed DIFFERENTLY than Cardinal's.

    Demo slice (Inventory & Fulfillment + Orders):
      - orders:    missing owner
      - supplier:  missing retention
      - product:   missing retention; untagged column `unit_cost` (SENSITIVE)
      - shipment:  missing classification
    Exercise slice (Customer Identity + Marketing):
      - customer:  untagged PII column `email`   <-- the headline find
      - campaign:  missing owner
      - campaign_membership: missing owner + retention; untagged PII column `cust_ref`
    """
    C = ColumnMeta
    tables = {
        "customer": TableMeta(
            "customer", "Customer Identity & Loyalty",
            [C("customer_id", "INTEGER", "PUBLIC", "surrogate key"),
             C("full_name", "TEXT", "PII", "customer name"),
             C("email", "TEXT", None, "primary contact email"),            # GAP: PII untagged
             C("phone", "TEXT", "PII", "contact phone"),
             C("region", "TEXT", "PUBLIC", "service region; drives row policy"),
             C("country", "TEXT", "PUBLIC"),
             C("loyalty_tier", "TEXT", "PUBLIC"),
             C("marketing_consent", "INTEGER", "SENSITIVE", "GDPR consent (loyalty view)"),
             C("created_ts", "TEXT", "PUBLIC")],
            owner="customer-identity@trailhead.example",
            classification="PII", retention="P7Y",
            description="Master customer profile, loyalty domain of record."),
        "orders": TableMeta(
            "orders", "E-commerce Orders",
            [C("order_id", "INTEGER", "PUBLIC"),
             C("customer_id", "INTEGER", "PUBLIC", "FK to customer (loyalty key)"),
             C("order_ts", "TEXT", "PUBLIC"),
             C("status", "TEXT", "PUBLIC"),
             C("amount", "REAL", "SENSITIVE"),
             C("currency", "TEXT", "PUBLIC")],
            owner=None,                                                     # GAP
            classification="SENSITIVE", retention="P7Y",
            description="Purchase events."),
        "order_returns": TableMeta(
            "order_returns", "E-commerce Orders",
            [C("return_id", "INTEGER", "PUBLIC"),
             C("order_id", "INTEGER", "PUBLIC"),
             C("reason", "TEXT", "PUBLIC"),
             C("qty", "INTEGER", "PUBLIC")],
            owner="orders-team@trailhead.example",
            classification="PUBLIC", retention="P3Y",
            description="Order returns."),
        "supplier": TableMeta(
            "supplier", "Inventory & Fulfillment",
            [C("supplier_id", "INTEGER", "PUBLIC"),
             C("name", "TEXT", "PUBLIC"),
             C("country", "TEXT", "PUBLIC"),
             C("esg_rating", "TEXT", "PUBLIC", "ESG supplier rating; CSRD input")],
            owner="inventory-fulfillment@trailhead.example",
            classification="PUBLIC", retention=None),                      # GAP
        "product": TableMeta(
            "product", "Inventory & Fulfillment",
            [C("product_id", "INTEGER", "PUBLIC"),
             C("name", "TEXT", "PUBLIC"),
             C("category", "TEXT", "PUBLIC", "mandatory per inventory standard"),
             C("supplier_id", "INTEGER", "PUBLIC"),
             C("unit_cost", "REAL", None, "wholesale cost; commercially sensitive"),  # GAP: untagged SENSITIVE
             C("sustainability_class", "TEXT", "PUBLIC", "CSRD attribute; often missing")],
            owner="inventory-fulfillment@trailhead.example",
            classification="SENSITIVE", retention=None),                   # GAP
        "shipment": TableMeta(
            "shipment", "Inventory & Fulfillment",
            [C("shipment_id", "INTEGER", "PUBLIC"),
             C("order_id", "INTEGER", "PUBLIC"),
             C("carrier", "TEXT", "PUBLIC"),
             C("ship_ts", "TEXT", "PUBLIC"),
             C("carbon_kg", "REAL", "PUBLIC", "per-shipment carbon (kg); CSRD source")],
            owner="inventory-fulfillment@trailhead.example",
            classification=None, retention="P10Y"),                        # GAP
        "campaign": TableMeta(
            "campaign", "Marketing & Campaigns",
            [C("campaign_id", "INTEGER", "PUBLIC"),
             C("name", "TEXT", "PUBLIC"),
             C("channel", "TEXT", "PUBLIC"),
             C("start_date", "TEXT", "PUBLIC"),
             C("end_date", "TEXT", "PUBLIC")],
            owner=None,                                                    # GAP
            classification="PUBLIC", retention="P3Y"),
        "campaign_membership": TableMeta(
            "campaign_membership", "Marketing & Campaigns",
            [C("membership_id", "INTEGER", "PUBLIC"),
             C("campaign_id", "INTEGER", "PUBLIC"),
             C("cust_ref", "TEXT", None, "customer EMAIL (marketing's key)"),  # GAP: PII untagged
             C("segment", "TEXT", "PUBLIC"),
             C("mkt_consent", "INTEGER", "SENSITIVE", "marketing consent (marketing view)")],
            owner=None, classification="SENSITIVE", retention=None,        # GAP x2
            description="Campaign membership; keys customers by email."),
    }
    conflicts = [
        {"concept": "customer identity key",
         "domain_a": "Customer Identity & Loyalty", "field_a": "customer.customer_id (INTEGER surrogate)",
         "domain_b": "Marketing & Campaigns", "field_b": "campaign_membership.cust_ref (email string)",
         "impact": "No shared join key; cross-domain customer resolution must match on email."},
        {"concept": "marketing consent",
         "domain_a": "Customer Identity & Loyalty", "field_a": "customer.marketing_consent",
         "domain_b": "Marketing & Campaigns", "field_b": "campaign_membership.mkt_consent",
         "impact": "Two systems of record for consent disagree ~20% of the time; GDPR risk if marketing acts on stale consent."},
        {"concept": "carbon unit of measure",
         "domain_a": "Inventory & Fulfillment", "field_a": "shipment.carbon_kg (kg)",
         "domain_b": "Reporting (derived)", "field_b": "a slice stored in grams",
         "impact": "Mixed units inflate the CSRD disclosure unless normalized; traceability breaks at the unit boundary."},
    ]
    return Catalog(database="trailhead", tables=tables, semantic_conflicts=conflicts)


if __name__ == "__main__":
    conn, cat = build(":memory:")
    cur = conn.cursor()
    print(f"{COMPANY} — tables, rows, gaps:")
    for t in cat.tables:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        gaps = [g for g in ("owner", "classification", "retention")
                if getattr(cat.table(t), g) is None]
        untagged = [c.name for c in cat.table(t).columns if c.classification is None]
        print(f"  {t:22} rows={n:5d}  tbl_gaps={gaps}  untagged_cols={untagged}")
    print(f"\nSemantic conflicts: {len(cat.semantic_conflicts)}")
