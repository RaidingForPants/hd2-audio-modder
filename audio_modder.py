import os
import subprocess
import struct
import tkinter
import shutil
import pathlib
import zipfile
import xml.etree.ElementTree as etree
import urllib.request
import json

from functools import partial
from functools import cmp_to_key
from math import ceil
from tkinterdnd2 import *
from tkinter import *
from tkinter import ttk
from tkinter import filedialog
from tkinter.messagebox import askokcancel
from tkinter.messagebox import showwarning
from tkinter.messagebox import showerror
from tkinter.messagebox import askyesnocancel
from tkinter.filedialog import askopenfilename
from typing import Any, Literal, Callable
from typing_extensions import Self
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

import config as cfg
import db
import log
import fileutil
from util import *
from wwise_hierarchy import *
from core import *
from xlocale import *
from env import *
from const import *

from log import logger

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720


import sys

from PySide6.QtCore import QSize, Qt, Signal, QMargins, QSortFilterProxyModel, QItemSelection, QItemSelectionModel
from PySide6.QtWidgets import QApplication, QMainWindow, QTreeView, QFileSystemModel, QMenu, QHBoxLayout, QVBoxLayout, QAbstractItemView, QSizePolicy, QWidget, QSplitter, QListView, QPushButton, QSpacerItem, QFileDialog, QLabel, QTabWidget, QStyledItemDelegate
from PySide6.QtGui import QStandardItem, QStandardItemModel, QPalette, QColor, QAction

WORKSPACE_FOLDER = os.path.abspath("./workspace_folders")

    
class WorkspaceEventHandler(FileSystemEventHandler):

    # TO-DO: Change get_item_by_path to return all matches, not just the first

    def __init__(self, workspace):
        self.workspace = workspace

    def on_created(self, event: FileSystemEvent) -> None:
        src_ext = os.path.splitext(event.src_path)[1]
        if ".patch" in src_ext or src_ext in SUPPORTED_AUDIO_TYPES or event.is_directory:
            parent = pathlib.Path(event.src_path).parents[0]
            parent_items = self.get_items_by_path(parent)
            new_item_name = os.path.basename(event.src_path)
            for parent_item in parent_items:
                idx = 0
                for i in self.workspace.get_children(parent_item):
                    if event.is_directory and self.workspace.item(i, option="tags")[0] != "dir":
                        break
                    if not event.is_directory and self.workspace.item(i, option="tags")[0] == "dir":
                        idx+=1
                        continue
                    name = self.workspace.item(i)["text"]
                    if name.lower() < new_item_name.lower():
                        idx+=1
                    else:
                        break
                self.workspace.insert(parent_item, idx,
                                                   text=new_item_name,
                                                   values=[event.src_path],
                                                   tags="dir" if event.is_directory else "file")
        
    def on_deleted(self, event: FileSystemEvent) -> None:
        matching_items = self.get_items_by_path(event.src_path)
        for item in matching_items:
            self.workspace.delete(item)
        
    # moved/renamed WITHIN SAME DIRECTORY
    # changing directories will fire a created and deleted event
    def on_moved(self, event: FileSystemEvent) -> None:
        matching_items = self.get_items_by_path(event.src_path)
        new_item_name = os.path.basename(event.dest_path)
        new_parent_items = self.get_items_by_path(pathlib.Path(event.dest_path).parents[0])
        dest_ext = os.path.splitext(event.dest_path)[1]
        for item in matching_items:
            self.workspace.delete(item)
        if ".patch" in dest_ext or dest_ext in SUPPORTED_AUDIO_TYPES or event.is_directory: 
            idx = 0
            for i in self.workspace.get_children(new_parent_items[0]):
                if event.is_directory and self.workspace.item(i, option="tags")[0] != "dir":
                    break
                if not event.is_directory and self.workspace.item(i, option="tags")[0] == "dir":
                    idx+=1
                    continue
                name = self.workspace.item(i)["text"]
                if name.lower() < new_item_name.lower():
                    idx+=1
                else:
                    break
            for parent_item in new_parent_items:
                self.workspace.insert(parent_item, idx,
                                               text=new_item_name,
                                               values=[event.dest_path],
                                               tags="dir" if event.is_directory else "file")
        
    def get_items_by_path(self, path):
        items = []
        path = pathlib.Path(path)
        for item in self.workspace.get_children():
            child_path = pathlib.Path(self.workspace.item(item, option="values")[0])
            if child_path in path.parents:
                i = self.get_item_by_path_recursion(item, path)
                if i is not None:
                    items.append(i)
            elif str(child_path) == str(path):
                items.append(item)
        return items
                    
    def get_item_by_path_recursion(self, node, path):
        for item in self.workspace.get_children(node):
            child_path = pathlib.Path(self.workspace.item(item, option="values")[0])
            if child_path in path.parents:
                return self.get_item_by_path_recursion(item, path)
            elif str(child_path) == str(path):
                return item
        
class ProgressWindow:
    def __init__(self, title, max_progress):
        self.title = title
        self.max_progress = max_progress
        
    def show(self):
        self.root = Tk()
        self.root.title(self.title)
        self.root.geometry("410x45")
        self.root.attributes('-topmost', True)
        self.progress_bar = tkinter.ttk.Progressbar(self.root, orient=HORIZONTAL, length=400, mode="determinate", maximum=self.max_progress)
        self.progress_bar_text = Text(self.root)
        self.progress_bar.pack()
        self.progress_bar_text.pack()
        self.root.resizable(False, False)
        
    def step(self):
        self.progress_bar.step()
        self.root.update_idletasks()
        self.root.update()
        
    def set_text(self, s):
        self.progress_bar_text.delete('1.0', END)
        self.progress_bar_text.insert(INSERT, s)
        self.root.update_idletasks()
        self.root.update()
        
    def destroy(self):
        self.root.destroy()
        
class PopupWindow:
    def __init__(self, message, title="Missing Data!"):
        self.message = message
        self.title = title
        
    def show(self):
        self.root = Tk()
        self.root.title(self.title)
        #self.root.geometry("410x45")
        self.root.attributes('-topmost', True)
        self.text = ttk.Label(self.root,
                              text=self.message,
                              font=('Segoe UI', 12),
                              wraplength=500,
                              justify="left")
        self.button = ttk.Button(self.root, text="OK", command=self.destroy)
        self.text.pack(padx=20, pady=0)
        self.button.pack(pady=20)
        self.root.resizable(False, False)
        
    def destroy(self):
        self.root.destroy()
        
class StringEntryWindow:
    
    def __init__(self, parent, update_modified):
        self.frame = Frame(parent)
        self.update_modified = update_modified
        self.text_box = Text(self.frame, width=54, font=('Segoe UI', 12), wrap=WORD)
        self.string_entry = None
        self.fake_image = tkinter.PhotoImage(width=1, height=1)
        
        self.revert_button = ttk.Button(self.frame, text="\u21b6", command=self.revert)
        
        self.apply_button = ttk.Button(self.frame, text="Apply", command=self.apply_changes)
        self.text_box.pack()
        self.revert_button.pack(side="left")
        self.apply_button.pack(side="left")
        
    def set_string_entry(self, string_entry):
        self.string_entry = string_entry
        self.text_box.delete("1.0", END)
        self.text_box.insert(END, string_entry.get_text())
        
    def apply_changes(self):
        if self.string_entry is not None:
            self.string_entry.set_text(self.text_box.get("1.0", "end-1c"))
            self.update_modified()
    
    def revert(self):
        if self.string_entry is not None:
            self.string_entry.revert_modifications()
            self.text_box.delete("1.0", END)
            self.text_box.insert(END, self.string_entry.get_text())
            self.update_modified()
            
class MusicTrackWindow:
    
    def __init__(self, parent, update_modified):
        self.frame = Frame(parent)
        self.selected_track = 0
        self.update_modified = update_modified
        self.fake_image = tkinter.PhotoImage(width=1, height=1)
        self.title_label = ttk.Label(self.frame, font=('Segoe UI', 14), width=50, anchor="center")
        self.revert_button = ttk.Button(self.frame, text='\u21b6', image=self.fake_image, compound='c', width=2, command=self.revert)
        self.play_at_text_var = tkinter.StringVar(self.frame)
        self.duration_text_var = tkinter.StringVar(self.frame)
        self.start_offset_text_var = tkinter.StringVar(self.frame)
        self.end_offset_text_var = tkinter.StringVar(self.frame)
        self.source_selection_listbox = tkinter.Listbox(self.frame)
        self.source_selection_listbox.bind("<Double-Button-1>", self.set_track_info)
        
        self.play_at_label = ttk.Label(self.frame,
                                   text="Play At (ms)",
                                   font=('Segoe UI', 12),
                                   anchor="center")
        self.play_at_text = ttk.Entry(self.frame, textvariable=self.play_at_text_var, font=('Segoe UI', 12), width=54)
        
        
        self.duration_label = ttk.Label(self.frame,
                                    text="Duration (ms)",
                                    font=('Segoe UI', 12),
                                    anchor="center")
        self.duration_text = ttk.Entry(self.frame, textvariable=self.duration_text_var, font=('Segoe UI', 12), width=54)
        
        
        self.start_offset_label = ttk.Label(self.frame,
                                        text="Start Trim (ms)",
                                        font=('Segoe UI', 12),
                                        anchor="center")
        self.start_offset_text = ttk.Entry(self.frame, textvariable=self.start_offset_text_var, font=('Segoe UI', 12), width=54)
        
        
        self.end_offset_label = ttk.Label(self.frame,
                                      text="End Trim (ms)",
                                      font=('Segoe UI', 12),
                                      anchor="center")
        self.end_offset_text = ttk.Entry(self.frame, textvariable=self.end_offset_text_var, font=('Segoe UI', 12), width=54)

        self.apply_button = ttk.Button(self.frame, text="Apply", command=self.apply_changes)
        
        self.title_label.pack(pady=5)
        
    def set_track_info(self, event=None, selection=0):
        if not selection:
            selection = self.source_selection_listbox.get(self.source_selection_listbox.curselection()[0])
        for t in self.track.track_info:
            if t.source_id == selection or t.event_id == selection:
                track_info_struct = t
                break
                
        self.selected_track = track_info_struct
                
        self.duration_text.delete(0, 'end')
        self.duration_text.insert(END, str(track_info_struct.source_duration))
        self.start_offset_text.delete(0, 'end')
        self.start_offset_text.insert(END, str(track_info_struct.begin_trim_offset))
        self.end_offset_text.delete(0, 'end')
        self.end_offset_text.insert(END, str(track_info_struct.end_trim_offset))
        self.play_at_text.delete(0, 'end')
        self.play_at_text.insert(END, str(track_info_struct.play_at))
        
        self.play_at_label.pack()
        self.play_at_text.pack()
        self.duration_label.pack()
        self.duration_text.pack()
        self.start_offset_label.pack()
        self.start_offset_text.pack()
        self.end_offset_label.pack()
        self.end_offset_text.pack()
        
        self.revert_button.pack(side="left")
        
    def set_track(self, track):
        self.track = track
        self.source_selection_listbox.delete(0, 'end')
        for track_info_struct in self.track.track_info:
            if track_info_struct.source_id != 0:
                self.source_selection_listbox.insert(END, track_info_struct.source_id)
            else:
                self.source_selection_listbox.insert(END, track_info_struct.event_id)
        
        if len(track.track_info) > 0:
            self.source_selection_listbox.pack()
            self.set_track_info(selection=track.track_info[0].source_id if track.track_info[0].source_id != 0 else track.track_info[0].event_id)
    def revert(self):
        self.track.revert_modifications()
        self.set_track(self.track)
        
    def apply_changes(self):
        pass
        
        
class AudioSourceWindow:
    
    def __init__(self, parent, play, update_modified):
        self.frame = Frame(parent)
        self.update_modified = update_modified
        self.fake_image = tkinter.PhotoImage(width=1, height=1)
        self.play = play
        self.track_info = None
        self.audio = None
        self.title_label = ttk.Label(self.frame, font=('Segoe UI', 14), width=50, anchor="center")
        self.revert_button = ttk.Button(self.frame, text='\u21b6', image=self.fake_image, compound='c', width=2, command=self.revert)
        self.play_button = ttk.Button(self.frame, text= '\u23f5', image=self.fake_image, compound='c', width=2)
        self.play_original_button = ttk.Button(self.frame, text= '\u23f5', width=2)
        self.play_original_label = ttk.Label(self.frame, font=('Segoe UI', 12), text="Play Original Audio")
        self.play_at_text_var = tkinter.StringVar(self.frame)
        self.duration_text_var = tkinter.StringVar(self.frame)
        self.start_offset_text_var = tkinter.StringVar(self.frame)
        self.end_offset_text_var = tkinter.StringVar(self.frame)
        
        self.play_at_label = ttk.Label(self.frame,
                                   text="Play At (ms)",
                                   font=('Segoe UI', 12),
                                   anchor="center")
        self.play_at_text = ttk.Entry(self.frame, textvariable=self.play_at_text_var, font=('Segoe UI', 12), width=54)
        
        
        self.duration_label = ttk.Label(self.frame,
                                    text="Duration (ms)",
                                    font=('Segoe UI', 12),
                                    anchor="center")
        self.duration_text = ttk.Entry(self.frame, textvariable=self.duration_text_var, font=('Segoe UI', 12), width=54)
        
        
        self.start_offset_label = ttk.Label(self.frame,
                                        text="Start Trim (ms)",
                                        font=('Segoe UI', 12),
                                        anchor="center")
        self.start_offset_text = ttk.Entry(self.frame, textvariable=self.start_offset_text_var, font=('Segoe UI', 12), width=54)
        
        
        self.end_offset_label = ttk.Label(self.frame,
                                      text="End Trim (ms)",
                                      font=('Segoe UI', 12),
                                      anchor="center")
        self.end_offset_text = ttk.Entry(self.frame, textvariable=self.end_offset_text_var, font=('Segoe UI', 12), width=54)

        self.apply_button = ttk.Button(self.frame, text="Apply", command=self.apply_changes)
        
        self.title_label.pack(pady=5)
        
    def set_audio(self, audio):
        self.audio = audio
        self.title_label.configure(text=f"Info for {audio.get_id()}.wem")
        self.play_button.configure(text= '\u23f5')
        self.revert_button.pack_forget()
        self.play_button.pack_forget()
        self.apply_button.pack_forget()
        def reset_button_icon(button):
            button.configure(text= '\u23f5')
        def press_button(button, file_id, callback):
            if button['text'] == '\u23f9':
                button.configure(text= '\u23f5')
            else:
                button.configure(text= '\u23f9')
            self.play(file_id, callback)
        def play_original_audio(button, file_id, callback):
            if button['text'] == '\u23f9':
                button.configure(text= '\u23f5')
            else:
                button.configure(text= '\u23f9')
            temp = self.audio.data
            self.audio.data = self.audio.data_old
            self.play(file_id, callback)
            self.audio.data = temp
        self.play_button.configure(command=partial(press_button, self.play_button, audio.get_short_id(), partial(reset_button_icon, self.play_button)))
        self.play_original_button.configure(command=partial(play_original_audio, self.play_original_button, audio.get_short_id(), partial(reset_button_icon, self.play_original_button)))
        
        self.revert_button.pack(side="left")
        self.play_button.pack(side="left")
        
        if self.audio.modified and self.audio.data_old != b"":
            self.play_original_label.pack(side="right")
            self.play_original_button.pack(side="right")
        else:
            self.play_original_label.forget()
            self.play_original_button.forget()
            
    def revert(self):
        self.audio.revert_modifications()
        if self.track_info is not None:
            self.track_info.revert_modifications()
            self.play_at_text.delete(0, 'end')
            self.duration_text.delete(0, 'end')
            self.start_offset_text.delete(0, 'end')
            self.end_offset_text.delete(0, 'end')
            self.play_at_text.insert(END, f"{self.track_info.play_at}")
            self.duration_text.insert(END, f"{self.track_info.source_duration}")
            self.start_offset_text.insert(END, f"{self.track_info.begin_trim_offset}")
            self.end_offset_text.insert(END, f"{self.track_info.end_trim_offset}")
        self.update_modified()
        self.play_original_label.forget()
        self.play_original_button.forget()
        
    def apply_changes(self):
        self.track_info.set_data(play_at=float(self.play_at_text_var.get()), begin_trim_offset=float(self.start_offset_text_var.get()), end_trim_offset=float(self.end_offset_text_var.get()), source_duration=float(self.duration_text_var.get()))
        self.update_modified()
        
class MusicSegmentWindow:
    def __init__(self, parent, update_modified):
        self.frame = Frame(parent)
        self.update_modified = update_modified
        
        self.title_label = ttk.Label(self.frame, font=('Segoe UI', 14), anchor="center")

        self.duration_text_var = tkinter.StringVar(self.frame)
        self.fade_in_text_var = tkinter.StringVar(self.frame)
        self.fade_out_text_var = tkinter.StringVar(self.frame)
        
        self.duration_label = ttk.Label(self.frame,
                                    text="Duration (ms)",
                                    font=('Segoe UI', 12))
        self.duration_text = ttk.Entry(self.frame, textvariable=self.duration_text_var, font=('Segoe UI', 12), width=54)
        
        self.fade_in_label = ttk.Label(self.frame,
                                   text="End fade-in (ms)",
                                   font=('Segoe UI', 12))
        self.fade_in_text = ttk.Entry(self.frame, textvariable=self.fade_in_text_var, font=('Segoe UI', 12), width=54)
        
        self.fade_out_label = ttk.Label(self.frame,
                                    text="Start fade-out (ms)",
                                    font=('Segoe UI', 12))
        self.fade_out_text = ttk.Entry(self.frame, textvariable=self.fade_out_text_var, font=('Segoe UI', 12), width=54)
        self.revert_button = ttk.Button(self.frame, text="\u21b6", command=self.revert)
        self.apply_button = ttk.Button(self.frame, text="Apply", command=self.apply_changes)
        
        self.title_label.pack(pady=5)
        
        self.duration_label.pack()
        self.duration_text.pack()
        self.fade_in_label.pack()
        self.fade_in_text.pack()
        self.fade_out_label.pack()
        self.fade_out_text.pack()
        self.revert_button.pack(side="left")
        self.apply_button.pack(side="left")
        
    def set_segment_info(self, segment):
        self.title_label.configure(text=f"Info for Music Segment {segment.get_id()}")
        self.segment = segment
        self.duration_text.delete(0, 'end')
        self.fade_in_text.delete(0, 'end')
        self.fade_out_text.delete(0, 'end')
        self.duration_text.insert(END, f"{self.segment.duration}")
        self.fade_in_text.insert(END, f"{self.segment.entry_marker[1]}")
        self.fade_out_text.insert(END, f"{self.segment.exit_marker[1]}")
        
        
    def revert(self):
        self.segment.revert_modifications()
        self.duration_text.delete(0, 'end')
        self.fade_in_text.delete(0, 'end')
        self.fade_out_text.delete(0, 'end')
        self.duration_text.insert(END, f"{self.segment.duration}")
        self.fade_in_text.insert(END, f"{self.segment.entry_marker[1]}")
        self.fade_out_text.insert(END, f"{self.segment.exit_marker[1]}")
        self.update_modified()
        
    def apply_changes(self):
        self.segment.set_data(duration=float(self.duration_text_var.get()), entry_marker=float(self.fade_in_text_var.get()), exit_marker=float(self.fade_out_text_var.get()))
        self.update_modified()
 
class EventWindow:

    def __init__(self, parent, update_modified):
        self.frame = Frame(parent)
        self.update_modified = update_modified
        
        self.title_label = Label(self.frame, font=('Segoe UI', 14))
        
        self.play_at_text_var = tkinter.StringVar(self.frame)
        self.duration_text_var = tkinter.StringVar(self.frame)
        self.start_offset_text_var = tkinter.StringVar(self.frame)
        self.end_offset_text_var = tkinter.StringVar(self.frame)
        
        self.play_at_label = ttk.Label(self.frame,
                                   text="Play At (ms)",
                                   font=('Segoe UI', 12))
        self.play_at_text = ttk.Entry(self.frame, textvariable=self.play_at_text_var, font=('Segoe UI', 12), width=54)
        
        self.duration_label = ttk.Label(self.frame,
                                    text="Duration (ms)",
                                    font=('Segoe UI', 12))
        self.duration_text = ttk.Entry(self.frame, textvariable=self.duration_text_var, font=('Segoe UI', 12), width=54)
        
        self.start_offset_label = ttk.Label(self.frame,
                                        text="Start Trim (ms)",
                                        font=('Segoe UI', 12))
        self.start_offset_text = ttk.Entry(self.frame, textvariable=self.start_offset_text_var, font=('Segoe UI', 12), width=54)
        
        self.end_offset_label = ttk.Label(self.frame,
                                      text="End Trim (ms)",
                                      font=('Segoe UI', 12))
        self.end_offset_text = ttk.Entry(self.frame, textvariable=self.end_offset_text_var, font=('Segoe UI', 12), width=54)
        self.revert_button = ttk.Button(self.frame, text="\u21b6", command=self.revert)
        self.apply_button = ttk.Button(self.frame, text="Apply", command=self.apply_changes)
        
        self.title_label.pack(pady=5)
        
        self.play_at_label.pack()
        self.play_at_text.pack()
        self.duration_label.pack()
        self.duration_text.pack()
        self.start_offset_label.pack()
        self.start_offset_text.pack()
        self.end_offset_label.pack()
        self.end_offset_text.pack()
        self.revert_button.pack(side="left")
        self.apply_button.pack(side="left")
        
    def set_track_info(self, track_info):
        self.title_label.configure(text=f"Info for Event {track_info.get_id()}")
        self.track_info = track_info
        self.play_at_text.delete(0, 'end')
        self.duration_text.delete(0, 'end')
        self.start_offset_text.delete(0, 'end')
        self.end_offset_text.delete(0, 'end')
        self.play_at_text.insert(END, f"{self.track_info.play_at}")
        self.duration_text.insert(END, f"{self.track_info.source_duration}")
        self.start_offset_text.insert(END, f"{self.track_info.begin_trim_offset}")
        self.end_offset_text.insert(END, f"{self.track_info.end_trim_offset}")
        
    def revert(self):
        self.track_info.revert_modifications()
        self.play_at_text.delete(0, 'end')
        self.duration_text.delete(0, 'end')
        self.start_offset_text.delete(0, 'end')
        self.end_offset_text.delete(0, 'end')
        self.play_at_text.insert(END, f"{self.track_info.play_at}")
        self.duration_text.insert(END, f"{self.track_info.source_duration}")
        self.start_offset_text.insert(END, f"{self.track_info.begin_trim_offset}")
        self.end_offset_text.insert(END, f"{self.track_info.end_trim_offset}")
        self.update_modified()
        
    def apply_changes(self):
        self.track_info.set_data(play_at=float(self.play_at_text_var.get()), begin_trim_offset=float(self.start_offset_text_var.get()), end_trim_offset=float(self.end_offset_text_var.get()), source_duration=float(self.duration_text_var.get()))
        self.update_modified()

"""
Not suggested to use this as a generic autocomplete widget for other searches.
Currently it's only used specifically for search archive.
"""
class ArchiveSearch(ttk.Entry):

    ignore_keys: list[str] = ["Up", "Down", "Left", "Right", "Escape", "Return"]

    def __init__(self, 
                 fmt: str,
                 entries: dict[str, str] = {}, 
                 on_select_cb: Callable[[Any], None] | None = None,
                 master: Misc | None = None,
                 **options):
        super().__init__(master, **options)

        self.on_select_cb = on_select_cb
        self.entries = entries
        self.fmt = fmt

        self.cmp_root: tkinter.Toplevel | None = None
        self.cmp_list: tkinter.Listbox | None = None
        self.cmp_scrollbar: ttk.Scrollbar | None = None

        self.bind("<Key>", self.on_key_release)
        self.bind("<FocusOut>", self.on_focus_out)
        self.bind("<Return>", self.on_return)
        self.bind("<Escape>", self.destroy_cmp)
        self.bind("<Up>", self.on_arrow_up)
        self.bind("<Down>", self.on_arrow_down)
        self.language = ""
        self.winfo_toplevel().bind("<Configure>", self.sync_windows)

    def sync_windows(self, event=None):
        if self.cmp_root is not None and self.winfo_toplevel() is not None:
            self.cmp_root.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height()}")
            self.cmp_root.lift()
            
    def add_language(self, name: str, language: str):
        if self.language == "" and language != "none":
            return f"{name} ({language})"
        else:
            return name

    def on_key_release(self, event: tkinter.Event):
        if event.keysym in self.ignore_keys:
            return
        query = self.get().lower()

        if self.cmp_root != None:
            if self.cmp_list == None:
                logger.error("Autocomplete error!" \
                        "cmp_list should not be None with cmp_root still" \
                        "active", stack_info=True)
                self.cmp_root.destroy()
                return
            archives = []
            if query == "":
                archives = [self.fmt.format(v.archive, self.add_language(v.friendlyname, v.language)) 
                            for v in self.entries.values()]
            else:
                unique: set[str] = set()
                for entry in self.entries.values():
                    match = entry.archive.find(query) != -1 or \
                            entry.friendlyname.lower().find(query) != -1
                    if not match or entry.name in unique:
                        continue
                    archives.append(self.fmt.format(entry.archive, self.add_language(entry.friendlyname, entry.language)))
                    unique.add(entry.name)
            self.cmp_list.delete(0, tkinter.END)
            for archive in archives:
                self.cmp_list.insert(tkinter.END, archive)
            height="128"
            if len(archives) < 7:
                height=str(2+18*len(archives))
                try:
                    self.cmp_scrollbar.pack_forget()
                except:
                    pass
            elif len(archives) > 7:
                try:
                    self.cmp_scrollbar.pack(side="left", fill="y")
                except:
                    pass
            self.cmp_root.geometry(f"{self.winfo_width()}x{height}")
            self.cmp_list.selection_clear(0, tkinter.END)
            self.cmp_list.selection_set(0)
            return

        archives = []
        if query == "":
            archives = [self.fmt.format(v.archive, self.add_language(v.friendlyname, v.language)) 
                        for v in self.entries.values()]
        else:
            unique: set[str] = set()
            for entry in self.entries.values():
                match = entry.archive.find(query) != -1 or \
                        entry.friendlyname.lower().find(query) != -1
                if not match or entry.name in unique:
                    continue
                archives.append(self.fmt.format(entry.archive, self.add_language(entry.friendlyname, entry.language)))
                unique.add(entry.name)

        self.cmp_root = tkinter.Toplevel(self)
        self.cmp_root.wm_overrideredirect(True) # Hide title bar
        

        self.cmp_list = tkinter.Listbox(self.cmp_root, borderwidth=1)

        self.cmp_list.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)
        
        if len(archives) > 7:
            self.cmp_scrollbar = ttk.Scrollbar(self.cmp_root, orient=VERTICAL)
            self.cmp_scrollbar.pack(side="left", fill="y")
            self.cmp_list.configure(yscrollcommand=self.cmp_scrollbar.set)
            self.cmp_scrollbar['command'] = self.cmp_list.yview

        for archive in archives:
            self.cmp_list.insert(tkinter.END, archive)

        self.cmp_list.selection_set(0)

        self.cmp_list.bind("<Double-Button-1>", self.on_return)
        height="128"
        if len(archives) < 7:
            height=str(2+18*len(archives))
        self.cmp_root.geometry(f"{self.winfo_width()}x{height}")
        self.cmp_root.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height()}")
        
    def error_check(self):
        if self.cmp_root == None:
            return 1
        if self.cmp_list == None:
            logger.critical("Autocomplete error!" \
                    "Autocomplete list is not initialized", stack_info=True)
            return 1
        curr_select = self.cmp_list.curselection()
        if len(curr_select) == 0:
            return 1
        if len(curr_select) != 1:
            logger.warning("Something went wrong with autocomplete: " \
                    "more than one item is selected.", stack_info=True)
        return 0

    def on_arrow_up(self, _: tkinter.Event) -> str | None:
        if self.error_check() != 0:
            return
        curr_select = self.cmp_list.curselection()
        curr_idx = curr_select[0]
        prev_idx = (curr_idx - 1) % self.cmp_list.size()
        self.cmp_list.selection_clear(0, tkinter.END)
        self.cmp_list.selection_set(prev_idx)
        self.cmp_list.activate(prev_idx)
        self.cmp_list.see(prev_idx)
        return "break" # Prevent default like in JS

    def on_arrow_down(self, _: tkinter.Event):
        if self.error_check() != 0:
            return
        curr_select = self.cmp_list.curselection()
        curr_idx = curr_select[0]
        next_idx = (curr_idx + 1) % self.cmp_list.size()
        self.cmp_list.selection_clear(0, tkinter.END)
        self.cmp_list.selection_set(next_idx)
        self.cmp_list.activate(next_idx)
        self.cmp_list.see(next_idx)
        return "break" # Prevent default like in JS

    def on_return(self, _: tkinter.Event):
        if self.error_check() != 0:
            return
        curr_select = self.cmp_list.curselection()
        value = self.cmp_list.get(curr_select[0])
        self.delete(0, tkinter.END)
        self.insert(0, value)
        self.icursor(tkinter.END)
        self.destroy_cmp(None)
        if self.on_select_cb == None:
            return
        self.on_select_cb(value)

    def destroy_cmp(self, _: tkinter.Event | None):
        if self.cmp_list != None:
            self.cmp_list.destroy()
            self.cmp_list = None

        if self.cmp_root != None:
            self.cmp_root.destroy()
            self.cmp_root = None

    def on_focus_out(self, event):
        if self.cmp_root is not None:
            self.cmp_root.after(1, self.check_should_destroy)

    def check_should_destroy(self):
        new_focus = self.cmp_root.focus_get()
        if new_focus != self.cmp_list and new_focus != self.cmp_root:
            self.destroy_cmp(None)

    def set_entries(self, entries: dict[str, str], fmt: str | None = None):
        if fmt != None:
            self.fmt = fmt
        self.entries = entries
        self.delete(0, tkinter.END)
        

class WorkspaceView(QTreeView):
    def __init__(self, parent):
        super().__init__(parent)
        self.selectedFiles = []
        self.initModel()
        self.initUI()
        
    def initModel(self):
        file_system_model = QFileSystemModel()
        file_system_model.setRootPath(WORKSPACE_FOLDER)
        file_system_model.setNameFilters(["*" + filetype for filetype in SUPPORTED_AUDIO_TYPES] + ["*.patch_*"])
        file_system_model.setNameFilterDisables(1)
        self.setModel(file_system_model)
        self.setRootIndex(file_system_model.index(WORKSPACE_FOLDER))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.resize(200, 200)
        
    def initUI(self):
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.hideColumn(1)
        self.hideColumn(2)
        self.hideColumn(3)
        self.initContextMenu()
        
    def addFolder(self, src):
        os.symlink(src, os.path.join(WORKSPACE_FOLDER, os.path.basename(src)), target_is_directory=True)
        
    def removeSelected(self):
        for f in self.selectedFiles:
            self.model().rmdir(f)
            self.model().remove(f)
            
    def importSelected(self):
        for f in self.selectedFiles:
            pass
        
    def setSelection(self, rect, command):
        super().setSelection(rect, command)
        self.selectedFiles = self.selectedIndexes()
        
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            filename = url.toLocalFile()
            if os.path.isdir(filename):
                self.addFolder(filename)
    
    def dragEnterEvent(self, event):
        for url in event.mimeData().urls():
            if not os.path.isdir(url.toLocalFile()):
                event.ignore()
                return
        event.accept()
        
    def dragMoveEvent(self, event):
        for url in event.mimeData().urls():
            if not os.path.isdir(url.toLocalFile()):
                event.ignore()
                return
        event.accept()
        
    def mouseDoubleClickEvent(self, event):
        selects = self.selectedIndexes()
        if len(selects) == 1:
            selectedIndex = selects[0]
            if not self.model().isDir(selectedIndex):
                filepath = self.model().filePath(selectedIndex)
            if os.path.splitext(filepath)[1] in SUPPORTED_AUDIO_TYPES:
                with open(filepath, "rb") as f:
                    audio_data = f.read()
                SoundHandler.get_instance().play_audio(os.path.basename(os.path.splitext(filepath)[0]), audio_data)
                
    def initContextMenu(self):
        self.contextMenu = QMenu(self)
        
        #check selected indices to see which actions to add
        
        self.contextMenuDeleteAction = QAction("Delete")
        self.contextMenuImportAction = QAction("Import")
        
        self.contextMenuDeleteAction.triggered.connect(self.removeSelected)
        self.contextMenuImportAction.triggered.connect(self.importSelected)
        
    def showContextMenu(self, pos):
        self.contextMenu.clear()
        if not self.selectedIndexes():
            return
        self.contextMenu.addAction(self.contextMenuDeleteAction)
        self.contextMenu.addAction(self.contextMenuImportAction)
        global_pos = self.mapToGlobal(pos)
        self.contextMenu.exec(global_pos)

class ModView(QWidget):
    selectionChanged = Signal(QItemSelection, QItemSelection)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        self.mod = None
        
    def initUI(self):
        self.treeView = ModTreeView(self)
        self.treeView.selectionChanged.connect(self.selectionChangedExport)
        self.nameLabel = QLabel("No mod currently loaded")
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.nameLabel)
        self.layout.addWidget(self.treeView)
        self.layout.setContentsMargins(QMargins(0, 0, 0, 0))
        self.setLayout(self.layout)
        
    def setMod(self, mod):
        self.mod = mod
        self.treeView.setMod(mod)
        if mod is not None:
            self.nameLabel.setText(mod.name)
        else:
            self.nameLabel.setText("No mod currently loaded")
        
    def activeModChanged(self, mod_name):
        try:
            self.setMod(ModHandler.get_instance().get_active_mod())
        except LookupError:
            self.setMod(None)
            
    def selectionChangedExport(self, selected, deselected):
        self.selectionChanged.emit(selected, deselected)
            
    def modRenamed(self, old_name, new_name):
        self.nameLabel.setText(self.mod.name)
        
    def refresh(self):
        self.treeView.refresh()

class ModTreeView(QTreeView):
    selectionChanged = Signal(QItemSelection, QItemSelection)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection = []
        self.models = {}
        self.initModel()
        self.initUI()
        
    def initModel(self):
        self.proxyModel = ModViewFilter()
        self.setModel(self.proxyModel)
        
    def initUI(self):
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.selectionModel().selectionChanged.connect(self.selectionChangedExport)
        self.customContextMenuRequested.connect(self.showContextMenu)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.resize(100, 100)
        self.initContextMenu()
        
    def setSelection(self, rect, command):
        super().setSelection(rect, command)
        self.selection = self.selectedIndexes()
        
    def setMod(self, mod):
        if mod in self.models.keys():
            self.proxyModel.setSourceModel(self.models[mod])
        else:
            new_model = ModModel()
            new_model.setMod(mod)
            self.models[mod] = new_model
            self.proxyModel.setSourceModel(self.models[mod])
            
    def selectionChangedExport(self, selected, deselected):
        self.selectionChanged.emit(selected, deselected)
        
    def dropEvent(self, event):
        pass
        #for url in event.mimeData().urls():
        #    filename = url.toLocalFile()
        #    if os.path.isdir(filename):
        #        self.addFolder(filename)
        
    def mouseDoubleClickEvent(self, event):
        selection = self.proxyModel.mapToSource(self.selectedIndexes()[0])
        selectedItem = self.proxyModel.sourceModel().itemFromIndex(selection)
        if selectedItem:
            audioSource = selectedItem.data()
            if isinstance(audioSource, AudioSource):
                SoundHandler.get_instance().play_audio(audioSource.get_id(), audioSource.get_data())
    
    def dragEnterEvent(self, event):
        for url in event.mimeData().urls():
            if not os.path.isdir(url.toLocalFile()):
                event.ignore()
                return
        event.accept()
        
    def dragMoveEvent(self, event):
        for url in event.mimeData().urls():
            if not os.path.isdir(url.toLocalFile()):
                event.ignore()
                return
        event.accept()
        
    def activeModChanged(self, mod_name):
        try:
            self.setMod(ModHandler.get_instance().get_active_mod())
        except LookupError:
            self.setMod(None)
            
    def initContextMenu(self):
        self.contextMenuRemoveArchive = QAction("Remove")
        self.contextMenuTargetedImport = QAction("Import")
        self.contextMenuDumpWav = QAction("Dump as Wav")
        self.contextMenuDumpWem = QAction("Dump as Wem")
        
    def showContextMenu(self, pos):
        pass
        #contextMenu = QMenu(self)
        
        #global_pos = self.mapToGlobal(pos)
        #contextMenu.exec(global_pos)
        
    def refresh(self):
        try:
            self.proxyModel.sourceModel().refresh()
        except:
            pass
    
    def drawRow(self, painter, options, index):
        data = self.proxyModel.sourceModel().itemFromIndex(self.proxyModel.mapToSource(index)).data()
        if isinstance(data, GameArchive):
            pass
        elif isinstance(data, (WwiseBank, AudioSource, TextBank, StringEntry)):
            if data.modified:
                painter.fillRect(options.rect, QColor(128, 128, 128, 255))
        elif isinstance(data, HircEntry):
            if data.modified or data.has_modified_children():
                painter.fillRect(options.rect, QColor(128, 128, 128, 255))
        super().drawRow(painter, options, index)

class ModViewFilter(QSortFilterProxyModel):
    
    acceptableTypes = (Sound, WwiseBank, MusicTrack, MusicSegment, GameArchive, AudioSource, StringEntry, TextBank)
    autoAcceptTypes = (GameArchive, WwiseBank, TextBank)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        

class ModModel(QStandardItemModel):
    
    ALL_TYPES = set([WwiseBank, TextBank, AudioSource, StringEntry, MusicTrack, MusicSegment, RandomSequenceContainer, GameArchive])
    
    def __init__(self):
        super().__init__()
        self.itemChanged.connect(self.update)
        self.visibleTypes = set([WwiseBank, TextBank, AudioSource, StringEntry, MusicTrack, MusicSegment, RandomSequenceContainer, GameArchive])
    
    beforeItemChanged = Signal(QStandardItem)
    
    def _create_row(self, item):
        if isinstance(item, WwiseBank):
            name = item.dep.data.replace('\x00', '')
            item_type = "Sound Bank"
            item_id = item.get_id()
        elif isinstance(item, TextBank):
            name = f"{item.get_id()}.text"
            item_type = "Text Bank"
            item_id = item.get_id()
        elif isinstance(item, AudioSource):
            name = f"{item.get_id()}.wem"
            item_type = "Audio Source"
            item_id = item.get_id()
        elif isinstance(item, TrackInfoStruct):
            name = f"Event {item.get_id()}"
            item_type = "Event"
            item_id = item.get_id()
        elif isinstance(item, StringEntry):
            item_type = "String"
            name = item.get_text()[:20]
            item_id = item.get_id()
        elif isinstance(item, MusicTrack):
            item_type = "Music Track"
            name = f"Track {item.get_id()}"
            item_id = item.get_id()
        elif isinstance(item, MusicSegment):
            item_type = "Music Segment"
            name = f"Segment {item.get_id()}"
            item_id = item.get_id()
        elif isinstance(item, RandomSequenceContainer):
            item_type = "Random Sequence"
            name = f"Sequence {item.get_id()}"
            item_id = item.get_id()
        elif isinstance(item, GameArchive):
            name = item.name
            item_type = "Archive File"
            item_id = item.name
        else:
            name = f"{type(item).__name__} {item.get_id()}"
            item_type = f"{type(item).__name__}"
            item_id = item.get_id()
        name_item = QStandardItem(name)
        name_item.setData(item)
        type_item = QStandardItem(item_type)
        type_item.setEditable(False)
        #id_item = QStandardItem(str(item_id))
        #id_item.setEditable(False)
        return [name_item, type_item]

    def setTypeVisibility(self, type, visible):
        if visible:
            self.visibleTypes.add(type)
        else:
            self.visibleTypes.remove(type)
    
    #add function that does a diff instead of redoing the entire thing when loading/removing an archive
    def refresh(self):
        self.clear()
        if self.mod is None:
            return
        self.setHorizontalHeaderLabels(["File Name", "Type"])
        root = self.invisibleRootItem()
        parentItem = root
        game_archives = self.mod.get_game_archives()
        sequence_sources = set()
        for archive in game_archives.values():
            archive_entry = self._create_row(archive)
            root.appendRow(archive_entry)
            for bank in archive.wwise_banks.values():
                bank_entry = self._create_row(bank)
                archive_entry[0].appendRow(bank_entry)
                for hierarchy_entry in bank.hierarchy.entries.values():
                    if isinstance(hierarchy_entry, MusicSegment):
                        segment_entry = self._create_row(hierarchy_entry)
                        bank_entry[0].appendRow(segment_entry)
                        for track_id in hierarchy_entry.tracks:
                            track = bank.hierarchy.entries[track_id]
                            track_entry = self._create_row(track)
                            segment_entry[0].appendRow(track_entry)
                            for source in track.sources:
                                if source.plugin_id == VORBIS:
                                    try:
                                        source_entry = self._create_row(self.mod.get_audio_source(source.source_id))
                                        track_entry[0].appendRow(source_entry)
                                    except:
                                        pass
                            for info in track.track_info:
                                if info.event_id != 0:
                                    event_entry = self._create_row(info)
                                    track_entry[0].appendRow(event_entry)
                    elif isinstance(hierarchy_entry, RandomSequenceContainer):
                        container_entry = self._create_row(hierarchy_entry)
                        bank_entry[0].appendRow(container_entry)
                        for s_id in hierarchy_entry.contents:
                            sound = bank.hierarchy.entries[s_id]
                            if len(sound.sources) > 0 and sound.sources[0].plugin_id == VORBIS:
                                sequence_sources.add(sound)
                                try:
                                    source_entry = self._create_row(self.mod.get_audio_source(sound.sources[0].source_id))
                                    container_entry[0].appendRow(source_entry)
                                except:
                                    pass
                for hierarchy_entry in bank.hierarchy.entries.values():
                    if isinstance(hierarchy_entry, Sound) and hierarchy_entry not in sequence_sources:
                        if hierarchy_entry.sources[0].plugin_id == VORBIS:
                            try:
                                source_entry = self._create_row(self.mod.get_audio_source(hierarchy_entry.sources[0].source_id))
                                bank_entry[0].appendRow(source_entry)
                            except:
                                pass
            for text_bank in archive.text_banks.values():
                if text_bank.language == language:
                    bank_entry = self._create_row(text_bank)
                    archive_entry[0].appendRow(bank_entry)
                    for string_entry in text_bank.entries.values():
                        text_entry = self._create_row(string_entry)
                        bank_entry[0].appendRow(text_entry)
                        
    def setMod(self, mod):
        self.mod = mod
        self.refresh()
        
    def update(self, item):
        pass
            

class ModSelectorView(QWidget):
    setActive = Signal(str)
    modRenamed = Signal(str, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.listView = self.plusButton = self.minusButton = self.setActiveButton = None
        self.model = None
        self.initModel()
        self.initUI()
        
    def initModel(self):
        self.model = ModSelectorModel()
        self.model.itemChanged.connect(self.itemChanged)
        self.model.beforeItemChanged.connect(self.beforeItemChanged)
        
    def initUI(self):
        self.listView = QListView(self)
        self.listView.setModel(self.model)
        self.plusButton = QPushButton("+", self)
        self.plusButton.setFixedSize(20, 20)
        #self.plusButton.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.minusButton = QPushButton("-", self)
        self.minusButton.setFixedSize(20, 20)
        #self.minusButton.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setActiveButton = QPushButton("Open", self)
        self.setActiveButton.setFixedSize(50, 20)
        #self.setActiveButton.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        buttonContainer = QWidget()
        buttonLayout = QHBoxLayout()
        buttonLayout.setContentsMargins(QMargins(4, 0, 4, 0))
        spacer = QSpacerItem(110, 20, hData=QSizePolicy.Policy.Expanding)
        buttonLayout.addSpacerItem(spacer)
        buttonLayout.addWidget(self.plusButton)
        buttonLayout.addWidget(self.minusButton)
        buttonLayout.addWidget(self.setActiveButton)
        self.plusButton.clicked.connect(self.addMod)
        self.minusButton.clicked.connect(self.removeMod)
        self.setActiveButton.clicked.connect(self.setActiveMod)
        buttonContainer.setLayout(buttonLayout)
        layout = QVBoxLayout()
        #layout.setContentsMargins(QMargins(11, 4, 11, 11))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.listView.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.listView.resize(100, 100)
        layout.addWidget(buttonContainer)
        layout.addWidget(self.listView)
        self.setMinimumSize(250, 100)
        self.resize(250, 175)
        self.setLayout(layout)
        
    def addMod(self):
        name = "new"
        count = 1
        while self.listView.model().nameTaken(name):
            name = f"new{count}"
            count += 1
        self.listView.model().addMod(name)
        ModHandler.get_instance().set_active_mod(name)
        index = self.listView.model().indexFromItem(self.listView.model().findItems(name)[0])
        selection = QItemSelection(index, index)
        self.listView.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
        self.setActive.emit(ModHandler.get_instance().get_active_mod())
        
    def removeMod(self):
        mod = self.listView.selectedIndexes()[0]
        self.listView.model().removeMod(mod)
        try:
            mod = ModHandler.get_instance().get_active_mod()
        except LookupError:
            self.setActive.emit(None)
            return
        
        index = self.listView.model().indexFromItem(self.listView.model().findItems(mod.name)[0])
        selection = QItemSelection(index, index)
        self.listView.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
        self.setActive.emit(mod)
        
    def setActiveMod(self):
        selected_mod = self.listView.model().itemFromIndex(self.listView.selectedIndexes()[0]).text()
        self.listView.model().mod_handler.set_active_mod(selected_mod)
        self.setActive.emit(selected_mod)
        
    def beforeItemChanged(self, item):
        self.old_name = item.text()
        
    def itemChanged(self, item):
        self.modRenamed.emit(self.old_name, item.text())
        
    def closeEvent(self, event):
        if not event.spontaneous():
            event.accept()
        else:
            event.ignore()
            self.hide()
            
    def toggleVisible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
        if self.isMinimized():
            self.showNormal()
    
class ModSelectorModel(QStandardItemModel):
    
    beforeItemChanged = Signal(QStandardItem)
    
    def __init__(self):
        super().__init__()
        self.setHorizontalHeaderLabels([""])
        self.itemChanged.connect(self.update)
        self.beforeItemChanged.connect(self.beforeUpdate)
        self.mod_handler = ModHandler.get_instance()
        root = self.invisibleRootItem()
        for name in self.mod_handler.get_mod_names():
            item = QStandardItem(name)
            root.appendRow(item)
        
    def getMod(self, mod_name):
        pass 
        
    def setData(self, index, value, role=Qt.EditRole):
        self.beforeItemChanged.emit(self.itemFromIndex(index))
        return super().setData(index, value, role)
    
    def addMod(self, mod_name):
        if not self.nameTaken(mod_name):
            name_item = QStandardItem(mod_name)
            self.invisibleRootItem().appendRow(name_item)
            self.mod_handler.create_new_mod(mod_name)
        
    def removeMod(self, index):
        row = self.takeRow(index.row())
        self.mod_handler.delete_mod(row[0].text())
        
    def nameTaken(self, name):
        return name in self.mod_handler.get_mod_names()
        
    def beforeUpdate(self, item):
        self.old_name = item.text()
        
    def update(self, item):
        self.mod_handler.rename_mod(self.old_name, item.text())

class InfoView(QWidget):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        
    def initUI(self):
        self.layout = QVBoxLayout()
        self.label = QLabel()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)
        
    def setContents(self, selected, deselected):
        itemSelectionRange = selected.first()
        content = itemSelectionRange.model().itemFromIndex(itemSelectionRange.topLeft()).data()
        try:
            self.label.setText(str(content.get_id()))
        except:
            self.label.setText("UNAVAILABLE")

class WindowBar(QWidget):
    
    modSelectToggle = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        
    def initUI(self):
        layout = QHBoxLayout()
        self.modSelectWindow = QPushButton("Manage Mods", self)
        self.modSelectWindow.clicked.connect(self.modSelectWindowToggle)
        layout.setContentsMargins(QMargins(4, 0, 4, 0))
        layout.addWidget(self.modSelectWindow)
        self.setLayout(layout)
        
    def modSelectWindowToggle(self):
        self.modSelectToggle.emit()
        
class TopBar(QWidget):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        
    def initUI(self):
        layout = QHBoxLayout()
        self.window_bar = WindowBar(self)
        spacer = QSpacerItem(300, 1, hData=QSizePolicy.Policy.Expanding)
        layout.addSpacerItem(spacer)
        layout.setContentsMargins(QMargins(4, 4, 4, 4))
        layout.addWidget(self.window_bar)
        self.resize(300, 20)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setLayout(layout)

class MainWindow(QMainWindow):

    def __init__(self, 
                 app_state: cfg.Config, 
                 lookup_store: db.LookupStore | None):
        super().__init__()
        
        self.mod_handler = ModHandler.get_instance()
        self.sound_handler = SoundHandler.get_instance()
        self.mod_handler.create_new_mod("new mod", set_active=True)
        self.setWindowTitle("HD2 Audio Modder")
        self.resize(1280, 720)
        
        self.initComponents()
        self.connectComponents()
        self.layoutComponents()
        
        
    def initComponents(self):
        self.initMenuBar()
        self.initModView()
        self.initModSelectorView()
        self.initInfoView()
        self.initWorkspaceView()
        self.initToolBars()
        
    def connectComponents(self):
        self.mod_selector_view.setActive.connect(self.mod_view.activeModChanged)
        self.mod_selector_view.modRenamed.connect(self.mod_view.modRenamed)
        self.mod_view.selectionChanged.connect(self.info_view.setContents)
        self.manageModsAction.triggered.connect(self.mod_selector_view.toggleVisible)
        self.fileOpenArchiveAction.triggered.connect(lambda x: self.load_archive(initialdir=GAME_FILE_LOCATION))
        self.fileImportAudioAction.triggered.connect(self.import_audio_files)
        self.fileImportPatchAction.triggered.connect(self.import_patch)
        self.fileWritePatchAction.triggered.connect(self.write_patch)
        self.editRevertAllAction.triggered.connect(self.revert_all)
        self.dumpAllAsWavAction.triggered.connect(self.dump_all_as_wav)
        self.dumpAllAsWemAction.triggered.connect(self.dump_all_as_wem)
        
    def layoutComponents(self):
        self.setMinimumSize(300, 200)
        self.layout = QVBoxLayout()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.workspace_view)
        self.splitter.addWidget(self.mod_view)
        self.splitter.addWidget(self.info_view)
        
        self.layout.addWidget(self.splitter)
        widget = QWidget()
        
        widget.setLayout(self.layout)
        self.setCentralWidget(widget)
        
    def initMenuBar(self):
        menu_bar = self.menuBar()
        
        self.file_menu = menu_bar.addMenu("File")
        
        self.fileOpenArchiveAction = QAction("Open Archive", self)
        self.fileImportPatchAction = QAction("Import Patch File", self)
        self.fileImportAudioAction = QAction("Import Audio Files", self)
        self.fileWritePatchAction = QAction("Write Patch", self)
        
        self.file_menu.addAction(self.fileOpenArchiveAction)
        self.file_menu.addAction(self.fileImportPatchAction)
        self.file_menu.addAction(self.fileImportAudioAction)
        self.file_menu.addAction(self.fileWritePatchAction)
        
        
        self.edit_menu = menu_bar.addMenu("Edit")
        
        self.editRevertAllAction = QAction("Revert All", self)
        self.editPreferencesAction = QAction("Preferences", self)
        
        self.edit_menu.addAction(self.editRevertAllAction)
        
        
        self.dump_menu = menu_bar.addMenu("Dump")
        
        self.dumpAllAsWemAction = QAction("Dump All As Wem", self)
        self.dumpAllAsWavAction = QAction("Dump All As Wav", self)
        
        self.dump_menu.addAction(self.dumpAllAsWemAction)
        self.dump_menu.addAction(self.dumpAllAsWavAction)
        
        
        
    def initToolBars(self):
        windowToolBar = self.addToolBar("Toolbar")
        
        self.manageModsAction = QAction("Manage Mods", self)
        self.manageModsAction.setToolTip("Toggles the Mod Selector window")
        windowToolBar.addAction(self.manageModsAction)
        
    def initTopBar(self):
        self.top_bar = TopBar(self)

    def initModView(self):
        self.mod_view = ModView(self)
        self.mod_view.setMod(self.mod_handler.get_active_mod())
        
    def initModSelectorView(self):
        self.mod_selector_view = ModSelectorView()
        self.mod_selector_view.setWindowTitle("Manage Mods")
        
    def initWorkspaceView(self):
        self.workspace_view = WorkspaceView(self)
        
    def initInfoView(self):
        self.info_view = InfoView(self)
    
    def closeEvent(self, event):
        self.mod_selector_view.close()
        
    def combine_music_mods(self):
        self.sound_handler.kill_sound()
        if not self.app_state.game_data_path or not os.path.exists(self.app_state.game_data_path):
            showwarning(title="Error", message="Unable to locate Helldivers 2 game files. Cannot automatically merge mods.")
        mod_files = filedialog.askopenfilenames(title="Choose mod files to combine", filetypes=[("Zip Archive", "*.zip")])
        if mod_files:
            combined_mod = self.mod_handler.create_new_mod("combined_mods_temp")
            combined_mod.load_archive_file(os.path.join(self.app_state.game_data_path, "046d4441a6dae0a9"))
            combined_mod.load_archive_file(os.path.join(self.app_state.game_data_path, "89de9c3d26d2adc1"))
            combined_mod.load_archive_file(os.path.join(self.app_state.game_data_path, "fdf011daecf24312"))
            combined_mod.load_archive_file(os.path.join(self.app_state.game_data_path, "2e24ba9dd702da5c"))
            extracted_mods = []
            for mod in mod_files:
                zip = zipfile.ZipFile(mod)
                zip.extractall(path=CACHE)
                for patch_file in [os.path.join(CACHE, file) for file in os.listdir(CACHE) if os.path.isfile(os.path.join(CACHE, file)) and "patch" in os.path.splitext(file)[1]]:
                    combined_mod.import_patch(patch_file)
                for file in os.listdir(CACHE):
                    file = os.path.join(CACHE, file)
                    try:
                        if os.path.isfile(file):
                            os.remove(file)
                        elif os.path.isdir(file):
                            shutil.rmtree(file)
                    except:
                        pass
            output_file = filedialog.asksaveasfilename(title="Save combined mod", filetypes=[("Zip Archive", "*.zip")], initialfile="combined_mod.zip")
            if output_file:
                combined_mod.write_patch(CACHE)
                zip = zipfile.ZipFile(output_file, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=3)
                with open(os.path.join(CACHE, "9ba626afa44a3aa3.patch_0"), 'rb') as patch_file:
                    zip.writestr("9ba626afa44a3aa3.patch_0", patch_file.read())
                if os.path.exists(os.path.join(CACHE, "9ba626afa44a3aa3.patch_0.stream")):
                    with open(os.path.join(CACHE, "9ba626afa44a3aa3.patch_0.stream"), 'rb') as stream_file:
                        zip.writestr("9ba626afa44a3aa3.patch_0.stream", stream_file.read())
                zip.close()
                try:
                    os.remove(os.path.join(CACHE, "9ba626afa44a3aa3.patch_0"))
                    os.remove(os.path.join(CACHE, "9ba626afa44a3aa3.patch_0.stream"))
                except:
                    pass
            self.mod_handler.delete_mod("combined_mods_temp")

    def drop_import(self, event):
        self.drag_source_widget = None
        renamed = False
        old_name = ""
        if event.data:
            import_files = []
            dropped_files = event.widget.tk.splitlist(event.data)
            for file in dropped_files:
                import_files.extend(list_files_recursive(file))
            if os.path.exists(WWISE_CLI):
                import_files = [file for file in import_files if os.path.splitext(file)[1] in SUPPORTED_AUDIO_TYPES or ".patch_" in os.path.basename(file)]
            else:
                import_files = [file for file in import_files if os.path.splitext(file)[1] == ".wem" or ".patch_" in os.path.basename(file)]
            if (
                len(import_files) == 1 
                and os.path.splitext(import_files[0])[1] in SUPPORTED_AUDIO_TYPES
                and self.treeview.item(event.widget.identify_row(event.y_root - self.treeview.winfo_rooty()), option="values")
                and self.treeview.item(event.widget.identify_row(event.y_root - self.treeview.winfo_rooty()), option="values")[0] == "Audio Source"
            ):
                audio_id = get_number_prefix(os.path.basename(import_files[0]))
                if audio_id != 0 and self.mod_handler.get_active_mod().get_audio_source(audio_id) is not None:
                    answer = askyesnocancel(title="Import", message="There is a file with the same name, would you like to replace that instead?")
                    if answer is None:
                        return
                    if not answer:
                        targets = [int(self.treeview.item(event.widget.identify_row(event.y_root - self.treeview.winfo_rooty()), option='tags')[0])]
                    else:
                        targets = [audio_id]
                else:
                    targets = [int(self.treeview.item(event.widget.identify_row(event.y_root - self.treeview.winfo_rooty()), option='tags')[0])]
                file_dict = {import_files[0]: targets}
            else:
                file_dict = {file: [get_number_prefix(os.path.basename(file))] for file in import_files}
            self.import_files(file_dict)

    def search_bar_on_enter_key(self, event):
        self.search()
        
    def set_theme(self):
        theme = self.selected_theme.get()
        try:
            if theme == "dark_mode":
                self.root.tk.call("set_theme", "dark")
                self.window.configure(background="white")
            elif theme == "light_mode":
                self.root.tk.call("set_theme", "light")
                self.window.configure(background="black")
        except Exception as e:
            logger.error(f"Error occurred when loading themes: {e}. Ensure azure.tcl and the themes folder are in the same folder as the executable")
        self.app_state.theme = theme
        self.workspace.column("#0", width=256+16)
        self.treeview.column("#0", width=250)
        self.treeview.column("type", width=100)
        self.check_modified()
        
    def get_colors(self, modified=False):
        theme = self.selected_theme.get()
        if theme == "dark_mode":
            if modified:
                return (MainWindow.dark_mode_modified_bg, MainWindow.dark_mode_modified_fg)
            else:
                return (MainWindow.dark_mode_bg, MainWindow.dark_mode_fg)
        elif theme == "light_mode":
            if modified:
                return (MainWindow.light_mode_modified_bg, MainWindow.light_mode_modified_fg)
            else:
                return (MainWindow.light_mode_bg, MainWindow.light_mode_fg)

    def import_audio_files(self):
        
        if os.path.exists(WWISE_CLI):
            available_filetypes = [("Audio Files", " ".join(SUPPORTED_AUDIO_TYPES))]
        else:
            available_filetypes = [("Wwise Vorbis", "*.wem")]
        files = filedialog.askopenfilenames(title="Choose files to import", filetypes=available_filetypes)
        if not files:
            return
        file_dict = {file: [get_number_prefix(os.path.basename(file))] for file in files}
        self.import_files(file_dict)
        
    def import_files(self, file_dict):
        self.mod_handler.get_active_mod().import_files(file_dict)

    def init_archive_search_bar(self):
        if self.name_lookup == None:
            logger.critical("Audio archive database connection is None after \
                    bypassing all check.", stack_info=True)
            return
        soundbanks = self.name_lookup.query_soundbanks()
        entries: dict[str, LookupResult] = {
                bank.id: bank
                for bank in soundbanks}
        self.archive_search = ArchiveSearch("{1} || {0}", 
                                            entries=entries,
                                            on_select_cb=self.on_archive_search_bar_return,
                                            master=self.top_bar,
                                            width=64)
        categories = ["English", "Spanish, Castilian", "Spanish, Latin America", "French", "Italian", "German", "Japanese", "Portuguese"]
        categories = [""] + categories
        self.category_search = ttk.Combobox(self.top_bar,
                                            state="readonly",
                                            font=('Segoe UI', 10),
                                            width=18, height=10,
                                            values=categories) 
        self.archive_search.pack(side="left", padx=4, pady=8)
        self.category_search.pack(side="left", padx=4, pady=8)
        self.category_search.bind("<<ComboboxSelected>>",
                                  self.on_category_search_bar_select)

    def on_archive_search_bar_return(self, value: str):
        splits = value.split(" || ")
        if len(splits) != 2:
            logger.critical("Something went wrong with the archive search \
                    autocomplete.", stack_info=True)
            return
        archive_file = os.path.join(self.app_state.game_data_path, splits[1])
        self.load_archive(initialdir="", archive_file=archive_file)

    def on_category_search_bar_select(self, event):
        if self.name_lookup == None:
            logger.critical("Audio archive database connection is None after \
                    bypassing all check.", stack_info=True)
            return
        category: str = self.category_search.get()
        self.archive_search.language = category
        soundbanks = self.name_lookup.query_soundbanks(language=category)
        entries: dict[str, LookupResult] = {
                bank.id: bank
                for bank in soundbanks}
        self.archive_search.set_entries(entries)
        self.archive_search.focus_set()
        self.category_search.selection_clear()
        
    def targeted_import(self, targets):
        if os.path.exists(WWISE_CLI):
            available_filetypes = [("Audio Files", " ".join(SUPPORTED_AUDIO_TYPES))]
        else:
            available_filetypes = [("Wwise Vorbis", "*.wem")]
        filename = askopenfilename(title="Select audio file to import", filetypes=available_filetypes)
        if not filename or not os.path.exists(filename):
            return
        file_dict = {filename: targets}
        self.import_files(file_dict)
        
    def remove_game_archive(self, archive_name):
        self.mod_handler.get_active_mod().remove_game_archive(archive_name)
        if self.selected_view.get() == "SourceView":
            self.create_source_view()
        else:
            self.create_hierarchy_view()
        

    def treeview_on_right_click(self, event):
        try:
            self.right_click_menu.delete(0, "end")

            selects = self.treeview.selection()
            is_single = len(selects) == 1

            all_audio = True
            for select in selects:
                values = self.treeview.item(select, option="values")
                assert(len(values) == 1)
                if values[0] != "Audio Source":
                    all_audio = False
                    break

            self.right_click_menu.add_command(
                label=("Copy File ID" if is_single else "Copy File IDs"),
                command=self.copy_id
            )
            if is_single and self.treeview.item(self.treeview.selection()[0], option="values")[0] == "Archive File":
                self.right_click_menu.add_command(
                    label="Remove Archive",
                    command=lambda: self.remove_game_archive(self.treeview.item(self.treeview.selection()[0], option="tags")[0])
                )

            if all_audio:
                self.right_click_menu.add_command(
                    label="Import audio",
                    command=lambda: self.targeted_import(targets=[int(self.treeview.item(select, option="tags")[0]) for select in selects])
                )

                tags = self.treeview.item(selects[-1], option="tags")
                assert(len(tags) == 1)
                self.right_click_id = int(tags[0])
                
                self.right_click_menu.add_command(
                    label=("Dump As .wem" if is_single else "Dump Selected As .wem"),
                    command=self.dump_as_wem
                )
                if os.path.exists(VGMSTREAM):
                    self.right_click_menu.add_command(
                        label=("Dump As .wav" if is_single else "Dump Selected As .wav"),
                        command=self.dump_as_wav,
                    )
                    self.right_click_menu.add_command(
                        label="Dump As .wav with Sequence Number",
                        command=lambda: self.dump_as_wav(with_seq=True)
                    )
                self.right_click_menu.add_command(
                    label="Dump muted .wav with same ID",
                    command=lambda: self.dump_as_wav(muted=True)
                )
                self.right_click_menu.add_command(
                    label="Dump muted .wav with same ID and sequence number",
                    command=lambda: self.dump_as_wav(muted=True, with_seq=True)
                )
            self.right_click_menu.tk_popup(event.x_root, event.y_root)
        except (AttributeError, IndexError):
            pass
        finally:
            self.right_click_menu.grab_release()

    def treeview_on_double_click(self, event):
        """
        It work as before but it's setup for playing multiple selected .wem 
        files I'm planning to implement. For now, it will be overhead since 
        there's extra code need to be loaded into the memory and interpreted.
        """
        # Rewrite this part against the doc how to use .item(). Provide better 
        # LSP type hinting
        selects = self.treeview.selection() 
        for select in selects:
            values = self.treeview.item(select, option="values")
            tags = self.treeview.item(select, option="tags")
            assert(len(values) == 1 and len(tags) == 1)
            if values[0] != "Audio Source":
                continue
            self.play_audio(int(tags[0]))

    def set_language(self):
        global language
        old_language = language
        language = language_lookup(self.selected_language.get())
        if language != old_language:
            if self.selected_view.get() == "SourceView":
                self.create_source_view()
            else:
                self.create_hierarchy_view()
    
    def search_down(self):
        if len(self.search_results) > 0:
            self.search_result_index += 1
            if self.search_result_index == len(self.search_results):
                self.search_result_index = 0
            self.treeview.selection_set(self.search_results[self.search_result_index])
            self.treeview.see(self.search_results[self.search_result_index])
            self.search_label['text'] = f"{self.search_result_index+1}/{len(self.search_results)}"

    def search_up(self):
        if len(self.search_results) > 0:
            self.search_result_index -= 1
            if self.search_result_index == -1:
                self.search_result_index = len(self.search_results)-1
            self.treeview.selection_set(self.search_results[self.search_result_index])
            self.treeview.see(self.search_results[self.search_result_index])
            self.search_label['text'] = f"{self.search_result_index+1}/{len(self.search_results)}"

    def show_info_window(self, event=None):
        if len(self.treeview.selection()) != 1:
            return
        selection_type = self.treeview.item(self.treeview.selection(), option="values")[0]
        if selection_type == "Archive File":
            return
        selection_id = int(self.treeview.item(self.treeview.selection(), option="tags")[0])
        item = self.treeview.selection()[0]
        while self.treeview.parent(self.treeview.parent(item)):
            item = self.treeview.parent(item)
        bank_id = int(self.treeview.item(item, option="tags")[0])
        for child in self.entry_info_panel.winfo_children():
            child.forget()
        if selection_type == "String":
            self.string_info_panel.set_string_entry(self.mod_handler.get_active_mod().get_string_entry(bank_id, selection_id))
            self.string_info_panel.frame.pack()
        elif selection_type == "Audio Source":
            self.audio_info_panel.set_audio(self.mod_handler.get_active_mod().get_audio_source(selection_id))
            self.audio_info_panel.frame.pack()
        elif selection_type == "Event":
            self.event_info_panel.set_track_info(self.mod_handler.get_active_mod().get_hierarchy_entry(bank_id, selection_id))
            self.event_info_panel.frame.pack()
        elif selection_type == "Music Segment":
            self.segment_info_panel.set_segment_info(self.mod_handler.get_active_mod().get_hierarchy_entry(bank_id, selection_id))
            self.segment_info_panel.frame.pack()
        elif selection_type == "Music Track":
            self.track_info_panel.set_track(self.mod_handler.get_active_mod().get_hierarchy_entry(bank_id, selection_id))
            self.track_info_panel.frame.pack()
        elif selection_type == "Sound Bank":
            pass
        elif selection_type == "Text Bank":
            pass

    def copy_id(self):
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join([self.treeview.item(i, option="tags")[0] for i in self.treeview.selection()]))
        self.root.update()

    def dump_as_wem(self):
        if len(self.treeview.selection()) == 1:
            output_file = filedialog.asksaveasfile(mode='wb', title="Save As", initialfile=f"{self.right_click_id}.wem", defaultextension=".wem", filetypes=[("Wwise Audio", "*.wem")])
            if not output_file:
                return
            self.mod_handler.get_active_mod().dump_as_wem(self.right_click_id, output_file)
        else:
            output_folder = filedialog.askdirectory(title="Save As")
            if not output_folder:
                return
            self.mod_handler.get_active_mod().dump_multiple_as_wem([int(self.treeview.item(i, option="tags")[0]) for i in self.treeview.selection()], output_folder)

    def dump_as_wav(self, muted: bool = False, with_seq: int = False):
        if len(self.treeview.selection()) == 1:
            output_file = filedialog.asksaveasfilename(
                title="Save As", 
                initialfile=f"{self.right_click_id}.wav", 
                defaultextension=".wav", 
                filetypes=[("Wav Audio", "*.wav")]
            )
            if not output_file:
                return
            self.mod_handler.get_active_mod().dump_as_wav(self.right_click_id, output_file=output_file, muted=muted)
            return
        else:
            output_folder = filedialog.askdirectory(title="Save As")
            if not output_folder:
                return
            self.mod_handler.get_active_mod().dump_multiple_as_wav(
                [int(self.treeview.item(i, option="tags")[0]) for i in self.treeview.selection()],
                muted=muted,
                with_seq=with_seq,
                output_folder=output_folder
            )

    def create_treeview_entry(self, entry, parent_item=""): #if HircEntry, add id of parent bank to the tags
        if entry is None: return
        if isinstance(entry, GameArchive):
            tree_entry = self.treeview.insert(parent_item, END, tag=entry.name)
        else:
            tree_entry = self.treeview.insert(parent_item, END, tag=entry.get_id())
        if isinstance(entry, WwiseBank):
            bank = self.name_lookup.lookup_soundbank(str(entry.get_id()))
            if bank.language != "none":
                name = f"{bank.friendlyname} ({bank.language})"
            else:
                name = bank.friendlyname
            entry_type = "Sound Bank"
        elif isinstance(entry, TextBank):
            name = f"{entry.get_id()}.text"
            entry_type = "Text Bank"
        elif isinstance(entry, AudioSource):
            name = f"{entry.get_id()}.wem"
            entry_type = "Audio Source"
        elif isinstance(entry, TrackInfoStruct):
            name = f"Event {entry.get_id()}"
            entry_type = "Event"
        elif isinstance(entry, StringEntry):
            entry_type = "String"
            name = entry.get_text()[:20]
        elif isinstance(entry, MusicTrack):
            entry_type = "Music Track"
            name = f"Track {entry.get_id()}"
        elif isinstance(entry, MusicSegment):
            entry_type = "Music Segment"
            name = f"Segment {entry.get_id()}"
        elif isinstance(entry, RandomSequenceContainer):
            entry_type = "Random Sequence"
            name = f"Sequence {entry.get_id()}"
        elif isinstance(entry, GameArchive):
            name = entry.name
            entry_type = "Archive File"
            self.treeview.item(tree_entry, open=True)
        self.treeview.item(tree_entry, text=name)
        self.treeview.item(tree_entry, values=(entry_type,))
        return tree_entry
        
    def clear_search(self):
        self.search_result_index = 0
        self.search_results.clear()
        self.search_label['text'] = ""
        self.search_text_var.set("")
            
    def create_hierarchy_view(self):
        self.clear_search()
        self.treeview.delete(*self.treeview.get_children())
        bank_dict = self.mod_handler.get_active_mod().get_wwise_banks()
        game_archives = self.mod_handler.get_active_mod().get_game_archives()
        sequence_sources = set()
        for archive in game_archives.values():
            archive_entry = self.create_treeview_entry(archive)
            for bank in archive.wwise_banks.values():
                bank_entry = self.create_treeview_entry(bank, archive_entry)
                for hierarchy_entry in bank.hierarchy.entries.values():
                    if isinstance(hierarchy_entry, MusicSegment):
                        segment_entry = self.create_treeview_entry(hierarchy_entry, bank_entry)
                        for track_id in hierarchy_entry.tracks:
                            track = bank.hierarchy.entries[track_id]
                            track_entry = self.create_treeview_entry(track, segment_entry)
                            for source in track.sources:
                                if source.plugin_id == VORBIS:
                                    try:
                                        self.create_treeview_entry(self.mod_handler.get_active_mod().get_audio_source(source.source_id), track_entry)
                                    except:
                                        pass
                            for info in track.track_info:
                                if info.event_id != 0:
                                    self.create_treeview_entry(info, track_entry)
                    elif isinstance(hierarchy_entry, RandomSequenceContainer):
                        container_entry = self.create_treeview_entry(hierarchy_entry, bank_entry)
                        for s_id in hierarchy_entry.contents:
                            sound = bank.hierarchy.entries[s_id]
                            if len(sound.sources) > 0 and sound.sources[0].plugin_id == VORBIS:
                                sequence_sources.add(sound)
                                try:
                                    self.create_treeview_entry(self.mod_handler.get_active_mod().get_audio_source(sound.sources[0].source_id), container_entry)
                                except:
                                    pass
                for hierarchy_entry in bank.hierarchy.entries.values():
                    if isinstance(hierarchy_entry, Sound) and hierarchy_entry not in sequence_sources:
                        if hierarchy_entry.sources[0].plugin_id == VORBIS:
                            try:
                                self.create_treeview_entry(self.mod_handler.get_active_mod().get_audio_source(hierarchy_entry.sources[0].source_id), bank_entry)
                            except:
                                pass
            for text_bank in archive.text_banks.values():
                if text_bank.language == language:
                    bank_entry = self.create_treeview_entry(text_bank, archive_entry)
                    for string_entry in text_bank.entries.values():
                        self.create_treeview_entry(string_entry, bank_entry)
        self.check_modified()
                
    def create_source_view(self):
        self.clear_search()
        existing_sources = set()
        self.treeview.delete(*self.treeview.get_children())
        game_archives = self.mod_handler.get_active_mod().get_game_archives()
        for archive in game_archives.values():
            archive_entry = self.create_treeview_entry(archive)
            for bank in archive.wwise_banks.values():
                existing_sources.clear()
                bank_entry = self.create_treeview_entry(bank, archive_entry)
                for hierarchy_entry in bank.hierarchy.entries.values():
                    for source in hierarchy_entry.sources:
                        if source.plugin_id == VORBIS and source.source_id not in existing_sources:
                            existing_sources.add(source.source_id)
                            try:
                                self.create_treeview_entry(self.mod_handler.get_active_mod().get_audio_source(source.source_id), bank_entry)
                            except:
                                pass
            for text_bank in archive.text_banks.values():
                if text_bank.language == language:
                    bank_entry = self.create_treeview_entry(text_bank, archive_entry)
                    for string_entry in text_bank.entries.values():
                        self.create_treeview_entry(string_entry, bank_entry)
        self.check_modified()
                
    def recursive_match(self, search_text_var, item):
        if self.treeview.item(item, option="values")[0] == "String":
            string_entry = self.mod_handler.get_active_mod().get_string_entry(int(self.treeview.item(item, option="tags")[0]))
            match = search_text_var in string_entry.get_text()
        else:
            s = self.treeview.item(item, option="text")
            match = s.startswith(search_text_var) or s.endswith(search_text_var)
        children = self.treeview.get_children(item)
        if match: self.search_results.append(item)
        if len(children) > 0:
            for child in children:
                self.recursive_match(search_text_var, child)

    def search(self):
        self.search_results.clear()
        self.search_result_index = 0
        text = self.search_text_var.get()
        if text != "":
            for child in self.treeview.get_children():
                self.recursive_match(text, child)
            if len(self.search_results) > 0:
                self.treeview.selection_set(self.search_results[self.search_result_index])
                self.treeview.see(self.search_results[self.search_result_index])
                self.search_label['text'] = f"1/{len(self.search_results)}"
            else:
                self.search_label['text'] = "0/0"
        else:
            self.search_label['text'] = ""

    def update_recent_files(self, filepath):
        try:
            self.app_state.recent_files.remove(os.path.normpath(filepath))
        except ValueError:
            pass
        self.app_state.recent_files.append(os.path.normpath(filepath))
        if len(self.app_state.recent_files) > 5:
            self.app_state.recent_files.pop(0)
        self.recent_file_menu.delete(0, "end")
        for item in reversed(self.app_state.recent_files):
            item = os.path.normpath(item)
            self.recent_file_menu.add_command(
                label=item,
                command=partial(self.load_archive, "", item)
            )

    def update_language_menu(self):
        self.options_menu.delete(1, "end") #change to delete only the language select menu
        if len(self.mod_handler.get_active_mod().text_banks) > 0:
            self.language_menu.delete(0, "end")
            first = ""
            self.options_menu.add_cascade(label="Game text language", menu=self.language_menu)
            for name, lang_id in LANGUAGE_MAPPING.items():
                if first == "": first = name
                for text_bank in self.mod_handler.get_active_mod().text_banks.values():
                    if lang_id == text_bank.language:
                        self.language_menu.add_radiobutton(label=name, variable=self.selected_language, value=name, command=self.set_language)
                        break
            self.selected_language.set(first)

    def load_archive(self, initialdir: str | None = '', archive_file: str | None = ""):
        if not archive_file:
            archive_file = QFileDialog.getOpenFileName(None, "Select archive", str(initialdir), "All Files (*.*)")
            archive_file = archive_file[0]
        if not archive_file:
            return
        if ".patch" in archive_file:
            showwarning(title="Invalid archive", message="Cannot open patch files. Use Import Patch to apply a patch file's changes to the loaded archive(s)")
            return
        self.sound_handler.kill_sound()
        self.mod_handler.get_active_mod().load_archive_file(archive_file=archive_file)
        self.mod_view.refresh()
        
    def save_mod(self):
        output_folder = filedialog.askdirectory(title="Select location to save combined mod")
        if output_folder and os.path.exists(output_folder):
            self.sound_handler.kill_sound()
            self.mod_handler.get_active_mod().save(output_folder)
        
    def dump_all_as_wem(self):
        self.sound_handler.kill_sound()
        output_folder = filedialog.askdirectory(title="Select folder to save files to")
        if not output_folder:
            return
        self.mod_handler.get_active_mod().dump_all_as_wem(output_folder)
        
    def dump_all_as_wav(self):
        self.sound_handler.kill_sound()
        output_folder = filedialog.askdirectory(title="Select folder to save files to")
        if not output_folder:
            return
        self.mod_handler.get_active_mod().dump_all_as_wav(output_folder)
        
    def play_audio(self, file_id: int, callback=None):
        audio = self.mod_handler.get_active_mod().get_audio_source(file_id)
        self.sound_handler.play_audio(audio.get_short_id(), audio.get_data(), callback)
        
    def revert_audio(self, file_id):
        self.mod_handler.get_active_mod().revert_audio(file_id)
        
    def revert_all(self):
        self.sound_handler.kill_sound()
        self.mod_handler.get_active_mod().revert_all()
        
    def write_patch(self):
        self.sound_handler.kill_sound()
        output_folder = filedialog.askdirectory(title="Select folder to save files to")
        if not output_folder:
            return
        self.mod_handler.get_active_mod().write_patch(output_folder)
        
    def import_patch(self):
        self.sound_handler.kill_sound()
        archive_file = askopenfilename(title="Select patch file")
        if not archive_file:
            return
        self.mod_handler.get_active_mod().import_patch(archive_file)
            
def get_dark_mode_palette( app=None ):
    
    darkPalette = app.palette()
    darkPalette.setColor( QPalette.Window, QColor( 53, 53, 53 ) )
    darkPalette.setColor( QPalette.WindowText, Qt.white )
    darkPalette.setColor( QPalette.Disabled, QPalette.WindowText, QColor( 127, 127, 127 ) )
    darkPalette.setColor( QPalette.Base, QColor( 42, 42, 42 ) )
    darkPalette.setColor( QPalette.AlternateBase, QColor( 66, 66, 66 ) )
    darkPalette.setColor( QPalette.ToolTipBase, QColor( 53, 53, 53 ) )
    darkPalette.setColor( QPalette.ToolTipText, Qt.white )
    darkPalette.setColor( QPalette.Text, Qt.white )
    darkPalette.setColor( QPalette.Disabled, QPalette.Text, QColor( 127, 127, 127 ) )
    darkPalette.setColor( QPalette.Dark, QColor( 35, 35, 35 ) )
    darkPalette.setColor( QPalette.Shadow, QColor( 20, 20, 20 ) )
    darkPalette.setColor( QPalette.Button, QColor( 53, 53, 53 ) )
    darkPalette.setColor( QPalette.ButtonText, Qt.white )
    darkPalette.setColor( QPalette.Disabled, QPalette.ButtonText, QColor( 127, 127, 127 ) )
    darkPalette.setColor( QPalette.BrightText, Qt.red )
    darkPalette.setColor( QPalette.Link, QColor( 42, 130, 218 ) )
    darkPalette.setColor( QPalette.Highlight, QColor( 42, 130, 218 ) )
    darkPalette.setColor( QPalette.Disabled, QPalette.Highlight, QColor( 80, 80, 80 ) )
    darkPalette.setColor( QPalette.HighlightedText, Qt.white )
    darkPalette.setColor( QPalette.Disabled, QPalette.HighlightedText, QColor( 127, 127, 127 ), )
    
    return darkPalette

if __name__ == "__main__":
    random.seed()
    app_state: cfg.Config | None = cfg.load_config()
    if app_state == None:
        exit(1)

    GAME_FILE_LOCATION = app_state.game_data_path

    try:
        if not os.path.exists(CACHE):
            os.mkdir(CACHE, mode=0o777)
        if not os.path.exists(TMP):
            os.mkdir(TMP, mode=0o777)
    except Exception as e:
        showerror("Error when initiating application", 
                    "Failed to create application caching space")
        exit(1)
        
    if not os.path.exists(VGMSTREAM):
        logger.error("Cannot find vgmstream distribution! " \
                     f"Ensure the {os.path.dirname(VGMSTREAM)} folder is " \
                     "in the same folder as the executable")
        showwarning(title="Missing Plugin", message="Cannot find vgmstream distribution! " \
                    "Audio playback is disabled.")
                     
    if not os.path.exists(WWISE_CLI) and SYSTEM != "Linux":
        logger.warning("Wwise installation not found. WAV file import is disabled.")
        showwarning(title="Missing Plugin", message="Wwise installation not found. WAV file import is disabled.")
    
    if os.path.exists(WWISE_CLI) and not os.path.exists(DEFAULT_WWISE_PROJECT):
        process = subprocess.run([
            WWISE_CLI,
            "create-new-project",
            DEFAULT_WWISE_PROJECT,
            "--platform",
            "Windows",
            "--quiet",
        ])
        if process.returncode != 0:
            logger.error("Error creating Wwise project. Audio import restricted to .wem files only")
            showwarning(title="Wwise Error", message="Error creating Wwise project. Audio import restricted to .wem files only")
            WWISE_CLI = ""

    lookup_store: db.FriendlyNameLookup | None = None
    
    if not os.path.exists(GAME_FILE_LOCATION):
        showwarning(title="Missing Game Data", message="No folder selected for Helldivers data folder." \
            " Audio archive search is disabled.")
    elif os.path.exists("friendlynames.db"):
        try:
            lookup_store = db.FriendlyNameLookup("friendlynames.db")
        except Exception as err:
            logger.error("Failed to connect to audio archive database", 
                         stack_info=True)
            lookup_store = None
    else:
        file, _ = urllib.request.urlretrieve("https://api.github.com/repos/raidingforpants/helldivers_audio_db/releases/latest")
        with open(file) as f:
            data = json.loads(f.read())
            download_url = data["assets"][0]["browser_download_url"]
        urllib.request.urlretrieve(download_url, "friendlynames.db")
        if not os.path.exists("friendlynames.db"):
            logger.error("Failed to fetch audio database. Built-in audio archive search is disabled.")
            showwarning(title="Missing Plugin", message="Audio database not found. Audio archive search is disabled.")
        else:
            try:
                lookup_store = db.FriendlyNameLookup("friendlynames.db")
            except Exception as err:
                logger.error("Failed to connect to audio archive database", 
                             stack_info=True)
                lookup_store = None
        
    language = language_lookup("English (US)")
    
    if not os.path.exists(WORKSPACE_FOLDER):
        os.mkdir(WORKSPACE_FOLDER)
    
    app = QApplication([])
    app.setStyle("Fusion")
    app.setPalette(get_dark_mode_palette(app))
    
    window = MainWindow(app_state, lookup_store)
    
    window.show()
    
    app.exec()
    
    SoundHandler.get_instance().kill_sound()
    app_state.save_config()

    if os.path.exists(CACHE):
        shutil.rmtree(CACHE)
        
    if os.path.exists(TMP):
        shutil.rmtree(TMP)