import os
import json
import shutil
import threading
import subprocess
import time
import tkinter as tk
import queue
import uuid

import zipfile
import customtkinter as Ctk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox, Text, Scrollbar
import pywinstyles
import math
import winreg
import ctypes
import logging
from customtkinter import CTkInputDialog


'''Constants...'''

current_filter = "mods"

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

external_mods_dir = os.path.join(os.path.dirname(__file__), "ExternalMods")
if not os.path.exists(external_mods_dir):
    os.makedirs(external_mods_dir)

external_mods_file = os.path.join(external_mods_dir, "external_mods.json")
if not os.path.exists(external_mods_file):
    with open(external_mods_file, "w") as f:
        json.dump({}, f, indent=4)



'''Functions'''


def load_external_mods():
    with open(external_mods_file, "r") as f:
        return json.load(f)


def save_external_mods(external_mods):
    with open(external_mods_file, "w") as f:
        json.dump(external_mods, f, indent=4)


def generate_unique_internal_name(mod_name):
    base_name = mod_name.replace(' ', '_').lower()
    unique_id = str(uuid.uuid4())[:8]
    return f"external_{base_name}_{unique_id}"


def import_external_mod():
    import_path = filedialog.askopenfilename(
        filetypes=[("RoForge Mod", "*.zip"), ("All Files", "*.*")],
        title="Import External Mod or Texture Pack"
    )
    if not import_path:
        return

    loading_window = show_loading_screen("Importing external mod...")
    result_queue = queue.Queue()

    thread = threading.Thread(
        target=_import_external_mod_worker,
        args=(import_path, result_queue),
        daemon=True
    )
    thread.start()

    app.after(100, check_external_mod_queue, loading_window, result_queue)


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
                selected_modpack.get(),
                internal_name,
                mod_config,
                enabled)

        mod_apply_functions[internal_name] = mod_apply_function

        app.after(
            0,
            lambda: add_mod_switch(
                mod_name,
                mod_apply_functions[internal_name],
                external_mods[internal_name]["icon_path"]))

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
            loading_window.label.configure(text=msg_data)
            app.after(
                100,
                check_external_mod_queue,
                loading_window,
                result_queue)
        elif msg_type == "error":
            loading_window.destroy()
            messagebox.showerror("Import Error", msg_data)
        elif msg_type == "warning":
            loading_window.destroy()
            messagebox.showwarning("Warning", msg_data)
        elif msg_type == "log_warning":
            logging.warning(msg_data)
            app.after(
                100,
                check_external_mod_queue,
                loading_window,
                result_queue)
        elif msg_type == "success":
            loading_window.destroy()
            messagebox.showinfo(
                "Success",
                f"Mod '{msg_data}' imported successfully and available for all modpacks!")
            filter_mods(current_filter)

    except queue.Empty:
        app.after(100, check_external_mod_queue, loading_window, result_queue)
    except Exception as e:
        loading_window.destroy()
        messagebox.showerror(
            "Error", f"Unexpected error during mod import: {e}")


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

        external_mods = load_external_mods()
        for internal_name, enabled in mod_state.items():
            if internal_name.startswith("external_") and enabled:
                mod_info = external_mods.get(internal_name)
                if not mod_info:
                    logging.warning(
                        f"External mod {internal_name} not found in external_mods.json")
                    continue
                if not validate_external_mod_entry(internal_name, mod_info):
                    continue
                try:
                    with open(mod_info["config_path"], "r") as f:
                        mod_config = json.load(f)
                    logging.info(
                        f"Reapplying enabled mod {mod_info['name']} ({internal_name}) for modpack {modpack}")
                    apply_external_mod(
                        modpack, internal_name, mod_config, True)
                except Exception as e:
                    logging.error(
                        f"Failed to reapply mod {internal_name}: {str(e)}")
    except Exception as e:
        logging.error(
            f"Error reading mod_state.json for modpack {modpack}: {str(e)}")


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


def load_global_mods():
    external_mods = load_external_mods()
    invalid_mods = []

    for internal_name, mod_info in external_mods.items():
        if not validate_external_mod_entry(internal_name, mod_info):
            invalid_mods.append(internal_name)
            continue

        try:
            mod_name = mod_info["name"]
            mod_type = mod_info["type"]
            mod_config_path = mod_info["config_path"]
            icon_path = mod_info["icon_path"]

            with open(mod_config_path, "r") as f:
                mod_config = json.load(f)

            def mod_apply_function(
                    enabled,
                    iname=internal_name,
                    config=mod_config):
                apply_external_mod(
                    selected_modpack.get(), iname, config, enabled)

            mod_apply_functions[internal_name] = mod_apply_function
            logging.debug(
                f"Registered mod_apply_function for {internal_name} ({mod_name})")

            if mod_type == "texturepack" and mod_name not in texture_packs:
                texture_packs.append(mod_name)

            if mod_name not in MOD_NAME_MAPPING:
                MOD_NAME_MAPPING[mod_name] = internal_name
                INTERNAL_TO_DISPLAY[internal_name] = mod_name
                CONFLICTING_MODS[mod_name] = mod_config.get("conflicts", [])

        except Exception as e:
            logging.error(
                f"Failed to load external mod {internal_name}: {str(e)}")
            invalid_mods.append(internal_name)

    if invalid_mods:
        for internal_name in invalid_mods:
            external_mods.pop(internal_name, None)
        save_external_mods(external_mods)
        logging.warning(f"Removed invalid mod entries: {invalid_mods}")

def create_client_settings():
    folder = get_roblox_folder()
    if folder is None:
        print("Roblox installation not found.")
        return None

    version = os.path.basename(folder)

    dst_folder = os.path.join(os.path.dirname(__file__), "RobloxCopy", version)
    if os.path.exists(dst_folder):
        print(
            f"Roblox folder with version {version} already exists in project directory.")
        return dst_folder

    shutil.copytree(folder, dst_folder)
    print(f"Copied Roblox folder to {dst_folder}")

    settings_folder = os.path.join(dst_folder, "ClientSettings")
    if not os.path.exists(settings_folder):
        os.makedirs(settings_folder)
        print(f"Created ClientSettings folder at: {settings_folder}")

    return dst_folder


def show_loading_screen(message):
    loading_window = Ctk.CTkToplevel(app)
    loading_window.title("Loading...")
    loading_window.geometry("300x150")
    loading_window.resizable(False, False)
    loading_window.transient(app)
    loading_window.grab_set()

    app_width = app.winfo_width()
    app_height = app.winfo_height()
    app_x = app.winfo_x()
    app_y = app.winfo_y()
    x = app_x + (app_width // 2) - 150
    y = app_y + (app_height // 2) - 75
    loading_window.geometry(f"+{x}+{y}")

    loading_window.label = Ctk.CTkLabel(
        loading_window,
        text=message,
        font=Ctk.CTkFont(
            size=14))
    loading_window.label.pack(pady=20, padx=20, fill='x')

    loading_window.progressbar = Ctk.CTkProgressBar(
        loading_window, mode='indeterminate')
    loading_window.progressbar.pack(pady=10, padx=20, fill='x')
    loading_window.progressbar.start()

    loading_window.update_idletasks()
    return loading_window


def _create_modpack_worker(name, img_path_or_none, result_queue):
    try:

        result_queue.put(("status", "Finding Roblox installation..."))
        folder = get_roblox_folder()
        if folder is None:

            result_queue.put(("error", "Roblox installation not found."))
            return

        version = os.path.basename(folder)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        modpack_folder = os.path.join(script_dir, "ModPacks", name)

        if os.path.exists(modpack_folder):
            result_queue.put(("warning", f"Modpack '{name}' already exists."))
            return

        modpacks_dir = os.path.join(script_dir, "ModPacks")
        if not os.path.exists(modpacks_dir):
            os.makedirs(modpacks_dir)

        result_queue.put(
            ("status", f"Copying Roblox files ({version[:10]})..."))
        dst_folder = os.path.join(modpack_folder, "RobloxCopy", version)
        shutil.copytree(
            folder,
            dst_folder,
            copy_function=shutil.copy2,
            dirs_exist_ok=True)

        result_queue.put(("status", "Creating settings..."))
        settings_folder = os.path.join(dst_folder, "ClientSettings")
        os.makedirs(settings_folder, exist_ok=True)
        settings_file = os.path.join(settings_folder, "ClientAppSettings.json")
        if not os.path.exists(settings_file):
            with open(settings_file, "w") as f:
                json.dump({}, f, indent=4)

        result_queue.put(("status", "Finalizing modpack..."))
        target_image_path = os.path.join(modpack_folder, "image.png")
        if img_path_or_none and img_path_or_none != "None":
            if os.path.exists(img_path_or_none):
                shutil.copy(img_path_or_none, target_image_path)
            else:

                result_queue.put(
                    ("log_warning", f"Selected image not found: {img_path_or_none}. Using default."))
                default_img = os.path.join(images_folder, "play.png")
                if os.path.exists(default_img):
                    shutil.copy(default_img, target_image_path)
                else:
                    result_queue.put(
                        ("log_warning", "Default image 'play.png' not found."))

        else:
            default_img = os.path.join(images_folder, "play.png")
            if os.path.exists(default_img):
                shutil.copy(default_img, target_image_path)
            else:
                result_queue.put(
                    ("log_warning", "Default image 'play.png' not found."))

        result_queue.put(("success", name))

    except Exception as e:
        logging.error(
            f"Error creating modpack in worker thread: {e}",
            exc_info=True)

        result_queue.put(("error", f"Failed to create modpack: {str(e)}"))


def handle_mod_conflicts(activated_display_name):
    modpack = selected_modpack.get()
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


def filter_mods(filter_type):
    global current_filter
    current_filter = filter_type
    search_term = search_entry.get().lower() if hasattr(search_entry, 'get') else ""
    for child in mods.winfo_children():
        if isinstance(child, Ctk.CTkFrame):
            mod_name = ""
            for widget in child.winfo_children():
                if isinstance(widget, Ctk.CTkLabel) and widget.cget("text"):
                    mod_name = widget.cget("text")
                    break
            matches_filter = (
                (filter_type == "mods" and mod_name not in texture_packs) or
                (filter_type == "texturepacks" and mod_name in texture_packs)
            )
            matches_search = search_term in mod_name.lower()
            if matches_filter and matches_search:
                child.pack(pady=10, padx=10)
            else:
                child.pack_forget()


logging.basicConfig(
    filename='app.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s')

Ctk.set_appearance_mode("Dark")
Ctk.set_default_color_theme("dark-blue")

images_folder = os.path.join(os.path.dirname(__file__), 'Assets', 'images')
sounds_folder = os.path.join(os.path.dirname(__file__), 'Assets', 'sounds')
meshes_folder = os.path.join(os.path.dirname(__file__), 'Assets', 'meshes')


def export_modpack():
    modpack_to_export = selected_modpack.get()
    if not modpack_to_export:
        messagebox.showwarning("Export Error",
                               "Please select a modpack from Tab 2 first.")
        return

    mod_state_path = os.path.join(
        modpacks_dir,
        modpack_to_export,
        "mod_state.json")

    if not os.path.exists(mod_state_path):
        messagebox.showerror(
            "Export Error",
            f"Mod state file not found for '{modpack_to_export}'. Cannot export.")
        return

    try:
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        messagebox.showerror(
            "Export Error",
            f"Error reading mod state for '{modpack_to_export}': {e}")
        return

    save_path = filedialog.asksaveasfilename(
        defaultextension=".roforgepack",
        filetypes=[("RoForge Modpack List", "*.roforgepack"), ("All Files", "*.*")],
        title="Export Modpack List As...",
        initialfile=f"{modpack_to_export}.roforgepack"
    )

    if not save_path:
        return

    try:
        with open(save_path, 'w') as f:
            json.dump(mod_state, f, indent=4)
        messagebox.showinfo(
            "Export Successful",
            f"Mod list for '{modpack_to_export}' exported to:\n{save_path}")
    except Exception as e:
        messagebox.showerror(
            "Export Error",
            f"Failed to write export file: {e}")
        logging.error(f"Failed to write export file '{save_path}': {e}")


def _import_modpack_worker(new_modpack_name, imported_mod_state, result_queue):
    new_modpack_folder = os.path.join(modpacks_dir, new_modpack_name)
    original_selected = None

    try:

        result_queue.put(("status", "Finding Roblox installation..."))
        folder = get_roblox_folder()
        selected_modpack.set(new_modpack_name)
        create_client_settings()
        if folder is None:
            result_queue.put(
                ("error", "Current Roblox installation not found. Cannot create base for import."))
            return

        version = os.path.basename(folder)
        script_dir = os.path.dirname(os.path.abspath(__file__))

        if not os.path.exists(modpacks_dir):
            os.makedirs(modpacks_dir)

        result_queue.put(("status", f"Copying Roblox v{version}..."))
        logging.info(
            f"Copying Roblox from '{folder}' to '{new_modpack_folder}' base")
        dst_folder = os.path.join(new_modpack_folder, "RobloxCopy", version)

        shutil.copytree(
            folder,
            dst_folder,
            copy_function=shutil.copy2,
            dirs_exist_ok=True)
        logging.info(f"Copied Roblox folder to {dst_folder}")

        result_queue.put(("status", "Creating settings..."))
        settings_folder = os.path.join(dst_folder, "ClientSettings")
        os.makedirs(settings_folder, exist_ok=True)
        settings_file = os.path.join(settings_folder, "ClientAppSettings.json")
        if not os.path.exists(settings_file):
            with open(settings_file, "w") as f:
                json.dump({}, f, indent=4)
            logging.info(
                f"Created default ClientAppSettings.json file at: {settings_file}")

        result_queue.put(("status", "Setting default image..."))
        default_image_path = os.path.join(images_folder, "play.png")
        target_image_path = os.path.join(new_modpack_folder, "image.png")
        if os.path.exists(default_image_path):
            shutil.copy(default_image_path, target_image_path)
        else:
            logging.warning(
                "Default modpack image not found, skipping image copy.")
            result_queue.put(
                ("log_warning", "Default modpack image not found."))

        result_queue.put(("status", "Applying mods..."))
        logging.info(f"Applying imported mods to '{new_modpack_name}'")

        applied_count = 0
        skipped_mods = []
        apply_errors = []
        current_mod_state = {}

        for key in mod_apply_functions.keys():
            current_mod_state[key] = False

        total_mods_to_process = len(imported_mod_state)
        processed_count = 0

        for mod_key, should_enable in imported_mod_state.items():
            processed_count += 1
            progress_percent = int(
                (processed_count /
                 total_mods_to_process) *
                100) if total_mods_to_process else 0

            if mod_key in mod_apply_functions:
                current_mod_state[mod_key] = False
                if should_enable:
                    result_queue.put(
                        ("status", f"Applying mod: {mod_key} ({progress_percent}%)"))
                    try:
                        logging.info(
                            f"Enabling mod via import: {mod_key} for {new_modpack_name}")

                        mod_apply_functions[mod_key](True)
                        current_mod_state[mod_key] = True
                        applied_count += 1
                    except Exception as apply_error:
                        err_msg = f"Error applying mod '{mod_key}': {apply_error}"
                        logging.error(
                            f"{err_msg} during import to '{new_modpack_name}'")
                        apply_errors.append(f"- {mod_key}: {apply_error}")

                        result_queue.put(("log_warning", err_msg))

            else:
                logging.warning(
                    f"Imported mod list contains unknown mod key '{mod_key}'. Skipping.")
                skipped_mods.append(mod_key)
                result_queue.put(
                    ("log_warning", f"Unknown mod key in import file: '{mod_key}'. Skipped."))

        result_queue.put(("status", "Saving mod state..."))
        new_mod_state_path = os.path.join(new_modpack_folder, "mod_state.json")
        with open(new_mod_state_path, "w") as f:
            json.dump(current_mod_state, f, indent=4)
        logging.info(f"Saved final mod state to {new_mod_state_path}")

        result_queue.put(
            ("success",
             (new_modpack_name,
              applied_count,
              skipped_mods,
              apply_errors)))

    except (FileNotFoundError, PermissionError, OSError, Exception) as e:
        logging.exception(
            f"Error during import worker thread for '{new_modpack_name}': {e}")

        if os.path.exists(new_modpack_folder):
            try:
                result_queue.put(("status", "Error occurred. Cleaning up..."))
                shutil.rmtree(new_modpack_folder, ignore_errors=True)
                logging.info(
                    f"Cleaned up partially created folder: {new_modpack_folder}")
            except Exception as cleanup_e:
                logging.error(
                    f"Failed to cleanup folder {new_modpack_folder} after error: {cleanup_e}")

        result_queue.put(("error", f"Import failed: {str(e)}"))


def import_modpack():
    import_path = filedialog.askopenfilename(
        filetypes=[("RoForge Modpack List", "*.roforgepack"), ("All Files", "*.*")],
        title="Import Modpack List"
    )
    if not import_path:
        return

    try:
        with open(import_path, 'r') as f:
            imported_mod_state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        messagebox.showerror(
            "Import Error",
            f"Failed to read or parse import file:\n{import_path}\nError: {e}")
        logging.error(f"Failed to read/parse import file '{import_path}': {e}")
        return
    except Exception as e:
        messagebox.showerror(
            "Import Error",
            f"An unexpected error occurred reading the file:\n{e}")
        logging.error(
            f"Unexpected error reading import file '{import_path}': {e}")
        return

    dialog = CTkInputDialog(
        text="Enter a name for the new imported modpack:",
        title="Import Modpack")
    new_modpack_name = dialog.get_input()

    if not new_modpack_name:
        return

    target_modpack_folder = os.path.join(modpacks_dir, new_modpack_name)
    if os.path.exists(target_modpack_folder):
        messagebox.showerror(
            "Import Error",
            f"A modpack named '{new_modpack_name}' already exists.")
        return

    loading_window = show_loading_screen(
        f"Starting import: '{new_modpack_name}'...")

    result_queue = queue.Queue()

    original_selected_modpack = selected_modpack.get()

    thread = threading.Thread(
        target=_import_modpack_worker,
        args=(new_modpack_name, imported_mod_state, result_queue),
        daemon=True
    )
    thread.start()

    app.after(
        100,
        check_import_modpack_queue,
        loading_window,
        result_queue,
        new_modpack_name,
        original_selected_modpack)


def check_import_modpack_queue(
        loading_window,
        result_queue,
        imported_name,
        original_selection):
    try:
        message = result_queue.get_nowait()
        msg_type, msg_data = message

        if msg_type == "status":
            if loading_window.winfo_exists():
                loading_window.label.configure(text=msg_data)

            app.after(
                100,
                check_import_modpack_queue,
                loading_window,
                result_queue,
                imported_name,
                original_selection)
        elif msg_type == "log_warning":
            logging.warning(f"Import Warning ({imported_name}): {msg_data}")

            app.after(
                100,
                check_import_modpack_queue,
                loading_window,
                result_queue,
                imported_name,
                original_selection)
        elif msg_type == "error":
            if loading_window.winfo_exists():
                loading_window.destroy()
            messagebox.showerror("Import Error", msg_data)

            if imported_name in modpacks:
                modpacks.remove(imported_name)
                update_modpacks_frame()

        elif msg_type == "success":
            if loading_window.winfo_exists():
                loading_window.destroy()

            created_name, applied_count, skipped_mods, apply_errors = msg_data

            if created_name not in modpacks:
                modpacks.append(created_name)
            update_modpacks_frame()

            selected_modpack.set(created_name)

            success_message = f"Successfully imported modpack '{created_name}'!"
            if skipped_mods:
                success_message += f"\n\nSkipped unknown mods:\n{', '.join(skipped_mods)}"
            if apply_errors:
                success_message += f"\n\nErrors applying some mods (check logs):\n" + "\n".join(
                    apply_errors)

            messagebox.showinfo("Import Successful", success_message)
            logging.info(
                f"Import complete for '{created_name}'. Applied {applied_count} mods. Skipped: {len(skipped_mods)}. Errors: {len(apply_errors)}.")

    except queue.Empty:

        app.after(
            100,
            check_import_modpack_queue,
            loading_window,
            result_queue,
            imported_name,
            original_selection)
    except Exception as e:

        logging.error(f"Error processing import queue: {e}", exc_info=True)
        if loading_window.winfo_exists():
            loading_window.destroy()
        messagebox.showerror(
            "Error",
            f"An unexpected error occurred while checking import status: {e}")

        target_modpack_folder = os.path.join(modpacks_dir, imported_name)
        if os.path.exists(target_modpack_folder):
            try:
                shutil.rmtree(target_modpack_folder, ignore_errors=True)
                logging.warning(
                    f"Cleaned up {target_modpack_folder} due to queue check error.")
            except Exception as cleanup_e:
                logging.error(
                    f"Failed to cleanup {target_modpack_folder} after queue check error: {cleanup_e}")
        if imported_name in modpacks:
            modpacks.remove(imported_name)
            update_modpacks_frame()


def button_function():
    print("button pressed")


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


def save_json(data):
    settings_folder = create_client_settings()
    if settings_folder:
        json_path = os.path.join(settings_folder, "ClientAppSettings.json")
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=4)
            print(f"Saved JSON to {json_path}. Restart Roblox to see changes.")


def update_modpacks_frame():

    for widget in modpacks_image_frame.winfo_children():
        widget.destroy()

    num_columns = int(math.sqrt(len(modpacks)))
    if num_columns * (num_columns - 1) >= len(modpacks):
        num_columns -= 1

    x = 0
    y = 0
    for modpack in modpacks:
        image_path = os.path.join(modpacks_dir, modpack, "image.png")

        image = Ctk.CTkImage(
            light_image=Image.open(image_path), size=(
                145, 145))

        button = Ctk.CTkButton(
            master=modpacks_image_frame,
            text=modpack,
            image=image,
            compound="top",
            command=lambda m=modpack: select_modpack(m),
            fg_color="#222222",
            hover_color="#000001",
            width=100,
            height=200)
        button.grid(row=y, column=x, pady=2, padx=2)

        button.photo = image

        if x < 3:
            x += 1
        else:
            x = 0
            y += 1


def create_modpack():
    name = name_entry.get()
    if not name:
        messagebox.showinfo("Info", "Please enter a name for the modpack.")
        return

    img_path_or_none = img_data.get()
    if img_path_or_none == "":
        img_path_or_none = None

    loading_window = show_loading_screen(f"Starting creation for '{name}'...")

    result_queue = queue.Queue()

    thread = threading.Thread(
        target=_create_modpack_worker,
        args=(name, img_path_or_none, result_queue),
        daemon=True
    )
    thread.start()

    app.after(
        100,
        check_create_modpack_queue,
        loading_window,
        result_queue,
        name)


def check_create_modpack_queue(loading_window, result_queue, original_name):
    try:

        message = result_queue.get_nowait()
        msg_type, msg_data = message

        if msg_type == "status":
            loading_window.label.configure(text=msg_data)

            app.after(
                100,
                check_create_modpack_queue,
                loading_window,
                result_queue,
                original_name)
        elif msg_type == "error":
            loading_window.destroy()
            messagebox.showerror("Error", msg_data)

        elif msg_type == "warning":
            loading_window.destroy()
            messagebox.showwarning("Warning", msg_data)

        elif msg_type == "log_warning":
            logging.warning(msg_data)

            app.after(
                100,
                check_create_modpack_queue,
                loading_window,
                result_queue,
                original_name)
        elif msg_type == "success":
            created_name = msg_data
            loading_window.destroy()

            if created_name not in modpacks:
                modpacks.append(created_name)
            update_modpacks_frame()
            selected_modpack.set(created_name)
            show_tab("Tab2")
            messagebox.showinfo(
                "Success", f"Modpack '{created_name}' created successfully!")

    except queue.Empty:

        app.after(
            100,
            check_create_modpack_queue,
            loading_window,
            result_queue,
            original_name)
    except Exception as e:

        logging.error(f"Error processing modpack queue: {e}", exc_info=True)
        if loading_window.winfo_exists():
            loading_window.destroy()
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")


def show_tab(tab):
    """Show a tab and initialize mod switches with saved states."""
    Tab1Frame.place_forget()
    Tab2Frame.place_forget()
    Tab3Frame.place_forget()

    if tab == "Tab1":
        Tab1Frame.place(x=10, y=10)
    elif tab == "Tab2":
        Tab2Frame.place(x=10, y=10)

        for child in mods.winfo_children():
            child.destroy()
        mod_states.clear()
        mod_apply_functions.clear()

        internal_mods = [
            ("R63 avatar", replace_character_meshes, os.path.join(images_folder, "girl.jpg")),
            ("Faster inputs", faster_inputs, os.path.join(images_folder, "keyboard.png")),
            ("Replace Font", replace_font, os.path.join(images_folder, "Replace Font.png")),
            ("Optimizer", apply_optimizer, os.path.join(images_folder, "Optimizer.png")),
            ("Cheat", apply_cheat, os.path.join(images_folder, "cheat.png")),
            ("Change celestial bodies", apply_day_night_cycle, os.path.join(images_folder, "moon.jpg")),
            ("Hide gui", apply_hide_gui, os.path.join(images_folder, "hide.png")),
            ("Remove grass", apply_remove_grass_mesh, os.path.join(images_folder, "grass.png")),
            ("Display fps", apply_display_fps, os.path.join(images_folder, "displayfps.png")),
            ("Disable remotes", disable_remotes, os.path.join(images_folder, "RemoteEvent.png")),
            ("Unlock fps", unlock_fps, os.path.join(images_folder, "unlock_fps.png")),
            ("Custom death sound", apply_custom_ouch_sound, os.path.join(images_folder, "noob.png")),
            ("Google browser", google_browser, os.path.join(images_folder, "google.png")),
            ("Chat gpt", chat_gpt, os.path.join(images_folder, "ChatGPT_logo.svg.png")),
            ("Graphic boost", graphic_boost, os.path.join(images_folder, "graphics.png")),
            ("Beautiful sky", beautiful_sky, os.path.join(images_folder, "beautiful.png")),
            ("Anime chan sky", anime_chan_sky, os.path.join(images_folder, "Chan.png")),
            ("Bloxstrap Theme", apply_bloxstrap_theme, os.path.join(images_folder, "bloxstrap.png")),
        ]

        for mod_name, mod_function, icon_path in internal_mods:
            internal_name = MOD_NAME_MAPPING.get(
                mod_name, mod_name.lower().replace(' ', '_'))
            mod_apply_functions[internal_name] = mod_function
            add_mod_switch(mod_name, mod_function, icon_path)

        external_mods = load_external_mods()
        for internal_name, mod_info in external_mods.items():
            if not validate_external_mod_entry(internal_name, mod_info):
                continue
            try:
                mod_name = mod_info["name"]
                mod_config_path = mod_info["config_path"]
                icon_path = mod_info["icon_path"]
                with open(mod_config_path, "r") as f:
                    mod_config = json.load(f)

                def mod_apply_function(
                        enabled,
                        iname=internal_name,
                        config=mod_config):
                    apply_external_mod(
                        selected_modpack.get(), iname, config, enabled)

                mod_apply_functions[internal_name] = mod_apply_function
                add_mod_switch(
                    mod_name,
                    mod_apply_functions[internal_name],
                    icon_path)
            except Exception as e:
                logging.error(
                    f"Failed to add switch for external mod {internal_name}: {str(e)}")

        modpack = selected_modpack.get()
        if modpack:
            mod_state_path = os.path.join(
                modpacks_dir, modpack, "mod_state.json")
            if os.path.exists(mod_state_path):
                try:
                    with open(mod_state_path, "r") as f:
                        mod_state = json.load(f)
                    for internal_name, enabled in mod_state.items():

                        mod_name = INTERNAL_TO_DISPLAY.get(internal_name)
                        if not mod_name and internal_name in external_mods:
                            mod_name = external_mods[internal_name]["name"]
                        if mod_name and mod_name in mod_states:
                            mod_states[mod_name].set(enabled)
                            logging.debug(
                                f"Set mod state for {mod_name} ({internal_name}): {enabled}")
                        else:
                            logging.warning(
                                f"Mod {internal_name} not found in mod_states for modpack {modpack}")
                except Exception as e:
                    logging.error(
                        f"Error loading mod_state.json for modpack {modpack}: {str(e)}")

        if hasattr(search_entry, 'delete'):
            search_entry.delete(0, "end")
        filter_mods("mods")

        if modpack:
            icon_path = os.path.join(modpacks_dir, modpack, "image.png")
            try:
                icon_image = Ctk.CTkImage(
                    light_image=Image.open(icon_path), size=(
                        125, 125))
                selected_modpack_icon_label.configure(image=icon_image)
                selected_modpack_icon_label.image = icon_image
            except Exception as e:
                logging.warning(
                    f"Failed to load modpack icon {icon_path}: {str(e)}")
            modpack_name_label.configure(text=f"{modpack}")

    elif tab == "Tab3":
        Tab3Frame.place(x=10, y=10)


def show_tab1():
    Tab1Frame.place_forget()
    Tab2Frame.place_forget()
    Tab3Frame.place_forget()
    createframe.place_forget()
    createblur.pack_forget()

    Tab1Frame.place(x=10, y=10)


def show_create_modpack():
    Tab1Frame.place_forget()
    Tab2Frame.pack_forget()
    Tab3Frame.pack_forget()

    Tab1Frame.place(x=10, y=10)

def create_modpack_tab():
    createframe.place(x=100, y=150)
    createblur.pack(pady=10, padx=10, expand=False, side=Ctk.LEFT)
    img_data.set(value="None")


def remove_modpack_tab():
    createframe.place_forget()
    createblur.pack_forget()

    change_button.configure(image=img2)


def create_settings_tab():
    createframe2.place(x=100, y=150)
    createblur2.pack(pady=10, padx=10, expand=False, side=Ctk.LEFT)


def remove_settings_tab():
    createframe2.place_forget()
    createblur2.pack_forget()

def select_modpack(m):
    selected_modpack.set(m)
    show_tab("Tab2")

def change_image():
    image_path = filedialog.askopenfilename(
        title="Select an image file", filetypes=[
            ("Image files", "*.png;*.jpg;*.jpeg")])
    img_data.set(image_path)

    img3 = Image.open(image_path)
    img4 = Ctk.CTkImage(img3, size=(75, 75))

    change_button.configure(image=img4)

def toggle_multi_roblox():
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

    if multi_roblox_enabled.get():
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

def load_fast_flags():
    modpack = selected_modpack.get()
    if not modpack:
        messagebox.showwarning("Warning", "Please select a modpack.")
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

    text_widget.delete(1.0, "end")
    text_widget.insert("end", json.dumps(settings, indent=4))


def save_fast_flags():
    modpack = selected_modpack.get()
    if not modpack:
        messagebox.showwarning("Warning", "Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(
        roblox_path,
        version,
        "ClientSettings",
        "ClientAppSettings.json")

    json_content = text_widget.get(1.0, "end")

    try:
        settings = json.loads(json_content)

        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=4)

        messagebox.showinfo("Info", "Fast flags saved successfully.")
    except json.JSONDecodeError:
        messagebox.showerror(
            "Error", "Invalid JSON content. Please check the syntax.")


def toggle_fflag_editor():
    if fflag_editor_frame.winfo_ismapped():
        createblur3.place_forget()
        fflag_editor_frame.place_forget()
    else:
        load_fast_flags()
        fflag_editor_frame.place(x=60, y=75)
        createblur3.place(x=10, y=10)


def delete_selected_modpack():
    modpack_to_delete = selected_modpack.get()

    if not modpack_to_delete:
        messagebox.showwarning("Delete Error", "No modpack selected.")
        return

    confirm = messagebox.askyesno(
        "Confirm Deletion",
        f"Are you sure you want to permanently delete the modpack '{modpack_to_delete}'?\n\n"
        "This action cannot be undone and will remove all its files.",
        icon='warning')

    if not confirm:
        logging.info(f"Deletion cancelled for modpack: {modpack_to_delete}")
        return

    modpack_path = os.path.join(modpacks_dir, modpack_to_delete)
    logging.info(f"Attempting to delete modpack: {modpack_path}")

    try:
        if os.path.exists(modpack_path):

            shutil.rmtree(modpack_path)
            logging.info(f"Successfully deleted directory: {modpack_path}")

            try:
                modpacks.remove(modpack_to_delete)
                logging.info(
                    f"Removed '{modpack_to_delete}' from internal modpacks list.")
            except ValueError:
                logging.warning(
                    f"Modpack '{modpack_to_delete}' was already removed from the list?")

            selected_modpack.set("")
            update_modpacks_frame()
            show_tab("Tab1")
            remove_modpack_tab()

        else:
            logging.warning(
                f"Tried to delete modpack, but path not found: {modpack_path}")
            messagebox.showerror(
                "Delete Error",
                f"Could not find the directory for modpack '{modpack_to_delete}'. It might have been already deleted.")

            if modpack_to_delete in modpacks:
                modpacks.remove(modpack_to_delete)
                update_modpacks_frame()

    except PermissionError:
        logging.error(
            f"Permission denied while trying to delete {modpack_path}")
        messagebox.showerror(
            "Delete Error",
            f"Permission denied when trying to delete '{modpack_to_delete}'.\n\nTry running RoForge as an administrator.")
    except OSError as e:
        logging.exception(f"OS error deleting {modpack_path}: {e}")
        messagebox.showerror(
            "Delete Error",
            f"An OS error occurred trying to delete '{modpack_to_delete}':\n{e}\n\nEnsure Roblox is not running from this modpack.")
    except Exception as e:
        logging.exception(
            f"Unexpected error deleting modpack '{modpack_to_delete}'")
        messagebox.showerror(
            "Delete Error",
            f"An unexpected error occurred while deleting '{modpack_to_delete}':\n{e}")


def launch_modpack():
    modpack = selected_modpack.get()
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    roblox_exe_path = os.path.join(
        roblox_path, version, "RobloxPlayerBeta.exe")

    subprocess.Popen([roblox_exe_path])


'''Yeah here is the start of ui...'''


app = Ctk.CTk()

os.path.join(images_folder, "play.ico")

img22 = tk.PhotoImage(file=os.path.join(images_folder, "play.png"))

app.wm_iconbitmap()
app.iconphoto(False, img22)

app.title("RoForge")
app.geometry("1200x800")
app.wm_iconphoto(True, img22)
app.resizable(False, False)

image = Image.open((os.path.join(images_folder, "background.jpg")))
background_image = Ctk.CTkImage(image, size=(1200, 800))

mod_states = {}

bg_lbl = Ctk.CTkLabel(app, text="", image=background_image)
bg_lbl.place(x=0, y=0)

label = Ctk.CTkLabel(app, text="")
label.pack(padx=20, pady=20)

tabsFrame = Ctk.CTkScrollableFrame(
    master=app,
    width=150,
    height=605,
    fg_color="#000000")

tabsText = Ctk.CTkLabel(master=tabsFrame, text="Application")

button = Ctk.CTkButton(
    master=tabsFrame,
    text="Create modpacks",
    command=lambda: show_tab("Tab1"),
    width=150,
    height=50)

button2 = Ctk.CTkButton(
    master=tabsFrame,
    text="Mods",
    command=lambda: show_tab("Tab2"),
    width=150,
    height=50)

button3 = Ctk.CTkButton(
    master=tabsFrame,
    text="Tab 3",
    command=lambda: show_tab("Tab3"),
    width=150,
    height=50)

modpacks_dir = os.path.join(os.path.dirname(__file__), "ModPacks")
if not os.path.exists(modpacks_dir):
    modpacks = []
else:
    modpacks = [
        f for f in os.listdir(modpacks_dir) if os.path.isdir(
            os.path.join(
                modpacks_dir,
    f))]


Tab1Frame = Ctk.CTkFrame(master=app, width=700, height=780, fg_color="#111111")
Tab1Frame.pack_propagate(False)

img_data = Ctk.StringVar(value="None")
createblur = Ctk.CTkFrame(
    master=app,
    width=700,
    height=702,
    fg_color="#111111")
createblur.pack_propagate(False)
createframe = Ctk.CTkFrame(
    master=app,
    width=500,
    height=500,
    fg_color="#222222")
createframe.pack_propagate(False)

simple_frame = Ctk.CTkFrame(
    master=createframe,
    width=700,
    height=45,
    fg_color="#222222")
simple_frame.pack_propagate(False)
simple_frame.pack(pady=30, padx=20, side=Ctk.TOP, expand=False)

simple_frame2 = Ctk.CTkFrame(
    master=createframe,
    width=700,
    height=90,
    fg_color="#222222")
simple_frame2.pack_propagate(False)
simple_frame2.pack(pady=0, padx=20, side=Ctk.TOP, expand=False)

simple_frame3 = Ctk.CTkFrame(
    master=simple_frame2,
    width=200,
    height=90,
    fg_color="#222222")
simple_frame3.pack_propagate(False)
simple_frame3.pack(pady=0, padx=50, side=Ctk.RIGHT, expand=False)

simple_frame4 = Ctk.CTkFrame(
    master=simple_frame2,
    width=200,
    height=200,
    fg_color="#222222")
simple_frame4.pack_propagate(False)
simple_frame4.pack(pady=0, padx=10, side=Ctk.LEFT, expand=False)

label_new = Ctk.CTkLabel(
    master=simple_frame,
    text="Create a profile",
    font=Ctk.CTkFont(
        family="Impact",
         size=24))
label_new.pack(pady=10, padx=10, side=Ctk.LEFT)

label_new2 = Ctk.CTkLabel(
    master=simple_frame3,
    text="Profile name",
    font=Ctk.CTkFont(
        family="Impact",
         size=20))
label_new2.pack(pady=10, padx=10, side=Ctk.TOP)

name_entry = Ctk.CTkEntry(
    master=simple_frame3,
    placeholder_text="Profile name",
    width=250)
framenew = Ctk.CTkFrame(
    master=createframe,
    width=700,
    height=90,
    fg_color="#222222")
create_button = Ctk.CTkButton(
    master=framenew,
    text="Create",
    command=create_modpack,
    width=130,
    height=70,
    fg_color="#111111",
    hover_color="#000001",
    font=Ctk.CTkFont(
        family="Impact",
         size=20))
cancel_button = Ctk.CTkButton(
    master=framenew,
    text="Cancel",
    command=remove_modpack_tab,
    width=185,
    height=70,
    fg_color="#111111",
    hover_color="#000001",
    font=Ctk.CTkFont(
        family="Impact",
         size=20))
framenew.pack(pady=0, padx=20, side=Ctk.BOTTOM, expand=False)

img1 = Image.open((os.path.join(images_folder, "play.png")))
img2 = Ctk.CTkImage(img1, size=(75, 75))

change_button = Ctk.CTkButton(
    master=simple_frame4,
    text="",
    command=change_image,
    width=75,
    height=150,
    image=img2,
    fg_color="#111111",
    hover_color="#000001")

change_button.pack_propagate(False)

name_entry.pack(pady=0, padx=0, side=Ctk.RIGHT)
create_button.pack(pady=20, padx=50, side=Ctk.RIGHT)
cancel_button.pack(pady=20, padx=50, side=Ctk.LEFT)
change_button.pack(pady=0, padx=0, side=Ctk.BOTTOM, fill='y')


multi_roblox_enabled = Ctk.BooleanVar(value=False)

img_data = Ctk.StringVar(value="None")
createblur2 = Ctk.CTkFrame(
    master=app,
    width=700,
    height=702,
    fg_color="#111111")
createblur2.pack_propagate(False)
createframe2 = Ctk.CTkFrame(
    master=app,
    width=500,
    height=500,
    fg_color="#222222")
cancel_button2 = Ctk.CTkButton(
    master=createframe2,
    text="Cancel",
    command=remove_settings_tab,
    width=175,
    height=70,
    fg_color="#111111",
    hover_color="#000001",
    font=Ctk.CTkFont(
        family="Impact",
         size=20))
createframe2.pack_propagate(False)
pywinstyles.set_opacity(createblur2, value=0.5, color="#000001")

settingframe2 = Ctk.CTkFrame(
    master=createframe2,
    width=490,
    height=60,
    fg_color="#111111")
settingframe2.pack_propagate(False)

label2 = Ctk.CTkLabel(master=settingframe2, text="Multi-Instance")

settingframe2.pack(pady=5)

switch2 = Ctk.CTkSwitch(
    master=settingframe2,
    text="",
    variable=multi_roblox_enabled,
    command=toggle_multi_roblox)
switch2.pack(pady=10, padx=10, side="right")
label2.pack(pady=10, padx=20, side="left")

cancel_button2.pack(pady=20, padx=50, side=Ctk.BOTTOM)

pywinstyles.set_opacity(createblur, value=0.5, color="#000001")

img = Image.open((os.path.join(images_folder, "play.png")))
img_logo = Ctk.CTkImage(img, size=(50, 50))
upperframe = Ctk.CTkFrame(
    master=Tab1Frame,
    width=700,
    height=50,
    fg_color="#111111")
upperframe.pack(pady=20, padx=20, expand=False)
label1 = Ctk.CTkLabel(
    master=upperframe,
    text="",
    image=img_logo,
    width=50,
    height=50)
label1.pack(pady=0, padx=0, side="left")
label = Ctk.CTkLabel(
    master=upperframe,
    text="RoForge",
    font=Ctk.CTkFont(
        family="Impact",
         size=24))
label.pack(pady=20, padx=20, side="top")
label2 = Ctk.CTkFrame(
    master=Tab1Frame,
    width=815,
    height=2,
    fg_color="#444444")
label2.pack_propagate(False)
label2.pack(pady=5, padx=20, side="top", expand=False)
middleframe = Ctk.CTkFrame(
    master=Tab1Frame,
    width=700,
    height=75,
    fg_color="#111111")
middleframe.pack_propagate(False)
middleframe.pack(pady=10, padx=20, expand=False)

create_start_button = Ctk.CTkButton(
    master=middleframe,
    text="+ Create",
    font=Ctk.CTkFont(
        family="Impact",
        size=22),
    command=create_modpack_tab,
    fg_color="#111111",
    hover_color="#000001",
    width=155,
    height=50)
create_start_button.pack(pady=0, padx=0, side=Ctk.LEFT)

create_settings_button = Ctk.CTkButton(
    master=middleframe,
    text="⚙ Settings",
    font=Ctk.CTkFont(
        family="Impact",
        size=22),
    command=create_settings_tab,
    fg_color="#111111",
    hover_color="#000001",
    width=155,
    height=50)
create_settings_button.pack(pady=0, padx=0, side=Ctk.LEFT)

modpacks_image_frame = Ctk.CTkScrollableFrame(
    master=Tab1Frame,
    width=600,
    height=605,
    fg_color="#111111",
    corner_radius=1)
modpacks_image_frame.pack(
    pady=0,
    padx=10,
    side=Ctk.TOP,
    expand=False,
    fill='both')

Tab2Frame = Ctk.CTkFrame(master=app, width=700, height=780, fg_color="#111111")
Tab2Frame.pack_propagate(False)

selected_modpack = Ctk.StringVar(value="")

modstop = Ctk.CTkFrame(master=Tab2Frame, width=800, height=150)
modstop.pack_propagate(False)
modstop.pack(pady=20, padx=20)

selected_modpack_icon_label = Ctk.CTkLabel(
    master=modstop, text="", image=None, width=125, height=125)
selected_modpack_icon_label.pack(pady=10, padx=30, side="left")

selected_modpack = Ctk.StringVar(value=f"")
modpack_menu = Ctk.CTkOptionMenu(master=Tab2Frame, variable=selected_modpack)


fflag_editor_button_frame = Ctk.CTkFrame(
    Tab2Frame, width=660, height=50, fg_color="#111111")

fflag_editor_button_frame.pack_propagate(False)
fflag_editor_button_frame.pack(pady=0, side="top")


upperframe2 = Ctk.CTkFrame(
    master=modstop,
    width=475,
    height=600,
    fg_color="#222222")
upperframe2.pack_propagate(False)
upperframe2.pack(pady=0, padx=1, side="right", expand=False)

upperframe3 = Ctk.CTkFrame(
    master=upperframe2,
    width=200,
    height=600,
    fg_color="#222222")
upperframe3.pack_propagate(False)
upperframe3.pack(pady=10, padx=1, side="right", expand=False)

upperframe34 = Ctk.CTkFrame(
    master=upperframe2,
    width=400,
    height=600,
    fg_color="#222222")
upperframe34.pack_propagate(False)
upperframe34.pack(pady=10, padx=1, side="left", expand=False)

modpack_name_label = Ctk.CTkLabel(
    master=upperframe34, text="", font=(
        "Impact", 24), height=2)
modpack_name_label.pack_propagate(False)
modpack_name_label.pack(pady=10, side="left")

upperframe4 = Ctk.CTkFrame(
    master=upperframe3,
    width=200,
    height=50,
    fg_color="#222222")
upperframe4.pack_propagate(False)
upperframe4.pack(pady=10, padx=1, side="top", expand=False)

launch_button = Ctk.CTkButton(
    master=upperframe4,
    text="▷ Launch",
    command=launch_modpack,
    width=110,
    height=25,
    fg_color="#222222",
    hover_color="#000001",
    font=Ctk.CTkFont(
        family="Impact",
         size=22))
launch_button.pack(pady=0, padx=0, side="left")

export_button = Ctk.CTkButton(
    master=upperframe4,
    text="📤",
    command=export_modpack,
    fg_color="#222222",
    hover_color="#000001",
    width=25,
    height=25,
    font=Ctk.CTkFont(
        family="Impact",
         size=22))
export_button.pack(pady=0, padx=0, side="left")

cancel_button = Ctk.CTkButton(
    master=upperframe3,
    text="❌",
    command=show_tab1,
    width=190,
    height=25,
    fg_color="#111111",
    hover_color="#000001",
    font=Ctk.CTkFont(
        family="Impact",
         size=22))
cancel_button.pack(pady=0, padx=0, side="top")
cancel_button.pack_propagate(False)

mods = Ctk.CTkScrollableFrame(master=Tab2Frame, width=800, height=600)
mods.pack(pady=20, padx=20)

label3 = Ctk.CTkFrame(
    master=Tab2Frame,
    width=400,
    height=2,
    fg_color="#555555")
label3.pack_propagate(False)
label3.pack(pady=3, padx=1, side="bottom", expand=False)

search_frame = Ctk.CTkFrame(
    master=fflag_editor_button_frame,
    width=200,
    height=200,
    fg_color="#111111")
search_frame.pack(pady=0, padx=0, side="left")
search_frame.pack_propagate(False)

show_mods_button = Ctk.CTkButton(
    fflag_editor_button_frame,
    text="Mods",
    command=lambda: filter_mods("mods"),
    fg_color="#111111",
    hover_color="#000001",
    height=50,
    font=Ctk.CTkFont(
        family="Impact",
         size=20))
show_mods_button.pack(pady=0, padx=5, side="left")

show_texturepacks_button = Ctk.CTkButton(
    fflag_editor_button_frame,
    text="Texture Packs",
    command=lambda: filter_mods("texturepacks"),
    fg_color="#111111",
    hover_color="#000001",
    height=50,
    font=Ctk.CTkFont(
        family="Impact",
         size=20))
show_texturepacks_button.pack(pady=0, padx=5, side="left")

fflag_editor_button = Ctk.CTkButton(
    fflag_editor_button_frame,
    text="Fast Flags",
    command=toggle_fflag_editor,
    fg_color="#111111",
    hover_color="#000001",
    height=50,
    font=Ctk.CTkFont(
        family="Impact",
         size=20))
fflag_editor_button.pack(pady=0, padx=5, side="left")

delete_button = Ctk.CTkButton(
    master=upperframe4,
    text="🗑",
    command=delete_selected_modpack,
    fg_color="#222222",
    hover_color="#000001",
    width=25,
    height=25,
    font=Ctk.CTkFont(
        family="Impact",
         size=22))
delete_button.pack(pady=0, side="left")


import_button = Ctk.CTkButton(
    master=middleframe,
    text="📥 Import",
    font=Ctk.CTkFont(
        family="Impact",
        size=22),
    command=import_modpack,
    fg_color="#111111",
    hover_color="#000001",
    width=155,
    height=50)

import_button.pack(pady=0, padx=0, side=Ctk.LEFT)

Tab3Frame = Ctk.CTkScrollableFrame(
    master=app,
    width=700,
    height=770,
    fg_color="#111111")

label = Ctk.CTkLabel(
    master=Tab3Frame,
    text="This is Tab 3",
    font=Ctk.CTkFont(
        family="Impact",
         size=24))

label.pack(pady=20, padx=20)

import_external_button = Ctk.CTkButton(
    master=middleframe,
    text="📥 Import Mod",
    font=Ctk.CTkFont(
        family="Impact",
        size=22),
    command=import_external_mod,
    fg_color="#111111",
    hover_color="#000001",
    width=155,
    height=50)

import_external_button.pack(pady=0, padx=0, side=Ctk.LEFT)


createblur3 = Ctk.CTkFrame(
    master=app,
    width=700,
    height=780,
    fg_color="#111111")

fflag_editor_frame = Ctk.CTkFrame(
    master=app,
    width=600,
    height=650,
    fg_color="#111111")

fflag_editor_blur = Ctk.CTkFrame(
    master=app,
    width=700,
    height=702,
    fg_color="#111111")

fflag_editor_blur.pack_propagate(False)
fflag_editor_frame.pack_propagate(False)

pywinstyles.set_opacity(fflag_editor_blur, value=0.5, color="#000001")

text_widget = Ctk.CTkTextbox(
    fflag_editor_frame,
    wrap="none",
    width=80,
    height=20,
    fg_color="#222222")
text_widget.pack(side="left", fill="both", expand=True)

scrollbar = Ctk.CTkScrollbar(fflag_editor_frame, command=text_widget.yview)
scrollbar.pack(side="right", fill="y")
text_widget.configure(yscrollcommand=scrollbar.set)

label_new3 = Ctk.CTkLabel(
    master=fflag_editor_frame,
    text="FastFlags editor",
    font=Ctk.CTkFont(
        family="Impact",
         size=20))

label_new3.pack(pady=10, padx=5)

fflag_editor_button2 = Ctk.CTkButton(
    fflag_editor_frame,
    text="Cancel",
    command=toggle_fflag_editor,
    height=50,
    fg_color="#111111",
    hover_color="#000001",
    font=Ctk.CTkFont(
        family="Impact",
         size=18))

fflag_editor_button2.pack(pady=10, padx=5)

save_fflags_button = Ctk.CTkButton(
    fflag_editor_frame,
    text="Save Fast Flags",
    command=save_fast_flags,
    height=50,
    fg_color="#111111",
    hover_color="#000001",
    font=Ctk.CTkFont(
        family="Impact",
         size=18))

save_fflags_button.pack(pady=10)

pywinstyles.set_opacity(createblur3, value=0.5, color="#000001")

search_entry = Ctk.CTkEntry(
    master=search_frame,
    placeholder_text="Search mods...",
    placeholder_text_color="#292929",
    width=400,
    height=200,
    fg_color="#171717",
    border_color="#191919",
    font=Ctk.CTkFont(
        family="Impact",
        size=20))

search_entry.pack(side="left", padx=10)

'''Ui code ends here lol'''

'''): I don't think this launcher is getting at least 1 download soon'''

x_max = 4
y_max = 4


global x, y
x = 0
y = 0

for modpack in modpacks:
    image_path = os.path.join(modpacks_dir, modpack, "image.png")

    image = Ctk.CTkImage(light_image=Image.open(image_path), size=(145, 145))

    button = Ctk.CTkButton(
        master=modpacks_image_frame,
        text=modpack,
        image=image,
        compound="top",
        command=lambda m=modpack: select_modpack(m),
        fg_color="#222222",
        hover_color="#000001",
        width=100,
        height=200)
    button.grid(row=y, column=x, pady=2, padx=2)

    button.photo = image

    if x < 3:
        x += 1
    else:
        x = 0
        y += 1
    print(x, y)


'''Mods!'''

def add_mod_switch(mod_name, mod_function, icon_path):

    if mod_name in mod_states:
        logging.debug(f"Removing existing mod switch for {mod_name}")
        del mod_states[mod_name]

    mod_state = Ctk.BooleanVar(value=False)
    mod_states[mod_name] = mod_state

    modframe = Ctk.CTkFrame(
        master=mods,
        width=800,
        height=80,
        fg_color="#111111")
    modframe.pack_propagate(False)

    try:
        icon_image = Ctk.CTkImage(
            light_image=Image.open(icon_path), size=(
                50, 50))
    except Exception as e:
        logging.warning(
            f"Failed to load icon {icon_path} for {mod_name}: {str(e)}")
        icon_image = Ctk.CTkImage(
            light_image=Image.open(
                os.path.join(
                    images_folder, "play.png")), size=(
                50, 50))

    icon_label = Ctk.CTkLabel(master=modframe, image=icon_image, text="")
    icon_label.pack(pady=10, padx=10, side="left")

    switch = Ctk.CTkSwitch(
        master=modframe,
        text="",
        variable=mod_state,
        command=lambda: mod_function(
            mod_state.get()))
    switch.pack(pady=10, padx=10, side="right")
    text = Ctk.CTkLabel(master=modframe, text=mod_name)
    text.pack(pady=10, padx=10, side="left")
    modframe.pack(pady=10, padx=10)

    icon_label.image = icon_image
    logging.debug(
        f"Added mod switch for {mod_name} with initial state {mod_state.get()}")


def apply_day_night_cycle(enabled):
    modpack = selected_modpack.get()
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


def close_file_handles(file_path):
    """Close any open handles to the specified file."""
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    INVALID_HANDLE_VALUE = -1
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

    handle = kernel32.CreateFileW(
        file_path,
        0,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None)
    if handle == INVALID_HANDLE_VALUE:

        return

    kernel32.CloseHandle(handle)


def replace_font(enabled):
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    modpack = selected_modpack.get()
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
    """Applies or removes the Bloxstrap theme to the selected modpack."""
    modpack = selected_modpack.get()
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


add_mod_switch(
    "R63 avatar",
    replace_character_meshes,
    os.path.join(
        images_folder,
        "girl.jpg"))
add_mod_switch(
    "Faster inputs",
    faster_inputs,
    os.path.join(
        images_folder,
        "keyboard.png"))
add_mod_switch(
    "Replace Font",
    replace_font,
    os.path.join(
        images_folder,
        "Replace Font.png"))
add_mod_switch(
    "Optimizer",
    apply_optimizer,
    os.path.join(
        images_folder,
        "Optimizer.png"))
add_mod_switch("Cheat", apply_cheat, os.path.join(images_folder, "cheat.png"))
add_mod_switch(
    "Change celestial bodies",
    apply_day_night_cycle,
    os.path.join(
        images_folder,
        "moon.jpg"))
add_mod_switch(
    "Hide gui",
    apply_hide_gui,
    os.path.join(
        images_folder,
        "hide.png"))
add_mod_switch(
    "Remove grass",
    apply_remove_grass_mesh,
    os.path.join(
        images_folder,
        "grass.png"))
add_mod_switch(
    "Display fps",
    apply_display_fps,
    os.path.join(
        images_folder,
        "displayfps.png"))
add_mod_switch(
    "Disable remotes",
    disable_remotes,
    os.path.join(
        images_folder,
        "RemoteEvent.png"))
add_mod_switch(
    "Unlock fps",
    unlock_fps,
    os.path.join(
        images_folder,
        "unlock_fps.png"))
add_mod_switch(
    "Custom death sound",
    apply_custom_ouch_sound,
    os.path.join(
        images_folder,
        "noob.png"))
add_mod_switch(
    "Google browser",
    google_browser,
    os.path.join(
        images_folder,
        "google.png"))
add_mod_switch(
    "Chat gpt",
    chat_gpt,
    os.path.join(
        images_folder,
        "ChatGPT_logo.svg.png"))
add_mod_switch(
    "Graphic boost",
    graphic_boost,
    os.path.join(
        images_folder,
        "graphics.png"))
add_mod_switch(
    "Beautiful sky",
    beautiful_sky,
    os.path.join(
        images_folder,
        "beautiful.png"))
add_mod_switch(
    "Anime chan sky",
    anime_chan_sky,
    os.path.join(
        images_folder,
        "Chan.png"))
add_mod_switch(
    "Bloxstrap Theme",
    apply_bloxstrap_theme,
    os.path.join(
        images_folder,
        "bloxstrap.png"))


def filter_mods_by_search(search_term):
    search_term = search_term.lower()

    for child in mods.winfo_children():
        if isinstance(child, Ctk.CTkFrame):
            mod_name = ""
            for widget in child.winfo_children():
                if isinstance(widget, Ctk.CTkLabel) and widget.cget("text"):
                    mod_name = widget.cget("text")
                    break

            matches_filter = (
                (current_filter == "mods" and mod_name not in texture_packs) or (
                    current_filter == "texturepacks" and mod_name in texture_packs))
            matches_search = search_term in mod_name.lower()

            if matches_filter and matches_search:
                child.pack(pady=10, padx=10)
            else:
                child.pack_forget()


search_entry.bind(
    "<KeyRelease>",
    lambda event: filter_mods_by_search(
        search_entry.get()))

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
}

show_tab("Tab1")

app.mainloop()
