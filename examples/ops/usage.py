"""The sensor: how full the disk is, in %. It only reads."""
from sim import world

with world() as w:
    print(round(w["used"], 1))
