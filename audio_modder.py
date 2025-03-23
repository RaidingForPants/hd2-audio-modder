import os
import subprocess
import struct
import tkinter
import shutil
import pathlib
import zipfile
import xml.etree.ElementTree as etree
import requests
import json
import logging
import queue
import random

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
import asyncio
import threading

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
from graph import *

from log import logger

WINDOW_WIDTH = 1480
WINDOW_HEIGHT = 848
VERSION = "1.17.0"
    
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
        
class ProgressFrame(Frame):
    
    DETERMINATE = 0
    INDETERMINATE = 1
    DONE = 2
    INDETERMINATE_AUTO = 3
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.progress_bar = ttk.Progressbar(self, orient=HORIZONTAL, length=300)
        self.text = ttk.Label(self, text="Done", font=('Segoe UI', 12))
        #self.progress_bar.grid(row=0, column=0)
        self.text.grid(row=0, column=0)
        
    def step(self):
        self.progress_bar.step()
        self.progress_bar.update_idletasks()
        
    def set_text(self, s):
        self.text.configure(text=s)
        
    def set_mode(self, max_progress = 0, mode = 0):
        if mode != self.INDETERMINATE_AUTO:
            self.progress_bar.stop()
        if mode == self.DONE:
            self.progress_bar.grid_forget()
            self.text.grid_forget()
            self.text.grid(row=0, column=0)
        else:
            self.text.grid_forget()
            self.progress_bar.grid(row=0, column=0)
            self.text.grid(row=0, column=1)
            if mode == self.INDETERMINATE:
                self.progress_bar.configure(mode="indeterminate")
            elif mode == self.DETERMINATE:
                self.progress_bar.configure(mode="determinate", maximum=max_progress)
            elif mode == self.INDETERMINATE_AUTO:
                self.progress_bar.configure(mode="indeterminate", maximum=20)
                self.progress_bar.start()
        
class VerticalScrolledFrame(ttk.Frame):
    """A pure Tkinter scrollable frame that actually works!
    * Use the 'interior' attribute to place widgets inside the scrollable frame.
    * Construct and pack/place/grid normally.
    * This frame only allows vertical scrolling.
    """
    def __init__(self, parent, *args, **kw):
        ttk.Frame.__init__(self, parent, *args, **kw)

        # Create a canvas object and a vertical scrollbar for scrolling it.
        vscrollbar = ttk.Scrollbar(self, orient=VERTICAL)
        vscrollbar.pack(fill=Y, side=RIGHT, expand=FALSE)
        canvas = Canvas(self, bd=0, highlightthickness=0,
                           yscrollcommand=vscrollbar.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=TRUE)
        vscrollbar.config(command=canvas.yview)

        # Reset the view
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

        # Create a frame inside the canvas which will be scrolled with it.
        self.interior = interior = ttk.Frame(canvas)
        interior_id = canvas.create_window(0, 0, window=interior,
                                           anchor=NW)

        # Track changes to the canvas and frame width and sync them,
        # also updating the scrollbar.
        def _configure_interior(event):
            # Update the scrollbars to match the size of the inner frame.
            size = (interior.winfo_reqwidth(), interior.winfo_reqheight())
            canvas.config(scrollregion="0 0 %s %s" % size)
            if interior.winfo_reqwidth() != canvas.winfo_width():
                # Update the canvas's width to fit the inner frame.
                canvas.config(width=interior.winfo_reqwidth())
        interior.bind('<Configure>', _configure_interior)

        def _configure_canvas(event):
            if interior.winfo_reqwidth() != canvas.winfo_width():
                # Update the inner frame's width to fill the canvas.
                canvas.itemconfigure(interior_id, width=canvas.winfo_width())
        canvas.bind('<Configure>', _configure_canvas)
        
class PendingFile(Frame):
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.filepath = ""
        self.button = ttk.Button(self, text="X", command=self.button_press)
        self.label = ttk.Label(self, text=self.filepath, font=('Segoe UI', 12),
                                      justify="center")
        self.button.pack(side="right", anchor="e")
        self.label.pack(side='left', expand=True, fill='x', anchor="w")
        
    def set_filepath(self, new_path):
        self.filepath = new_path
        self.label.config(text=new_path)
    
    def get_filepath(self):
        return self.filepath
    
    def button_press(self):
        self.destroy()

class FileUploadWindow:
    
    def __init__(self, parent, callback=None):
        self.root = Toplevel(parent)
        self.root.geometry("500x500")
        if os.path.exists("icon.ico"):
            self.root.iconbitmap("icon.ico")
        self.root.title("Select Mods to Combine")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.scrollframe = VerticalScrolledFrame(self.root)
        self.drop_frame = Frame(self.root, width=500, height=500, borderwidth=3, highlightbackground="gray", highlightthickness=2)
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.grid_columnconfigure(0, weight=1)
        self.drop_frame.grid_columnconfigure(1, weight=1)
        self.drop_frame.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=0)
        self.label = Label(self.drop_frame, text="Drop Files Here or ", font=('Segoe UI', 12), justify="right")
        self.label.grid(row=0, column=0, sticky="nse")
        self.drop_frame.grid(row=0, column=0, columnspan=2, sticky="news")
        self.drop_frame.dnd_bind("<<Drop>>", self.drop_add_files)
        self.upload_button = ttk.Button(self.drop_frame, text="Add file", command=self.add_files)
        self.accept_button = ttk.Button(self.root, text="Accept", command=self.return_files)
        self.accept_button.grid(row=2, column=0, sticky="w")
        self.cancel_button = ttk.Button(self.root, text="Cancel", command=self.on_close)
        self.cancel_button.grid(row=2, column=1, sticky="e")
        self.upload_button.grid(row=0, column=1, sticky="w")
        self.scrollframe.grid(row=1, column=0, columnspan=2, sticky="news")
        self.callback = callback
        
    def drop_add_files(self, event):
        if event.data:
            dropped_files = event.widget.tk.splitlist(event.data)
            dropped_files = [file for file in dropped_files if os.path.splitext(file)[1].lower() == ".zip" or ".patch_" in os.path.splitext(file)[1]]
            for file in dropped_files:
                pending_file = PendingFile(self.scrollframe.interior)
                pending_file.set_filepath(file)
                pending_file.pack(side="top", expand=True, fill="x", pady=2)
        
    def add_files(self):
        filenames = filedialog.askopenfilenames(parent=self.root, title="Choose mod files to combine", filetypes=[("Mod Files", "*.zip *.patch*")])
        for name in filenames:
            pending_file = PendingFile(self.scrollframe.interior)
            pending_file.set_filepath(name)
            pending_file.pack(side="top", expand=True, fill="x")
        
    def return_files(self):
        files = [file.get_filepath() for file in self.scrollframe.interior.winfo_children() if isinstance(file, PendingFile)]
        self.root.destroy()
        if self.callback is not None:
            self.callback(files)
        
        
    def on_close(self):
        self.root.destroy()
        if self.callback is not None:
            self.callback([])
    

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
            self.update_modified(diff=[self.string_entry])
    
    def revert(self):
        if self.string_entry is not None:
            self.string_entry.revert_modifications()
            self.text_box.delete("1.0", END)
            self.text_box.insert(END, self.string_entry.get_text())
            self.update_modified(diff=[self.string_entry])
            
class MusicTrackWindow:
    
    def __init__(self, parent, update_modified, play):
        self.frame = Frame(parent)
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_columnconfigure(1, weight=1)
        self.frame.grid_rowconfigure(10, weight=1)
        self.button_container = Frame(self.frame)
        self.listbox_container = Frame(self.frame)
        self.listbox_scrollbar = ttk.Scrollbar(self.listbox_container, orient=VERTICAL)
        self.graph_notebook = ttk.Notebook(self.frame)
        self.graphs = []
        self.selected_track = 0
        self.update_modified = update_modified
        self.play = play
        self.fake_image = tkinter.PhotoImage(width=1, height=1)
        self.title_label = ttk.Label(self.frame, font=('Segoe UI', 14), width=50, anchor="center")
        self.revert_button = ttk.Button(self.button_container, text='\u21b6', image=self.fake_image, compound='c', width=2, command=self.revert)
        self.play_button = ttk.Button(self.button_container, text="\u23f5", image=self.fake_image, compound="c", width=2, command=self.play_audio)
        self.play_at_text_var = tkinter.StringVar(self.frame)
        self.duration_text_var = tkinter.StringVar(self.frame)
        self.start_offset_text_var = tkinter.StringVar(self.frame)
        self.end_offset_text_var = tkinter.StringVar(self.frame)
        self.source_selection_listbox = tkinter.Listbox(self.listbox_container, exportselection=False)
        self.source_selection_listbox.bind("<<ListboxSelect>>", self.set_track_info)
        self.source_selection_listbox.config(width=50)
        self.source_selection_listbox.config(height=4)
        self.source_selection_listbox.configure(yscrollcommand=self.listbox_scrollbar.set)
        self.listbox_scrollbar['command'] = self.source_selection_listbox.yview
        
        self.play_at_label = ttk.Label(self.frame,
                                   text="Play At (ms)",
                                   font=('Segoe UI', 12),
                                   anchor="center")
        self.play_at_text = ttk.Entry(self.frame, textvariable=self.play_at_text_var, font=('Segoe UI', 12), width=25)
        
        
        self.duration_label = ttk.Label(self.frame,
                                    text="Duration (ms)",
                                    font=('Segoe UI', 12),
                                    anchor="center")
        self.duration_text = ttk.Entry(self.frame, textvariable=self.duration_text_var, font=('Segoe UI', 12), width=25)
        
        
        self.start_offset_label = ttk.Label(self.frame,
                                        text="Start Trim (ms)",
                                        font=('Segoe UI', 12),
                                        anchor="center")
        self.start_offset_text = ttk.Entry(self.frame, textvariable=self.start_offset_text_var, font=('Segoe UI', 12), width=25)
        
        
        self.end_offset_label = ttk.Label(self.frame,
                                      text="End Trim (ms)",
                                      font=('Segoe UI', 12),
                                      anchor="center")
        self.end_offset_text = ttk.Entry(self.frame, textvariable=self.end_offset_text_var, font=('Segoe UI', 12), width=25)

        self.apply_button = ttk.Button(self.button_container, text="Apply", command=self.apply_changes)
        
        self.title_label.grid(row=0, column=0, pady=2, columnspan=2, sticky="news")
        
        self.button_container.grid(row=9, column=0, sticky="w", pady=2)
        self.revert_button.pack(side="left")
        self.apply_button.pack(side="left")
        
        #self.title_label.pack(pady=5)
        
        #self.graph_notebook.pack(side="bottom")
        self.graph_notebook.grid(row=10, column=0, sticky="news", pady=2, columnspan=2)
        self.listbox_container.grid(row=1, column=0, columnspan=2, pady=2, sticky="news")
        
        #self.graph = Graph(self.frame)
        
    def play_audio(self):
        selection = self.source_selection_listbox.get(self.source_selection_listbox.curselection()[0])
        id = selection.split(" ")[1]
        selection = int(id)
        for t in self.track.track_info:
            if t.source_id == selection or murmur64_hash(f"content/audio/{t.source_id}".encode("utf-8")) == selection:
                self.play(selection)
                break
        
    def set_track_info(self, event=None, selection=0):
        if not selection:
            try:
                selection = self.source_selection_listbox.get(self.source_selection_listbox.curselection()[0])
            except:
                return
        if selection.split(" ")[0] == "Audio":
            self.play_button.pack(side="left")
        else:
            self.play_button.pack_forget()
        id = selection.split(" ")[1]
        selection = int(id)
        for t in self.track.track_info:
            if t.source_id == selection or murmur64_hash(f"content/audio/{t.source_id}".encode("utf-8")) == selection or t.event_id == selection:
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
        
        self.play_at_label.grid(row=5, column=0, sticky="news")
        self.play_at_text.grid(row=6, column=0, sticky="news")
        self.duration_label.grid(row=5, column=1, sticky="news")
        self.duration_text.grid(row=6, column=1, sticky="news")
        self.start_offset_label.grid(row=7, column=0, sticky="news")
        self.start_offset_text.grid(row=8, column=0, sticky="news")
        self.end_offset_label.grid(row=7, column=1, sticky="news")
        self.end_offset_text.grid(row=8, column=1, sticky="news")
        
        #if len(self.track.clip_automations) == 1:
        #    self.graph.pack(side="top")
        
        
        
    def set_track(self, track):
        self.title_label.configure(text=f"Info for Track {track.get_id()}")
        self.track = track
        self.source_selection_listbox.delete(0, 'end')
        for track_info_struct in self.track.track_info:
            if track_info_struct.source_id != 0:
                resource_id = murmur64_hash(f"content/audio/{track_info_struct.source_id}".encode("utf-8"))
                self.source_selection_listbox.insert(END, f"Audio {resource_id}")
            else:
                self.source_selection_listbox.insert(END, f"Event {track_info_struct.event_id}")
        
        
        
        if len(track.track_info) > 0:
            self.source_selection_listbox.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)
            self.set_track_info(selection=self.source_selection_listbox.get(0))
            self.source_selection_listbox.select_set(0)
        if len(track.track_info) > 4:
            self.listbox_scrollbar.pack(side="right", fill='y')
        else:
            self.listbox_scrollbar.pack_forget()
            
        self.graphs.clear()
        
        for child in self.graph_notebook.winfo_children():
            child.destroy()
            
        
        info = [x for x in self.track.track_info if x.source_id != 0]
        
        for i in range(len(track.clip_automations)):
            x = [point[0] for point in track.clip_automations[i].graph_points]
            y = [point[1] for point in track.clip_automations[i].graph_points]
            g = Graph(self.graph_notebook)
            self.graphs.append(g)

            g.set_data(x, y)
            source_id = info[self.track.clip_automations[i].clip_index].source_id
            source = next(x for x in self.track.sources if x.source_id == source_id)
            if source.stream_type == BANK:
                pass
            else:
                source_id = murmur64_hash(f"content/audio/{source_id}".encode("utf-8"))
            if track.clip_automations[i].auto_type == 0: #VOLUME
                g.set_xlabel("time (s)")
                g.set_ylabel("dB")
                g.set_title(f"Volume for Audio {source_id}")
            elif track.clip_automations[i].auto_type == 3: #FADE-IN
                g.set_xlabel("time (s)")
                g.set_ylabel("dB")
                g.set_title(f"Fade-In for Audio {source_id}")
            elif track.clip_automations[i].auto_type == 4: #FADE-OUT
                g.set_xlabel("time (s)")
                g.set_ylabel("dB")
                g.set_title(f"Fade-Out for Audio {source_id}")
            else:
                g.set_xlabel("")
                g.set_ylabel("")
                g.set_title(f"Unknown Graph")
            self.graph_notebook.add(g, text=f"RTPC {i+1}")
            
    def revert(self):
        self.track.revert_modifications()
        self.set_track(self.track)
        self.update_modified(diff=[self.track])
        
    def apply_changes(self):
        tracks = copy.deepcopy(self.track.track_info)
        for t in tracks:
            if (t.source_id != 0 and t.source_id == self.selected_track.source_id) or (t.event_id !=0 and t.event_id == self.selected_track.event_id):
                t.begin_trim_offset = float(self.start_offset_text_var.get())
                t.end_trim_offset = float(self.end_offset_text_var.get())
                t.source_duration = float(self.duration_text_var.get())
                t.play_at = float(self.play_at_text_var.get())
                break
        clip_automations = copy.deepcopy(self.track.clip_automations)
        for index, tab in enumerate(self.graph_notebook.tabs()):
            graph = self.graph_notebook.nametowidget(tab)
            x, y = graph.get_data()
            clip_automations[index].num_graph_points = len(x)
            clip_automations[index].graph_points = [(x[i], y[i], 4) for i in range(len(x))] #linear interpolation = 0x04
        self.track.set_data(track_info=tracks, clip_automations=clip_automations)
        self.update_modified(diff=[self.track])
        
        
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
        self.update_modified([self.audio])
        self.play_original_label.forget()
        self.play_original_button.forget()
        
    def apply_changes(self):
        self.track_info.set_data(play_at=float(self.play_at_text_var.get()), begin_trim_offset=float(self.start_offset_text_var.get()), end_trim_offset=float(self.end_offset_text_var.get()), source_duration=float(self.duration_text_var.get()))
        self.update_modified([self.audio])
        
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
        self.update_modified([self.segment])
        
    def apply_changes(self):
        self.segment.set_data(duration=float(self.duration_text_var.get()), entry_marker=float(self.fade_in_text_var.get()), exit_marker=float(self.fade_out_text_var.get()))
        self.update_modified([self.segment])
 
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
        
class TaskItem:
    
    def __init__(self, thread, name):
        self.thread = thread
        self.name = name
        
    def get_thread(self):
        return self.thread
        
    def get_name(self):
        return self.name
        
class TaskManager:
    
    def __init__(self):
        self.async_event_loop = EventLoop()
        self.async_task_queue = queue.Queue()
        self.sync_task_queue = queue.Queue()
        self.sync_thread_running = False
        self.sync_thread = None
        self.progress_frame = None
        
    def schedule(self, name, callback, task, *args, **kwargs):
        task = self.sync_wrapper(task, callback)
        t = threading.Thread(target=task, args=args, kwargs=kwargs)
        item = TaskItem(t, name)
        if self.sync_thread_running:
            self.sync_task_queue.put(item)
        else:
            self.start_task(item)
            
    def schedule_in_new_thread(self, name, callback, task, *args, **kwargs):
        task = self.sync_wrapper(task, callback)
        t = threading.Thread(target=task, args=args, kwargs=kwargs)
        t.start()
            
    def start_task(self, task_item):
        assert not self.sync_thread_running, "Tried to start new sync task with task already running!"
        self.sync_thread_running = True
        self.sync_thread = task_item.get_thread()
        self.start_progress_frame()
        self.set_progress_frame_text(task_item.get_name())
        self.sync_thread.start()
            
    def set_progress_frame(self, frame):
        self.progress_frame = frame
        
    def set_progress_frame_text(self, text):
        if self.progress_frame is not None:
            self.progress_frame.set_text(text)
            
    def start_progress_frame(self):
        if self.progress_frame is not None:
            self.progress_frame.set_mode(mode=ProgressFrame.INDETERMINATE_AUTO)
            
    def stop_progress_frame(self):
        if self.progress_frame is not None:
            self.progress_frame.set_mode(mode=ProgressFrame.DONE)
            self.progress_frame.set_text("Done")
        
    def schedule_async(self, name, callback, task, *args, **kwargs):
        callback = self.async_wrapper(callback)
        self.async_event_loop.start_task(callback, task, *args, **kwargs)
    
    def async_wrapper(self, callback):
        if callback is not None:
            def wrapper(future):
                try:
                    callback(*future.result())
                finally:
                    self.async_task_finished(future)
        else:
            def wrapper(future):
                self.async_task_finished(future)
        return wrapper
        
    def sync_wrapper(self, task, callback):
        if callback is not None:
            def wrapper(*args, **kwargs):
                try:
                    result = task(*args, **kwargs)
                    callback(*result)
                finally:
                    self.sync_task_finished()
        else:
            def wrapper(*args, **kwargs):
                try:
                    task(*args, **kwargs)
                finally:
                    self.sync_task_finished()
        return wrapper
        
    def async_task_finished(self, future):
        pass
        
    def sync_task_finished(self):
        self.sync_thread_running = False
        if not self.sync_task_queue.empty():
            task_item = self.sync_task_queue.get()
            self.start_task(task_item)
        else:
            self.sync_thread = None
            self.stop_progress_frame()
    
class EventLoop:
    
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_asyncio_loop, args=(self.loop,), daemon=True)
        self.thread.start()
    
    def start_task(self, callback, coroutine, *args, **kwargs):
        task = asyncio.run_coroutine_threadsafe(coroutine(*args, **kwargs), self.loop)
        task.add_done_callback(callback)
    
    def run_asyncio_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()
    
    def get_loop(self):
        return self.loop
        
def task(func):
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if not type(result) is tuple:
            result = (result,)
        return result
    return wrapper
    
def async_task(func):
    async def wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)
        if not type(result) is tuple:
            result = (result,)
        return result
    return wrapper

def callback(callback):
    def wrapper(*args, **kwargs):
        args[0].root.after_idle(callback, *args, **kwargs)
    return wrapper

class MainWindow:

    dark_mode_bg = "#333333"
    dark_mode_fg = "#ffffff"
    dark_mode_modified_bg = "#ffffff"
    dark_mode_modified_fg = "#333333"
    light_mode_bg = "#ffffff"
    light_mode_fg = "#000000"
    light_mode_modified_bg = "#7CFC00"
    light_mode_modified_fg = "#000000"

    def __init__(self, 
                 app_state: cfg.Config, 
                 lookup_store: db.LookupStore | None):
        self.app_state = app_state
        self.name_lookup = lookup_store
        self.sound_handler = SoundHandler.get_instance()
        self.watched_paths = []
        self.mod_handler = ModHandler.get_instance(lookup_store)
        self.mod_handler.create_new_mod("default")
        
        self.task_manager = TaskManager()
        self.active_task_ids = []
        
        self.root = TkinterDnD.Tk()
        if os.path.exists("icon.ico"):
            self.root.iconbitmap("icon.ico")
        
        self.drag_source_widget = None
        self.workspace_selection = []
        
        self.file_upload_window = None
        
        try:
            self.root.tk.call("source", "azure.tcl")
        except Exception as e:
            logger.critical("Error occurred when loading themes:")
            logger.critical(e)
            logger.critical("Ensure azure.tcl and the themes folder are in the same folder as the executable")

        self.fake_image = tkinter.PhotoImage(width=1, height=1)

        self.top_bar = Frame(self.root, width=WINDOW_WIDTH, height=40)
        self.search_text_var = tkinter.StringVar(self.root)
        self.search_bar = ttk.Entry(self.top_bar, textvariable=self.search_text_var, font=('Segoe UI', 14))
        self.top_bar.pack(side="top", fill='x')
        if lookup_store != None and os.path.exists(GAME_FILE_LOCATION):
            self.init_archive_search_bar()

        self.up_button = ttk.Button(self.top_bar, text='\u25b2',
                                    width=2, command=self.search_up)
        self.down_button = ttk.Button(self.top_bar, text='\u25bc',
                                      width=2, command=self.search_down)

        self.search_label = ttk.Label(self.top_bar,
                                      width=10,
                                      font=('Segoe UI', 14),
                                      justify="center")

        self.search_icon = ttk.Label(self.top_bar, font=('Arial', 20), text="\u2315")

        self.search_label.pack(side="right", padx=1)
        self.search_bar.pack(side="right", padx=1)
        self.down_button.pack(side="right")
        self.up_button.pack(side="right")
        self.search_icon.pack(side="right", padx=4)

        self.default_bg = "#333333"
        self.default_fg = "#ffffff"
        
        self.window = PanedWindow(self.root, orient=HORIZONTAL, borderwidth=0, background="white")
        self.window.config(sashwidth=8, sashrelief="raised", opaqueresize=False)
        
        self.top_bar.pack(side="top", fill='x')
        
        self.progress_frame = ProgressFrame(self.root)
        self.progress_frame.pack(side="bottom", fill='x')
        
        self.window.pack(fill=BOTH)
        
        self.search_results = []
        self.search_result_index = 0

        self.init_workspace()
        
        self.treeview_panel = Frame(self.window)
        self.scroll_bar = ttk.Scrollbar(self.treeview_panel, orient=VERTICAL)
        self.treeview = ttk.Treeview(self.treeview_panel, columns=("type",), height=WINDOW_HEIGHT-100)
        self.scroll_bar.pack(side="right", pady=8, fill="y", padx=(0, 10))
        self.treeview.pack(side="right", padx=8, pady=8, fill="x", expand=True)
        self.treeview.heading("#0", text="File")
        self.treeview.column("#0", width=250)
        self.treeview.column("type", width=100)
        self.treeview.heading("type", text="Type")
        self.treeview.configure(yscrollcommand=self.scroll_bar.set)
        self.treeview.bind("<<TreeviewSelect>>", self.show_info_window)
        self.treeview.bind("<Double-Button-1>", self.treeview_on_double_click)
        self.treeview.bind("<Return>", self.treeview_on_double_click)
        self.scroll_bar['command'] = self.treeview.yview

        self.entry_info_panel = Frame(self.window, width=int(WINDOW_WIDTH/3))
        self.entry_info_panel.pack(side="left", fill="both", padx=8, pady=8)
        
        self.audio_info_panel = AudioSourceWindow(self.entry_info_panel,
                                                  self.play_audio,
                                                  self.check_modified)
        self.event_info_panel = EventWindow(self.entry_info_panel,
                                            self.check_modified)
        self.string_info_panel = StringEntryWindow(self.entry_info_panel,
                                                   self.check_modified)
        self.segment_info_panel = MusicSegmentWindow(self.entry_info_panel,
                                                     self.check_modified)
                                                     
        self.track_info_panel = MusicTrackWindow(self.entry_info_panel, self.check_modified, self.play_audio)
                                                     
        self.window.add(self.treeview_panel)
        self.window.add(self.entry_info_panel)
        
        self.root.title(f"Helldivers 2 Audio Modder {VERSION}")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        
        self.right_click_menu = Menu(self.treeview, tearoff=0)
        self.right_click_id = 0

        self.menu = Menu(self.root, tearoff=0)
        
        self.selected_view = StringVar()
        self.selected_view.set("SourceView")
        self.view_menu = Menu(self.menu, tearoff=0)
        self.view_menu.add_radiobutton(label="Sources", variable=self.selected_view, value="SourceView", command=self.create_source_view)
        self.view_menu.add_radiobutton(label="Hierarchy", variable=self.selected_view, value="HierarchyView", command=self.create_hierarchy_view)
        
        self.selected_language = StringVar()
        self.options_menu = Menu(self.menu, tearoff=0)
        
        self.selected_theme = StringVar()
        self.selected_theme.set(self.app_state.theme)
        self.set_theme()
        self.theme_menu = Menu(self.menu, tearoff=0)
        self.theme_menu.add_radiobutton(label="Dark Mode", variable=self.selected_theme, value="dark_mode", command=self.set_theme)
        self.theme_menu.add_radiobutton(label="Light Mode", variable=self.selected_theme, value="light_mode", command=self.set_theme)
        self.options_menu.add_cascade(menu=self.theme_menu, label="Set Theme")
        
        self.language_menu = Menu(self.options_menu, tearoff=0)
        
        self.file_menu = Menu(self.menu, tearoff=0)

        self.recent_file_menu = Menu(self.file_menu, tearoff=0)

        self.load_archive_menu = Menu(self.menu, tearoff=0)
        if os.path.exists(GAME_FILE_LOCATION):
            self.load_archive_menu.add_command(
                label="From HD2 Data Folder",
                command=lambda: self.load_archive(initialdir=self.app_state.game_data_path)
            )
        self.load_archive_menu.add_command(
            label="From File Explorer",
            command=self.load_archive
        )

        for item in reversed(self.app_state.recent_files):
            item = os.path.normpath(item)
            self.recent_file_menu.add_command(
                label=item,
                command=partial(self.load_archive, "", item)
            )

        self.import_menu = Menu(self.menu, tearoff=0)
        self.import_menu.add_command(
            label="Import Patch File",
            command=self.import_patch
        )
        self.import_menu.add_command(
            label="Import Audio Files",
            command=self.import_audio_files
        )
            
        self.file_menu.add_cascade(
            menu=self.load_archive_menu, 
            label="Open"
        )
        self.file_menu.add_cascade(
            menu=self.recent_file_menu,
            label="Open Recent"
        )
        self.file_menu.add_cascade(
            menu=self.import_menu,
            label="Import"
        )
        
        if self.name_lookup is not None and os.path.exists(self.app_state.game_data_path):
            self.file_menu.add_command(label="Combine Mods", command=self.combine_mods)
        
        self.file_menu.add_command(label="Save", command=self.save_mod)
        self.file_menu.add_command(label="Write Patch", command=self.write_patch)
        
        self.file_menu.add_command(label="Add a Folder to Workspace",
                                   command=self.add_new_workspace)
        
        self.edit_menu = Menu(self.menu, tearoff=0)
        self.edit_menu.add_command(label="Revert All Changes", command=self.revert_all)
        
        self.dump_menu = Menu(self.menu, tearoff=0)
        if os.path.exists(VGMSTREAM):
            self.dump_menu.add_command(label="Dump all as .wav", command=self.dump_all_as_wav)
        self.dump_menu.add_command(label="Dump all as .wem", command=self.dump_all_as_wem)
        
        self.menu.add_cascade(label="File", menu=self.file_menu)
        self.menu.add_cascade(label="Edit", menu=self.edit_menu)
        self.menu.add_cascade(label="Dump", menu=self.dump_menu)
        self.menu.add_cascade(label="View", menu=self.view_menu)
        self.menu.add_cascade(label="Options", menu=self.options_menu)
        self.root.config(menu=self.menu)
        
        self.treeview.drop_target_register(DND_FILES)
        self.workspace.drop_target_register(DND_FILES)
        self.workspace.drag_source_register(1, DND_FILES)

        self.treeview.bind("<Button-3>", self.treeview_on_right_click)
        self.workspace.bind("<Button-3>", self.workspace_on_right_click)
        self.workspace.bind("<Double-Button-1>", self.workspace_on_double_click)
        self.search_bar.bind("<Return>", self.search_bar_on_enter_key)
        self.treeview.dnd_bind("<<Drop>>", self.drop_import)
        self.treeview.dnd_bind("<<DropPosition>>", self.drop_position)
        self.workspace.dnd_bind("<<Drop>>", self.drop_add_to_workspace)
        self.workspace.dnd_bind("<<DragInitCmd>>", self.drag_init_workspace)
        self.workspace.bind("<B1-Motion>", self.workspace_drag_assist)
        self.workspace.bind("<Button-1>", self.workspace_save_selection)
        
        self.task_manager.set_progress_frame(self.progress_frame)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.root.resizable(True, True)
        #async_mainloop(self.root)
        self.root.mainloop()
        
    def on_close(self):
        self.root.destroy()
        
    def drop_position(self, event):
        if event.data:
            if len(event.widget.tk.splitlist(event.data)) != 1:
                return
        self.treeview.selection_set(event.widget.identify_row(event.y_root - self.treeview.winfo_rooty()))

    def workspace_drag_assist(self, event):
        selected_item = self.workspace.identify_row(event.y)
        if selected_item in self.workspace_selection:
            self.workspace.selection_set(self.workspace_selection)

    def workspace_save_selection(self, event):
        self.workspace_selection = self.workspace.selection()
        
    def generate_task_id(self):
        while True:
            id = random.randint(0, 2**64-1)
            if id not in self.active_task_ids:
                break
        return id
        
    def combine_mods(self):
        if not os.path.exists(self.app_state.game_data_path):
            showerror(title="Missing Required Configuration", message="Unknown game data folder location. Unable to automatically combine mods")
            return
        if self.file_upload_window is None:
            self.sound_handler.kill_sound()
            self.file_upload_window = FileUploadWindow(self.root, callback=self.combine_mods_callback)
            
    def combine_mods_callback(self, files):
        self.file_upload_window = None
        if len(files) == 1:
            tkinter.messagebox.showinfo("You cannot combine only 1 mod!")
        elif len(files) > 1:
            current_mod = self.mod_handler.get_active_mod()
            combined_mod = self.mod_handler.create_new_mod("combined_mods_temp")
            self.mod_handler.set_active_mod(current_mod.name)
            self.task_manager.schedule(name="Processing Input Files", callback=self.combine_mods_soundbank_lookup, task=self.combine_mods_task, files=files, mod=combined_mod)

    @task
    def combine_mods_task(self, files, mod):
        zip_files = [file for file in files if os.path.splitext(file)[1].lower() == ".zip"]
        patch_files = [file for file in files if ".patch_" in os.path.basename(file)]
        
        for index, mod_file in enumerate(zip_files):
            zip = zipfile.ZipFile(mod_file)
            extract_location = os.path.join(CACHE, str(index))
            os.mkdir(extract_location)
            zip.extractall(path=extract_location)
            patch_files.extend([os.path.join(extract_location, file) for file in os.listdir(extract_location) if os.path.isfile(os.path.join(extract_location, file)) and "patch" in os.path.splitext(file)[1]])
        missing_soundbank_ids = []
        archives = set()
        for index, file in enumerate(patch_files):
            new_archive = GameArchive.from_file(file)
            if len(new_archive.text_banks) > 0:
                archives.add("9ba626afa44a3aa3")
            missing_soundbank_ids.extend([soundbank_id for soundbank_id in new_archive.get_wwise_banks().keys()])
        return patch_files, archives, missing_soundbank_ids, mod

    @callback
    def combine_mods_soundbank_lookup(self, files, archives, missing_soundbank_ids, mod):
        for soundbank_id in missing_soundbank_ids:
            r = self.name_lookup.lookup_soundbank(soundbank_id)
            if r.success:
                archives.add(r.archive)
            else:
                showerror(title="", message="Unable to complete automated mod merging; please merge manually.")
                return
        for archive in archives:
            archive = os.path.join(self.app_state.game_data_path, archive)
            self.task_manager.schedule(name=f"Loading Archive {os.path.basename(archive)}", callback=None, task=task(mod.load_archive_file), archive_file=archive)
        for file in files:
            self.task_manager.schedule(name=f"Applying Patch {file}", callback=None, task=task(mod.import_patch), patch_file=file)
        self.task_manager.schedule(name="Saving Output File", callback=None, task=self.combine_mods_write_output, mod=mod)
        
    @task    
    def combine_mods_write_output(self, mod):
        output_file = filedialog.asksaveasfilename(title="Save combined mod", filetypes=[("Zip Archive", "*.zip")], initialfile="combined_mod.zip")
        if output_file:
            mod.write_patch(CACHE)
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
        #self.mod_handler.set_active_mod(current_mod.name)
        
        for file in os.listdir(CACHE):
            file = os.path.join(CACHE, file)
            try:
                if os.path.isfile(file):
                    os.remove(file)
                elif os.path.isdir(file):
                    shutil.rmtree(file)
            except:
                pass
        
    def combine_mods_cleanup(self):
        pass

    def drop_import(self, event):
        self.drag_source_widget = None
        renamed = False
        old_name = ""
        if event.data:
            import_files = []
            dropped_files = event.widget.tk.splitlist(event.data)
            for file in dropped_files:
                import_files.extend(list_files_recursive(file))
            patch_files = [file for file in import_files if ".patch_" in os.path.basename(file)]
            for file in patch_files:
                self.import_patch(file)
            if os.path.exists(WWISE_CLI):
                import_files = [file for file in import_files if os.path.splitext(file)[1] in SUPPORTED_AUDIO_TYPES]
            else:
                import_files = [file for file in import_files if os.path.splitext(file)[1] == ".wem"]
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

    def drop_add_to_workspace(self, event):
        if self.drag_source_widget is not self.workspace and event.data:
            dropped_files = event.widget.tk.splitlist(event.data)
            for file in dropped_files:
                if os.path.isdir(file):
                    self.add_new_workspace(file)
        self.drag_source_widget = None

    def drag_init_workspace(self, event):
        self.drag_source_widget = self.workspace
        data = ()
        if self.workspace.selection():
            data = tuple([self.workspace.item(i, option="values")[0] for i in self.workspace.selection()])
        return ((ASK, COPY), (DND_FILES,), data)

    def search_bar_on_enter_key(self, event):
        self.search()
        
    def set_theme(self):
        theme = self.selected_theme.get()
        try:
            if theme == "dark_mode":
                self.root.tk.call("set_theme", "dark")
                graphs_set_dark_mode()
                self.window.configure(background="white")
                self.treeview.tag_configure("modified", background=MainWindow.dark_mode_modified_bg, foreground=MainWindow.dark_mode_modified_fg)
            elif theme == "light_mode":
                self.root.tk.call("set_theme", "light")
                graphs_set_light_mode()
                self.window.configure(background="black")
                self.treeview.tag_configure("modified", background=MainWindow.light_mode_modified_bg, foreground=MainWindow.light_mode_modified_fg)
            
        except Exception as e:
            logger.error(f"Error occurred when loading themes: {e}. Ensure azure.tcl and the themes folder are in the same folder as the executable")
        self.app_state.theme = theme
        self.workspace.column("#0", width=256+16)
        self.treeview.column("#0", width=250)
        self.treeview.column("type", width=100)
        #self.check_modified()

    def render_workspace(self):
        """
        TO-DO: This should be fine grained diffing instead of tearing the entire
        thing down despite Tkinter already perform some type of rendering and
        display optimization behind the scene.
        """
        self.workspace_inodes.clear()

        for p in sorted(self.app_state.get_workspace_paths()):
            inode = fileutil.generate_file_tree(p)
            if inode != None:
                self.workspace_inodes.append(inode)

        for c in self.workspace.get_children():
            self.workspace.delete(c)

        for root_inode in self.workspace_inodes:
            root_id = self.workspace.insert("", "end", 
                                            text=root_inode.basename,
                                            values=[root_inode.absolute_path],
                                            tags="workspace")
            inode_stack = [root_inode]
            id_stack = [root_id]
            while len(inode_stack) > 0:
                top_inode = inode_stack.pop()
                top_id = id_stack.pop()
                for node in top_inode.nodes:
                    id = self.workspace.insert(top_id, "end", 
                                               text=node.basename,
                                               values=[node.absolute_path],
                                               tags="dir" if node.isdir else "file")
                    if node.isdir:
                        inode_stack.append(node)
                        id_stack.append(id)

    def add_new_workspace(self, workspace_path=""):
        if workspace_path == "":
            workspace_path = filedialog.askdirectory(
                mustexist=True,
                title="Select a folder to open as workspace"
            )
        if self.app_state.add_new_workspace(workspace_path) == 1:
            return
        inode = fileutil.generate_file_tree(workspace_path)
        if inode == None:
            return
        self.workspace_inodes.append(inode)
        idx = sorted(self.app_state.get_workspace_paths()).index(workspace_path)
        root_id = self.workspace.insert("", idx,
                                            text=inode.basename,
                                            values=[inode.absolute_path],
                                            tags="workspace")
        inode_stack = [inode]
        id_stack = [root_id]
        while len(inode_stack) > 0:
            top_inode = inode_stack.pop()
            top_id = id_stack.pop()
            for node in top_inode.nodes:
                id = self.workspace.insert(top_id, "end",
                                           text=node.basename,
                                           values=[node.absolute_path],
                                           tags="dir" if node.isdir else "file")
                if node.isdir:
                    inode_stack.append(node)
                    id_stack.append(id)
                    
        # I'm too lazy so I'm just going to unschedule and then reschedule all the watches
        # instead of locating all subfolders and then figuring out which ones to not schedule
        self.reload_watched_paths()
            
    def reload_watched_paths(self):
        for p in self.watched_paths:
            self.observer.unschedule(p)
        self.watched_paths = []
        # only track top-most folder if subfolders are added:
        # sort by number of levels
        paths = [pathlib.Path(p) for p in self.app_state.get_workspace_paths()]
        paths = sorted(paths, key=cmp_to_key(lambda item1, item2: len(item1.parents) - len(item2.parents)))

        # skip adding a folder if a parent folder has already been added
        trimmed_paths = []
        for p in paths:
            add = True
            for item in trimmed_paths:
                if item in p.parents:
                    add = False
                    break
            if add:
                trimmed_paths.append(p)
                
        for path in trimmed_paths:
            self.watched_paths.append(self.observer.schedule(self.event_handler, path, recursive=True))

    def remove_workspace(self, workspace_item):
        values = self.workspace.item(workspace_item, option="values")
        self.app_state.workspace_paths.remove(values[0])
        self.workspace.delete(workspace_item)

        # I'm too lazy so I'm just going to unschedule and then reschedule all the watches
        # instead of locating all subfolders and then figuring out which ones to not schedule
        self.reload_watched_paths()

    def workspace_on_right_click(self, event):
        self.workspace_popup_menu.delete(0, "end")
        selects: tuple[str, ...] = self.workspace.selection()
        if len(selects) == 0:
            return
        if len(selects) == 1:
            select = selects[0]
            tags = self.workspace.item(select, option="tags")
            assert(tags != '' and len(tags) == 1)
            if tags[0] == "workspace":
                values = self.workspace.item(select, option="values")
                assert(values != '' and len(values) == 1)
                self.workspace_popup_menu.add_command(
                    label="Remove Folder from Workspace",
                    command=lambda: self.remove_workspace(select),
                )
                self.workspace_popup_menu.tk_popup(
                    event.x_root, event.y_root
                )
                self.workspace_popup_menu.grab_release()
                return
            elif tags[0] == "dir":
                return
        file_dict = {self.workspace.item(i, option="values")[0]: [get_number_prefix(os.path.basename(self.workspace.item(i, option="values")[0]))] for i in selects if self.workspace.item(i, option="tags")[0] == "file"} 
        self.workspace_popup_menu.add_command(
            label="Import", 
            command=lambda: self.import_files(file_dict)
        )
        self.workspace_popup_menu.tk_popup(event.x_root, event.y_root)
        self.workspace_popup_menu.grab_release()
        
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
        self.task_manager.schedule(name="Importing Files", callback=self.import_files_callback, task=self.import_files_task, file_dict=file_dict)
        
    @task
    def import_files_task(self, file_dict):
        try:
            self.mod_handler.get_active_mod().import_files(file_dict)
        except Exception as e:
            self.progress_frame.set_mode(mode=ProgressFrame.DONE)
            self.progress_frame.set_text("Done")
            showwarning(title="Import Error", message=f"Error occurred during file import: {str(e)} Some imports may have been skipped.")
        return file_dict
    
    @callback
    def import_files_callback(self, file_dict):
        # use file dict for diffing? not sure how this would work with patch files
        self.check_modified()
        self.show_info_window()

    def init_workspace(self):
        self.workspace_panel = Frame(self.window)
        self.window.add(self.workspace_panel)
        self.workspace = ttk.Treeview(self.workspace_panel, height=WINDOW_HEIGHT - 100)
        self.workspace.heading("#0", text="Workspace Folders")
        self.workspace.column("#0", width=256+16)
        self.workspace_scroll_bar = ttk.Scrollbar(self.workspace_panel, orient=VERTICAL)
        self.workspace_scroll_bar['command'] = self.workspace.yview
        self.workspace_scroll_bar.pack(side="right", pady=8, fill="y", padx=(0, 10))
        self.workspace.pack(side="right", padx=8, pady=8, fill="x", expand=True)
        self.workspace_inodes: list[fileutil.INode] = []
        self.workspace_popup_menu = Menu(self.workspace, tearoff=0)
        self.workspace.configure(yscrollcommand=self.workspace_scroll_bar.set)
        self.render_workspace()
        self.event_handler = WorkspaceEventHandler(self.workspace)
        self.observer = Observer()
        self.reload_watched_paths()
        self.observer.start()

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
            if values[0] != "Audio Source":
                continue
            self.play_audio(int(tags[0]))

    def workspace_on_double_click(self, event):
        selects = self.workspace.selection()
        if len(selects) == 1:
            select = selects[0]
            values = self.workspace.item(select, option="values")
            tags = self.workspace.item(select, option="tags")
            assert(len(values) == 1 and len(tags) == 1)
            if tags[0] == "file" and os.path.splitext(values[0])[1] in SUPPORTED_AUDIO_TYPES and os.path.exists(values[0]):
                audio_data = None
                with open(values[0], "rb") as f:
                    audio_data = f.read()
                self.sound_handler.play_audio(os.path.basename(os.path.splitext(values[0])[0]), audio_data)

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
            child.pack_forget()
        if selection_type == "String":
            self.string_info_panel.set_string_entry(self.mod_handler.get_active_mod().get_string_entry(bank_id, selection_id))
            self.string_info_panel.frame.pack(side="top", fill="x", padx=8, pady=8)
        elif selection_type == "Audio Source":
            self.audio_info_panel.set_audio(self.mod_handler.get_active_mod().get_audio_source(selection_id))
            self.audio_info_panel.frame.pack(side="top", fill="x", padx=8, pady=8)
        elif selection_type == "Event":
            self.event_info_panel.set_track_info(self.mod_handler.get_active_mod().get_hierarchy_entry(selection_id))
            self.event_info_panel.frame.pack(side="top", fill="x", padx=8, pady=8)
        elif selection_type == "Music Segment":
            self.segment_info_panel.set_segment_info(self.mod_handler.get_active_mod().get_hierarchy_entry(selection_id))
            self.segment_info_panel.frame.pack(side="top", fill="x", padx=8, pady=8)
        elif selection_type == "Music Track":
            self.track_info_panel.set_track(self.mod_handler.get_active_mod().get_hierarchy_entry(selection_id))
            self.track_info_panel.frame.pack(side="top", fill="x", padx=8, pady=8)
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
            output_file = filedialog.asksaveasfilename(title="Save As", initialfile=f"{self.right_click_id}.wem", defaultextension=".wem", filetypes=[("Wwise Audio", "*.wem")])
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
            self.mod_handler.get_active_mod().dump_as_wav(self.right_click_id, output_file=output_file, muted=False)
        else:
            output_folder = filedialog.askdirectory(title="Save To")
            if not output_folder:
                return
            file_ids = [int(self.treeview.item(i, option="tags")[0]) for i in self.treeview.selection()]
            task_id = self.generate_task_id()
            self.active_task_ids.append(task_id)
            task_folder = os.path.join(output_folder, f"dump_{task_id}")
            os.mkdir(task_folder)
            self.task_manager.schedule(name="Dumping Files", callback=None, task=self.dump_as_wav_setup_task, task_id=task_id, file_ids=file_ids, output_location=task_folder)
    
    @task
    def dump_as_wav_setup_task(self, task_id, file_ids, output_location):
        self.mod_handler.get_active_mod().create_dummy_bank(file_ids, os.path.join(output_location, "temp.bnk"))
        self.task_manager.schedule_async(name="Dumping Files", callback=self.dump_as_wav_finished, task=self.dump_as_wav_task, file_ids=file_ids, output_folder=output_location, bank_filepath=os.path.join(output_location, "temp.bnk"), task_id=task_id)
            
    @async_task 
    async def dump_as_wav_task(self, file_ids, output_folder, bank_filepath, task_id):
        await self.mod_handler.get_active_mod().dump_from_bank_file(output_folder=output_folder, bank_filepath=bank_filepath)
        os.remove(bank_filepath)
        for audio_source in [self.mod_handler.get_active_mod().get_audio_source(source_id) for source_id in file_ids]:
            if audio_source.get_resource_id() != 0:
                os.rename(os.path.join(output_folder, f"{audio_source.get_short_id()}.wav"), os.path.join(output_folder, f"{audio_source.get_resource_id()}.wav"))

        return task_id

    @callback
    def dump_as_wav_finished(self, task_id):
        self.active_task_ids.remove(task_id)
        
    def create_treeview_entry(self, entry, parent_item=""): #if HircEntry, add id of parent bank to the tags
        if entry is None: return
        if isinstance(entry, GameArchive):
            tree_entry = self.treeview.insert(parent_item, END, tag=entry.name)
        else:
            if isinstance(entry, StringEntry):
                tree_entry = self.treeview.insert(parent_item, END, tags=(entry.get_id(), entry.parent.get_id()))
            else:
                tree_entry = self.treeview.insert(parent_item, END, tag=entry.get_id())
            if entry.modified or (isinstance(entry, HircEntry) and entry.has_modified_children()): 
                self.mark_modified(entry, tree_entry)
        if isinstance(entry, WwiseBank):
            if self.name_lookup is not None:
                bank = self.name_lookup.lookup_soundbank(str(entry.get_id()))
                if not bank.success:
                    name = entry.dep.data
                elif bank.language != "none":
                    name = f"{bank.friendlyname} ({bank.language})"
                else:
                    name = bank.friendlyname
            else:
                name = entry.dep.data
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
            
    def create_hierarchy_view(self, new_game_archive=None):
        self.clear_search()
        sequence_sources = set()
        if new_game_archive is not None:
            archive_list = [new_game_archive]
        else:
            game_archives = self.mod_handler.get_active_mod().get_game_archives()
            self.treeview.delete(*self.treeview.get_children())
            archive_list = game_archives.values()
        for archive in archive_list:
            archive_entry = self.create_treeview_entry(archive)
            for bank in archive.wwise_banks.values():
                sequence_sources.clear()
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
                    elif isinstance(hierarchy_entry, RandomSequenceContainer):
                        container_entry = self.create_treeview_entry(hierarchy_entry, bank_entry)
                        for s_id in hierarchy_entry.containerChildren.children:
                            sound = bank.hierarchy.entries[s_id]
                            if not isinstance(sound, Sound):
                                continue
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
                
    def create_source_view(self, new_game_archive=None):
        self.clear_search()
        existing_sources = set()
        if new_game_archive is not None:
            archive_list = [new_game_archive]
        else:
            self.treeview.delete(*self.treeview.get_children())
            game_archives = self.mod_handler.get_active_mod().get_game_archives()
            archive_list = game_archives.values()
        for archive in archive_list:
            archive_entry = self.create_treeview_entry(archive)
            for bank in archive.wwise_banks.values():
                existing_sources.clear()
                bank_entry = self.create_treeview_entry(bank, archive_entry)
                for hierarchy_entry in bank.hierarchy.get_sounds() + bank.hierarchy.get_music_tracks():
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
                
    def recursive_match(self, search_text_var, item):
        if self.treeview.item(item, option="values")[0] == "String":
            string_entry = self.mod_handler.get_active_mod().get_string_entry(textbank_id=int(self.treeview.item(item, option="tags")[1]), entry_id=int(self.treeview.item(item, option="tags")[0]))
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
        self.sound_handler.kill_sound()
        if not archive_file:
            archive_file = askopenfilename(title="Select archive", initialdir=initialdir)
        if not archive_file:
            return
        if ".patch" in os.path.basename(archive_file):
            self.import_patch(archive_file)
            return
        self.task_manager.schedule(name=f"Loading Archive {os.path.basename(archive_file)}", callback=self.load_archive_task_finished, task=self.load_archive_task, archive_files=[archive_file])
    
    @task
    def load_archive_task(self, archive_files: str | None = ""):
        results = []
        for archive_file in archive_files:
            results.append((self.mod_handler.get_active_mod().load_archive_file(archive_file=archive_file), archive_file))
        return results
    
    @callback
    def load_archive_task_finished(self, results):
        new_game_archives = []
        for result in results:
            success = result[0]
            archive_file = result[1]
            if success:
                self.update_recent_files(filepath=archive_file)
                archive = self.mod_handler.get_active_mod().get_game_archive(os.path.splitext(os.path.basename(archive_file))[0])
                new_game_archives.append(archive)
        for archive in new_game_archives:
            if self.selected_view.get() == "SourceView":
                self.create_source_view(new_game_archive=archive)
            else:
                self.create_hierarchy_view(new_game_archive=archive)
        if len(new_game_archives) > 0:
            self.clear_search()
            self.update_language_menu()
            for child in self.entry_info_panel.winfo_children():
                child.forget()

    def save_mod(self):
        output_folder = filedialog.askdirectory(title="Select location to save combined mod")
        if output_folder and os.path.exists(output_folder):
            self.sound_handler.kill_sound()
            self.mod_handler.get_active_mod().save(output_folder)
        
    """
    TO-DO:
    optimization point: small, but noticeable lag if there are many, many 
    entries in the tree
    """
    
    def clear_modified(self):
        modified_items = self.treeview.tag_has("modified")
        for item in modified_items:
            tags = self.treeview.item(item, option="tags")
            tags = list(tags)
            tags.remove("modified")
            self.treeview.item(item, tags=tags)
    
    def mark_modified(self, entry, item=None):
        if isinstance(entry, HircEntry):
            modified = entry.modified or entry.has_modified_children()
        else:
            modified = entry.modified
        if item is None:
            if isinstance(entry, AudioSource):
                i = self.treeview.tag_has(entry.get_short_id())
                if len(i) == 0:
                    return
                i = i[0]
            else:
                i = self.treeview.tag_has(entry.get_id())
                if len(i) == 0:
                    return
                i = i[0]
        else:
            i = item
        tags = self.treeview.item(i, option="tags")
        if modified:
            if "modified" not in tags:
                tags = tags + ("modified",)
        else:
            if "modified" in tags:
                tags = list(tags)
                tags.remove("modified")
        self.treeview.item(i, tags=tags)
        
    def get_all_treeview_items(self, tree, item=""):
        children = tree.get_children(item)
        for child in children:
            children += self.get_all_treeview_items(tree, child)
        return children

    def check_modified(self, diff = None):
        if diff is not None:
            for item in diff:
                self.mark_modified(item)
                parents = []
                if isinstance(item, HircEntry):
                    parents = [item.parent] if item.parent is not None else item.soundbanks
                elif isinstance(item, AudioSource):
                    parents = item.parents
                elif isinstance(item, WwiseBank):
                    parents = []
                elif isinstance(item, StringEntry):
                    parents = [item.parent]
                elif isinstance(item, TextBank):
                    parents = []
                self.check_modified(parents)
        else:
            for item in self.get_all_treeview_items(self.treeview):
                item_type = self.treeview.item(item, option="values")[0]
                if item_type == "Archive File":
                    continue
                elif item_type == "Sound Bank":
                    try:
                        bank = self.mod_handler.get_active_mod().get_wwise_bank(int(self.treeview.item(item, option="tags")[0]))
                    except:
                        continue
                    self.mark_modified(bank, item)
                elif item_type == "Text Bank":
                    bank = self.mod_handler.get_active_mod().get_text_bank(int(self.treeview.item(item, option="tags")[0]))
                    self.mark_modified(bank, item)
                elif item_type == "Audio Source":
                    source = self.mod_handler.get_active_mod().get_audio_source(int(self.treeview.item(item, option="tags")[0]))
                    self.mark_modified(source, item)
                elif item_type == "String":
                    tags = self.treeview.item(item, option="tags")
                    string_entry = self.mod_handler.get_active_mod().get_string_entry(int(tags[1]), int(tags[0]))
                    self.mark_modified(string_entry, item)
                else: #HircEntry
                    entry = self.mod_handler.get_active_mod().get_hierarchy_entry(int(self.treeview.item(item, option="tags")[0]))
                    self.mark_modified(entry, item)
        
    def dump_all_as_wem(self):
        self.sound_handler.kill_sound()
        output_folder = filedialog.askdirectory(title="Select folder to save files to")
        if not output_folder:
            return
        self.task_manager.schedule(name="Dumping Files", callback=None, task=task(self.mod_handler.get_active_mod().dump_all_as_wem), output_folder=output_folder)
        
    def dump_all_as_wav(self):
        self.sound_handler.kill_sound()
        output_folder = filedialog.askdirectory(title="Select folder to save files to")
        if not output_folder:
            return
        #1. queue tasks for creating each dummy bank
        #2. schedule tasks to dump each dummy bank
        for bank in self.mod_handler.get_active_mod().get_wwise_banks().values():
            bank_folder = os.path.join(output_folder, bank.dep.data.replace("\x00", "").split("/")[-1])
            os.mkdir(bank_folder)
            file_ids = [audio_source.get_short_id() for audio_source in bank.get_content()]
            task_id = self.generate_task_id()
            self.active_task_ids.append(task_id)
            self.task_manager.schedule(name="Initializing File Dump", callback=None, task=self.dump_as_wav_setup_task, task_id=task_id, file_ids=file_ids, output_location=bank_folder)
        
    def play_audio(self, file_id: int, callback=None):
        audio = self.mod_handler.get_active_mod().get_audio_source(file_id)
        self.sound_handler.play_audio(audio.get_short_id(), audio.get_data(), callback)
        
    def revert_audio(self, file_id):
        self.mod_handler.get_active_mod().revert_audio(file_id)
        
    def revert_all(self):
        self.sound_handler.kill_sound()
        self.mod_handler.get_active_mod().revert_all()
        self.clear_modified()
        self.show_info_window()
        
    def write_patch(self):
        self.sound_handler.kill_sound()
        output_folder = filedialog.askdirectory(title="Select folder to save files to")
        if not output_folder:
            return
        self.task_manager.schedule(name="Saving Patch File", callback=None, task=task(self.mod_handler.get_active_mod().write_patch), output_folder=output_folder)
        
    def import_patch(self, archive_file: str = ""):
        self.sound_handler.kill_sound()
        if archive_file == "":
            archive_file = askopenfilename(title="Select patch file", filetypes=[("Patch File", "*.patch_*")])
        if not archive_file:
            return
        if os.path.splitext(archive_file)[1] in (".stream", ".gpu_resources"):
            archive_file = os.path.splitext(archive_file)[0]
        self.task_manager.schedule(name="Processing Patch Contents", callback=self.import_patch_soundbank_lookup, task=self.import_patch_task, archive_file=archive_file)
    
    @task
    def import_patch_task(self, archive_file: str = ""):
        new_archive = GameArchive.from_file(archive_file)
        missing_soundbank_ids = [soundbank_id for soundbank_id in new_archive.get_wwise_banks().keys() if soundbank_id not in self.mod_handler.get_active_mod().get_wwise_banks()]
        return missing_soundbank_ids, new_archive, archive_file
    
    @callback
    def import_patch_soundbank_lookup(self, missing_soundbank_ids, new_archive, patch_file):
        archives = set()
        if len(new_archive.text_banks) > 0 and "9ba626afa44a3aa3" not in self.mod_handler.get_active_mod().get_game_archives().keys():
            archives.add("9ba626afa44a3aa3")
        if self.name_lookup is not None and os.path.exists(self.app_state.game_data_path):
            for soundbank_id in missing_soundbank_ids:
                r = self.name_lookup.lookup_soundbank(soundbank_id)
                if r.success:
                    archives.add(r.archive)
        for archive in archives:
            archive = os.path.join(self.app_state.game_data_path, archive)
            self.task_manager.schedule(name=f"Loading Archive {os.path.basename(archive)}", callback=self.import_patch_load_archive_finished, task=self.load_archive_task, archive_files=[archive])
        self.task_manager.schedule(name="Applying Patch", callback=self.import_patch_finished, task=task(self.mod_handler.get_active_mod().import_patch), patch_file=patch_file)
        
    @callback
    def import_patch_load_archive_finished(self, results):
        new_game_archives = []
        for result in results:
            success = result[0]
            archive_file = result[1]
            if success:
                archive = self.mod_handler.get_active_mod().get_game_archive(os.path.splitext(os.path.basename(archive_file))[0])
                new_game_archives.append(archive)
        for archive in new_game_archives:
            if self.selected_view.get() == "SourceView":
                self.create_source_view(new_game_archive=archive)
            else:
                self.create_hierarchy_view(new_game_archive=archive)
        if "9ba626afa44a3aa3" in [archive.name for archive in new_game_archives]:
            self.update_language_menu()

    @callback
    def import_patch_finished(self, success):
        self.check_modified()
        self.show_info_window()

if __name__ == "__main__":
    logger.setLevel(logging.INFO)
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
        logger.warning("Wwise installation not found. The only file type available for import is WEM.")
        showwarning(title="Missing Plugin", message="Wwise installation not found. The only file type available for import is WEM.")
    
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
    try:
        if os.path.exists(FRIENDLYNAMES_DB):
            current_version = db.get_db_version(FRIENDLYNAMES_DB)
        else:
            current_version = -1
        r = requests.get("https://api.github.com/repos/raidingforpants/helldivers_audio_db/releases/latest")
        if r.status_code != 200:
            raise Exception("Error fetching latest database")
        data = r.json()
        download_url = data["assets"][0]["browser_download_url"]
        latest_version = int(float(data["tag_name"].replace("v", "")))
        if current_version < latest_version:
            r = requests.get(download_url)
            if r.status_code != 200:
                raise Exception("Error fetching latest database")
            with open(FRIENDLYNAMES_DB, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        print(e)
        
    try:
        if not (getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')):
            raise Exception("Automatic updates not supported for python script")
        r = requests.get("https://api.github.com/repos/raidingforpants/hd2-audio-modder/releases/latest")
        if r.status_code != 200:
            raise Exception("Error fetching update info")
        data = r.json()
        if SYSTEM == "Darwin":
            download_url = data["assets"][1]["browser_download_url"]
            updater = "updater"
        elif SYSTEM == "Windows":
            download_url = data["assets"][2]["browser_download_url"]
            updater = "updater.exe"
        elif SYSTEM == "Linux":
            download_url = data["assets"][0]["browser_download_url"]
            updater = "updater"
        latest_version = [int(i) for i in data["tag_name"].replace("v", "").split(".")]
        current_version = [int(i) for i in VERSION.split(".")]
        while len(latest_version) < 3:
            latest_version.append(0)
        update_available = False
        if latest_version[0] > current_version[0]:
            update_available = True
        elif latest_version[0] == current_version[0] and latest_version[1] > current_version[1]:
            update_available = True
        elif latest_version[0] == current_version[0] and latest_version[1] == current_version[1] and latest_version[2] > current_version[2]:
            update_available = True
        if update_available:
            response = askyesnocancel(title="Update", message=f"A new version is available ({data['tag_name'].replace('v', '')}). Would you like to install it?")
            if response:
                subprocess.Popen(
                    [
                        updater,
                        download_url,
                        str(os.getpid())
                    ],
                    creationflags=subprocess.DETACHED_PROCESS
                )
                sys.exit()
    except Exception as e:
        print(e)

    if os.path.exists(FRIENDLYNAMES_DB):
        try:
            lookup_store = db.FriendlyNameLookup(FRIENDLYNAMES_DB)
        except Exception as err:
            logger.error("Failed to connect to audio archive database", 
                         stack_info=True)
            lookup_store = None
    else:
        lookup_store = None
        
    language = language_lookup("English (US)")
    window = MainWindow(app_state, lookup_store)
    
    SoundHandler.get_instance().kill_sound()
    app_state.save_config()

    if os.path.exists(CACHE):
        shutil.rmtree(CACHE)
        
    if os.path.exists(TMP):
        shutil.rmtree(TMP)
