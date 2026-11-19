"""A developer, standing in: given one ticket (ERGOSTAT_ITEM, under a lease), works it a few seconds and sends it
to review. Lines without an item are about the ticket."""
import json
import os
import random
import time

name = os.environ.get("ERGOSTAT_ITEM", "")
print(json.dumps({"event": "ticket.started"}), flush=True)
long = 9 if "integrate" in name or "build-api" in name else 4
time.sleep(random.uniform(2, long))
print(json.dumps({"event": "ticket.submitted", "data": {"commits": random.randint(1, 4)}}), flush=True)
