"""
workshop_utils.py
------------------
Shared helper functions for the "KFC Loyalty Platform" MongoDB schema design
workshop. Keeping this plumbing out of the notebook lets each notebook cell
stay focused on the schema-design concept being taught.

Each attendee shares one Atlas cluster (MONGODB_URI) but works in their own
database (DB_NAME), both read from a local .env file. See README.md for setup.
"""

import os
import random
import time
from datetime import datetime, timedelta, timezone

import certifi
import pandas as pd
from bson import ObjectId
from dotenv import load_dotenv
from faker import Faker
from pymongo import MongoClient
from pymongo.errors import ConfigurationError

fake = Faker()
Faker.seed(42)
random.seed(42)

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_db():
    """
    Load MONGODB_URI and DB_NAME from .env and return a pymongo Database
    handle. Uses certifi's CA bundle for TLS verification, which avoids the
    common "SSL: CERTIFICATE_VERIFY_FAILED" error on some macOS / Python
    installs when connecting to Atlas.
    """
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("DB_NAME")

    if not uri:
        raise ConfigurationError(
            "MONGODB_URI not found. Copy .env.example to .env and fill in "
            "the connection string provided by your workshop organizer."
        )
    if not db_name or db_name == "kfc_loyalty_<yourname>":
        raise ConfigurationError(
            "DB_NAME not set to a unique value. Edit .env and set DB_NAME "
            "to something like kfc_loyalty_<yourname> so you don't collide "
            "with other attendees on the shared cluster."
        )

    client = MongoClient(uri, tlsCAFile=certifi.where())
    # Fail fast with a clear error if the connection/credentials are bad.
    client.admin.command("ping")
    db = client[db_name]
    print(f"Connected to Atlas cluster. Using database: '{db_name}'")
    return db


def reset_workshop_db(db, collections=None):
    """
    Drop the workshop's collections so notebook cells can be re-run from a
    clean slate. Only ever touches the caller's own database.
    """
    collections = collections or [
        "customers",
        "stores",
        "menu_items",
        "orders",
        "point_transactions",
        "rewards",
        "redemptions",
        "customer_overflow",
    ]
    for name in collections:
        db.drop_collection(name)
    print(f"Dropped collections in '{db.name}': {', '.join(collections)}")


# ---------------------------------------------------------------------------
# Pretty printing / explain helpers
# ---------------------------------------------------------------------------

def pprint_doc(doc):
    """Pretty-print a single document (handles ObjectId/datetime)."""
    import json

    def default(o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)

    print(json.dumps(doc, indent=2, default=default))


def pprint_docs(cursor, n=5):
    """Pretty-print up to n documents from a cursor/list."""
    for i, doc in enumerate(cursor):
        if i >= n:
            print(f"... ({n} of more shown)")
            break
        pprint_doc(doc)
        print("-" * 40)


def explain_summary(explain_result, label=""):
    """
    Extract the key metrics from a .explain('executionStats') result into a
    one-row pandas DataFrame, so we can line up multiple strategies
    side-by-side (e.g. $lookup join vs. extended reference).
    """
    stats = explain_result.get("executionStats", {})
    winning_plan = explain_result.get("queryPlanner", {}).get("winningPlan", {})

    def find_stage(plan, key="stage"):
        if key in plan:
            return plan[key]
        for child_key in ("inputStage", "shards"):
            child = plan.get(child_key)
            if isinstance(child, dict):
                found = find_stage(child, key)
                if found:
                    return found
        return None

    row = {
        "label": label,
        "stage": find_stage(winning_plan) or "N/A",
        "executionTimeMillis": stats.get("executionTimeMillis"),
        "totalDocsExamined": stats.get("totalDocsExamined"),
        "totalKeysExamined": stats.get("totalKeysExamined"),
        "nReturned": stats.get("nReturned"),
    }
    return pd.DataFrame([row])


def time_it(fn, *args, **kwargs):
    """Run fn and return (result, elapsed_ms)."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return result, elapsed_ms


def doc_size_bytes(doc):
    """Return the BSON-encoded size of a document in bytes."""
    from bson import BSON

    return len(BSON.encode(doc))


# ---------------------------------------------------------------------------
# KFC-themed data generators
# ---------------------------------------------------------------------------

MENU_ITEMS = [
    {"sku": "ORC-8PC", "name": "8pc Original Recipe Bucket", "category": "Chicken", "price": 24.99},
    {"sku": "ZNG-BURGER", "name": "Zinger Burger", "category": "Sandwich", "price": 7.49},
    {"sku": "POPCORN-L", "name": "Popcorn Chicken (Large)", "category": "Chicken", "price": 6.99},
    {"sku": "FAMOUS-BOWL", "name": "Famous Bowl", "category": "Bowl", "price": 5.99},
    {"sku": "TENDERS-3PC", "name": "3pc Extra Crispy Tenders", "category": "Chicken", "price": 6.49},
    {"sku": "BISCUIT", "name": "Buttermilk Biscuit", "category": "Side", "price": 1.99},
    {"sku": "MASHED-POTATO", "name": "Mashed Potatoes & Gravy", "category": "Side", "price": 2.49},
    {"sku": "COLESLAW", "name": "Coleslaw", "category": "Side", "price": 2.29},
    {"sku": "PEPSI-20", "name": "Pepsi (20oz)", "category": "Beverage", "price": 2.19},
    {"sku": "MAC-CHEESE", "name": "Mac & Cheese", "category": "Side", "price": 2.99},
]

STORE_CITIES = [
    "Louisville, KY", "Nashville, TN", "Atlanta, GA", "Dallas, TX",
    "Charlotte, NC", "Orlando, FL", "Columbus, OH", "Memphis, TN",
]

TIERS = ["Bronze", "Silver", "Gold", "Platinum"]

REWARD_TYPES = ["free_item", "percent_discount", "delivery_waiver", "bogo"]


def generate_stores(n=6):
    docs = []
    for i in range(n):
        city = STORE_CITIES[i % len(STORE_CITIES)]
        docs.append({
            "_id": f"STORE-{1000 + i}",
            "name": f"KFC {city.split(',')[0]} #{1000 + i}",
            "city": city,
            "address": fake.street_address(),
            "openedOn": fake.date_between(start_date="-10y", end_date="-1y").isoformat(),
        })
    return docs


def generate_menu_items():
    return [{"_id": item["sku"], **item} for item in MENU_ITEMS]


def generate_customers(n=50, store_ids=None):
    store_ids = store_ids or ["STORE-1000"]
    docs = []
    for _ in range(n):
        joined = fake.date_time_between(start_date="-3y", end_date="-1M", tzinfo=timezone.utc)
        docs.append({
            "_id": ObjectId(),
            "name": fake.name(),
            "email": fake.unique.email(),
            "phone": fake.phone_number(),
            "homeStoreId": random.choice(store_ids),
            "joinedAt": joined,
            "tier": random.choices(TIERS, weights=[50, 30, 15, 5])[0],
            "loyaltyStats": {
                "lifetimePoints": 0,
                "currentBalance": 0,
                "totalOrders": 0,
                "lastComputedAt": joined,
            },
            "hasExtendedHistory": False,
        })
    return docs


def generate_orders(customers, store_ids, menu_items, n=200):
    """
    Generates orders using the EXTENDED REFERENCE pattern: each order embeds
    a small denormalized snapshot of the customer (id, name, tier) alongside
    the storeId reference, so order-list views don't need a $lookup.
    """
    docs = []
    for _ in range(n):
        customer = random.choice(customers)
        n_items = random.randint(1, 4)
        chosen_items = random.sample(menu_items, k=min(n_items, len(menu_items)))
        line_items = [
            {"sku": item["_id"], "name": item["name"], "qty": random.randint(1, 2), "unitPrice": item["price"]}
            for item in chosen_items
        ]
        total = round(sum(li["qty"] * li["unitPrice"] for li in line_items), 2)
        docs.append({
            "_id": ObjectId(),
            "customerRef": {
                "customerId": customer["_id"],
                "displayName": customer["name"],
                "tier": customer["tier"],
            },
            "storeId": random.choice(store_ids),
            "items": line_items,
            "total": total,
            "pointsEarned": int(total),
            "orderedAt": fake.date_time_between(start_date="-1y", end_date="now", tzinfo=timezone.utc),
        })
    return docs


def generate_point_transactions_for_customer(customer_id, n=20, start_balance=0):
    """Generate a chronological list of point transactions for one customer."""
    txns = []
    balance = start_balance
    ts = datetime.now(timezone.utc) - timedelta(days=n * 3)
    for i in range(n):
        delta = random.choice([5, 8, 12, 15, 20, -50, -100]) if i % 7 != 0 else -random.choice([50, 100, 150])
        balance = max(0, balance + delta)
        ts = ts + timedelta(days=random.randint(1, 3))
        txns.append({
            "_id": ObjectId(),
            "customerId": customer_id,
            "type": "earn" if delta > 0 else "redeem",
            "points": delta,
            "balanceAfter": balance,
            "timestamp": ts,
        })
    return txns


def generate_polymorphic_rewards():
    """
    Returns sample documents for the Inheritance (Polymorphic) Pattern demo:
    one base shape, three discriminated subtypes via the `type` field.
    """
    now = datetime.now(timezone.utc)
    valid_to = now + timedelta(days=60)
    return [
        {
            "_id": "RWD-FREE-TENDERS",
            "type": "free_item",
            "name": "Free 3pc Tenders",
            "pointsCost": 150,
            "validFrom": now,
            "validTo": valid_to,
            "freeItem": {"sku": "TENDERS-3PC", "maxQtyPerRedemption": 1},
        },
        {
            "_id": "RWD-20-OFF",
            "type": "percent_discount",
            "name": "20% Off Entire Order",
            "pointsCost": 200,
            "validFrom": now,
            "validTo": valid_to,
            "percentDiscount": {"percentage": 20, "maxDiscountAmount": 10.00},
        },
        {
            "_id": "RWD-FREE-DELIVERY",
            "type": "delivery_waiver",
            "name": "Free Delivery",
            "pointsCost": 75,
            "validFrom": now,
            "validTo": valid_to,
            "deliveryWaiver": {"waivedFeeAmount": 4.99},
        },
        {
            "_id": "RWD-BOGO-ZINGER",
            "type": "bogo",
            "name": "Buy One Get One Zinger Burger",
            "pointsCost": 180,
            "validFrom": now,
            "validTo": valid_to,
            "bogo": {"eligibleSkus": ["ZNG-BURGER"], "maxFreeQty": 1},
        },
    ]
