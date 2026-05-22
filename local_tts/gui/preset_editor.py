"""Preset editor — one preset at a time.

Form sections: name + provider, dynamic provider-options form (built from
`Provider.options_schema()`), cleanup flags, and the regex rules table.
The regex section gets the lion's share of vertical space and has its
own Validate button that surfaces re.compile errors inline.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    Qt,
)

from ..presets import CleanupOptions, Preset, RegexRule
from ..providers.base import ProviderError
from ..text.regex_rules import validate_pattern

if TYPE_CHECKING:
    from ..addon import LocalTTSAddon


_RUBY_MODES = [("base", "Base character (本)"), ("reading", "Reading (ほん)")]
_BRACKET_MODES = [
    ("base", "Base before bracket (日々)"),
    ("reading", "Reading inside bracket (ひび)"),
    ("strip_brackets_only", "Keep both"),
]


class PresetEditorDialog(QDialog):
    def __init__(
        self,
        addon: LocalTTSAddon,
        preset: Preset,
        parent: QWidget | None = None,
        *,
        is_new: bool = False,
        provider_settings: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Preset · {preset.name}")
        self.resize(740, 640)
        self._addon = addon
        self._preset = preset
        self._is_new = is_new
        # Draft provider settings from the surrounding Settings dialog,
        # so the voice picker / test honour unsaved edits. Falls back to
        # the live addon config if the dialog wasn't opened from Settings.
        self._provider_settings = provider_settings if provider_settings is not None \
            else addon.config.provider_settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        layout.addWidget(self._build_header())

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_top())
        splitter.addWidget(self._build_regex_group())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---- top: name + provider + provider options + cleanup ----

    def _build_header(self) -> QWidget:
        wrap = QWidget()
        form = QFormLayout(wrap)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

        self._name = QLineEdit(self._preset.name)
        form.addRow("Name", self._name)

        self._provider = QComboBox()
        for name in self._addon.providers.names():
            self._provider.addItem(name)
        idx = self._provider.findText(self._preset.provider)
        if idx >= 0:
            self._provider.setCurrentIndex(idx)
        self._provider.currentTextChanged.connect(self._rebuild_provider_options)
        form.addRow("Provider", self._provider)

        if self._is_new:
            pick = QPushButton("Pick voice from server…")
            pick.setToolTip("Requires the provider's service to be running. "
                            "Voices are fetched live and not cached.")
            pick.clicked.connect(self._pick_voice)
            form.addRow("", pick)
        return wrap

    def _pick_voice(self) -> None:
        provider = self._addon.providers.get(self._provider.currentText())
        if provider is None:
            return
        provider_settings = self._provider_settings.get(provider.name, {})
        dlg = VoicePickerDialog(self._addon, provider, provider_settings, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.selected is None:
            return
        voice = dlg.selected
        for key, value in voice.options.items():
            widget = self._option_widgets.get(key)
            if isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))
        lang = getattr(provider, "display_language", "")
        disp = getattr(provider, "display_name", provider.name)
        full_name = " ".join(part for part in (lang, disp, voice.label) if part)
        self._name.setText(full_name)
        self.setWindowTitle(f"Preset · {full_name}")

    def _build_top(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._options_box = QGroupBox("Provider options")
        self._options_form = QFormLayout(self._options_box)
        self._options_form.setHorizontalSpacing(16)
        self._options_form.setVerticalSpacing(6)
        self._option_widgets: dict[str, QWidget] = {}
        self._rebuild_provider_options(self._provider.currentText())
        layout.addWidget(self._options_box)

        layout.addWidget(self._build_cleanup_box())
        return wrap

    def _rebuild_provider_options(self, provider_name: str) -> None:
        while self._options_form.rowCount():
            self._options_form.removeRow(0)
        self._option_widgets.clear()

        provider = self._addon.providers.get(provider_name)
        if provider is None:
            self._options_form.addRow(QLabel(f"Unknown provider {provider_name!r}"))
            return

        schema = provider.options_schema()
        current = self._preset.options if provider_name == self._preset.provider else {}
        for key, spec in schema.items():
            widget = self._make_option_widget(spec, current.get(key, spec.get("default")))
            self._option_widgets[key] = widget
            self._options_form.addRow(key, widget)

    def _make_option_widget(self, spec: dict[str, Any], value: Any) -> QWidget:
        t = spec.get("type", "string")
        if t == "integer":
            w = QSpinBox()
            w.setRange(int(spec.get("min", -2**31)), int(spec.get("max", 2**31 - 1)))
            w.setValue(int(value if value is not None else spec.get("default", 0)))
            return w
        if t == "number":
            w = QDoubleSpinBox()
            w.setDecimals(2)
            w.setSingleStep(0.05)
            w.setRange(float(spec.get("min", -1e6)), float(spec.get("max", 1e6)))
            w.setValue(float(value if value is not None else spec.get("default", 0.0)))
            return w
        if t == "boolean":
            w = QCheckBox()
            w.setChecked(bool(value if value is not None else spec.get("default", False)))
            return w
        le = QLineEdit(str(value if value is not None else spec.get("default", "")))
        return le

    def _build_cleanup_box(self) -> QWidget:
        box = QGroupBox("Cleanup")
        form = QFormLayout(box)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(6)

        self._ruby_mode = QComboBox()
        for v, label in _RUBY_MODES:
            self._ruby_mode.addItem(label, v)
        self._ruby_mode.setCurrentIndex(
            max(0, self._ruby_mode.findData(self._preset.cleanup.ruby_mode))
        )
        form.addRow("Ruby tags", self._ruby_mode)

        self._bracket_mode = QComboBox()
        for v, label in _BRACKET_MODES:
            self._bracket_mode.addItem(label, v)
        self._bracket_mode.setCurrentIndex(
            max(0, self._bracket_mode.findData(self._preset.cleanup.bracket_mode))
        )
        form.addRow("Bracket readings", self._bracket_mode)

        self._brackets = QLineEdit(", ".join(self._preset.cleanup.brackets))
        self._brackets.setPlaceholderText("[], (), {}")
        form.addRow("Bracket pairs", self._brackets)

        self._collapse_cjk = QCheckBox("Collapse spaces between Japanese characters")
        self._collapse_cjk.setChecked(self._preset.cleanup.collapse_cjk_spaces)
        form.addRow("", self._collapse_cjk)
        return box

    # ---- regex rules ----

    def _build_regex_group(self) -> QWidget:
        box = QGroupBox("Regex rules — applied in order after cleanup")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._rules_table = QTableWidget(0, 3)
        self._rules_table.setHorizontalHeaderLabels(["On", "Pattern", "Replacement"])
        header = self._rules_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._rules_table.verticalHeader().setVisible(False)
        self._rules_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        for rule in self._preset.regex_rules:
            self._append_rule_row(rule)

        self._status = QLabel("")
        self._status.setStyleSheet("color: gray;")
        self._status.setWordWrap(True)

        btns = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(lambda: self._append_rule_row(RegexRule(pattern="", replacement="")))
        del_btn = QPushButton("Remove")
        del_btn.clicked.connect(self._remove_selected_rules)
        validate_btn = QPushButton("Validate")
        validate_btn.clicked.connect(self._validate_rules)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        btns.addStretch(1)
        btns.addWidget(validate_btn)

        layout.addWidget(self._rules_table, 1)
        layout.addLayout(btns)
        layout.addWidget(_separator())
        layout.addWidget(self._status)
        return box

    def _append_rule_row(self, rule: RegexRule) -> None:
        row = self._rules_table.rowCount()
        self._rules_table.insertRow(row)
        check = QCheckBox()
        check.setChecked(rule.enabled)
        wrapper = QWidget()
        hl = QHBoxLayout(wrapper)
        hl.setContentsMargins(6, 0, 0, 0)
        hl.addWidget(check)
        hl.addStretch(1)
        self._rules_table.setCellWidget(row, 0, wrapper)
        wrapper.setProperty("checkbox", check)
        self._rules_table.setItem(row, 1, QTableWidgetItem(rule.pattern))
        self._rules_table.setItem(row, 2, QTableWidgetItem(rule.replacement))

    def _remove_selected_rules(self) -> None:
        rows = sorted({i.row() for i in self._rules_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._rules_table.removeRow(row)

    def _collect_rules(self) -> list[RegexRule]:
        rules: list[RegexRule] = []
        for row in range(self._rules_table.rowCount()):
            wrapper = self._rules_table.cellWidget(row, 0)
            check = wrapper.property("checkbox") if wrapper else None
            enabled = bool(check.isChecked()) if isinstance(check, QCheckBox) else True
            pattern_item = self._rules_table.item(row, 1)
            replacement_item = self._rules_table.item(row, 2)
            pattern = pattern_item.text() if pattern_item else ""
            replacement = replacement_item.text() if replacement_item else ""
            if not pattern:
                continue
            rules.append(RegexRule(pattern=pattern, replacement=replacement, enabled=enabled))
        return rules

    def _validate_rules(self) -> None:
        broken: list[tuple[int, str, str]] = []
        for row in range(self._rules_table.rowCount()):
            item = self._rules_table.item(row, 1)
            pattern = item.text() if item else ""
            if not pattern:
                continue
            err = validate_pattern(pattern)
            if err:
                broken.append((row + 1, pattern, err))
        if not broken:
            self._status.setText(f"All {self._rules_table.rowCount()} pattern(s) compile.")
            self._status.setStyleSheet("color: #2e7d32;")
            return
        lines = [f"Row {row}: {pat!r} — {err}" for row, pat, err in broken]
        self._status.setText("\n".join(lines))
        self._status.setStyleSheet("color: #c62828;")

    # ---- save ----

    def _collect_provider_options(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, widget in self._option_widgets.items():
            if isinstance(widget, QSpinBox):
                out[key] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                out[key] = widget.value()
            elif isinstance(widget, QCheckBox):
                out[key] = widget.isChecked()
            elif isinstance(widget, QLineEdit):
                out[key] = widget.text()
        return out

    def _on_accept(self) -> None:
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Local TTS", "Preset name is required.")
            return
        brackets = [b.strip() for b in self._brackets.text().split(",") if b.strip()]
        self._preset.name = name
        self._preset.provider = self._provider.currentText()
        self._preset.options = self._collect_provider_options()
        self._preset.cleanup = CleanupOptions(
            ruby_mode=self._ruby_mode.currentData(),
            bracket_mode=self._bracket_mode.currentData(),
            brackets=brackets or ["[]", "()"],
            collapse_cjk_spaces=self._collapse_cjk.isChecked(),
        )
        self._preset.regex_rules = self._collect_rules()
        self.accept()


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


DEFAULT_TEST_TEXT = "こんにちは、今日からよろしくお願いします。"


class VoicePickerDialog(QDialog):
    """Live voice picker — fetches each time, never caches.

    Requires the provider's service to be reachable. If the connection
    fails the status label shows the friendly error from the provider.
    Has a test box: pick a voice, edit the sample text, hit Test to hear it.
    """

    def __init__(self, addon, provider, provider_settings: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Voices · {provider.name}")
        self.resize(480, 600)
        self._addon = addon
        self._provider = provider
        self._provider_settings = dict(provider_settings)
        self.selected = None  # type: ignore[assignment]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        hint = QLabel(
            "Live request — the provider's service must be running. "
            "Results are not cached; you will fetch again next time."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

        from aqt.qt import QListWidget, QListWidgetItem, QSizePolicy
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _: self._accept_selected())
        layout.addWidget(self._list, 1)

        test_box = QGroupBox("Test selected voice")
        test_layout = QVBoxLayout(test_box)
        test_layout.setContentsMargins(10, 10, 10, 10)
        test_layout.setSpacing(6)
        self._test_text = QLineEdit(DEFAULT_TEST_TEXT)
        self._test_text.setPlaceholderText("Text to synthesize…")
        self._test_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        test_row = QHBoxLayout()
        test_btn = QPushButton("Play")
        test_btn.clicked.connect(self._play_test)
        test_row.addWidget(self._test_text, 1)
        test_row.addWidget(test_btn)
        test_layout.addLayout(test_row)
        layout.addWidget(test_box)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        row = QHBoxLayout()
        fetch = QPushButton("Fetch")
        fetch.clicked.connect(self._fetch)
        select = QPushButton("Select")
        select.clicked.connect(self._accept_selected)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(fetch)
        row.addStretch(1)
        row.addWidget(select)
        row.addWidget(cancel)
        layout.addLayout(row)

        self._fetch()

    def _fetch(self) -> None:
        self._list.clear()
        self._status.setText("Fetching…")
        self._status.setStyleSheet("color: gray;")
        QApplication_processEvents()
        try:
            voices = self._provider.voices(self._provider_settings)
        except ProviderError as exc:
            self._status.setText(str(exc))
            self._status.setStyleSheet("color: #c62828;")
            return
        except Exception as exc:
            self._status.setText(f"Error: {exc}")
            self._status.setStyleSheet("color: #c62828;")
            return
        if not voices:
            self._status.setText("Provider returned no voices.")
            self._status.setStyleSheet("color: gray;")
            return
        from aqt.qt import QListWidgetItem
        for v in voices:
            item = QListWidgetItem(v.label)
            item.setData(Qt.ItemDataRole.UserRole, v)
            self._list.addItem(item)
        self._status.setText(f"{len(voices)} voice(s) loaded.")
        self._status.setStyleSheet("color: #2e7d32;")

    def _accept_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        self.selected = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _play_test(self) -> None:
        item = self._list.currentItem()
        if item is None:
            self._status.setText("Pick a voice first.")
            self._status.setStyleSheet("color: gray;")
            return
        voice = item.data(Qt.ItemDataRole.UserRole)
        text = self._test_text.text().strip()
        if not text:
            self._status.setText("Type something to test.")
            self._status.setStyleSheet("color: gray;")
            return

        temp_preset = Preset(name=f"test:{voice.label}", provider=self._provider.name,
                             options=dict(voice.options))

        self._status.setText(f"Synthesizing with {voice.label}…")
        self._status.setStyleSheet("color: gray;")
        QApplication_processEvents()

        try:
            wav = self._provider.synthesize(text, temp_preset, self._provider_settings)
        except ProviderError as exc:
            self._status.setText(str(exc))
            self._status.setStyleSheet("color: #c62828;")
            return
        except Exception as exc:
            self._status.setText(f"Error: {exc}")
            self._status.setStyleSheet("color: #c62828;")
            return

        key = self._addon.cache.key(temp_preset, text)
        path = self._addon.cache.get(key) or self._addon.cache.put(key, wav)
        try:
            from aqt.sound import av_player
            av_player.insert_file(str(path))
            self._status.setText(f"Playing {voice.label}.")
            self._status.setStyleSheet("color: #2e7d32;")
        except Exception as exc:
            self._status.setText(f"Playback failed: {exc}")
            self._status.setStyleSheet("color: #c62828;")


def QApplication_processEvents() -> None:
    """Pump events so the 'Fetching…' status renders before the blocking
    network call. Intentionally a no-op outside Qt."""
    try:
        from aqt.qt import QApplication
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
    except Exception:
        pass
