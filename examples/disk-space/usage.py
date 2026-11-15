"""The sensor: how full the disk is, in %. It only reads."""
from sim import used

print(round(used(), 1))
