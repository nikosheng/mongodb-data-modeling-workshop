# Capstone Exercise Solution: Referral Program

This is the full written solution for the capstone exercise in Part 5 of
`notebook/kfc_loyalty_schema_workshop.ipynb`. Try the exercise yourself in
the notebook before reading this.

*(繁體中文版請見 [`CAPSTONE_SOLUTION.zh-TW.md`](./CAPSTONE_SOLUTION.zh-TW.md)。)*

## The feature

An existing customer shares a referral code. When a new customer signs up
using that code and places their first order, **both** the referrer and the
referee receive bonus points.

## 1. Where does the referral relationship live?

**Both a new field on `customers` and a new `referrals` collection** —
this is the same embed-vs-reference reasoning from Part 1, applied again:

- **`customers.referralCode`** (new field): a short, unique, indexed string
  each customer can share (e.g. `"JORDAN2K4"`). This is 1:1 with the
  customer, never changes, and is always read together with the profile —
  a clear **embed**.

- **`referrals` collection** (new collection): one document per
  referrer→referee relationship. A single customer can refer **many**
  people over **years** — that's the exact 1:many, unbounded-growth shape
  we already saw with `point_transactions` in Part 4.1. Embedding an
  array of referrals inside the referrer's customer document would
  recreate the **Unbounded Array anti-pattern** almost immediately (a
  popular referral code could generate hundreds of referrals). So:
  **reference**, in its own collection, not embedded.

```json
// referrals collection
{
  "_id": ObjectId("..."),
  "referralCode": "JORDAN2K4",
  "referrerId": ObjectId("..."),           // customer who shared the code
  "refereeId": ObjectId("..."),            // customer who signed up with it
  "referrerRef": { "name": "Jordan Lee", "tier": "Gold" },   // extended reference
  "refereeRef": { "name": "Alex Kim" },                      // extended reference
  "status": "completed",                   // "pending" until referee's first order
  "referrerBonusPoints": 100,
  "refereeBonusPoints": 50,
  "createdAt": ISODate("2024-03-01T00:00:00Z"),
  "completedAt": ISODate("2024-03-04T18:22:00Z")
}
```

```json
// customers collection (excerpt) — new fields in bold-equivalent
{
  "_id": ObjectId("..."),
  "name": "Jordan Lee",
  "tier": "Gold",
  "referralCode": "JORDAN2K4",
  "loyaltyStats": {
    "lifetimePoints": 4200,
    "currentBalance": 1850,
    "totalOrders": 37,
    "totalReferrals": 12,
    "referralBonusPoints": 1200,
    "lastComputedAt": ISODate("...")
  }
}
```

## 2. Which patterns apply, and why?

| Pattern | Applied where | Why |
|---|---|---|
| **Referencing** | `referrals` collection, referenced via `referrerId`/`refereeId` | 1:many, unbounded growth per referrer — same reasoning as `point_transactions` (Part 4.1). Embedding would eventually reproduce the unbounded array anti-pattern. |
| **Extended Reference** | `referrals.referrerRef` / `referrals.refereeRef` (name, tier snapshot) | An admin "referral activity" dashboard needs to list referrer/referee names without a `$lookup` per row — exactly the Part 2 problem, solved the same way. |
| **Computed** | `customers.loyaltyStats.totalReferrals` and `referralBonusPoints` | The customer profile screen needs "referrals made" and "points earned from referrals" on every load (just like `lifetimePoints` in Part 4.2) — precompute instead of aggregating `referrals` live every time. |
| **Inheritance (Polymorphic)** *(if the program evolves)* | A future `referral_campaigns` collection, if marketing launches multiple referral promos with different reward shapes (flat bonus vs. percentage vs. free item) | Same shape divergence problem as `rewards.type` in Part 4.5 — one collection, a `type` discriminator, type-specific nested object. |
| **Attribute** *(if needed)* | Campaign eligibility rules on `referral_campaigns` (e.g. "only for new customers in TX", "only during launch month") | Same sparse/optional criteria problem as `rewards.eligibility[]` in Part 4.3 — one generic `(k, v)` array + one index covers all current and future criteria. |

Note that **Outlier Pattern** isn't needed here: we already reference
`referrals` in its own collection from the start (we didn't make the
mistake of embedding first), so there's no "normal case vs. outlier case"
document shape problem to solve — the lesson from Part 4.1 was already
applied proactively.

## 3. Answering "how many referrals has customer X made, and how many bonus points has it earned?"

**Don't aggregate `referrals` on every request.** Apply the Computed
Pattern exactly as in Part 4.2: maintain the counters on the customer
document, updated incrementally at the moment a referral completes.

```python
def complete_referral(db, referral_id):
    """
    Called when a referee places their first order. Marks the referral
    completed and incrementally updates BOTH customers' precomputed stats
    in the same logical operation (wrap in a multi-document transaction
    in production for atomicity, same caveat as Part 4.2).
    """
    referral = db.referrals.find_one({"_id": referral_id})

    db.referrals.update_one(
        {"_id": referral_id},
        {"$set": {"status": "completed", "completedAt": datetime.now(timezone.utc)}},
    )

    # Referrer gets credit for a successful referral + their bonus points
    db.customers.update_one(
        {"_id": referral["referrerId"]},
        {"$inc": {
            "loyaltyStats.totalReferrals": 1,
            "loyaltyStats.referralBonusPoints": referral["referrerBonusPoints"],
            "loyaltyStats.lifetimePoints": referral["referrerBonusPoints"],
            "loyaltyStats.currentBalance": referral["referrerBonusPoints"],
        }},
    )

    # Referee gets their signup bonus too
    db.customers.update_one(
        {"_id": referral["refereeId"]},
        {"$inc": {
            "loyaltyStats.lifetimePoints": referral["refereeBonusPoints"],
            "loyaltyStats.currentBalance": referral["refereeBonusPoints"],
        }},
    )
```

Now the profile screen's "You've referred 12 friends and earned 1,200
bonus points!" banner is a single indexed document lookup:

```python
db.customers.find_one({"_id": customer_id}, {"loyaltyStats": 1})
```

— O(1) regardless of whether that customer has referred 2 people or 2,000.

For **admin reporting/reconciliation** (not a hot path, can tolerate
latency — same tradeoff discussed in Part 4.2), you'd still periodically
verify the computed counters against a live aggregation over `referrals`:

```python
db.referrals.aggregate([
    {"$match": {"referrerId": customer_id, "status": "completed"}},
    {"$group": {
        "_id": "$referrerId",
        "totalReferrals": {"$sum": 1},
        "referralBonusPoints": {"$sum": "$referrerBonusPoints"},
    }},
])
```

## New/changed indexes

```python
db.customers.create_index("referralCode", unique=True)
db.referrals.create_index("referrerId")
db.referrals.create_index("refereeId", unique=True)  # a referee can only be referred once
db.referrals.create_index([("status", 1), ("createdAt", -1)])  # for the admin "pending referrals" view
```
