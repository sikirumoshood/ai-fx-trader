import os
import pathlib
from data.mt5_bridge import MT5Bridge
from config.settings import MT5_BRIDGE_FILES

path = os.path.expanduser(MT5_BRIDGE_FILES)
print("Bridge folder:", path)
print("Folder exists:", os.path.exists(path))

b = MT5Bridge(files_path=path)
if b.connect():
    print("Connected!")
    acc = b.account_info()
    print("Balance:", acc.balance)

    print("\n--- Open positions ---")
    positions = b.positions_get()
    if positions:
        for p in positions:
            print(f"  ticket={p.ticket} symbol={p.symbol} type={p.type} vol={p.volume} profit={p.profit}")
    else:
        print("  (none)")

    print("\n--- Pending orders ---")
    orders = b.orders_get()
    if orders:
        for o in orders:
            print(f"  ticket={o.ticket} symbol={o.symbol} type={o.type} vol={o.volume_initial} price={o.price_open}")
    else:
        print("  (none)")
else:
    print("Failed to connect")
    req = pathlib.Path(path) / "aifx_req.txt"
    res = pathlib.Path(path) / "aifx_res.txt"
    print("req file stuck:", req.exists())
    print("res file exists:", res.exists())
