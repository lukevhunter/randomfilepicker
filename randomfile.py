from collections import deque
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
  from PIL import Image, ImageTk

  HAS_PILLOW = True
except ImportError:
  HAS_PILLOW = False

try:
  import pygame

  pygame.mixer.init()
  HAS_PYGAME = True
except ImportError:
  HAS_PYGAME = False

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"}

PRESETS = {
    "All Files": set(),
    "Images": IMAGE_EXTENSIONS,
    "Audio": AUDIO_EXTENSIONS,
    "Video": VIDEO_EXTENSIONS,
    "Folders": "FOLDERS",
    "Custom": None,
}

THEMES = {
    "Light": {
        "bg": "#f4f6f9",
        "card_bg": "#ffffff",
        "fg": "#2d3748",
        "muted": "#718096",
        "border": "#e2e8f0",
        "input_bg": "#ffffff",
        "input_fg": "#2d3748",
        "canvas_bg": "#fafbfc",
        "highlight_bg": "#ebf8ff",
        "highlight_fg": "#2b6cb0",
    },
    "Dark": {
        "bg": "#1a202c",
        "card_bg": "#2d3748",
        "fg": "#e2e8f0",
        "muted": "#a0aec0",
        "border": "#4a5568",
        "input_bg": "#1a202c",
        "input_fg": "#e2e8f0",
        "canvas_bg": "#171923",
        "highlight_bg": "#2b6cb0",
        "highlight_fg": "#ffffff",
    },
    "Dracula": {
        "bg": "#282a36",
        "card_bg": "#44475a",
        "fg": "#f8f8f2",
        "muted": "#6272a4",
        "border": "#6272a4",
        "input_bg": "#282a36",
        "input_fg": "#f8f8f2",
        "canvas_bg": "#21222c",
        "highlight_bg": "#6272a4",
        "highlight_fg": "#f8f8f2",
    },
    "Solarized Light": {
        "bg": "#fdf6e3",
        "card_bg": "#eee8d5",
        "fg": "#657b83",
        "muted": "#93a1a1",
        "border": "#93a1a1",
        "input_bg": "#eee8d5",
        "input_fg": "#657b83",
        "canvas_bg": "#fdf6e3",
        "highlight_bg": "#2aa198",
        "highlight_fg": "#ffffff",
    },
}


class RandomFilePickerApp:

  def __init__(self, root):
    self.root = root
    self.root.title("Random File & Media Picker")
    self.root.geometry("1000x740")
    self.root.minsize(800, 550)

    self.current_theme_name = "Light"
    self.colors = THEMES[self.current_theme_name]
    self.root.configure(bg=self.colors["bg"])

    self.thumbnail_size = 210
    self.cell_padding = 8
    self.num_columns = 0

    self.raw_images = []
    self.current_images = []
    self.media_labels = []
    self.path_to_label = {}
    self.current_highlighted_label = None

    self.roll_history = []
    self.max_history = 5
    self.last_chosen_files = []
    self.last_media_data = []

    self.slideshow_running = False
    self.slideshow_job_id = None
    self.slideshow_interval_var = tk.IntVar(value=5)

    self.setup_styles()
    self.create_widgets()
    self.root.protocol("WM_DELETE_WINDOW", self.on_close)

  def setup_styles(self):
    self.style = ttk.Style()
    self.style.theme_use("clam")
    self.update_ttk_styles()

  def update_ttk_styles(self):
    c = self.colors
    self.style.configure(
        "TCombobox",
        fieldbackground=c["input_bg"],
        background=c["card_bg"],
        foreground=c["input_fg"],
        selectbackground=c["highlight_bg"],
        selectforeground=c["highlight_fg"],
    )
    self.style.map(
        "TCombobox",
        fieldbackground=[("readonly", c["input_bg"])],
        foreground=[("readonly", c["input_fg"])],
    )
    self.style.configure(
        "Horizontal.TProgressbar",
        troughcolor=c["border"],
        background="#2f855a",
        thickness=6,
    )

  def on_theme_change(self, event=None):
    theme_name = self.theme_var.get()
    if theme_name in THEMES:
      self.current_theme_name = theme_name
      self.colors = THEMES[theme_name]
      self.update_ttk_styles()
      self.root.configure(bg=self.colors["bg"])

      folder_text = (
          self.folder_entry.get() if hasattr(self, "folder_entry") else ""
      )
      current_list_items = (
          list(self.file_listbox.get(0, tk.END))
          if hasattr(self, "file_listbox")
          else []
      )

      for widget in self.root.winfo_children():
        widget.destroy()

      self.create_widgets()

      if folder_text and hasattr(self, "folder_entry"):
        self.folder_entry.delete(0, tk.END)
        self.folder_entry.insert(0, folder_text)

      if current_list_items and hasattr(self, "file_listbox"):
        for item in current_list_items:
          self.file_listbox.insert(tk.END, item)

      if self.last_media_data:
        allow_media = self.preset_var.get() in (
            "All Files",
            "Images",
            "Audio",
            "Video",
            "Folders",
        ) or (
            self.preset_var.get() == "Custom"
            and any(
                ext in IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
                for ext in self.get_valid_exts()
            )
        )
        self.update_ui_with_results(
            self.last_chosen_files, self.last_media_data, allow_media
        )

  def create_widgets(self):
    c = self.colors
    main_wrapper = tk.Frame(self.root, bg=c["bg"], padx=14, pady=14)
    main_wrapper.pack(fill="both", expand=True)

    frame_folder = tk.Frame(main_wrapper, bg=c["card_bg"], padx=12, pady=10)
    frame_folder.pack(fill="x", pady=(0, 10))

    tk.Label(
        frame_folder,
        text="Folder:",
        bg=c["card_bg"],
        fg=c["fg"],
        font=("Segoe UI", 10, "bold"),
    ).pack(side="left")
    self.folder_entry = tk.Entry(
        frame_folder,
        bg=c["input_bg"],
        fg=c["input_fg"],
        insertbackground=c["fg"],
        font=("Segoe UI", 10),
        relief="solid",
        bd=1,
        highlightthickness=0,
    )
    self.folder_entry.pack(side="left", padx=8, expand=True, fill="x")
    tk.Button(
        frame_folder,
        text="Browse...",
        command=self.select_folder,
        bg=c["border"],
        fg=c["fg"],
        font=("Segoe UI", 9, "bold"),
        relief="flat",
        padx=10,
        pady=3,
        cursor="hand2",
    ).pack(side="right")

    frame_options = tk.Frame(main_wrapper, bg=c["bg"])
    frame_options.pack(fill="x", pady=(0, 10))

    self.recursive_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        frame_options,
        text="Include Subfolders",
        variable=self.recursive_var,
        bg=c["bg"],
        fg=c["fg"],
        font=("Segoe UI", 9),
        selectcolor=c["card_bg"],
        activebackground=c["bg"],
        activeforeground=c["fg"],
    ).pack(side="left")

    tk.Label(
        frame_options,
        text="Count:",
        bg=c["bg"],
        fg=c["muted"],
        font=("Segoe UI", 9, "bold"),
    ).pack(side="left", padx=(16, 4))
    self.count_var = tk.IntVar(value=1)
    self.count_spin = tk.Spinbox(
        frame_options,
        from_=1,
        to=1000,
        width=5,
        textvariable=self.count_var,
        wrap=True,
        bg=c["input_bg"],
        fg=c["input_fg"],
        font=("Segoe UI", 9),
        relief="solid",
        bd=1,
    )
    self.count_spin.pack(side="left")

    tk.Label(
        frame_options,
        text="Filter:",
        bg=c["bg"],
        fg=c["muted"],
        font=("Segoe UI", 9, "bold"),
    ).pack(side="left", padx=(16, 4))
    self.preset_var = tk.StringVar(value="All Files")
    preset_dropdown = ttk.Combobox(
        frame_options,
        textvariable=self.preset_var,
        values=list(PRESETS.keys()),
        state="readonly",
        width=11,
        font=("Segoe UI", 9),
    )
    preset_dropdown.pack(side="left")
    preset_dropdown.bind("<<ComboboxSelected>>", self.on_preset_change)

    self.ext_entry = tk.Entry(
        frame_options,
        width=16,
        state="disabled",
        bg=c["input_bg"],
        fg=c["input_fg"],
        insertbackground=c["fg"],
        font=("Segoe UI", 9),
        relief="solid",
        bd=1,
    )
    self.ext_entry.pack(side="left", padx=8)
    self.ext_entry.insert(0, "png, mp3, mp4")
    self.ext_entry.bind(
        "<KeyRelease>", lambda e: self.update_preview_state_based_on_exts()
    )

    tk.Label(
        frame_options,
        text="Theme:",
        bg=c["bg"],
        fg=c["muted"],
        font=("Segoe UI", 9, "bold"),
    ).pack(side="left", padx=(16, 4))
    self.theme_var = tk.StringVar(value=self.current_theme_name)
    theme_dropdown = ttk.Combobox(
        frame_options,
        textvariable=self.theme_var,
        values=list(THEMES.keys()),
        state="readonly",
        width=12,
        font=("Segoe UI", 9),
    )
    theme_dropdown.pack(side="left")
    theme_dropdown.bind("<<ComboboxSelected>>", self.on_theme_change)

    frame_action = tk.Frame(main_wrapper, bg=c["bg"])
    frame_action.pack(fill="x", pady=(0, 10))

    self.btn_pick = tk.Button(
        frame_action,
        text="Pick Random Files",
        command=self.start_pick_thread,
        bg="#2f855a",
        fg="white",
        font=("Segoe UI", 10, "bold"),
        relief="flat",
        padx=14,
        pady=6,
        cursor="hand2",
    )
    self.btn_pick.pack(side="left", expand=True, fill="x", padx=(0, 6))

    btn_explorer = tk.Button(
        frame_action,
        text="Show Selected in Explorer",
        command=self.open_selected_in_explorer,
        bg="#3182ce",
        fg="white",
        font=("Segoe UI", 9, "bold"),
        relief="flat",
        padx=10,
        pady=6,
        cursor="hand2",
    )
    btn_explorer.pack(side="right", expand=True, fill="x", padx=(6, 0))

    btn_slideshow = tk.Button(
        frame_action,
        text="⏱️ Slideshow",
        command=self.open_slideshow_window,
        bg="#2b6cb0",
        fg="white",
        font=("Segoe UI", 9, "bold"),
        relief="flat",
        padx=10,
        pady=6,
        cursor="hand2",
    )
    btn_slideshow.pack(side="right", padx=4)

    btn_copy = tk.Button(
        frame_action,
        text="📂 Copy Picked",
        command=self.copy_picked_items,
        bg="#805ad5",
        fg="white",
        font=("Segoe UI", 9, "bold"),
        relief="flat",
        padx=10,
        pady=6,
        cursor="hand2",
    )
    btn_copy.pack(side="right", padx=4)

    btn_history = tk.Button(
        frame_action,
        text="📜 Roll History",
        command=self.open_history_window,
        bg="#dd6b20",
        fg="white",
        font=("Segoe UI", 9, "bold"),
        relief="flat",
        padx=10,
        pady=6,
        cursor="hand2",
    )
    btn_history.pack(side="right", padx=4)

    frame_progress = tk.Frame(main_wrapper, bg=c["bg"])
    frame_progress.pack(fill="x", pady=(0, 6))
    self.progress = ttk.Progressbar(
        frame_progress,
        orient="horizontal",
        mode="indeterminate",
        style="Horizontal.TProgressbar",
    )
    self.progress.pack(fill="x")

    content_frame = tk.Frame(main_wrapper, bg=c["bg"])
    content_frame.pack(fill="both", expand=True)

    list_frame = tk.LabelFrame(
        content_frame,
        text=" Selected Items ",
        bg=c["card_bg"],
        fg=c["fg"],
        font=("Segoe UI", 9, "bold"),
        padx=8,
        pady=8,
        relief="solid",
        bd=1,
    )
    list_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))

    self.file_listbox = tk.Listbox(
        list_frame,
        selectmode=tk.SINGLE,
        font=("Segoe UI", 9),
        bg=c["input_bg"],
        fg=c["input_fg"],
        selectbackground=c["highlight_bg"],
        selectforeground=c["highlight_fg"],
        highlightthickness=0,
        relief="flat",
    )
    self.file_listbox.pack(side="left", fill="both", expand=True)
    self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)

    list_scroll = ttk.Scrollbar(
        list_frame, orient="vertical", command=self.file_listbox.yview
    )
    list_scroll.pack(side="right", fill="y")
    self.file_listbox.config(yscrollcommand=list_scroll.set)

    self.preview_outer = tk.LabelFrame(
        content_frame,
        text=" Previews ",
        bg=c["card_bg"],
        fg=c["fg"],
        font=("Segoe UI", 9, "bold"),
        padx=8,
        pady=8,
        relief="solid",
        bd=1,
    )
    self.preview_outer.pack(side="right", fill="both", expand=True, padx=(6, 0))

    self.canvas = tk.Canvas(
        self.preview_outer, bg=c["canvas_bg"], highlightthickness=0
    )
    self.preview_scroll = ttk.Scrollbar(
        self.preview_outer, orient="vertical", command=self.canvas.yview
    )
    self.preview_inner = tk.Frame(self.canvas, bg=c["canvas_bg"])

    self.canvas_window = self.canvas.create_window(
        (0, 0), window=self.preview_inner, anchor="nw"
    )

    self.preview_inner.bind(
        "<Configure>",
        lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")
        ),
    )
    self.canvas.bind("<Configure>", self.on_canvas_resize)
    self.canvas.configure(yscrollcommand=self.preview_scroll.set)

    self.canvas.pack(side="left", fill="both", expand=True)
    self.preview_scroll.pack(side="right", fill="y")

    warnings = []
    if not HAS_PILLOW:
      warnings.append("Pillow")
    if not HAS_PYGAME:
      warnings.append("pygame")

    if warnings:
      warning_lbl = tk.Label(
          main_wrapper,
          text=(
              "Tip: Run 'pip install " + " ".join(warnings) +
              "' for full feature support."
          ),
          fg="#e53e3e",
          bg=c["bg"],
          font=("Segoe UI", 9),
      )
      warning_lbl.pack(pady=(6, 0))

  def on_preset_change(self, event=None):
    preset = self.preset_var.get()
    if preset == "Custom":
      self.ext_entry.config(state="normal")
    else:
      self.ext_entry.config(state="disabled")
    self.update_preview_state_based_on_exts()

  def get_valid_exts(self):
    preset = self.preset_var.get()
    if preset != "Custom":
      return PRESETS[preset]
    else:
      ext_text = self.ext_entry.get().strip()
      if not ext_text:
        return set()
      parts = [
          e.strip() for e in ext_text.replace(",", " ").split() if e.strip()
      ]
      return {e if e.startswith(".") else f".{e}" for e in parts}

  def update_preview_state_based_on_exts(self):
    preset = self.preset_var.get()
    if preset in ("All Files", "Images", "Audio", "Video", "Folders"):
      allow_media = True
    else:
      valid_exts = self.get_valid_exts()
      allow_media = any(
          ext in IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
          for ext in valid_exts
      )

    self.set_media_section_state(enabled=allow_media)

  def set_media_section_state(self, enabled):
    c = self.colors
    self.stop_audio()
    for widget in self.preview_inner.winfo_children():
      widget.destroy()
    self.raw_images.clear()
    self.current_images.clear()
    self.media_labels.clear()
    self.path_to_label.clear()
    self.num_columns = 0

    if enabled:
      self.preview_outer.config(fg=c["fg"])
      self.canvas.config(bg=c["canvas_bg"])
      self.preview_inner.config(bg=c["canvas_bg"])
      tk.Label(
          self.preview_inner,
          text="Pick items to preview",
          bg=c["canvas_bg"],
          fg=c["muted"],
          font=("Segoe UI", 9),
      ).pack(pady=30, padx=20)
    else:
      self.preview_outer.config(fg=c["muted"])
      self.canvas.config(bg=c["bg"])
      self.preview_inner.config(bg=c["bg"])
      tk.Label(
          self.preview_inner,
          text=(
              "Previews disabled (Selected filter contains no previewable"
              " media)"
          ),
          bg=c["bg"],
          fg=c["muted"],
          font=("Segoe UI", 9),
          wraplength=250,
      ).pack(pady=30, padx=20)

  def on_canvas_resize(self, event):
    self.canvas.itemconfig(self.canvas_window, width=event.width)
    preset = self.preset_var.get()
    if preset in ("All Files", "Images", "Audio", "Video", "Folders") or (
        preset == "Custom"
        and any(
            ext in IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
            for ext in self.get_valid_exts()
        )
    ):
      self.update_media_displays(event.width)

  def select_folder(self):
    folder_selected = filedialog.askdirectory()
    if folder_selected:
      self.folder_entry.delete(0, tk.END)
      self.folder_entry.insert(0, folder_selected)

  def start_pick_thread(self):
    self.btn_pick.config(state="disabled", text="Scanning...")
    self.progress.start(10)
    threading.Thread(target=self.pick_files, daemon=True).start()

  def pick_files(self):
    try:
      folder_path = self.folder_entry.get().strip()
      if not folder_path:
        self.root.after(
            0,
            lambda: messagebox.showwarning(
                "Warning", "Please select a folder first."
            ),
        )
        return

      path = Path(folder_path)
      if not path.exists() or not path.is_dir():
        self.root.after(
            0,
            lambda: messagebox.showerror(
                "Error", "The specified folder path is invalid."
            ),
        )
        return

      try:
        count = int(self.count_var.get())
      except ValueError:
        count = 1

      preset = self.preset_var.get()
      is_folders_mode = preset == "Folders"
      recursive = self.recursive_var.get()

      items = []
      if is_folders_mode:
        if recursive:
          dirs_to_scan = [path]
          while dirs_to_scan:
            current_dir = dirs_to_scan.pop()
            try:
              with os.scandir(current_dir) as entries:
                for entry in entries:
                  if entry.is_dir(follow_symlinks=False):
                    sub_path = Path(entry.path)
                    items.append(sub_path)
                    dirs_to_scan.append(sub_path)
            except PermissionError:
              continue
        else:
          try:
            with os.scandir(path) as entries:
              for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                  items.append(Path(entry.path))
          except PermissionError:
            pass
        chosen_items = items
      else:
        if recursive:
          dirs_to_scan = [path]
          while dirs_to_scan:
            current_dir = dirs_to_scan.pop()
            try:
              with os.scandir(current_dir) as entries:
                for entry in entries:
                  if entry.is_file(follow_symlinks=False):
                    items.append(Path(entry.path))
                  elif entry.is_dir(follow_symlinks=False):
                    dirs_to_scan.append(Path(entry.path))
            except PermissionError:
              continue
        else:
          try:
            with os.scandir(path) as entries:
              for entry in entries:
                if entry.is_file(follow_symlinks=False):
                  items.append(Path(entry.path))
          except PermissionError:
            pass

        valid_exts = self.get_valid_exts()
        if valid_exts:
          items = [p for p in items if p.suffix.lower() in valid_exts]

        chosen_items = items

      if not chosen_items:
        self.root.after(
            0,
            lambda: messagebox.showinfo(
                "No Items", "No matching items found in this folder."
            ),
        )
        return

      k = min(count, len(chosen_items))
      chosen_files = random.sample(chosen_items, k)

      allow_media = preset in ("All Files", "Images", "Audio", "Video", "Folders") or (
          preset == "Custom"
          and any(
              ext in IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
              for ext in valid_exts
          )
      )

      media_data_to_load = []
      if allow_media:
        for f in chosen_files:
          if is_folders_mode:
            media_data_to_load.append((f, "folder", None))
          else:
            ext = f.suffix.lower()
            if ext in IMAGE_EXTENSIONS:
              if HAS_PILLOW:
                try:
                  img = Image.open(f)
                  img.thumbnail(
                      (self.thumbnail_size, self.thumbnail_size),
                      Image.Resampling.LANCZOS,
                  )
                  media_data_to_load.append((f, "image", img))
                except Exception:
                  media_data_to_load.append((f, "error", "Error loading image"))
              else:
                media_data_to_load.append(
                    (f, "error", "Install Pillow to preview")
                )
            elif ext in AUDIO_EXTENSIONS:
              media_data_to_load.append((f, "audio", None))
            elif ext in VIDEO_EXTENSIONS:
              media_data_to_load.append((f, "video", None))
            else:
              media_data_to_load.append((f, "other", None))

      self.last_chosen_files = chosen_files
      self.last_media_data = media_data_to_load

      self.roll_history.append((chosen_files, media_data_to_load))
      if len(self.roll_history) > self.max_history:
        self.roll_history = self.roll_history[-self.max_history:]

      self.root.after(
          0,
          lambda: self.update_ui_with_results(
              chosen_files, media_data_to_load, allow_media
          ),
      )

    finally:
      self.root.after(0, lambda: self.progress.stop())
      self.root.after(
          0,
          lambda: self.btn_pick.config(state="normal", text="Pick Random Files"),
      )

  def update_ui_with_results(
      self, chosen_files, media_data_to_load, allow_media
  ):
    c = self.colors
    self.stop_audio()
    self.file_listbox.delete(0, tk.END)
    for f in chosen_files:
      self.file_listbox.insert(tk.END, str(f))

    for widget in self.preview_inner.winfo_children():
      widget.destroy()
    self.raw_images.clear()
    self.current_images.clear()
    self.media_labels.clear()
    self.path_to_label.clear()
    self.current_highlighted_label = None
    self.num_columns = 0

    if not allow_media:
      tk.Label(
          self.preview_inner,
          text=(
              "Previews disabled (Selected filter contains no previewable"
              " media)"
          ),
          bg=c["canvas_bg"],
          fg=c["muted"],
          font=("Segoe UI", 9),
          wraplength=250,
      ).pack(pady=30, padx=20)
      return

    if media_data_to_load:
      for file_path, mtype, data in media_data_to_load:
        container = tk.Frame(
            self.preview_inner,
            bg=c["card_bg"],
            bd=1,
            relief="solid",
            highlightbackground=c["border"],
        )
        self.media_labels.append(container)
        self.path_to_label[file_path.resolve()] = container

        def bind_events(w):
          w.bind(
              "<Button-1>", lambda e, p=file_path: self.select_file_by_path(p)
          )
          w.bind(
              "<Double-Button-1>",
              lambda e, p=file_path: self.on_preview_double_click(p),
          )

        bind_events(container)

        if mtype == "folder":
          lbl_title = tk.Label(
              container,
              text=f"📁 {file_path.name}",
              bg=c["card_bg"],
              fg=c["fg"],
              font=("Segoe UI", 9, "bold"),
              wraplength=self.thumbnail_size,
          )
          lbl_title.pack(padx=8, pady=(14, 6))
          bind_events(lbl_title)

          btn_open_folder = tk.Button(
              container,
              text="Open Folder",
              bg="#dd6b20",
              fg="white",
              font=("Segoe UI", 8, "bold"),
              relief="flat",
              padx=8,
              pady=3,
              cursor="hand2",
              command=lambda p=file_path: self.open_file_in_explorer_by_path(p),
          )
          btn_open_folder.pack(padx=8, pady=(0, 10))
          bind_events(btn_open_folder)

        elif mtype == "image":
          try:
            photo = ImageTk.PhotoImage(data)
            self.raw_images.append(data)
            self.current_images.append(photo)

            lbl_img = tk.Label(container, image=photo, bg=c["card_bg"])
            lbl_img.pack(padx=6, pady=(6, 0))
            bind_events(lbl_img)
          except Exception:
            pass

          lbl_name = tk.Label(
              container,
              text=file_path.name,
              bg=c["card_bg"],
              fg=c["fg"],
              font=("Segoe UI", 9, "bold"),
              wraplength=self.thumbnail_size,
          )
          lbl_name.pack(padx=6, pady=6)
          bind_events(lbl_name)

        elif mtype == "error":
          lbl_err = tk.Label(
              container,
              text=f"⚠️ {data}",
              bg=c["card_bg"],
              fg="#e53e3e",
              font=("Segoe UI", 8, "bold"),
              wraplength=self.thumbnail_size,
          )
          lbl_err.pack(padx=6, pady=(10, 2))
          bind_events(lbl_err)

          lbl_name = tk.Label(
              container,
              text=file_path.name,
              bg=c["card_bg"],
              fg=c["fg"],
              font=("Segoe UI", 9, "bold"),
              wraplength=self.thumbnail_size,
          )
          lbl_name.pack(padx=6, pady=(0, 10))
          bind_events(lbl_name)

        elif mtype == "audio":
          lbl_title = tk.Label(
              container,
              text=f"🎵 {file_path.name}",
              bg=c["card_bg"],
              fg=c["fg"],
              font=("Segoe UI", 9, "bold"),
              wraplength=self.thumbnail_size,
          )
          lbl_title.pack(padx=6, pady=6)
          bind_events(lbl_title)

          btn_frame = tk.Frame(container, bg=c["card_bg"])
          btn_frame.pack(padx=6, pady=(0, 6))

          btn_play = tk.Button(
              btn_frame,
              text="▶ Play",
              bg="#38a169",
              fg="white",
              font=("Segoe UI", 8, "bold"),
              relief="flat",
              padx=6,
              pady=2,
              cursor="hand2",
              command=lambda p=file_path: self.play_audio(p),
          )
          btn_play.pack(side="left", padx=2)

          btn_stop = tk.Button(
              btn_frame,
              text="⏹ Stop",
              bg="#e53e3e",
              fg="white",
              font=("Segoe UI", 8, "bold"),
              relief="flat",
              padx=6,
              pady=2,
              cursor="hand2",
              command=self.stop_audio,
          )
          btn_stop.pack(side="left", padx=2)

        elif mtype == "video":
          lbl_title = tk.Label(
              container,
              text=f"🎬 {file_path.name}",
              bg=c["card_bg"],
              fg=c["fg"],
              font=("Segoe UI", 9, "bold"),
              wraplength=self.thumbnail_size,
          )
          lbl_title.pack(padx=6, pady=(10, 6))
          bind_events(lbl_title)

          btn_play_vid = tk.Button(
              container,
              text="▶ Play Video",
              bg="#3182ce",
              fg="white",
              font=("Segoe UI", 8, "bold"),
              relief="flat",
              padx=10,
              pady=3,
              cursor="hand2",
              command=lambda p=file_path: self.open_file(p),
          )
          btn_play_vid.pack(padx=6, pady=(0, 10))
          bind_events(btn_play_vid)

        elif mtype == "other":
          lbl_title = tk.Label(
              container,
              text=f"📄 {file_path.name}",
              bg=c["card_bg"],
              fg=c["fg"],
              font=("Segoe UI", 9, "bold"),
              wraplength=self.thumbnail_size,
          )
          lbl_title.pack(padx=6, pady=(16, 16))
          bind_events(lbl_title)

      self.root.update_idletasks()
      current_width = self.canvas.winfo_width()
      if current_width > 10:
        self.update_media_displays(current_width)
    else:
      tk.Label(
          self.preview_inner,
          text="No previewable media in selection",
          bg=c["canvas_bg"],
          fg=c["muted"],
          font=("Segoe UI", 9),
      ).pack(pady=30, padx=20)

  def update_media_displays(self, canvas_width):
    if not self.media_labels:
      return

    available_width = canvas_width - 25
    column_width = self.thumbnail_size + (self.cell_padding * 4)
    new_num_columns = max(1, available_width // column_width)

    if new_num_columns != self.num_columns:
      self.num_columns = new_num_columns

      for container in self.media_labels:
        container.grid_forget()

      for c in range(self.num_columns):
        self.preview_inner.columnconfigure(c, weight=1)

      for i, container in enumerate(self.media_labels):
        row = i // self.num_columns
        col = i % self.num_columns
        container.grid(
            row=row,
            column=col,
            padx=self.cell_padding,
            pady=self.cell_padding,
            sticky="n",
        )

  def copy_picked_items(self):
    if self.file_listbox.size() == 0:
      messagebox.showwarning(
          "Warning", "No items have been picked yet to copy."
      )
      return

    dest_dir = filedialog.askdirectory(
        title="Select Destination Folder for Copying"
    )
    if not dest_dir:
      return

    dest_path = Path(dest_dir)
    success_count = 0
    error_count = 0

    for idx in range(self.file_listbox.size()):
      item_str = self.file_listbox.get(idx)
      item_path = Path(item_str)
      if not item_path.exists():
        error_count += 1
        continue

      try:
        target_dest = dest_path / item_path.name
        if item_path.is_dir():
          if target_dest.exists():
            shutil.copytree(item_path, target_dest, dirs_exist_ok=True)
          else:
            shutil.copytree(item_path, target_dest)
        else:
          shutil.copy2(item_path, target_dest)
        success_count += 1
      except Exception:
        error_count += 1

    msg = f"Successfully copied {success_count} item(s) to:\n{dest_path}"
    if error_count > 0:
      msg += f"\n(Failed to copy {error_count} item(s))"
    messagebox.showinfo("Copy Complete", msg)

  def open_slideshow_window(self):
    if hasattr(self, "slide_win") and self.slide_win.winfo_exists():
      self.slide_win.lift()
      return

    c = self.colors
    self.slide_win = tk.Toplevel(self.root)
    self.slide_win.title("Slideshow / Auto-Roll Mode")
    self.slide_win.geometry("400x220")
    self.slide_win.minsize(360, 200)
    self.slide_win.configure(bg=c["bg"])

    tk.Label(
        self.slide_win,
        text="Auto-Roll Slideshow",
        font=("Segoe UI", 12, "bold"),
        bg=c["bg"],
        fg=c["fg"],
        pady=10,
    ).pack()

    frame_ctrl = tk.Frame(self.slide_win, bg=c["bg"], padx=14, pady=5)
    frame_ctrl.pack(fill="x")

    tk.Label(
        frame_ctrl,
        text="Interval (seconds):",
        bg=c["bg"],
        fg=c["fg"],
        font=("Segoe UI", 9),
    ).pack(side="left")
    interval_spin = tk.Spinbox(
        frame_ctrl,
        from_=1,
        to=300,
        width=5,
        textvariable=self.slideshow_interval_var,
        bg=c["input_bg"],
        fg=c["input_fg"],
        font=("Segoe UI", 9),
        relief="solid",
        bd=1,
    )
    interval_spin.pack(side="left", padx=8)

    self.slideshow_status_lbl = tk.Label(
        self.slide_win,
        text="",
        fg=c["muted"],
        bg=c["bg"],
        font=("Segoe UI", 9),
        pady=10,
    )
    self.slideshow_status_lbl.pack()

    self.slideshow_btn_toggle = tk.Button(
        self.slide_win,
        text="",
        font=("Segoe UI", 10, "bold"),
        width=16,
        relief="flat",
        pady=5,
        cursor="hand2",
        command=self.toggle_slideshow,
    )
    self.slideshow_btn_toggle.pack(pady=8)

    self.update_slideshow_ui()

    def on_slide_close():
      self.slide_win.destroy()

    self.slide_win.protocol("WM_DELETE_WINDOW", on_slide_close)

  def toggle_slideshow(self):
    if self.slideshow_running:
      self.stop_slideshow()
    else:
      self.start_slideshow()

  def start_slideshow(self):
    folder_path = self.folder_entry.get().strip()
    if not folder_path:
      messagebox.showwarning(
          "Warning", "Please select a folder first before starting slideshow."
      )
      return
    self.slideshow_running = True
    self.update_slideshow_ui()
    self.run_slideshow_tick()

  def stop_slideshow(self):
    self.slideshow_running = False
    if self.slideshow_job_id is not None:
      try:
        self.root.after_cancel(self.slideshow_job_id)
      except Exception:
        pass
      self.slideshow_job_id = None
    self.update_slideshow_ui()

  def run_slideshow_tick(self):
    if not self.slideshow_running:
      return

    folder_path = self.folder_entry.get().strip()
    if not folder_path:
      self.stop_slideshow()
      return

    self.start_pick_thread()

    try:
      interval_secs = max(1, int(self.slideshow_interval_var.get()))
    except ValueError:
      interval_secs = 5

    if self.slideshow_running:
      self.slideshow_job_id = self.root.after(
          interval_secs * 1000, self.run_slideshow_tick
      )

  def update_slideshow_ui(self):
    if hasattr(self, "slide_win") and self.slide_win.winfo_exists():
      if hasattr(self, "slideshow_status_lbl") and hasattr(
          self, "slideshow_btn_toggle"
      ):
        if self.slideshow_running:
          self.slideshow_status_lbl.config(
              text="Status: Running...", fg="#38a169"
          )
          self.slideshow_btn_toggle.config(
              text="Stop Slideshow", bg="#e53e3e", fg="white"
          )
        else:
          self.slideshow_status_lbl.config(
              text="Status: Stopped", fg=self.colors["muted"]
          )
          self.slideshow_btn_toggle.config(
              text="Start Slideshow", bg="#38a169", fg="white"
          )

  def open_history_window(self):
    c = self.colors
    hist_win = tk.Toplevel(self.root)
    hist_win.title("Previous Roll History")
    hist_win.geometry("820x680")
    hist_win.minsize(580, 420)
    hist_win.configure(bg=c["bg"])

    top_ctrl = tk.Frame(hist_win, bg=c["bg"], padx=12, pady=10)
    top_ctrl.pack(fill="x")

    tk.Label(
        top_ctrl,
        text="Max Rolls to Keep:",
        bg=c["bg"],
        fg=c["fg"],
        font=("Segoe UI", 9, "bold"),
    ).pack(side="left")
    max_hist_var = tk.IntVar(value=self.max_history)

    def on_max_change(*args):
      try:
        val = int(max_hist_var.get())
        if val < 1:
          val = 1
        self.max_history = val
        if len(self.roll_history) > self.max_history:
          self.roll_history = self.roll_history[-self.max_history:]
        refresh_history_content()
      except ValueError:
        pass

    max_hist_spin = tk.Spinbox(
        top_ctrl,
        from_=1,
        to=50,
        width=5,
        textvariable=max_hist_var,
        bg=c["input_bg"],
        fg=c["input_fg"],
        font=("Segoe UI", 9),
        relief="solid",
        bd=1,
        command=lambda: on_max_change(),
    )
    max_hist_spin.pack(side="left", padx=8)
    max_hist_var.trace_add("write", lambda *args: on_max_change())

    def clear_history():
      self.roll_history.clear()
      refresh_history_content()

    btn_clear = tk.Button(
        top_ctrl,
        text="Clear History",
        bg="#e53e3e",
        fg="white",
        font=("Segoe UI", 8, "bold"),
        relief="flat",
        padx=10,
        pady=3,
        cursor="hand2",
        command=clear_history,
    )
    btn_clear.pack(side="right")

    container_frame = tk.Frame(hist_win, bg=c["bg"])
    container_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    canvas = tk.Canvas(container_frame, bg=c["bg"], highlightthickness=0)
    scrollbar = ttk.Scrollbar(
        container_frame, orient="vertical", command=canvas.yview
    )
    scroll_frame = tk.Frame(canvas, bg=c["bg"])

    canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    scroll_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.bind(
        "<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width)
    )
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def refresh_history_content():
      for widget in scroll_frame.winfo_children():
        widget.destroy()

      if not self.roll_history:
        tk.Label(
            scroll_frame,
            text="No roll history yet. Pick some random items first!",
            font=("Segoe UI", 10),
            fg=c["muted"],
            bg=c["bg"],
        ).pack(expand=True, pady=60)
        return

      for idx, (chosen_files, media_data) in enumerate(
          reversed(list(self.roll_history))
      ):
        roll_num = len(self.roll_history) - idx
        roll_frame = tk.LabelFrame(
            scroll_frame,
            text=f" Roll #{roll_num} ({len(chosen_files)} items) ",
            font=("Segoe UI", 9, "bold"),
            fg=c["fg"],
            padx=10,
            pady=10,
            bg=c["card_bg"],
            relief="solid",
            bd=1,
        )
        roll_frame.pack(fill="x", padx=4, pady=6)

        items_container = tk.Frame(roll_frame, bg=c["card_bg"])
        items_container.pack(fill="x", expand=True)

        for file_path, mtype, data in media_data:
          card = tk.Frame(
              items_container,
              bg=c["bg"],
              bd=1,
              relief="solid",
              highlightbackground=c["border"],
              padx=6,
              pady=6,
          )
          card.pack(side="left", padx=5, pady=5, anchor="n")

          if mtype == "image" and data is not None:
            try:
              hist_img = data.copy()
              hist_img.thumbnail((110, 110), Image.Resampling.LANCZOS)
              photo = ImageTk.PhotoImage(hist_img)
              if not hasattr(hist_win, "images"):
                hist_win.images = []
              hist_win.images.append(photo)

              lbl_img = tk.Label(card, image=photo, bg=c["bg"])
              lbl_img.pack(pady=(0, 2))
            except Exception:
              pass

          icon_map = {
              "folder": "📁",
              "image": "🖼️",
              "audio": "🎵",
              "video": "🎬",
              "other": "📄",
              "error": "⚠️",
          }
          icon = icon_map.get(mtype, "📄")

          if mtype in ("other", "error"):
            info_box = tk.Frame(
                card, bg=c["card_bg"], bd=1, relief="solid", padx=6, pady=6
            )
            info_box.pack(fill="x", padx=2, pady=4)

            lbl_box_title = tk.Label(
                info_box,
                text=f"{icon} File Info",
                bg=c["card_bg"],
                fg=c["fg"],
                font=("Segoe UI", 8, "bold"),
            )
            lbl_box_title.pack(anchor="w")

            ext_str = file_path.suffix.lower() if file_path.suffix else "None"
            if mtype == "error":
              info_text = f"Error: {data}"
            else:
              info_text = f"Name: {file_path.name}\nExt: {ext_str}"

            lbl_details = tk.Label(
                info_box,
                text=info_text,
                bg=c["card_bg"],
                fg=c["muted"],
                font=("Segoe UI", 8),
                justify="left",
                anchor="w",
                wraplength=120,
            )
            lbl_details.pack(anchor="w", pady=(2, 0))
          else:
            display_text = f"{icon} {file_path.name}"
            lbl_name = tk.Label(
                card,
                text=display_text,
                bg=c["bg"],
                fg=c["fg"],
                font=("Segoe UI", 8),
                wraplength=120,
                justify="center",
            )
            lbl_name.pack(pady=2)

          btn_open = tk.Button(
              card,
              text="Open",
              bg="#3182ce",
              fg="white",
              font=("Segoe UI", 7, "bold"),
              relief="flat",
              padx=6,
              pady=2,
              cursor="hand2",
              command=lambda p=file_path: self.open_file_in_explorer_by_path(p),
          )
          btn_open.pack(pady=(4, 0))

    refresh_history_content()

  def select_file_by_path(self, file_path):
    for idx in range(self.file_listbox.size()):
      try:
        item_path = Path(self.file_listbox.get(idx)).resolve()
        if item_path == file_path.resolve():
          self.file_listbox.selection_clear(0, tk.END)
          self.file_listbox.selection_set(idx)
          self.file_listbox.see(idx)
          self.on_file_select(None)
          break
      except Exception:
        pass

  def on_preview_double_click(self, file_path):
    self.select_file_by_path(file_path)
    self.open_file_in_explorer_by_path(file_path)

  def play_audio(self, file_path):
    if not HAS_PYGAME:
      messagebox.showerror(
          "Error", "Pygame is not installed. Run 'pip install pygame' for audio"
          " playback."
      )
      return
    try:
      pygame.mixer.music.load(str(file_path))
      pygame.mixer.music.play()
    except Exception as e:
      messagebox.showerror("Error", f"Could not play audio: {e}")

  def stop_audio(self):
    if HAS_PYGAME:
      try:
        pygame.mixer.music.stop()
      except Exception:
        pass

  def open_file(self, file_path):
    try:
      if sys.platform == "win32":
        os.startfile(str(file_path))
      elif sys.platform == "darwin":
        subprocess.run(["open", str(file_path)])
      else:
        subprocess.run(["xdg-open", str(file_path)])
    except Exception as e:
      messagebox.showerror("Error", f"Could not open file: {e}")

  def on_file_select(self, event):
    c = self.colors
    preset = self.preset_var.get()
    valid_exts = self.get_valid_exts()
    allow_media = preset in ("All Files", "Images", "Audio", "Video", "Folders") or (
        preset == "Custom"
        and any(
            ext in IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
            for ext in valid_exts
        )
    )
    if not allow_media:
      return

    selection = self.file_listbox.curselection()
    if not selection:
      return

    try:
      selected_path = Path(self.file_listbox.get(selection[0])).resolve()
    except Exception:
      return

    if self.current_highlighted_label:
      try:
        self.current_highlighted_label.config(bg=c["card_bg"])
        for child in self.current_highlighted_label.winfo_children():
          if isinstance(child, tk.Label):
            child.config(bg=c["card_bg"])
      except Exception:
        pass
      self.current_highlighted_label = None

    if selected_path in self.path_to_label:
      container = self.path_to_label[selected_path]
      container.config(bg=c["highlight_bg"])
      for child in container.winfo_children():
        if isinstance(child, tk.Label):
          child.config(bg=c["highlight_bg"])
      self.current_highlighted_label = container

      self.preview_inner.update_idletasks()
      inner_height = self.preview_inner.winfo_height()
      if inner_height > 0:
        y_pos = container.winfo_y()
        fraction = max(0.0, min(1.0, y_pos / inner_height))
        self.canvas.yview_moveto(fraction)

  def open_file_in_explorer_by_path(self, file_path):
    try:
      resolved_path = file_path.resolve()
      if not resolved_path.exists():
        messagebox.showerror("Error", "Item no longer exists.")
        return

      if sys.platform == "win32":
        norm_path = str(resolved_path)
        subprocess.run(f'explorer /select,"{norm_path}"', shell=True)
      elif sys.platform == "darwin":
        subprocess.run(["open", "-R", str(resolved_path)])
      else:
        subprocess.run(["xdg-open", str(resolved_path.parent)])
    except Exception as e:
      messagebox.showerror("Error", f"Could not open explorer: {e}")

  def open_selected_in_explorer(self):
    try:
      selected_idx = self.file_listbox.curselection()
      if not selected_idx:
        messagebox.showwarning("Warning", "Please select an item from the list.")
        return
      file_path = Path(self.file_listbox.get(selected_idx[0]))
      self.open_file_in_explorer_by_path(file_path)
    except Exception as e:
      messagebox.showerror("Error", f"Could not open explorer: {e}")

  def on_close(self):
    self.stop_audio()
    self.stop_slideshow()
    self.root.destroy()


if __name__ == "__main__":
  root = tk.Tk()
  app = RandomFilePickerApp(root)
  root.mainloop()