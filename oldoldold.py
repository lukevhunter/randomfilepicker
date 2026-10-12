import os
from pathlib import Path
import random
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

try:
  from PIL import Image, ImageTk

  HAS_PILLOW = True
except ImportError:
  HAS_PILLOW = False

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


class RandomFilePickerApp:

  def __init__(self, root):
    self.root = root
    self.root.title("Random File & Image Picker")
    self.root.geometry("850x650")
    self.root.minsize(700, 500)

    self.thumbnail_size = 200
    self.cell_padding = 5
    self.num_columns = 0

    self.raw_images = []
    self.current_images = []
    self.image_labels = []
    self.path_to_label = {}
    self.current_highlighted_label = None

    self.create_widgets()

  def create_widgets(self):
    # Top: Folder selection
    frame_folder = tk.Frame(self.root, padx=10, pady=10)
    frame_folder.pack(fill="x")

    tk.Label(frame_folder, text="Folder:").pack(side="left")
    self.folder_entry = tk.Entry(frame_folder)
    self.folder_entry.pack(side="left", padx=5, expand=True, fill="x")
    tk.Button(
        frame_folder, text="Browse...", command=self.select_folder
    ).pack(side="right")

    # Options: Recursive, Count, & Extension Filter
    frame_options = tk.Frame(self.root, padx=10, pady=5)
    frame_options.pack(fill="x")

    self.recursive_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        frame_options, text="Include Subfolders", variable=self.recursive_var
    ).pack(side="left")

    tk.Label(frame_options, text="   Count:").pack(side="left", padx=(10, 0))
    self.count_var = tk.IntVar(value=1)
    self.count_spin = tk.Spinbox(
        frame_options,
        from_=1,
        to=1000,
        width=5,
        textvariable=self.count_var,
        wrap=True,
    )
    self.count_spin.pack(side="left", padx=5)

    # Extension Filter Options
    self.filter_ext_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        frame_options,
        text="Custom Ext:",
        variable=self.filter_ext_var,
        command=self.toggle_extension_filter,
    ).pack(side="left", padx=(15, 0))

    self.ext_entry = tk.Entry(frame_options, width=12, state="disabled")
    self.ext_entry.pack(side="left", padx=5)
    self.ext_entry.insert(0, ".txt, .pdf")

    # Action Buttons
    frame_action = tk.Frame(self.root, padx=10, pady=5)
    frame_action.pack(fill="x")

    btn_pick = tk.Button(
        frame_action,
        text="Pick Random Files",
        command=self.pick_files,
        bg="#4CAF50",
        fg="white",
        font=("Arial", 10, "bold"),
        pady=5,
    )
    btn_pick.pack(side="left", expand=True, fill="x", padx=(0, 5))

    btn_explorer = tk.Button(
        frame_action,
        text="Show Selected in Explorer",
        command=self.open_selected_in_explorer,
        pady=5,
    )
    btn_explorer.pack(side="right", expand=True, fill="x", padx=(5, 0))

    # Main Content Layout (List on left, Previews on right)
    content_frame = tk.Frame(self.root, padx=10, pady=10)
    content_frame.pack(fill="both", expand=True)

    # Left: File list
    list_frame = tk.LabelFrame(
        content_frame, text="Selected Files", padx=5, pady=5
    )
    list_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

    self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
    self.file_listbox.pack(side="left", fill="both", expand=True)
    self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)

    list_scroll = tk.Scrollbar(
        list_frame, orient="vertical", command=self.file_listbox.yview
    )
    list_scroll.pack(side="right", fill="y")
    self.file_listbox.config(yscrollcommand=list_scroll.set)

    # Right: Image Previews (Scrollable, dynamically resizing grid)
    self.preview_outer = tk.LabelFrame(
        content_frame, text="Image Previews", padx=5, pady=5
    )
    self.preview_outer.pack(side="right", fill="both", expand=True, padx=(5, 0))

    self.canvas = tk.Canvas(
        self.preview_outer, bg="#f0f0f0", highlightthickness=0
    )
    self.preview_scroll = tk.Scrollbar(
        self.preview_outer, orient="vertical", command=self.canvas.yview
    )
    self.preview_inner = tk.Frame(self.canvas, bg="#f0f0f0")

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

    if not HAS_PILLOW:
      warning_lbl = tk.Label(
          self.root,
          text=(
              "Note: Run 'pip install Pillow' to enable image previews inside"
              " the app."
          ),
          fg="red",
          font=("Arial", 9),
      )
      warning_lbl.pack(pady=5)

  def toggle_extension_filter(self):
    if self.filter_ext_var.get():
      self.ext_entry.config(state="normal")
      self.set_image_section_state(enabled=False)
    else:
      self.ext_entry.config(state="disabled")
      self.set_image_section_state(enabled=True)

  def set_image_section_state(self, enabled):
    # Clear current previews when toggled
    for widget in self.preview_inner.winfo_children():
      widget.destroy()
    self.raw_images.clear()
    self.current_images.clear()
    self.image_labels.clear()
    self.path_to_label.clear()

    if enabled:
      self.preview_outer.config(fg="black")
      self.canvas.config(bg="#f0f0f0")
      self.preview_inner.config(bg="#f0f0f0")
      tk.Label(
          self.preview_inner,
          text="Pick files to preview images",
          bg="#f0f0f0",
          fg="gray",
      ).pack(pady=20, padx=20)
    else:
      self.preview_outer.config(fg="gray")
      self.canvas.config(bg="#e0e0e0")
      self.preview_inner.config(bg="#e0e0e0")
      tk.Label(
          self.preview_inner,
          text="Image previews disabled (Custom extension filter active)",
          bg="#e0e0e0",
          fg="#888888",
          wraplength=250,
      ).pack(pady=20, padx=20)

  def on_canvas_resize(self, event):
    self.canvas.itemconfig(self.canvas_window, width=event.width)
    if not self.filter_ext_var.get():
      self.update_image_displays(event.width)

  def select_folder(self):
    folder_selected = filedialog.askdirectory()
    if folder_selected:
      self.folder_entry.delete(0, tk.END)
      self.folder_entry.insert(0, folder_selected)

  def pick_files(self):
    folder_path = self.folder_entry.get().strip()
    if not folder_path:
      messagebox.showwarning("Warning", "Please select a folder first.")
      return

    path = Path(folder_path)
    if not path.exists() or not path.is_dir():
      messagebox.showerror("Error", "The specified folder path is invalid.")
      return

    try:
      count = int(self.count_var.get())
    except ValueError:
      count = 1

    if self.recursive_var.get():
      files = [p for p in path.rglob("*") if p.is_file()]
    else:
      files = [p for p in path.iterdir() if p.is_file()]

    # Apply custom extension filter if enabled
    if self.filter_ext_var.get():
      ext_text = self.ext_entry.get().strip()
      if ext_text:
        valid_exts = {
            e.strip().lower() if e.strip().startswith(".") else f".{e.strip().lower()}"
            for e in ext_text.replace(",", " ").split()
            if e.strip()
        }
        files = [p for p in files if p.suffix.lower() in valid_exts]

    if not files:
      messagebox.showinfo("No Files", "No matching files found in this folder.")
      return

    k = min(count, len(files))
    chosen_files = random.sample(files, k)

    # Populate file list
    self.file_listbox.delete(0, tk.END)
    for f in chosen_files:
      self.file_listbox.insert(tk.END, str(f))

    # Clear previous images
    for widget in self.preview_inner.winfo_children():
      widget.destroy()
    self.raw_images.clear()
    self.current_images.clear()
    self.image_labels.clear()
    self.path_to_label.clear()
    self.current_highlighted_label = None

    if self.filter_ext_var.get():
      # Image section is disabled when custom extension filter is active
      tk.Label(
          self.preview_inner,
          text="Image previews disabled (Custom extension filter active)",
          bg="#e0e0e0",
          fg="#888888",
          wraplength=250,
      ).pack(pady=20, padx=20)
      return

    image_files = [
        f for f in chosen_files if f.suffix.lower() in IMAGE_EXTENSIONS
    ]

    if image_files and HAS_PILLOW:
      for img_path in image_files:
        try:
          img = Image.open(img_path)
          img.thumbnail(
              (self.thumbnail_size, self.thumbnail_size),
              Image.Resampling.LANCZOS,
          )
          photo = ImageTk.PhotoImage(img)

          self.raw_images.append(img)
          self.current_images.append(photo)

          lbl = tk.Label(
              self.preview_inner,
              image=photo,
              text=img_path.name,
              compound="top",
              bg="#f0f0f0",
              wraplength=self.thumbnail_size,
          )
          self.image_labels.append(lbl)
          self.path_to_label[img_path.resolve()] = lbl
        except Exception:
          pass

      self.root.update_idletasks()
      current_width = self.canvas.winfo_width()
      if current_width > 10:
        self.update_image_displays(current_width)
    else:
      msg = (
          "No images in selection"
          if not image_files
          else "Install Pillow to preview images"
      )
      tk.Label(
          self.preview_inner, text=msg, bg="#f0f0f0", fg="gray"
      ).pack(pady=20, padx=20)

  def update_image_displays(self, canvas_width):
    if not self.image_labels:
      return

    available_width = canvas_width - 25
    column_width = self.thumbnail_size + (self.cell_padding * 2)
    new_num_columns = max(1, available_width // column_width)

    if new_num_columns != self.num_columns:
      self.num_columns = new_num_columns

      for lbl in self.image_labels:
        lbl.grid_forget()

      for c in range(self.num_columns):
        self.preview_inner.columnconfigure(c, weight=1)

      for i, lbl in enumerate(self.image_labels):
        row = i // self.num_columns
        col = i % self.num_columns
        lbl.grid(
            row=row,
            column=col,
            padx=self.cell_padding,
            pady=self.cell_padding,
            sticky="n",
        )

  def on_file_select(self, event):
    if self.filter_ext_var.get():
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
        self.current_highlighted_label.config(bg="#f0f0f0")
      except Exception:
        pass
      self.current_highlighted_label = None

    if selected_path in self.path_to_label:
      lbl = self.path_to_label[selected_path]
      lbl.config(bg="#cce8ff")
      self.current_highlighted_label = lbl

      self.preview_inner.update_idletasks()
      inner_height = self.preview_inner.winfo_height()
      if inner_height > 0:
        y_pos = lbl.winfo_y()
        fraction = max(0.0, min(1.0, y_pos / inner_height))
        self.canvas.yview_moveto(fraction)

  def open_selected_in_explorer(self):
    try:
      selected_idx = self.file_listbox.curselection()
      if not selected_idx:
        messagebox.showwarning("Warning", "Please select a file from the list.")
        return
      file_path = Path(self.file_listbox.get(selected_idx[0])).resolve()
      if not file_path.exists():
        messagebox.showerror("Error", "File no longer exists.")
        return

      if sys.platform == "win32":
        norm_path = str(file_path)
        subprocess.run(f'explorer /select,"{norm_path}"', shell=True)
      elif sys.platform == "darwin":
        subprocess.run(["open", "-R", str(file_path)])
      else:
        subprocess.run(["xdg-open", str(file_path.parent)])
    except Exception as e:
      messagebox.showerror("Error", f"Could not open explorer: {e}")


if __name__ == "__main__":
  root = tk.Tk()
  app = RandomFilePickerApp(root)
  root.mainloop()