"""Top-level Settings dialog.

Three tabs: General (toggles + cache + ffmpeg), Presets (CRUD via modal),
Routing (deck/notetype/language -> preset tables). OK saves the config
to disk and asks the addon to rebuild its Config/Router/Cache so the
next playback picks up changes without an Anki restart.
"""
from __future__ import annotations

import copy
import shutil
from typing import Any, TYPE_CHECKING

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    Qt,
)

from ..presets import CleanupOptions, Preset, RegexRule
from ..text.regex_rules import validate_pattern
from .preset_editor import PresetEditorDialog

if TYPE_CHECKING:
    from ..addon import LocalTTSAddon


def open_settings(addon: LocalTTSAddon) -> None:
    from aqt import mw
    dlg = SettingsDialog(addon, mw)
    dlg.exec()


class SettingsDialog(QDialog):
    def __init__(self, addon: LocalTTSAddon, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Local TTS")
        self.resize(720, 560)
        self._addon = addon
        self._cfg = copy.deepcopy(addon.config)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_general_tab(), "General")
        tabs.addTab(self._build_providers_tab(), "Providers")
        tabs.addTab(self._build_presets_tab(), "Presets")
        tabs.addTab(self._build_rules_tab(), "Rules")
        tabs.addTab(self._build_routing_tab(), "Routing")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # ---------------- General ----------------

    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(16, 16, 16, 16)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        self._enabled = QCheckBox("Enable Local TTS")
        self._enabled.setChecked(self._cfg.enabled)
        form.addRow(self._enabled)

        self._default_preset = QComboBox()
        self._default_preset.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._refresh_preset_combo(self._default_preset, self._cfg.default_preset)
        form.addRow("Default preset", self._default_preset)

        ff_wrapper = QWidget()
        ff_row = QHBoxLayout(ff_wrapper)
        ff_row.setContentsMargins(0, 0, 0, 0)
        self._ffmpeg = QLineEdit(self._cfg.ffmpeg_path or "")
        self._ffmpeg.setPlaceholderText("auto-detect — leave blank to probe PATH and common locations")
        self._ffmpeg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_ffmpeg)
        ff_row.addWidget(self._ffmpeg, 1)
        ff_row.addWidget(browse)
        form.addRow("ffmpeg path", ff_wrapper)

        self._cache_max = QSpinBox()
        self._cache_max.setRange(16, 65536)
        self._cache_max.setSuffix(" MB")
        self._cache_max.setValue(self._cfg.cache_max_mb)
        form.addRow("Cache size limit", self._cache_max)

        cache_dir_label = QLabel(str(self._cfg.cache_dir))
        cache_dir_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cache_dir_label.setStyleSheet("color: gray;")
        form.addRow("Cache directory", cache_dir_label)

        clear_btn = QPushButton("Clear cache now")
        clear_btn.clicked.connect(self._clear_cache)
        form.addRow("", clear_btn)
        return tab

    def _browse_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select ffmpeg binary")
        if path:
            self._ffmpeg.setText(path)

    def _clear_cache(self) -> None:
        cache_dir = self._addon.config.cache_dir
        if not cache_dir.exists():
            QMessageBox.information(self, "Local TTS", "Cache is already empty.")
            return
        if QMessageBox.question(
            self, "Clear cache",
            f"Delete every cached audio file under\n{cache_dir}?",
        ) != QMessageBox.StandardButton.Yes:
            return
        for entry in cache_dir.iterdir():
            if entry.is_file():
                entry.unlink(missing_ok=True)
            elif entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
        QMessageBox.information(self, "Local TTS", "Cache cleared.")

    # ---------------- Providers ----------------

    def _build_providers_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(14)

        outer.addWidget(_section_label(
            "Provider-level settings — shared across every preset that uses this provider. "
            "Change once when you move the server; presets don't need editing."
        ))

        self._provider_widgets: dict[str, dict[str, QWidget]] = {}
        any_provider = False
        for name in self._addon.providers.names():
            provider = self._addon.providers.get(name)
            schema = provider.provider_options_schema() if hasattr(provider, "provider_options_schema") else {}
            if not schema:
                continue
            any_provider = True
            box = QGroupBox(getattr(provider, "display_name", name))
            form = QFormLayout(box)
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(8)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

            current_settings = self._cfg.provider_settings.get(name, {})
            widgets: dict[str, QWidget] = {}
            for key, spec in schema.items():
                widget = _make_schema_widget(spec, current_settings.get(key, spec.get("default")))
                widgets[key] = widget
                form.addRow(key, widget)
            self._provider_widgets[name] = widgets
            outer.addWidget(box)

        if not any_provider:
            outer.addWidget(QLabel("Registered providers expose no provider-level settings."))
        outer.addStretch(1)
        return tab

    def _collect_provider_settings(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for name, widgets in self._provider_widgets.items():
            slot: dict = {}
            for key, widget in widgets.items():
                slot[key] = _read_schema_widget(widget)
            out[name] = slot
        return out

    # ---------------- Presets ----------------

    def _build_presets_tab(self) -> QWidget:
        tab = QWidget()
        outer = QHBoxLayout(tab)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        self._preset_list = QListWidget()
        self._preset_list.itemDoubleClicked.connect(lambda _: self._edit_preset())
        self._refresh_preset_list()

        side = QVBoxLayout()
        for label, handler in [
            ("New",       self._new_preset),
            ("Edit",      self._edit_preset),
            ("Duplicate", self._duplicate_preset),
            ("Delete",    self._delete_preset),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            side.addWidget(btn)
        side.addStretch(1)

        outer.addWidget(self._preset_list, 1)
        outer.addLayout(side)
        return tab

    def _refresh_preset_list(self) -> None:
        self._preset_list.clear()
        for p in self._cfg.presets:
            self._preset_list.addItem(QListWidgetItem(p.name))

    def _current_preset_index(self) -> int:
        row = self._preset_list.currentRow()
        return row if 0 <= row < len(self._cfg.presets) else -1

    def _new_preset(self) -> None:
        provider_name = next(iter(self._addon.providers.names()), "voicevox")
        provider = self._addon.providers.get(provider_name)
        lang = getattr(provider, "display_language", "")
        disp = getattr(provider, "display_name", provider_name)
        base_name = " ".join(part for part in (lang, disp) if part) or "New preset"
        preset = Preset(name=self._unique_name(base_name), provider=provider_name)
        if self._open_editor(preset, is_new=True):
            preset.name = self._unique_name(preset.name)
            self._cfg.presets.append(preset)
            self._after_preset_change(select=preset.name)

    def _edit_preset(self) -> None:
        i = self._current_preset_index()
        if i < 0:
            return
        edited = copy.deepcopy(self._cfg.presets[i])
        if self._open_editor(edited):
            self._cfg.presets[i] = edited
            self._after_preset_change(select=edited.name)

    def _duplicate_preset(self) -> None:
        i = self._current_preset_index()
        if i < 0:
            return
        clone = copy.deepcopy(self._cfg.presets[i])
        clone.name = self._unique_name(f"{clone.name} copy")
        self._cfg.presets.append(clone)
        self._after_preset_change(select=clone.name)

    def _delete_preset(self) -> None:
        i = self._current_preset_index()
        if i < 0:
            return
        name = self._cfg.presets[i].name
        if QMessageBox.question(
            self, "Delete preset", f"Delete preset {name!r}?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._cfg.presets.pop(i)
        self._after_preset_change()

    def _after_preset_change(self, *, select: str | None = None) -> None:
        self._refresh_preset_list()
        self._refresh_preset_combo(self._default_preset, self._cfg.default_preset)
        self._refresh_routing_preset_columns()
        if select:
            for row in range(self._preset_list.count()):
                if self._preset_list.item(row).text() == select:
                    self._preset_list.setCurrentRow(row)
                    break

    def _open_editor(self, preset: Preset, *, is_new: bool = False) -> bool:
        # Snapshot the draft provider settings from the Providers tab so
        # the editor's voice picker / test honour unsaved edits.
        drafted = self._collect_provider_settings() if self._provider_widgets \
            else dict(self._cfg.provider_settings)
        dlg = PresetEditorDialog(self._addon, preset, self, is_new=is_new,
                                 provider_settings=drafted)
        return dlg.exec() == QDialog.DialogCode.Accepted

    def _unique_name(self, base: str) -> str:
        names = {p.name for p in self._cfg.presets}
        if base not in names:
            return base
        i = 2
        while f"{base} {i}" in names:
            i += 1
        return f"{base} {i}"

    # ---------------- Rules ----------------

    def _build_rules_tab(self) -> QWidget:
        self._rules = _RulesTab(self._cfg.cleanup, self._cfg.regex_rules)
        return self._rules

    # ---------------- Routing ----------------

    def _build_routing_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(14)

        outer.addWidget(_section_label("Resolution order: deck → notetype → language → default"))

        from aqt import mw

        deck_options = self._deck_options(mw)
        notetype_options = self._notetype_options(mw)

        self._routing_deck = _RoutingTable("Deck", deck_options, self._preset_names(), self._cfg.routing.by_deck)
        self._routing_notetype = _RoutingTable("Note type", notetype_options, self._preset_names(), self._cfg.routing.by_notetype)
        self._routing_lang = _RoutingTable("Language", _COMMON_LANGS, self._preset_names(), self._cfg.routing.by_language)

        for group_title, table in [
            ("By deck", self._routing_deck),
            ("By note type", self._routing_notetype),
            ("By language", self._routing_lang),
        ]:
            box = QGroupBox(group_title)
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(10, 10, 10, 10)
            box_layout.addWidget(table)
            outer.addWidget(box, 1)
        return tab

    def _deck_options(self, mw) -> list[tuple[str, str]]:
        try:
            return [(str(d.id), d.name) for d in mw.col.decks.all_names_and_ids()]
        except Exception:
            return []

    def _notetype_options(self, mw) -> list[tuple[str, str]]:
        try:
            return [(str(n.id), n.name) for n in mw.col.models.all_names_and_ids()]
        except Exception:
            return []

    def _preset_names(self) -> list[str]:
        return [p.name for p in self._cfg.presets]

    def _refresh_routing_preset_columns(self) -> None:
        names = self._preset_names()
        for table in (self._routing_deck, self._routing_notetype, self._routing_lang):
            table.update_preset_options(names)

    # ---------------- Combo helpers ----------------

    def _refresh_preset_combo(self, combo: QComboBox, current: str) -> None:
        combo.clear()
        combo.addItem("(none)", "")
        for name in self._preset_names():
            combo.addItem(name, name)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    # ---------------- Save ----------------

    def _on_save(self) -> None:
        self._cfg.enabled = self._enabled.isChecked()
        self._cfg.default_preset = self._default_preset.currentData() or ""
        self._cfg.ffmpeg_path = self._ffmpeg.text().strip() or None
        self._cfg.cache_max_mb = self._cache_max.value()
        self._cfg.provider_settings = self._collect_provider_settings()
        self._cfg.cleanup = self._rules.collect_cleanup()
        self._cfg.regex_rules = self._rules.collect_rules()
        self._cfg.routing.by_deck = self._routing_deck.to_dict()
        self._cfg.routing.by_notetype = self._routing_notetype.to_dict()
        self._cfg.routing.by_language = self._routing_lang.to_dict()

        errors = self._cfg.validation_errors()
        if errors:
            QMessageBox.warning(self, "Local TTS — validation",
                                "Saved with these issues:\n\n" + "\n".join(errors))

        self._addon.apply_config(self._cfg)
        self.accept()


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color: gray;")
    lbl.setWordWrap(True)
    return lbl


def _make_schema_widget(spec: dict, value) -> QWidget:
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
    le.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return le


def _read_schema_widget(widget: QWidget):
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QDoubleSpinBox):
        return widget.value()
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QLineEdit):
        return widget.text()
    return None


_RUBY_MODES = [("base", "Base character (本)"), ("reading", "Reading (ほん)")]
_BRACKET_MODES = [
    ("base", "Base before bracket (日々)"),
    ("reading", "Reading inside bracket (ひび)"),
    ("strip_brackets_only", "Keep both"),
]


class _RulesTab(QWidget):
    """Global text-processing config: cleanup pipeline flags + ordered
    regex rules applied to every preset. Sits between the cleanup pass
    and the provider call.
    """

    def __init__(self, cleanup: CleanupOptions, rules: list[RegexRule]) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(14)

        outer.addWidget(_section_label(
            "Applied to every preset. Cleanup runs first, then regex rules in order. "
            "Editing these does not invalidate cached audio for unaffected text."
        ))

        outer.addWidget(self._build_cleanup_box(cleanup))
        outer.addWidget(self._build_regex_box(rules), 1)

    def _build_cleanup_box(self, cleanup: CleanupOptions) -> QGroupBox:
        box = QGroupBox("Cleanup")
        form = QFormLayout(box)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(6)

        self._ruby_mode = QComboBox()
        for v, label in _RUBY_MODES:
            self._ruby_mode.addItem(label, v)
        self._ruby_mode.setCurrentIndex(max(0, self._ruby_mode.findData(cleanup.ruby_mode)))
        form.addRow("Ruby tags", self._ruby_mode)

        self._bracket_mode = QComboBox()
        for v, label in _BRACKET_MODES:
            self._bracket_mode.addItem(label, v)
        self._bracket_mode.setCurrentIndex(max(0, self._bracket_mode.findData(cleanup.bracket_mode)))
        form.addRow("Bracket readings", self._bracket_mode)

        self._brackets = QLineEdit(", ".join(cleanup.brackets))
        self._brackets.setPlaceholderText("[], (), {}")
        form.addRow("Bracket pairs", self._brackets)

        self._collapse_cjk = QCheckBox("Collapse spaces between Japanese characters")
        self._collapse_cjk.setChecked(cleanup.collapse_cjk_spaces)
        form.addRow("", self._collapse_cjk)
        return box

    def _build_regex_box(self, rules: list[RegexRule]) -> QGroupBox:
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

        for rule in rules:
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

    def collect_cleanup(self) -> CleanupOptions:
        brackets = [b.strip() for b in self._brackets.text().split(",") if b.strip()]
        return CleanupOptions(
            ruby_mode=self._ruby_mode.currentData(),
            bracket_mode=self._bracket_mode.currentData(),
            brackets=brackets or ["[]", "()"],
            collapse_cjk_spaces=self._collapse_cjk.isChecked(),
        )

    def collect_rules(self) -> list[RegexRule]:
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


_COMMON_LANGS = [
    ("ja", "Japanese (ja)"), ("en", "English (en)"), ("zh", "Chinese (zh)"),
    ("ko", "Korean (ko)"), ("de", "German (de)"), ("fr", "French (fr)"),
    ("es", "Spanish (es)"), ("hu", "Hungarian (hu)"),
]


class _RoutingTable(QWidget):
    """Two-column table: key (combo / free text) -> preset (combo). Add/remove buttons."""

    def __init__(
        self,
        key_label: str,
        key_options: list[tuple[str, str]],
        preset_names: list[str],
        data: dict[str, str],
        key_is_freeform: bool = False,
    ) -> None:
        super().__init__()
        self._key_label = key_label
        self._key_options = key_options
        self._preset_names = list(preset_names)
        self._key_is_freeform = key_is_freeform

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([key_label, "Preset"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        for key, preset in data.items():
            self._append_row(key, preset)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(lambda: self._append_row("", ""))
        del_btn = QPushButton("Remove")
        del_btn.clicked.connect(self._remove_selected)

        btns = QHBoxLayout()
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        btns.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        layout.addLayout(btns)

    def _append_row(self, key: str, preset: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setCellWidget(row, 0, self._make_key_widget(key))
        self.table.setCellWidget(row, 1, self._make_preset_combo(preset))

    def _make_key_widget(self, current: str) -> QWidget:
        if self._key_is_freeform:
            le = QLineEdit(current)
            le.setPlaceholderText("e.g. ja, en_US")
            return le
        combo = QComboBox()
        combo.setEditable(False)
        for value, display in self._key_options:
            combo.addItem(display, value)
        if current:
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.addItem(f"(unknown id {current})", current)
                combo.setCurrentIndex(combo.count() - 1)
        return combo

    def _make_preset_combo(self, current: str) -> QComboBox:
        combo = QComboBox()
        for name in self._preset_names:
            combo.addItem(name, name)
        if not self._preset_names:
            combo.addItem("(no presets — create one first)", "")
            combo.setEnabled(False)
        idx = combo.findData(current) if current else -1
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        return combo

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def update_preset_options(self, names: list[str]) -> None:
        self._preset_names = list(names)
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 1)
            if not isinstance(combo, QComboBox):
                continue
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for name in names:
                combo.addItem(name, name)
            if not names:
                combo.addItem("(no presets)", "")
                combo.setEnabled(False)
            else:
                combo.setEnabled(True)
            idx = combo.findData(current) if current else -1
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

    def to_dict(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for row in range(self.table.rowCount()):
            key_widget = self.table.cellWidget(row, 0)
            preset_combo = self.table.cellWidget(row, 1)
            if isinstance(key_widget, QLineEdit):
                key = key_widget.text().strip()
            elif isinstance(key_widget, QComboBox):
                key = key_widget.currentData() or ""
            else:
                continue
            preset = preset_combo.currentData() if isinstance(preset_combo, QComboBox) else ""
            if key and preset:
                out[key] = preset
        return out
