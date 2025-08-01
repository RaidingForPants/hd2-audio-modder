import numpy
import os
import pyaudio
import subprocess
import struct
import wave
import copy
import locale
import random
import xml.etree.ElementTree as etree
import posixpath as xpath
import asyncio

from typing import Callable, Literal, Union

from backend.db import SQLiteDatabase
from const import *
from env import *
import env
from xlocale import *
from util import *
import wwise_hierarchy_140
import wwise_hierarchy_154
from wwise_hierarchy_154 import WwiseHierarchy_154
from wwise_hierarchy_140 import WwiseHierarchy_140

from log import logger

class VideoSource:

    def __init__(self):
        self.replacement_filepath: str = ""
        self.filepath: str = ""
        self.video_size: int = 0
        self.replacement_video_size: int = 0
        self.replacement_video_offset: int = 0
        self.stream_offset: int = 0
        self.file_id: int = 0
        self.modified: bool = False

    def revert_modifications(self):
        self.modified = False

    def get_data(self):
        if not self.modified:
            with open(self.filepath+".stream", "rb") as f:
                f.seek(self.stream_offset)
                return f.read(self.video_size)
        else:
            with open(self.replacement_filepath, "rb") as f:
                f.seek(self.replacement_video_offset)
                return f.read(self.replacement_video_size)

    def set_data(self, replacement_filepath: str):
        self.replacement_filepath = replacement_filepath
        self.replacement_video_size = os.path.getsize(replacement_filepath)
        self.modified = True

    def get_id(self):
        return self.file_id

class AudioSource:

    def __init__(self):
        self.data: bytearray | Literal[b""] = b""
        self.size: int = 0
        self.resource_id: int = 0
        self.short_id: int = 0
        self.modified: bool = False
        self.data_old: bytearray | Literal[b""] = b""
        self.parents: set[wwise_hierarchy_154.HircEntry | wwise_hierarchy_140.HircEntry | WwiseStream] = set()
        self.stream_type: int = 0
        self.muted = False
        
    def set_data(self, data: bytearray, notify_subscribers: bool = True, set_modified: bool = True):
        if not self.modified and set_modified:
            self.data_old = self.data
        self.data = data
        self.size = len(self.data)
        if notify_subscribers:
            for item in self.parents:
                if not self.modified:
                    item.raise_modified()
                    if isinstance(item, (wwise_hierarchy_154.HircEntry, wwise_hierarchy_140.HircEntry)):
                        for bank in item.soundbanks:
                            bank.raise_modified()
        if set_modified:
            self.modified = True
            
    def get_id(self) -> int:
        if self.stream_type == BANK:
            return self.get_short_id()
        else:
            return self.get_resource_id()
            
    def is_modified(self) -> bool:
        return self.modified

    def get_data(self) -> bytearray:
        if not self.muted:
            return bytearray() if self.data == b"" else self.data 
        else:
            return b"" # returns wem with no samples
        
    def get_resource_id(self) -> int:
        return self.resource_id
        
    def get_short_id(self) -> int:
        return self.short_id
        
    def revert_modifications(self, notify_subscribers: bool = True):
        if self.modified:
            self.modified = False
            if self.data_old != b"":
                self.data = self.data_old
                self.data_old = b""
            self.size = len(self.data)
            if notify_subscribers:
                for item in self.parents:
                    item.lower_modified()
                    if isinstance(item, (wwise_hierarchy_154.HircEntry, wwise_hierarchy_140.HircEntry)):
                        for bank in item.soundbanks:
                            bank.lower_modified()
                

class TocHeader:

    def __init__(self):
        self.file_id = self.type_id = self.toc_data_offset = self.stream_file_offset = self.gpu_resource_offset = 0
        self.unknown1 = self.unknown2 = self.toc_data_size = self.stream_size = self.gpu_resource_size = 0
        self.unknown3 = 16
        self.unknown4 = 64
        self.entry_index = 0
        
    def from_memory_stream(self, stream: MemoryStream):
        self.file_id             = stream.uint64_read()
        self.type_id             = stream.uint64_read()
        self.toc_data_offset     = stream.uint64_read()
        self.stream_file_offset  = stream.uint64_read()
        self.gpu_resource_offset = stream.uint64_read()
        self.unknown1            = stream.uint64_read() #seems to contain duplicate entry index
        self.unknown2            = stream.uint64_read()
        self.toc_data_size       = stream.uint32_read()
        self.stream_size         = stream.uint32_read()
        self.gpu_resource_size   = stream.uint32_read()
        self.unknown3            = stream.uint32_read()
        self.unknown4            = stream.uint32_read()
        self.entry_index         = stream.uint32_read()
        
    def get_data(self) -> bytes:
        return (struct.pack("<QQQQQQQIIIIII",
            self.file_id,
            self.type_id,
            self.toc_data_offset,
            self.stream_file_offset,
            self.gpu_resource_offset,
            self.unknown1,
            self.unknown2,
            self.toc_data_size,
            self.stream_size,
            self.gpu_resource_size,
            self.unknown3,
            self.unknown4,
            self.entry_index))
                

class WwiseDep:

    def __init__(self):
        self.data: str = ""
        self.skip = True
        self.file_id = 0
        
    def from_memory_stream(self, stream: MemoryStream):
        self.offset = stream.tell()
        self.tag = stream.uint32_read()
        self.data_size = stream.uint32_read()
        self.skip = False
        self.data = stream.read(self.data_size).decode('utf-8')
        
    def get_data(self) -> bytes:
        return (self.tag.to_bytes(4, byteorder='little')
                + self.data_size.to_bytes(4, byteorder='little')
                + self.data.encode('utf-8'))
                

class DidxEntry:
    def __init__(self):
        self.id = self.offset = self.size = 0
        
    @classmethod
    def from_bytes(cls, bytes: bytes | bytearray):
        e = DidxEntry()
        e.id, e.offset, e.size = struct.unpack("<III", bytes)
        return e
        
    def get_data(self) -> bytes:
        return struct.pack("<III", self.id, self.offset, self.size)
        

class MediaIndex:

    def __init__(self):
        self.entries = {}
        self.data = {}
        
    def load(self, didxChunk: bytes | bytearray, dataChunk: bytes | bytearray):
        for n in range(int(len(didxChunk)/12)):
            entry = DidxEntry.from_bytes(didxChunk[12*n : 12*(n+1)])
            self.entries[entry.id] = entry
            self.data[entry.id] = dataChunk[entry.offset:entry.offset+entry.size]
        
    def get_data(self) -> bytes:
        arr = [x.get_data() for x in self.entries.values()]
        data_arr = self.data.values()
        return b"".join(arr) + b"".join(data_arr)
                         

class BankParser:
    
    def __init__(self):
        self.chunks = {}
        
    def load(self, bank_data: bytes | bytearray):
        self.chunks.clear()
        reader = MemoryStream()
        reader.write(bank_data)
        reader.seek(0)
        while True:
            tag = ""
            try:
                tag = reader.read(4).decode('utf-8')
            except:
                break
            size = reader.uint32_read()
            self.chunks[tag] = reader.read(size)
            
    def GetChunk(self, chunk_tag: str) -> bytearray:
        try:
            return self.chunks[chunk_tag]
        except:
            return bytearray()


class DummyBank:
    
    def __init__(self):
        self.header = bytes.fromhex("424B4844140000008D00000088EBF538A63FBFDE8947E009160D0000")
        self.audio_sources = []
        
    def set_audio_sources(self, audio_sources):
        self.audio_sources = audio_sources
        
    def to_file(self, filepath):
        data_array = []
        didx_array = []
        offset = 0
        
        for audio in self.audio_sources:
            data_array.append(audio.get_data())
            didx_array.append(struct.pack("<III", audio.get_short_id(), offset, audio.size))
            offset += audio.size
        
        data = bytearray()
        data += self.header
        data += "DIDX".encode('utf-8') + (12*len(didx_array)).to_bytes(4, byteorder="little")
        data += b"".join(didx_array)
        data += "DATA".encode('utf-8') + sum([len(x) for x in data_array]).to_bytes(4, byteorder="little")
        data += b"".join(data_array)
            
        with open(filepath, "wb") as f:
            f.write(data)


class WwiseBank:
    
    def __init__(self):
        self.bank_header: bytes = b""
        self.bank_misc_data: bytes = b""
        self.modified: bool = False
        self.dep: WwiseDep | None = None
        self.modified_count: int = 0
        self.hierarchy: WwiseHierarchy_154 | None = None
        self.content: list[int] = []
        self.file_id: int = 0
        
    def import_hierarchy(self, new_hierarchy: WwiseHierarchy_154):
        if self.hierarchy == None:
            raise RuntimeError(
                "No wwise hierarchy is assigned to this instance of "
                "WwiseHierarchy"
            )
        self.hierarchy.import_hierarchy(new_hierarchy)
        
    def add_content(self, content: int):
        self.content.append(content)
        
    def remove_content(self, content: int):
        try:
            self.content.remove(content)
        except:
            pass
            
    def get_content(self) -> list[int]:
        return self.content
        
    def raise_modified(self):
        self.modified = True
        self.modified_count += 1
        
    def lower_modified(self):
        if self.modified:
            self.modified_count -= 1
            if self.modified_count == 0:
                self.modified = False
        
    def get_name(self) -> str:
        if self.dep == None:
            raise AssertionError(
                "No WwiseDep instance is attached to this instance of WwiseBank"
            )

        return self.dep.data
        
    def get_id(self) -> int:
        try:
            return self.file_id
        except:
            return 0
            
    def generate(self, audio_sources) -> bytearray:
        if self.hierarchy == None:
            raise AssertionError(
                f"No WwiseHierarchy is attach to WwiseBank {self.file_id}"
            )

        data = bytearray()
        data += self.bank_header
        offset = 0
        
        #regenerate soundbank from the hierarchy information
        
        didx_array = []
        data_array = []
        
        added_sources = set()

        entries: list[wwise_hierarchy_140.Sound | wwise_hierarchy_140.MusicTrack | wwise_hierarchy_154.Sound | wwise_hierarchy_154.MusicTrack] = self.hierarchy.get_sounds() + self.hierarchy.get_music_tracks()
        for entry in entries:
            for source in entry.sources:
                if source.plugin_id == VORBIS:
                    try:
                        audio = audio_sources[source.source_id]
                    except KeyError as _:
                        continue
                    if source.stream_type == PREFETCH_STREAM and source.source_id not in added_sources:
                        data_array.append(audio.get_data()[:source.mem_size])
                        didx_array.append(struct.pack("<III", source.source_id, offset, source.mem_size))
                        offset += source.mem_size
                        added_sources.add(source.source_id)
                    elif source.stream_type == BANK and source.source_id not in added_sources:
                        data_array.append(audio.get_data())
                        didx_array.append(struct.pack("<III", source.source_id, offset, audio.size))
                        offset += audio.size
                        added_sources.add(source.source_id)
                elif source.plugin_id == REV_AUDIO:
                    try:
                        custom_fx_entry = self.hierarchy.entries[source.source_id]
                        fx_data = custom_fx_entry.get_data()
                        plugin_param_size = int.from_bytes(fx_data[13:17], byteorder="little")
                        media_index_id = int.from_bytes(fx_data[19+plugin_param_size:23+plugin_param_size], byteorder="little")
                        audio = audio_sources[media_index_id]
                    except KeyError:
                        continue
                    if source.stream_type == BANK and source.source_id not in added_sources:
                        data_array.append(audio.get_data())
                        didx_array.append(struct.pack("<III", media_index_id, offset, audio.size))
                        offset += audio.size
                        added_sources.add(media_index_id)
                        
        if len(didx_array) > 0:
            data += "DIDX".encode('utf-8') + (12*len(didx_array)).to_bytes(4, byteorder="little")
            data += b"".join(didx_array)
            data += "DATA".encode('utf-8') + sum([len(x) for x in data_array]).to_bytes(4, byteorder="little")
            data += b"".join(data_array)
            
        hierarchy_section = self.hierarchy.get_data()
        data += "HIRC".encode('utf-8') + len(hierarchy_section).to_bytes(4, byteorder="little")
        data += hierarchy_section
        data += self.bank_misc_data
        return data
        

class WwiseStream:

    def __init__(self):
        self.audio_source: AudioSource | None = None
        self.modified: bool = False
        self.file_id: int = 0
        
    def set_source(self, audio_source: AudioSource):
        if self.audio_source != None:
            self.audio_source.parents.remove(self)
        self.audio_source = audio_source
        audio_source.parents.add(self)
        
    def raise_modified(self):
        self.modified = True
        
    def lower_modified(self):
        self.modified = False
        
    def get_id(self) -> int:
        try:
            return self.file_id
        except:
            return 0
            
    def get_data(self) -> bytearray | bytes:
        if self.audio_source == None:
            raise AssertionError(
                f"No audio source is attached to WwiseStream {self.file_id}"
            )
        return self.audio_source.get_data()


class StringEntry:

    def __init__(self):
        self.text = ""
        self.text_old = ""
        self.string_id = 0
        self.modified = False
        self.parent: TextBank | None = None
        
    def get_id(self) -> int:
        return self.string_id
        
    def get_text(self) -> str:
        return self.text
        
    def set_text(self, text: str):
        if not self.modified:
            self.text_old = self.text
            if self.parent != None:
                self.parent.raise_modified()
        self.modified = True
        self.text = text
        
    def revert_modifications(self):
        if self.modified:
            self.text = self.text_old
            self.modified = False
            if self.parent != None:
                self.parent.lower_modified()
        
class TextBank:
    
    def __init__(self):
        self.file_id = 0
        self.entries = {}
        self.language = 0
        self.modified = False
        self.modified_count = 0
     
    def set_data(self, data: bytearray):
        self.entries.clear()
        num_entries = int.from_bytes(data[8:12], byteorder='little')
        self.language = int.from_bytes(data[12:16], byteorder='little')
        id_section_start = 16
        offset_section_start = id_section_start + 4 * num_entries
        data_section_start = offset_section_start + 4 * num_entries
        ids = data[id_section_start:offset_section_start]
        offsets = data[offset_section_start:data_section_start]
        for n in range(num_entries):
            entry = StringEntry()
            entry.parent = self
            string_id = int.from_bytes(ids[4*n:+4*(n+1)], byteorder="little")
            string_offset = int.from_bytes(offsets[4*n:4*(n+1)], byteorder="little")
            entry.string_id = string_id
            stopIndex = string_offset + 1
            while data[stopIndex] != 0:
                stopIndex += 1
            entry.text = data[string_offset:stopIndex].decode('utf-8')
            self.entries[string_id] = entry
            
    def revert_modifications(self, entry_id: int = 0):
        if entry_id:
            self.entries[entry_id].revert_modifications()
        else:
            for entry in self.entries.values():
                entry.revert_modifications()
            
    def update(self):
        pass
        
    def get_language(self) -> int:
        return self.language
        
    def is_modified(self) -> bool:
        return self.modified

    def import_text(self, text_bank: "TextBank"):
        for new_string_entry in text_bank.entries.values():
            try:
                old_string_entry = self.entries[new_string_entry.string_id]
            except:
                continue
            if (old_string_entry.modified and new_string_entry.get_text() != old_string_entry.text_old
                or (not old_string_entry.modified and new_string_entry.get_text() != old_string_entry.get_text())
            ):
                old_string_entry.set_text(new_string_entry.get_text())
        
    def generate(self) -> bytearray:
        stream = MemoryStream()
        stream.write(b'\xae\xf3\x85\x3e\x01\x00\x00\x00')
        stream.write(len(self.entries).to_bytes(4, byteorder="little"))
        stream.write(self.language.to_bytes(4, byteorder="little"))
        offset = 16 + 8*len(self.entries)
        for entry in self.entries.values():
            stream.write(entry.get_id().to_bytes(4, byteorder="little"))
        for entry in self.entries.values():
            stream.write(offset.to_bytes(4, byteorder="little"))
            initial_position = stream.tell()
            stream.seek(offset)
            text_bytes = entry.text.encode('utf-8') + b'\x00'
            stream.write(text_bytes)
            offset += len(text_bytes)
            stream.seek(initial_position)
        return stream.data
        
    def get_id(self) -> int:
        return self.file_id
            
    def raise_modified(self):
        self.modified_count+=1
        self.modified = True
        
    def lower_modified(self):
        if self.modified:
            self.modified_count-=1
            if self.modified_count == 0:
                self.modified = False

class GameArchive:
    
    def __init__(self):
        self.magic: int = -1
        self.name: str = ""
        self.num_files: int = -1
        self.num_types: int = -1
        self.path: str = ""
        self.unk4Data: bytes | bytearray = b""
        self.unknown: int = -1
        self.wwise_streams: dict[int, WwiseStream] = {}
        self.wwise_banks: dict[int, WwiseBank] = {}
        self.audio_sources: dict[int, AudioSource] = {}
        self.hierarchy_entries: dict[int, wwise_hierarchy_140.HircEntry | wwise_hierarchy_154.HircEntry] = {}
        self.video_sources: dict[int, VideoSource] = {}
        self.text_banks = {}
    
    @classmethod
    def from_file(cls, path: str) -> 'GameArchive': 
        archive = GameArchive()
        archive.name = os.path.basename(path)
        archive.path = path
        toc_file = MemoryStream()
        with open(path, 'r+b') as f:
            toc_file = MemoryStream(f.read())

        stream_file = MemoryStream()
        if os.path.isfile(path+".stream"):
            with open(path+".stream", 'r+b') as f:
                stream_file = MemoryStream(f.read())
        archive.load(toc_file, stream_file)
        return archive
        
    def get_wwise_streams(self) -> dict[int, WwiseStream]:
        return self.wwise_streams
        
    def get_wwise_banks(self) -> dict[int, WwiseBank]:
        return self.wwise_banks
        
    def get_audio_sources(self) -> dict[int, AudioSource]:
        return self.audio_sources

    def get_video_sources(self) -> dict[int, VideoSource]:
        return self.video_sources

    def get_text_banks(self) -> dict[int, TextBank]:
        return self.text_banks

    def get_hierarchy_entries(self) -> dict[int, wwise_hierarchy_140.HircEntry | wwise_hierarchy_154.HircEntry]:
        return self.hierarchy_entries

    def write_type_header(self, toc_file: MemoryStream, entry_type: int, num_entries: int):
        if num_entries > 0:
            toc_file.write(struct.pack("<QQQII", 0, entry_type, num_entries, 16, 64))
        
    def to_file(self, path: str):
        toc_file = MemoryStream()
        stream_file = MemoryStream()
        wwise_deps = [bank.dep for bank in self.wwise_banks.values() if not bank.dep.skip]
        self.num_files = len(self.wwise_streams) + len(self.wwise_banks) + len(wwise_deps) + len(self.text_banks) + len(self.video_sources)
        self.num_types = 0
        for item in [self.wwise_streams, self.wwise_banks, self.text_banks, self.video_sources, wwise_deps]:
            if item:
                self.num_types += 1
        
        # write header
        toc_file.write(struct.pack("<IIII56s", self.magic, self.num_types, self.num_files, self.unknown, self.unk4Data))
        
        self.write_type_header(toc_file, WWISE_STREAM, len(self.wwise_streams))
        self.write_type_header(toc_file, WWISE_BANK, len(self.wwise_banks))
        self.write_type_header(toc_file, WWISE_DEP, len(wwise_deps))
        self.write_type_header(toc_file, TEXT_BANK, len(self.text_banks))
        self.write_type_header(toc_file, BINK_VIDEO, len(self.video_sources))
        
        toc_data_offset = toc_file.tell() + 80 * self.num_files + 8
        stream_file_offset = 0
        
        # generate data and toc entries
        toc_entries = []
        toc_data = []
        stream_data = []
        entry_index = 0
        
        for stream in self.wwise_streams.values():
            s_data = pad_to_16_byte_align(stream.get_data())
            t_data = bytes.fromhex("D82F767800000000") + struct.pack("<Q", len(stream.get_data()))
            toc_entry = TocHeader()
            toc_entry.file_id = stream.get_id()
            toc_entry.type_id = WWISE_STREAM
            toc_entry.toc_data_offset = toc_data_offset
            toc_entry.stream_file_offset = stream_file_offset
            toc_entry.toc_data_size = 0x0C
            toc_entry.stream_size = len(stream.get_data())
            toc_entry.entry_index = entry_index
            stream_data.append(s_data)
            toc_data.append(t_data)
            toc_entries.append(toc_entry)
            entry_index += 1
            stream_file_offset += len(s_data)
            toc_data_offset += 16
            
        
        for bank in self.wwise_banks.values():
            bank_data = bank.generate(self.audio_sources)
            toc_entry = TocHeader()
            toc_entry.file_id = bank.get_id()
            toc_entry.type_id = WWISE_BANK
            toc_entry.toc_data_offset = toc_data_offset
            toc_entry.stream_file_offset = stream_file_offset
            toc_entry.toc_data_size = len(bank_data) + 16
            toc_entry.entry_index = entry_index
            toc_entries.append(toc_entry)
            bank_data = b"".join([bytes.fromhex("D82F7678"), len(bank_data).to_bytes(4, byteorder="little"), bank.get_id().to_bytes(8, byteorder="little"), pad_to_16_byte_align(bank_data)])
            toc_data.append(bank_data)
            
            toc_data_offset += len(bank_data)
            entry_index += 1
            
        for text_bank in self.text_banks.values():
            text_data = text_bank.generate()
            toc_entry = TocHeader()
            toc_entry.file_id = text_bank.get_id()
            toc_entry.type_id = TEXT_BANK
            toc_entry.toc_data_offset = toc_data_offset
            toc_entry.stream_file_offset = stream_file_offset
            toc_entry.toc_data_size = len(text_data)
            toc_entry.entry_index = entry_index
            text_data = pad_to_16_byte_align(text_data)
            
            toc_entries.append(toc_entry)
            toc_data.append(text_data)
            
            toc_data_offset += len(text_data)
            entry_index += 1
        
        for dep in wwise_deps:
            dep_data = dep.get_data()
            toc_entry = TocHeader()
            toc_entry.file_id = dep.file_id
            toc_entry.type_id = WWISE_DEP
            toc_entry.toc_data_offset = toc_data_offset
            toc_entry.stream_file_offset = stream_file_offset
            toc_entry.toc_data_size = len(dep_data)
            toc_entry.entry_index = entry_index
            toc_entries.append(toc_entry)
            dep_data = pad_to_16_byte_align(dep_data)
            toc_data.append(dep_data)
            
            toc_data_offset += len(dep_data)
            entry_index += 1

        for video in self.video_sources.values():
            data = video.get_data()
            s_data = pad_to_16_byte_align(data)
            t_data = bytes.fromhex("E9030000000000000000000000000000")
            toc_entry = TocHeader()
            toc_entry.file_id = video.file_id
            toc_entry.type_id = BINK_VIDEO
            toc_entry.toc_data_offset = toc_data_offset
            toc_entry.stream_file_offset = stream_file_offset
            toc_entry.toc_data_size = 0x10
            toc_entry.stream_size = len(data)
            toc_entry.entry_index = entry_index
            stream_data.append(s_data)
            toc_data.append(t_data)
            toc_entries.append(toc_entry)
            entry_index += 1
            stream_file_offset += len(s_data)
            toc_data_offset += 16
            
        toc_file.write(b"".join([entry.get_data() for entry in toc_entries]))
        toc_file.advance(8)
        toc_file.write(b"".join(toc_data))
        stream_file.write(b"".join(stream_data))

        with open(os.path.join(path, self.name), 'w+b') as f:
            f.write(toc_file.data)
            
        if len(stream_file.data) > 0:
            with open(os.path.join(path, self.name+".stream"), 'w+b') as f:
                f.write(stream_file.data)

    def load(self, toc_file: MemoryStream, stream_file: MemoryStream):
        self.wwise_streams.clear()
        self.wwise_banks.clear()
        self.audio_sources.clear()
        self.video_sources.clear()
        self.text_banks.clear()
        self.hierarchy_entries.clear()
        
        media_index = MediaIndex()
        
        self.magic      = toc_file.uint32_read()
        if self.magic != 0xF0000011: return False

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
                entry = WwiseStream()
                entry.file_id = toc_header.file_id
                toc_file.seek(toc_header.toc_data_offset)
                stream_file.seek(toc_header.stream_file_offset)
                audio.set_data(stream_file.read(toc_header.stream_size), notify_subscribers=False, set_modified=False)
                audio.resource_id = toc_header.file_id
                entry.set_source(audio)
                self.wwise_streams[entry.get_id()] = entry
            elif toc_header.type_id == WWISE_BANK:
                entry = WwiseBank()
                toc_file.seek(toc_header.toc_data_offset)
                toc_file.advance(16)
                entry.file_id = toc_header.file_id
                bank = BankParser()
                bank.load(toc_file.read(toc_header.toc_data_size-16))
                entry.bank_header = "BKHD".encode('utf-8') + len(bank.chunks["BKHD"]).to_bytes(4, byteorder="little") + bank.chunks["BKHD"]
                bank_version = int.from_bytes(bank.chunks['BKHD'][0:4], "little") ^ BANK_VERSION_KEY
                if bank_version == 154:
                    hirc = WwiseHierarchy_154(soundbank=entry)
                else:
                    hirc = WwiseHierarchy_140(soundbank=entry)
                try:
                    hirc.load(bank.chunks['HIRC'])
                except KeyError:
                    pass
                replacements = {}
                for hirc_id, hirc_entry in hirc.entries.items():
                    if hirc_id in self.hierarchy_entries:
                        existing_entry = self.hierarchy_entries[hirc_id]
                        # rearrange stuff
                        if isinstance(hirc_entry, (wwise_hierarchy_140.ActorMixer, wwise_hierarchy_140.SwitchContainer, wwise_hierarchy_140.RandomSequenceContainer, wwise_hierarchy_140.LayerContainer, wwise_hierarchy_140.MusicSwitchContainer
                                                   , wwise_hierarchy_154.ActorMixer, wwise_hierarchy_154.SwitchContainer, wwise_hierarchy_154.RandomSequenceContainer, wwise_hierarchy_154.LayerContainer, wwise_hierarchy_154.MusicSwitchContainer)):
                            for child in hirc_entry.children.children:
                                if child not in existing_entry.children.children:
                                    existing_entry.children.children.append(child)
                                    existing_entry.children.numChildren += 1
                                    existing_entry.size += 4
                        existing_entry.soundbanks.append(entry)
                        replacements[hirc_id] = existing_entry
                    else:
                        self.hierarchy_entries[hirc_id] = hirc_entry
                for hirc_id, hirc_entry in replacements.items():
                    hirc._remove_categorized_entry(hirc.entries[hirc_id])
                    hirc._categorized_entry(hirc_entry)
                hirc.entries.update(replacements)
                entry.hierarchy = hirc
                #Add all bank sources to the source list
                if "DIDX" in bank.chunks.keys():
                    media_index.load(bank.chunks["DIDX"], bank.chunks["DATA"])
                
                entry.bank_misc_data = b''
                for chunk in bank.chunks.keys():
                    if chunk not in ["BKHD", "DATA", "DIDX", "HIRC"]:
                        entry.bank_misc_data = entry.bank_misc_data + chunk.encode('utf-8') + len(bank.chunks[chunk]).to_bytes(4, byteorder='little') + bank.chunks[chunk]

                # create default dependency
                dep = WwiseDep()
                dep.skip = True
                dep.data = f"Bank {entry.get_id()}"
                dep.file_id = toc_header.file_id
                entry.dep = dep

                self.wwise_banks[entry.get_id()] = entry
            elif toc_header.type_id == WWISE_DEP: #wwise dep
                dep = WwiseDep()
                dep.file_id = toc_header.file_id
                toc_file.seek(toc_header.toc_data_offset)
                dep.from_memory_stream(toc_file)
                try:
                    self.wwise_banks[toc_header.file_id].dep = dep
                except KeyError:
                    pass
            elif toc_header.type_id == TEXT_BANK: #string_entry
                toc_file.seek(toc_header.toc_data_offset)
                data = toc_file.read(toc_header.toc_data_size)
                text_bank = TextBank()
                text_bank.file_id = toc_header.file_id
                text_bank.set_data(data)
                self.text_banks[text_bank.get_id()] = text_bank
            elif toc_header.type_id == BINK_VIDEO:
                new_video_source = VideoSource()
                new_video_source.file_id = toc_header.file_id
                new_video_source.stream_offset = toc_header.stream_file_offset
                new_video_source.video_size = toc_header.stream_size
                new_video_source.filepath = self.path
                self.video_sources[new_video_source.file_id] = new_video_source

        
        # Create all AudioSource objects

        self._create_all_audio_source_objects(media_index)

        # Construct list of audio sources in each bank
        self._book_keep_audio_sources_per_bank()

    def _create_all_audio_source_objects(self, media_index: MediaIndex):
       for bank in self.wwise_banks.values():
           self._create_all_audio_source_objects_from_bank(bank, media_index)

    def _create_all_audio_source_objects_from_bank(
        self, bank: WwiseBank, media_index: MediaIndex
    ):
        if bank.hierarchy == None:
            raise AssertionError(f"WwiseBank {bank.file_id} has no WwiseHierarchy")
        if bank.dep == None:
            raise AssertionError(f"WwiseBank {bank.file_id} has no WwiseDep")

        hirc = bank.hierarchy
        dep = bank.dep

        entries_with_audio_sources = hirc.get_sounds() + hirc.get_music_tracks()
        for entry_with_audio_source in entries_with_audio_sources:
            for source_struct in entry_with_audio_source.sources:
                audio_source = self._create_audio_source(
                    source_struct, media_index, hirc, dep
                )
                if audio_source == None:
                    continue
                self.audio_sources[audio_source.short_id] = audio_source


    def _create_audio_source(
        self, 
        source: wwise_hierarchy_140.BankSourceStruct | wwise_hierarchy_154.BankSourceStruct,
        media_index: MediaIndex,
        hirc: WwiseHierarchy_154,
        dep: WwiseDep
    ) -> AudioSource | None:
        """
        Question: for REV_AUDIO, it uses media index ID. Should we use source 
        ID to check for duplication again?
        """
        source_id = source.source_id
        if source_id in self.audio_sources:
            logger.info(
                f"Audio source {source_id} already registered. Skipping audio "
                f"source {source_id}..."
            )
            return None

        plugin_id = source.plugin_id
        if plugin_id not in [VORBIS, REV_AUDIO]:
            logger.info(
               f"Audio source {source_id} has plugin ID {plugin_id}. Audio "
                "tool currently can only unpack audio source with plugin_id of "
               f"{VORBIS} or {REV_AUDIO}"
            )
            return None

        stream_type = source.stream_type
        if stream_type not in [BANK, STREAM, PREFETCH_STREAM]:
            logger.warning(
                f"Audio source {source_id} has stream type: {stream_type}. Audio"
                 "tool currently can only unpack audio source with stream type  "
                f"{BANK}, {STREAM}, or {PREFETCH_STREAM}."
            )
            return None

        if stream_type == BANK and plugin_id == REV_AUDIO:
            if not hirc.has_entry(source_id):
                logger.warning(
                    f"There's no custom FX hierarchy entry associated with audio"
                    f" source {source_id}!"
                )
                return None
            return self._create_audio_source_type_rev_audio(
                hirc.get_entry(source_id), media_index
            )
        if stream_type == BANK:
            if source_id not in media_index.data:
                logger.warning(
                    "There is no media index data associated with audio source ID "
                   f"{source_id}"
                )
                return None
            return self._create_audio_source_type_bank(source, media_index)
        if stream_type in [STREAM, PREFETCH_STREAM]:
            return self._create_audio_source_type_stream(source, dep)

        raise AssertionError("Invalid code path!")
    
    @staticmethod
    def _create_audio_source_type_bank(
        source: wwise_hierarchy_140.BankSourceStruct | wwise_hierarchy_154.BankSourceStruct, media_index: MediaIndex
    ) -> AudioSource:
        audio = AudioSource()
        audio.stream_type = BANK
        audio.short_id = source.source_id
        audio.set_data(
            media_index.data[source.source_id],
            set_modified=False,
            notify_subscribers=False
        )

        return audio

    def _create_audio_source_type_rev_audio(
        self, 
        custom_fx_entry: wwise_hierarchy_140.HircEntry | wwise_hierarchy_154.HircEntry,
        media_index: MediaIndex,
    ) -> AudioSource | None:
        # TODO: This should be parsed and organized in the parsing phase
        data = custom_fx_entry.get_data()
        plugin_param_size = int.from_bytes(data[13:17], byteorder="little")

        plugin_data_start = 19 + plugin_param_size
        plugin_data_end = 23 + plugin_param_size

        media_index_id = int.from_bytes(
            data[plugin_data_start:plugin_data_end], byteorder="little"
        )
        if media_index_id not in media_index.data:
            logger.warning(
                f"There is no media index data associated with {media_index_id}"
            )
            return None

        audio = AudioSource()
        audio.stream_type = BANK
        audio.short_id = media_index_id
        audio.set_data(
            media_index.data[media_index_id],
            set_modified=False,
            notify_subscribers=False
        )

        return audio

    def _create_audio_source_type_stream(
        self,
        source: wwise_hierarchy_140.BankSourceStruct | wwise_hierarchy_154.BankSourceStruct,
        dep: WwiseDep
    ) -> AudioSource | None:
        stream_resource_id = murmur64_hash(
            (os.path.dirname(dep.data) + "/" + str(source.source_id)).encode('utf-8')
        )
        if stream_resource_id not in self.wwise_streams:
            logger.warning(
                "There is no WwiseStream associated with stream resource ID"
               f"{stream_resource_id}"
            )
            return None

        audio = self.wwise_streams[stream_resource_id].audio_source
        if audio == None:
            logger.warning(
                f"WwiseStream {stream_resource_id} has no audio source."
            )
            return None
        audio.short_id = source.source_id
        return audio

    def _book_keep_audio_sources_per_bank(self):
        for bank in self.wwise_banks.values():
            if bank.hierarchy == None:
                raise AssertionError(
                    f"WwiseBank {bank.file_id} has no WwiseHierarchy"
                )

            bank_audio_sources = bank.get_content()
            music_tracks = bank.hierarchy.get_music_tracks()
            for music_track in music_tracks:
                for info in music_track.track_info:
                    source_id = info.source_id
                    if source_id == 0:
                        continue
                    if source_id not in self.audio_sources:
                        logger.warning(
                             "There is no audio source associated with audio "
                            f"source ID {source_id}."
                        )
                        continue
                    """
                    TODO: determine whether if adding TrackInfoStruct into 
                    audio source
                    """
                for source in music_track.sources:
                    if source.plugin_id != VORBIS:
                        continue
                    source_id = source.source_id
                    if source_id not in self.audio_sources:
                        logger.warning(
                            f"Audio source {source_id} is not tracked and registered "
                            f"in the list of all audio sources!",
                        )
                        continue
                    self.audio_sources[source_id].parents.add(music_track)
                    if source_id not in bank_audio_sources:
                        bank.add_content(source_id)

            sounds = bank.hierarchy.get_sounds()
            for sound in sounds:
                assert_equal(
                    "Sound object should only one single audio source but Sound "
                   f" {sound.hierarchy_id} does not.",
                    1,
                    len(sound.sources),
                )

                source = sound.sources[0]
                source_id = source.source_id
                if source_id not in self.audio_sources:
                    logger.warning(
                        f"Audio source {source_id} is not tracked and registered "
                        f"in the list of all audio sources!",
                    )
                    continue
                
                if source.plugin_id != VORBIS:
                    continue
                audio_source = self.audio_sources[source_id]
                audio_source.parents.add(sound)
                if audio_source.get_short_id() not in bank_audio_sources:
                    bank.add_content(audio_source.get_short_id())

        
class SoundHandler:
    
    handler_instance: Union['SoundHandler', None] = None
    
    def __init__(self, start_func = None, update_func = None):
        self.audio_process = None
        self.wave_object = None
        self.audio_id = 0
        self.playing = False
        self.audio_file = ""
        self.wave_file = None
        self.frame_count = 0
        self.audio = pyaudio.PyAudio()
        self.update_func = update_func
        self.start_func = start_func
        
    @classmethod
    def create_instance(cls):
        cls.handler_instance = SoundHandler()
        
    @classmethod
    def get_instance(cls) -> 'SoundHandler':
        if cls.handler_instance == None:
            cls.handler_instance = SoundHandler()
        return cls.handler_instance
        
    def kill_sound(self):
        if self.audio_process is not None:
            if self.callback is not None:
                try:
                    self.callback()
                except:
                    pass
                self.callback = None
            self.audio_process.close()
            self.wave_file.close()
            try:
                os.remove(self.audio_file)
            except:
                pass
            self.audio_process = None
            self.playing = False
        
    def play_audio(self, sound_id: int, sound_data: bytearray, callback: Callable | None = None):
        if not os.path.exists(VGMSTREAM):
            return
        self.kill_sound()
        self.callback = callback
        if self.wave_file is not None:
            self.wave_file.close()
        if self.audio_process is not None:
            self.audio_process.close()
        if os.path.exists(self.audio_file):
            try:
                os.remove(self.audio_file)
            except OSError:
                pass
        filename = f"temp{sound_id}"
        if not os.path.isfile(f"{filename}.wav"):
            with open(f'{os.path.join(TMP, filename)}.wem', 'wb') as f:
                f.write(sound_data)
            process = subprocess.run([VGMSTREAM, "-o", f"{os.path.join(TMP, filename)}.wav", f"{os.path.join(TMP, filename)}.wem"], stdout=subprocess.DEVNULL)
            os.remove(f"{os.path.join(TMP, filename)}.wem")
            if process.returncode != 0:
                logger.error(f"Encountered error when converting {sound_id}.wem for playback")
                self.callback = None
                return
            
        self.audio_id = sound_id
        self.wave_file = wave.open(f"{os.path.join(TMP, filename)}.wav")
        self.audio_file = f"{os.path.join(TMP, filename)}.wav"
        self.frame_count = 0
        self.frame_count_timer = 0
        self.max_frames = self.wave_file.getnframes()
        if self.start_func is not None:
            self.start_func(self.max_frames / self.wave_file.getframerate())
        
        def read_stream(
            _, 
            frame_count, 
            __, 
            ___
        ):
            self.frame_count += frame_count
            self.frame_count_timer += frame_count
            if self.frame_count > self.max_frames:
                if self.callback is not None:
                    self.callback()
                return (None, pyaudio.paComplete)
            data = self.wave_file.readframes(frame_count)
            if self.wave_file.getnchannels() > 2:
                data = self.downmix_to_stereo(data, self.wave_file.getnchannels(), self.wave_file.getsampwidth(), frame_count)
            if self.update_func is not None and self.frame_count_timer > self.wave_file.getframerate() / 10:
                self.frame_count_timer = 0
                self.update_func(self.frame_count / self.wave_file.getframerate())
            return (data, pyaudio.paContinue)

        self.audio_process = self.audio.open(format=self.audio.get_format_from_width(self.wave_file.getsampwidth()),
                channels = min(self.wave_file.getnchannels(), 2),
                rate=self.wave_file.getframerate(),
                output=True,
                stream_callback=read_stream)
        self.audio_file = f"{os.path.join(TMP, filename)}.wav"
        self.playing = True

    def toggle_play_pause(self):
        if self.audio_process is not None:
            if self.playing:
                self.playing = False
                self.audio_process.stop_stream()
            elif not self.playing and self.audio_id != 0:
                self.playing = True
                self.audio_process.start_stream()

    def pause(self):
        if self.audio_process is not None:
            if self.playing:
                self.playing = False
                try:
                    self.audio_process.stop_stream()
                except:
                    self.audio_process.close()
                    self.audio_process = None

    def play(self):
        if self.audio_process is not None:
            if not self.playing and self.audio_id != 0:
                self.playing = True
                self.audio_process.start_stream()

    def seek(self, time):
        if self.wave_file is not None:
            new_frame = int(time*self.wave_file.getframerate())
            self.wave_file.setpos(new_frame)
            self.frame_count = new_frame
        
    def downmix_to_stereo(self, data: bytearray, channels: int, channel_width: int, frame_count: int) -> bytes:
        if channel_width == 2:
            arr = numpy.frombuffer(data, dtype=numpy.int16)
            stereo_array = numpy.zeros(shape=(frame_count, 2), dtype=numpy.int16)
        elif channel_width == 1:
            arr = numpy.frombuffer(data, dtype=numpy.int8)
            stereo_array = numpy.zeros(shape=(frame_count, 2), dtype=numpy.int8)
        elif channel_width == 4:
            arr = numpy.frombuffer(data, dtype=numpy.int32)
            stereo_array = numpy.zeros(shape=(frame_count, 2), dtype=numpy.int32)
        arr = arr.reshape((frame_count, channels)) # type: ignore

        for index, frame in enumerate(arr):
            stereo_array[index][0] = frame[0]  # type: ignore
            stereo_array[index][1] = frame[1]  # type: ignore

        return stereo_array.tobytes()  # type: ignore

class Mod:

    def __init__(self, name: str, db: SQLiteDatabase):
        self.db = db
        self.wwise_streams: dict[int, WwiseStream] = {}
        self.stream_count: dict[int, int] = {}
        self.wwise_banks: dict[int, WwiseBank] = {}
        self.bank_count: dict[int, int] = {}
        self.audio_sources: dict[int, AudioSource] = {}
        self.audio_count: dict[int, int] = {}
        self.text_banks: dict[int, TextBank] = {}
        self.text_count = {}
        self.video_sources: dict[int, VideoSource] = {}
        self.video_count: dict[int, int] = {}
        self.hierarchy_entries: dict[int, wwise_hierarchy_140.HircEntry | wwise_hierarchy_154.HircEntry] = {}
        self.hierarchy_count: dict[int, int] = {}
        self.game_archives: dict[str, GameArchive] = {}
        self.name: str = name
        
    def revert_all(self):
        for audio in self.audio_sources.values():
            audio.revert_modifications()
        for bank in self.wwise_banks.values():
            if bank.hierarchy == None:
                raise AssertionError(
                    f"WwiseBank {bank.file_id} does not have a WwiseHierarchy"
                )
            bank.hierarchy.revert_modifications()
        for bank in self.text_banks.values():
            bank.revert_modifications()
        for video in self.video_sources.values():
            video.revert_modifications()
        
    def revert_audio(self, file_id: int):
        audio = self.get_audio_source(file_id)
        audio.revert_modifications()

    def revert_video(self, file_id: int):
        video = self.get_video_source(file_id)
        video.revert_modifications()

    def get_video_source(self, file_id: int):
        try:
            return self.video_sources[file_id]
        except KeyError:
            raise KeyError(f"Cannot find video with id {file_id}")
        
    def add_new_hierarchy_entry(self, soundbank_id: int, entry: wwise_hierarchy_140.HircEntry | wwise_hierarchy_154.HircEntry):
        bank = self.get_wwise_bank(soundbank_id)
        if bank.hierarchy == None:
            raise AssertionError(f"WwiseBank {soundbank_id} with no WwiseHierarchy")
        if bank in entry.soundbanks:
            raise Exception(f"Entry {entry.hierarchy_id} already exists in soundbank {soundbank_id}!")
        if entry.hierarchy_id in self.hierarchy_entries:
            entry = self.hierarchy_entries[entry.hierarchy_id]
            self.hierarchy_count[entry.hierarchy_id] = self.hierarchy_count[entry.hierarchy_id] + 1
        else:
            self.hierarchy_count[entry.hierarchy_id] = 1
            self.hierarchy_entries[entry.hierarchy_id] = entry
        bank.hierarchy.add_entry(entry)
        
    def remove_hierarchy_entry(self, soundbank_id: int, entry_id: int):
        if entry_id not in self.hierarchy_entries:
            raise AssertionError(f"Hierarchy entry {entry_id} not found")
        bank = self.get_wwise_bank(soundbank_id)
        if bank.hierarchy == None:
            raise AssertionError(f"WwiseBank {soundbank_id} with no WwiseHierarchy")
        entry = self.get_hierarchy_entry(entry_id)
        bank.hierarchy.remove_entry(entry)
        if self.hierarchy_count[entry_id] > 1:
            self.hierarchy_count[entry_id] = self.hierarchy_count[entry_id] - 1
        else:
            del self.hierarchy_count[entry_id]
            del self.hierarchy_entries[entry_id]
            
        
    def revert_hierarchy_entry(self, soundbank_id: int, entry_id: int):
        self.get_hierarchy_entry(entry_id).revert_modifications()
        
    def revert_string_entry(self, textbank_id: int, entry_id: int):
        self.get_string_entry(textbank_id, entry_id).revert_modifications()
        
    def revert_text_bank(self, textbank_id: int):
        self.get_text_bank(textbank_id).revert_modifications()
        
    def revert_wwise_hierarchy(self, soundbank_id: int): 
        bank = self.get_wwise_bank(soundbank_id)
        if bank.hierarchy == None:
            raise AssertionError(f"WwiseBank {soundbank_id} with no WwiseHierarchy")
        bank.hierarchy.revert_modifications()
        
    def revert_wwise_bank(self, soundbank_id: int):
        self.revert_wwise_hierarchy(soundbank_id)
        for audio_id in self.get_wwise_bank(soundbank_id).get_content():
            audio = self.get_audio_source(audio_id)
            audio.revert_modifications()

    def reroute_sound(self, sound: wwise_hierarchy_140.Sound | wwise_hierarchy_154.Sound, audio_data: bytearray):
        """
        @exception
        - AssertionError
        - NotImplementedError
        - KeyError
        """
        if len(sound.sources) != 1:
            raise AssertionError(
                "There are more than one audio source in a Sound object."
            )

        source_struct = sound.sources[0]
        if source_struct.plugin_id != VORBIS:
            raise NotImplementedError(
                "Sound rerouting only work with VORBIS type of audio source."
               f" The Sound object {sound.hierarchy_id} has plugin id"
               f" {source_struct.plugin_id}."
            )
        
        short_id = wwise_hierarchy_154.ak_media_id(self.db)
        if short_id in self.audio_sources:
            raise KeyError(
                f"Audio source short ID {short_id} already exists. Please retry "
                f"with this method call."
            )

        # Create new AudioSource
        audio_source = AudioSource()
        audio_source.data = audio_data
        audio_source.size = len(audio_data)
        audio_source.short_id = short_id
        audio_source.data_old = audio_data
        audio_source.parents.add(sound)
        audio_source.stream_type = BANK

        # Update BankSourceStruct
        source_struct.source_id = short_id

        # Mark sound is modified
        sound.raise_modified()

        # Update WwiseBank audio source list
        bank = sound.soundbank
        if not isinstance(bank, WwiseBank): 
            raise AssertionError(
                f"Sound object {sound.hierarchy_id} sound bank field is not "
                 "an instance of sound bank."
            )
        bank.content.append(audio_source)

        # Update Mod audio source list
        self.audio_sources[short_id] = audio_source
        self.audio_count[short_id] = 1
        
    def dump_as_wem(self, file_id: int, output_path: str = ""):
        """
        @exception
        - ValueError
            - Empty output file name
        """
        if output_path == "":
            raise ValueError("Invalid output filename!")
        with open(output_path, "wb") as f:
            f.write(self.get_audio_source(file_id).get_data())
        
    def dump_as_wav(self, file_id: int, output_file: str = "", muted: bool = False):
        """
        @exception
        - ValueError
            - Empty output file name
        """
        if output_file == "":
            raise ValueError("Invalid output filename!")

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

        with open(f"{save_path}.wem", 'wb') as f:
            f.write(self.get_audio_source(file_id).get_data())

        process = subprocess.run([
            VGMSTREAM, "-o", f"{save_path}.wav", f"{save_path}.wem"
            ],
            stdout=subprocess.DEVNULL
        )
        
        if process.returncode != 0:
            logger.error(f"Encountered error when converting {file_id}.wem into .wav format")

        os.remove(f"{save_path}.wem")
        
    def dump_multiple_as_wem(self, file_ids: list[int], output_folder: str = ""):
        """
        @exception
        - OSError
            - output_folder does not exist
        """
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise OSError(f"Invalid output folder '{output_folder}'")

        for file_id in file_ids:
            audio = self.get_audio_source(file_id)
            if audio is not None:
                save_path = os.path.join(output_folder, f"{audio.get_id()}")
                with open(save_path+".wem", "wb") as f:
                    f.write(audio.get_data())
                    
    def create_dummy_bank(self, file_ids: list[int], output_filepath: str):
        bank = DummyBank()
        bank.set_audio_sources([self.get_audio_source(int(file_id)) for file_id in file_ids])
        bank.to_file(output_filepath)
    
    async def dump_from_bank_file(self, output_folder: str, bank_filepath: str):
        process = await asyncio.create_subprocess_exec(
            VGMSTREAM, "-S", "0", "-o", os.path.join(output_folder, "?n.wav"), bank_filepath,
            stdout=subprocess.DEVNULL,
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Encountered error when converting to .wav")
        
    def dump_multiple_as_wav(self, file_ids: list[int], output_folder: str = "", muted: bool = False,
                             with_seq: bool = False):
        """
        @exception
        - OSError
            - output_folder does not exist
        """
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise OSError(f"Invalid output folder '{output_folder}'")

        self.create_dummy_bank(file_ids, os.path.join(CACHE, "temp.bnk"))

        process = subprocess.run([
            VGMSTREAM, "-S", "0", "-o", os.path.join(output_folder, "?n.wav"), os.path.join(CACHE, "temp.bnk"),
            ],
            stdout=subprocess.DEVNULL,
        )
        
        if process.returncode != 0:
            logger.error(f"Encountered error when converting to .wav")
        os.remove(os.path.join(CACHE, "temp.bnk"))
        
        for audio_source in audio_sources:
            if audio_source.get_resource_id() != 0:
                os.rename(os.path.join(output_folder, f"{audio_source.get_short_id()}.wav"), os.path.join(output_folder, f"{audio_source.get_resource_id()}.wav"))

    def dump_all_as_wem(self, output_folder: str = ""):
        """
        @exception
        - OSError
            - output_folder does not exist
        """
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise OSError(f"Invalid output folder '{output_folder}'")

        for bank in self.get_wwise_banks().values():
            if bank.dep == None:
                raise AssertionError(
                    f"Wwise bank {bank.get_id()} does not have a Wwise "
                     "dependency."
                )
            subfolder = os.path.join(output_folder, os.path.basename(bank.dep.data.replace('\x00', '')))
            if not os.path.exists(subfolder):
                os.mkdir(subfolder)
            for audio_id in bank.get_content():
                audio = self.get_audio_source(audio_id)
                save_path = os.path.join(subfolder, f"{audio.get_id()}")
                with open(save_path+".wem", "wb") as f:
                    f.write(audio.get_data())
    
    def dump_all_as_wav(self, output_folder: str = ""):
        """
        @exception
        - OSError
            - output_folder does not exist
        """
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise OSError(f"Invalid output folder '{output_folder}'")

        for bank in self.get_wwise_banks().values():
            if bank.dep == None:
                raise AssertionError(
                    f"Wwise bank {bank.get_id()} does not have a Wwise "
                     "dependency."
                )
            subfolder = os.path.join(output_folder, os.path.basename(bank.dep.data.replace('\x00', '')))
            if not os.path.exists(subfolder):
                os.mkdir(subfolder)
            file_ids = bank.get_content()
            self.dump_multiple_as_wav(file_ids=file_ids, output_folder=subfolder)

    def save_archive_file(self, game_archive: GameArchive, output_folder: str = ""):
        """
        @exception
        - OSError
            - output_folder does not exist
        """
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise OSError(f"Invalid output folder '{output_folder}'")
        
        game_archive.to_file(output_folder)
        
    def save(self, output_folder: str = "", combined = True):
        """
        @exception
        - OSError
            - output_folder does not exist
        """
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise OSError(f"Invalid output folder '{output_folder}'")
        
        if combined:
            combined_game_archive = GameArchive()
            combined_game_archive.name = "9ba626afa44a3aa3.patch_0"
            combined_game_archive.magic = 0xF0000011
            combined_game_archive.num_types = 0
            combined_game_archive.num_files = 0
            combined_game_archive.unknown = 0
            combined_game_archive.unk4Data = bytes.fromhex("CE09F5F4000000000C729F9E8872B8BD00A06B02000000000079510000000000000000000000000000000000000000000000000000000000")
            combined_game_archive.audio_sources = self.audio_sources
            combined_game_archive.wwise_banks = self.wwise_banks
            combined_game_archive.wwise_streams = self.wwise_streams
            combined_game_archive.text_banks = self.text_banks
            combined_game_archive.to_file(output_folder)
        else:
            for game_archive in self.get_game_archives().values():
                self.save_archive_file(game_archive, output_folder)
            
    def get_audio_source(self, audio_id: int) -> AudioSource:
        """
        @exception
        - KeyError
        """
        try:
            return self.audio_sources[audio_id] #short_id
        except KeyError:
            pass
        for source in self.audio_sources.values(): #resource_id
            if source.resource_id == audio_id:
                return source
        raise KeyError(f"Cannot find audio source with id {audio_id}")
                
    def get_string_entry(self, textbank_id: int, entry_id: int) -> StringEntry:
        """
        @exception
        - KeyError
        """
        try:
            return self.get_text_bank(textbank_id).entries[entry_id]
        except KeyError:
            raise KeyError(f"Cannot find string with id {entry_id} in textbank with id {textbank_id}")
            
    def get_string_entries(self, textbank_id: int) -> dict[int, StringEntry]:
        return self.get_text_bank(textbank_id).entries

    def get_hierarchy_entry(self, hierarchy_id: int) -> wwise_hierarchy_140.HircEntry | wwise_hierarchy_154.HircEntry:
        """
        @exception
        - KeyError
        """
        return self.get_hierarchy_entries()[hierarchy_id]
            
    def get_hierarchy_entries(self, soundbank_id: int = 0):
        """
        @exception
        - KeyError (Bubble up)
        - AssertionError
        """
        if soundbank_id == 0:
            return self.hierarchy_entries
        bank = self.get_wwise_bank(soundbank_id)
        if bank.hierarchy == None:
            raise AssertionError(f"WwiseBank {soundbank_id} with no WwiseHierarchy")

        return bank.hierarchy.get_entries()
            
    def get_wwise_bank(self, soundbank_id: int) -> WwiseBank:
        """
        @exception
        - KeyError
            - Trivial
        """
        try:
            return self.wwise_banks[soundbank_id]
        except KeyError:
            raise KeyError(f"Cannot find soundbank with id {soundbank_id}")
        
    def set_wwise_bank(self, soundbank_id: int, bank: WwiseBank):
        self.wwise_banks[soundbank_id] = bank
        
    def get_wwise_stream(self, stream_id: int) -> WwiseStream:
        """
        @exception
        - KeyError
            - Trivial
        """
        try:
            return self.wwise_streams[stream_id]
        except KeyError:
            raise KeyError(f"Cannot find wwise stream with id {stream_id}")
        
    def set_wwise_stream(self, stream_id: int, stream: WwiseStream):
        self.wwise_streams[stream_id] = stream
    
    def get_text_bank(self, textbank_id: int) -> TextBank:
        """
        @exception
        - KeyError
            - Trivial
        """
        try:
            return self.text_banks[textbank_id]
        except KeyError:
            raise KeyError(f"Cannot find text bank with id {textbank_id}")
    
    def get_game_archives(self) -> dict[str, GameArchive]:
        return self.game_archives
        
    def get_game_archive(self, archive_name: str) -> GameArchive:
        try:
            return self.get_game_archives()[archive_name]
        except KeyError:
            raise Exception(f"Cannot find game archive {archive_name}")
        
    def get_wwise_streams(self) -> dict[int, WwiseStream]:
        return self.wwise_streams

    def get_video_sources(self) -> dict[int, VideoSource]:
        return self.video_sources
        
    def get_wwise_banks(self) -> dict[int, WwiseBank]:
        return self.wwise_banks
        
    def get_audio_sources(self) -> dict[int, AudioSource]:
        return self.audio_sources
        
    def get_text_banks(self) -> dict[int, TextBank]:
        return self.text_banks
        
    def load_archive_file(self, archive_file: str = ""):
        """
        @exception
        - OSError
            - archive file does not exist
        """
        if not archive_file or not os.path.exists(archive_file) or not os.path.isfile(archive_file):
            raise OSError("Invalid path!")

        if os.path.splitext(archive_file)[1] in (".stream", ".gpu_resources"):
            archive_file = os.path.splitext(archive_file)[0]
        new_archive = GameArchive.from_file(archive_file)
        
        key = new_archive.name
        if key in self.game_archives.keys():
            return False
        
        self.add_game_archive(new_archive)

        return True
        
    def import_wwise_hierarchy(self, soundbank_id: int, new_hierarchy: WwiseHierarchy_154):
        self.get_wwise_bank(soundbank_id).import_hierarchy(new_hierarchy)
        
    def generate_hierarchy_id(self, soundbank_id: int) -> int:
        hierarchy = self.get_wwise_bank(soundbank_id).hierarchy

        if hierarchy == None:
            raise AssertionError(f"WwiseBank {soundbank_id} without WwiseHierarchy")

        new_id = random.randint(0, 0xffffffff)

        while new_id in hierarchy.entries.keys():
            new_id = random.randint(0, 0xffffffff)
        return new_id
        
    def remove_game_archive(self, archive_name: str = ""):
        if archive_name not in self.game_archives.keys():
            raise AssertionError(f"Archive {archive_name} not in mod!")
            
        game_archive = self.game_archives[archive_name]

        for key in game_archive.video_sources.keys():
            if key in self.video_sources.keys():
                self.video_count[key] -= 1
                if self.video_count[key] == 0:
                    del self.video_sources[key]
            
        for key in game_archive.wwise_banks.keys():
            if key in self.get_wwise_banks().keys():
                self.bank_count[key] -= 1
                if self.bank_count[key] == 0:
                    for entry in game_archive.get_wwise_banks()[key].hierarchy.entries.values():
                        entry.soundbanks.remove(game_archive.get_wwise_banks()[key])
                    for audio_id in self.get_wwise_banks()[key].get_content():
                        try:
                            audio = self.get_audio_source(audio_id)
                        except KeyError:
                            continue
                        parents = [p for p in audio.parents]
                        for parent in parents:
                            if isinstance(parent, (wwise_hierarchy_154.HircEntry, wwise_hierarchy_140.HircEntry)) and key in [b.get_id() for b in parent.soundbanks]:
                                audio.parents.remove(parent)
                    del self.get_wwise_banks()[key]
                    del self.bank_count[key]
        for key, entry in game_archive.get_hierarchy_entries().items():
            self.hierarchy_count[key] -= 1
            if self.hierarchy_count[key] == 0:
                del self.hierarchy_count[key]
                del self.get_hierarchy_entries()[key]
        for key in game_archive.wwise_streams.keys():
            if key in self.get_wwise_streams().keys():
                self.stream_count[key] -= 1
                if self.stream_count[key] == 0:
                    stream = self.wwise_streams[key]

                    if stream.audio_source == None:
                        logger.warning(
                            f"Wwise stream {stream.get_id()} does not have an "
                             "audio source!"
                        )
                        continue
                    stream.audio_source.parents.remove(self.get_wwise_streams()[key])
                    del self.get_wwise_streams()[key]
                    del self.stream_count[key]
        for key in game_archive.text_banks.keys():
            if key in self.get_text_banks().keys():
                self.text_count[key] -= 1
                if self.text_count[key] == 0:
                    del self.get_text_banks()[key]
                    del self.text_count[key]
        for key in game_archive.audio_sources.keys():
            if key in self.get_audio_sources().keys():
                self.audio_count[key] -= 1
                if self.audio_count[key] == 0:
                    del self.get_audio_sources()[key]
                    del self.audio_count[key]
        
        try:
            del self.game_archives[archive_name]
        except:
            pass
    
    def remove_all_game_archives(self):
        """
        Remove all game archives from the mod.
        This will clear all audio sources, wwise banks, wwise streams, 
        text banks, video sources, and hierarchy entries.
        """
        # Get all archive names to remove
        archive_names = list(self.game_archives.keys())
        
        # Remove each archive
        for archive_name in archive_names:
            self.remove_game_archive(archive_name)
    
    def add_game_archive(self, game_archive: GameArchive):
        """
        @exception
        - AssertionError
        """
        key = game_archive.name
        if key in self.game_archives.keys():
            return

        self.game_archives[key] = game_archive

        # handle if video already loaded
        for key, entry in game_archive.video_sources.items():
            if key in self.video_sources.keys():
                self.video_count[key] += 1
                video = self.get_video_source(key)
                game_archive.video_sources[key] = video
                if "_patch" not in os.path.splitext(game_archive.name)[1]:
                    video.filepath = entry.filepath
                    video.video_size = entry.video_size
                    video.stream_offset = entry.stream_offset
            else:
                self.video_sources[key] = entry
                self.video_count[key] = 1
        
        replacements = {}
        for key, entry in game_archive.get_hierarchy_entries().items():
            if key in self.get_hierarchy_entries():
                self.hierarchy_count[key] += 1
                existing_entry = self.get_hierarchy_entry(key)
                replacements[key] = existing_entry
                if isinstance(entry, (wwise_hierarchy_154.ActorMixer, wwise_hierarchy_140.ActorMixer)):
                    for child in entry.children.children:
                        if child not in existing_entry.children.children:
                            existing_entry.children.children.append(child)
                            existing_entry.children.numChildren += 1
                            existing_entry.size += 4
                for bank in entry.soundbanks:
                    bank.hierarchy.entries[key] = existing_entry
                    if existing_entry.modified:
                        bank.raise_modified()
                    if bank not in existing_entry.soundbanks:
                        existing_entry.soundbanks.append(bank)
            else:
                self.hierarchy_count[key] = 1
                self.hierarchy_entries[key] = entry
        # update in each soundbank hierarchy's type lists, each soundbank hierarchy, and then GameArchive
        for bank in game_archive.wwise_banks.values():
            hirc = bank.hierarchy
            for hirc_id, hirc_entry in replacements.items():
                if hirc_id in hirc.entries.keys():
                    try:
                        hirc._remove_categorized_entry(hirc.entries[hirc_id])
                    except:
                        pass
                    hirc._categorized_entry(hirc_entry)
                    hirc.entries[hirc_id] = hirc_entry
        game_archive.get_hierarchy_entries().update(replacements)
        
        for key in game_archive.wwise_banks.keys():
            if key in self.get_wwise_banks().keys():
                self.bank_count[key] += 1
                for audio_id in game_archive.wwise_banks[key].get_content():
                    try:
                        audio = self.get_audio_source(audio_id)
                    except KeyError:
                        continue
                    parents = [p for p in audio.parents]
                    for parent in parents:
                        if isinstance(parent, (wwise_hierarchy_154.HircEntry, wwise_hierarchy_140.HircEntry)) and key in [b.get_id() for b in parent.soundbanks]:
                            audio.parents.remove(parent)
                            try:
                                new_parent = self.get_hierarchy_entry(parent.get_id())
                            except:
                                continue # add missing hierarchy entry?
                            audio.parents.add(new_parent)
                            if audio.modified:
                                new_parent.raise_modified()
                game_archive.wwise_banks[key] = self.get_wwise_banks()[key]
            else:
                self.bank_count[key] = 1
                self.get_wwise_banks()[key] = game_archive.wwise_banks[key]
        for key in game_archive.wwise_streams.keys():
            if key in self.get_wwise_streams().keys():
                self.stream_count[key] += 1
                audio = game_archive.wwise_streams[key].audio_source

                if audio == None:
                    raise AssertionError(
                        f"WwiseStream {key} has no audio source"
                    )

                audio.parents.remove(game_archive.wwise_streams[key])
                audio.parents.add(self.get_wwise_streams()[key])
                if audio.modified:
                    self.get_wwise_streams()[key].raise_modified()
                game_archive.wwise_streams[key] = self.get_wwise_streams()[key]
            else:
                self.stream_count[key] = 1
                self.get_wwise_streams()[key] = game_archive.wwise_streams[key]
        for key in game_archive.text_banks.keys():
            if key in self.get_text_banks().keys():
                self.text_count[key] += 1
                game_archive.text_banks[key] = self.get_text_banks()[key]
            else:
                self.text_count[key] = 1
                self.get_text_banks()[key] = game_archive.text_banks[key]
        for key in game_archive.audio_sources.keys():
            if key in self.get_audio_sources().keys():
                self.audio_count[key] += 1
                for parent in game_archive.audio_sources[key].parents:
                    if parent.get_id() not in [p.get_id() for p in self.audio_sources[key].parents]:
                        self.get_audio_sources()[key].parents.add(parent)
                game_archive.audio_sources[key] = self.get_audio_sources()[key]
            else:
                self.audio_count[key] = 1
                self.get_audio_sources()[key] = game_archive.audio_sources[key]
            
    def import_patch(self, patch_file: str = "", import_hierarchy=True):
        """
        @exception
        - OSError
            - patch file does not exists
        - AssertionError
        """

        if os.path.splitext(patch_file)[1] in (".stream", ".gpu_resources"):
            patch_file = os.path.splitext(patch_file)[0]
        if not os.path.exists(patch_file) or not os.path.isfile(patch_file):
            raise OSError("Invalid file!")

        patch_game_archive = None
        
        try:
            patch_game_archive = GameArchive.from_file(patch_file)
        except Exception as e:
            logger.error(f"Error occured when loading {patch_file}: {e}.")
            logger.warning("Aborting load")
            return False
                                
        for new_audio in patch_game_archive.get_audio_sources().values():
            try:
                old_audio = self.get_audio_source(new_audio.get_short_id())
            except:
                continue
            if (not old_audio.modified and new_audio.get_data() != old_audio.get_data()
                or old_audio.modified and new_audio.get_data() != old_audio.data_old):
                old_audio.set_data(new_audio.get_data())
                sample_rate = int.from_bytes(new_audio.get_data()[24:28], byteorder="little")
                num_samples = int.from_bytes(new_audio.get_data()[44:48], byteorder="little")
                len_ms = num_samples * 1000 / sample_rate
                for item in old_audio.parents:
                    if isinstance(item, (wwise_hierarchy_140.MusicTrack, wwise_hierarchy_154.MusicTrack)):
                        if item.parent == None:
                            continue
                        item.parent.set_data(
                            duration=len_ms,
                            entry_marker=0,
                            exit_marker=len_ms
                        )
                        tracks = copy.deepcopy(item.track_info)
                        for t in tracks:
                            if t.source_id == old_audio.get_short_id():
                                t.begin_trim_offset = 0
                                t.end_trim_offset = 0
                                t.source_duration = len_ms
                                t.play_at = 0
                                break
                        item.set_data(track_info=tracks)

        if import_hierarchy:
            for bank in patch_game_archive.get_wwise_banks().values():
                if bank.hierarchy == None:
                    raise AssertionError(
                        f"WwiseBank {bank.file_id} has no WwiseHierarchy"
                    )
                try:
                    self.get_wwise_banks()[bank.get_id()].import_hierarchy(bank.hierarchy)
                except Exception as e:
                    logger.error(e)
                    logger.error(f"Unable to import heirarchy information for {bank.dep.data}")

        for text_bank in patch_game_archive.get_text_banks().values():
            try:
                self.get_text_banks()[text_bank.get_id()].import_text(text_bank)
            except:
                logger.warning("Unable to import some text data")

        add_patch = False
        for bank in list(patch_game_archive.get_wwise_banks().values()):
            if bank.get_id() in self.get_wwise_banks().keys():
                del patch_game_archive.wwise_banks[bank.get_id()]
        if len(patch_game_archive.get_wwise_banks()) > 0:
            add_patch = True

        for video in list(patch_game_archive.get_video_sources().values()):
            has_video_source = False
            try:
                self.get_video_source(video.file_id)
                has_video_source = True
            except KeyError:
                pass

            if not has_video_source:
                video.modified = True
                video.replacement_video_offset = video.stream_offset
                video.replacement_video_size = video.video_size
                video.replacement_filepath = video.filepath+".stream"
                add_patch = True
            else:
                try:
                    self.import_video(patch_file+".stream", video.file_id)
                    self.get_video_source(video.file_id).replacement_video_offset = video.stream_offset
                except Exception as e:
                    logger.warning("Unable to import some video data")
                del patch_game_archive.video_sources[video.file_id]
        if add_patch:
            patch_game_archive.text_banks.clear()
            self.add_game_archive(patch_game_archive)
        
        return True

    def write_separate_patches(self, output_folder: str = ""):
        """
        @exception
        - OSError
            - output folder path does not exists
        """
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise OSError(f"Invalid output folder '{output_folder}'")
        for archive in self.game_archives.values():
            patch_game_archive = GameArchive()
            patch_game_archive.name = f"{archive.name}.patch_0"
            patch_game_archive.magic = 0xF0000011
            patch_game_archive.num_types = 0
            patch_game_archive.num_files = 0
            patch_game_archive.unknown = archive.unknown
            patch_game_archive.unk4Data = archive.unk4Data
            patch_game_archive.audio_sources = archive.audio_sources
            patch_game_archive.wwise_banks = {}
            patch_game_archive.wwise_streams = {}
            patch_game_archive.text_banks = {}
            patch_game_archive.video_sources = {}

            for key, value in archive.get_wwise_streams().items():
                if value.modified:
                    patch_game_archive.wwise_streams[key] = value

            for key, value in archive.get_wwise_banks().items():
                if value.modified:
                    patch_game_archive.wwise_banks[key] = value

            for key, value in archive.get_text_banks().items():
                if value.modified:
                    patch_game_archive.text_banks[key] = value

            for key, value in archive.get_video_sources().items():
                if value.modified:
                    patch_game_archive.video_sources[key] = value

            patch_game_archive.to_file(output_folder)

    def write_patch(self, output_folder: str = "", output_filename: str = ""):
        """
        @exception
        - OSError
            - output folder path does not exists
        """
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise OSError(f"Invalid output folder '{output_folder}'")
        patch_game_archive = GameArchive()
        patch_game_archive.name = "9ba626afa44a3aa3.patch_0" if output_filename == "" else output_filename
        patch_game_archive.magic = 0xF0000011
        patch_game_archive.num_types = 0
        patch_game_archive.num_files = 0
        patch_game_archive.unknown = 0
        patch_game_archive.unk4Data = bytes.fromhex("CE09F5F4000000000C729F9E8872B8BD00A06B02000000000079510000000000000000000000000000000000000000000000000000000000")
        patch_game_archive.audio_sources = self.audio_sources
        patch_game_archive.wwise_banks = {}
        patch_game_archive.wwise_streams = {}
        patch_game_archive.text_banks = {}
        patch_game_archive.video_sources = {}
            
        for key, value in self.get_wwise_streams().items():
            if value.modified:
                patch_game_archive.wwise_streams[key] = value
                
        for key, value in self.get_wwise_banks().items():
            if value.modified:
                patch_game_archive.wwise_banks[key] = value
                
        for key, value in self.get_text_banks().items():
            if value.modified:
                patch_game_archive.text_banks[key] = value

        for key, value in self.get_video_sources().items():
            if value.modified:
                patch_game_archive.video_sources[key] = value
 
        patch_game_archive.to_file(output_folder)

    def import_video(self, video_path: str, video_id: int):
        self.get_video_sources()[video_id].set_data(video_path)
        self.get_video(video_id).replacement_video_offset = 0

    def dump_video(self, output_path: str, video_id: int):
        with open(output_path, "wb") as output_file:
            output_file.write(self.get_video(video_id).get_data())

    def get_video(self, video_id: int):
        return self.get_video_sources()[video_id]

    def import_wems(self, wems: dict[str, list[int]] | None = None, set_duration=True): 
        """
        @exception
        - ValueError
            - wems is None
        - RuntimeError
        """

        if wems == None:
            raise ValueError("No wems selected for import")
        if len(wems) <= 0:
            return

        length_import_failed = False
        wrong_file_format = False
        for filepath, targets in wems.items():
            if not os.path.exists(filepath) or not os.path.isfile(filepath):
                continue
            have_length = True
            with open(filepath, 'rb') as f:
                audio_data = bytearray(f.read())
                if audio_data[20:22] != b"\xFF\xFF":
                    wrong_file_format = True
                    logger.warning(f"File {filepath} was the incorrect audio format!")
                    continue
            if set_duration:
                try:
                    sample_rate = float(int.from_bytes(audio_data[24:28], byteorder="little"))
                    total_samples = float(int.from_bytes(audio_data[44:48], byteorder="little"))
                    len_ms = total_samples * 1000 / sample_rate
                except Exception as e:
                    print(e)
                    logger.warning(f"Failed to get duration info for {filepath}!")
                    have_length = False
                    length_import_failed = True
            for target in targets:
                audio: AudioSource | None = self.get_audio_source(target)
                if audio:
                    audio.set_data(audio_data)
                    if have_length:
                        # find music segment for Audio Source
                        for item in audio.parents:
                            if isinstance(item, (wwise_hierarchy_140.MusicTrack, wwise_hierarchy_154.MusicTrack)):
                                if item.parent == None:
                                    raise AssertionError(
                                        f"Music track {item.hierarchy_id} does not have"
                                        " a parent!"
                                    )
                                item.parent.set_data(duration=len_ms, entry_marker=0, exit_marker=len_ms)
                                tracks = copy.deepcopy(item.track_info)
                                for t in tracks:
                                    if t.source_id == audio.get_short_id():
                                        t.begin_trim_offset = 0
                                        t.end_trim_offset = 0
                                        t.source_duration = len_ms
                                        t.play_at = 0
                                        break
                                item.set_data(track_info=tracks)
                                
        if length_import_failed and wrong_file_format:
            raise RuntimeError("Failed to set track duration for some audio sources. Some audio was not the correct format.")

        if length_import_failed:
            raise RuntimeError("Failed to set track duration for some audio sources.")
            
        if wrong_file_format:
            raise RuntimeError("Some audio was not the correct format. If using Wwise, ensure your Conversion Setting format is set to Vorbis.")
    
    def create_external_sources_list(self, sources: list[str], conversion_setting: str = DEFAULT_CONVERSION_SETTING) -> str:
        root = etree.Element("ExternalSourcesList", attrib={
            "SchemaVersion": "1",
            "Root": __file__
        })
        file = etree.ElementTree(root)
        for source in sources:
            etree.SubElement(root, "Source", attrib={
                "Path": source,
                "Conversion": conversion_setting,
                "Destination": os.path.basename(source)
            })
        file.write(os.path.join(TMP, "external_sources.wsources"))
        
        return os.path.join(TMP, "external_sources.wsources")
        
    def import_wavs(self, wavs: dict[str, list[int]] | None = None, wwise_project: str = DEFAULT_WWISE_PROJECT):
        """
        @exception
        - ValueError
            - wavs is None
        - CalledProcessError
            - subprocess.run
        - NotImplementedError
            - Platform is on Linux
        """
        if wavs == None:
            raise ValueError("No wav files selected for import!")

        if len(wavs) <= 0:
            return
            
        source_list = self.create_external_sources_list(list(wavs.keys()))

        if SYSTEM not in WWISE_SUPPORTED_SYSTEMS:
            raise NotImplementedError(
                "The current operating system does not support this feature"
            )
        process = subprocess.run([
            env.WWISE_CLI,
            "migrate",
            wwise_project,
            "--quiet",
        ])
        
        if process.returncode != 0:
            raise Exception("Non-zero return code in Wwise project migration")
        
        convert_dest = os.path.join(TMP, SYSTEM)
        
        process = subprocess.run([
            env.WWISE_CLI,
            "convert-external-source",
            wwise_project,
            "--platform", "Windows",
            "--source-file",
            source_list,
            "--output",
            TMP,
        ])
        
        if process.returncode != 0:
            raise Exception("Non-zero return code in Wwise source conversion")
        
        wems = {os.path.join(convert_dest, f"{os.path.splitext(os.path.basename(filepath))[0]}.wem"): targets for filepath, targets in wavs.items()}

        self.import_wems(wems)
        
        for wem in wems.keys():
            try:
                os.remove(wem)
            except OSError as err:
                logger.error(err)
                
        try:
            os.remove(source_list)
        except OSError as err:
            logger.error(err)
            
    def import_files(self, file_dict: dict[str, list[int]]):
        patches = [file for file in file_dict.keys() if "patch" in os.path.splitext(file)[1]]
        wems = {file: targets for file, targets in file_dict.items() if os.path.splitext(file)[1].lower() == ".wem"}
        wavs = {file: targets for file, targets in file_dict.items() if os.path.splitext(file)[1].lower() == ".wav"}
        
        # check other file extensions and call vgmstream to convert to wav, then add to wavs dict
        filetypes = list(SUPPORTED_AUDIO_TYPES)
        filetypes.remove(".wav")
        filetypes.remove(".wem")
        others = {file: targets for file, targets in file_dict.items() if os.path.splitext(file)[1].lower() in filetypes}

        # move invalid wems to the "other audio formats" list
        if os.path.exists(env.WWISE_CLI):
            for wem in list(wems.keys()):
                with open(wem, 'rb') as f:
                    audio_data = bytearray(f.read(24))
                    if audio_data[20:22] != b"\xFF\xFF": # invalid wem
                        # add wem to "others"
                        others[wem] = wems[wem]
                        del wems[wem]

        temp_files = []
        for file in others.keys():
            subprocess.run([VGMSTREAM, "-o", f"{os.path.join(TMP, os.path.splitext(os.path.basename(file))[0])}.wav", file], stdout=subprocess.DEVNULL).check_returncode()
            wavs[f"{os.path.join(TMP, os.path.splitext(os.path.basename(file))[0])}.wav"] = others[file]
            temp_files.append(f"{os.path.join(TMP, os.path.splitext(os.path.basename(file))[0])}.wav")
        
        for patch in patches:
            self.import_patch(patch_file=patch)
        if len(wems) > 0:
            self.import_wems(wems)
        if len(wavs) > 0:
            self.import_wavs(wavs)
        for file in temp_files:
            try:
                os.remove(file)
            except OSError as err:
                logger.error(err)
        
class ModHandler:
    
    handler_instance: Union['ModHandler', None] = None
    
    def __init__(self, db: SQLiteDatabase):
        self.db = db
        self.mods: dict[str, Mod] = {}
        
    @classmethod
    def create_instance(cls, db: SQLiteDatabase):
        cls.handler_instance = ModHandler(db)
        
    @classmethod
    def get_instance(cls, db: SQLiteDatabase) -> 'ModHandler':
        if cls.handler_instance == None:
            cls.handler_instance = ModHandler(db)
        return cls.handler_instance

    def add_new_mod(self, mod_name: str, mod: Mod):
        """
        @exception
        - KeyError
        """
        if mod_name in self.mods:
            raise KeyError(f"Mod name '{mod_name}' already exists!")
        self.mods[mod_name] = mod

    def create_new_mod(self, mod_name: str):
        """
        @exception
        - KeyError
            - Mod name conflict
        """
        if mod_name in self.mods.keys():
            raise KeyError(f"Mod name '{mod_name}' already exists!")
        new_mod = Mod(mod_name, self.db)
        self.mods[mod_name] = new_mod
        self.active_mod = new_mod
        return new_mod
        
    def get_active_mod(self) -> Mod:
        """
        @exception
        - LookupError
            - Query an empty blank state of ModHandler
        """
        if not self.active_mod:
            raise LookupError("No active mod!")
        return self.active_mod
        
    def set_active_mod(self, mod_name: str):
        """
        @exception
        - KeyError 
            - no matching mod name
        """
        try:
            self.active_mod = self.mods[mod_name]
        except:
            raise KeyError(f"No matching mod found for '{mod_name}'")
            
    def get_mod_names(self) -> list[str]:
        return list(self.mods.keys())

    def has_mod(self, mod_name: str) -> bool:
        return mod_name in self.mods
        
    def delete_mod(self, mod: str | Mod):
        """
        @exception
        - KeyError 
            - no matching mod name
        """

        if isinstance(mod, Mod):
            mod_name = mod.name
        else:
            mod_name = mod
        try:
            mod_to_delete = self.mods[mod_name]
        except:
            raise KeyError(f"No matching mod found for '{mod}'")
        if mod_to_delete is self.active_mod:
            if len(self.mods) > 1:
                for mod in self.mods.values():
                    if mod is not self.active_mod:
                        self.active_mod = mod
                        break
            else:
                self.active_mod = None
        del self.mods[mod_name]
