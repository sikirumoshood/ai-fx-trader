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
else:
    print("Failed to connect")
    req = pathlib.Path(path) / "aifx_req.txt"
    res = pathlib.Path(path) / "aifx_res.txt"
    print("req file stuck:", req.exists())
    print("res file exists:", res.exists())
