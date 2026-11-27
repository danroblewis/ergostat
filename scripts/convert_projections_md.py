#!/usr/bin/env python3
"""The YAML blocks of Markdown files rewritten to the projection workbench's syntax (scripts/convert_projections.py);
a one-off. ``python3 scripts/convert_projections_md.py FILE.md...``"""

import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from convert_projections import convert_string  # noqa: E402

BLOCK = re.compile(r"(```ya?ml\n)(.*?)(```)", re.S)


def main():
    for p in sys.argv[1:]:
        text = open(p).read()
        n = [0, 0]

        def sub(m):
            got = convert_string(m.group(2))
            if got is None:
                if re.search(r"^\s*(match|states|otherwise):", m.group(2), re.M):
                    n[1] += 1
                return m.group(0)
            n[0] += 1
            return m.group(1) + got + ("" if got.endswith("\n") else "\n") + m.group(3)

        new = BLOCK.sub(sub, text)
        if new != text:
            open(p, "w").write(new)
        if n[0] or n[1]:
            print(f"{p}: {n[0]} rewritten" + (f", {n[1]} NOT (by hand)" if n[1] else ""))


if __name__ == "__main__":
    main()
