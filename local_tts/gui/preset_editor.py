"""Preset editor — one preset at a time.

A preset is a voice configuration: name, provider, and the dynamic
provider-options form (built from `Provider.options_schema()`). It may
optionally override the global cleanup and regex rules; both sections
are gated by an "override" checkbox and are off by default.
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
        voice_defaults: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Preset · {preset.name}")
        self.resize(740, 640)
        self._addon = addon
        self._preset = preset
        self._is_new = is_new
        # Draft provider settings + voice defaults from the surrounding
        # Settings dialog so the voice picker / test / inherit hints
        # honour unsaved edits. Falls back to the live addon config.
        self._provider_settings = provider_settings if provider_settings is not None \
            else addon.config.provider_settings
        self._voice_defaults = voice_defaults if voice_defaults is not None \
            else dict(addon.config.voice_defaults)

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

    # ---- name + provider + provider options ----

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
            # Voice picker is choosing a concrete value — drop inherit.
            check = self._inherit_checks.get(key)
            if check is not None:
                check.setChecked(False)
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

    def _build_cleanup_box(self) -> QWidget:
        box = QGroupBox("Cleanup")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(6)

        self._cleanup_override = QCheckBox("Override global cleanup for this preset")
        self._cleanup_override.toggled.connect(self._on_cleanup_override_toggled)
        outer.addWidget(self._cleanup_override)

        form_wrap = QWidget()
        form = QFormLayout(form_wrap)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(6)

        effective = self._preset.cleanup or self._addon.config.cleanup

        self._ruby_mode = QComboBox()
        for v, label in _RUBY_MODES:
            self._ruby_mode.addItem(label, v)
        self._ruby_mode.setCurrentIndex(max(0, self._ruby_mode.findData(effective.ruby_mode)))
        form.addRow("Ruby tags", self._ruby_mode)

        self._bracket_mode = QComboBox()
        for v, label in _BRACKET_MODES:
            self._bracket_mode.addItem(label, v)
        self._bracket_mode.setCurrentIndex(max(0, self._bracket_mode.findData(effective.bracket_mode)))
        form.addRow("Bracket readings", self._bracket_mode)

        self._brackets = QLineEdit(", ".join(effective.brackets))
        self._brackets.setPlaceholderText("[], (), {}")
        form.addRow("Bracket pairs", self._brackets)

        self._collapse_cjk = QCheckBox("Collapse spaces between Japanese characters")
        self._collapse_cjk.setChecked(effective.collapse_cjk_spaces)
        form.addRow("", self._collapse_cjk)

        outer.addWidget(form_wrap)
        self._cleanup_form_wrap = form_wrap

        self._cleanup_override.setChecked(self._preset.cleanup is not None)
        self._on_cleanup_override_toggled(self._cleanup_override.isChecked())
        return box

    def _on_cleanup_override_toggled(self, on: bool) -> None:
        self._cleanup_form_wrap.setEnabled(on)

    def _rebuild_provider_options(self, provider_name: str) -> None:
        while self._options_form.rowCount():
            self._options_form.removeRow(0)
        self._option_widgets.clear()
        self._inherit_checks: dict[str, QCheckBox] = {}

        provider = self._addon.providers.get(provider_name)
        if provider is None:
            self._options_form.addRow(QLabel(f"Unknown provider {provider_name!r}"))
            return

        schema = provider.options_schema()
        current = self._preset.options if provider_name == self._preset.provider else {}
        for key, spec in schema.items():
            stored = current.get(key)
            inherit_default = self._voice_defaults.get(key)
            inherits = key in self._voice_defaults
            initial = stored if stored is not None else (
                inherit_default if inherits else spec.get("default")
            )
            widget = self._make_option_widget(spec, initial)
            self._option_widgets[key] = widget
            if inherits:
                row = self._make_inherit_row(key, widget, inherit_default,
                                              stored_is_present=(key in current and stored is not None))
                self._options_form.addRow(key, row)
            else:
                self._options_form.addRow(key, widget)

    def _make_inherit_row(self, key: str, widget: QWidget, global_value: Any,
                          *, stored_is_present: bool) -> QWidget:
        """Wrap an inheritable option's widget with an 'Use global (X)' check."""
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        check = QCheckBox(f"Use global ({global_value})")
        check.setChecked(not stored_is_present)

        def apply(on: bool) -> None:
            widget.setEnabled(not on)
        check.toggled.connect(apply)
        apply(check.isChecked())
        row.addWidget(widget, 1)
        row.addWidget(check)
        self._inherit_checks[key] = check
        return wrap

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

    # ---- regex rules ----

    def _build_regex_group(self) -> QWidget:
        box = QGroupBox("Regex rules")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._regex_override = QCheckBox(
            "Override global regex rules for this preset (replaces the global list)"
        )
        self._regex_override.toggled.connect(self._on_regex_override_toggled)
        layout.addWidget(self._regex_override)

        self._rules_table = QTableWidget(0, 3)
        self._rules_table.setHorizontalHeaderLabels(["On", "Pattern", "Replacement"])
        header = self._rules_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._rules_table.verticalHeader().setVisible(False)
        self._rules_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        seed = self._preset.regex_rules if self._preset.regex_rules is not None \
            else self._addon.config.regex_rules
        for rule in seed:
            self._append_rule_row(rule)

        self._status = QLabel("")
        self._status.setStyleSheet("color: gray;")
        self._status.setWordWrap(True)

        self._regex_add = QPushButton("Add")
        self._regex_add.clicked.connect(lambda: self._append_rule_row(RegexRule(pattern="", replacement="")))
        self._regex_del = QPushButton("Remove")
        self._regex_del.clicked.connect(self._remove_selected_rules)
        self._regex_validate = QPushButton("Validate")
        self._regex_validate.clicked.connect(self._validate_rules)

        btns = QHBoxLayout()
        btns.addWidget(self._regex_add)
        btns.addWidget(self._regex_del)
        btns.addStretch(1)
        btns.addWidget(self._regex_validate)

        layout.addWidget(self._rules_table, 1)
        layout.addLayout(btns)
        layout.addWidget(self._status)

        self._regex_override.setChecked(self._preset.regex_rules is not None)
        self._on_regex_override_toggled(self._regex_override.isChecked())
        return box

    def _on_regex_override_toggled(self, on: bool) -> None:
        self._rules_table.setEnabled(on)
        self._regex_add.setEnabled(on)
        self._regex_del.setEnabled(on)
        self._regex_validate.setEnabled(on)

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

    def _collect_provider_options(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, widget in self._option_widgets.items():
            check = self._inherit_checks.get(key)
            if check is not None and check.isChecked():
                # Key omitted from preset.options → inherits global default.
                continue
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
        self._preset.name = name
        self._preset.provider = self._provider.currentText()
        self._preset.options = self._collect_provider_options()
        if self._cleanup_override.isChecked():
            brackets = [b.strip() for b in self._brackets.text().split(",") if b.strip()]
            self._preset.cleanup = CleanupOptions(
                ruby_mode=self._ruby_mode.currentData(),
                bracket_mode=self._bracket_mode.currentData(),
                brackets=brackets or ["[]", "()"],
                collapse_cjk_spaces=self._collapse_cjk.isChecked(),
            )
        else:
            self._preset.cleanup = None
        if self._regex_override.isChecked():
            self._preset.regex_rules = self._collect_rules()
        else:
            self._preset.regex_rules = None
        self.accept()


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
