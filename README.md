# MongoDB Schema Design Workshop: KFC Loyalty Platform

A hands-on Jupyter notebook workshop teaching MongoDB schema design through a
realistic use case: a fast-food loyalty platform (customers, orders, point
transactions, rewards).

**Available in two languages** — pick whichever notebook/solution pair you
prefer; both cover identical content and run against the same `workshop_utils.py`:

| Language | Notebook | Capstone Solution |
|---|---|---|
| English | `notebook/kfc_loyalty_schema_workshop.ipynb` | `CAPSTONE_SOLUTION.md` |
| 繁體中文 (Traditional Chinese) | `notebook/kfc_loyalty_schema_workshop.zh-TW.ipynb` | `CAPSTONE_SOLUTION.zh-TW.md` |

By the end of the workshop you'll be able to:

1. Decide between **embedding** and **referencing**, and apply the
   **Extended Reference Pattern** to avoid expensive joins.
2. Design a loyalty platform schema step-by-step from real access patterns.
3. Recognize and apply the **Computed**, **Attribute**, **Outlier**, and
   **Inheritance (Polymorphic)** patterns — and recognize the **Unbounded
   Array anti-pattern** before it causes production problems.

## Architecture

All attendees connect to **one shared MongoDB Atlas cluster**, but each
attendee works in **their own database** on that cluster (so up to ~20
people can run the workshop concurrently without colliding). This is
controlled entirely by two values in your local `.env` file:

- `MONGODB_URI` — shared cluster connection string (same for everyone)
- `DB_NAME` — unique per attendee (e.g. `kfc_loyalty_niko`)

---

## For the Organizer: Provisioning the Shared Cluster

1. Create a free/shared-tier cluster on [MongoDB Atlas](https://www.mongodb.com/atlas).
2. **Database Access** → add a database user (e.g. `workshop_user`) with
   `readWriteAnyDatabase` on the cluster, so every attendee's own database
   works without per-attendee provisioning.
3. **Network Access** → add `0.0.0.0/0` for the duration of the workshop
   (simplest for a short-lived event; remove afterward), or pre-collect
   attendee IPs if you prefer tighter control.
4. Copy the connection string (**Connect → Drivers → Python**), e.g.:
   ```
   mongodb+srv://workshop_user:<password>@kfc-loyalty-cluster.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
5. Distribute this connection string to attendees (e.g. via chat/slide) —
   this is the `MONGODB_URI` they'll each put in their own `.env`.
6. Tell attendees to each pick a **unique** `DB_NAME` (first name is usually
   enough) to avoid colliding with each other on the shared cluster.

## For Attendees: Setup

1. **Clone/download this repo** and open a terminal in its root folder.

2. **Create a virtual environment and install dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure your `.env`:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env`:
   ```
   MONGODB_URI=<connection string from your organizer>
   DB_NAME=kfc_loyalty_<yourname>
   ```
   ⚠️ Make sure `DB_NAME` is unique to you — this is your own private
   workspace on the shared cluster.

4. **Launch Jupyter** (pick the English or 繁體中文 notebook):
   ```bash
   jupyter notebook notebook/kfc_loyalty_schema_workshop.ipynb
   # or, for Traditional Chinese:
   jupyter notebook notebook/kfc_loyalty_schema_workshop.zh-TW.ipynb
   ```

5. Run the first setup cell in the notebook — it will connect to Atlas and
   confirm which database you're using. If you see a TLS/SSL error, make
   sure `certifi` installed correctly (`pip show certifi`); the notebook's
   connection helper (`workshop_utils.get_db`) explicitly uses certifi's CA
   bundle to avoid this.

6. Follow the notebook top to bottom. Each pattern section includes a short
   exercise — try it yourself before expanding the solution.

7. The capstone exercise at the end has its own written solution in
   [`CAPSTONE_SOLUTION.md`](./CAPSTONE_SOLUTION.md) (or
   [`CAPSTONE_SOLUTION.zh-TW.md`](./CAPSTONE_SOLUTION.zh-TW.md) for the
   Chinese notebook) — try the exercise in the notebook first, then read
   the solution doc.

## Repo Structure

```
.
├── README.md                                    # This file
├── CAPSTONE_SOLUTION.md                         # Written solution for the final capstone exercise (English)
├── CAPSTONE_SOLUTION.zh-TW.md                   # Written solution (繁體中文)
├── requirements.txt                             # Python dependencies
├── .env.example                                 # Template for your local .env
├── workshop_utils.py                            # Shared helpers (DB connection, data generators, explain() summaries)
└── notebook/
    ├── kfc_loyalty_schema_workshop.ipynb        # The workshop notebook (English)
    └── kfc_loyalty_schema_workshop.zh-TW.ipynb  # The workshop notebook (繁體中文)
```

## Troubleshooting

- **`ConfigurationError: MONGODB_URI not found`** — you haven't created
  `.env` from `.env.example`, or it's not in the repo root.
- **`DB_NAME not set to a unique value`** — edit `.env` and replace the
  placeholder with your own unique name.
- **SSL / certificate verify failed** — ensure `certifi` is installed
  (`pip install -r requirements.txt` again); `get_db()` already passes
  `tlsCAFile=certifi.where()` to the Mongo client.
- **Authentication failed** — double-check you copied the full
  `MONGODB_URI` including the password, and that there are no extra quotes
  or spaces in `.env`.
