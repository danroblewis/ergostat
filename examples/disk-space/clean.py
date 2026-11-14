"""The disk cleaner: a simulated disk (sim.json) that the services fill a little at a time.
Measures usage, and over 80% deletes the oldest files down to 65%."""
import json
import random
from pathlib import Path

sim = Path(".sim.json")
used = json.loads(sim.read_text())["used"] if sim.exists() else 60.0
used += random.uniform(0.5, 2.5)            # the services wrote logs since the last look
print(json.dumps({"sensor": "disk-usage", "value": round(used, 1)}))
if used > 80:
    freed = round(used - 65, 1)
    used -= freed
    print(json.dumps({"controller": "disk-under-80", "decision": f"over 80: free {freed}%"}))
    print(json.dumps({"valve": "delete-old-files", "amount": freed}))
else:
    print(json.dumps({"controller": "disk-under-80", "decision": "under 80: nothing to do"}))
sim.write_text(json.dumps({"used": used}))
