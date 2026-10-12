import json, os, time, requests
from pathlib import Path

# ---- settings ----
URL = "https://api.stackexchange.com/2.3/users"
KEY = os.environ["SE_KEY"]                      # authentication: key from an environment variable
SITE = "datascience"
FOLDER = Path("data/raw/users")
FOLDER.mkdir(parents=True, exist_ok=True)
MAX_PAGES = 3000                                # safety limit against an endless loop


def get_page(params, tries=4):
    """One API call. Retries temporary failures, stops on permanent ones."""
    for attempt in range(tries):
        try:
            r = requests.get(URL, params=params, timeout=30)     # timeout: never hang forever
            if r.status_code >= 500 or r.status_code == 429:     # server trouble / too many requests
                raise RuntimeError(f"HTTP {r.status_code}")
            data = r.json()                                      # bad JSON raises ValueError
        except (requests.exceptions.RequestException, RuntimeError, ValueError) as e:
            wait = 2 ** attempt                                  # exponential backoff: 1, 2, 4, 8 s
            print(f"  attempt {attempt + 1} failed ({e}), waiting {wait}s")
            time.sleep(wait)
            continue
        if "error_id" in data:                                   # API-level error: do not retry
            raise SystemExit(f"API error: {data}")
        return data
    raise SystemExit("giving up after retries")


params = {"site": SITE, "key": KEY, "pagesize": 100,
          "sort": "creation", "order": "asc"}       # stable order: new users append at the end
seen_ids = set()                                    # unique user_ids, for the final count
page = 1

while page <= MAX_PAGES:
    params["page"] = page                           # pagination: only the page number changes
    data = get_page(params)

    # save the raw response exactly as received (same page = same file, so reruns overwrite)
    (FOLDER / f"users_{page:05d}.json").write_text(json.dumps(data))

    seen_ids.update(u["user_id"] for u in data["items"])
    print(f"page {page}: {len(seen_ids)} unique users, quota left {data['quota_remaining']}")

    if not data["has_more"]:                        # the API tells us when to stop
        break
    time.sleep(data.get("backoff", 0) + 0.3)        # rate limiting: obey backoff, plus a small pause
    page += 1
else:
    print("WARNING: hit MAX_PAGES, data may be incomplete")

# validation: compare our unique count with the API's own total
total = requests.get(URL, params={"site": SITE, "key": KEY, "filter": "total"},
                     timeout=30).json().get("total")
print(f"Done. Unique users saved: {len(seen_ids)} | API total: {total}")