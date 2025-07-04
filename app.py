import os
import json
import shutil
import threading
import subprocess
import time
import uuid
import zipfile
import math
import winreg
import ctypes
import logging
import queue
from functools import partial
from tkinter import filedialog

from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PIL import Image

current_filter = "mods"
mod_states = {}
selected_modpack = None

MOD_NAME_MAPPING = {
    "Replace Font": "replace_font",
    "Optimizer": "optimizer",
    "Cheat": "cheat",
    "Change celestial bodies": "celestials",
    "Hide gui": "hidegui",
    "Remove grass": "remove_grass_mesh",
    "Display fps": "displayfps",
    "Disable remotes": "disable_remotes",
    "Unlock fps": "unlock_fps",
    "Custom death sound": "custom_ouch_sound",
    "Google browser": "google_browser",
    "Chat gpt": "chat_gpt",
    "R63 avatar": "character_meshes",
    "Faster inputs": "faster_inputs",
    "Graphic boost": "graphic_boost",
    "Beautiful sky": "beautiful_sky",
    "Anime chan sky": "anime_chan_sky",
    "Bloxstrap Theme": "bloxstrap_theme"
}

texture_packs = [
    "Replace Font",
    "Change celestial bodies",
    "Custom death sound",
    "R63 avatar",
    "Remove grass",
    "Beautiful sky",
    "Anime chan sky",
    "Bloxstrap Theme",
]

INTERNAL_TO_DISPLAY = {v: k for k, v in MOD_NAME_MAPPING.items()}

CONFLICTING_MODS = {
    "Google browser": ["Chat gpt"],
    "Chat gpt": ["Google browser"],
    "Beautiful sky": ["Anime chan sky"],
    "Anime chan sky": ["Beautiful sky"]
}

script_dir = os.path.dirname(os.path.abspath(__file__))
modpacks_dir = os.path.join(script_dir, "ModPacks")
external_mods_dir = os.path.join(script_dir, "ExternalMods")
images_folder = os.path.join(script_dir, "Assets", "images")
sounds_folder = os.path.join(script_dir, "Assets", "sounds")
meshes_folder = os.path.join(script_dir, "Assets", "meshes")


external_mods_dir = os.path.join(os.path.dirname(__file__), "ExternalMods")
if not os.path.exists(external_mods_dir):
    os.makedirs(external_mods_dir)

external_mods_file = os.path.join(external_mods_dir, "external_mods.json")
if not os.path.exists(external_mods_file):
    with open(external_mods_file, "w") as f:
        json.dump({}, f, indent=4)

def update_mod_state(modpack_path, key, value):
    mod_state_path = os.path.join(modpack_path, "mod_state.json")
    mod_state = {}
    try:
        if os.path.exists(mod_state_path):
            with open(mod_state_path, "r") as f:
                mod_state = json.load(f)
    except Exception as e:
        print(f"Warning: Could not read mod state file {mod_state_path}: {e}")

    mod_state[key] = value

    try:
        with open(mod_state_path, "w") as f:
            json.dump(mod_state, f, indent=4)
        print(f"Updated mod state '{key}' to '{value}' in {mod_state_path}")
    except Exception as e:
        print(f"Error writing mod state file {mod_state_path}: {e}")

def load_external_mods():
    with open(external_mods_file, "r") as f:
        return json.load(f)

def validate_external_mod_entry(internal_name, mod_info):
    try:
        required_keys = ["name", "type", "config_path", "icon_path"]
        if not all(key in mod_info for key in required_keys):
            logging.error(
                f"Invalid mod entry {internal_name}: Missing required keys")
            return False
        if not os.path.exists(mod_info["config_path"]):
            logging.error(
                f"Invalid mod entry {internal_name}: Config path {mod_info['config_path']} does not exist")
            return False
        if mod_info["type"] not in ["mod", "texturepack"]:
            logging.error(
                f"Invalid mod entry {internal_name}: Invalid type {mod_info['type']}")
            return False
        return True
    except Exception as e:
        logging.error(f"Error validating mod entry {internal_name}: {str(e)}")
        return False

def reapply_enabled_mods(modpack):
    if not modpack:
        logging.warning("No modpack selected for reapply_enabled_mods.")
        return

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    if not os.path.exists(mod_state_path):
        logging.debug(f"No mod_state.json found for modpack {modpack}")
        return

    try:
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

        # Apply internal mods
        for internal_name, enabled in mod_state.items():
            if not internal_name.startswith("external_") and enabled:
                func = mod_apply_functions.get(internal_name)
                if func:
                    try:
                        func(True)
                        logging.info(f"Reapplied internal mod {internal_name} for modpack {modpack}")
                    except Exception as e:
                        logging.error(f"Failed to reapply internal mod {internal_name}: {str(e)}")

        external_mods = load_external_mods()
        for internal_name, enabled in mod_state.items():
            if internal_name.startswith("external_") and enabled:
                mod_info = external_mods.get(internal_name)
                if not mod_info:
                    logging.warning(f"External mod {internal_name} not found in external_mods.json")
                    continue
                if not validate_external_mod_entry(internal_name, mod_info):
                    continue
                try:
                    with open(mod_info["config_path"], "r") as f:
                        mod_config = json.load(f)
                    logging.info(f"Reapplying enabled mod {mod_info['name']} ({internal_name}) for modpack {modpack}")
                    apply_external_mod(modpack, internal_name, mod_config, True)
                except Exception as e:
                    logging.error(f"Failed to reapply mod {internal_name}: {str(e)}")
    except Exception as e:
        logging.error(f"Error reading mod_state.json for modpack {modpack}: {str(e)}")

def handle_mod_conflicts(activated_display_name):
    modpack = selected_modpack
    if not modpack or activated_display_name not in CONFLICTING_MODS:
        return

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    if not os.path.exists(mod_state_path):
        return

    with open(mod_state_path, "r") as f:
        mod_state = json.load(f)

    changed = False
    for conflicting_display_name in CONFLICTING_MODS[activated_display_name]:

        internal_key = MOD_NAME_MAPPING.get(conflicting_display_name)
        if not internal_key:
            continue

        if internal_key in mod_state and mod_state[internal_key]:

            mod_state[internal_key] = False

            if conflicting_display_name in mod_states:
                mod_states[conflicting_display_name].set(False)

            func_name = MOD_NAME_MAPPING.get(conflicting_display_name)
            if func_name and func_name in mod_apply_functions:
                mod_apply_functions[func_name](False)

            changed = True
            print(f"Disabled conflicting mod: {conflicting_display_name}")

    if changed:
        with open(mod_state_path, "w") as f:
            json.dump(mod_state, f, indent=4)

def get_roblox_folder():

    potential_paths = [
        os.path.join(os.getenv("LOCALAPPDATA"), "Roblox", "Versions"),
        os.path.join("C:\\Program Files (x86)", "Roblox", "Versions"),
        os.path.join("C:\\Program Files", "Roblox", "Versions")
    ]

    for path in potential_paths:
        if os.path.exists(path):
            for root, dirs, files in os.walk(path):
                if "RobloxPlayerBeta.exe" in files and "RobloxPlayerBeta.dll" in files:
                    print(root)
                    return root
    return None


def generate_unique_internal_name(display_name):
    base_name = display_name.lower().replace(' ', '_')
    unique_id = str(uuid.uuid4())[:8]
    return f"external_{base_name}_{unique_id}"


def save_external_mods(mod_data):
    try:
        with open(external_mods_file, "w") as f:
            json.dump(mod_data, f, indent=4)
        return True
    except Exception as e:
        logging.error(f"Error saving external mods: {str(e)}")
        return False


def create_external_mod():
    dialog = QDialog()
    dialog.setWindowTitle("Create External Mod")
    dialog.setMinimumSize(500, 600)

    layout = QVBoxLayout()

    name_label = QLabel("Mod Name:")
    name_input = QLineEdit()
    layout.addWidget(name_label)
    layout.addWidget(name_input)

    type_label = QLabel("Mod Type:")
    type_combo = QComboBox()
    type_combo.addItems(["mod", "texturepack"])
    layout.addWidget(type_label)
    layout.addWidget(type_combo)

    icon_label = QLabel("Mod Icon:")
    icon_preview = QLabel()
    icon_preview.setFixedSize(100, 100)
    icon_preview.setStyleSheet("background-color: #333; border: 1px solid #444;")

    def select_icon():
        icon_path, _ = QFileDialog.getOpenFileName(
            dialog,
            "Select Mod Icon",
            "",
            "Image Files (*.png *.jpg *.jpeg)"
        )
        if icon_path:
            try:
                img = Image.open(icon_path)
                img = img.resize((100, 100))
                img.save("temp_icon.png")
                pixmap = QPixmap("temp_icon.png")
                os.remove("temp_icon.png")
                icon_preview.setPixmap(pixmap)
                return icon_path
            except Exception as e:
                QMessageBox.warning(dialog, "Error", f"Could not load image: {str(e)}")
        return None

    icon_button = QPushButton("Select Icon")
    icon_button.clicked.connect(select_icon)

    icon_layout = QHBoxLayout()
    icon_layout.addWidget(icon_preview)
    icon_layout.addWidget(icon_button)
    layout.addLayout(icon_layout)

    files_label = QLabel("File Replacements:")
    files_table = QTableWidget()
    files_table.setColumnCount(2)
    files_table.setHorizontalHeaderLabels(["Source Path", "Destination Path"])
    files_table.horizontalHeader().setStretchLastSection(True)

    def add_file_replacement():
        row = files_table.rowCount()
        files_table.insertRow(row)

        source_button = QPushButton("Browse")
        dest_button = QPushButton("Browse")

        def browse_source():
            path, _ = QFileDialog.getOpenFileName(dialog, "Select Source File")
            if path:
                files_table.setItem(row, 0, QTableWidgetItem(path))

        def browse_dest():
            path, _ = QFileDialog.getSaveFileName(
                dialog,
                "Select Destination Path",
                "",
                "All Files (*)"
            )
            if path:
                files_table.setItem(row, 1, QTableWidgetItem(path))

        source_button.clicked.connect(browse_source)
        dest_button.clicked.connect(browse_dest)

        files_table.setCellWidget(row, 0, source_button)
        files_table.setCellWidget(row, 1, dest_button)

    add_file_button = QPushButton("Add File Replacement")
    add_file_button.clicked.connect(add_file_replacement)

    layout.addWidget(files_label)
    layout.addWidget(files_table)
    layout.addWidget(add_file_button)

    flags_label = QLabel("Fast Flags:")
    flags_table = QTableWidget()
    flags_table.setColumnCount(2)
    flags_table.setHorizontalHeaderLabels(["Flag Name", "Flag Value"])
    flags_table.horizontalHeader().setStretchLastSection(True)

    def add_flag():
        row = flags_table.rowCount()
        flags_table.insertRow(row)
        flags_table.setItem(row, 0, QTableWidgetItem(""))
        flags_table.setItem(row, 1, QTableWidgetItem(""))

    add_flag_button = QPushButton("Add Fast Flag")
    add_flag_button.clicked.connect(add_flag)

    layout.addWidget(flags_label)
    layout.addWidget(flags_table)
    layout.addWidget(add_flag_button)

    conflicts_label = QLabel("Conflicting Mods:")
    conflicts_input = QLineEdit()
    conflicts_input.setPlaceholderText("Comma-separated mod names")
    layout.addWidget(conflicts_label)
    layout.addWidget(conflicts_input)

    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)
    layout.addWidget(button_box)

    dialog.setLayout(layout)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        # Gather all mod data
        mod_name = name_input.text().strip()
        if not mod_name:
            QMessageBox.warning(dialog, "Error", "Mod name cannot be empty!")
            return

        mod_type = type_combo.currentText()
        icon_path = select_icon()  # Get the selected icon path

        if not icon_path:
            QMessageBox.warning(dialog, "Error", "Please select an icon for the mod!")
            return

        file_replacements = []
        for row in range(files_table.rowCount()):
            source = files_table.item(row, 0).text() if files_table.item(row, 0) else ""
            dest = files_table.item(row, 1).text() if files_table.item(row, 1) else ""
            if source and dest:
                file_replacements.append({
                    "source": os.path.basename(source),
                    "destination": dest
                })

        fast_flags = {}
        for row in range(flags_table.rowCount()):
            flag_name = flags_table.item(row, 0).text() if flags_table.item(row, 0) else ""
            flag_value = flags_table.item(row, 1).text() if flags_table.item(row, 1) else ""
            if flag_name and flag_value:
                fast_flags[flag_name] = flag_value

        conflicts = [c.strip() for c in conflicts_input.text().split(",") if c.strip()]

        internal_name = generate_unique_internal_name(mod_name)
        mod_dir = os.path.join(external_mods_dir, internal_name)
        os.makedirs(mod_dir, exist_ok=True)

        icon_dest = os.path.join(mod_dir, "icon.png")
        shutil.copy(icon_path, icon_dest)

        for file in file_replacements:
            src_path = file["source"]
            dest_rel_path = os.path.join(mod_dir, os.path.basename(src_path))
            shutil.copy(src_path, dest_rel_path)

        mod_config = {
            "name": mod_name,
            "type": mod_type,
            "fast_flags": fast_flags,
            "replace_files": file_replacements,
            "conflicts": conflicts
        }

        config_path = os.path.join(mod_dir, "mod_config.rfmod")
        with open(config_path, "w") as f:
            json.dump(mod_config, f, indent=4)

        # Add to external mods registry
        external_mods = load_external_mods()
        external_mods[internal_name] = {
            "name": mod_name,
            "type": mod_type,
            "config_path": config_path,
            "icon_path": icon_dest
        }

        if save_external_mods(external_mods):
            MOD_NAME_MAPPING[mod_name] = internal_name
            INTERNAL_TO_DISPLAY[internal_name] = mod_name
            if conflicts:
                CONFLICTING_MODS[mod_name] = conflicts

            def mod_apply_function(enabled):
                apply_external_mod(selected_modpack, internal_name, mod_config, enabled)

            mod_apply_functions[internal_name] = mod_apply_function

            # Add to appropriate category
            if mod_type == "texturepack":
                texture_packs.append(mod_name)

            QMessageBox.information(dialog, "Success", f"Mod '{mod_name}' created successfully!")
            return True
        else:
            QMessageBox.warning(dialog, "Error", "Failed to save mod configuration!")
            return False
    return False


def update_all_external_mods():
    external_mods = load_external_mods()
    if not external_mods:
        QMessageBox.information(None, "Info", "No external mods found to update.")
        return

    progress = QProgressDialog("Updating external mods...", "Cancel", 0, len(external_mods))
    progress.setWindowTitle("Updating Mods")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)

    updated_count = 0

    for i, (internal_name, mod_info) in enumerate(external_mods.items()):
        progress.setValue(i)
        QApplication.processEvents()

        if progress.wasCanceled():
            break

        try:
            config_path = mod_info["config_path"]
            if not os.path.exists(config_path):
                logging.warning(f"Config file not found for {mod_info['name']}")
                continue

            with open(config_path, "r") as f:
                mod_config = json.load(f)

            # Update the mod apply function
            def mod_apply_function(enabled, name=internal_name, config=mod_config):
                apply_external_mod(selected_modpack, name, config, enabled)

            mod_apply_functions[internal_name] = mod_apply_function
            updated_count += 1

        except Exception as e:
            logging.error(f"Failed to update mod {mod_info['name']}: {str(e)}")

    progress.setValue(len(external_mods))
    QMessageBox.information(None, "Complete",
                            f"Successfully updated {updated_count}/{len(external_mods)} external mods.")


def update_single_external_mod(internal_name):
    external_mods = load_external_mods()
    mod_info = external_mods.get(internal_name)

    if not mod_info:
        QMessageBox.warning(None, "Error", "Mod not found in external mods list.")
        return

    try:
        config_path = mod_info["config_path"]
        if not os.path.exists(config_path):
            QMessageBox.warning(None, "Error", f"Config file not found for {mod_info['name']}")
            return

        with open(config_path, "r") as f:
            mod_config = json.load(f)

        # Update the mod apply function
        def mod_apply_function(enabled, name=internal_name, config=mod_config):
            apply_external_mod(selected_modpack, name, config, enabled)

        mod_apply_functions[internal_name] = mod_apply_function

        # If currently enabled, reapply the mod
        if selected_modpack:
            mod_state_path = os.path.join(modpacks_dir, selected_modpack, "mod_state.json")
            if os.path.exists(mod_state_path):
                with open(mod_state_path, "r") as f:
                    mod_state = json.load(f)
                if mod_state.get(internal_name, False):
                    apply_external_mod(selected_modpack, internal_name, mod_config, True)

        QMessageBox.information(None, "Success",
                                f"Mod '{mod_info['name']}' updated successfully!")
    except Exception as e:
        QMessageBox.critical(None, "Error",
                             f"Failed to update mod {mod_info['name']}:\n{str(e)}")


def show_external_mod_manager():
    dialog = QDialog()
    dialog.setWindowTitle("Manage External Mods")
    dialog.setMinimumSize(600, 400)

    layout = QVBoxLayout()

    toolbar = QToolBar()
    import_action = QAction("Import Mod", dialog)
    create_action = QAction("Create Mod", dialog)
    update_action = QAction("Update All", dialog)  # New action
    remove_action = QAction("Remove Selected", dialog)

    import_action.triggered.connect(import_external_mod)
    create_action.triggered.connect(create_external_mod)
    update_action.triggered.connect(update_all_external_mods)  # Connect to new function
    remove_action.triggered.connect(lambda: remove_selected_mods(mods_table))

    toolbar.addAction(import_action)
    toolbar.addAction(create_action)
    toolbar.addAction(update_action)  # Add to toolbar
    toolbar.addAction(remove_action)
    layout.addWidget(toolbar)

    mods_table = QTableWidget()
    mods_table.setColumnCount(4)
    mods_table.setHorizontalHeaderLabels(["Name", "Type", "Status", "Actions"])
    mods_table.horizontalHeader().setStretchLastSection(True)
    mods_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    mods_table.verticalHeader().setDefaultSectionSize(60)  # Increase row height

    external_mods = load_external_mods()
    mods_table.setRowCount(len(external_mods))

    for row, (internal_name, mod_info) in enumerate(external_mods.items()):
        mods_table.setItem(row, 0, QTableWidgetItem(mod_info["name"]))
        mods_table.setItem(row, 1, QTableWidgetItem(mod_info["type"]))

        # Status (whether it's enabled in current modpack)
        status_item = QTableWidgetItem()
        if selected_modpack:
            mod_state_path = os.path.join(modpacks_dir, selected_modpack, "mod_state.json")
            if os.path.exists(mod_state_path):
                with open(mod_state_path, "r") as f:
                    mod_state = json.load(f)
                status = "Enabled" if mod_state.get(internal_name, False) else "Disabled"
                status_item.setText(status)
        else:
            status_item.setText("N/A")
        mods_table.setItem(row, 2, status_item)

        action_widget = QWidget()
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(5, 5, 5, 5)
        action_layout.setSpacing(5)

        # Add refresh button
        refresh_button = QPushButton("Refresh")
        refresh_button.setFixedSize(80, 30)
        refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #3a5a78;
                color: white;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #4a6a88;
            }
        """)
        refresh_button.clicked.connect(lambda _, name=internal_name: update_single_external_mod(name))
        action_layout.addWidget(refresh_button)

        if selected_modpack:
            toggle_button = QPushButton("Toggle")
            toggle_button.setFixedSize(80, 30)
            toggle_button.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3a;
                    color: white;
                    border-radius: 5px;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
            """)
            toggle_button.clicked.connect(lambda _, name=internal_name: toggle_external_mod(name))
            action_layout.addWidget(toggle_button)

        edit_button = QPushButton("Edit")
        edit_button.setFixedSize(80, 30)
        edit_button.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: white;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        edit_button.clicked.connect(lambda _, name=internal_name: edit_external_mod(name))
        action_layout.addWidget(edit_button)

        action_widget.setLayout(action_layout)
        mods_table.setCellWidget(row, 3, action_widget)

    layout.addWidget(mods_table)
    dialog.setLayout(layout)
    dialog.exec()


def toggle_external_mod(internal_name):
    if not selected_modpack:
        QMessageBox.warning(None, "Warning", "Please select a modpack first.")
        return

    mod_state_path = os.path.join(modpacks_dir, selected_modpack, "mod_state.json")
    if not os.path.exists(mod_state_path):
        QMessageBox.warning(None, "Warning", "No mod state file found for this modpack.")
        return

    with open(mod_state_path, "r") as f:
        mod_state = json.load(f)

    current_state = mod_state.get(internal_name, False)
    new_state = not current_state

    external_mods = load_external_mods()
    mod_info = external_mods.get(internal_name)
    if not mod_info:
        QMessageBox.warning(None, "Error", "Mod configuration not found!")
        return

    with open(mod_info["config_path"], "r") as f:
        mod_config = json.load(f)

    apply_external_mod(selected_modpack, internal_name, mod_config, new_state)

    # Update the UI
    mod_state[internal_name] = new_state
    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f, indent=4)

    QMessageBox.information(None, "Success",
                            f"Mod '{mod_info['name']}' is now {'enabled' if new_state else 'disabled'}.")


def edit_external_mod(internal_name):
    external_mods = load_external_mods()
    mod_info = external_mods.get(internal_name)
    if not mod_info:
        QMessageBox.warning(None, "Error", "Mod not found!")
        return

    with open(mod_info["config_path"], "r") as f:
        mod_config = json.load(f)

    dialog = QDialog()
    dialog.setWindowTitle(f"Edit Mod: {mod_info['name']}")
    dialog.setMinimumSize(500, 400)

    layout = QVBoxLayout()

    name_label = QLabel("Mod Name:")
    name_input = QLineEdit(mod_info["name"])
    layout.addWidget(name_label)
    layout.addWidget(name_input)

    type_label = QLabel("Mod Type:")
    type_display = QLabel(mod_info["type"])
    layout.addWidget(type_label)
    layout.addWidget(type_display)
    
    flags_label = QLabel("Fast Flags:")
    flags_editor = QTextEdit()
    flags_editor.setPlainText(json.dumps(mod_config.get("fast_flags", {}), indent=4))
    layout.addWidget(flags_label)
    layout.addWidget(flags_editor)

    files_label = QLabel("File Replacements:")
    files_display = QTextEdit()
    files_display.setPlainText(json.dumps(mod_config.get("replace_files", []), indent=4))
    files_display.setReadOnly(True)
    layout.addWidget(files_label)
    layout.addWidget(files_display)

    conflicts_label = QLabel("Conflicting Mods:")
    conflicts_input = QLineEdit(", ".join(mod_config.get("conflicts", [])))
    layout.addWidget(conflicts_label)
    layout.addWidget(conflicts_input)

    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)
    layout.addWidget(button_box)

    dialog.setLayout(layout)

    if dialog.exec() == QDialog.DialogCode.Accepted:

        new_name = name_input.text().strip()
        if not new_name:
            QMessageBox.warning(dialog, "Error", "Mod name cannot be empty!")
            return

        try:
            new_flags = json.loads(flags_editor.toPlainText())
            new_conflicts = [c.strip() for c in conflicts_input.text().split(",") if c.strip()]

            mod_config["name"] = new_name
            mod_config["fast_flags"] = new_flags
            mod_config["conflicts"] = new_conflicts

            with open(mod_info["config_path"], "w") as f:
                json.dump(mod_config, f, indent=4)

            external_mods[internal_name]["name"] = new_name
            save_external_mods(external_mods)

            if new_name != mod_info["name"]:
                if mod_info["name"] in MOD_NAME_MAPPING:
                    del MOD_NAME_MAPPING[mod_info["name"]]
                MOD_NAME_MAPPING[new_name] = internal_name

                if mod_info["name"] in INTERNAL_TO_DISPLAY:
                    INTERNAL_TO_DISPLAY[internal_name] = new_name

                if mod_info["name"] in CONFLICTING_MODS:
                    CONFLICTING_MODS[new_name] = CONFLICTING_MODS.pop(mod_info["name"])

            QMessageBox.information(dialog, "Success", "Mod updated successfully!")
            return True
        except json.JSONDecodeError:
            QMessageBox.warning(dialog, "Error", "Invalid JSON in fast flags!")
            return False
    return False


def remove_selected_mods(table):

    selected_rows = set(index.row() for index in table.selectionModel().selectedRows())
    if not selected_rows:
        QMessageBox.warning(None, "Warning", "Please select at least one mod to remove.")
        return

    external_mods = load_external_mods()
    mods_to_remove = []

    for row in selected_rows:
        internal_name = list(external_mods.keys())[row]
        mods_to_remove.append((internal_name, external_mods[internal_name]["name"]))

    reply = QMessageBox.question(
        None,
        "Confirm Removal",
        f"Are you sure you want to remove these mods?\n{', '.join(name for _, name in mods_to_remove)}",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )

    if reply == QMessageBox.StandardButton.Yes:
        for internal_name, mod_name in mods_to_remove:
            del external_mods[internal_name]

            if mod_name in MOD_NAME_MAPPING:
                del MOD_NAME_MAPPING[mod_name]

            if internal_name in INTERNAL_TO_DISPLAY:
                del INTERNAL_TO_DISPLAY[internal_name]

            if mod_name in CONFLICTING_MODS:
                del CONFLICTING_MODS[mod_name]

            mod_dir = os.path.join(external_mods_dir, internal_name)
            if os.path.exists(mod_dir):
                shutil.rmtree(mod_dir)

        save_external_mods(external_mods)
        QMessageBox.information(None, "Success", "Selected mods removed successfully!")
        show_external_mod_manager()  # Refresh the manager

def apply_external_mod(modpack, internal_name, mod_config, enabled):
    if not modpack:
        logging.error("No modpack selected for apply_external_mod.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    if not os.path.exists(roblox_path):
        logging.error(f"Roblox path not found: {roblox_path}")
        return

    try:
        version = os.listdir(roblox_path)[0]
        settings_path = os.path.join(
            roblox_path,
            version,
            "ClientSettings",
            "ClientAppSettings.json")
        roblox_content_path = os.path.join(roblox_path, version, "content")
        backup_path = os.path.join(
            roblox_path,
            version,
            "backup_external",
            internal_name)
        mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
        mod_dir = os.path.join(external_mods_dir, internal_name)

        fast_flags = mod_config.get("fast_flags", {})
        replace_files = mod_config.get("replace_files", [])
        mod_name = mod_config.get("name")

        mod_state = {}
        if os.path.exists(mod_state_path):
            with open(mod_state_path, "r") as f:
                mod_state = json.load(f)

        if internal_name not in mod_state:
            mod_state[internal_name] = False
            logging.debug(
                f"Initialized mod state for {internal_name} in {modpack}")

        if enabled:
            logging.info(
                f"Enabling external mod '{mod_name}' ({internal_name}) for modpack '{modpack}'")
            handle_mod_conflicts(mod_name)

            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    settings = json.load(f)
                settings.update(fast_flags)
                with open(settings_path, "w") as f:
                    json.dump(settings, f, indent=4)
                    logging.debug(
                        f"Updated FastFlags for {internal_name}: {fast_flags}")

            os.makedirs(backup_path, exist_ok=True)
            for file_entry in replace_files:
                src_rel_path = file_entry.get("source")
                dst_rel_path = file_entry.get("destination")
                if not src_rel_path or not dst_rel_path:
                    logging.warning(
                        f"Invalid file entry in {internal_name}: {file_entry}")
                    continue
                src_path = os.path.join(mod_dir, src_rel_path)
                dst_path = os.path.join(roblox_content_path, dst_rel_path)
                if os.path.exists(src_path):
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    if os.path.exists(dst_path):
                        shutil.copy2(
                            dst_path, os.path.join(
                                backup_path, dst_rel_path))
                        logging.debug(f"Backed up {dst_path} to {backup_path}")
                    shutil.copy2(src_path, dst_path)
                    logging.debug(f"Copied {src_path} to {dst_path}")
        else:
            logging.info(
                f"Disabling external mod '{mod_name}' ({internal_name}) for modpack '{modpack}'")

            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    settings = json.load(f)
                for key in fast_flags.keys():
                    settings.pop(key, None)
                with open(settings_path, "w") as f:
                    json.dump(settings, f, indent=4)
                    logging.debug(
                        f"Removed FastFlags for {internal_name}: {fast_flags}")

            for file_entry in replace_files:
                dst_rel_path = file_entry.get("destination")
                if not dst_rel_path:
                    logging.warning(
                        f"Invalid destination in {internal_name}: {file_entry}")
                    continue
                dst_path = os.path.join(roblox_content_path, dst_rel_path)
                backup_file = os.path.join(backup_path, dst_rel_path)
                if os.path.exists(backup_file):
                    shutil.copy2(backup_file, dst_path)
                    logging.debug(f"Restored {backup_file} to {dst_path}")
                elif os.path.exists(dst_path):
                    os.remove(dst_path)
                    logging.debug(
                        f"Removed modded file {dst_path} (no backup)")

        mod_state[internal_name] = enabled
        with open(mod_state_path, "w") as f:
            json.dump(mod_state, f, indent=4)
            logging.debug(f"Saved mod state for {internal_name}: {enabled}")

    except Exception as e:
        logging.error(
            f"Error applying external mod {internal_name} for modpack {modpack}: {str(e)}")


def validate_external_mod_entry(internal_name, mod_info):
    try:
        required_keys = ["name", "type", "config_path", "icon_path"]
        if not all(key in mod_info for key in required_keys):
            logging.error(
                f"Invalid mod entry {internal_name}: Missing required keys")
            return False
        if not os.path.exists(mod_info["config_path"]):
            logging.error(
                f"Invalid mod entry {internal_name}: Config path {mod_info['config_path']} does not exist")
            return False
        if mod_info["type"] not in ["mod", "texturepack"]:
            logging.error(
                f"Invalid mod entry {internal_name}: Invalid type {mod_info['type']}")
            return False
        return True
    except Exception as e:
        logging.error(f"Error validating mod entry {internal_name}: {str(e)}")
        return False


def _import_external_mod_worker(zip_path, result_queue):
    try:
        result_queue.put(("status", "Extracting mod archive..."))
        temp_dir = os.path.join(os.path.dirname(__file__), "TempModExtract")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        config_path = os.path.join(temp_dir, "mod_config.rfmod")
        if not os.path.exists(config_path):
            result_queue.put(
                ("error", "mod_config.rfmod not found in archive."))
            shutil.rmtree(temp_dir)
            return

        with open(config_path, "r") as f:
            mod_config = json.load(f)

        mod_name = mod_config.get("name")
        mod_type = mod_config.get("type", "mod")
        conflicts = mod_config.get("conflicts", [])

        if not mod_name or mod_type not in ["mod", "texturepack"]:
            result_queue.put(
                ("error", "Invalid mod_config.rfmod: Missing or invalid name/type."))
            shutil.rmtree(temp_dir)
            return

        internal_name = generate_unique_internal_name(mod_name)
        external_mods = load_external_mods()
        if internal_name in external_mods:
            result_queue.put(
                ("warning", f"Mod '{mod_name}' already exists (internal collision)."))
            shutil.rmtree(temp_dir)
            return

        mod_dir = os.path.join(external_mods_dir, internal_name)
        if os.path.exists(mod_dir):
            shutil.rmtree(mod_dir)
        shutil.move(temp_dir, mod_dir)

        icon_src = os.path.join(mod_dir, "icon.png")
        icon_dst = os.path.join(mod_dir, "icon.png")
        if not os.path.exists(icon_src):
            shutil.copy(os.path.join(images_folder, "play.png"), icon_dst)

        external_mods[internal_name] = {
            "name": mod_name,
            "type": mod_type,
            "config_path": os.path.join(mod_dir, "mod_config.rfmod"),
            "icon_path": icon_dst
        }
        save_external_mods(external_mods)

        # Get list of modpacks from the modpacks directory
        modpacks = [d for d in os.listdir(modpacks_dir)
                    if os.path.isdir(os.path.join(modpacks_dir, d))]

        for modpack in modpacks:
            mod_state_path = os.path.join(
                modpacks_dir, modpack, "mod_state.json")
            mod_state = {}
            if os.path.exists(mod_state_path):
                with open(mod_state_path, "r") as f:
                    mod_state = json.load(f)
            mod_state[internal_name] = False
            with open(mod_state_path, "w") as f:
                json.dump(mod_state, f, indent=4)

        def mod_apply_function(enabled):
            apply_external_mod(
                selected_modpack,
                internal_name,
                mod_config,
                enabled)

        mod_apply_functions[internal_name] = mod_apply_function

        if mod_type == "texturepack":
            texture_packs.append(mod_name)
        else:
            if mod_name in texture_packs:
                texture_packs.remove(mod_name)

        if mod_name not in MOD_NAME_MAPPING:
            MOD_NAME_MAPPING[mod_name] = internal_name
            INTERNAL_TO_DISPLAY[internal_name] = mod_name
            CONFLICTING_MODS[mod_name] = conflicts

        result_queue.put(("success", mod_name))

    except Exception as e:
        result_queue.put(("error", f"Failed to import mod: {str(e)}"))
        shutil.rmtree(temp_dir, ignore_errors=True)

def check_external_mod_queue(loading_window, result_queue):
    try:
        message = result_queue.get_nowait()
        msg_type, msg_data = message

        if msg_type == "status":
            loading_window.label.setText(msg_data)
            QApplication.processEvents()
        elif msg_type == "error":
            loading_window.close()
            QMessageBox.critical(None, "Import Error", msg_data)
        elif msg_type == "warning":
            loading_window.close()
            QMessageBox.warning(None, "Warning", msg_data)
        elif msg_type == "log_warning":
            logging.warning(msg_data)
        elif msg_type == "success":
            loading_window.close()
            QMessageBox.information(
                None,
                "Success",
                f"Mod '{msg_data}' imported successfully and available for all modpacks!")

            # Refresh the mods display if we're in the mods page
            if hasattr(app, 'activeWindow') and isinstance(app.activeWindow(), MainWindow):
                app.activeWindow().filter_mods(current_filter)
    except queue.Empty:
        pass


def import_external_mod():
    import_path = filedialog.askopenfilename(
        filetypes=[("RoForge Mod", "*.zip"), ("All Files", "*.*")],
        title="Import External Mod or Texture Pack"
    )
    if not import_path:
        return

    loading_window = LoadingDialog(None, "Importing external mod...")  # Pass None as parent
    result_queue = queue.Queue()

    thread = threading.Thread(
        target=_import_external_mod_worker,
        args=(import_path, result_queue),
        daemon=True
    )
    thread.start()

    timer = QTimer()
    timer.timeout.connect(lambda: check_external_mod_queue(loading_window, result_queue))
    timer.start(100)


def apply_day_night_cycle(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    sky_path = os.path.join(roblox_path, version, "content", "sky")

    moon_path = os.path.join(sky_path, "moon.jpg")
    sun_path = os.path.join(sky_path, "sun.jpg")

    if enabled:

        if os.path.exists(moon_path) and os.path.exists(sun_path):

            shutil.copy(moon_path, os.path.join(sky_path, "moon_original.jpg"))
            shutil.copy(sun_path, os.path.join(sky_path, "sun_original.jpg"))

            os.rename(moon_path, os.path.join(sky_path, "temp.jpg"))
            os.rename(sun_path, moon_path)
            os.rename(os.path.join(sky_path, "temp.jpg"), sun_path)
            print(f"Switched day/night cycle for modpack '{modpack}'")
    else:

        moon_original_path = os.path.join(sky_path, "moon_original.jpg")
        sun_original_path = os.path.join(sky_path, "sun_original.jpg")

        if os.path.exists(moon_original_path) and os.path.exists(
                sun_original_path):

            os.remove(moon_path)
            os.remove(sun_path)

            shutil.copy(moon_original_path, moon_path)
            shutil.copy(sun_original_path, sun_path)
            print(f"Restored original day/night cycle for modpack '{modpack}'")

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["celestials"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)

def replace_font(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    fonts_dir = os.path.join(roblox_path, version, "content", "fonts")

    if enabled:

        custom_font_path = filedialog.askopenfilename(
            title="Select a font file", filetypes=[
                ("Font files", "*.otf;*.ttf")])
        if custom_font_path:

            backup_dir = os.path.join(fonts_dir, "backup")
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            for font_file in os.listdir(fonts_dir):
                if font_file.endswith(".otf") or font_file.endswith(".ttf"):
                    shutil.copy(os.path.join(fonts_dir, font_file), backup_dir)

            for font_file in os.listdir(fonts_dir):
                if font_file.endswith(".otf") or font_file.endswith(".ttf"):
                    shutil.copy(
                        custom_font_path, os.path.join(
                            fonts_dir, font_file))
            print(
                f"Replaced all fonts in modpack '{modpack}' with {custom_font_path}")
    else:

        backup_dir = os.path.join(fonts_dir, "backup")
        if os.path.exists(backup_dir):
            for font_file in os.listdir(backup_dir):

                os.remove(os.path.join(fonts_dir, font_file))
                shutil.copy(
                    os.path.join(
                        backup_dir, font_file), os.path.join(
                        fonts_dir, font_file))
            print(f"Restored original fonts in modpack '{modpack}'")

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["replace_font"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def apply_optimizer(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["FFlagOptimizeNetwork"] = "True"
        settings["FFlagOptimizeNetworkRouting"] = "True"
        settings["FFlagOptimizeNetworkTransport"] = "True"
        settings["FFlagOptimizeServerTickRate"] = "True"
        print(f"Enabled 'Optimizer' mod for modpack '{modpack}'")
    else:

        settings.pop("FFlagOptimizeNetwork", None)
        settings.pop("FFlagOptimizeNetworkRouting", None)
        settings.pop("FFlagOptimizeNetworkTransport", None)
        settings.pop("FFlagOptimizeServerTickRate", None)
        print(f"Disabled 'Optimizer' mod for modpack '{modpack}'")

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["optimizer"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def apply_remove_grass_mesh(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["FIntFRMMinGrassDistance"] = "0"
        settings["FIntFRMMaxGrassDistance"] = "0"
        settings["FIntRenderGrassDetailStrands"] = "0"
        settings["FIntRenderGrassHeightScaler"] = "0"
        print(f"Enabled 'Remove grass mesh' mod for modpack '{modpack}'")
    else:

        settings.pop("FIntFRMMinGrassDistance", None)
        settings.pop("FIntFRMMaxGrassDistance", None)
        settings.pop("FIntRenderGrassDetailStrands", None)
        settings.pop("FIntRenderGrassHeightScaler", None)
        print(f"Disabled 'Remove grass mesh' mod for modpack '{modpack}'")

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["remove_grass_mesh"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def apply_hide_gui(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["FFlagUserShowGuiHideToggles"] = "True"
        settings["GuiHidingApiSupport2"] = "True"
        settings["DFIntCanHideGuiGroupId"] = "3375285"

        print(f"Enabled 'Hide gui' mod for modpack '{modpack}'")
    else:

        settings.pop("FFlagUserShowGuiHideToggles", None)
        settings.pop("GuiHidingApiSupport2", None)
        settings.pop("DFIntCanHideGuiGroupId", None)
        print(f"Disabled 'Hide gui' mod for modpack '{modpack}'")

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["hidegui"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def apply_display_fps(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:
        settings["FFlagDebugDisplayFPS"] = "True"

        print(f"Enabled 'Display fps' mod for modpack '{modpack}'")
    else:
        settings.pop("FFlagDebugDisplayFPS", None)
        print(f"Disabled 'Display fps' mod for modpack '{modpack}'")

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["displayfps"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def apply_cheat(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["FFlagDebugSimDefaultPrimalSolver"] = "True"
        settings["DFIntDebugSimPrimalLineSearch"] = "22222222"
        settings["DFIntSolidFloorPercentForceApplication"] = "-1000"
        settings["DFIntNonSolidFloorPercentForceApplication"] = "-5000"
        settings["DFIntMaxMissedWorldStepsRemembered"] = "1000"
        print(f"Enabled 'Cheat' mod for modpack '{modpack}'")
    else:
        settings.pop("DFIntMaxMissedWorldStepsRemembered", None)
        settings.pop("DFIntNonSolidFloorPercentForceApplication", None)
        settings.pop("DFIntSolidFloorPercentForceApplication", None)
        settings.pop("DFIntDebugSimPrimalLineSearch", None)
        settings.pop("FFlagDebugSimDefaultPrimalSolver", None)
        print(f"Disabled 'Cheat' mod for modpack '{modpack}'")

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["cheat"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def disable_remotes(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["DFIntRemoteEventSingleInvocationSizeLimit"] = "1"
        print(f"Enabled 'Disable remotes' mod for modpack '{modpack}'")
    else:
        settings.pop("DFIntRemoteEventSingleInvocationSizeLimit", None)
        print(f"Disabled 'Disable remotes' mod for modpack '{modpack}'")

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["disable_remotes"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def google_browser(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        handle_mod_conflicts("Google browser")

        settings["FFlagPlatformEventEnabled2"] = "True"
        settings["FStringPlatformEventUrl"] = "https://google.com/"
        settings["FFlagTopBarUseNewBadge"] = "True"
        settings["FStringTopBarBadgeLearnMoreLink"] = "https://google.com/"
        settings["FStringVoiceBetaBadgeLearnMoreLink"] = "https://google.com/"
        settings["FFlagDebugEnableNewWebView2DevTool"] = "True"
        print(f"Enabled 'Google browser' mod for modpack '{modpack}'")
    else:
        settings.pop("FFlagPlatformEventEnabled2", None)
        settings.pop("FStringPlatformEventUrl", None)
        settings.pop("FFlagTopBarUseNewBadge", None)
        settings.pop("FStringTopBarBadgeLearnMoreLink", None)
        settings.pop("FStringVoiceBetaBadgeLearnMoreLink", None)
        settings.pop("FFlagDebugEnableNewWebView2DevTool", None)
        print(f"Disabled 'Google browser' mod for modpack '{modpack}'")

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["google_browser"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def replace_character_meshes(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]
    original_meshes_path = os.path.join(
        roblox_path, version, "content", "avatar", "meshes")
    backup_meshes_path = os.path.join(
        roblox_path,
        version,
        "content",
        "avatar",
        "meshes_backup")
    custom_meshes_path = os.path.join(meshes_folder, "chan")

    if enabled:

        if not os.path.exists(backup_meshes_path):
            shutil.copytree(original_meshes_path, backup_meshes_path)
            print("Created backup of original meshes")

        shutil.rmtree(original_meshes_path)
        os.makedirs(original_meshes_path)

        for mesh_file in os.listdir(custom_meshes_path):
            if mesh_file.endswith(".mesh"):
                shutil.copy(
                    os.path.join(custom_meshes_path, mesh_file),
                    os.path.join(original_meshes_path, mesh_file)
                )
        print(
            f"Replaced character meshes with custom ones in modpack '{modpack}'")
    else:

        if os.path.exists(backup_meshes_path):
            shutil.rmtree(original_meshes_path)
            shutil.copytree(backup_meshes_path, original_meshes_path)
            print(f"Restored original character meshes in modpack '{modpack}'")

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["character_meshes"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def chat_gpt(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        handle_mod_conflicts("Chat gpt")

        settings["FFlagPlatformEventEnabled2"] = "True"
        settings["FStringPlatformEventUrl"] = "https://chatbotchatapp.com/"
        settings["FFlagTopBarUseNewBadge"] = "True"
        settings["FStringTopBarBadgeLearnMoreLink"] = "https://chatbotchatapp.com/"
        settings["FStringVoiceBetaBadgeLearnMoreLink"] = "https://chatbotchatapp.com/"
        settings["FFlagDebugEnableNewWebView2DevTool"] = "True"
        print(f"Enabled 'Google browser' mod for modpack '{modpack}'")
    else:
        settings.pop("FFlagPlatformEventEnabled2", None)
        settings.pop("FStringPlatformEventUrl", None)
        settings.pop("FFlagTopBarUseNewBadge", None)
        settings.pop("FStringTopBarBadgeLearnMoreLink", None)
        settings.pop("FStringVoiceBetaBadgeLearnMoreLink", None)
        settings.pop("FFlagDebugEnableNewWebView2DevTool", None)
        print(f"Disabled 'Google browser' mod for modpack '{modpack}'")

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["chat_gpt"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def faster_inputs(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["FIntActivatedCountTimerMSKeyboard"] = 1
        print(f"Enabled 'Faster inputs' mod for modpack '{modpack}'")
    else:
        settings.pop("FIntActivatedCountTimerMSKeyboard", None)
        print(f"Disabled 'Faster inputs' mod for modpack '{modpack}'")

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["faster_inputs"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def unlock_fps(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["FFlagTaskSchedulerLimitTargetFpsTo2402"] = "False"
        settings["DFIntTaskSchedulerTargetFps"] = "9999"
        print(f"Enabled 'Unlock fps' mod for modpack '{modpack}'")
    else:
        settings.pop("FFlagTaskSchedulerLimitTargetFpsTo2402", None)
        settings.pop("DFIntTaskSchedulerTargetFps", None)
        print(f"Disabled 'Unlock fps' mod for modpack '{modpack}'")

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["unlock_fps"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def graphic_boost(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:
        settings["FFlagMovePrerenderV2"] = "True"
        settings["FFlagCommitToGraphicsQualityFix"] = "True"
        settings["FFlagFixGraphicsQuality"] = "True"
        settings["DFIntDebugFRMQualityLevelOverride"] = "21"
        settings["FFlagCommitToGraphicsQualityFix"] = "True"
        settings["FFlagFixGraphicsQuality"] = "True"
        settings["FFlagDebugGraphicsDisableDirect3D11"] = "True"
        settings["FFlagDebugGraphicsPreferOpenGL"] = "True"
        settings["DFIntMaxFrameBufferSize"] = "4"
        settings["DFFlagTextureQualityOverrideEnabled"] = "True"
        settings["DFIntTextureQualityOverride"] = "3"
        settings["FFlagDebugForceFutureIsBrightPhase3"] = "True"
        print(f"Enabled 'Graphic boost' mod for modpack '{modpack}'")
    else:
        settings.pop("FFlagFixGraphicsQuality", None)
        settings.pop("FFlagCommitToGraphicsQualityFix", None)
        settings.pop("FFlagMovePrerenderV2", None)
        settings.pop("DFIntDebugFRMQualityLevelOverride", None)
        settings.pop("FFlagCommitToGraphicsQualityFix", None)
        settings.pop("FFlagFixGraphicsQuality", None)
        settings.pop("FFlagDebugGraphicsDisableDirect3D11", None)
        settings.pop("FFlagDebugGraphicsPreferOpenGL", None)
        settings.pop("FFlagCommitToGraphicsQualityFix", None)
        settings.pop("DFIntMaxFrameBufferSize", None)
        settings.pop("DFFlagTextureQualityOverrideEnabled", None)
        settings.pop("DFIntTextureQualityOverride", None)
        settings.pop("FFlagDebugForceFutureIsBrightPhase3", None)
        print(f"Disabled 'Graphic boost' mod for modpack '{modpack}'")

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["graphic_boost"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def apply_custom_ouch_sound(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    ouch_path = os.path.join(
        roblox_path,
        version,
        "content",
        "sounds",
        "ouch.ogg")

    if enabled:

        if os.path.exists(ouch_path):

            shutil.copy(
                ouch_path,
                os.path.join(
                    roblox_path,
                    version,
                    "content",
                    "sounds",
                    "ouch_original.ogg"))

        new_ouch_path = filedialog.askopenfilename(
            title="Select a new ouch.ogg file", filetypes=[
                ("Ogg files", "*.ogg")])
        if new_ouch_path:
            shutil.copy(new_ouch_path, ouch_path)
            print(
                f"Replaced ouch.ogg in modpack '{modpack}' with {new_ouch_path}")
    else:

        original_ouch_path = os.path.join(
            roblox_path, version, "content", "sounds", "ouch_original.ogg")
        if os.path.exists(original_ouch_path):
            shutil.copy(original_ouch_path, ouch_path)
            print(f"Restored original ouch.ogg in modpack '{modpack}'")

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["custom_ouch_sound"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f)


def beautiful_sky(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    sky_textures = {
        'bk': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_bk.tex"),
        'dn': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_dn.tex"),
        'ft': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_ft.tex"),
        'lf': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_lf.tex"),
        'rt': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_rt.tex"),
        'up': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_up.tex")}

    new_sky_path = os.path.join(os.path.dirname(
        __file__), "Assets", "sky", "beautiful")

    if enabled:

        handle_mod_conflicts("Beautiful sky")

        backup_path = os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "backup")
        if not os.path.exists(backup_path):
            os.makedirs(backup_path)

        for direction in ['bk', 'dn', 'ft', 'lf', 'rt', 'up']:
            original_path = sky_textures[direction]
            backup_file = os.path.join(
                backup_path, f"sky512_{direction}_original.tex")

            if os.path.exists(original_path):
                shutil.copy2(original_path, backup_file)

            new_texture = os.path.join(new_sky_path, f"sky512_{direction}.tex")
            if os.path.exists(new_texture):
                shutil.copy2(new_texture, original_path)

        print(f"Replaced outdoor sky textures for modpack '{modpack}'")
    else:

        backup_path = os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "backup")
        if os.path.exists(backup_path):
            for direction in ['bk', 'dn', 'ft', 'lf', 'rt', 'up']:
                original_path = sky_textures[direction]
                backup_file = os.path.join(
                    backup_path, f"sky512_{direction}_original.tex")

                if os.path.exists(backup_file):
                    shutil.copy2(backup_file, original_path)

        print(
            f"Restored original outdoor sky textures for modpack '{modpack}'")

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["beautiful_sky"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f, indent=4)


def anime_chan_sky(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    sky_textures = {
        'bk': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_bk.tex"),
        'dn': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_dn.tex"),
        'ft': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_ft.tex"),
        'lf': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_lf.tex"),
        'rt': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_rt.tex"),
        'up': os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "sky512_up.tex")}

    new_sky_path = os.path.join(
        os.path.dirname(__file__),
        "Assets",
        "sky",
        "chan")

    if enabled:

        handle_mod_conflicts("Anime chan sky")

        backup_path = os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "backup")
        if not os.path.exists(backup_path):
            os.makedirs(backup_path)

        for direction in ['bk', 'dn', 'ft', 'lf', 'rt', 'up']:
            original_path = sky_textures[direction]
            backup_file = os.path.join(
                backup_path, f"sky512_{direction}_original.tex")

            if os.path.exists(original_path):
                shutil.copy2(original_path, backup_file)

            new_texture = os.path.join(new_sky_path, f"sky512_{direction}.tex")
            if os.path.exists(new_texture):
                shutil.copy2(new_texture, original_path)

        print(f"Replaced outdoor sky textures for modpack '{modpack}'")
    else:

        backup_path = os.path.join(
            roblox_path,
            version,
            "PlatformContent",
            "pc",
            "textures",
            "sky",
            "backup")
        if os.path.exists(backup_path):
            for direction in ['bk', 'dn', 'ft', 'lf', 'rt', 'up']:
                original_path = sky_textures[direction]
                backup_file = os.path.join(
                    backup_path, f"sky512_{direction}_original.tex")

                if os.path.exists(backup_file):
                    shutil.copy2(backup_file, original_path)

        print(
            f"Restored original outdoor sky textures for modpack '{modpack}'")

    mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
    mod_state = {}
    if os.path.exists(mod_state_path):
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

    mod_state["anime_chan_sky"] = enabled

    with open(mod_state_path, "w") as f:
        json.dump(mod_state, f, indent=4)


def apply_bloxstrap_theme(enabled):
    modpack = selected_modpack
    if not modpack:
        print("Error: Please select a modpack first.")

        return

    modpacks_base_dir = modpacks_dir
    modpack_path = os.path.join(modpacks_base_dir, modpack)
    roblox_copy_path = os.path.join(modpack_path, "RobloxCopy")

    if not os.path.exists(roblox_copy_path):
        print(
            f"Error: RobloxCopy folder not found for modpack '{modpack}' at {roblox_copy_path}")
        return

    try:
        versions = [
            d for d in os.listdir(roblox_copy_path) if os.path.isdir(
                os.path.join(
                    roblox_copy_path, d))]
        if not versions:
            print(f"Error: No version folder found inside {roblox_copy_path}")
            return

        version = versions[0]
        roblox_version_path = os.path.join(roblox_copy_path, version)
    except Exception as e:
        print(
            f"Error accessing Roblox version folder in {roblox_copy_path}: {e}")
        return

    script_dir = os.path.dirname(__file__)
    theme_base_path = os.path.join(
        script_dir, "Assets", "ui", "bloxstraptheme")
    theme_content_path = os.path.join(theme_base_path, "content")
    theme_extracontent_path = os.path.join(theme_base_path, "ExtraContent")

    roblox_content_path = os.path.join(roblox_version_path, "content")
    roblox_extracontent_path = os.path.join(
        roblox_version_path, "ExtraContent")

    backup_path = os.path.join(roblox_version_path, "backup_bloxstrap_theme")

    def copy_files_with_backup(src_base, dst_base, backup_base):
        print(f"Processing: {src_base} -> {dst_base}")
        if not os.path.exists(src_base):
            print(f"Warning: Source path {src_base} does not exist. Skipping.")
            return

        copied_files = 0
        errors = 0
        for root, dirs, files in os.walk(src_base):

            relative_path = os.path.relpath(root, src_base)
            dst_dir = os.path.join(dst_base, relative_path)
            backup_dir = os.path.join(backup_base, relative_path)

            if files:
                os.makedirs(dst_dir, exist_ok=True)

            for file in files:
                src_file = os.path.join(root, file)
                dst_file = os.path.join(dst_dir, file)
                backup_file = os.path.join(backup_dir, file)

                try:

                    if os.path.exists(dst_file):

                        if not os.path.exists(backup_file):
                            os.makedirs(
                                os.path.dirname(backup_file), exist_ok=True)
                            print(f"  Backing up: {dst_file} -> {backup_file}")
                            shutil.copy2(dst_file, backup_file)
                        else:
                            print(f"  Backup exists: {backup_file}")

                    print(f"  Copying: {src_file} -> {dst_file}")
                    shutil.copy2(src_file, dst_file)
                    copied_files += 1

                except Exception as e:
                    print(f"  Error processing file {src_file}: {e}")
                    errors += 1
        print(
            f"Finished processing {src_base}. Copied: {copied_files}, Errors: {errors}")
        return errors == 0

    def restore_files_from_backup(backup_base, dst_base):
        print(f"Restoring from: {backup_base} -> {dst_base}")
        if not os.path.exists(backup_base):
            print(f"Backup path {backup_base} not found. Nothing to restore.")
            return True

        restored_files = 0
        errors = 0
        for root, dirs, files in os.walk(backup_base):
            relative_path = os.path.relpath(root, backup_base)
            dst_dir = os.path.join(dst_base, relative_path)

            for file in files:
                backup_file = os.path.join(root, file)
                dst_file = os.path.join(dst_dir, file)

                try:

                    os.makedirs(os.path.dirname(dst_file), exist_ok=True)

                    print(f"  Restoring: {backup_file} -> {dst_file}")
                    shutil.copy2(backup_file, dst_file)
                    restored_files += 1
                except Exception as e:
                    print(f"  Error restoring file {backup_file}: {e}")
                    errors += 1

        print(
            f"Finished restoring {backup_base}. Restored: {restored_files}, Errors: {errors}")
        return errors == 0

    try:
        if enabled:
            print(f"\nApplying Bloxstrap theme to modpack '{modpack}'...")

            os.makedirs(backup_path, exist_ok=True)

            success1 = copy_files_with_backup(
                theme_content_path,
                roblox_content_path,
                os.path.join(backup_path, "content")
            )

            success2 = copy_files_with_backup(
                theme_extracontent_path,
                roblox_extracontent_path,
                os.path.join(backup_path, "ExtraContent")
            )

            if success1 and success2:
                print(
                    f"\nSuccessfully applied Bloxstrap theme to modpack '{modpack}'")
                update_mod_state(modpack_path, "bloxstrap_theme", True)
            else:
                print(
                    f"\nErrors occurred while applying Bloxstrap theme to modpack '{modpack}'. Check logs above.")

        else:
            print(f"\nRemoving Bloxstrap theme from modpack '{modpack}'...")
            if not os.path.exists(backup_path):
                print(
                    "No backup found. Assuming theme was not applied or backup was removed.")

                update_mod_state(modpack_path, "bloxstrap_theme", False)
                return

            success1 = restore_files_from_backup(
                os.path.join(backup_path, "content"),
                roblox_content_path
            )

            success2 = restore_files_from_backup(
                os.path.join(backup_path, "ExtraContent"),
                roblox_extracontent_path
            )

            if success1 and success2:

                try:
                    print(f"Removing backup directory: {backup_path}")
                    shutil.rmtree(backup_path)
                    print(
                        f"\nSuccessfully removed Bloxstrap theme and restored original files for modpack '{modpack}'")
                    update_mod_state(modpack_path, "bloxstrap_theme", False)
                except Exception as e:
                    print(
                        f"Error removing backup directory {backup_path}: {e}")

                    update_mod_state(modpack_path, "bloxstrap_theme", False)
            else:
                print(
                    f"\nErrors occurred while restoring from backup for modpack '{modpack}'. Backup NOT removed. Check logs above.")

    except Exception as e:
        print(f"\nAn unexpected error occurred during theme operation: {e}")


mod_apply_functions = {
            "replace_font": replace_font,
            "optimizer": apply_optimizer,
            "cheat": apply_cheat,
            "celestials": apply_day_night_cycle,
            "hidegui": apply_hide_gui,
            "remove_grass_mesh": apply_remove_grass_mesh,
            "displayfps": apply_display_fps,
            "disable_remotes": disable_remotes,
            "unlock_fps": unlock_fps,
            "custom_ouch_sound": apply_custom_ouch_sound,
            "google_browser": google_browser,
            "chat_gpt": chat_gpt,
            "character_meshes": replace_character_meshes,
            "faster_inputs": faster_inputs,
            "graphic_boost": graphic_boost,
            "beautiful_sky": beautiful_sky,
            "anime_chan_sky": anime_chan_sky,
            "bloxstrap_theme": apply_bloxstrap_theme
}

class LoadingDialog(QDialog):
    def __init__(self, parent=None, message="Loading..."):
        super().__init__(parent)
        self.setWindowTitle("Loading")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFixedSize(300, 100)

        layout = QVBoxLayout()
        self.label = QLabel(message)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate mode

        layout.addWidget(self.label)
        layout.addWidget(self.progress)
        self.setLayout(layout)

    def update_message(self, message):
        self.label.setText(message)
        QApplication.processEvents()


class ModSwitch(QFrame):
    def __init__(self, mod_name, icon_path, toggle_callback, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
            }
        """)

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)

        # Icon
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(50, 50)
        self.set_icon(icon_path)
        layout.addWidget(self.icon_label)

        # Mod name
        self.name_label = QLabel(mod_name)
        self.name_label.setStyleSheet("font-size: 14px; color: white;")
        layout.addWidget(self.name_label)

        # Spacer
        layout.addStretch()

        # Toggle switch
        self.toggle = QCheckBox()
        self.toggle.setStyleSheet("""
            QCheckBox {
                background-color: transparent;
            }
            
            QCheckBox::indicator {
                width: 50px;
                height: 25px;
            }
            QCheckBox::indicator:checked {
                image: url(:/checked);
                background-color: #4CAF50;
                border-radius: 12px;
            }
            QCheckBox::indicator:unchecked {
                image: url(:/unchecked);
                background-color: #555555;
                border-radius: 12px;
            }
        """)
        self.toggle.stateChanged.connect(toggle_callback)
        layout.addWidget(self.toggle)

        self.setLayout(layout)

    def set_icon(self, icon_path):
        try:
            img = Image.open(icon_path)
            img = img.resize((50, 50))
            img.save("temp_icon.png")  # Save temporarily
            pixmap = QPixmap("temp_icon.png")
            os.remove("temp_icon.png")
            self.icon_label.setPixmap(pixmap)
        except:
            # Fallback icon
            pixmap = QPixmap(50, 50)
            pixmap.fill(QColor(100, 100, 100))
            self.icon_label.setPixmap(pixmap)


class ModpackCard(QFrame):
    def __init__(self, modpack_name, icon_path, click_callback, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 180)

        self.setStyleSheet("""
            ModpackCard {
                border: 1px solid;
                border-radius: 5px;
            }
            ModpackCard QLabel {
                border: none !important;
                background: none !important;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(140, 140)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_icon(icon_path)
        layout.addWidget(self.icon_label)

        self.name_label = QLabel(modpack_name)
        self.name_label.setStyleSheet("font-size: 14px;")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.name_label)

        self.setLayout(layout)

        self.mousePressEvent = lambda e: click_callback(modpack_name)

    def set_icon(self, icon_path):
        try:
            img = Image.open(icon_path)
            img = img.resize((140, 140))
            img.save("temp_modpack_icon.png")
            pixmap = QPixmap("temp_modpack_icon.png")
            os.remove("temp_modpack_icon.png")
            self.icon_label.setPixmap(pixmap)
        except:
            pixmap = QPixmap(140, 140)
            pixmap.fill(QColor(100, 100, 100))
            self.icon_label.setPixmap(pixmap)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RoForge")
        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(1000, 700)

        default_font = QFont("Roboto", 10)
        QApplication.setFont(default_font)

        QFontDatabase.addApplicationFont("assets/fonts/Roboto-Regular.ttf")
        QFontDatabase.addApplicationFont("assets/fonts/Roboto-Bold.ttf")

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.main_layout = QHBoxLayout()
        self.central_widget.setLayout(self.main_layout)

        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setStyleSheet("background-color: #1a1a1a;")
        self.sidebar_layout = QVBoxLayout()
        self.sidebar_layout.setContentsMargins(0, 20, 0, 20)
        self.sidebar_layout.setSpacing(10)

        logo_container = QWidget()
        logo_layout = QHBoxLayout()
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(10)

        center_container = QWidget()
        center_layout = QHBoxLayout()
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)  # Maintain 10px gap

        logo_text = QLabel("RoForge")
        logo_text.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")

        self.logo_img = QLabel()
        self.logo_img.setFixedSize(24, 24)
        self.set_logo_image("assets/images/play.png")

        center_layout.addWidget(logo_text)
        center_layout.addWidget(self.logo_img)

        logo_layout.addStretch()
        logo_layout.addLayout(center_layout)
        logo_layout.addStretch()

        logo_container.setLayout(logo_layout)
        self.sidebar_layout.addWidget(logo_container)

        self.btn_modpacks = QPushButton("Modpacks")
        self.btn_mods = QPushButton("Mods")
        self.btn_settings = QPushButton("Settings")

        for btn in [self.btn_modpacks, self.btn_mods, self.btn_settings]:
            btn.setFixedHeight(50)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: white;
                    font-size: 16px;
                    text-align: left;
                    padding-left: 20px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #2a2a2a;
                }
                QPushButton:pressed {
                    background-color: #3a3a3a;
                }
            """)
            self.sidebar_layout.addWidget(btn)

        self.sidebar_layout.addStretch()
        self.sidebar.setLayout(self.sidebar_layout)
        self.main_layout.addWidget(self.sidebar)

        self.content_area = QFrame()
        self.content_area.setStyleSheet("background-color: #222222;")
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(20, 20, 20, 20)

        self.stacked_widget = QStackedWidget()

        self.modpacks_page = QWidget()
        self.setup_modpacks_page()
        self.stacked_widget.addWidget(self.modpacks_page)

        self.mods_page = QWidget()
        self.setup_mods_page()
        self.stacked_widget.addWidget(self.mods_page)

        self.settings_page = QWidget()
        self.setup_settings_page()
        self.stacked_widget.addWidget(self.settings_page)

        self.content_layout.addWidget(self.stacked_widget)
        self.content_area.setLayout(self.content_layout)
        self.main_layout.addWidget(self.content_area)

        self.btn_modpacks.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        self.btn_mods.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        self.btn_settings.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(2))

        self.modpacks_dir = os.path.join(os.path.dirname(__file__), "ModPacks")
        if not os.path.exists(self.modpacks_dir):
            os.makedirs(self.modpacks_dir)
        self.modpacks = [f for f in os.listdir(self.modpacks_dir) if os.path.isdir(os.path.join(self.modpacks_dir, f))]
        global selected_modpack
        self.selected_modpack = None
        selected_modpack = self.selected_modpack
        self.update_modpacks_display()

        self.mod_states = {}

    def set_logo_image(self, icon_path):
        try:
            img = Image.open(icon_path)
            img = img.resize((24, 24))
            img.save("temp_logo.png")
            pixmap = QPixmap("temp_logo.png")
            os.remove("temp_logo.png")
            self.logo_img.setPixmap(pixmap)
        except Exception as e:
            print(f"Error loading logo: {str(e)}")
            # Fallback icon
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(100, 100, 100))
            self.logo_img.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'modpacks'):
            self.update_modpacks_display()

    def setup_modpacks_page(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QFrame()
        top_bar.setFixedHeight(60)
        top_bar.setStyleSheet("background-color: #2a2a2a; border-radius: 8px;")
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("Modpacks")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")

        self.btn_create_modpack = QPushButton("Create Modpack ➕")
        self.btn_import_modpack = QPushButton("Import Modpack 📥")

        for btn in [self.btn_create_modpack, self.btn_import_modpack]:
            btn.setFixedHeight(40)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3a;
                    color: white;
                    border-radius: 5px;
                    padding: 5px 15px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
            """)

        top_bar_layout.addWidget(title)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.btn_create_modpack)
        top_bar_layout.addWidget(self.btn_import_modpack)
        top_bar.setLayout(top_bar_layout)
        layout.addWidget(top_bar)

        self.modpacks_scroll = QScrollArea()
        self.modpacks_scroll.setWidgetResizable(True)
        self.modpacks_scroll.setStyleSheet("border: none;")

        self.modpacks_container = QWidget()
        self.modpacks_grid = QGridLayout()
        self.modpacks_grid.setSpacing(20)
        self.modpacks_grid.setContentsMargins(20, 20, 20, 20)

        self.modpacks_container.setLayout(self.modpacks_grid)
        self.modpacks_scroll.setWidget(self.modpacks_container)
        layout.addWidget(self.modpacks_scroll)

        self.btn_create_modpack.clicked.connect(self.show_create_modpack_dialog)
        self.btn_import_modpack.clicked.connect(self.import_modpack)

        self.modpacks_page.setLayout(layout)

    def setup_mods_page(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.top_bar_mods = QFrame()
        self.top_bar_mods.setFixedHeight(100)
        self.top_bar_mods.setStyleSheet("background-color: #2a2a2a; border-radius: 8px;")
        self.top_bar_mods_layout = QHBoxLayout()
        self.top_bar_mods_layout.setContentsMargins(20, 0, 20, 0)

        self.modpack_icon = QLabel()
        self.modpack_icon.setFixedSize(80, 80)
        self.modpack_icon.setStyleSheet("background-color: #333333; border-radius: 5px;")

        self.modpack_info = QFrame()
        self.modpack_info_layout = QVBoxLayout()
        self.modpack_info_layout.setContentsMargins(10, 0, 0, 0)

        self.modpack_name = QLabel("No modpack selected")
        self.modpack_name.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")

        self.modpack_actions = QFrame()
        self.modpack_actions_layout = QHBoxLayout()
        self.modpack_actions_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_launch = QPushButton("Launch ▶️")
        self.btn_update = QPushButton("Update 🔄")
        self.btn_export = QPushButton("Export 📤")
        self.btn_delete = QPushButton("Delete ❌")

        for btn in [self.btn_launch, self.btn_update, self.btn_export, self.btn_delete]:
            btn.setFixedHeight(30)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3a;
                    color: white;
                    border-radius: 5px;
                    padding: 5px 10px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
            """)
            self.modpack_actions_layout.addWidget(btn)

        self.modpack_actions.setLayout(self.modpack_actions_layout)

        self.modpack_info_layout.addWidget(self.modpack_name)
        self.modpack_info_layout.addWidget(self.modpack_actions)
        self.modpack_info.setLayout(self.modpack_info_layout)

        spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.top_bar_mods_layout.addWidget(self.modpack_icon)
        self.top_bar_mods_layout.addWidget(self.modpack_info)
        self.top_bar_mods_layout.addItem(spacer)
        self.top_bar_mods.setLayout(self.top_bar_mods_layout)
        layout.addWidget(self.top_bar_mods)

        filter_bar = QFrame()
        filter_bar.setFixedHeight(60)
        filter_bar.setStyleSheet("background-color: #2a2a2a; border-radius: 8px;")
        filter_bar_layout = QHBoxLayout()
        filter_bar_layout.setContentsMargins(20, 0, 20, 0)


        self.btn_manage_mods = QPushButton("Manage External Mods")
        self.btn_manage_mods.setFixedHeight(40)
        self.btn_manage_mods.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: white;
                border-radius: 5px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        self.btn_manage_mods.clicked.connect(show_external_mod_manager)
        filter_bar_layout.addWidget(self.btn_manage_mods)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search mods...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #333333;
                color: white;
                border: 1px solid #444444;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 14px;
            }
        """)

        self.btn_show_mods = QPushButton("Mods")
        self.btn_show_texturepacks = QPushButton("Texture Packs")
        self.btn_fflags = QPushButton("Fast Flags")

        for btn in [self.btn_show_mods, self.btn_show_texturepacks, self.btn_fflags]:
            btn.setFixedHeight(40)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3a;
                    color: white;
                    border-radius: 5px;
                    padding: 5px 15px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
            """)

        filter_bar_layout.addWidget(self.search_input)
        filter_bar_layout.addWidget(self.btn_show_mods)
        filter_bar_layout.addWidget(self.btn_show_texturepacks)
        filter_bar_layout.addWidget(self.btn_fflags)
        filter_bar.setLayout(filter_bar_layout)
        layout.addWidget(filter_bar)

        self.mods_scroll = QScrollArea()
        self.mods_scroll.setWidgetResizable(True)
        self.mods_scroll.setStyleSheet("border: none;")

        self.mods_container = QWidget()
        self.mods_layout = QVBoxLayout()
        self.mods_layout.setSpacing(10)
        self.mods_layout.setContentsMargins(0, 10, 0, 10)

        self.mods_container.setLayout(self.mods_layout)
        self.mods_scroll.setWidget(self.mods_container)
        layout.addWidget(self.mods_scroll)

        self.btn_launch.clicked.connect(self.launch_modpack)
        self.btn_update.clicked.connect(self.update_modpack)
        self.btn_export.clicked.connect(self.export_modpack)
        self.btn_delete.clicked.connect(self.delete_modpack)
        self.btn_show_mods.clicked.connect(lambda: self.filter_mods("mods"))
        self.btn_show_texturepacks.clicked.connect(lambda: self.filter_mods("texturepacks"))
        self.btn_fflags.clicked.connect(self.show_fflag_editor)
        self.search_input.textChanged.connect(self.filter_mods_by_search)

        self.mods_page.setLayout(layout)

    def setup_settings_page(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        settings_content = QFrame()
        settings_content.setStyleSheet("background-color: #2a2a2a; border-radius: 8px;")
        settings_layout = QVBoxLayout()
        settings_layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        settings_layout.addWidget(title)

        multi_instance_frame = QFrame()
        multi_instance_frame.setStyleSheet("background-color: #333333; border-radius: 5px;")
        multi_instance_layout = QHBoxLayout()
        multi_instance_layout.setContentsMargins(15, 10, 15, 10)

        multi_instance_label = QLabel("Enable Multi-Instance")
        multi_instance_label.setStyleSheet("font-size: 14px; color: white;")

        self.multi_instance_toggle = QCheckBox()
        self.multi_instance_toggle.setStyleSheet("""
            QCheckBox::indicator {
                width: 50px;
                height: 25px;
            }
            QCheckBox::indicator:checked {
                image: url(:/checked);
                background-color: #4CAF50;
                border-radius: 12px;
            }
            QCheckBox::indicator:unchecked {
                image: url(:/unchecked);
                background-color: #555555;
                border-radius: 12px;
            }
        """)

        multi_instance_layout.addWidget(multi_instance_label)
        multi_instance_layout.addStretch()
        multi_instance_layout.addWidget(self.multi_instance_toggle)
        multi_instance_frame.setLayout(multi_instance_layout)
        settings_layout.addWidget(multi_instance_frame)

        settings_layout.addStretch()
        settings_content.setLayout(settings_layout)
        layout.addWidget(settings_content)

        self.settings_page.setLayout(layout)

        self.multi_instance_toggle.stateChanged.connect(self.toggle_multi_roblox)

    def update_modpacks_display(self):
        for i in reversed(range(self.modpacks_grid.count())):
            widget = self.modpacks_grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        window_width = self.width()
        card_width = 180
        spacing = 20
        max_cols = max(2, window_width // (card_width + spacing))

        row, col = 0, 0

        for modpack in self.modpacks:
            icon_path = os.path.join(self.modpacks_dir, modpack, "image.png")
            if not os.path.exists(icon_path):
                icon_path = os.path.join("assets", "images", "play.png")

            card = ModpackCard(modpack, icon_path, self.select_modpack)
            card.setFixedSize(160, 180)  # Set fixed size for consistency

            self.modpacks_grid.addWidget(card, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        self.modpacks_grid.setRowStretch(row + 1, 1)
        for c in range(max_cols):
            self.modpacks_grid.setColumnStretch(c, 1)

    def select_modpack(self, modpack_name):
        self.selected_modpack = modpack_name
        global selected_modpack
        selected_modpack = self.selected_modpack

        self.modpack_name.setText(modpack_name)

        icon_path = os.path.join(self.modpacks_dir, modpack_name, "image.png")
        if os.path.exists(icon_path):
            img = Image.open(icon_path)
            img = img.resize((80, 80))
            img.save("temp_modpack_icon.png")
            pixmap = QPixmap("temp_modpack_icon.png")
            os.remove("temp_modpack_icon.png")
            self.modpack_icon.setPixmap(pixmap)
        else:
            self.modpack_icon.setPixmap(QPixmap(80, 80))

        self.stacked_widget.setCurrentIndex(1)

        self.load_mod_states(modpack_name)

    def load_mod_states(self, modpack_name):
        for i in reversed(range(self.mods_layout.count())):
            self.mods_layout.itemAt(i).widget().setParent(None)

        mod_state_path = os.path.join(self.modpacks_dir, modpack_name, "mod_state.json")
        if not os.path.exists(mod_state_path):
            return

        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

        internal_mods = [
            ("R63 avatar", replace_character_meshes, os.path.join("assets", "images", "girl.jpg")),
            ("Faster inputs", faster_inputs, os.path.join("assets", "images", "keyboard.png")),
            ("Replace Font", replace_font, os.path.join("assets", "images", "Replace Font.png")),
            ("Optimizer", apply_optimizer, os.path.join("assets", "images", "Optimizer.png")),
            ("Cheat", apply_cheat, os.path.join("assets", "images", "cheat.png")),
            ("Change celestial bodies", apply_day_night_cycle, os.path.join("assets", "images", "moon.jpg")),
            ("Hide gui", apply_hide_gui, os.path.join("assets", "images", "hide.png")),
            ("Remove grass", apply_remove_grass_mesh, os.path.join("assets", "images", "grass.png")),
            ("Display fps", apply_display_fps, os.path.join("assets", "images", "displayfps.png")),
            ("Disable remotes", disable_remotes, os.path.join("assets", "images", "RemoteEvent.png")),
            ("Unlock fps", unlock_fps, os.path.join("assets", "images", "unlock_fps.png")),
            ("Custom death sound", apply_custom_ouch_sound, os.path.join("assets", "images", "noob.png")),
            ("Google browser", google_browser, os.path.join("assets", "images", "google.png")),
            ("Chat gpt", chat_gpt, os.path.join("assets", "images", "ChatGPT_logo.svg.png")),
            ("Graphic boost", graphic_boost, os.path.join("assets", "images", "graphics.png")),
            ("Beautiful sky", beautiful_sky, os.path.join("assets", "images", "beautiful.png")),
            ("Anime chan sky", anime_chan_sky, os.path.join("assets", "images", "Chan.png")),
            ("Bloxstrap Theme", apply_bloxstrap_theme, os.path.join("assets", "images", "bloxstrap.png")),
        ]

        for mod_name, mod_function, icon_path in internal_mods:
            internal_name = MOD_NAME_MAPPING.get(mod_name, mod_name.lower().replace(' ', '_'))
            enabled = mod_state.get(internal_name, False)

            mod_switch = ModSwitch(
                mod_name,
                icon_path,
                lambda state, m=mod_name, f=mod_function: self.toggle_mod(m, f, state)
            )
            mod_switch.toggle.setChecked(enabled)
            self.mods_layout.addWidget(mod_switch)

        external_mods = load_external_mods()
        for internal_name, mod_info in external_mods.items():
            if not validate_external_mod_entry(internal_name, mod_info):
                continue

            mod_name = mod_info["name"]
            icon_path = mod_info["icon_path"]
            enabled = mod_state.get(internal_name, False)

            with open(mod_info["config_path"], "r") as f:
                mod_config = json.load(f)

            mod_switch = ModSwitch(
                mod_name,
                icon_path,
                lambda state, iname=internal_name, config=mod_config: self.toggle_external_mod(iname, config, state)
            )
            mod_switch.toggle.setChecked(enabled)
            self.mods_layout.addWidget(mod_switch)

        self.filter_mods(current_filter)

    def toggle_mod(self, mod_name, mod_function, state):
        if not self.selected_modpack:
            QMessageBox.warning(self, "Warning", "Please select a modpack first.")
            return

        mod_state_path = os.path.join(self.modpacks_dir, self.selected_modpack, "mod_state.json")
        mod_state = {}
        if os.path.exists(mod_state_path):
            with open(mod_state_path, "r") as f:
                mod_state = json.load(f)

        internal_name = MOD_NAME_MAPPING.get(mod_name, mod_name.lower().replace(' ', '_'))

        if internal_name in mod_state and mod_state[internal_name] == state:
            return

        try:
            mod_function(state)

            mod_state[internal_name] = state
            with open(mod_state_path, "w") as f:
                json.dump(mod_state, f, indent=4)

            if state and mod_name in CONFLICTING_MODS:
                self.handle_mod_conflicts(mod_name)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to toggle mod: {str(e)}")

    def toggle_external_mod(self, internal_name, mod_config, state):
        if not self.selected_modpack:
            QMessageBox.warning(self, "Warning", "Please select a modpack first.")
            return

        mod_state_path = os.path.join(self.modpacks_dir, self.selected_modpack, "mod_state.json")
        mod_state = {}
        if os.path.exists(mod_state_path):
            with open(mod_state_path, "r") as f:
                mod_state = json.load(f)

        # Only apply if state has changed
        if internal_name in mod_state and mod_state[internal_name] == state:
            return

        try:
            apply_external_mod(self.selected_modpack, internal_name, mod_config, state)

            mod_state[internal_name] = state
            with open(mod_state_path, "w") as f:
                json.dump(mod_state, f, indent=4)

            if state and mod_config.get("name") in CONFLICTING_MODS:
                self.handle_mod_conflicts(mod_config.get("name"))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to toggle mod: {str(e)}")

    def handle_mod_conflicts(self, activated_display_name):
        if not self.selected_modpack or activated_display_name not in CONFLICTING_MODS:
            return

        mod_state_path = os.path.join(self.modpacks_dir, self.selected_modpack, "mod_state.json")
        if not os.path.exists(mod_state_path):
            return

        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)

        changed = False
        for conflicting_display_name in CONFLICTING_MODS[activated_display_name]:
            internal_key = MOD_NAME_MAPPING.get(conflicting_display_name)
            if not internal_key:
                continue

            if internal_key in mod_state and mod_state[internal_key]:
                mod_state[internal_key] = False
                changed = True

                # Update the UI
                for i in range(self.mods_layout.count()):
                    widget = self.mods_layout.itemAt(i).widget()
                    if isinstance(widget, ModSwitch) and widget.name_label.text() == conflicting_display_name:
                        widget.toggle.setChecked(False)
                        break

        if changed:
            with open(mod_state_path, "w") as f:
                json.dump(mod_state, f, indent=4)

    def filter_mods(self, filter_type):
        global current_filter
        current_filter = filter_type

        for i in range(self.mods_layout.count()):
            widget = self.mods_layout.itemAt(i).widget()
            if isinstance(widget, ModSwitch):
                mod_name = widget.name_label.text()
                matches_filter = (
                        (filter_type == "mods" and mod_name not in texture_packs) or
                        (filter_type == "texturepacks" and mod_name in texture_packs)
                )
                widget.setVisible(matches_filter)

    def filter_mods_by_search(self):
        search_term = self.search_input.text().lower()

        for i in range(self.mods_layout.count()):
            widget = self.mods_layout.itemAt(i).widget()
            if isinstance(widget, ModSwitch):
                mod_name = widget.name_label.text().lower()
                matches_search = search_term in mod_name
                widget.setVisible(matches_search)

    def show_create_modpack_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Modpack")
        dialog.setFixedSize(400, 300)

        layout = QVBoxLayout()

        name_label = QLabel("Modpack Name:")
        name_label.setStyleSheet("color: white;")
        self.modpack_name_input = QLineEdit()
        self.modpack_name_input.setStyleSheet("""
            QLineEdit {
                background-color: #333333;
                color: white;
                border: 1px solid #444444;
                border-radius: 5px;
                padding: 5px 10px;
            }
        """)

        image_label = QLabel("Modpack Image:")
        image_label.setStyleSheet("color: white;")

        self.image_path = ""
        self.image_preview = QLabel()
        self.image_preview.setFixedSize(100, 100)
        self.image_preview.setStyleSheet("background-color: #333333; border-radius: 5px;")

        btn_select_image = QPushButton("Select Image")
        btn_select_image.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: white;
                border-radius: 5px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        btn_select_image.clicked.connect(self.select_modpack_image)

        btn_frame = QFrame()
        btn_layout = QHBoxLayout()

        btn_create = QPushButton("Create")
        btn_create.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #5CBF5C;
            }
        """)
        btn_create.clicked.connect(lambda: self.create_modpack(dialog))

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 5px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #ff5346;
            }
        """)
        btn_cancel.clicked.connect(dialog.reject)

        btn_layout.addWidget(btn_create)
        btn_layout.addWidget(btn_cancel)
        btn_frame.setLayout(btn_layout)

        layout.addWidget(name_label)
        layout.addWidget(self.modpack_name_input)
        layout.addWidget(image_label)
        layout.addWidget(self.image_preview)
        layout.addWidget(btn_select_image)
        layout.addStretch()
        layout.addWidget(btn_frame)

        dialog.setLayout(layout)
        dialog.exec()

    def select_modpack_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Modpack Image",
            "",
            "Image Files (*.png *.jpg *.jpeg)")

        if file_path:
            self.image_path = file_path
            img = Image.open(file_path)
            img = img.resize((100, 100))
            img.save("temp_preview.png")
            pixmap = QPixmap("temp_preview.png")
            os.remove("temp_preview.png")
            self.image_preview.setPixmap(pixmap)

    def create_modpack(self, dialog):
        name = self.modpack_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Please enter a modpack name.")
            return

        loading_dialog = LoadingDialog(self, "Creating modpack...")
        loading_dialog.show()

        self.create_thread = CreateModpackThread(name, self.image_path)
        self.create_thread.finished.connect(lambda: self.on_modpack_created(name, loading_dialog, dialog))
        self.create_thread.start()

    def on_modpack_created(self, modpack_name, loading_dialog, dialog):
        loading_dialog.close()

        if modpack_name not in self.modpacks:
            self.modpacks.append(modpack_name)

        self.update_modpacks_display()
        dialog.accept()
        QMessageBox.information(self, "Success", f"Modpack '{modpack_name}' created successfully!")

    def import_modpack(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Modpack",
            "",
            "RoForge Modpack (*.roforgepack)")

        if not file_path:
            return

        try:
            with open(file_path, 'r') as f:
                imported_mod_state = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read import file: {str(e)}")
            return

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Import Modpack")
        dialog.setLabelText("Enter a name for the new imported modpack:")
        dialog.setStyleSheet("""
                    QInputDialog {
                        background-color: #2a2a2a;
                        color: white;
                    }
                    QLabel {
                        color: white;
                    }
                    QLineEdit {
                        background-color: #333333;
                        color: white;
                        border: 1px solid #444444;
                    }
                """)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_modpack_name = dialog.textValue().strip()
            if not new_modpack_name:
                QMessageBox.warning(self, "Warning", "Please enter a modpack name.")
                return

            if new_modpack_name in self.modpacks:
                QMessageBox.warning(self, "Warning", f"A modpack named '{new_modpack_name}' already exists.")
                return

            loading_dialog = LoadingDialog(self, f"Importing modpack '{new_modpack_name}'...")
            loading_dialog.show()

            self.import_thread = ImportModpackThread(new_modpack_name, imported_mod_state)
            self.import_thread.finished.connect(lambda: self.on_modpack_imported(new_modpack_name, loading_dialog))
            self.import_thread.start()

    def on_modpack_imported(self, modpack_name, loading_dialog):
        loading_dialog.close()

        if modpack_name not in self.modpacks:
            self.modpacks.append(modpack_name)

        self.update_modpacks_display()
        self.select_modpack(modpack_name)
        QMessageBox.information(self, "Success", f"Modpack '{modpack_name}' imported successfully!")

    def launch_modpack(self):
        if not self.selected_modpack:
            QMessageBox.warning(self, "Warning", "Please select a modpack first.")
            return

        try:
            roblox_path = os.path.join(self.modpacks_dir, self.selected_modpack, "RobloxCopy")
            version = os.listdir(roblox_path)[0]
            roblox_exe_path = os.path.join(roblox_path, version, "RobloxPlayerBeta.exe")

            subprocess.Popen([roblox_exe_path])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch modpack: {str(e)}")

    def update_modpack(self):
        if not self.selected_modpack:
            QMessageBox.warning(self, "Warning", "Please select a modpack first.")
            return

        loading_dialog = LoadingDialog(self, "Updating modpack...")
        loading_dialog.show()

        self.update_thread = UpdateModpackThread(self.selected_modpack)
        self.update_thread.finished.connect(lambda: self.on_modpack_updated(loading_dialog))
        self.update_thread.start()

    def on_modpack_updated(self, loading_dialog):
        loading_dialog.close()
        QMessageBox.information(self, "Success", "Modpack updated successfully!")

    def export_modpack(self):
        if not self.selected_modpack:
            QMessageBox.warning(self, "Warning", "Please select a modpack first.")
            return

        mod_state_path = os.path.join(self.modpacks_dir, self.selected_modpack, "mod_state.json")
        if not os.path.exists(mod_state_path):
            QMessageBox.critical(self, "Error", f"Mod state file not found for '{self.selected_modpack}'")
            return

        try:
            with open(mod_state_path, 'r') as f:
                mod_state = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read mod state: {str(e)}")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Modpack",
            f"{self.selected_modpack}.roforgepack",
            "RoForge Modpack (*.roforgepack)")

        if not file_path:
            return

        try:
            with open(file_path, 'w') as f:
                json.dump(mod_state, f, indent=4)

            QMessageBox.information(
                self,
                "Success",
                f"Modpack '{self.selected_modpack}' exported to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export modpack: {str(e)}")

    def delete_modpack(self):
        if not self.selected_modpack:
            QMessageBox.warning(self, "Warning", "Please select a modpack first.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the modpack '{self.selected_modpack}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.No:
            return

        try:
            modpack_path = os.path.join(self.modpacks_dir, self.selected_modpack)
            shutil.rmtree(modpack_path)

            self.modpacks.remove(self.selected_modpack)
            self.selected_modpack = None
            selected_modpack = self.selected_modpack
            self.update_modpacks_display()

            self.stacked_widget.setCurrentIndex(0)

            QMessageBox.information(self, "Success", "Modpack deleted successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete modpack: {str(e)}")

    def show_fflag_editor(self):
        if not self.selected_modpack:
            QMessageBox.warning(self, "Warning", "Please select a modpack first.")
            return

        try:
            roblox_path = os.path.join(self.modpacks_dir, self.selected_modpack, "RobloxCopy")
            version = os.listdir(roblox_path)[0]
            settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

            with open(settings_path, 'r') as f:
                settings = json.load(f)

            dialog = QDialog(self)
            dialog.setWindowTitle("Fast Flags Editor")
            dialog.setMinimumSize(800, 600)

            layout = QVBoxLayout()

            toolbar = QToolBar()

            save_preset_action = QAction("Save Preset", dialog)
            save_preset_action.setIcon(QIcon.fromTheme("document-save"))
            save_preset_action.triggered.connect(lambda: self.save_fflag_preset(editor.toPlainText()))
            toolbar.addAction(save_preset_action)

            load_preset_action = QAction("Load Preset", dialog)
            load_preset_action.setIcon(QIcon.fromTheme("document-open"))
            load_preset_action.triggered.connect(lambda: self.load_fflag_preset(editor))
            toolbar.addAction(load_preset_action)

            toolbar.addSeparator()

            clear_action = QAction("Clear Flags", dialog)
            clear_action.setIcon(QIcon.fromTheme("edit-clear"))
            clear_action.triggered.connect(lambda: editor.setPlainText("{}"))
            toolbar.addAction(clear_action)

            layout.addWidget(toolbar)

            editor = QTextEdit()
            editor.setPlainText(json.dumps(settings, indent=4))
            editor.setStyleSheet("""
                QTextEdit {
                    background-color: #333333;
                    color: white;
                    font-family: Consolas, monospace;
                    font-size: 12px;
                }
            """)

            btn_frame = QFrame()
            btn_layout = QHBoxLayout()

            btn_save = QPushButton("Save")
            btn_save.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border-radius: 5px;
                    padding: 5px 15px;
                }
                QPushButton:hover {
                    background-color: #5CBF5C;
                }
            """)
            btn_save.clicked.connect(lambda: self.save_fflags(editor.toPlainText(), dialog))

            btn_cancel = QPushButton("Cancel")
            btn_cancel.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    border-radius: 5px;
                    padding: 5px 15px;
                }
                QPushButton:hover {
                    background-color: #ff5346;
                }
            """)
            btn_cancel.clicked.connect(dialog.reject)

            btn_layout.addWidget(btn_save)
            btn_layout.addWidget(btn_cancel)
            btn_frame.setLayout(btn_layout)

            layout.addWidget(editor)
            layout.addWidget(btn_frame)
            dialog.setLayout(layout)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open FFlag editor: {str(e)}")

    def save_fflag_preset(self, fflags_text):
        try:
            # Validate JSON first
            json.loads(fflags_text)

            # Get preset name
            name, ok = QInputDialog.getText(
                self,
                "Save Preset",
                "Enter a name for this preset:",
                QLineEdit.EchoMode.Normal,
                "")

            if not ok or not name.strip():
                return

            presets_dir = os.path.join(os.path.dirname(__file__), "Presets")
            if not os.path.exists(presets_dir):
                os.makedirs(presets_dir)

            preset_path = os.path.join(presets_dir, f"{name}.json")
            with open(preset_path, 'w') as f:
                f.write(fflags_text)

            QMessageBox.information(self, "Success", f"Preset '{name}' saved successfully!")
        except json.JSONDecodeError:
            QMessageBox.critical(self, "Error", "Invalid JSON content. Please check the syntax.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save preset: {str(e)}")

    def load_fflag_preset(self, editor):
        try:
            presets_dir = os.path.join(os.path.dirname(__file__), "Presets")
            if not os.path.exists(presets_dir):
                QMessageBox.information(self, "Info", "No presets found.")
                return

            presets = [f[:-5] for f in os.listdir(presets_dir) if f.endswith('.json')]
            if not presets:
                QMessageBox.information(self, "Info", "No presets found.")
                return

            preset, ok = QInputDialog.getItem(
                self,
                "Load Preset",
                "Select a preset to load:",
                presets,
                0,
                False)

            if not ok:
                return

            preset_path = os.path.join(presets_dir, f"{preset}.json")
            with open(preset_path, 'r') as f:
                preset_data = f.read()

            json.loads(preset_data)

            editor.setPlainText(preset_data)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load preset: {str(e)}")

    def save_fflags(self, fflags_text, dialog):
        try:
            settings = json.loads(fflags_text)

            roblox_path = os.path.join(self.modpacks_dir, self.selected_modpack, "RobloxCopy")
            version = os.listdir(roblox_path)[0]
            settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

            with open(settings_path, 'w') as f:
                json.dump(settings, f, indent=4)

            QMessageBox.information(self, "Success", "Fast flags saved successfully!")
            dialog.accept()
        except json.JSONDecodeError:
            QMessageBox.critical(self, "Error", "Invalid JSON content. Please check the syntax.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save fast flags: {str(e)}")

    def toggle_multi_roblox(self, state):
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.GetCurrentProcess()
        mutexes = [
            "ROBLOX_singletonMutex",
            "ROBLOX_singletonEvent",
            "ROBLOX_SingletonEvent",
            "RobloxMultiplayerPipe",
            "RobloxGameExplorer"
        ]
        mutex_handles = []

        if state:
            for mutex_name in mutexes:
                mutex = kernel32.CreateMutexW(None, False, mutex_name)
                if mutex == 0:
                    continue
                mutex_handles.append(mutex)
            print("Enabled multi-instance")
        else:
            for mutex_name in mutexes:
                mutex = kernel32.OpenMutexW(0x0001, False, mutex_name)
                if mutex == 0:
                    continue
                kernel32.ReleaseMutex(mutex)
                kernel32.CloseHandle(mutex)
            print("Disabled multi-instance")

class CreateModpackThread(QThread):
        def __init__(self, name, image_path):
            super().__init__()
            self.name = name
            self.image_path = image_path

        def run(self):
            try:
                folder = get_roblox_folder()
                if folder is None:
                    self.finished.emit()
                    return

                version = os.path.basename(folder)
                script_dir = os.path.dirname(os.path.abspath(__file__))
                modpack_folder = os.path.join(script_dir, "ModPacks", self.name)

                if os.path.exists(modpack_folder):
                    self.finished.emit()
                    return

                modpacks_dir = os.path.join(script_dir, "ModPacks")
                if not os.path.exists(modpacks_dir):
                    os.makedirs(modpacks_dir)

                dst_folder = os.path.join(modpack_folder, "RobloxCopy", version)
                shutil.copytree(folder, dst_folder, copy_function=shutil.copy2, dirs_exist_ok=True)

                settings_folder = os.path.join(dst_folder, "ClientSettings")
                os.makedirs(settings_folder, exist_ok=True)
                settings_file = os.path.join(settings_folder, "ClientAppSettings.json")
                if not os.path.exists(settings_file):
                    with open(settings_file, "w") as f:
                        json.dump({}, f, indent=4)

                mod_state_path = os.path.join(modpack_folder, "mod_state.json")
                mod_state = {internal_name: False for internal_name in MOD_NAME_MAPPING.values()}

                external_mods = load_external_mods()
                for internal_name in external_mods.keys():
                    mod_state[internal_name] = False

                with open(mod_state_path, "w") as f:
                    json.dump(mod_state, f, indent=4)

                target_image_path = os.path.join(modpack_folder, "image.png")
                if self.image_path and os.path.exists(self.image_path):
                    shutil.copy(self.image_path, target_image_path)
                else:
                    default_img = os.path.join("assets", "images", "play.png")
                    if os.path.exists(default_img):
                        shutil.copy(default_img, target_image_path)

                self.finished.emit()
            except Exception as e:
                print(f"Error creating modpack: {str(e)}")
                self.finished.emit()

class ImportModpackThread(QThread):
        def __init__(self, name, mod_state):
            super().__init__()
            self.name = name
            self.mod_state = mod_state

        def run(self):
            try:
                folder = get_roblox_folder()
                if folder is None:
                    self.finished.emit()
                    return

                version = os.path.basename(folder)
                script_dir = os.path.dirname(os.path.abspath(__file__))
                modpack_folder = os.path.join(script_dir, "ModPacks", self.name)

                if os.path.exists(modpack_folder):
                    self.finished.emit()
                    return

                modpacks_dir = os.path.join(script_dir, "ModPacks")
                if not os.path.exists(modpacks_dir):
                    os.makedirs(modpacks_dir)

                dst_folder = os.path.join(modpack_folder, "RobloxCopy", version)
                shutil.copytree(folder, dst_folder, copy_function=shutil.copy2, dirs_exist_ok=True)

                settings_folder = os.path.join(dst_folder, "ClientSettings")
                os.makedirs(settings_folder, exist_ok=True)
                settings_file = os.path.join(settings_folder, "ClientAppSettings.json")
                if not os.path.exists(settings_file):
                    with open(settings_file, "w") as f:
                        json.dump({}, f, indent=4)

                default_mod_state = {internal_name: False for internal_name in MOD_NAME_MAPPING.values()}
                for mod in self.mod_state:
                    default_mod_state[mod] = self.mod_state[mod]

                external_mods = load_external_mods()
                for internal_name in external_mods.keys():
                    if internal_name not in default_mod_state:
                        default_mod_state[internal_name] = False

                mod_state_path = os.path.join(modpack_folder, "mod_state.json")
                with open(mod_state_path, "w") as f:
                    json.dump(default_mod_state, f, indent=4)

                target_image_path = os.path.join(modpack_folder, "image.png")
                default_img = os.path.join("assets", "images", "play.png")
                if os.path.exists(default_img):
                    shutil.copy(default_img, target_image_path)

                self.finished.emit()
            except Exception as e:
                print(f"Error importing modpack: {str(e)}")
                self.finished.emit()

class UpdateModpackThread(QThread):
        def __init__(self, modpack_name):
            super().__init__()
            self.modpack_name = modpack_name

        def run(self):
            try:
                current_roblox_path = get_roblox_folder()
                if not current_roblox_path:
                    self.finished.emit()
                    return

                current_version = os.path.basename(current_roblox_path)
                modpack_dir = os.path.join(os.path.dirname(__file__), "ModPacks", self.modpack_name)
                roblox_copy_dir = os.path.join(modpack_dir, "RobloxCopy")

                existing_versions = os.listdir(roblox_copy_dir)
                if not existing_versions:
                    self.finished.emit()
                    return

                existing_version = existing_versions[0]
                if existing_version == current_version:
                    self.finished.emit()
                    return

                mod_state_path = os.path.join(modpack_dir, "mod_state.json")
                with open(mod_state_path, "r") as f:
                    mod_states = json.load(f)

                shutil.rmtree(roblox_copy_dir)
                new_version_path = os.path.join(roblox_copy_dir, current_version)
                shutil.copytree(current_roblox_path, new_version_path)

                settings_dir = os.path.join(new_version_path, "ClientSettings")
                os.makedirs(settings_dir, exist_ok=True)
                settings_file = os.path.join(settings_dir, "ClientAppSettings.json")
                if not os.path.exists(settings_file):
                    with open(settings_file, "w") as f:
                        json.dump({}, f, indent=4)

                reapply_enabled_mods(self.modpack_name)
                self.finished.emit()
            except Exception as e:
                print(f"Error updating modpack: {str(e)}")
                self.finished.emit()

if __name__ == "__main__":
    app = QApplication([])

    app.setStyle("Fusion")
    dark_palette = app.palette()
    dark_palette.setColor(dark_palette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(dark_palette.ColorRole.WindowText, Qt.GlobalColor.white)
    dark_palette.setColor(dark_palette.ColorRole.Base, QColor(35, 35, 35))
    dark_palette.setColor(dark_palette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(dark_palette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    dark_palette.setColor(dark_palette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    dark_palette.setColor(dark_palette.ColorRole.Text, Qt.GlobalColor.white)
    dark_palette.setColor(dark_palette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(dark_palette.ColorRole.ButtonText, Qt.GlobalColor.white)
    dark_palette.setColor(dark_palette.ColorRole.BrightText, Qt.GlobalColor.red)
    dark_palette.setColor(dark_palette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(dark_palette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(dark_palette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    app.setPalette(dark_palette)

    window = MainWindow()
    window.show()
    app.exec()
