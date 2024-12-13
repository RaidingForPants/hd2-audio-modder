import os

from tkinter.filedialog import askopenfilename

from game_asset_entity import AudioSource, MusicSegment
from game_asset_entity import TocHeader, TextBank, WwiseBank, WwiseDep, WwiseStream
from game_asset_entity import StringEntry, MediaIndex
from util import strip_patch_index
from ui_window_component import PopupWindow
from xstruct import MemoryStream
from xstruct import align_16_byte_with_pad, align_16_byte, murmur64_hash

# static const import
from const_global import BANK, PREFETCH_STREAM, STREAM, STRING, VORBIS, \
        WWISE_BANK, WWISE_DEP, WWISE_STREAM
# runtime const import
from const_global import GAME_FILE_LOCATION


class FileReader:
    
    def __init__(self):
        self.wwise_streams = {}
        self.wwise_banks = {}
        self.audio_sources: dict[int, AudioSource] = {}
        self.text_banks = {}
        self.music_track_events = {}
        self.string_entries: dict[int, dict[int, StringEntry]] = {}
        self.music_segments: dict[int, MusicSegment] = {}
        
    def from_file(self, path):
        self.name = os.path.basename(path)
        self.path = path
        toc_file = MemoryStream()
        with open(path, 'r+b') as f:
            toc_file = MemoryStream(f.read())

        stream_file = MemoryStream()
        if os.path.isfile(path+".stream"):
            with open(path+".stream", 'r+b') as f:
                stream_file = MemoryStream(f.read())
        self.load(toc_file, stream_file)
        
    def to_file(self, path):
        toc_file = MemoryStream()
        stream_file = MemoryStream()
        self.num_files = len(self.wwise_streams) + 2*len(self.wwise_banks) + len(self.text_banks)
        self.num_types = 0
        if len(self.wwise_streams) > 0: self.num_types += 1
        if len(self.wwise_banks) > 0: self.num_types += 2
        if len(self.text_banks) > 0: self.num_types += 1
        
        toc_file.write(self.magic.to_bytes(4, byteorder="little"))
        
        toc_file.write(self.num_types.to_bytes(4, byteorder="little"))
        toc_file.write(self.num_files.to_bytes(4, byteorder="little"))
        toc_file.write(self.unknown.to_bytes(4, byteorder="little"))
        toc_file.write(self.unk4Data)
        
        if len(self.wwise_streams) > 0:
            unk = 0
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = WWISE_STREAM
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = len(self.wwise_streams)
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = 16
            toc_file.write(unk.to_bytes(4, byteorder='little'))
            unk = 64
            toc_file.write(unk.to_bytes(4, byteorder='little'))
            
        if len(self.wwise_banks) > 0:
            unk = 0
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = WWISE_BANK
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = len(self.wwise_banks)
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = 16
            toc_file.write(unk.to_bytes(4, byteorder='little'))
            unk = 64
            toc_file.write(unk.to_bytes(4, byteorder='little'))
            
            #deps
            unk = 0
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = WWISE_DEP
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = len(self.wwise_banks)
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = 16
            toc_file.write(unk.to_bytes(4, byteorder='little'))
            unk = 64
            toc_file.write(unk.to_bytes(4, byteorder='little'))
            
        if len(self.text_banks) > 0:
            unk = 0
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = STRING
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = len(self.text_banks)
            toc_file.write(unk.to_bytes(8, byteorder='little'))
            unk = 16
            toc_file.write(unk.to_bytes(4, byteorder='little'))
            unk = 64
            toc_file.write(unk.to_bytes(4, byteorder='little'))
        
        file_position = toc_file.tell()
        for key in self.wwise_streams.keys():
            toc_file.seek(file_position)
            file_position += 80
            stream = self.wwise_streams[key]
            toc_file.write(stream.toc_header.get_data())
            toc_file.seek(stream.toc_header.toc_data_offset)
            toc_file.write(align_16_byte_with_pad(stream.TocData))
            stream_file.seek(stream.toc_header.stream_file_offset)
            stream_file.write(align_16_byte_with_pad(stream.content.get_data()))
            
        for key in self.wwise_banks.keys():
            toc_file.seek(file_position)
            file_position += 80
            bank = self.wwise_banks[key]
            toc_file.write(bank.toc_header.get_data())
            toc_file.seek(bank.toc_header.toc_data_offset)
            toc_file.write(align_16_byte_with_pad(bank.toc_data_header + bank.get_data()))
            
        for key in self.wwise_banks.keys():
            toc_file.seek(file_position)
            file_position += 80
            bank = self.wwise_banks[key]
            toc_file.write(bank.dep.toc_header.get_data())
            toc_file.seek(bank.dep.toc_header.toc_data_offset)
            toc_file.write(align_16_byte_with_pad(bank.dep.get_data()))
            
        for key in self.text_banks.keys():
            toc_file.seek(file_position)
            file_position += 80
            entry = self.text_banks[key]
            toc_file.write(entry.toc_header.get_data())
            toc_file.seek(entry.toc_header.toc_data_offset)
            toc_file.write(align_16_byte_with_pad(entry.get_data()))
            
        with open(os.path.join(path, self.name), 'w+b') as f:
            f.write(toc_file.data)
            
        if len(stream_file.data) > 0:
            with open(os.path.join(path, self.name+".stream"), 'w+b') as f:
                f.write(stream_file.data)

    def rebuild_headers(self):
        self.num_types = 0
        if len(self.wwise_streams) > 0: self.num_types += 1
        if len(self.wwise_banks) > 0: self.num_types += 2
        if len(self.text_banks) > 0: self.num_types += 1
        self.num_files = len(self.wwise_streams) + 2*len(self.wwise_banks) + len(self.text_banks)
        stream_file_offset = 0
        toc_file_offset = 80 + self.num_types * 32 + 80 * self.num_files
        for _, value in self.wwise_streams.items():
            value.toc_header.stream_file_offset = stream_file_offset
            value.toc_header.toc_data_offset = toc_file_offset
            stream_file_offset += align_16_byte(value.toc_header.stream_size)
            toc_file_offset += align_16_byte(value.toc_header.toc_data_size)
        
        for _, value in self.wwise_banks.items():
            value.generate(self.audio_sources, self.music_track_events)
            
            value.toc_header.toc_data_offset = toc_file_offset
            toc_file_offset += align_16_byte(value.toc_header.toc_data_size)
            
        for _, value in self.wwise_banks.items():
            value.dep.toc_header.toc_data_offset = toc_file_offset
            toc_file_offset += align_16_byte(value.toc_header.toc_data_size)
            
        for _, value in self.text_banks.items():
            value.generate(string_entries=self.string_entries)
            value.toc_header.toc_data_offset = toc_file_offset
            toc_file_offset += align_16_byte(value.toc_header.toc_data_size)
        
    def load(self, toc_file, stream_file):
        self.wwise_streams.clear()
        self.wwise_banks.clear()
        self.audio_sources.clear()
        self.text_banks.clear()
        self.music_track_events.clear()
        self.string_entries.clear()
        self.music_segments.clear()
        
        media_index = MediaIndex()
        
        self.magic      = toc_file.uint32_read()
        if self.magic != 4026531857: return False

        self.num_types   = toc_file.uint32_read()
        self.num_files   = toc_file.uint32_read()
        self.unknown    = toc_file.uint32_read()
        self.unk4Data   = toc_file.read(56)
        toc_file.seek(toc_file.tell() + 32 * self.num_types)
        toc_start = toc_file.tell()
        for n in range(self.num_files):
            toc_file.seek(toc_start + n*80)
            toc_header = TocHeader()
            toc_header.from_memory_stream(toc_file)
            entry = None
            if toc_header.type_id == WWISE_STREAM:
                audio = AudioSource()
                audio.stream_type = STREAM
                entry = WwiseStream(toc_header)
                toc_file.seek(toc_header.toc_data_offset)
                entry.TocData = toc_file.read(toc_header.toc_data_size)
                stream_file.seek(toc_header.stream_file_offset)
                audio.set_data(stream_file.read(toc_header.stream_size), notify_subscribers=False, set_modified=False)
                audio.resource_id = toc_header.file_id
                entry.set_content(audio)
                self.wwise_streams[entry.get_id()] = entry
            elif toc_header.type_id == WWISE_BANK:
                entry = WwiseBank(toc_header)
                toc_data_offset = toc_header.toc_data_offset
                toc_file.seek(toc_data_offset)
                entry.toc_data_header = toc_file.read(16)
                bank = WwiseBank.BankParser()
                bank.load(toc_file.read(toc_header.toc_data_size-16))
                entry.bank_header = "BKHD".encode('utf-8') + len(bank.chunks["BKHD"]).to_bytes(4, byteorder="little") + bank.chunks["BKHD"]
                
                hirc = WwiseBank.HircReader(soundbank=entry)
                try:
                    hirc.load(bank.chunks['HIRC'])
                except KeyError:
                    pass
                entry.hierarchy = hirc
                #Add all bank sources to the source list
                if "DIDX" in bank.chunks.keys():
                    media_index.load(bank.chunks["DIDX"], bank.chunks["DATA"])
                
                entry.bank_misc_data = b''
                for chunk in bank.chunks.keys():
                    if chunk not in ["BKHD", "DATA", "DIDX", "HIRC"]:
                        entry.bank_misc_data = entry.bank_misc_data + chunk.encode('utf-8') + len(bank.chunks[chunk]).to_bytes(4, byteorder='little') + bank.chunks[chunk]
                        
                self.wwise_banks[entry.get_id()] = entry
            elif toc_header.type_id == WWISE_DEP: #wwise dep
                dep = WwiseDep(toc_header)
                toc_file.seek(toc_header.toc_data_offset)
                dep.from_memory_stream(toc_file)
                try:
                    self.wwise_banks[toc_header.file_id].dep = dep
                except KeyError:
                    pass
            elif toc_header.type_id == STRING: #string_entry
                toc_file.seek(toc_header.toc_data_offset)
                data = toc_file.read(toc_header.toc_data_size)
                num_entries = int.from_bytes(data[8:12], byteorder='little')
                language = int.from_bytes(data[12:16], byteorder='little')
                if language not in self.string_entries:
                    self.string_entries[language] = {}
                id_section_start = 16
                offset_section_start = id_section_start + 4 * num_entries
                data_section_start = offset_section_start + 4 * num_entries
                ids = data[id_section_start:offset_section_start]
                offsets = data[offset_section_start:data_section_start]
                text_bank = TextBank(toc_header)
                text_bank.language = language
                for n in range(num_entries):
                    entry = StringEntry()
                    string_id = int.from_bytes(ids[4*n:+4*(n+1)], byteorder="little")
                    text_bank.string_ids.append(string_id)
                    string_offset = int.from_bytes(offsets[4*n:4*(n+1)], byteorder="little")
                    entry.string_id = string_id
                    stopIndex = string_offset + 1
                    while data[stopIndex] != 0:
                        stopIndex += 1
                    entry.text = data[string_offset:stopIndex].decode('utf-8')
                    self.string_entries[language][string_id] = entry
                self.text_banks[text_bank.get_id()] = text_bank
        
        # ---------- Backwards compatibility checks ----------
        for bank in self.wwise_banks.values():
            if bank.dep == None: #can be None because older versions didn't save the dep along with the bank
                if not self.load_deps():
                    print("Failed to load")
                    self.wwise_streams.clear()
                    self.wwise_banks.clear()
                    self.text_banks.clear()
                    self.audio_sources.clear()
                    return
                break
        
        if len(self.wwise_banks) == 0 and len(self.wwise_streams) > 0: #0 if patch was only for streams
            if not self.load_banks():
                print("Failed to load")
                self.wwise_streams.clear()
                self.wwise_banks.clear()
                self.text_banks.clear()
                self.audio_sources.clear()
                return
        # ---------- End backwards compatibility checks ----------
        
        # Create all AudioSource objects
        for bank in self.wwise_banks.values():
            for entry in bank.hierarchy.entries.values():
                for source in entry.sources:
                    if source.plugin_id == VORBIS and source.stream_type == BANK and source.source_id not in self.audio_sources:
                        try:
                            audio = AudioSource()
                            audio.stream_type = BANK
                            audio.short_id = source.source_id
                            audio.set_data(media_index.data[source.source_id], set_modified=False, notify_subscribers=False)
                            self.audio_sources[source.source_id] = audio
                        except KeyError:
                            pass
                    elif source.plugin_id == VORBIS and source.stream_type in [STREAM, PREFETCH_STREAM] and source.source_id not in self.audio_sources:
                        try:
                            stream_resource_id = murmur64_hash((os.path.dirname(bank.dep.data) + "/" + str(source.source_id)).encode('utf-8'))
                            audio = self.wwise_streams[stream_resource_id].content
                            audio.short_id = source.source_id
                            self.audio_sources[source.source_id] = audio
                        except KeyError:
                            pass
                for info in entry.track_info:
                    if info.event_id != 0:
                        self.music_track_events[info.event_id] = info
                if isinstance(entry, MusicSegment):
                    self.music_segments[entry.get_id()] = entry

        #construct list of audio sources in each bank
        #add track_info to audio sources?
        for bank in self.wwise_banks.values():
            for entry in bank.hierarchy.entries.values():
                for info in entry.track_info:
                    try:
                        if info.source_id != 0:
                            self.audio_sources[info.source_id].set_track_info(info, notify_subscribers=False, set_modified=False)
                    except:
                        continue
                for source in entry.sources:
                    try:
                        if source.plugin_id == VORBIS and self.audio_sources[source.source_id] not in bank.get_content(): #may be missing streamed audio if the patch didn't change it
                            bank.add_content(self.audio_sources[source.source_id])
                    except:
                        continue
                
        
    def load_deps(self):
        archive_file = ""
        if os.path.exists(GAME_FILE_LOCATION):
            archive_file = os.path.join(GAME_FILE_LOCATION, strip_patch_index(self.name))
        if not os.path.exists(archive_file):
            warning = PopupWindow(message = "This patch may have been created using an older version of the audio modding tool and is missing required data. Please select the original game file to load required data.")
            warning.show()
            warning.root.wait_window(warning.root)
            archive_file = askopenfilename(title="Select archive")
            if os.path.splitext(archive_file)[1] in (".stream", ".gpu_resources"):
                archive_file = os.path.splitext(archive_file)[0]
        if not os.path.exists(archive_file):
            return False
        toc_file = MemoryStream()
        with open(archive_file, 'r+b') as f:
            toc_file = MemoryStream(f.read())

        self.magic      = toc_file.uint32_read()
        if self.magic != 4026531857: return False

        self.num_types   = toc_file.uint32_read()
        self.num_files   = toc_file.uint32_read()
        self.unknown    = toc_file.uint32_read()
        self.unk4Data   = toc_file.read(56)
        toc_file.seek(toc_file.tell() + 32 * self.num_types)
        toc_start = toc_file.tell()
        for n in range(self.num_files):
            toc_file.seek(toc_start + n*80)
            toc_header = TocHeader()
            toc_header.from_memory_stream(toc_file)
            if toc_header.type_id == WWISE_DEP: #wwise dep
                dep = WwiseDep(toc_header)
                toc_file.seek(toc_header.toc_data_offset)
                dep.from_memory_stream(toc_file)
                try:
                    self.wwise_banks[toc_header.file_id].dep = dep
                except KeyError:
                    pass
        return True
        
    def load_banks(self):
        archive_file = ""
        if os.path.exists(GAME_FILE_LOCATION):
            archive_file = os.path.join(GAME_FILE_LOCATION, strip_patch_index(self.name))
        if not os.path.exists(archive_file):
            warning = PopupWindow(
                    message = "This patch may have been created using an older "
                    "version of the audio modding tool and is missing required "
                    "data. Please select the original game file to load required"
                    " data.")
            warning.show()
            warning.root.wait_window(warning.root)
            archive_file = askopenfilename(title="Select archive")
            if os.path.splitext(archive_file)[1] in (".stream", ".gpu_resources"):
                archive_file = os.path.splitext(archive_file)[0]
        if not os.path.exists(archive_file):
            return False
        toc_file = MemoryStream()
        with open(archive_file, 'r+b') as f:
            toc_file = MemoryStream(f.read())

        self.magic      = toc_file.uint32_read()
        if self.magic != 4026531857: return False

        self.num_types   = toc_file.uint32_read()
        self.num_files   = toc_file.uint32_read()
        self.unknown    = toc_file.uint32_read()
        self.unk4Data   = toc_file.read(56)
        toc_file.seek(toc_file.tell() + 32 * self.num_types)
        toc_start = toc_file.tell()
        for n in range(self.num_files):
            toc_file.seek(toc_start + n*80)
            toc_header = TocHeader()
            toc_header.from_memory_stream(toc_file)
            entry = None
            if toc_header.type_id == WWISE_BANK:
                entry = WwiseBank(toc_header)
                toc_data_offset = toc_header.toc_data_offset
                toc_file.seek(toc_data_offset)
                entry.toc_data_header = toc_file.read(16)
                #-------------------------------------
                bank = WwiseBank.BankParser()
                bank.load(toc_file.read(toc_header.toc_data_size-16))
                entry.bank_header = "BKHD".encode('utf-8') + len(bank.chunks["BKHD"]).to_bytes(4, byteorder="little") + bank.chunks["BKHD"]
                
                hirc = WwiseBank.HircReader(soundbank=entry)
                try:
                    hirc.load(bank.chunks['HIRC'])
                except KeyError:
                    continue
                entry.hierarchy = hirc
                #-------------------------------------
                entry.bank_misc_data = b''
                for chunk in bank.chunks.keys():
                    if chunk not in ["BKHD", "DATA", "DIDX", "HIRC"]:
                        entry.bank_misc_data = entry.bank_misc_data + chunk.encode('utf-8') + len(bank.chunks[chunk]).to_bytes(4, byteorder='little') + bank.chunks[chunk]
                        
                self.wwise_banks[entry.get_id()] = entry
            elif toc_header.type_id == WWISE_DEP: #wwise dep
                dep = WwiseDep(toc_header)
                toc_file.seek(toc_header.toc_data_offset)
                dep.from_memory_stream(toc_file)
                try:
                    self.wwise_banks[toc_header.file_id].dep = dep
                except KeyError:
                    pass
        
        #only include banks that contain at least 1 of the streams
        temp_banks = {}
        for key, bank in self.wwise_banks.items():
            include_bank = False
            for hierarchy_entry in bank.hierarchy.entries.values():
                for source in hierarchy_entry.sources:
                    if source.plugin_id == VORBIS and source.stream_type in [STREAM, PREFETCH_STREAM]:
                        stream_resource_id = murmur64_hash((os.path.dirname(bank.dep.data) + "/" + str(source.source_id)).encode('utf-8'))
                        for stream in self.wwise_streams.values():
                            if stream.get_id() == stream_resource_id:
                                include_bank = True
                                temp_banks[key] = bank
                                break
                    if include_bank:
                        break
                if include_bank:
                    break
        self.wwise_banks = temp_banks
        
        return True
        
