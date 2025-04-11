import os
import json
import shutil
import json
import threading
import subprocess
import time
import tkinter as tk

import customtkinter as Ctk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox, Text, Scrollbar
import pywinstyles
import math
import winreg
import ctypes
import logging
from customtkinter import CTkInputDialog

import win32gui
import win32api
import win32con
import win32ui
import time

def filter_mods(filter_type):

    texture_packs = [
        "Replace Font",
        "Change celestial bodies",
        "Custom death sound",
        "R63 avatar",
        "Remove grass"
    ]

    for child in mods.winfo_children():
        if isinstance(child, Ctk.CTkFrame):
            child.pack_forget()

    for child in mods.winfo_children():
        if isinstance(child, Ctk.CTkFrame):
            mod_name = child.winfo_children()[2].cget("text")
            if (filter_type == "mods" and mod_name not in texture_packs) or \
                    (filter_type == "texturepacks" and mod_name in texture_packs):
                child.pack(pady=10, padx=10)

logging.basicConfig(filename='app.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

Ctk.set_appearance_mode("Dark")
Ctk.set_default_color_theme("dark-blue")

images_folder = os.path.join(os.path.dirname(__file__), 'Assets', 'images')
sounds_folder = os.path.join(os.path.dirname(__file__), 'Assets', 'sounds')
meshes_folder = os.path.join(os.path.dirname(__file__), 'Assets', 'meshes')

def export_modpack():
    modpack_to_export = selected_modpack.get()
    if not modpack_to_export:
        messagebox.showwarning("Export Error", "Please select a modpack from Tab 2 first.")
        return

    mod_state_path = os.path.join(modpacks_dir, modpack_to_export, "mod_state.json")

    if not os.path.exists(mod_state_path):
        messagebox.showerror("Export Error", f"Mod state file not found for '{modpack_to_export}'. Cannot export.")
        return

    try:
        with open(mod_state_path, "r") as f:
            mod_state = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        messagebox.showerror("Export Error", f"Error reading mod state for '{modpack_to_export}': {e}")
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
        messagebox.showinfo("Export Successful", f"Mod list for '{modpack_to_export}' exported to:\n{save_path}")
    except Exception as e:
        messagebox.showerror("Export Error", f"Failed to write export file: {e}")
        logging.error(f"Failed to write export file '{save_path}': {e}")

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
        messagebox.showerror("Import Error", f"Failed to read or parse import file:\n{import_path}\nError: {e}")
        logging.error(f"Failed to read/parse import file '{import_path}': {e}")
        return
    except Exception as e:
         messagebox.showerror("Import Error", f"An unexpected error occurred reading the file:\n{e}")
         logging.error(f"Unexpected error reading import file '{import_path}': {e}")
         return

    dialog = CTkInputDialog(text="Enter a name for the new imported modpack:", title="Import Modpack")
    new_modpack_name = dialog.get_input()

    if not new_modpack_name:
        return

    new_modpack_folder = os.path.join(modpacks_dir, new_modpack_name)
    if os.path.exists(new_modpack_folder):
         messagebox.showerror("Import Error", f"A modpack named '{new_modpack_name}' already exists.")
         return

    logging.info(f"Starting import process for new modpack: {new_modpack_name}")
    try:
        folder = get_roblox_folder()
        if folder is None:
            messagebox.showerror("Import Error", "Current Roblox installation not found. Cannot create base for import.")
            logging.error("Roblox installation not found during import.")
            return

        version = os.path.basename(folder)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        _modpacks_dir = os.path.join(script_dir, "ModPacks")
        if not os.path.exists(_modpacks_dir):
            os.makedirs(_modpacks_dir)
            logging.info(f"Created ModPacks folder at: {_modpacks_dir}")

        dst_folder = os.path.join(new_modpack_folder, "RobloxCopy", version)
        print(f"Creating new modpack '{new_modpack_name}' based on Roblox version '{version}'...")
        logging.info(f"Copying Roblox from '{folder}' to '{dst_folder}'")
        shutil.copytree(folder, dst_folder, copy_function=shutil.copy2)
        logging.info(f"Copied Roblox folder to {dst_folder}")

        settings_folder = os.path.join(dst_folder, "ClientSettings")
        if not os.path.exists(settings_folder):
            os.makedirs(settings_folder)
            logging.info(f"Created ClientSettings folder at: {settings_folder}")

        settings_file = os.path.join(settings_folder, "ClientAppSettings.json")
        if not os.path.exists(settings_file):
            with open(settings_file, "w") as f:
                json.dump({}, f, indent=4)
            logging.info(f"Created default ClientAppSettings.json file at: {settings_file}")

        default_image_path = os.path.join(images_folder, "play.png")
        target_image_path = os.path.join(new_modpack_folder, "image.png")
        if os.path.exists(default_image_path):
             shutil.copy(default_image_path, target_image_path)
        else:
             logging.warning("Default modpack image not found, skipping image copy.")

        print(f"Applying mods to '{new_modpack_name}'...")
        logging.info(f"Applying imported mods to '{new_modpack_name}'")
        original_selected = selected_modpack.get()
        selected_modpack.set(new_modpack_name)

        applied_count = 0
        skipped_mods = []

        current_mod_state = {key: False for key in mod_apply_functions.keys()}

        for mod_key, should_enable in imported_mod_state.items():
            if mod_key in mod_apply_functions:
                if should_enable:
                    try:
                        print(f"  Enabling mod: {mod_key}")

                        mod_apply_functions[mod_key](True)
                        current_mod_state[mod_key] = True
                        applied_count += 1
                    except Exception as apply_error:
                        messagebox.showwarning("Import Warning", f"Error applying mod '{mod_key}' to '{new_modpack_name}':\n{apply_error}\n\nCheck logs for details. Skipping this mod.")
                        logging.error(f"Error applying mod '{mod_key}' during import to '{new_modpack_name}': {apply_error}")
                        current_mod_state[mod_key] = False
                else:
                     current_mod_state[mod_key] = False
            else:
                logging.warning(f"Imported mod list contains unknown mod key '{mod_key}'. Skipping.")
                skipped_mods.append(mod_key)

        new_mod_state_path = os.path.join(new_modpack_folder, "mod_state.json")
        with open(new_mod_state_path, "w") as f:
            json.dump(current_mod_state, f, indent=4)
        logging.info(f"Saved final mod state to {new_mod_state_path}")

        selected_modpack.set(original_selected)
        modpacks.append(new_modpack_name)
        update_modpacks_frame()
        print(f"Import complete for '{new_modpack_name}'. Applied {applied_count} mods.")
        logging.info(f"Import complete for '{new_modpack_name}'. Applied {applied_count} mods.")
        success_message = f"Successfully imported modpack '{new_modpack_name}'!"
        if skipped_mods:
            success_message += f"\n\nNote: The following mods from the import file were unknown and skipped:\n{', '.join(skipped_mods)}"
        messagebox.showinfo("Import Successful", success_message)

    except FileNotFoundError as fnf_error:
        messagebox.showerror("Import Error", f"File not found during import process:\n{fnf_error}")
        logging.error(f"FileNotFoundError during import: {fnf_error}")

        if os.path.exists(new_modpack_folder):
            shutil.rmtree(new_modpack_folder, ignore_errors=True)
    except PermissionError as perm_error:
         messagebox.showerror("Import Error", f"Permission denied during import process:\n{perm_error}\n\nTry running as administrator.")
         logging.error(f"PermissionError during import: {perm_error}")
         if os.path.exists(new_modpack_folder):
            shutil.rmtree(new_modpack_folder, ignore_errors=True)
    except Exception as e:
        messagebox.showerror("Import Error", f"An unexpected error occurred during import:\n{e}\n\nCheck logs for details.")
        logging.exception("Unexpected error during import process.")

        if os.path.exists(new_modpack_folder):
            shutil.rmtree(new_modpack_folder, ignore_errors=True)

        if new_modpack_name in modpacks: modpacks.remove(new_modpack_name)
        update_modpacks_frame()
        selected_modpack.set(original_selected if 'original_selected' in locals() else "")

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

def create_client_settings():
    folder = get_roblox_folder()
    if folder is None:
        print("Roblox installation not found.")
        return None

    version = os.path.basename(folder)

    dst_folder = os.path.join(os.path.dirname(__file__), "RobloxCopy", version)
    if os.path.exists(dst_folder):
        print(f"Roblox folder with version {version} already exists in project directory.")
        return dst_folder

    shutil.copytree(folder, dst_folder)
    print(f"Copied Roblox folder to {dst_folder}")

    settings_folder = os.path.join(dst_folder, "ClientSettings")
    if not os.path.exists(settings_folder):
        os.makedirs(settings_folder)
        print(f"Created ClientSettings folder at: {settings_folder}")

    return dst_folder

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

        image = Ctk.CTkImage(light_image=Image.open(image_path), size=(145, 145))

        button = Ctk.CTkButton(master=modpacks_image_frame, text=modpack, image=image, compound="top", command=lambda m=modpack: select_modpack(m), fg_color="#222222", hover_color="#000001",width=100, height=200)
        button.grid(row=y, column=x, pady=2, padx=2)

        button.photo = image

        if x < 3:
            x += 1
        else:
            x = 0
            y += 1

def create_modpack():
    try:
        name = name_entry.get()
        if not name:
            print("Please enter a name for the modpack.")
            messagebox.showinfo("Info", f"Please enter a name for the modpack.")
            return

        folder = get_roblox_folder()
        if folder is None:
            print("Roblox installation not found.")
            return None
            messagebox.showerror("Error", f"Roblox installation not found.")

        version = os.path.basename(folder)

        modpack_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ModPacks", name)
        if os.path.exists(modpack_folder):
            print(f"Modpack '{name}' already exists in project directory.")
            return modpack_folder

        script_dir = os.path.dirname(os.path.abspath(__file__))
        modpacks_dir = os.path.join(script_dir, "ModPacks")
        if not os.path.exists(modpacks_dir):
            os.makedirs(modpacks_dir)
            logging.info(f"Created ModPacks folder at: {modpacks_dir}")

        dst_folder = os.path.join(modpack_folder, "RobloxCopy", version)
        shutil.copytree(folder, dst_folder, copy_function=shutil.copy2)
        print(f"Copied Roblox folder to {dst_folder}")
        logging.info(f"Copied Roblox folder to {dst_folder}")

        settings_folder = os.path.join(dst_folder, "ClientSettings")
        if not os.path.exists(settings_folder):
            os.makedirs(settings_folder)
            print(f"Created ClientSettings folder at: {settings_folder}")
            logging.info(f"Created ClientSettings folder at: {settings_folder}")

        settings_file = os.path.join(settings_folder, "ClientAppSettings.json")
        if not os.path.exists(settings_file):
            with open(settings_file, "w") as f:
                json.dump({}, f, indent=4)
            print(f"Created ClientAppSettings.json file at: {settings_file}")
            logging.info(f"Created ClientAppSettings.json file at: {settings_file}")

        if img_data.get() != "None" and img_data.get() != "":
            shutil.copy(img_data.get(), os.path.join(modpack_folder, "image.png"))
        else:
            shutil.copy(os.path.join(images_folder, "play.png"), os.path.join(modpack_folder, "image.png"))

        modpacks.append(name)
        update_modpacks_frame()

        selected_modpack.set(name)

        update_modpacks_frame()

        show_tab("Tab2")

    except Exception as e:
        logging.error(f"Error creating modpack: {e}")

    return modpack_folder

def show_tab(tab):
    Tab1Frame.place_forget()
    Tab2Frame.place_forget()
    Tab3Frame.place_forget()

    if tab == "Tab1":
        Tab1Frame.place(x=10, y=10)
    elif tab == "Tab2":
        Tab2Frame.place(x=10, y=10)

        filter_mods("mods")

        modpack = selected_modpack.get()
        if not modpack:
            return

        icon_path = os.path.join(modpacks_dir, modpack, "image.png")

        icon_image = Ctk.CTkImage(light_image=Image.open(icon_path), size=(125, 125))

        selected_modpack_icon_label.configure(image=icon_image)

        selected_modpack_icon_label.image = icon_image

        modpack_name_label.configure(text=f"{modpack}")

        mod_state_path = os.path.join(modpacks_dir, modpack, "mod_state.json")
        if os.path.exists(mod_state_path):
            with open(mod_state_path, "r") as f:
                mod_state = json.load(f)

            mod_states["Replace Font"].set(mod_state.get("replace_font", False))
            mod_states["Optimizer"].set(mod_state.get("optimizer", False))
            mod_states["Cheat"].set(mod_state.get("cheat", False))
            mod_states["Change celestial bodies"].set(mod_state.get("celestials", False))
            mod_states["Hide gui"].set(mod_state.get("hidegui", False))
            mod_states["Remove grass"].set(mod_state.get("remove_grass_mesh", False))
            mod_states["Display fps"].set(mod_state.get("displayfps", False))
            mod_states["Disable remotes"].set(mod_state.get("disable_remotes", False))
            mod_states["Unlock fps"].set(mod_state.get("unlock_fps", False))
            mod_states["Custom death sound"].set(mod_state.get("custom_ouch_sound", False))
            mod_states["Google browser"].set(mod_state.get("google_browser", False))
            mod_states["Chat gpt"].set(mod_state.get("chat_gpt", False))
            mod_states["R63 avatar"].set(mod_state.get("character_meshes", False))
            mod_states["Faster inputs"].set(mod_state.get("faster_inputs", False))
            mod_states["Graphic boost"].set(mod_state.get("graphic_boost", False))

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

def bg_resizer(e):
    if e.widget is app:
        i = Ctk.CTkImage(image, size=(e.width, e.height))
        bg_lbl.configure(text="", image=i)

mod_states = {}

bg_lbl = Ctk.CTkLabel(app, text="", image=background_image)
bg_lbl.place(x=0, y=0)

label = Ctk.CTkLabel(app, text="")
label.pack(padx=20, pady=20)

tabsFrame = Ctk.CTkScrollableFrame(master=app, width=150, height=605, fg_color="#000000")

tabsText = Ctk.CTkLabel(master=tabsFrame, text="Application")

button = Ctk.CTkButton(master=tabsFrame, text="Create modpacks", command=lambda: show_tab("Tab1"), width=150, height=50)

button2 = Ctk.CTkButton(master=tabsFrame, text="Mods", command=lambda: show_tab("Tab2"), width=150, height=50)

button3 = Ctk.CTkButton(master=tabsFrame, text="Tab 3", command=lambda: show_tab("Tab3"), width=150, height=50)

modpacks_dir = os.path.join(os.path.dirname(__file__), "ModPacks")
if not os.path.exists(modpacks_dir):
    modpacks = []
else:
    modpacks = [f for f in os.listdir(modpacks_dir) if os.path.isdir(os.path.join(modpacks_dir, f))]

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

def change_image():
    image_path = filedialog.askopenfilename(title="Select an image file",filetypes=[("Image files", "*.png;*.jpg;*.jpeg")])
    img_data.set(image_path)

    img3 = Image.open(image_path)
    img4 = Ctk.CTkImage(img3, size=(75, 75))

    change_button.configure(image=img4)

Tab1Frame = Ctk.CTkFrame(master=app, width=700, height=780, fg_color="#111111")
Tab1Frame.pack_propagate(False)

img_data = Ctk.StringVar(value="None")
createblur = Ctk.CTkFrame(master=app, width=700, height=702, fg_color="#111111")
createblur.pack_propagate(False)
createframe = Ctk.CTkFrame(master=app, width=500, height=500, fg_color="#222222")
createframe.pack_propagate(False)

simple_frame = Ctk.CTkFrame(master=createframe, width=700, height=45, fg_color="#222222")
simple_frame.pack_propagate(False)
simple_frame.pack(pady=30, padx=20, side=Ctk.TOP, expand = False)

simple_frame2 = Ctk.CTkFrame(master=createframe, width=700, height=90, fg_color="#222222")
simple_frame2.pack_propagate(False)
simple_frame2.pack(pady=0, padx=20, side=Ctk.TOP, expand = False)

simple_frame3 = Ctk.CTkFrame(master=simple_frame2, width=200, height=90, fg_color="#222222")
simple_frame3.pack_propagate(False)
simple_frame3.pack(pady=0, padx=50, side=Ctk.RIGHT, expand = False)

simple_frame4 = Ctk.CTkFrame(master=simple_frame2, width=200, height=200, fg_color="#222222")
simple_frame4.pack_propagate(False)
simple_frame4.pack(pady=0, padx=10, side=Ctk.LEFT, expand = False)

label_new = Ctk.CTkLabel(master=simple_frame, text="Create a profile", font=Ctk.CTkFont(family="Impact", size=24))
label_new.pack(pady=10, padx=10, side=Ctk.LEFT)

label_new2 = Ctk.CTkLabel(master=simple_frame3, text="Profile name", font=Ctk.CTkFont(family="Impact", size=20))
label_new2.pack(pady=10, padx=10, side=Ctk.TOP)

name_entry = Ctk.CTkEntry(master=simple_frame3, placeholder_text="Profile name", width=250)
framenew = Ctk.CTkFrame(master=createframe, width=700, height=90, fg_color="#222222")
create_button = Ctk.CTkButton(master=framenew, text="Create", command=create_modpack, width=130, height=70, fg_color="#111111", hover_color="#000001", font=Ctk.CTkFont(family="Impact", size=20))
cancel_button = Ctk.CTkButton(master=framenew, text="Cancel", command=remove_modpack_tab, width=185, height=70, fg_color="#111111", hover_color="#000001", font=Ctk.CTkFont(family="Impact", size=20))
framenew.pack(pady=0, padx=20, side=Ctk.BOTTOM, expand = False)

img1 = Image.open((os.path.join(images_folder, "play.png")))
img2 = Ctk.CTkImage(img1, size=(75, 75))

change_button = Ctk.CTkButton(master=simple_frame4, text="", command=change_image, width=75, height=150, image=img2, fg_color="#111111", hover_color="#000001")

change_button.pack_propagate(False)

name_entry.pack(pady=0, padx=0, side=Ctk.RIGHT)
create_button.pack(pady=20, padx=50, side=Ctk.RIGHT)
cancel_button.pack(pady=20, padx=50, side=Ctk.LEFT)
change_button.pack(pady=0, padx=0, side=Ctk.BOTTOM, fill = 'y')

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

multi_roblox_enabled = Ctk.BooleanVar(value=False)

img_data = Ctk.StringVar(value="None")
createblur2 = Ctk.CTkFrame(master=app, width=700, height=702, fg_color="#111111")
createblur2.pack_propagate(False)
createframe2 = Ctk.CTkFrame(master=app, width=500, height=500, fg_color="#222222")
cancel_button2 = Ctk.CTkButton(master=createframe2, text="Cancel", command=remove_settings_tab, width=175, height=70, fg_color="#111111", hover_color="#000001", font=Ctk.CTkFont(family="Impact", size=20))
createframe2.pack_propagate(False)
pywinstyles.set_opacity(createblur2, value=0.5, color="#000001")

settingframe2 = Ctk.CTkFrame(master=createframe2, width=490, height=60, fg_color="#111111")
settingframe2.pack_propagate(False)

label2 = Ctk.CTkLabel(master=settingframe2,text="Multi-Instance")

settingframe2.pack(pady=5)

switch2 = Ctk.CTkSwitch(master=settingframe2, text="", variable=multi_roblox_enabled, command=toggle_multi_roblox)
switch2.pack(pady=10, padx=10, side="right")
label2.pack(pady=10, padx=20, side="left")

cancel_button2.pack(pady=20, padx=50, side=Ctk.BOTTOM)

pywinstyles.set_opacity(createblur, value=0.5, color="#000001")

img = Image.open((os.path.join(images_folder, "play.png")))
img_logo = Ctk.CTkImage(img, size=(50, 50))
upperframe = Ctk.CTkFrame(master=Tab1Frame, width=700, height=50, fg_color="#111111")
upperframe.pack(pady=20, padx=20, expand = False)
label1 = Ctk.CTkLabel(master=upperframe, text="", image=img_logo, width=50, height=50)
label1.pack(pady=0, padx=0, side="left")
label = Ctk.CTkLabel(master=upperframe, text="RoForge", font=Ctk.CTkFont(family="Impact", size=24))
label.pack(pady=20, padx=20, side="top")
label2 = Ctk.CTkFrame(master=Tab1Frame, width=815, height=2, fg_color="#444444")
label2.pack_propagate(False)
label2.pack(pady=5, padx=20, side="top", expand = False)
middleframe = Ctk.CTkFrame(master=Tab1Frame, width=700, height=75, fg_color="#111111")
middleframe.pack_propagate(False)
middleframe.pack(pady=10, padx=20, expand = False)

create_start_button = Ctk.CTkButton(master=middleframe, text="+ Create", font=Ctk.CTkFont(family="Impact", size=22), command=create_modpack_tab, fg_color="#111111", hover_color="#000001", width=155, height=50)
create_start_button.pack(pady=0, padx=0, side=Ctk.LEFT)

create_settings_button = Ctk.CTkButton(master=middleframe, text="⚙ Settings", font=Ctk.CTkFont(family="Impact", size=22), command=create_settings_tab, fg_color="#111111", hover_color="#000001", width=155, height=50)
create_settings_button.pack(pady=0, padx=0, side=Ctk.LEFT)

modpacks_image_frame = Ctk.CTkScrollableFrame(master=Tab1Frame, width=600, height=605, fg_color="#111111", corner_radius=1)
modpacks_image_frame.pack(pady=0, padx=10, side=Ctk.TOP, expand = False, fill = 'both')
x_max = 4
y_max = 4

def select_modpack(m):
    selected_modpack.set(m)
    show_tab("Tab2")

global x, y
x=0
y=0

for modpack in modpacks:
    image_path = os.path.join(modpacks_dir, modpack, "image.png")

    image = Ctk.CTkImage(light_image=Image.open(image_path), size=(145, 145))

    button = Ctk.CTkButton(master=modpacks_image_frame, text=modpack, image=image, compound="top", command=lambda m=modpack: select_modpack(m), fg_color="#222222", hover_color="#000001", width=100, height=200)
    button.grid(row=y, column=x, pady=2, padx=2)

    button.photo = image

    if x < 3:
        x += 1
    else:
        x = 0
        y += 1
    print(x, y)

Tab2Frame = Ctk.CTkFrame(master=app, width=700, height=780, fg_color="#111111")
Tab2Frame.pack_propagate(False)

selected_modpack = Ctk.StringVar(value="")

modstop = Ctk.CTkFrame(master=Tab2Frame, width=800, height=150)
modstop.pack_propagate(False)
modstop.pack(pady=20, padx=20)

selected_modpack_icon_label = Ctk.CTkLabel(master=modstop, text="", image=None, width=125, height=125)
selected_modpack_icon_label.pack(pady=10, padx=30, side="left")

selected_modpack = Ctk.StringVar(value=f"")
modpack_menu = Ctk.CTkOptionMenu(master=Tab2Frame, variable=selected_modpack)

def load_fast_flags():
    modpack = selected_modpack.get()
    if not modpack:
        messagebox.showwarning("Warning", "Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

    json_content = text_widget.get(1.0, "end")

    try:
        settings = json.loads(json_content)

        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=4)

        messagebox.showinfo("Info", "Fast flags saved successfully.")
    except json.JSONDecodeError:
        messagebox.showerror("Error", "Invalid JSON content. Please check the syntax.")

def toggle_fflag_editor():
    if fflag_editor_frame.winfo_ismapped():
        createblur3.place_forget()
        fflag_editor_frame.place_forget()
    else:
        load_fast_flags()
        fflag_editor_frame.place(x=60, y=75)
        createblur3.place(x=10, y=10)

fflag_editor_button_frame = Ctk.CTkFrame(Tab2Frame, width=660, height=50, fg_color="#111111")

fflag_editor_button_frame.pack_propagate(False)
fflag_editor_button_frame.pack(pady=0, side="top")

fflag_editor_button = Ctk.CTkButton(fflag_editor_button_frame, text="⚙ Fast Flags Editor", command=toggle_fflag_editor, fg_color="#111111", hover_color="#000001", height=50, font=Ctk.CTkFont(family="Impact", size=15))
fflag_editor_button.pack(pady=0, padx=45, side="right")

def launch_modpack():
    modpack = selected_modpack.get()
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    roblox_exe_path = os.path.join(roblox_path, version, "RobloxPlayerBeta.exe")

    subprocess.Popen([roblox_exe_path])

upperframe2 = Ctk.CTkFrame(master=modstop, width=475, height=600, fg_color="#222222")
upperframe2.pack_propagate(False)
upperframe2.pack(pady=10, padx=1, side="right", expand = False)

upperframe3 = Ctk.CTkFrame(master=upperframe2, width=200, height=600, fg_color="#222222")
upperframe3.pack_propagate(False)
upperframe3.pack(pady=10, padx=1, side="right", expand = False)

modpack_name_label = Ctk.CTkLabel(master=upperframe2, text="", font=("Impact", 24))
modpack_name_label.pack(pady=20, side="left")

upperframe4 = Ctk.CTkFrame(master=upperframe3, width=200, height=50, fg_color="#222222")
upperframe4.pack_propagate(False)
upperframe4.pack(pady=10, padx=1, side="top", expand = False)

launch_button = Ctk.CTkButton(master=upperframe4, text="▷ Launch", command=launch_modpack, width=150, height=25, fg_color="#222222", hover_color="#000001", font=Ctk.CTkFont(family="Impact", size=22))
launch_button.pack(pady=0, padx=0, side="left")

export_button = Ctk.CTkButton(master=upperframe4, text="📤", command=export_modpack, fg_color="#222222", hover_color="#000001", width=25, height=25, font=Ctk.CTkFont(family="Impact", size=22))
export_button.pack(pady=0, padx=0, side="left")

cancel_button = Ctk.CTkButton(master=upperframe3, text="❌", command=show_tab1, width=190, height=25, fg_color="#111111", hover_color="#000001", font=Ctk.CTkFont(family="Impact", size=22))
cancel_button.pack(pady=0, padx=0, side="left")
cancel_button.pack_propagate(False)

mods = Ctk.CTkScrollableFrame(master=Tab2Frame, width=800, height=600)
mods.pack(pady=20, padx=20)

label3 = Ctk.CTkFrame(master=Tab2Frame, width=400, height=2, fg_color="#555555")
label3.pack_propagate(False)
label3.pack(pady=3, padx=1, side="bottom", expand = False)

show_mods_button = Ctk.CTkButton(fflag_editor_button_frame, text="Mods", command=lambda: filter_mods("mods"), fg_color="#111111", hover_color="#000001", height=50, font=Ctk.CTkFont(family="Impact", size=20))
show_mods_button.pack(pady=0, padx=5, side="left")

show_texturepacks_button = Ctk.CTkButton(fflag_editor_button_frame, text="Texture Packs", command=lambda: filter_mods("texturepacks"), fg_color="#111111", hover_color="#000001", height=50, font=Ctk.CTkFont(family="Impact", size=20))
show_texturepacks_button.pack(pady=0, padx=5, side="left")

def add_mod_switch(mod_name, mod_function, icon_path):

    mod_state = Ctk.BooleanVar(value=False)
    mod_states[mod_name] = mod_state

    modframe = Ctk.CTkFrame(master=mods, width=800, height=80, fg_color="#111111")
    modframe.pack_propagate(False)

    icon_image = Ctk.CTkImage(light_image=Image.open(icon_path), size=(50, 50))

    icon_label = Ctk.CTkLabel(master=modframe, image=icon_image, text="")
    icon_label.pack(pady=10, padx=10, side="left")

    switch = Ctk.CTkSwitch(master=modframe, text="", variable=mod_state, command=lambda: mod_function(mod_state.get()))
    switch.pack(pady=10, padx=10, side="right")
    text = Ctk.CTkLabel(master=modframe, text=mod_name)
    text.pack(pady=10, padx=10, side="left")
    modframe.pack(pady=10, padx=10)

    icon_label.image = icon_image

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

        if os.path.exists(moon_original_path) and os.path.exists(sun_original_path):

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

    handle = kernel32.CreateFileW(file_path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None)
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

        custom_font_path = filedialog.askopenfilename(title="Select a font file", filetypes=[("Font files", "*.otf;*.ttf")])
        if custom_font_path:

            backup_dir = os.path.join(fonts_dir, "backup")
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            for font_file in os.listdir(fonts_dir):
                if font_file.endswith(".otf") or font_file.endswith(".ttf"):
                    shutil.copy(os.path.join(fonts_dir, font_file), backup_dir)

            for font_file in os.listdir(fonts_dir):
                if font_file.endswith(".otf") or font_file.endswith(".ttf"):
                    shutil.copy(custom_font_path, os.path.join(fonts_dir, font_file))
            print(f"Replaced all fonts in modpack '{modpack}' with {custom_font_path}")
    else:

        backup_dir = os.path.join(fonts_dir, "backup")
        if os.path.exists(backup_dir):
            for font_file in os.listdir(backup_dir):

                os.remove(os.path.join(fonts_dir, font_file))
                shutil.copy(os.path.join(backup_dir, font_file), os.path.join(fonts_dir, font_file))
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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["FFlagOptimizeNetwork"] = "True"
        settings["FFlagOptimizeNetworkRouting"] = "True"
        settings["FFlagOptimizeNetworkTransport"] = "True"
        settings["FFlagOptimizeServerTickRate"] = "True"
        print(f"Enabled 'Optimizer' mod for modpack '{modpack}'")
    else:

        settings["FFlagOptimizeNetwork"] = "False"
        settings["FFlagOptimizeNetworkRouting"] = "False"
        settings["FFlagOptimizeNetworkTransport"] = "False"
        settings["FFlagOptimizeServerTickRate"] = "False"
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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["FFlagUserShowGuiHideToggles"] = "True"
        settings["GuiHidingApiSupport2"] = "True"
        settings["DFIntCanHideGuiGroupId"] = "3375285"

        print(f"Enabled 'Hide gui' mod for modpack '{modpack}'")
    else:

        settings["FFlagUserShowGuiHideToggles"] = "False"
        settings["GuiHidingApiSupport2"] = "False"
        settings["DFIntCanHideGuiGroupId"] = "0"
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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:
        settings["FFlagDebugDisplayFPS"] = "True"

        print(f"Enabled 'Display fps' mod for modpack '{modpack}'")
    else:
        settings["FFlagDebugDisplayFPS"] = "False"
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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["FFlagPlatformEventEnabled2"] = "True"
        settings["FStringPlatformEventUrl"] = "https://google.com/"
        settings["FFlagTopBarUseNewBadge"] = "True"
        settings["FStringTopBarBadgeLearnMoreLink"] = "https://google.com/"
        settings["FStringVoiceBetaBadgeLearnMoreLink"] = "https://google.com/"
        print(f"Enabled 'Google browser' mod for modpack '{modpack}'")
    else:
        settings.pop("FFlagPlatformEventEnabled2", None)
        settings.pop("FStringPlatformEventUrl", None)
        settings.pop("FFlagTopBarUseNewBadge", None)
        settings.pop("FStringTopBarBadgeLearnMoreLink", None)
        settings.pop("FStringVoiceBetaBadgeLearnMoreLink", None)
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
    original_meshes_path = os.path.join(roblox_path, version, "content", "avatar", "meshes")
    backup_meshes_path = os.path.join(roblox_path, version, "content", "avatar", "meshes_backup")
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
        print(f"Replaced character meshes with custom ones in modpack '{modpack}'")
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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["FFlagPlatformEventEnabled2"] = "True"
        settings["FStringPlatformEventUrl"] = "https://chatbotchatapp.com/"
        settings["FFlagTopBarUseNewBadge"] = "True"
        settings["FStringTopBarBadgeLearnMoreLink"] = "https://chatbotchatapp.com/"
        settings["FStringVoiceBetaBadgeLearnMoreLink"] = "https://chatbotchatapp.com/"
        print(f"Enabled 'Google browser' mod for modpack '{modpack}'")
    else:
        settings.pop("FFlagPlatformEventEnabled2", None)
        settings.pop("FStringPlatformEventUrl", None)
        settings.pop("FFlagTopBarUseNewBadge", None)
        settings.pop("FStringTopBarBadgeLearnMoreLink", None)
        settings.pop("FStringVoiceBetaBadgeLearnMoreLink", None)
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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:

        settings["FIntActivatedCountTimerMSKeyboard"] = 1
        print(f"Enabled 'Unlock fps' mod for modpack '{modpack}'")
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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

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

    settings_path = os.path.join(roblox_path, version, "ClientSettings", "ClientAppSettings.json")

    with open(settings_path, "r") as f:
        settings = json.load(f)

    if enabled:
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

import os
import shutil
import json
import customtkinter as Ctk
from tkinter import filedialog

def apply_custom_ouch_sound(enabled):
    modpack = selected_modpack.get()
    if not modpack:
        print("Please select a modpack.")
        return

    roblox_path = os.path.join(modpacks_dir, modpack, "RobloxCopy")
    version = os.listdir(roblox_path)[0]

    ouch_path = os.path.join(roblox_path, version, "content", "sounds", "ouch.ogg")

    if enabled:

        if os.path.exists(ouch_path):

            shutil.copy(ouch_path, os.path.join(roblox_path, version, "content", "sounds", "ouch_original.ogg"))

        new_ouch_path = filedialog.askopenfilename(title="Select a new ouch.ogg file", filetypes=[("Ogg files", "*.ogg")])
        if new_ouch_path:
            shutil.copy(new_ouch_path, ouch_path)
            print(f"Replaced ouch.ogg in modpack '{modpack}' with {new_ouch_path}")
    else:

        original_ouch_path = os.path.join(roblox_path, version, "content", "sounds", "ouch_original.ogg")
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

add_mod_switch("R63 avatar", replace_character_meshes, os.path.join(images_folder, "girl.jpg"))
add_mod_switch("Faster inputs", faster_inputs, os.path.join(images_folder, "keyboard.png"))
add_mod_switch("Replace Font", replace_font, os.path.join(images_folder, "Replace Font.png"))
add_mod_switch("Optimizer", apply_optimizer, os.path.join(images_folder, "Optimizer.png"))
add_mod_switch("Cheat", apply_cheat, os.path.join(images_folder, "cheat.png"))
add_mod_switch("Change celestial bodies", apply_day_night_cycle, os.path.join(images_folder, "moon.jpg"))
add_mod_switch("Hide gui", apply_hide_gui, os.path.join(images_folder, "hide.png"))
add_mod_switch("Remove grass", apply_remove_grass_mesh, os.path.join(images_folder, "grass.png"))
add_mod_switch("Display fps", apply_display_fps, os.path.join(images_folder, "displayfps.png"))
add_mod_switch("Disable remotes", disable_remotes, os.path.join(images_folder, "RemoteEvent.png"))
add_mod_switch("Unlock fps", unlock_fps, os.path.join(images_folder, "unlock_fps.png"))
add_mod_switch("Custom death sound", apply_custom_ouch_sound, os.path.join(images_folder, "noob.png"))
add_mod_switch("Google browser", google_browser, os.path.join(images_folder,"google.png"))
add_mod_switch("Chat gpt", chat_gpt, os.path.join(images_folder,"ChatGPT_logo.svg.png"))
add_mod_switch("Graphic boost", graphic_boost, os.path.join(images_folder,"graphics.png"))

createblur3 = Ctk.CTkFrame(master=app, width=700, height=780, fg_color="#111111")

fflag_editor_frame = Ctk.CTkFrame(master=app, width=600, height=650, fg_color="#111111")
fflag_editor_blur = Ctk.CTkFrame(master=app, width=700, height=702, fg_color="#111111")
fflag_editor_blur.pack_propagate(False)
fflag_editor_frame.pack_propagate(False)

pywinstyles.set_opacity(fflag_editor_blur, value=0.5, color="#000001")

text_widget = Ctk.CTkTextbox(fflag_editor_frame, wrap="none", width=80, height=20, fg_color="#222222")
text_widget.pack(side="left", fill="both", expand=True)

scrollbar = Ctk.CTkScrollbar(fflag_editor_frame, command=text_widget.yview)
scrollbar.pack(side="right", fill="y")
text_widget.configure(yscrollcommand=scrollbar.set)

label_new3 = Ctk.CTkLabel(master=fflag_editor_frame, text="FastFlags editor", font=Ctk.CTkFont(family="Impact", size=20))
label_new3.pack(pady=10, padx=5)
fflag_editor_button2 = Ctk.CTkButton(fflag_editor_frame, text="Cancel", command=toggle_fflag_editor, height=50, fg_color="#111111", hover_color="#000001",font=Ctk.CTkFont(family="Impact", size=18))
fflag_editor_button2.pack(pady=10, padx=5)
save_fflags_button = Ctk.CTkButton(fflag_editor_frame, text="Save Fast Flags", command=save_fast_flags, height=50, fg_color="#111111", hover_color="#000001",font=Ctk.CTkFont(family="Impact", size=18))
save_fflags_button.pack(pady=10)

pywinstyles.set_opacity(createblur3, value=0.5, color="#000001")

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
    "graphic_boost": graphic_boost
}

import_button = Ctk.CTkButton(master=middleframe, text="📥 Import", font=Ctk.CTkFont(family="Impact", size=22), command=import_modpack, fg_color="#111111", hover_color="#000001", width=155, height=50)
import_button.pack(pady=0, padx=0, side=Ctk.LEFT)

Tab3Frame = Ctk.CTkScrollableFrame(master=app, width=700, height=770, fg_color="#111111")
label = Ctk.CTkLabel(master=Tab3Frame, text="This is Tab 3", font=Ctk.CTkFont(family="Impact", size=24))
label.pack(pady=20, padx=20)

show_tab("Tab1")

app.bind("<Configure>", bg_resizer)

app.mainloop()
