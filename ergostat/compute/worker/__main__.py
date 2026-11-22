"""``python3 -I PATH/worker --stdio``, or a zipapp of this folder (``ergostat worker --pack FILE``): a compute node's
worker, standard library only, needing no ergostat on the node (SPEC §12s). Its modules import each other by bare
name; this folder (or the zipapp) is put first on the path if Python has not put it there, which is how
``ergostat worker --stdio`` loads it by path. No bytecode is written: the worker writes nothing outside its root."""

import os
import sys

sys.dont_write_bytecode = True
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import serve  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    return serve.main(argv)


if __name__ == "__main__":
    sys.exit(main())
