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

from typing import Callable
from typing_extensions import Self

from util import *
from wwise_hierarchy import *

from log import logger
    

class AudioSource:

    def __init__(self):
        self.data = b""
        self.size = 0
        self.resource_id = 0
        self.short_id = 0
        self.modified = False
        self.data_old = b""
        self.parents = set()
        self.stream_type = 0
        
    def set_data(self, data: bytes, notify_subscribers: bool = True, set_modified: bool = True):
        if not self.modified and set_modified:
            self.data_old = self.data
        self.data = data
        self.size = len(self.data)
        if notify_subscribers:
            for item in self.parents:
                if not self.modified:
                    item.raise_modified()
        if set_modified:
            self.modified = True
            
    def get_id(self) -> int:
        if self.stream_type == BANK:
            return self.get_short_id()
        else:
            return self.get_resource_id()
            
    def is_modified(self) -> bool:
        return self.modified

    def get_data(self) -> bytes:
        return self.data
        
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
        self.data = ""
        
    def from_memory_stream(self, stream: MemoryStream):
        self.offset = stream.tell()
        self.tag = stream.uint32_read()
        self.data_size = stream.uint32_read()
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
            return None

class WwiseBank:
    
    def __init__(self):
        self.bank_header = b""
        self.bank_misc_data = b""
        self.modified = False
        self.dep = None
        self.modified_count = 0
        self.hierarchy = None
        self.content = []
        self.file_id = 0
        
    def import_hierarchy(self, new_hierarchy: WwiseHierarchy):
        self.hierarchy.import_hierarchy(new_hierarchy)
        
    def add_content(self, content: AudioSource):
        self.content.append(content)
        
    def remove_content(self, content: AudioSource):
        try:
            self.content.remove(content)
        except:
            pass
            
    def get_content(self) -> list[AudioSource]:
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
        return self.dep.data
        
    def get_id(self) -> int:
        try:
            return self.file_id
        except:
            return 0
            
    def generate(self, audio_sources) -> bytearray:
        data = bytearray()
        data += self.bank_header
        offset = 0
        
        #regenerate soundbank from the hierarchy information
        
        didx_array = []
        data_array = []
        
        added_sources = set()
        
        for entry in self.hierarchy.get_type(SOUND) + self.hierarchy.get_type(MUSIC_TRACK):
            for source in entry.sources:
                if source.plugin_id == VORBIS:
                    try:
                        audio = audio_sources[source.source_id]
                    except KeyError as e:
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
        self.audio_source = None
        self.modified = False
        self.file_id = 0
        
    def set_source(self, audio_source: AudioSource):
        try:
            self.audio_source.parents.remove(self)
        except:
            pass
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
            
    def get_data(self) -> bytes:
        return self.audio_source.get_data()

class StringEntry:

    def __init__(self):
        self.text = ""
        self.text_old = ""
        self.string_id = 0
        self.modified = False
        self.parent = None
        
    def get_id(self) -> int:
        return self.string_id
        
    def get_text(self) -> str:
        return self.text
        
    def set_text(self, text: str):
        if not self.modified:
            self.text_old = self.text
            self.parent.raise_modified()
        self.modified = True
        self.text = text
        
    def revert_modifications(self):
        if self.modified:
            self.text = self.text_old
            self.modified = False
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
        offset = 0
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
        self.wwise_streams = {}
        self.wwise_banks = {}
        self.audio_sources = {}
        self.text_banks = {}
    
    @classmethod
    def from_file(cls, path: str) -> Self:
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
        
    def get_text_banks(self) -> dict[int, TextBank]:
        return self.text_banks
        
        
    def write_type_header(self, toc_file: MemoryStream, entry_type: int, num_entries: int):
        if num_entries > 0:
            toc_file.write(struct.pack("<QQQII", 0, entry_type, num_entries, 16, 64))
        
    def to_file(self, path: str):
        toc_file = MemoryStream()
        stream_file = MemoryStream()
        self.num_files = len(self.wwise_streams) + 2*len(self.wwise_banks) + len(self.text_banks)
        self.num_types = (1 if self.wwise_streams else 0) + (1 if self.text_banks else 0) + (2 if self.wwise_banks else 0)
        
        # write header
        toc_file.write(struct.pack("<IIII56s", self.magic, self.num_types, self.num_files, self.unknown, self.unk4Data))
        
        self.write_type_header(toc_file, WWISE_STREAM, len(self.wwise_streams))
        self.write_type_header(toc_file, WWISE_BANK, len(self.wwise_banks))
        self.write_type_header(toc_file, WWISE_DEP, len(self.wwise_banks))
        self.write_type_header(toc_file, TEXT_BANK, len(self.text_banks))
        
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
        
        for bank in self.wwise_banks.values():
            dep_data = bank.dep.get_data()
            toc_entry = TocHeader()
            toc_entry.file_id = bank.get_id()
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
        self.text_banks.clear()
        
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
                
                hirc = WwiseHierarchy(soundbank=entry)
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
                dep = WwiseDep()
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
        
        # Create all AudioSource objects
        for bank in self.wwise_banks.values():
            for entry in bank.hierarchy.get_entries():
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
                            audio = self.wwise_streams[stream_resource_id].audio_source
                            audio.short_id = source.source_id
                            self.audio_sources[source.source_id] = audio
                        except KeyError:
                            pass
                    elif source.plugin_id == REV_AUDIO and source.stream_type == BANK and source.source_id not in self.audio_sources:
                        try:
                            custom_fx = bank.hierarchy.entries[source.source_id]
                            data = custom_fx.get_data()
                            plugin_param_size = int.from_bytes(data[13:17], byteorder="little")
                            media_index_id = int.from_bytes(data[19+plugin_param_size:23+plugin_param_size], byteorder="little")
                            audio = AudioSource()
                            audio.stream_type = BANK
                            audio.short_id = media_index_id
                            audio.set_data(media_index.data[media_index_id], set_modified=False, notify_subscribers=False)
                            self.audio_sources[media_index_id] = audio
                        except KeyError:
                            pass

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
                        if source.plugin_id == VORBIS:
                            self.audio_sources[source.source_id].parents.add(entry)
                        if source.plugin_id == VORBIS and self.audio_sources[source.source_id] not in bank.get_content(): #may be missing streamed audio if the patch didn't change it
                            bank.add_content(self.audio_sources[source.source_id])
                    except:
                        continue
        
class SoundHandler:
    
    handler_instance = None
    
    def __init__(self):
        self.audio_process = None
        self.wave_object = None
        self.audio_id = -1
        self.audio = pyaudio.PyAudio()
        
    @classmethod
    def create_instance(cls):
        cls.handler_instance = SoundHandler()
        
    @classmethod
    def get_instance(cls) -> Self:
        if not cls.handler_instance:
            cls.create_instance()
        return cls.handler_instance
        
    def kill_sound(self):
        if self.audio_process is not None:
            if self.callback is not None:
                self.callback()
                self.callback = None
            self.audio_process.close()
            self.wave_file.close()
            try:
                os.remove(self.audio_file)
            except:
                pass
            self.audio_process = None
        
    def play_audio(self, sound_id: int, sound_data: bytearray, callback: Callable = None):
        if not os.path.exists(VGMSTREAM):
            return
        self.kill_sound()
        self.callback = callback
        if self.audio_id == sound_id:
            self.audio_id = -1
            return
        filename = f"temp{sound_id}"
        if not os.path.isfile(f"{filename}.wav"):
            with open(f'{os.path.join(CACHE, filename)}.wem', 'wb') as f:
                f.write(sound_data)
            process = subprocess.run([VGMSTREAM, "-o", f"{os.path.join(CACHE, filename)}.wav", f"{os.path.join(CACHE, filename)}.wem"], stdout=subprocess.DEVNULL)
            os.remove(f"{os.path.join(CACHE, filename)}.wem")
            if process.returncode != 0:
                logger.error(f"Encountered error when converting {sound_id}.wem for playback")
                self.callback = None
                return
            
        self.audio_id = sound_id
        self.wave_file = wave.open(f"{os.path.join(CACHE, filename)}.wav")
        self.audio_file = f"{os.path.join(CACHE, filename)}.wav"
        self.frame_count = 0
        self.max_frames = self.wave_file.getnframes()
        
        def read_stream(input_data, frame_count, time_info, status):
            self.frame_count += frame_count
            if self.frame_count > self.max_frames:
                if self.callback is not None:
                    self.callback()
                    self.callback = None
                self.audio_id = -1
                self.wave_file.close()
                try:
                    os.remove(self.audio_file)
                except:
                    pass
                return (None, pyaudio.paComplete)
            data = self.wave_file.readframes(frame_count)
            if self.wave_file.getnchannels() > 2:
                data = self.downmix_to_stereo(data, self.wave_file.getnchannels(), self.wave_file.getsampwidth(), frame_count)
            return (data, pyaudio.paContinue)

        self.audio_process = self.audio.open(format=self.audio.get_format_from_width(self.wave_file.getsampwidth()),
                channels = min(self.wave_file.getnchannels(), 2),
                rate=self.wave_file.getframerate(),
                output=True,
                stream_callback=read_stream)
        self.audio_file = f"{os.path.join(CACHE, filename)}.wav"
        
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
        arr = arr.reshape((frame_count, channels))
        
        if channels == 4:
            for index, frame in enumerate(arr):
                stereo_array[index][0] = int(0.42265 * frame[0] + 0.366025 * frame[2] + 0.211325 * frame[3])
                stereo_array[index][1] = int(0.42265 * frame[1] + 0.366025 * frame[3] + 0.211325 * frame[2])
        
            return stereo_array.tobytes()
                
        if channels == 6:
            for index, frame in enumerate(arr):
                stereo_array[index][0] = int(0.374107*frame[1] + 0.529067*frame[0] + 0.458186*frame[3] + 0.264534*frame[4] + 0.374107*frame[5])
                stereo_array[index][1] = int(0.374107*frame[1] + 0.529067*frame[2] + 0.458186*frame[4] + 0.264534*frame[3] + 0.374107*frame[5])
        
            return stereo_array.tobytes()
        
        #if not 4 or 6 channel, default to taking the L and R channels rather than mixing
        for index, frame in enumerate(arr):
            stereo_array[index][0] = frame[0]
            stereo_array[index][1] = frame[1]
        
        return stereo_array.tobytes()
        
class Mod:

    def __init__(self, name):
        self.wwise_streams = {}
        self.stream_count = {}
        self.wwise_banks = {}
        self.bank_count = {}
        self.audio_sources = {}
        self.audio_count = {}
        self.text_banks = {}
        self.text_count = {}
        self.game_archives = {}
        self.name = name
        
    def revert_all(self):
        for audio in self.audio_sources.values():
            audio.revert_modifications()
        for bank in self.wwise_banks.values():
            bank.hierarchy.revert_modifications()
        for bank in self.text_banks.values():
            bank.revert_modifications()
        
    def revert_audio(self, file_id: int):
        audio = self.get_audio_source(file_id)
        audio.revert_modifications()
        
    def add_new_hierarchy_entry(self, soundbank_id: int, entry: HircEntry):
        self.get_wwise_bank(soundbank_id).hierarchy.add_entry(entry)
        
    def remove_hierarchy_entry(self, soundbank_id: int, entry_id: int):
        entry = self.get_hierarchy_entry(soundbank_id, entry_id)
        self.get_wwise_bank(soundbank_id).hierarchy.remove_entry(entry)
        
    def revert_hierarchy_entry(self, soundbank_id: int, entry_id: int):
        self.get_hierarchy_entry(soundbank_id, entry_id).revert_modifications()
        
    def revert_string_entry(self, textbank_id: int, entry_id: int):
        self.get_string_entry(textbank_id, entry_id).revert_modifications()
        
    def revert_text_bank(self, textbank_id: int):
        self.get_text_bank(textbank_id).revert_modifications()
        
    def revert_wwise_hierarchy(self, soundbank_id: int):
        self.get_wwise_bank(soundbank_id).hierarchy.revert_modifications()
        
    def revert_wwise_bank(self, soundbank_id: int):
        self.revert_wwise_hierarchy(soundbank_id)
        for audio in self.get_wwise_bank(soundbank_id).get_content():
            audio.revert_modifications()
        
    def dump_as_wem(self, file_id: int, output_file: str = ""):
        if not output_file:
            raise ValueError("Invalid output filename!")
        output_file.write(self.get_audio_source(file_id).get_data())
        
    def dump_as_wav(self, file_id: int, output_file: str = "", muted: bool = False):

        if not output_file:
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

        process = subprocess.run(
            [VGMSTREAM, "-o", f"{save_path}.wav", f"{save_path}.wem"], 
            stdout=subprocess.DEVNULL
        )
        
        if process.returncode != 0:
            logger.error(f"Encountered error when converting {file_id}.wem into .wav format")

        os.remove(f"{save_path}.wem")
        
    def dump_multiple_as_wem(self, file_ids: list[int], output_folder: str = ""):
        
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise ValueError(f"Invalid output folder '{output_folder}'")

        for file_id in file_ids:
            audio = self.get_audio_source(file_id)
            if audio is not None:
                save_path = os.path.join(folder, f"{audio.get_id()}")
                with open(save_path+".wem", "wb") as f:
                    f.write(audio.get_data())
        
    def dump_multiple_as_wav(self, file_ids: list[str], output_folder: str = "", muted: bool = False,
                             with_seq: bool = False):
        
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise ValueError(f"Invalid output folder '{output_folder}'")

        for i, file_id in enumerate(file_ids, start=0):
            audio: int | None = self.get_audio_source(int(file_id))
            if audio is None:
                continue
            basename = str(audio.get_id())
            if with_seq:
                basename = f"{i:02d}" + "_" + basename
            save_path = os.path.join(folder, basename)
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

    def dump_all_as_wem(self, output_folder: str = ""):
        
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise ValueError(f"Invalid output folder '{output_folder}'")
        for bank in self.game_archive.wwise_banks.values():
            subfolder = os.path.join(folder, os.path.basename(bank.dep.data.replace('\x00', '')))
            if not os.path.exists(subfolder):
                os.mkdir(subfolder)
            for audio in bank.get_content():
                save_path = os.path.join(subfolder, f"{audio.get_id()}")
                with open(save_path+".wem", "wb") as f:
                    f.write(audio.get_data())
    
    def dump_all_as_wav(self, output_folder: str = ""):
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise ValueError(f"Invalid output folder '{output_folder}'")
        for bank in self.game_archive.wwise_banks.values():
            subfolder = os.path.join(folder, os.path.basename(bank.dep.data.replace('\x00', '')))
            if not os.path.exists(subfolder):
                os.mkdir(subfolder)
            for audio in bank.get_content():
                save_path = os.path.join(subfolder, f"{audio.get_id()}")
                with open(save_path+".wem", "wb") as f:
                    f.write(audio.get_data())
                process = subprocess.run([VGMSTREAM, "-o", f"{save_path}.wav", f"{save_path}.wem"], stdout=subprocess.DEVNULL)
                if process.returncode != 0:
                    logger.error(f"Encountered error when converting {os.path.basename(save_path)}.wem to .wav")
                os.remove(f"{save_path}.wem")

    def save_archive_file(self, game_archive: GameArchive, output_folder: str = ""):

        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise ValueError(f"Invalid output folder '{output_folder}'")
        
        game_archive.to_file(output_folder)
        
    def save(self, output_folder: str = "", combined = True):
        
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise ValueError(f"Invalid output folder '{output_folder}'")
        
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
        try:
            return self.audio_sources[audio_id] #short_id
        except KeyError:
            pass
        for source in self.audio_sources.values(): #resource_id
            if source.resource_id == audio_id:
                return source
        raise Exception(f"Cannot find audio source with id {audio_id}")
                
    def get_string_entry(self, textbank_id: int, entry_id: int) -> StringEntry:
        try:
            return self.get_text_bank(textbank_id).entries[entry_id]
        except KeyError:
            raise Exception(f"Cannot find string with id {entry_id} in textbank with id {textbank_id}")
            
    def get_string_entries(self, textbank_id: int) -> dict[int, StringEntry]:
        return self.get_text_bank(textbank_id).entries
                
    def get_hierarchy_entry(self, soundbank_id: int, hierarchy_id: int) -> HircEntry:
        try:
            return self.get_wwise_bank(soundbank_id).hierarchy.get_entry(hierarchy_id)
        except:
            raise Exception(f"Cannot find wwise hierarchy entry with id {hierarchy_id} in soundbank with id {soundbank_id}")
            
    def get_hierarchy_entries(self, soundbank_id: int) -> dict[int, HircEntry]:
        return self.get_wwise_bank(soundbank_id).hierarchy.get_entries()
            
    def get_wwise_bank(self, soundbank_id: int) -> WwiseBank:
        try:
            return self.wwise_banks[soundbank_id]
        except KeyError:
            raise Exception(f"Cannot find soundbank with id {soundbank_id}")
        
    def set_wwise_bank(self, soundbank_id: int, bank: WwiseBank):
        self.wwise_banks[soundbank_id] = bank
        
    def get_wwise_stream(self, stream_id: int) -> WwiseStream:
        try:
            return self.wwise_streams[stream_id]
        except KeyError:
            raise Exception(f"Cannot find wwise stream with id {stream_id}")
        
    def set_wwise_stream(self, stream_id: int, stream: WwiseStream):
        self.wwise_streams[stream_id] = stream
    
    def get_text_bank(self, textbank_id: int) -> TextBank:
        try:
            return self.text_banks[textbank_id]
        except KeyError:
            raise Exception(f"Cannot find text bank with id {textbank_id}")
    
    def get_game_archives(self) -> dict[str, GameArchive]:
        return self.game_archives
        
    def get_game_archive(self, archive_name: str) -> GameArchive:
        try:
            return self.get_game_archives()[archive_name]
        except KeyError:
            raise Exception(f"Cannot find game archive {archive_name}")
        
    def get_wwise_streams(self) -> dict[int, WwiseStream]:
        return self.wwise_streams
        
    def get_wwise_banks(self) -> dict[int, WwiseBank]:
        return self.wwise_banks
        
    def get_audio_sources(self) -> dict[int, AudioSource]:
        return self.audio_sources
        
    def get_text_banks(self) -> dict[int, TextBank]:
        return self.text_banks
        
    def load_archive_file(self, archive_file: str = ""):
        if not archive_file or not os.path.exists(archive_file) or not os.path.isfile(archive_file):
            raise ValueError("Invalid path!")
        if os.path.splitext(archive_file)[1] in (".stream", ".gpu_resources"):
            archive_file = os.path.splitext(archive_file)[0]
        new_archive = GameArchive.from_file(archive_file)
        self.add_game_archive(new_archive)
        return True
        
    def import_wwise_hierarchy(self, soundbank_id: int, new_hierarchy: WwiseHierarchy):
        self.get_wwise_bank(soundbank_id).import_hierarchy(new_hierarchy)
        
    def generate_hierarchy_id(self, soundbank_id: int) -> int:
        hierarchy = self.get_wwise_bank(soundbank_id).hierarchy
        new_id = random.randint(0, 0xffffffff)
        while new_id in hierarchy.entries.keys():
            new_id = random.randint(0, 0xffffffff)
        return new_id
        
    def remove_game_archive(self, archive_name: str = ""):
        
        if archive_name not in self.game_archives.keys():
            return
            
        game_archive = self.game_archives[archive_name]
            
        for key in game_archive.wwise_banks.keys():
            if key in self.get_wwise_banks().keys():
                self.bank_count[key] -= 1
                if self.bank_count[key] == 0:
                    for audio in self.get_wwise_banks()[key].get_content():
                        parents = [p for p in audio.parents]
                        for parent in parents:
                            if isinstance(parent, HircEntry) and parent.soundbank.get_id() == key:
                                audio.parents.remove(parent)
                    del self.get_wwise_banks()[key]
                    del self.bank_count[key]
        for key in game_archive.wwise_streams.keys():
            if key in self.get_wwise_streams().keys():
                self.stream_count[key] -= 1
                if self.stream_count[key] == 0:
                    self.get_wwise_streams()[key].audio_source.parents.remove(self.get_wwise_streams()[key])
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
    
    def add_game_archive(self, game_archive: GameArchive):
        key = game_archive.name
        if key in self.game_archives.keys():
            return
        else:
            self.game_archives[key] = game_archive
            for key in game_archive.wwise_banks.keys():
                if key in self.get_wwise_banks().keys():
                    self.bank_count[key] += 1
                    for audio in game_archive.wwise_banks[key].get_content():
                        parents = [p for p in audio.parents]
                        for parent in parents:
                            if isinstance(parent, HircEntry) and parent.soundbank.get_id() == key:
                                audio.parents.remove(parent)
                                try:
                                    new_parent = self.get_hierarchy_entry(key, parent.get_id())
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
                        self.get_audio_sources()[key].parents.add(parent)
                    game_archive.audio_sources[key] = self.get_audio_sources()[key]
                else:
                    self.audio_count[key] = 1
                    self.get_audio_sources()[key] = game_archive.audio_sources[key]
            
    def import_patch(self, patch_file: str = ""):
        if os.path.splitext(patch_file)[1] in (".stream", ".gpu_resources"):
            patch_file = os.path.splitext(patch_file)[0]
        if not os.path.exists(patch_file) or not os.path.isfile(patch_file):
            raise ValueError("Invalid file!")
        
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
                    if isinstance(item, MusicTrack):
                        item.parent.set_data(duration=len_ms, entry_marker=0, exit_marker=len_ms)
                        tracks = copy.deepcopy(item.track_info)
                        for t in tracks:
                            if t.source_id == old_audio.get_short_id():
                                t.begin_trim_offset = 0
                                t.end_trim_offset = 0
                                t.source_duration = len_ms
                                t.play_at = 0
                                break
                        item.set_data(track_info=tracks)
                            
        for bank in patch_game_archive.get_wwise_banks().values():
            self.get_wwise_banks()[bank.get_id()].import_hierarchy(bank.hierarchy)
                            

        for text_bank in patch_game_archive.get_text_banks().values():
            self.get_text_banks()[text_bank.get_id()].import_text(text_bank)
        
        return True

    def write_patch(self, output_folder: str = ""):
        if not os.path.exists(output_folder) or not os.path.isdir(output_folder):
            raise ValueError(f"Invalid output folder '{output_folder}'")
        patch_game_archive = GameArchive()
        patch_game_archive.name = "9ba626afa44a3aa3.patch_0"
        patch_game_archive.magic = 0xF0000011
        patch_game_archive.num_types = 0
        patch_game_archive.num_files = 0
        patch_game_archive.unknown = 0
        patch_game_archive.unk4Data = bytes.fromhex("CE09F5F4000000000C729F9E8872B8BD00A06B02000000000079510000000000000000000000000000000000000000000000000000000000")
        patch_game_archive.audio_sources = self.audio_sources
        patch_game_archive.wwise_banks = {}
        patch_game_archive.wwise_streams = {}
        patch_game_archive.text_banks = {}
            
        for key, value in self.get_wwise_streams().items():
            if value.modified:
                patch_game_archive.wwise_streams[key] = value
                
        for key, value in self.get_wwise_banks().items():
            if value.modified:
                patch_game_archive.wwise_banks[key] = value
                
        for key, value in self.get_text_banks().items():
            if value.modified:
                patch_game_archive.text_banks[key] = value
 
        patch_game_archive.to_file(output_folder)

    def import_wems(self, wems: dict[str, list[int]] | None = None, set_duration=True): 
        if not wems:
            raise Exception("No wems selected for import")
        length_import_failed = False
        for filepath, targets in wems.items():
            if not os.path.exists(filepath) or not os.path.isfile(filepath):
                continue
            have_length = True
            with open(filepath, 'rb') as f:
                audio_data = f.read()    
            if set_duration:
                try:
                    process = subprocess.run([VGMSTREAM, "-m", filepath], capture_output=True)
                    process.check_returncode()
                    for line in process.stdout.decode(locale.getpreferredencoding()).split("\n"):
                        if "sample rate" in line:
                            sample_rate = float(line[13:line.index("Hz")-1])
                        if "stream total samples" in line:
                            total_samples = int(line[22:line.index("(")-1])
                    len_ms = total_samples * 1000 / sample_rate
                except:
                    have_length = False
                    length_import_failed = True
            for target in targets:
                audio: AudioSource | None = self.get_audio_source(target)
                if audio:
                    audio.set_data(audio_data)
                    if have_length:
                        # find music segment for Audio Source
                        for item in audio.parents:
                            if isinstance(item, MusicTrack):
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
        if length_import_failed:
            raise Exception("Failed to set track duration for some audio sources")
    
    def create_external_sources_list(self, sources: list[str], converstion_setting: str = DEFAULT_CONVERSION_SETTING) -> str:
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
        file.write(os.path.join(CACHE, "external_sources.wsources"))
        
        return os.path.join(CACHE, "external_sources.wsources")
        
    def import_wavs(self, wavs: dict[str, list[int]] | None = None, wwise_project: str = DEFAULT_WWISE_PROJECT):
        if not wavs:
            raise ValueError("No wav files selected for import!")
            
        source_list = self.create_external_sources_list(wavs.keys())
        
        if SYSTEM in WWISE_SUPPORTED_SYSTEMS:
            subprocess.run([
                WWISE_CLI,
                "migrate",
                wwise_project,
                "--quiet",
            ]).check_returncode()
        else:
            raise Exception("The current operating system does not support this feature")
        
        convert_dest = os.path.join(CACHE, SYSTEM)
        if SYSTEM in WWISE_SUPPORTED_SYSTEMS:
            subprocess.run([
                WWISE_CLI,
                "convert-external-source",
                wwise_project,
                "--platform", "Windows",
                "--source-file",
                source_list,
                "--output",
                CACHE,
            ]).check_returncode()
        else:
            raise Exception("The current operating system does not support this feature")
        
        wems = {os.path.join(convert_dest, filepath): targets for filepath, targets in wavs.items()}
        
        self.import_wems(wems)
        
        for wem in wems.keys():
            try:
                os.remove(wem)
            except:
                pass
                
        try:
            os.remove(source_list)
        except:
            pass
            
    def import_files(self, file_dict: dict[str, list[int]]):
        patches = [file for file in file_dict.keys() if "patch" in os.path.splitext(file)[1]]
        wems = {file: targets for file, targets in file_dict.items() if os.path.splitext(file)[1] == ".wem"}
        wavs = {file: targets for file, targets in file_dict.items() if os.path.splitext(file)[1] == ".wav"}
        
        # check other file extensions and call vgmstream to convert to wav, then add to wavs dict
        filetypes = list(SUPPORTED_AUDIO_TYPES)
        filetypes.remove(".wav")
        filetypes.remove(".wem")
        others = {file: targets for file, targets in file_dict.items() if os.path.splitext(file)[1] in filetypes}
        temp_files = []
        for file in others.keys():
            process = subprocess.run([VGMSTREAM, "-o", f"{os.path.join(CACHE, os.path.splitext(os.path.basename(file))[0])}.wav", file], stdout=subprocess.DEVNULL).check_returncode()
            wavs[f"{os.path.join(CACHE, os.path.splitext(os.path.basename(file))[0])}.wav"] = others[file]
            temp_files.append(f"{os.path.join(CACHE, os.path.splitext(os.path.basename(file))[0])}.wav")
        
        for patch in patches:
            self.import_patch(patch_file=patch)
        if len(wems) > 0:
            self.import_wems(wems)
        if len(wavs) > 0:
            self.import_wavs(wavs)
        for file in temp_files:
            try:
                os.remove(file)
            except:
                pass
        
class ModHandler:
    
    handler_instance = None
    
    def __init__(self):
        self.mods = {}
        
    @classmethod
    def create_instance(cls):
        cls.handler_instance = ModHandler()
        
    @classmethod
    def get_instance(cls) -> Self:
        if cls.handler_instance == None:
            cls.create_instance()
        return cls.handler_instance
        
    def create_new_mod(self, mod_name: str):
        if mod_name in self.mods.keys():
            raise ValueError(f"Mod name '{mod_name}' already exists!")
        new_mod = Mod(mod_name)
        self.mods[mod_name] = new_mod
        self.active_mod = new_mod
        return new_mod
        
    def get_active_mod(self) -> Mod:
        if not self.active_mod:
            raise Exception("No active mod!")
        return self.active_mod
        
    def set_active_mod(self, mod_name: str):
        try:
            self.active_mod = self.mods[mod_name]
        except:
            raise ValueError(f"No matching mod found for '{mod_name}'")
            
    def get_mod_names(self) -> list[str]:
        return self.mods.keys()
        
    def delete_mod(self, mod: str | Mod):
        if isinstance(mod, Mod):
            mod_name = mod.name
        else:
            mod_name = mod
        try:
            mod_to_delete = self.mods[mod_name]
        except:
            raise ValueError(f"No matching mod found for '{mod}'")
        if mod_to_delete is self.active_mod:
            if len(self.mods) > 1:
                for mod in self.mods.values():
                    if mod is not self.active_mod:
                        self.active_mod = mod
                        break
            else:
                self.active_mod = None
        del self.mods[mod_name]
