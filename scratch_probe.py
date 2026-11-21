import sys
import tempfile
from pathlib import Path

from ergostat.spec import read

sys.path.insert(0, "tests")
from test_slowjudge import SLOW  # noqa: E402

d = Path(tempfile.mkdtemp(dir="/work/.probe"))
for name, text in {"plain": SLOW.format(k=0.05),
                   "done": SLOW.format(k=0.05).replace("    from: queue\n", "    from: queue\n    to: done\n", 1)
                   .replace("flows:", "  done:\n    unit: jobs\nflows:", 1)}.items():
    (d / f"{name}.yaml").write_text(text)
    _, pr = read(d / f"{name}.yaml")
    print(name, [(x.level, x.code, x.about) for x in pr])
