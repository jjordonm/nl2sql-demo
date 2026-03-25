"""
generate_seed_data.py - Generate realistic seed CSVs for the key Snowflake tables.

Run this script to regenerate seed data:
    python generate_seed_data.py

Creates CSV files in data/seed/ for the key business tables.
"""

import csv
import random
import os
from datetime import datetime, timedelta
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent / "data" / "seed"
SEED_DIR.mkdir(parents=True, exist_ok=True)

random.seed(42)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

PLANTS = [
    ("P100", "SAP01", "Windsor Locks", "CT", "US", "EAST"),
    ("P200", "SAP01", "Rockford", "IL", "US", "CENTRAL"),
    ("P300", "SAP02", "Burnsville", "MN", "US", "CENTRAL"),
    ("P400", "SAP01", "Pueblo", "CO", "US", "WEST"),
    ("P500", "SAP03", "Singapore", "SG", "SG", "APAC"),
    ("P600", "SAP02", "Figeac", "OC", "FR", "EMEA"),
    ("P700", "SAP01", "Wolverhampton", "WM", "GB", "EMEA"),
    ("P800", "SAP03", "Suzhou", "JS", "CN", "APAC"),
    ("P900", "SAP02", "Mexicali", "BC", "MX", "LATAM"),
    ("P010", "SAP01", "Jacksonville", "FL", "US", "EAST"),
]

VENDORS = [
    ("V1001", "Precision Castparts Corp"),
    ("V1002", "Honeywell Aerospace"),
    ("V1003", "GE Aviation"),
    ("V1004", "Safran SA"),
    ("V1005", "MTU Aero Engines"),
    ("V1006", "Triumph Group"),
    ("V1007", "Spirit AeroSystems"),
    ("V1008", "Ducommun Inc"),
    ("V1009", "Heico Corp"),
    ("V1010", "TransDigm Group"),
    ("V1011", "Kaman Aerospace"),
    ("V1012", "Senior Aerospace"),
]

MATERIAL_GROUPS = [
    ("MG01", "Raw Materials"),
    ("MG02", "Machined Parts"),
    ("MG03", "Castings & Forgings"),
    ("MG04", "Electronic Components"),
    ("MG05", "Fasteners & Hardware"),
    ("MG06", "Seals & Gaskets"),
    ("MG07", "Bearings"),
    ("MG08", "Sub-Assemblies"),
]

PO_TYPES = [
    ("NB", "Standard PO"),
    ("UB", "Stock Transfer"),
    ("FO", "Framework Order"),
    ("ZNB", "Subcontracting"),
]

SUPPLIER_TYPES = ["External", "Intercompany", "Subcontractor"]
STATUSES = ["Open", "Partially Delivered", "In Transit"]
CURRENCIES = ["USD", "EUR", "GBP", "CNY", "SGD", "MXN"]
PURCHASING_GROUPS = [
    ("PG1", "Structures Procurement"),
    ("PG2", "Electronics Procurement"),
    ("PG3", "Mechanical Procurement"),
    ("PG4", "MRO Procurement"),
    ("PG5", "Raw Materials Procurement"),
]

MATERIALS = [
    (f"MAT{i:05d}", f"10{i:05d}", f"Part assembly {chr(65 + (i % 26))}-{i}")
    for i in range(1, 51)
]

SEGMENTS = ["Aerostructures", "Mission Systems", "Interiors", "Power & Controls", "Avionics"]
LIFECYCLE = ["Active", "Phase Out", "Obsolete", "New Introduction"]
OE_SPARES = ["OE", "Spares", "MRO"]
MATERIAL_TYPES = ["FERT", "HALB", "ROH", "HIBE", "ERSA"]
PROCUREMENT_TYPES = ["E", "F", "X"]  # External, In-house, Both


def rand_date(start: str, end: str) -> str:
    """Random date string between start and end (YYYY-MM-DD)."""
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    d = s + timedelta(days=random.randint(0, (e - s).days))
    return d.strftime("%Y-%m-%d")


def rand_ts(start: str, end: str) -> str:
    """Random timestamp string."""
    return rand_date(start, end) + " " + f"{random.randint(0,23):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}"


# ---------------------------------------------------------------------------
# CORE_PLANT
# ---------------------------------------------------------------------------

def gen_core_plant():
    rows = []
    for plant_id, tas, name, region, country, district in PLANTS:
        rows.append({
            "TAS_SOURCE_ID": tas,
            "PLANT_ID": plant_id,
            "PLANT_NAME": name,
            "PLANT_NAME_2": f"{name} Facility",
            "VALUATION_AREA_ID": plant_id,
            "PLANT_CATEGORY": random.choice(["Manufacturing", "Distribution", "Service"]),
            "PURCHASING_ORGANISATION_ID": f"POrg-{plant_id}",
            "CUSTOMER_ID": f"CUST-{random.randint(1000, 9999)}",
            "VENDOR_ID": f"VEND-{plant_id}",
            "SALES_ORGANISATION_ID": f"SO-{country}",
            "DISTRIBUTION_CHANNEL_ID": random.choice(["10", "20", "30"]),
            "DIVISION_ID": random.choice(["01", "02", "03"]),
            "ADDRESS_ID": f"ADDR-{plant_id}",
            "SALES_DISTRICT_ID": district,
            "ADDRESS": f"{random.randint(100, 9999)} Industrial Pkwy",
            "CITY": name,
            "REGION": region,
            "COUNTRY": country,
            "SALES_OPER_PLANNING_PLANT_IND": random.choice(["X", ""]),
            "FACTORY_CALENDAR_CD": f"FC-{country}",
            "PLANNING_PLANT": plant_id,
            "SHIPPING_PLANT": plant_id,
            "DWH_CHANGE_DATE": rand_ts("2025-01-01", "2026-03-24"),
        })
    return rows


# ---------------------------------------------------------------------------
# AIML_OPEN_PURCHASE_ORDERS
# ---------------------------------------------------------------------------

def gen_open_purchase_orders(n=30):
    rows = []
    for i in range(1, n + 1):
        plant = random.choice(PLANTS)
        vendor = random.choice(VENDORS)
        mg = random.choice(MATERIAL_GROUPS)
        po_type = random.choice(PO_TYPES)
        pg = random.choice(PURCHASING_GROUPS)
        mat = random.choice(MATERIALS)
        currency = random.choice(CURRENCIES)
        creation_date = rand_date("2024-06-01", "2026-03-01")
        delivery_date = rand_date("2026-01-01", "2026-12-31")
        sched_qty = round(random.uniform(1, 500), 0)
        received_qty = round(random.uniform(0, sched_qty * 0.8), 0)
        open_qty = sched_qty - received_qty
        unit_price = round(random.uniform(10, 5000), 2)
        open_val = round(open_qty * unit_price, 2)
        exchange_rate = round(random.uniform(0.7, 1.3), 4) if currency != "USD" else 1.0
        open_val_usd = round(open_val * exchange_rate, 2)

        rows.append({
            "TAS_SOURCE_ID": plant[1],
            "PLANT_ID": plant[0],
            "COMPANY_ID": f"CO-{plant[1]}",
            "VEND_NM": vendor[1],
            "VENDOR_ID": vendor[0],
            "SUPPLIER_TYPE": random.choice(SUPPLIER_TYPES),
            "SUPPLYING_PLANT": random.choice([p[0] for p in PLANTS] + [""]),
            "PURCHASE_GROUP_ID": pg[0],
            "PURCHASING_GROUP_NAME": pg[1],
            "PURCHASE_ORDER_TYPE_ID": po_type[0],
            "PURCHASE_ORDER_TYPE_DESCRIPTION": po_type[1],
            "PURCHASE_ORDER_HEADER_CREATION_DATE": creation_date,
            "PURCHASE_ORDER_ID": f"45{random.randint(10000000, 99999999)}",
            "PURCHASE_ORDER_ITEM_ID": random.randint(1, 20) * 10,
            "PURCHASE_ORDER_SCHED_LINE_ID": str(random.randint(1, 5)),
            "MATERIAL_GROUP": mg[0],
            "MATERIAL_GROUP_DESCRIPTION": mg[1],
            "MATERIAL_ID": mat[0],
            "MATERIAL_NUMBER": mat[1],
            "PRFT_CNTR_ID": f"PC-{random.randint(1000, 9999)}",
            "PO_SCHD_LINE_QTY": sched_qty,
            "RECEIVED_QTY": received_qty,
            "SHIPPED_NOT_RECEIVED_QTY": round(random.uniform(0, 50), 0),
            "STATISTICS_RELEVANT_DATE": rand_date("2025-06-01", "2026-06-30"),
            "PO_SCHD_LINE_DELIVERY_DATE": delivery_date,
            "PO_COMMIT_DT": rand_date("2025-01-01", "2026-06-30"),
            "EXCPTN_MSG_NUM": random.choice(["", "06", "07", "10", "12"]),
            "EXCPTN_MSG_DESC": random.choice(["", "Bring forward", "Postpone", "Cancel", "Expedite"]),
            "EXCPTN_RSCHD_DT": rand_date("2026-01-01", "2026-12-31") if random.random() > 0.5 else "",
            "OPEN_QTY": open_qty,
            "OPEN_SUPPLYING_PLANT_QTY": round(random.uniform(0, open_qty * 0.5), 0),
            "OPEN_VALUE_IN_DC": open_val,
            "OPEN_VALUE_IN_USD": open_val_usd,
            "DOCUMENT_CURRENCY": currency,
            "OVERRIDE_DATE": "",
            "TRADE_OFF_ZONE": random.randint(-5, 30),
            "DWH_CHANGE_DATE": rand_ts("2025-01-01", "2026-03-24"),
            "ELIKZ_EKPO": random.choice(["", "X"]),
            "MENGE_EKPO": sched_qty,
            "LOEKZ_EKPO": "",
            "LOEKZ_EKKO": "",
            "MENGE_EKET": sched_qty,
            "WEMNG_EKET": received_qty,
            "STATU_EKKO": random.choice(["", "5", "9"]),
            "EREKZ_EKPO_FINALINVIND": random.choice(["", "X"]),
            "EGLKZ_EKPO_OUTWARDDELCOMPLETEIND": random.choice(["", "X"]),
            "REASON_FOR_CANCELLATION": "",
        })
    return rows


# ---------------------------------------------------------------------------
# EDW_INVENTORY_SEGMENTATION_SNAPSHOT (subset of columns for seed)
# ---------------------------------------------------------------------------

def gen_inventory_snapshot(n=40):
    rows = []
    for i in range(1, n + 1):
        plant = random.choice(PLANTS)
        mat = random.choice(MATERIALS)
        currency = random.choice(["USD", "EUR", "GBP"])
        std_price = round(random.uniform(5, 3000), 2)
        exchange = 1.0 if currency == "USD" else round(random.uniform(0.8, 1.2), 4)

        # Generate values for all 113 columns; use defaults for most
        row = {
            "TAS_SOURCE_ID": plant[1],
            "SNAPSHOT_ID": f"SNAP-{rand_date('2026-01-01', '2026-03-24').replace('-', '')}",
            "SNAPSHOT_TYPE": random.choice(["MONTHLY", "WEEKLY"]),
            "MATERIAL_NUMBER": mat[1],
            "MATERIAL_ID": mat[0],
            "MATERIAL_DESCRIPTION": mat[2],
            "MATERIAL_TYPE": random.choice(MATERIAL_TYPES),
            "PLANT_ID": plant[0],
            "PLANT_NAME": plant[2],
            "COMPANY_CODE": f"CO-{plant[1]}",
            "PROFIT_CENTER": f"PC-{random.randint(1000, 9999)}",
            "OE_SPARES_MRO": random.choice(OE_SPARES),
            "SEGMENT": random.choice(SEGMENTS),
            "LTB": random.choice(["Y", "N", ""]),
            "LIFE_CYCLE": random.choice(LIFECYCLE),
            "DCM_CLASS": random.choice(["A", "B", "C", "D"]),
            "NO_ABC": random.choice(["A", "B", "C"]),
            "EXCHANGE_RATE": exchange,
            "CURRENCY": currency,
            "STANDARD_PRICE_LC": std_price,
            "STANDARD_PRICE_USD": round(std_price * exchange, 2),
            "PROCUREMENT_TYPE": random.choice(PROCUREMENT_TYPES),
            "MRP_CONTROLLER_ID": f"MRP-{random.randint(100, 999)}",
            "VALUATION_TYPE": random.choice(["", "NEW", "REPAIRED"]),
            "MRP_GROUP": f"GRP-{random.randint(1, 20)}",
            "MATERIAL_GROUP_4_ID": f"MG4-{random.randint(100, 999)}",
            "MATERIAL_GROUP_5_ID": f"MG5-{random.randint(100, 999)}",
            "CURRENT_EMP_POLICY": random.choice(["MIN-MAX", "REORDER POINT", "MRP"]),
        }

        # Fill remaining numeric columns with plausible values
        numeric_extras = {
            "ON_HAND_QTY": round(random.uniform(0, 1000), 0),
            "ON_HAND_VALUE_LC": round(random.uniform(0, 200000), 2),
            "ON_HAND_VALUE_USD": round(random.uniform(0, 200000), 2),
            "IN_TRANSIT_QTY": round(random.uniform(0, 200), 0),
            "IN_TRANSIT_VALUE_USD": round(random.uniform(0, 50000), 2),
            "BLOCKED_QTY": round(random.uniform(0, 50), 0),
            "QI_QTY": round(random.uniform(0, 30), 0),
            "SAFETY_STOCK_QTY": round(random.uniform(0, 200), 0),
            "REORDER_POINT_QTY": round(random.uniform(0, 300), 0),
            "AVG_MONTHLY_DEMAND": round(random.uniform(0, 100), 2),
            "AVG_MONTHLY_DEMAND_VALUE_USD": round(random.uniform(0, 50000), 2),
            "EXCESS_QTY": round(random.uniform(0, 200), 0),
            "EXCESS_VALUE_USD": round(random.uniform(0, 100000), 2),
            "SLOW_MOVING_QTY": round(random.uniform(0, 100), 0),
            "OBSOLETE_QTY": round(random.uniform(0, 50), 0),
            "MONTHS_ON_HAND": round(random.uniform(0, 36), 1),
            "DAYS_ON_HAND": round(random.uniform(0, 1080), 0),
            "LEAD_TIME_DAYS": round(random.uniform(5, 180), 0),
        }
        row.update(numeric_extras)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# EDW_MATL_LOC_DEMAND_INFO
# ---------------------------------------------------------------------------

def gen_demand_info(n=25):
    rows = []
    for i in range(1, n + 1):
        plant = random.choice(PLANTS)
        mat = random.choice(MATERIALS)
        rows.append({
            "SRC": plant[1],
            "MATL_ID": mat[0],
            "PLANT_ID": plant[0],
            "TAS_SRC_ID": plant[1],
            "BASE_UOM_CD": random.choice(["EA", "KG", "M", "L"]),
            "TOT_DMND_QTY": round(random.uniform(0, 500), 0),
            "TOT_DMND_VAL_USD": round(random.uniform(0, 100000), 2),
            "CUR_MNTH_DMND_QTY": round(random.uniform(0, 80), 0),
            "CUR_MNTH_DMND_VAL_USD": round(random.uniform(0, 20000), 2),
            "AVG_3M_DMND_QTY": round(random.uniform(0, 60), 2),
            "AVG_6M_DMND_QTY": round(random.uniform(0, 50), 2),
            "AVG_12M_DMND_QTY": round(random.uniform(0, 45), 2),
            "FCST_NXT_3M_QTY": round(random.uniform(0, 150), 0),
            "FCST_NXT_6M_QTY": round(random.uniform(0, 300), 0),
            "FCST_NXT_12M_QTY": round(random.uniform(0, 500), 0),
            "LAST_ISSUE_DT": rand_date("2025-01-01", "2026-03-24"),
            "LAST_RECEIPT_DT": rand_date("2025-01-01", "2026-03-24"),
            "DAYS_SINCE_LAST_DMND": random.randint(0, 365),
            "ADJ_AVG_DMND_QTY": round(random.uniform(0, 60), 2),
            "PEAK_DMND_QTY": round(random.uniform(10, 200), 0),
            "MIN_DMND_QTY": round(random.uniform(0, 20), 0),
            "DMND_VARIABILITY_PCT": round(random.uniform(0, 100), 1),
            "DMND_TREND": random.choice(["UP", "DOWN", "STABLE", "SEASONAL"]),
            "DWH_CHANGE_DATE": rand_ts("2025-01-01", "2026-03-24"),
        })
    return rows


# ---------------------------------------------------------------------------
# Write CSVs
# ---------------------------------------------------------------------------

def write_csv(filename: str, rows: list[dict]):
    if not rows:
        return
    path = SEED_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    print("Generating seed data...")
    write_csv("CORE_PLANT.csv", gen_core_plant())
    write_csv("AIML_OPEN_PURCHASE_ORDERS.csv", gen_open_purchase_orders(30))
    write_csv("EDW_INVENTORY_SEGMENTATION_SNAPSHOT.csv", gen_inventory_snapshot(40))
    write_csv("EDW_MATL_LOC_DEMAND_INFO.csv", gen_demand_info(25))
    print("Done!")
