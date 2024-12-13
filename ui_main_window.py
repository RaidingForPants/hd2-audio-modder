import os
import pathlib
import subprocess

from functools import partial, cmp_to_key

import tkinter
from tkinter import Frame, Menu, PanedWindow, StringVar
from tkinter import BOTH, END, HORIZONTAL, VERTICAL
from tkinter import filedialog
from tkinter import ttk
from tkinterdnd2 import TkinterDnD
from tkinterdnd2 import ASK, COPY, DND_FILES
from typing import Any, Union
from watchdog.observers import Observer

import config as cfg
import db
import fileutil

from const_global import language, language_lookup, LANGUAGE_MAPPING
from const_global import CACHE, GAME_FILE_LOCATION, VGMSTREAM, WWISE_CLI, VORBIS

from game_asset_entity import AudioSource, MusicSegment, MusicTrack, StringEntry, \
        Sound, TextBank, TrackInfoStruct, WwiseBank
from fileutil import list_files_recursive
from log import logger

from ui_archive_search import ArchiveSearch
from ui_controller_file import FileHandler
from ui_controller_sound import SoundHandler
from ui_controller_workspace import WorkspaceEventHandler
from ui_window_component import AudioSourceWindow, EventWindow, \
        StringEntryWindow, MusicSegmentWindow


WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720


class MainWindow:

    dark_mode_bg = "#333333"
    dark_mode_fg = "#ffffff"
    dark_mode_modified_bg = "#ffffff"
    dark_mode_modified_fg = "#333333"
    light_mode_bg = "#ffffff"
    light_mode_fg = "#000000"
    light_mode_modified_bg = "#7CFC00"
    light_mode_modified_fg = "#000000"

    ENTRY_TYPE_AUDIO_SOURCE = "Audio Source"
    ENTRY_TYPE_EVENT = "Event"
    ENTRY_TYPE_MUSIC_SEGMENT = "Music Segment"
    ENTRY_TYPE_MUSIC_TRACK = "Music Track"
    ENTRY_TYPE_SOUND_BANK = "Sound Bank"
    ENTRY_TYPE_STRING = "String"
    ENTRY_TYPE_TEXT_BANK = "Text Bank"
    ENTRY_TYPE_UNKNONW = "Unknonw"

    type TreeViewEntry = Union[
        AudioSource,
        MusicSegment,
        MusicTrack,
        StringEntry,
        TextBank,
        TrackInfoStruct,
        WwiseBank
    ] 

    def __init__(self, 
                 app_state: cfg.Config, 
                 lookup_store: db.LookupStore | None,
                 file_handler: FileHandler,
                 sound_handler: SoundHandler):
        self.app_state = app_state
        self.lookup_store = lookup_store
        self.file_handler = file_handler
        self.sound_handler = sound_handler
        self.watched_paths = []
        
        self.root = TkinterDnD.Tk()
        
        self.drag_source_widget = None
        self.workspace_selection = []
        
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
        if lookup_store != None and os.path.exists(GAME_FILE_LOCATION()):
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
        self.window.config(sashwidth=8, sashrelief="raised")
        self.window.pack(fill=BOTH)

        
        self.top_bar.pack(side="top")
        
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
                                                     
        self.window.add(self.treeview_panel)
        self.window.add(self.entry_info_panel)
        
        self.root.title("Helldivers 2 Audio Modder")
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
        if os.path.exists(GAME_FILE_LOCATION()):
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
            command=self.load_patch
        )
        self.import_menu.add_command(
            label="Import Audio Files",
            command=self.import_audio_files
        )
        self.import_menu.add_command(
            label="Import using spec.json (.wem)",
            command=lambda: self.file_handler.load_wems_spec() or 
                self.check_modified()
        )
        if os.path.exists(WWISE_CLI):
            self.import_menu.add_command(
                label="Import using spec.json (.wav)",
                command=lambda: self.file_handler.load_convert_spec() or 
                    self.check_modified()
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
        
        self.file_menu.add_command(label="Save", command=self.save_archive)
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
        self.workspace.dnd_bind("<<Drop>>", self.drop_add_to_workspace)
        self.workspace.dnd_bind("<<DragInitCmd>>", self.drag_init_workspace)

        self.workspace.bind("<B1-Motion>", self.workspace_drag_assist)
        self.workspace.bind("<Button-1>", self.workspace_save_selection)

        self.root.resizable(True, True)
        self.root.mainloop()

    def workspace_drag_assist(self, event):
        selected_item = self.workspace.identify_row(event.y)
        if selected_item in self.workspace_selection:
            self.workspace.selection_set(self.workspace_selection)

    def workspace_save_selection(self, _):
        self.workspace_selection = self.workspace.selection()

    def drop_import(self, event):
        if event.data:
            import_files = []
            dropped_files = event.widget.tk.splitlist(event.data)
            for file in dropped_files:
                import_files.extend(list_files_recursive(file))
            self.import_files(import_files)
        self.drag_source_widget = None

    def drop_add_to_workspace(self, event):
        if self.drag_source_widget is not self.workspace and event.data:
            dropped_files = event.widget.tk.splitlist(event.data)
            for file in dropped_files:
                if os.path.isdir(file):
                    self.add_new_workspace(file)
        self.drag_source_widget = None

    def drag_init_workspace(self, _):
        self.drag_source_widget = self.workspace
        data = ()
        if self.workspace.selection():
            data = tuple([self.workspace.item(i, option="values")[0] for i in self.workspace.selection()])
        return ((ASK, COPY), (DND_FILES,), data)

    def search_bar_on_enter_key(self, _):
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
        if theme == "light_mode":
            if modified:
                return (MainWindow.light_mode_modified_bg, MainWindow.light_mode_modified_fg)
            else:
                return (MainWindow.light_mode_bg, MainWindow.light_mode_fg)
        if modified:
            return (MainWindow.dark_mode_modified_bg, MainWindow.dark_mode_modified_fg)
        else:
            return (MainWindow.dark_mode_bg, MainWindow.dark_mode_fg)

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
            elif tags[0] == "file":
                values = self.workspace.item(select, option="values")
                assert(values != '' and len(values) == 1)
                if "patch" in os.path.splitext(values[0])[1] and os.path.exists(values[0]):
                    self.workspace_popup_menu.add_command(
                        label="Open",
                        command=lambda: self.load_archive(archive_file=values[0]),
                    )
        wems = []
        for i in selects:
            tags = self.workspace.item(i, option="tags")
            assert(tags != '' and len(tags) == 1)
            if tags[0] != "file":
                continue
            values = self.workspace.item(i, option="values")
            assert(values != '' and len(values) == 1)
            if os.path.exists(values[0]):
                wems.append(values[0])
        self.workspace_popup_menu.add_command(
            label="Import", 
            command=lambda: self.import_files(files=wems)
        )
        self.workspace_popup_menu.tk_popup(event.x_root, event.y_root)
        self.workspace_popup_menu.grab_release()
        
    def import_audio_files(self):
        
        if os.path.exists(WWISE_CLI):
            available_filetypes = [("Audio Files", "*.wem *.wav *.mp3 *.ogg *.m4a")]
        else:
            available_filetypes = [("Wwise Vorbis", "*.wem")]
        files = filedialog.askopenfilenames(title="Choose files to import", filetypes=available_filetypes)
        self.import_files(files)
        
    def import_files(self, files):
        patches = [file for file in files if "patch" in os.path.splitext(file)[1]]
        wems = [file for file in files if os.path.splitext(file)[1] == ".wem"]
        wavs = [file for file in files if os.path.splitext(file)[1] == ".wav"]
        
        # check other file extensions and call vgmstream to convert to wav, then add to wavs list
        others = [file for file in files if os.path.splitext(file)[1] in [".mp3", ".ogg", ".m4a"]]
        temp_files = []
        for file in others:
            process = subprocess.run([VGMSTREAM, "-o", f"{os.path.join(CACHE, os.path.splitext(os.path.basename(file))[0])}.wav", file], stdout=subprocess.DEVNULL)
            if process.returncode != 0:
                logger.error(f"Encountered error when importing {os.path.basename(file)}")
            else:
                wavs.append(f"{os.path.join(CACHE, os.path.splitext(os.path.basename(file))[0])}.wav")
                temp_files.append(f"{os.path.join(CACHE, os.path.splitext(os.path.basename(file))[0])}.wav")
        
        for patch in patches:
            self.file_handler.load_patch(patch_file=patch)
        if len(wems) > 0:
            self.load_wems(wems=wems)
        if len(wavs) > 0:
            self.load_wavs(wavs=wavs)
        if len(wems) == 0 and len(wavs) == 0:
            self.check_modified()
        self.show_info_window()
        for file in temp_files:
            try:
                os.remove(file)
            except:
                pass

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
        if self.lookup_store == None:
            logger.critical("Audio archive database connection is None after \
                    bypassing all check.", stack_info=True)
            return
        archives = self.lookup_store.query_helldiver_audio_archive()
        entries: dict[str, str] = {
                archive.audio_archive_id: archive.audio_archive_name 
                for archive in archives}
        self.archive_search = ArchiveSearch("{1} || {0}", 
                                            entries=entries,
                                            on_select_cb=self.on_archive_search_bar_return,
                                            master=self.top_bar,
                                            width=64)
        categories = self.lookup_store.query_helldiver_audio_archive_category()
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

    def on_category_search_bar_select(self, _):
        if self.lookup_store == None:
            logger.critical("Audio archive database connection is None after \
                    bypassing all check.", stack_info=True)
            return
        category: str = self.category_search.get()
        archives = self.lookup_store.query_helldiver_audio_archive(category)
        entries: dict[str, str] = {
                archive.audio_archive_id: archive.audio_archive_name 
                for archive in archives
        }
        self.archive_search.set_entries(entries)
        self.archive_search.focus_set()
        self.category_search.selection_clear()

    def treeview_on_right_click(self, event):
        try:
            self.right_click_menu.delete(0, "end")

            selects = self.treeview.selection()
            is_single = len(selects) == 1

            all_audio = True
            for select in selects:
                values = self.treeview.item(select, option="values")
                assert(len(values) == 1)
                if values[0] != MainWindow.ENTRY_TYPE_AUDIO_SOURCE:
                    all_audio = False
                    break

            self.right_click_menu.add_command(
                label=("Copy File ID" if is_single else "Copy File IDs"),
                command=self.copy_id
            )

            if not all_audio:
                return

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

    def treeview_on_double_click(self, _):
        # Rewrite this part against the doc how to use .item(). Provide better 
        # LSP type hinting
        selects = self.treeview.selection() 
        for select in selects:
            values = self.treeview.item(select, option="values")
            tags = self.treeview.item(select, option="tags")
            assert(len(values) == 1 and len(tags) == 1)
            if values[0] != MainWindow.ENTRY_TYPE_AUDIO_SOURCE:
                continue
            self.play_audio(int(tags[0]))

    def workspace_on_double_click(self, _):
        selects = self.workspace.selection()
        if len(selects) == 1:
            select = selects[0]
            values = self.workspace.item(select, option="values")
            tags = self.workspace.item(select, option="tags")
            assert(len(values) == 1 and len(tags) == 1)
            if tags[0] == "file" and os.path.splitext(values[0])[1] == ".wem" and os.path.exists(values[0]):
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

    def show_info_window(self, _ = None):
        if len(self.treeview.selection()) != 1:
            return

        selected = self.treeview.selection()[0]

        selected_type = self.treeview.item(selected, option="values")[0]
        selected_id = int(self.treeview.item(selected, option="tags")[0])
        for child in self.entry_info_panel.winfo_children():
            child.forget()
        if selected_type == MainWindow.ENTRY_TYPE_STRING:
            self.string_info_panel.set_string_entry(self.file_handler.get_string_by_id(selected_id))
            self.string_info_panel.frame.pack()
        elif selected_type == MainWindow.ENTRY_TYPE_AUDIO_SOURCE:
            self.audio_info_panel.set_audio(self.file_handler.get_audio_by_id(selected_id))
            self.audio_info_panel.frame.pack()
        elif selected_type == MainWindow.ENTRY_TYPE_EVENT:
            self.event_info_panel.set_track_info(self.file_handler.get_event_by_id(selected_id))
            self.event_info_panel.frame.pack()
        elif selected_type == MainWindow.ENTRY_TYPE_MUSIC_SEGMENT:
            self.segment_info_panel.set_segment_info(self.file_handler.get_music_segment_by_id(selected_id))
            self.segment_info_panel.frame.pack()
        elif selected_type == MainWindow.ENTRY_TYPE_SOUND_BANK:
            pass
        elif selected_type == MainWindow.ENTRY_TYPE_TEXT_BANK:
            pass

    def copy_id(self):
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join([self.treeview.item(i, option="tags")[0] for i in self.treeview.selection()]))
        self.root.update()

    def dump_as_wem(self):
        if len(self.treeview.selection()) == 1:
            self.file_handler.dump_as_wem(self.right_click_id)
        else:
            self.file_handler.dump_multiple_as_wem([int(self.treeview.item(i, option="tags")[0]) for i in self.treeview.selection()])

    def dump_as_wav(self, muted: bool = False, with_seq: bool = False):
        if len(self.treeview.selection()) == 1:
            self.file_handler.dump_as_wav(self.right_click_id, muted=muted)
            return
        self.file_handler.dump_multiple_as_wav(
            [int(self.treeview.item(i, option="tags")[0]) for i in self.treeview.selection()],
            muted=muted,
            with_seq=with_seq
        )

    def create_treeview_entry(
            self, entry: TreeViewEntry | None, 
            parentItem: str = ""):
        if entry is None:
            return ""

        tree_entry = self.treeview.insert(
            parentItem, END, tags=str(entry.get_id()))

        if isinstance(entry, AudioSource):
            entry_type = MainWindow.ENTRY_TYPE_AUDIO_SOURCE 
            name = f"{entry.get_id()}.wem"
        elif isinstance(entry, MusicSegment):
            entry_type = MainWindow.ENTRY_TYPE_MUSIC_SEGMENT
            name = f"Segment {entry.get_id()}"
        elif isinstance(entry, MusicTrack):
            entry_type = MainWindow.ENTRY_TYPE_MUSIC_TRACK
            name = f"Track {entry.get_id()}"
        elif isinstance(entry, StringEntry):
            entry_type = MainWindow.ENTRY_TYPE_STRING
            name = entry.get_text()[:20]
        elif isinstance(entry, TextBank):
            entry_type = MainWindow.ENTRY_TYPE_TEXT_BANK 
            name = f"{entry.get_id()}.text"
        elif isinstance(entry, TrackInfoStruct):
            entry_type = MainWindow.ENTRY_TYPE_EVENT
            name = f"Event {entry.get_id()}"
        elif isinstance(entry, WwiseBank):
            entry_type = MainWindow.ENTRY_TYPE_SOUND_BANK 
            name = entry.get_name()
            if entry.dep != None:
                name = entry.dep.data.split('/')[-1]

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
        bank_dict = self.file_handler.get_wwise_banks()
        for bank in bank_dict.values():
            bank_entry = self.create_treeview_entry(bank)
            for hierarchy_entry in bank.hierarchy.entries.values():
                if not isinstance(hierarchy_entry, MusicSegment):
                    segment_entry = self.create_treeview_entry(hierarchy_entry, bank_entry)
                    for track_id in hierarchy_entry.tracks:
                        track = bank.hierarchy.entries[track_id]
                        track_entry = self.create_treeview_entry(track, segment_entry)
                        for source in track.sources:
                            if source.plugin_id == VORBIS:
                                self.create_treeview_entry(self.file_handler.get_audio_by_id(source.source_id), track_entry)
                        for info in track.track_info:
                            if info.event_id != 0:
                                self.create_treeview_entry(info, track_entry)
                if isinstance(hierarchy_entry, Sound):
                    if not hierarchy_entry.sources[0].plugin_id == VORBIS:
                        self.create_treeview_entry(self.file_handler.get_audio_by_id(hierarchy_entry.sources[0].source_id), bank_entry)
        for entry in self.file_handler.file_reader.text_banks.values():
            if entry.language == language:
                e = self.create_treeview_entry(entry)
                for string_id in entry.string_ids:
                    self.create_treeview_entry(self.file_handler.file_reader.string_entries[language][string_id], e)
        self.check_modified()
                
    def create_source_view(self):
        self.clear_search()
        existing_sources = set()
        self.treeview.delete(*self.treeview.get_children())
        bank_dict = self.file_handler.get_wwise_banks()
        for bank in bank_dict.values():
            existing_sources.clear()
            bank_entry = self.create_treeview_entry(bank)
            for hierarchy_entry in bank.hierarchy.entries.values():
                for source in hierarchy_entry.sources:
                    if source.plugin_id == VORBIS and source.source_id not in existing_sources:
                        existing_sources.add(source.source_id)
                        self.create_treeview_entry(self.file_handler.get_audio_by_id(source.source_id), bank_entry)
        for entry in self.file_handler.file_reader.text_banks.values():
            if entry.language == language:
                e = self.create_treeview_entry(entry)
                for string_id in entry.string_ids:
                    self.create_treeview_entry(self.file_handler.file_reader.string_entries[language][string_id], e)
        self.check_modified()
                
    def recursive_match(self, search_text_var, item):
        is_string_entry = self.treeview.item(item, option="values")[0] \
                == MainWindow.ENTRY_TYPE_STRING
        match = False
        if is_string_entry:
            string_entry = self.file_handler.get_string_by_id(int(self.treeview.item(item, option="tags")[0]))
            if string_entry != None:
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
        if len(self.file_handler.get_strings()) > 0:
            self.language_menu.delete(0, "end")
            first = ""
            self.options_menu.add_cascade(label="Game text language", menu=self.language_menu)
            for name, lang_id in LANGUAGE_MAPPING.items():
                if first == "": first = name
                if lang_id in self.file_handler.get_strings():
                    self.language_menu.add_radiobutton(label=name, variable=self.selected_language, value=name, command=self.set_language)
            self.selected_language.set(first)

    def load_archive(self, initialdir: str | None = '', archive_file: str | None = None):
        self.sound_handler.kill_sound()
        if self.file_handler.load_archive_file(initialdir=initialdir, archive_file=archive_file):
            self.clear_search()
            self.update_language_menu()
            self.update_recent_files(filepath=self.file_handler.file_reader.path)
            if self.selected_view.get() == "SourceView":
                self.create_source_view()
            else:
                self.create_hierarchy_view()
            for child in self.entry_info_panel.winfo_children():
                child.forget()
        else:
            for child in self.treeview.get_children():
                self.treeview.delete(child)

    def save_archive(self):
        self.sound_handler.kill_sound()
        self.file_handler.save_archive_file()

    def clear_treeview_background(self, item):
        bg_color, fg_color = self.get_colors()
        self.treeview.tag_configure(self.treeview.item(item)['tags'][0],
                                    background=bg_color,
                                    foreground=fg_color)
        for child in self.treeview.get_children(item):
            self.clear_treeview_background(child)
        
    """
    TO-DO:
    optimization point: small, but noticeable lag if there are many, many 
    entries in the tree
    """
    def check_modified(self): 
        for child in self.treeview.get_children():
            self.clear_treeview_background(child)
        bg: Any
        fg: Any
        
        for segment in self.file_handler.file_reader.music_segments.values():
            bg, fg = self.get_colors(modified=segment.modified)
            self.treeview.tag_configure(str(segment.get_id()),
                                        background=bg,
                                        foreground=fg)
            if not segment.modified:
                continue

            items = self.treeview.tag_has(str(segment.get_id()))
            for item in items:
                parent = self.treeview.parent(item)
                while parent != "":
                    self.treeview.tag_configure(self.treeview.item(parent)['tags'][0], 
                                                background=bg,
                                                foreground=fg)
                    parent = self.treeview.parent(parent)
        
        for audio in self.file_handler.get_audio().values():
            is_modified = audio.modified or audio.get_track_info() is not None \
                    and audio.get_track_info().modified
            bg, fg = self.get_colors(modified=is_modified)
            self.treeview.tag_configure(str(audio.get_id()),
                                        background=bg,
                                        foreground=fg)
            if not is_modified:
                continue

            items = self.treeview.tag_has(str(audio.get_id()))
            for item in items:
                parent = self.treeview.parent(item)
                while parent != "":
                    self.treeview.tag_configure(self.treeview.item(parent)['tags'][0], 
                                                background=bg, 
                                                foreground=fg)
                    parent = self.treeview.parent(parent)

        for event in self.file_handler.file_reader.music_track_events.values():
            bg, fg = self.get_colors(modified=event.modified)
            self.treeview.tag_configure(event.get_id(),
                                        background=bg,
                                        foreground=fg)
            if not event.modified:
                continue

            items = self.treeview.tag_has(event.get_id())
            for item in items:
                parent = self.treeview.parent(item)
                while parent != "":
                    self.treeview.tag_configure(self.treeview.item(parent)['tags'][0], 
                                                background=bg,
                                                foreground=fg)
                    parent = self.treeview.parent(parent)
                    
        try:
            for string in self.file_handler.get_strings()[language].values():
                bg, fg = self.get_colors(modified=string.modified)
                self.treeview.tag_configure(str(string.get_id()), 
                                            background=bg,
                                            foreground=fg)
                if not string.modified:
                    continue
                item = self.treeview.tag_has(str(string.get_id()))
                parent = self.treeview.parent(item[0])
                while parent != "":
                    self.treeview.tag_configure(self.treeview.item(parent)['tags'][0],
                                                background=bg,
                                                foreground=fg)
                    parent = self.treeview.parent(parent)
        except KeyError:
            pass

    def load_wems(self, wems: list[str] | None = None):
        self.sound_handler.kill_sound()
        self.file_handler.load_wems(wems=wems)
        self.check_modified()
        self.show_info_window()
        
    def load_wavs(self, wavs: list[str] | None = None):
        self.sound_handler.kill_sound()
        self.file_handler.load_wavs(wavs=wavs)
        self.check_modified()
        self.show_info_window()
        
    def dump_all_as_wem(self):
        self.sound_handler.kill_sound()
        self.file_handler.dump_all_as_wem()
        
    def dump_all_as_wav(self):
        self.sound_handler.kill_sound()
        self.file_handler.dump_all_as_wav()
        
    def play_audio(self, file_id: int, callback=None):
        audio = self.file_handler.get_audio_by_id(file_id)
        if audio != None:
            self.sound_handler.play_audio(audio.get_short_id(), audio.get_data(), callback)
        
    def revert_audio(self, file_id):
        self.file_handler.revert_audio(file_id)
        
    def revert_all(self):
        self.sound_handler.kill_sound()
        self.file_handler.revert_all()
        self.check_modified()
        self.show_info_window()
        
    def write_patch(self):
        self.sound_handler.kill_sound()
        self.file_handler.write_patch()
        
    def load_patch(self):
        self.sound_handler.kill_sound()
        if self.file_handler.load_patch():
            self.check_modified()
            self.show_info_window()