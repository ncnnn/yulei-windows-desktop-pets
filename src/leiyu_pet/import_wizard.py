"""首次启动素材导入向导。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .asset_importer import AssetImportError, active_asset_root, import_asset_pack
from .paths import assets_store_dir


class ImportWizard(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.pack = None
        self.setWindowTitle("导入原项目素材")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        self._status = QLabel(
            "未检测到素材，请选择原项目的 Assets 文件夹或 ZIP 包进行导入。"
        )
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        folder_btn = QPushButton("选择文件夹")
        folder_btn.clicked.connect(self._choose_folder)
        layout.addWidget(folder_btn)

        zip_btn = QPushButton("选择 ZIP")
        zip_btn.clicked.connect(self._choose_zip)
        layout.addWidget(zip_btn)

        later_btn = QPushButton("稍后再说")
        later_btn.clicked.connect(self.reject)
        layout.addWidget(later_btn)

    @classmethod
    def should_show(cls) -> bool:
        return active_asset_root(assets_store_dir()) is None

    def _choose_folder(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        source = QFileDialog.getExistingDirectory(self, "选择 Assets 文件夹")
        if source:
            self._import(Path(source))

    def _choose_zip(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        source, _ = QFileDialog.getOpenFileName(
            self, "选择素材 ZIP", "", "素材 ZIP (*.zip)"
        )
        if source:
            self._import(Path(source))

    def _import(self, source: Path) -> None:
        try:
            self.pack = import_asset_pack(source, assets_store_dir())
        except AssetImportError as exc:
            self._status.setText(f"导入失败：{exc}")
            QMessageBox.warning(self, "导入失败", f"导入失败：{exc}")
            return
        self.accept()
