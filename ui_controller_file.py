import os
import json
import shutil
import subprocess
import xml.etree.ElementTree as etree

from itertools import takewhile
from tkinter import filedialog
from tkinter.filedialog import askopenfilename
from tkinter.messagebox import showerror, showwarning
from typing import Any, Literal, Union

from const_global import language
from const_global import CACHE, DEFAULT_CONVERSION_SETTING, DEFAULT_WWISE_PROJECT, \
        FFMPEG, SYSTEM, VGMSTREAM, WWISE_CLI
from game_asset_entity import AudioSource
from log import logger
from parser import FileReader
from ui_window_component import ProgressWindow


class FileHandler:

    def __init__(self):
        self.file_reader = FileReader()
        
    def revert_all(self):
        for audio in self.file_reader.audio_sources.values():
            audio.revert_modifications()
        for language in self.file_reader.string_entries.values():
            for string in language.values():
                string.revert_modifications()
        for track_info in self.file_reader.music_track_events.values():
            track_info.revert_modifications()
        for music_segment in self.file_reader.music_segments.values():
            music_segment.revert_modifications()
        
    def revert_audio(self, file_id):
        audio = self.get_audio_by_id(file_id)
        audio.revert_modifications()
        
    def dump_as_wem(self, file_id):
        output_file = filedialog.asksaveasfile(mode='wb', title="Save As", initialfile=(str(file_id)+".wem"), defaultextension=".wem", filetypes=[("Wwise Audio", "*.wem")])
        if output_file is None:
            return

        audio = self.get_audio_by_id(file_id)
        if audio == None:
            return

        output_file.write(audio.get_data())
        
    def dump_as_wav(self, file_id, muted: bool = False):
        output_file = filedialog.asksaveasfilename(
            title="Save As", 
            initialfile=f"{file_id}.wav", 
            defaultextension=".wav", 
            filetypes=[("Wav Audio", "*.wav")]
        )

        if output_file == "":
            return

        save_path = os.path.splitext(output_file)[0]

        if muted:
            subprocess.run([
                FFMPEG, 
                "-f", "lavfi", 
                "-i", "anullsrc=r=48000:cl=stereo",
                "-t", "1", # TO-DO, this should match up with actual duration
                "-c:a", "pcm_s16le",
                f"{save_path}.wav"],
                stdout=subprocess.DEVNULL
            )
            return

        audio = self.get_audio_by_id(file_id)
        if audio == None:
            logger.error(f"Error when converting {file_id}.wem into .wav format."
                         f"No audio source found assoicated with {file_id}")
            return

        with open(f"{save_path}.wem", 'wb') as f:
            f.write(audio.get_data())

        process = subprocess.run(
            [VGMSTREAM, "-o", f"{save_path}.wav", f"{save_path}.wem"], 
            stdout=subprocess.DEVNULL)
        
        if process.returncode != 0:
            logger.error(f"Encountered error when converting {file_id}.wem into .wav format")

        os.remove(f"{save_path}.wem")
        
    def dump_multiple_as_wem(self, file_ids):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        
        progress_window = ProgressWindow(title="Dumping Files", max_progress=len(file_ids))
        progress_window.show()
        
        if os.path.exists(folder):
            for file_id in file_ids:
                audio = self.get_audio_by_id(file_id)
                if audio is not None:
                    save_path = os.path.join(folder, f"{audio.get_id()}")
                    progress_window.set_text("Dumping " + os.path.basename(save_path) + ".wem")
                    with open(save_path+".wem", "wb") as f:
                        f.write(audio.get_data())
                progress_window.step()
        else:
            print("Invalid folder selected, aborting dump")
            
        progress_window.destroy()
        
    def dump_multiple_as_wav(self, file_ids: list[int], muted: bool = False,
                             with_seq: bool = False):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        
        if not os.path.exists(folder):
            logger.warning("Invalid folder selected, aborting dump")
            return

        progress_window = ProgressWindow(title="Dumping Files", 
                                         max_progress=len(file_ids))
        progress_window.show()


        for i, file_id in enumerate(file_ids, start=0):
            audio = self.get_audio_by_id(int(file_id))
            if audio is None:
                continue
            basename = str(audio.get_id())
            if with_seq:
                basename = f"{i:02d}" + "_" + basename
            save_path = os.path.join(folder, basename)
            progress_window.set_text(
                "Dumping " + os.path.basename(save_path) + ".wem"
            )
            if muted:
                subprocess.run([
                    FFMPEG, 
                    "-f", "lavfi", 
                    "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", "1", # TO-DO, this should match up with actual duration
                    "-c:a", "pcm_s16le",
                    f"{save_path}.wav"],
                    stdout=subprocess.DEVNULL
                )
            else:
                with open(save_path + ".wem", "wb") as f:
                    f.write(audio.get_data())
                process = subprocess.run(
                    [VGMSTREAM, "-o", f"{save_path}.wav", f"{save_path}.wem"],
                    stdout=subprocess.DEVNULL,
                )
                if process.returncode != 0:
                    logger.error(f"Encountered error when converting {basename}.wem to .wav")
                os.remove(f"{save_path}.wem")
            progress_window.step()

        progress_window.destroy()

    def dump_all_as_wem(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        
        progress_window = ProgressWindow(title="Dumping Files", max_progress=len(self.file_reader.audio_sources))
        progress_window.show()
        
        if os.path.exists(folder):
            for bank in self.file_reader.wwise_banks.values():
                subfolder = os.path.join(folder, os.path.basename(bank.dep.data.replace('\x00', '')))
                if not os.path.exists(subfolder):
                    os.mkdir(subfolder)
                for audio in bank.get_content():
                    save_path = os.path.join(subfolder, f"{audio.get_id()}")
                    progress_window.set_text("Dumping " + os.path.basename(save_path) + ".wem")
                    with open(save_path+".wem", "wb") as f:
                        f.write(audio.get_data())
                    progress_window.step()
        else:
            print("Invalid folder selected, aborting dump")
            
        progress_window.destroy()
    
    def dump_all_as_wav(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")

        progress_window = ProgressWindow(title="Dumping Files", max_progress=len(self.file_reader.audio_sources))
        progress_window.show()
        
        if os.path.exists(folder):
            for bank in self.file_reader.wwise_banks.values():
                subfolder = os.path.join(folder, os.path.basename(bank.dep.data.replace('\x00', '')))
                if not os.path.exists(subfolder):
                    os.mkdir(subfolder)
                for audio in bank.get_content():
                    save_path = os.path.join(subfolder, f"{audio.get_id()}")
                    progress_window.set_text("Dumping " + os.path.basename(save_path) + ".wav")
                    with open(save_path+".wem", "wb") as f:
                        f.write(audio.get_data())
                    process = subprocess.run([VGMSTREAM, "-o", f"{save_path}.wav", f"{save_path}.wem"], stdout=subprocess.DEVNULL)
                    if process.returncode != 0:
                        logger.error(f"Encountered error when converting {os.path.basename(save_path)}.wem to .wav")
                    os.remove(f"{save_path}.wem")
                    progress_window.step()
        else:
            print("Invalid folder selected, aborting dump")
            
        progress_window.destroy()
        
    def get_number_prefix(self, n):
        number = ''.join(takewhile(str.isdigit, n or ""))
        try:
            return int(number)
        except:
            logger.warning(f"File name must begin with a number: {n}")
        
    def save_archive_file(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        if os.path.exists(folder):
            self.file_reader.rebuild_headers()
            self.file_reader.to_file(folder)
        else:
            print("Invalid folder selected, aborting save")
            
    def get_audio_by_id(self, file_id: int):
        if file_id in self.file_reader.audio_sources:
            return self.file_reader.audio_sources[file_id]

        for source in self.file_reader.audio_sources.values(): #resource_id
            if source.resource_id == file_id:
                return source

        return None
                
    def get_event_by_id(self, event_id):
        try:
            return self.file_reader.music_track_events[event_id]
        except:
            pass
            
    def get_string_by_id(self, string_id: int):
        if string_id in self.file_reader.string_entries[language]:
            return self.file_reader.string_entries[language][string_id]
        return None
        
    def get_music_segment_by_id(self, segment_id):
        try:
            return self.file_reader.music_segments[segment_id]
        except:
            pass
        
    def get_wwise_streams(self):
        return self.file_reader.wwise_streams
        
    def get_wwise_banks(self):
        return self.file_reader.wwise_banks
        
    def get_audio(self):
        return self.file_reader.audio_sources
        
    def get_strings(self):
        return self.file_reader.string_entries
        
    def load_archive_file(self, initialdir: str | None = '', archive_file: str | None = None):
        if archive_file == None:
            archive_file = askopenfilename(initialdir=initialdir, 
                                           title="Select archive")
        if os.path.splitext(archive_file)[1] in (".stream", ".gpu_resources"):
            archive_file = os.path.splitext(archive_file)[0]
        if os.path.exists(archive_file):
            try:
                self.file_reader.from_file(archive_file)
            except Exception as e:
                logger.error(f"Error occured when loading {archive_file}: {e}.")
                logger.warning("Aborting load")
                return False
        else:
            print("Invalid file selected, aborting load")
            return False
        return True
            
            
    def load_patch(self, patch_file: str | None = None): #TO-DO: only import if DIFFERENT from original audio; makes it possible to import different mods that change the same soundbank
        patch_file_reader = FileReader()
        if patch_file == None:
            patch_file = filedialog.askopenfilename(title="Choose patch file to import")
        if os.path.splitext(patch_file)[1] in (".stream", ".gpu_resources"):
            patch_file = os.path.splitext(patch_file)[0]
        if os.path.exists(patch_file):
            try:
                patch_file_reader.from_file(patch_file)
            except Exception as e:
                logger.error(f"Error occured when loading {patch_file}: {e}.")
                logger.warning("Aborting load")
                return False
        else:
            print("Invalid file selected, aborting load")
            return False
            
        progress_window = ProgressWindow(title="Loading Files", max_progress=len(patch_file_reader.audio_sources))
        progress_window.show()
        
        #TO-DO: Import hierarchy changes
        
        for bank in patch_file_reader.wwise_banks.values(): #something is a bit wrong here
            #load audio content from the patch
            for new_audio in bank.get_content():
                progress_window.set_text(f"Loading {new_audio.get_id()}")
                old_audio = self.get_audio_by_id(new_audio.get_short_id())
                if old_audio is not None:
                    old_audio.set_data(new_audio.get_data())
                    if old_audio.get_track_info() is not None and new_audio.get_track_info() is not None:
                        new_track_info = new_audio.get_track_info()
                        old_audio.get_track_info().set_data(play_at=new_track_info.play_at, begin_trim_offset=new_track_info.begin_trim_offset, end_trim_offset=new_track_info.end_trim_offset, source_duration=new_track_info.source_duration)
                progress_window.step()

        for key, music_segment in patch_file_reader.music_segments.items():
            try:
                old_music_segment = self.file_reader.music_segments[key]
            except:
                continue
            if (
                (
                    not old_music_segment.modified
                    and (
                        music_segment.entry_marker[1] != old_music_segment.entry_marker[1]
                        or music_segment.exit_marker[1] != old_music_segment.exit_marker[1]
                        or music_segment.duration != old_music_segment.duration
                    )
                )
                or
                (
                    old_music_segment.modified
                    and (
                        music_segment.entry_marker[1] != old_music_segment.entry_marker_old
                        or music_segment.exit_marker[1] != old_music_segment.exit_marker_old
                        or music_segment.duration != old_music_segment.duration_old
                    )
                )
            ):
                old_music_segment.set_data(duration=music_segment.duration, entry_marker=music_segment.entry_marker[1], exit_marker=music_segment.exit_marker[1])

        for text_data in patch_file_reader.text_banks.values():
            for string_id in text_data.string_ids:
                new_text_data = patch_file_reader.string_entries[language][string_id]
                try:
                    old_text_data = self.file_reader.string_entries[language][string_id]
                except:
                    continue
                if (
                    (not old_text_data.modified and new_text_data.get_text() != old_text_data.get_text())
                    or (old_text_data.modified and new_text_data.get_text() != old_text_data.text_old)
                ):
                    old_text_data.set_text(new_text_data.get_text())
        
        progress_window.destroy()
        return True

    def write_patch(self, folder=None):
        if folder == None:
            folder = filedialog.askdirectory(title="Select folder to save files to")
        if os.path.exists(folder):
            patch_file_reader = FileReader()
            patch_file_reader.name = self.file_reader.name + ".patch_0"
            patch_file_reader.magic = self.file_reader.magic
            patch_file_reader.num_types = 0
            patch_file_reader.num_files = 0
            patch_file_reader.unknown = self.file_reader.unknown
            patch_file_reader.unk4Data = self.file_reader.unk4Data
            patch_file_reader.audio_sources = self.file_reader.audio_sources
            patch_file_reader.string_entries = self.file_reader.string_entries
            patch_file_reader.music_track_events = self.file_reader.music_track_events
            patch_file_reader.music_segments = self.file_reader.music_segments
            patch_file_reader.wwise_banks = {}
            patch_file_reader.wwise_streams = {}
            patch_file_reader.text_banks = {}
            
            for key, value in self.file_reader.wwise_streams.items():
                if value.content.modified:
                    patch_file_reader.wwise_streams[key] = value
                    
            for key, value in self.file_reader.wwise_banks.items():
                if value.modified:
                    patch_file_reader.wwise_banks[key] = value
                    
            for key, value in self.file_reader.text_banks.items():
                for string_id in value.string_ids:
                    if self.file_reader.string_entries[value.language][string_id].modified:
                        patch_file_reader.text_banks[key] = value
                        break
     
            patch_file_reader.rebuild_headers()
            patch_file_reader.to_file(folder)
        else:
            print("Invalid folder selected, aborting save")
            return False
        return True

    def load_wems(self, wems: Union[list[str], tuple[str, ...], Literal[""], None] = None): 
        if wems == None:
            wems = filedialog.askopenfilenames(title="Choose .wem files to import")
        if wems == "":
            return
        progress_window = ProgressWindow(title="Loading Files", 
                                         max_progress=len(wems))
        progress_window.show()
        for wem in wems:
            basename = os.path.basename(wem)
            splits: list[str] = basename.split("_", 1)
            try:
                match splits:
                    case [prefix, name] if int(prefix) < 10000:
                        basename = name
            except:
                pass
            progress_window.set_text("Loading " + basename)
            file_id: int | None = self.get_number_prefix(basename)
            if file_id == None:
                continue
            audio: AudioSource | None = self.get_audio_by_id(file_id)
            if audio == None:
                continue
            with open(wem, 'rb') as f:
                audio.set_data(f.read())
            progress_window.step()
        progress_window.destroy()
        
    def create_external_sources_list(self, sources: list[str] | tuple[str, ...]):
        root = etree.Element("ExternalSourcesList", attrib={
            "SchemaVersion": "1",
            "Root": __file__
        })
        file = etree.ElementTree(root)
        for source in sources:
            etree.SubElement(root, "Source", attrib={
                "Path": source,
                "Conversion": DEFAULT_CONVERSION_SETTING,
                "Destination": os.path.basename(source)
            })
        file.write(os.path.join(CACHE, "external_sources.wsources"))
        
        return os.path.join(CACHE, "external_sources.wsources")
        
        
    def load_wavs(self, wavs: Union[list[str], tuple[str, ...], Literal[''], None] = None):
        if wavs == None:
            wavs = filedialog.askopenfilenames(title="Choose .wav files to import")
        if wavs == "" or None:
            return
            
        source_list = self.create_external_sources_list(wavs)
        try:
            if SYSTEM in ["Windows", "Darwin"]:
                subprocess.run([
                    WWISE_CLI,
                    "migrate",
                    DEFAULT_WWISE_PROJECT,
                    "--quiet",
                ]).check_returncode()
            else:
                showerror(title="Operation Failed",
                    message="The current operating system does not support this feature yet")
        except Exception as e:
            logger.error(e)
            showerror(title="Error", message="Error occurred during project migration. Please check log.txt.")
        
        convert_dest = os.path.join(CACHE, SYSTEM)
        try:
            if SYSTEM == "Darwin":
                subprocess.run([
                    WWISE_CLI,
                    "convert-external-source",
                    DEFAULT_WWISE_PROJECT,
                    "--platform", "Windows",
                    "--source-file",
                    source_list,
                    "--output",
                    CACHE,
                ]).check_returncode()
            elif SYSTEM == "Windows":
                subprocess.run([
                    WWISE_CLI,
                    "convert-external-source",
                    DEFAULT_WWISE_PROJECT,
                    "--platform", "Windows",
                    "--source-file",
                    source_list,
                    "--output",
                    CACHE,
                ]).check_returncode()
            else:
                showerror(title="Operation Failed",
                    message="The current operating system does not support this feature yet")
        except Exception as e:
            logger.error(e)
            showerror(title="Error", message="Error occurred during conversion. Please check log.txt.")
            
        wems = [os.path.join(convert_dest, x) for x in os.listdir(convert_dest)]
        
        self.load_wems(wems)
        
        for wem in wems:
            try:
                os.remove(wem)
            except:
                pass
                
        try:
            os.remove(source_list)
        except:
            pass

    def load_wav_by_mapping(self,
                 project: str,
                 wems: list[tuple[str, AudioSource, int]],
                 schema: etree.Element) -> bool:
        if len(wems) == 0:
            return True
        tree = etree.ElementTree(schema)
        schema_path = os.path.join(CACHE, "schema.xml")
        tree.write(schema_path, encoding="utf-8", xml_declaration=True)
        convert_ok = True
        convert_dest = os.path.join(CACHE, SYSTEM)
        try:
            if SYSTEM == "Darwin":
                subprocess.run([
                    WWISE_CLI,
                    "convert-external-source",
                    project,
                    "--platform", "Windows",
                    "--source-file",
                    schema_path,
                    "--output",
                    CACHE,
                ]).check_returncode()
            elif SYSTEM == "Windows":
                subprocess.run([
                    WWISE_CLI,
                    "convert-external-source",
                    project,
                    "--platform", "Windows",
                    "--source-file",
                    schema_path,
                    "--output",
                    CACHE,
                ]).check_returncode()
            else:
                convert_ok = False
                showerror(title="Operation Failed",
                    message="The current operating system does not support this feature yet")
        except Exception as e:
            convert_ok = False
            logger.error(e)
            showerror(title="Error", message="Error occurred during conversion. Please check log.txt.")

        if not convert_ok:
            return False

        for wem in wems:
            try:
                dest_path = os.path.join(convert_dest, wem[0])
                assert(os.path.exists(dest_path))
                with open(dest_path, "rb") as f:
                    wem[1].set_data(f.read())
            except Exception as e:
                logger.error(e)

        try:
            os.remove(schema_path)
            shutil.rmtree(convert_dest)
        except Exception as e:
            logger.error(e)

        return True

    def load_convert_spec(self):
        spec_path = filedialog.askopenfilename(title="Choose .spec file to import", 
                                          filetypes=[("json", "")])
        if spec_path == "":
            logger.warning("Import operation cancelled")
            return
        if not os.path.exists(spec_path):
            showerror(title="Operation Failed", message=f"{spec_path} does not exist.")
            logger.warning(f"{spec_path} does not exist. Import operation " \
                    "cancelled")
            return

        root_spec: Any = None
        try:
            with open(spec_path, mode="r") as f:
                root_spec = json.load(f)
        except json.JSONDecodeError as err:
            logger.warning(err)
            root_spec = None

        if root_spec == None:
            return

        if not isinstance(root_spec, dict):
            showerror(title="Operation Failed",
                      message="Invalid data format in the given spec file.") 
            logger.warning("Invalid data format in the given spec file. Import "
                           "operation cancelled")
            return

        # Validate version number #
        if "v" not in root_spec:
            showerror(title="Operation Failed", 
                      message="The given spec file is missing field `v`") 
            logger.warning("The given spec file is missing field `v`. Import "
                           "operation cancelled.")
            return
        v = root_spec["v"]
        if v != 2:
            showerror(title="Operation Failed", 
                      message="The given spec file contain invalid version " 
                      f'number {v}.')
            logger.warning("The given spec file contain invalid version "
                           f'number {v}. Import operation cancelled')
            return

        # Validate `specs` field #
        if "specs" not in root_spec:
            showerror(title="Operation Failed", 
                      message="The given spec file is missing field `specs`.")
            logger.warning("The given spec file is missing field `specs`."
                            " Import operation cancelled.")
            return
        if not isinstance(root_spec["specs"], list):
            showerror(title="Operation Failed",
                      message="Field `specs` is not an array.")
            logger.warning("Field `specs` is not an array. Import operation "
                           "cancelled.")
            return

        # Validate `project` path #
        project = DEFAULT_WWISE_PROJECT
        if "project" not in root_spec:
            logger.warning("Missing field `project`. Using default Wwise project")
        else:
            if not isinstance(root_spec["project"], str):
                logger.warning("Field `project` is not a string. Using default"
                               " Wwise project")
            elif not os.path.exists(root_spec["project"]):
                logger.warning("The given Wwise project does not exist. Using "
                               "default Wwise project")
            else:
                project = root_spec["project"]
        if not os.path.exists(project):
            showerror(title="Operation Failed",
                      message="The default Wwise Project does not exist.")
            logger.warning("The default Wwise Project does not exist. Import "
                           "operation cancelled.")
            return
        # Validate project `conversion` setting #
        conversion = DEFAULT_CONVERSION_SETTING
        if project != DEFAULT_WWISE_PROJECT:
            if "conversion" not in root_spec:
                showerror(title="Operation Failed",
                          message="Missing field `conversion`.")
                logger.warning("Missing field `conversion`. Import operation"
                               " cancelled.")
                return
            if not isinstance(root_spec["conversion"], str):
                showerror(title="Operation Failed",
                          message="Field `conversion` is not a string.")
                logger.warning("Field `conversion` is not a string. Import "
                               "operation cancelled.")
                return
            conversion = root_spec["conversion"]

        spec_dir = os.path.dirname(spec_path)
        root = etree.Element("ExternalSourcesList", attrib={
            "SchemaVersion": "1",
            "Root": spec_dir
        })
        wems: list[tuple[str, AudioSource, int]] = []
        for sub_spec in root_spec["specs"]:
            # Validate spec format #
            if not isinstance(sub_spec, dict):
                logger.warning("Current entry is not an object. Skipping "
                               "current entry.")
                continue

            # Validate work space #
            workspace = ""
            if "workspace" not in sub_spec:
                logger.warning("The given spec file is missing field "
                               "`workspace`. Use the current directory of the "
                               "given spec file is in instead.")
                workspace = spec_dir 
            else:
                workspace = sub_spec["workspace"]
                # Relative path
                if not os.path.exists(workspace): 
                    workspace = os.path.join(spec_dir, workspace) 
            if not os.path.exists(workspace):
                showwarning(title="Operation Skipped",
                            message=f"{workspace} does not exist.")
                logger.warning(f"{workspace} does not exist. Skipping current "
                               "entry.")
                continue

            # Validate `mapping` format #
            mapping: dict[str, list[str] | str] | None
            if "mapping" not in sub_spec:
                showwarning(title="Operation Skipped", 
                            message=f"The given spec file is missing field " 
                            "`mapping`")
                logger.warning("The given spec file is missing field `mapping`. "
                        "Skipping current entry.")
                continue
            mapping = sub_spec["mapping"]
            if mapping == None or not isinstance(mapping, dict):
                showwarning(title="Operation Skipped", 
                            message="field `mapping` has an invalid data type")
                logger.warning("field `mapping` has an invalid data type. Skipping "
                        "current entry.")
                continue

            suffix: str = ""
            if "suffix" in sub_spec:
                if not isinstance(sub_spec["suffix"], str):
                    logger.warning("`suffix` is not a str. Disable "
                            "substring filtering")
                else:
                    suffix = sub_spec["suffix"]
            prefix: str = ""
            if "prefix" in sub_spec:
                if not isinstance(sub_spec["prefix"], str):
                    logger.warning("`prefix` is not a str. Disable "
                            "substring filtering")
                else:
                    prefix = sub_spec["prefix"]

            for src, dest in mapping.items():
                src = prefix + src + suffix

                abs_src = os.path.join(workspace, src)
                if not abs_src.endswith(".wav"):
                    logger.info("Require import file missing .wav extension. "
                            "Adding extension.")
                    abs_src += ".wav"
                if not os.path.exists(abs_src):
                    logger.warning(f"Required import file does not exist "
                            "Skipping the current entry.")
                    continue

                if isinstance(dest, str):
                    file_id: int | None = self.get_number_prefix(dest)
                    if file_id == None:
                        logger.warning(f"{dest} does not contain a valid game "
                                       "asset file id. Skipping the current "
                                       "entry.")
                        continue
                    audio = self.get_audio_by_id(file_id)
                    convert_dest = f"{file_id}.wem"
                    if audio == None:
                        logger.warning(f"No audio source is associated with "
                                       f"game asset file id {file_id}. Skipping "
                                       "the current entry.")
                        continue
                    etree.SubElement(root, "Source", attrib={
                        "Path": abs_src,
                        "Conversion": conversion,
                        "Destination": convert_dest 
                    })
                    wems.append((convert_dest, audio, file_id))
                elif isinstance(dest, list):
                    for d in dest:
                        if not isinstance(d, str):
                            logger.warning(f"{d} is not a string. Skipping the "
                                    "current entry.")
                        file_id: int | None = self.get_number_prefix(d)
                        if file_id == None:
                            logger.warning(f"{d} does not contain a valid game "
                                           "asset file id. Skipping the current "
                                           "entry.")
                            continue
                        audio = self.get_audio_by_id(file_id)
                        if audio == None:
                            logger.warning(f"No audio source is associated with "
                                           f"game asset file id {file_id}. "
                                           "Skipping the current entry.")
                            continue
                        convert_dest = f"{file_id}.wem"
                        etree.SubElement(root, "Source", attrib={
                            "Path": abs_src,
                            "Conversion": conversion,
                            "Destination": convert_dest
                        })
                        wems.append((convert_dest, audio, file_id))
                else:
                    logger.warning(f"{dest} is not a string or list of string. "
                            "Skipping the current entry.")
            out: str | None = None
            if "write_patch_to" not in sub_spec:
                continue
            out = sub_spec["write_patch_to"]
            if not isinstance(out, str):
                showwarning(title="Operation Skipped", 
                            message="field `write_patch_to` has an invalid data "
                            "type. Write patch operation cancelled.")
                logger.warning("field `write_patch_to` has an invalid data "
                               "type. Write patch operation cancelled.")
                continue
            if not os.path.exists(out):
                # Relative patch write #
                out = os.path.join(spec_dir, out)
                if not os.path.exists(out):
                    showwarning(title="Operation Skipped",
                                message=f"{out} does not exist. Write patch "
                                "operation cancelled.")
                    logger.warning(f"{out} does not exist. Write patch operation "
                                   "cancelled.")
                    continue
            if not self.load_wav_by_mapping(project, wems, root):
                continue
            if not self.write_patch(folder=out):
                showerror(title="Operation Failed", message="Write patch operation failed. Check "
                            "log.txt for detailed.")
            root = etree.Element("ExternalSourcesList", attrib={
                "SchemaVersion": "1",
                "Root": spec_dir 
            })
            is_revert = "revert" in sub_spec and \
                    isinstance(sub_spec["revert"], bool) and \
                    sub_spec["revert"]
            is_revert_all = "revert_all" in sub_spec and \
                    isinstance(sub_spec["revert_all"], bool) and \
                    sub_spec["revert_all"]
            if is_revert_all:
                self.revert_all()
                continue
            if is_revert:
                for wem in wems:
                    self.revert_audio(wem[2])
            wems.clear()

        self.load_wav_by_mapping(project, wems, root)
        out: str | None = None
        if "write_patch_to" not in root_spec:
            return
        out = root_spec["write_patch_to"]
        if not isinstance(out, str):
            showerror(title="Operation Failed", 
                      message="field `write_patch_to` has an invalid data "
                      "type. Write patch operation cancelled.")
            logger.warning("field `write_patch_to` has an invalid data "
                           "type. Write patch operation cancelled.")
            return
        if not os.path.exists(out):
            # Relative path patch writing #
            out = os.path.join(spec_dir, out)
            if not os.path.exists(out):
                showerror(title="Operation Failed",
                          message=f"{out} does not exist. Write patch "
                          "operation cancelled.")
                logger.warning(f"{out} does not exist. Write patch operation "
                              "cancelled.")
                return
        if not self.write_patch(folder=out):
            showerror(title="Operation Failed",
                      message="Write patch operation failed. Check "
                      "log.txt for detailed.")

        is_revert = "revert" in root_spec and \
                isinstance(root_spec["revert"], bool) and \
                root_spec["revert"]
        if is_revert:
            for wem in wems:
                self.revert_audio(wem[2])

    def load_wems_spec(self):
        spec_path = filedialog.askopenfilename(title="Choose .spec file to import", 
                                          filetypes=[("json", "")])
        if spec_path == "":
            logger.warning("Import operation cancelled")
            return
        if not os.path.exists(spec_path):
            showerror(title="Operation Failed", 
                      message=f"{spec_path} does not exist.")
            logger.warning(f"{spec_path} does not exist. Import operation "
                           "cancelled")
            return

        root_spec: Any = None
        try:
            with open(spec_path, mode="r") as f:
                root_spec = json.load(f)
        except json.JSONDecodeError as err:
            logger.warning(err)
            root_spec = None

        if root_spec == None:
            return

        if not isinstance(root_spec, dict):
            showerror(title="Operation Failed",
                      message="Invalid data format in the given spec file.") 
            logger.warning("Invalid data format in the given spec file. Import "
                    "operation cancelled")
            return

        # Validate version number # 
        if "v" not in root_spec:
            showerror(title="Operation Failed",
                      message="The given spec file is missing field `v`") 
            logger.warning("The given spec file is missing field `v`. Import "
                    "operation cancelled.")
            return
        if root_spec["v"] != 2:
            showerror(title="Operation Failed",
                      message="The given spec file contain invalid version " + 
                        f'number {root_spec["v"]}.')
            logger.warning("The given spec file contain invalid version "
                    f'number {root_spec["v"]}. Import operation cancelled')
            return

        # Validate `specs` format #
        if "specs" not in root_spec:
            showerror(title="Operation Failed",
                      message="The given spec file is missing field `specs`.")
            logger.warning("The given spec file is missing field `specs`."
                            " Import operation cancelled.")
            return
        if not isinstance(root_spec["specs"], list):
            showerror(title="Operation Failed",
                      message="Field `specs` is not an array.")
            logger.warning("Field `specs` is not an array. Import operation "
                           "cancelled.")
            return

        spec_dir = os.path.dirname(spec_path)
        patched_ids: list[int] = []
        for sub_spec in root_spec["specs"]:
            if not isinstance(sub_spec, dict):
                logger.warning("Current entry is not an object. Skipping "
                               "current entry.")
                continue

            workspace = ""
            # Validate work space # 
            if "workspace" not in sub_spec:
                logger.warning("The given spec file is missing field "
                               "`workspace`. Use the current directory of the "
                               "given spec file is in instead.")
                workspace = spec_dir
            else:
                workspace = sub_spec["workspace"]
                # Relative path
                if not os.path.exists(workspace): 
                    workspace = os.path.join(spec_dir, workspace) 
            if not os.path.exists(workspace):
                showwarning(title="Operation Skipped",
                            message=f"{workspace} does not exist.")
                logger.warning(f"{workspace} does not exist. Skipping current"
                        " entry")
                continue

            # Validate `mapping` format # 
            mapping: dict[str, list[str] | str] | None
            if "mapping" not in sub_spec:
                showwarning(title="Operation Skipped",
                            message=f"The given spec file is missing field "
                            "`mapping`")
                logger.warning("The given spec file is missing field `mapping`. "
                        "Skipping current entry")
                continue
            mapping = sub_spec["mapping"]
            if mapping == None or not isinstance(mapping, dict):
                showwarning(title="Operation Skipped",
                            message="field `mapping` has an invalid data type")
                logger.warning("field `mapping` has an invalid data type. "
                        "Skipping current entry")
                continue

            suffix: str = ""
            if "suffix" in sub_spec:
                if not isinstance(sub_spec["suffix"], str):
                    logger.warning("`suffix` is not a str. Disable "
                            "substring filtering")
                else:
                    suffix = sub_spec["suffix"]
            prefix: str = ""
            if "prefix" in sub_spec:
                if not isinstance(sub_spec["prefix"], str):
                    logger.warning("`prefix` is not a str. Disable "
                            "substring filtering")
                else:
                    prefix = sub_spec["prefix"]

            progress_window = ProgressWindow(title="Loading Files",
                                             max_progress=len(sub_spec.items()))
            progress_window.show()

            for src, dest in mapping.items():
                logger.info(f"Loading {src} into {dest}")
                progress_window.set_text(f"Loading {src} into {dest}")

                src = prefix + src + suffix

                abs_src = os.path.join(workspace, src)
                if not abs_src.endswith(".wem"):
                    logger.info("Require import file missing .wem extension. "
                            "Adding extension.")
                    abs_src += ".wem"
                if not os.path.exists(abs_src):
                    logger.warning(f"Required import file does not exist "
                            "Skipping the current entry.")
                    continue

                if isinstance(dest, str):
                    file_id: int | None = self.get_number_prefix(dest)
                    if file_id == None:
                        logger.warning(f"{dest} does not contain a valid game "
                                       "asset file id. Skipping the current "
                                       "entry.")
                        continue
                    audio: AudioSource | None = self.get_audio_by_id(file_id)
                    if audio == None:
                        logger.warning(f"No audio source is associated with "
                                       "game asset file id {file_id}. Skipping "
                                       "the current entry.")
                        continue
                    with open(abs_src, "rb") as f:
                        audio.set_data(f.read())
                    progress_window.step()

                    patched_ids.append(file_id)
                elif isinstance(dest, list):
                    for d in dest:
                        if not isinstance(d, str):
                            logger.warning(f"{d} is not a string. Skipping the "
                                    "current entry.")
                        file_id: int | None = self.get_number_prefix(d)
                        if file_id == None:
                            logger.warning(f"{d} does not contain a valid game "
                                           "asset file id. Skipping the current "
                                           "entry.")
                            continue
                        audio: AudioSource | None = self.get_audio_by_id(file_id)
                        if audio == None:
                            logger.warning(f"No audio source is associated with "
                                    "game asset file id {file_id}. Skipping the "
                                    "current entry.")
                            continue
                        with open(abs_src, "rb") as f:
                            audio.set_data(f.read())
                        progress_window.step()

                        patched_ids.append(file_id)
                else:
                    logger.warning(f"{dest} is not a string or list of string. "
                            "Skipping the current entry.")

            progress_window.destroy()

            out: str | None = None
            if "write_patch_to" not in sub_spec:
                return
            out = sub_spec["write_patch_to"]
            if not isinstance(out, str):
                showwarning(title="Operation Skipped",
                            message="field `write_patch_to` has an invalid data "
                            "type. Write patch operation cancelled.")
                logger.warning("field `write_patch_to` has an invalid data "
                               "type. Write patch operation cancelled.")
                continue
            if not os.path.exists(out):
                # Relative path
                out = os.path.join(spec_dir, out)
                if not os.path.exists(out):
                    showwarning(title="Operation Skipped", 
                                message=f"{out} does not exist. Write patch "
                                "operation cancelled.")
                    logger.warning(f"{out} does not exist. Write patch operation "
                                   "cancelled.")
                    continue
            if not self.write_patch(folder=out):
                showerror(title="Operation Failed",
                          message="Write patch operation failed. Check "
                          "log.txt for detailed.")
            is_revert = "revert" in sub_spec and \
                    isinstance(sub_spec["revert"], bool) and \
                    sub_spec["revert"]
            if is_revert:
                for patched_id in patched_ids:
                    self.revert_audio(patched_id)
            patched_ids.clear()
            
        out: str | None = None
        if "write_patch_to" not in root_spec:
            return
        out = root_spec["write_patch_to"]
        if not isinstance(out, str):
            showerror(title="Operation Failed", message="field `write_patch_to` has an invalid data "
                        "type. Write patch operation cancelled.")
            logger.warning("field `write_patch_to` has an invalid data "
                           "type. Write patch operation cancelled.")
            return
        if not os.path.exists(out):
            # Relative path
            out = os.path.join(spec_dir, out)
            if not os.path.exists(out):
                showerror(title="Operation Failed", message=f"{out} does not exist. Write patch "
                            "operation cancelled.")
                logger.warning(f"{out} does not exist. Write patch operation "
                               "cancelled.")
                return
        if not self.write_patch(folder=out):
            showerror(title="Operation Failed", message="Write patch operation failed. Check "
                            "log.txt for detailed.")

        is_revert = "revert" in root_spec and \
                isinstance(root_spec["revert"], bool) and \
                root_spec["revert"]
        if is_revert:
            for patched_id in patched_ids:
                self.revert_audio(patched_id)
        patched_ids.clear()
