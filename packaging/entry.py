"""PyInstaller 入口脚本（隐藏控制台，交给 ``leiyu_pet.__main__``）。"""

from __future__ import annotations

from leiyu_pet.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
