"""A reviewer, standing in: approves the ticket after a moment."""
import json
import random
import time

time.sleep(random.uniform(1, 3))
print(json.dumps({"event": "ticket.approved"}), flush=True)
