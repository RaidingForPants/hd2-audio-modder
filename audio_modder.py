import copy
import numpy
import os
import platform
import pyaudio
import subprocess
import struct
import tkinter
import wave

from functools import partial
from itertools import takewhile
from math import ceil
from tkinter import *
from tkinter import ttk
from tkinter import filedialog
from tkinter.filedialog import askopenfilename
from typing import Any, Literal, Tuple, Union

import config as cfg
import log
import fileutil

import config as cfg

from log import logger

#constants
MUSIC_TRACK = 11
SOUND = 2
BANK = 0
PREFETCH_STREAM = 1
STREAM = 2
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
VORBIS = 0x00040001
DRIVE_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
WWISE_BANK = 6006249203084351385
WWISE_DEP = 12624162998411505776
WWISE_STREAM = 5785811756662211598
STRING = 979299457696010195
LANGUAGE_MAPPING = ({
    "English (US)" : 0x03f97b57,
    "English (UK)" : 0x6f4515cb,
    "Français" : 4271961631,
    "Português 1": 1861586415,
    "Português 2": 1244441033,
    "Polski": 260593578,
    "日本語": 2427891497,
    "中文（繁體）": 2663028010,
    "中文（简体）": 2189905090,
    "Nederlands": 291057413,
    "한국어": 3151476177,
    "Español 1": 830498882,
    "Español 2": 3854981686,
    "Deutsch": 3124347884,
    "Italiano": 3808107213,
    "Русский": 3317373165
})

#"constants" (set once on runtime)
FFMPEG = ""
GAME_FILE_LOCATION = ""
VGMSTREAM = ""

#global variables
language = 0
num_segments = 0


def look_for_steam_install_windows():
    path = "C:\\Program Files (x86)\\steam\\steamapps\\common\\Helldivers 2\\data"
    if os.path.exists(path):
        return path
    for letter in DRIVE_LETTERS:
        path = f"{letter}:\\SteamLibrary\\steamapps\\common\\Helldivers 2\\data"
        if os.path.exists(path):
            return path
    return ""
    
def language_lookup(lang_string):
    try:
        return LANGUAGE_MAPPING[lang_string]
    except:
        return int(lang_string)
    
def strip_patch_index(filename):
    split = filename.split(".")
    for n in range(len(split)):
        if "patch_" in split[n]:
            del split[n]
            break
    filename = ".".join(split)
    return filename

class MemoryStream:
    '''
    Modified from https://github.com/kboykboy2/io_scene_helldivers2 with permission from kboykboy
    '''
    def __init__(self, Data=b"", io_mode = "read"):
        self.location = 0
        self.data = bytearray(Data)
        self.io_mode = io_mode
        self.endian = "<"

    def open(self, Data, io_mode = "read"): # Open Stream
        self.data = bytearray(Data)
        self.io_mode = io_mode

    def set_read_mode(self):
        self.io_mode = "read"

    def set_write_mode(self):
        self.io_mode = "write"

    def is_reading(self):
        return self.io_mode == "read"

    def is_writing(self):
        return self.io_mode == "write"

    def seek(self, location): # Go To Position In Stream
        self.location = location
        if self.location > len(self.data):
            missing_bytes = self.location - len(self.data)
            self.data += bytearray(missing_bytes)

    def tell(self): # Get Position In Stream
        return self.location

    def read(self, length=-1): # read Bytes From Stream
        if length == -1:
            length = len(self.data) - self.location
        if self.location + length > len(self.data):
            raise Exception("reading past end of stream")

        newData = self.data[self.location:self.location+length]
        self.location += length
        return bytearray(newData)

    def write(self, bytes): # Write Bytes To Stream
        length = len(bytes)
        if self.location + length > len(self.data):
            missing_bytes = (self.location + length) - len(self.data)
            self.data += bytearray(missing_bytes)
        self.data[self.location:self.location+length] = bytearray(bytes)
        self.location += length

    def read_format(self, format, size):
        format = self.endian+format
        return struct.unpack(format, self.read(size))[0]
        
    def bytes(self, value, size = -1):
        if size == -1:
            size = len(value)
        if len(value) != size:
            value = bytearray(size)

        if self.is_reading():
            return bytearray(self.read(size))
        elif self.is_writing():
            self.write(value)
            return bytearray(value)
        return value
        
    def int8_read(self):
        return self.read_format('b', 1)

    def uint8_read(self):
        return self.read_format('B', 1)

    def int16_read(self):
        return self.read_format('h', 2)

    def uint16_read(self):
        return self.read_format('H', 2)

    def int32_read(self):
        return self.read_format('i', 4)

    def uint32_read(self):
        return self.read_format('I', 4)

    def int64_read(self):
        return self.read_format('q', 8)

    def uint64_read(self):
        return self.read_format('Q', 8)
        
def pad_to_16_byte_align(data):
    b = bytearray(data)
    l = len(b)
    new_len = ceil(l/16)*16
    return b + bytearray(new_len-l)
    
def _16_byte_align(addr):
    return ceil(addr/16)*16
    
def bytes_to_long(bytes):
    assert len(bytes) == 8
    return sum((b << (k * 8) for k, b in enumerate(bytes)))

def murmur64_hash(data, seed = 0):

    m = 0xc6a4a7935bd1e995
    r = 47

    MASK = 2 ** 64 - 1

    data_as_bytes = bytearray(data)

    h = seed ^ ((m * len(data_as_bytes)) & MASK)

    off = int(len(data_as_bytes)/8)*8
    for ll in range(0, off, 8):
        k = bytes_to_long(data_as_bytes[ll:ll + 8])
        k = (k * m) & MASK
        k = k ^ ((k >> r) & MASK)
        k = (k * m) & MASK
        h = (h ^ k)
        h = (h * m) & MASK

    l = len(data_as_bytes) & 7

    if l >= 7:
        h = (h ^ (data_as_bytes[off+6] << 48))

    if l >= 6:
        h = (h ^ (data_as_bytes[off+5] << 40))

    if l >= 5:
        h = (h ^ (data_as_bytes[off+4] << 32))

    if l >= 4:
        h = (h ^ (data_as_bytes[off+3] << 24))

    if l >= 3:
        h = (h ^ (data_as_bytes[off+2] << 16))

    if l >= 2:
        h = (h ^ (data_as_bytes[off+1] << 8))

    if l >= 1:
        h = (h ^ data_as_bytes[off])
        h = (h * m) & MASK

    h = h ^ ((h >> r) & MASK)
    h = (h * m) & MASK
    h = h ^ ((h >> r) & MASK)

    return h

class Subscriber:
    def __init__(self):
        pass
        
    def update(self, content):
        pass
        
    def raise_modified(self):
        pass
        
    def lower_modified(self):
        pass
        
class AudioSource:

    def __init__(self):
        self.data = b""
        self.size = 0
        self.resource_id = 0
        self.short_id = 0
        self.modified = False
        self.data_OLD = b""
        self.subscribers = set()
        self.stream_type = 0
        self.track_info = None
        
    def set_data(self, data, notify_subscribers=True, set_modified=True):
        if not self.modified and set_modified:
            self.data_OLD = self.data
        self.data = data
        self.size = len(self.data)
        if notify_subscribers:
            for item in self.subscribers:
                item.update(self)
                if not self.modified:
                    item.raise_modified()
        if set_modified:
            self.modified = True
            
    def get_id(self):
        if self.stream_type == BANK:
            return self.get_short_id()
        else:
            return self.get_resource_id()
            
    def is_modified(self):
        return self.modified
            
    def set_track_info(self, track_info,  notify_subscribers=True, set_modified=True):
        if not self.modified and set_modified:
            self.track_info_old = self.track_info
        self.track_info = track_info
        if notify_subscribers:
            for item in self.subscribers:
                item.update(self)
                if not self.modified:
                    item.raise_modified()
        if set_modified:
            self.modified = True
            
    def get_track_info(self):
        return self.track_info
        
    def get_data(self):
        return self.data
        
    def get_resource_id(self):
        return self.resource_id
        
    def get_short_id(self):
        return self.short_id
        
    def revert_modifications(self, notify_subscribers=True):
        if self.modified:
            self.modified = False
            if self.data_OLD != b"":
                self.data = self.data_OLD
                self.data_OLD = b""
            if self.track_info is not None:
                self.track_info.revert_modifications()
            self.size = len(self.data)
            if notify_subscribers:
                for item in self.subscribers:
                    item.lower_modified()
                    item.update(self)
                
class TocHeader:

    def __init__(self):
        pass
        
    def from_memory_stream(self, stream):
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
        
    def get_data(self):
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
        
    def from_memory_stream(self, stream):
        self.offset = stream.tell()
        self.tag = stream.uint32_read()
        self.data_size = stream.uint32_read()
        self.data = stream.read(self.data_size).decode('utf-8')
        
    def get_data(self):
        return (self.tag.to_bytes(4, byteorder='little')
                + self.data_size.to_bytes(4, byteorder='little')
                + self.data.encode('utf-8'))
                
class DidxEntry:
    def __init__(self):
        self.id = self.offset = self.size = 0
        
    @classmethod
    def from_bytes(cls, bytes):
        e = DidxEntry()
        e.id, e.offset, e.size = struct.unpack("<III", bytes)
        return e
        
    def get_data(self):
        return struct.pack("<III", self.id, self.offset, self.size)
        
class MediaIndex:

    def __init__(self):
        self.entries = {}
        self.data = {}
        
    def load(self, didxChunk, dataChunk):
        for n in range(int(len(didxChunk)/12)):
            entry = DidxEntry.from_bytes(didxChunk[12*n : 12*(n+1)])
            self.entries[entry.id] = entry
            self.data[entry.id] = dataChunk[entry.offset:entry.offset+entry.size]
        
    def get_data(self):
        arr = [x.get_data() for x in self.entries.values()]
        data_arr = self.data.values()
        return b"".join(arr) + b"".join(data_arr)
                
class HircEntry:
    
    def __init__(self):
        self.size = self.hierarchy_type = self.hierarchy_id = self.misc = 0
        self.sources = []
        self.track_info = []
    
    @classmethod
    def from_memory_stream(cls, stream):
        entry = HircEntry()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
        entry.hierarchy_id = stream.uint32_read()
        entry.misc = stream.read(entry.size - 4)
        return entry
        
    def get_id(self):
        return self.hierarchy_id
        
    def get_data(self):
        return self.hierarchy_type.to_bytes(1, byteorder="little") + self.size.to_bytes(4, byteorder="little") + self.hierarchy_id.to_bytes(4, byteorder="little") + self.misc
        
class MusicRandomSequence(HircEntry):
    
    def __init__(self):
        super().__init__()
    
    @classmethod
    def from_memory_stream(cls, stream):
        entry = MusicRandomSequence()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
        entry.hierarchy_id = stream.uint32_read()
        return entry
        
    def get_data(self):
        pass
    
class MusicSegment(HircEntry):

    def __init__(self):
        super().__init__()
        self.tracks = []
        self.duration = 0
        self.entry_marker = None
        self.exit_marker = None
        self.unused_sections = []
        self.markers = []
        self.modified = False
    
    @classmethod
    def from_memory_stream(cls, stream):
        global num_segments
        num_segments += 1
        entry = MusicSegment()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
        start_position = stream.tell()
        entry.hierarchy_id = stream.uint32_read()
        entry.unused_sections.append(stream.read(15))
        n = stream.uint8_read() #number of props
        stream.seek(stream.tell()-1)
        entry.unused_sections.append(stream.read(5*n + 1))
        n = stream.uint8_read() #number of props (again)
        stream.seek(stream.tell()-1)
        entry.unused_sections.append(stream.read(5*n + 1 + 12 + 4)) #the 4 is the count of state props, state chunks, and RTPC, which are currently always 0
        n = stream.uint32_read() #number of children (tracks)
        for _ in range(n):
            entry.tracks.append(stream.uint32_read())
        entry.unused_sections.append(stream.read(23)) #meter info
        n = stream.uint32_read() #number of stingers
        stream.seek(stream.tell()-4)
        entry.unused_sections.append(stream.read(24*n + 4))
        entry.duration = struct.unpack("<d", stream.read(8))[0]
        n = stream.uint32_read() #number of markers
        for i in range(n):
            id = stream.uint32_read()
            position = struct.unpack("<d", stream.read(8))[0]
            name = []
            temp = b"1"
            while temp != b"\x00":
                temp = stream.read(1)
                name.append(temp)
            name = b"".join(name)
            marker = [id, position, name]
            entry.markers.append(marker)
            if i == 0:
                entry.entry_marker = marker
            elif i == n-1:
                entry.exit_marker = marker
        return entry
        
    def set_data(self, duration=None, entry_marker=None, exit_marker=None):
        if not self.modified:
            self.duration_old = self.duration
            self.entry_marker_old = self.entry_marker[1]
            self.exit_marker_old = self.exit_marker[1]
        if duration is not None: self.duration = duration
        if entry_marker is not None: self.entry_marker[1] = entry_marker
        if exit_marker is not None: self.exit_marker[1] = exit_marker
        self.modified = True
        
    def revert_modifications(self):
        if self.modified:
            self.entry_marker[1] = self.entry_marker_old
            self.exit_marker[1] = self.exit_marker_old
            self.duration = self.duration_old
            self.modified = False
        
    def get_data(self):
        return (
            b"".join([
                struct.pack("<BII", self.hierarchy_type, self.size, self.hierarchy_id),
                self.unused_sections[0],
                self.unused_sections[1],
                self.unused_sections[2],
                len(self.tracks).to_bytes(4, byteorder="little"),
                b"".join([x.to_bytes(4, byteorder="little") for x in self.tracks]),
                self.unused_sections[3],
                self.unused_sections[4],
                struct.pack("<d", self.duration),
                len(self.markers).to_bytes(4, byteorder="little"),
                b"".join([b"".join([x[0].to_bytes(4, byteorder="little"), struct.pack("<d", x[1]), x[2]]) for x in self.markers])
            ])
        )
        
class HircEntryFactory:
    
    @classmethod
    def from_memory_stream(cls, stream):
        hierarchy_type = stream.uint8_read()
        stream.seek(stream.tell()-1)
        if hierarchy_type == 2: #sound
            return Sound.from_memory_stream(stream)
        elif hierarchy_type == 11: #music track
            return MusicTrack.from_memory_stream(stream)
        elif hierarchy_type == 0x0A: #music segment
            return MusicSegment.from_memory_stream(stream)
        else:
            return HircEntry.from_memory_stream(stream)
        
class HircReader:
    
    def __init__(self):
        self.entries = {}
        
    def load(self, hierarchy_data):
        self.entries.clear()
        reader = MemoryStream()
        reader.write(hierarchy_data)
        reader.seek(0)
        num_items = reader.uint32_read()
        for item in range(num_items):
            entry = HircEntryFactory.from_memory_stream(reader)
            self.entries[entry.get_id()] = entry
            
    def get_data(self):
        arr = [entry.get_data() for entry in self.entries.values()]
        return len(arr).to_bytes(4, byteorder="little") + b"".join(arr)
            
class BankParser:
    
    def __init__(self):
        self.chunks = {}
        
    def load(self, bank_data):
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
            
    def GetChunk(self, chunk_tag):
        try:
            return self.chunks[chunk_tag]
        except:
            return None
            
class BankSourceStruct:

    def __init__(self):
        self.plugin_id = 0
        self.stream_type = self.source_id = self.mem_size = self.bit_flags = 0
        
    @classmethod
    def from_bytes(cls, bytes):
        b = BankSourceStruct()
        b.plugin_id, b.stream_type, b.source_id, b.mem_size, b.bit_flags = struct.unpack("<IBIIB", bytes)
        return b
        
    def get_data(self):
        return struct.pack("<IBIIB", self.plugin_id, self.stream_type, self.source_id, self.mem_size, self.bit_flags)
        
class TrackInfoStruct:
    
    def __init__(self):
        self.track_id = self.source_id = self.event_id = self.play_at = self.begin_trim_offset = self.end_trim_offset = self.source_duration = 0
        self.play_at_old = self.begin_trim_offset_old = self.end_trim_offset_old = self.source_duration_old = 0
        self.modified = False
        
    @classmethod
    def from_bytes(cls, bytes):
        t = TrackInfoStruct()
        t.track_id, t.source_id, t.event_id, t.play_at, t.begin_trim_offset, t.end_trim_offset, t.source_duration = struct.unpack("<IIIdddd", bytes)
        return t
        
    def get_id(self):
        if self.source_id != 0:
            return self.source_id
        else:
            return self.event_id
            
    def is_modified(self):
        return self.modified
            
    def set_data(self, play_at=None, begin_trim_offset=None, end_trim_offset=None, source_duration=None):
        if not self.modified:
            self.play_at_old = self.play_at
            self.begin_trim_offset_old = self.begin_trim_offset
            self.end_trim_offset_old = self.end_trim_offset
            self.source_duration_old = self.source_duration
        if play_at is not None: self.play_at = play_at
        if begin_trim_offset is not None: self.begin_trim_offset = begin_trim_offset
        if end_trim_offset is not None: self.end_trim_offset = end_trim_offset
        if source_duration is not None: self.source_duration = source_duration
        self.modified = True
        
    def revert_modifications(self):
        if self.modified:
            self.play_at = self.play_at_old
            self.begin_trim_offset = self.begin_trim_offset_old
            self.end_trim_offset = self.end_trim_offset_old
            self.source_duration = self.source_duration_old
            self.modified = False
        
    def get_data(self):
        return struct.pack("<IIIdddd", self.track_id, self.source_id, self.event_id, self.play_at, self.begin_trim_offset, self.end_trim_offset, self.source_duration)
            
class MusicTrack(HircEntry):
    
    def __init__(self):
        super().__init__()
        self.bit_flags = 0
        
    @classmethod
    def from_memory_stream(cls, stream):
        entry = MusicTrack()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
        start_position = stream.tell()
        entry.hierarchy_id = stream.uint32_read()
        entry.bit_flags = stream.uint8_read()
        num_sources = stream.uint32_read()
        for _ in range(num_sources):
            source = BankSourceStruct.from_bytes(stream.read(14))
            entry.sources.append(source)
        num_track_info = stream.uint32_read()
        for _ in range(num_track_info):
            track = TrackInfoStruct.from_bytes(stream.read(44))
            entry.track_info.append(track)
        entry.misc = stream.read(entry.size - (stream.tell()-start_position))
        return entry

    def get_data(self):
        b = b"".join([source.get_data() for source in self.sources])
        t = b"".join([track.get_data() for track in self.track_info])
        return struct.pack("<BIIBI", self.hierarchy_type, self.size, self.hierarchy_id, self.bit_flags, len(self.sources)) + b + len(self.track_info).to_bytes(4, byteorder="little") + t + self.misc
    
class Sound(HircEntry):
    
    def __init__(self):
        super().__init__()
    
    @classmethod
    def from_memory_stream(cls, stream):
        entry = Sound()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
        entry.hierarchy_id = stream.uint32_read()
        entry.sources.append(BankSourceStruct.from_bytes(stream.read(14)))
        entry.misc = stream.read(entry.size - 18)
        return entry

    def get_data(self):
        return struct.pack(f"<BII14s{len(self.misc)}s", self.hierarchy_type, self.size, self.hierarchy_id, self.sources[0].get_data(), self.misc)
        
class WwiseBank(Subscriber):
    
    def __init__(self):
        self.data = b""
        self.bank_header = b""
        self.toc_data_header = b""
        self.bank_misc_data = b""
        self.modified = False
        self.toc_header = None
        self.dep = None
        self.modified_count = 0
        self.hierarchy = None
        self.content = []
        
    def add_content(self, content):
        content.subscribers.add(self)
        self.content.append(content)
        
    def remove_content(self, content):
        try:
            content.subscribers.remove(self)
        except:
            pass
            
        try:
            self.content.remove(content)
        except:
            pass
  
    def get_content(self):
        return self.content
        
    def raise_modified(self):
        self.modified = True
        self.modified_count += 1
        
    def lower_modified(self):
        if self.modified:
            self.modified_count -= 1
            if self.modified_count == 0:
                self.modified = False
        
    def get_name(self):
        return self.dep.data
        
    def get_id(self):
        try:
            return self.toc_header.file_id
        except:
            return 0
            
    def get_type_id(self):
        try:
            return self.toc_header.type_id
        except:
            return 0
            
    def get_data(self):
        return self.data
            
    def generate(self, audio_sources, eventTrackInfo):
        data = bytearray()
        data += self.bank_header
        
        didx_section = b""
        data_section = b""
        offset = 0
        
        #regenerate soundbank from the hierarchy information
        max_progress = 0
        for entry in self.hierarchy.entries.values():
            if entry.hierarchy_type == SOUND:
                max_progress += 1
            elif entry.hierarchy_type == MUSIC_TRACK:
                max_progress += len(entry.sources)
                    
        
        bank_generation_progress_window = ProgressWindow("Generating Soundbanks", max_progress)
        bank_generation_progress_window.show()
        bank_generation_progress_window.set_text(f"Generating {self.dep.data}")
        
        didx_array = []
        data_array = []
        
        for entry in self.hierarchy.entries.values():
            for index, info in enumerate(entry.track_info):
                if info.event_id != 0:
                    entry.track_info[index] = eventTrackInfo[info.event_id]
            for source in entry.sources:
                bank_generation_progress_window.step()
                if source.plugin_id == VORBIS:
                    try:
                        audio = audio_sources[source.source_id]
                    except KeyError:
                        continue
                    try:
                        count = 0
                        for info in entry.track_info:
                            if info.source_id == source.source_id:
                                break
                            count += 1
                        if audio.get_track_info() is not None: #is this needed?
                            entry.track_info[count] = audio.get_track_info()
                        else:
                            pass
                            #print(audio.get_id())
                            #print(entry.track_info[count])
                    except: #exception because there may be no original track info struct
                        pass
                    if source.stream_type == PREFETCH_STREAM:
                        data_array.append(audio.get_data()[:source.mem_size])
                        didx_array.append(struct.pack("<III", source.source_id, offset, source.mem_size))
                        offset += source.mem_size
                    elif source.stream_type == BANK:
                        data_array.append(audio.get_data())
                        didx_array.append(struct.pack("<III", source.source_id, offset, audio.size))
                        offset += audio.size
        if len(didx_array) > 0:
            data += "DIDX".encode('utf-8') + (12*len(didx_array)).to_bytes(4, byteorder="little")
            data += b"".join(didx_array)
            data += "DATA".encode('utf-8') + sum([len(x) for x in data_array]).to_bytes(4, byteorder="little")
            data += b"".join(data_array)
            
        hierarchy_section = self.hierarchy.get_data()
        data += "HIRC".encode('utf-8') + len(hierarchy_section).to_bytes(4, byteorder="little")
        data += hierarchy_section
        data += self.bank_misc_data
        self.toc_header.toc_data_size = len(data) + len(self.toc_data_header)
        self.toc_data_header[4:8] = len(data).to_bytes(4, byteorder="little")
        self.data = data
        bank_generation_progress_window.destroy()
                     
    def get_entry_index(self):
        try:
            return self.toc_header.entry_index
        except:
            return 0
        
class WwiseStream(Subscriber):

    def __init__(self):
        self.content = None
        self.modified = False
        self.toc_header = None
        self.TocData = bytearray()
        
    def set_content(self, content):
        try:
            self.content.subscribers.remove(self)
        except:
            pass
        self.content = content
        content.subscribers.add(self)
        
    def update(self, content):
        self.toc_header.stream_size = content.size
        self.TocData[8:12] = content.size.to_bytes(4, byteorder='little')
        
    def raise_modified(self):
        self.modified = True
        
    def lower_modified(self):
        self.modified = False
        
    def get_id(self):
        try:
            return self.toc_header.file_id
        except:
            return 0
        
    def get_type_id(self):
        try:
            return self.toc_header.type_id
        except:
            return 0
            
    def get_entry_index(self):
        try:
            return self.toc_header.entry_index
        except:
            return 0
            
    def get_data(self):
        return self.content.get_data()

class StringEntry:

    def __init__(self):
        self.text = ""
        self.text_old = ""
        self.string_id = 0
        self.modified = False
        
    def get_id(self):
        return self.string_id
        
    def get_text(self):
        return self.text
        
    def set_text(self, text):
        if not self.modified:
            self.text_old = self.text
        self.modified = True
        self.text = text
        
    def revert_modifications(self):
        if self.modified:
            self.text = self.text_old
            self.modified = False
        
class TextBank:
    
    def __init__(self):
        self.toc_header = None
        self.data = b''
        self.string_ids = []
        self.language = 0
        self.modified = False
        
    def set_data(self, data):
        self.string_ids.clear()
        num_entries = int.from_bytes(data[8:12], byteorder='little')
        id_section_start = 16
        offset_section_start = id_section_start + 4 * num_entries
        data_section_start = offset_section_start + 4 * num_entries
        ids = data[id_section_start:offset_section_start]
        offsets = data[offset_section_start:data_section_start]
        for n in range(num_entries):
            string_id = int.from_bytes(ids[4*n:+4*(n+1)], byteorder="little")
            self.string_ids.append(string_id)
            
    def update(self):
        pass
        
    def get_data(self):
        return self.data
        
    def GetLanguage(self):
        return self.language
        
    def is_modified(self):
        return self.modified
        
    def generate(self, string_entries):
        entries = string_entries[self.language]
        stream = MemoryStream()
        stream.write(b'\xae\xf3\x85\x3e\x01\x00\x00\x00')
        stream.write(len(self.string_ids).to_bytes(4, byteorder="little"))
        stream.write(self.language.to_bytes(4, byteorder="little"))
        offset = 16 + 8*len(self.string_ids)
        for i in self.string_ids:
            stream.write(entries[i].get_id().to_bytes(4, byteorder="little"))
        for i in self.string_ids:
            stream.write(offset.to_bytes(4, byteorder="little"))
            initial_position = stream.tell()
            stream.seek(offset)
            stream.write(entries[i].text.encode('utf-8') + b'\x00')
            offset += len(entries[i].text) + 1
            stream.seek(initial_position)
        self.data = stream.data
        self.toc_header.toc_data_size = len(self.data)
        
    def Rebuild(self, string_id, offset_difference):
        pass
        
    def get_id(self):
        try:
            return self.toc_header.file_id
        except:
            return 0
        
    def get_type_id(self):
        try:
            return self.toc_header.type_id
        except:
            return 0
            
    def get_entry_index(self):
        try:
            return self.toc_header.entry_index
        except:
            return 0

class FileReader:
    
    def __init__(self):
        self.wwise_streams = {}
        self.wwise_banks = {}
        self.audio_sources = {}
        self.text_banks = {}
        self.music_track_events = {}
        self.string_entries = {}
        self.music_segments = {}
        
    def from_file(self, path):
        self.name = os.path.basename(path)
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
            toc_file.write(pad_to_16_byte_align(stream.TocData))
            stream_file.seek(stream.toc_header.stream_file_offset)
            stream_file.write(pad_to_16_byte_align(stream.content.get_data()))
            
        for key in self.wwise_banks.keys():
            toc_file.seek(file_position)
            file_position += 80
            bank = self.wwise_banks[key]
            toc_file.write(bank.toc_header.get_data())
            toc_file.seek(bank.toc_header.toc_data_offset)
            toc_file.write(pad_to_16_byte_align(bank.toc_data_header + bank.get_data()))
            
        for key in self.wwise_banks.keys():
            toc_file.seek(file_position)
            file_position += 80
            bank = self.wwise_banks[key]
            toc_file.write(bank.dep.toc_header.get_data())
            toc_file.seek(bank.dep.toc_header.toc_data_offset)
            toc_file.write(pad_to_16_byte_align(bank.dep.get_data()))
            
        for key in self.text_banks.keys():
            toc_file.seek(file_position)
            file_position += 80
            entry = self.text_banks[key]
            toc_file.write(entry.toc_header.get_data())
            toc_file.seek(entry.toc_header.toc_data_offset)
            toc_file.write(pad_to_16_byte_align(entry.get_data()))
            
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
        for key, value in self.wwise_streams.items():
            value.toc_header.stream_file_offset = stream_file_offset
            value.toc_header.toc_data_offset = toc_file_offset
            stream_file_offset += _16_byte_align(value.toc_header.stream_size)
            toc_file_offset += _16_byte_align(value.toc_header.toc_data_size)
        
        for key, value in self.wwise_banks.items():
            value.generate(self.audio_sources, self.music_track_events)
            
            value.toc_header.toc_data_offset = toc_file_offset
            toc_file_offset += _16_byte_align(value.toc_header.toc_data_size)
            
        for key, value in self.wwise_banks.items():
            value.dep.toc_header.toc_data_offset = toc_file_offset
            toc_file_offset += _16_byte_align(value.toc_header.toc_data_size)
            
        for key, value in self.text_banks.items():
            value.generate(string_entries=self.string_entries)
            value.toc_header.toc_data_offset = toc_file_offset
            toc_file_offset += _16_byte_align(value.toc_header.toc_data_size)
        
    def load(self, toc_file, stream_file):
        self.wwise_streams.clear()
        self.wwise_banks.clear()
        self.audio_sources.clear()
        self.text_banks.clear()
        self.music_track_events.clear()
        self.string_entries.clear()
        self.music_segments.clear()
        
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
                entry = WwiseStream()
                entry.toc_header = toc_header
                toc_file.seek(toc_header.toc_data_offset)
                entry.TocData = toc_file.read(toc_header.toc_data_size)
                stream_file.seek(toc_header.stream_file_offset)
                audio.set_data(stream_file.read(toc_header.stream_size), notify_subscribers=False, set_modified=False)
                audio.resource_id = toc_header.file_id
                entry.set_content(audio)
                self.wwise_streams[entry.get_id()] = entry
            elif toc_header.type_id == WWISE_BANK:
                entry = WwiseBank()
                entry.toc_header = toc_header
                toc_data_offset = toc_header.toc_data_offset
                toc_data_size = toc_header.toc_data_size
                toc_file.seek(toc_data_offset)
                entry.toc_data_header = toc_file.read(16)
                #-------------------------------------
                bank = BankParser()
                bank.load(toc_file.read(toc_header.toc_data_size-16))
                entry.bank_header = "BKHD".encode('utf-8') + len(bank.chunks["BKHD"]).to_bytes(4, byteorder="little") + bank.chunks["BKHD"]
                
                hirc = HircReader()
                try:
                    hirc.load(bank.chunks['HIRC'])
                except KeyError:
                    continue
                entry.hierarchy = hirc    
                #-------------------------------------
                #Add all bank sources to the source list
                if "DIDX" in bank.chunks.keys():
                    bank_id = entry.toc_header.file_id
                    media_index = MediaIndex()
                    media_index.load(bank.chunks["DIDX"], bank.chunks["DATA"])
                    for e in hirc.entries.values():
                        for source in e.sources:
                            if source.plugin_id == VORBIS and source.stream_type == BANK and source.source_id not in self.audio_sources:
                                audio = AudioSource()
                                audio.stream_type = BANK
                                audio.short_id = source.source_id
                                audio.set_data(media_index.data[source.source_id], set_modified=False, notify_subscribers=False)
                                self.audio_sources[source.source_id] = audio
                
                entry.bank_misc_data = b''
                for chunk in bank.chunks.keys():
                    if chunk not in ["BKHD", "DATA", "DIDX", "HIRC"]:
                        entry.bank_misc_data = entry.bank_misc_data + chunk.encode('utf-8') + len(bank.chunks[chunk]).to_bytes(4, byteorder='little') + bank.chunks[chunk]
                        
                self.wwise_banks[entry.get_id()] = entry
            elif toc_header.type_id == WWISE_DEP: #wwise dep
                dep = WwiseDep()
                dep.toc_header = toc_header
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
                text_bank = TextBank()
                text_bank.toc_header = toc_header
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
        
        
        #checks for backwards compatibility with patches created in older version(s) of the tool
        #that didn't save data needed for computing resource_id hashes
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
        
        #Add all stream entries to the AudioSource list, using their short_id (requires mapping via the dep)
        for bank in self.wwise_banks.values():
            for entry in bank.hierarchy.entries.values():
                for source in entry.sources:
                    if source.plugin_id == VORBIS and source.stream_type in [STREAM, PREFETCH_STREAM] and source.source_id not in self.audio_sources:
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
                for source in entry.sources:
                    try:
                        if source.plugin_id == VORBIS and self.audio_sources[source.source_id] not in bank.get_content(): #may be missing streamed audio if the patch didn't change it
                            bank.add_content(self.audio_sources[source.source_id])
                    except:
                        continue
                for info in entry.track_info:
                    try:
                        if info.source_id != 0:
                            self.audio_sources[info.source_id].set_track_info(info, notify_subscribers=False, set_modified=False)
                    except:
                        continue
        
    def load_deps(self):
        archive_file = ""
        if GAME_FILE_LOCATION != "":
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
                dep = WwiseDep()
                dep.toc_header = toc_header
                toc_file.seek(toc_header.toc_data_offset)
                dep.from_memory_stream(toc_file)
                try:
                    self.wwise_banks[toc_header.file_id].dep = dep
                except KeyError:
                    pass
        return True
        
    def load_banks(self):
        archive_file = ""
        if GAME_FILE_LOCATION != "":
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
            entry = None
            if toc_header.type_id == WWISE_BANK:
                entry = WwiseBank()
                entry.toc_header = toc_header
                toc_data_offset = toc_header.toc_data_offset
                toc_data_size = toc_header.toc_data_size
                toc_file.seek(toc_data_offset)
                entry.toc_data_header = toc_file.read(16)
                #-------------------------------------
                bank = BankParser()
                bank.load(toc_file.read(toc_header.toc_data_size-16))
                entry.bank_header = "BKHD".encode('utf-8') + len(bank.chunks["BKHD"]).to_bytes(4, byteorder="little") + bank.chunks["BKHD"]
                
                hirc = HircReader()
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
                dep = WwiseDep()
                dep.toc_header = toc_header
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
        
class SoundHandler:
    
    def __init__(self):
        self.audio_process = None
        self.wave_object = None
        self.audio_id = -1
        self.audio = pyaudio.PyAudio()
        
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
        
    def play_audio(self, sound_id, sound_data, callback=None):
        self.kill_sound()
        self.callback = callback
        if self.audio_id == sound_id:
            self.audio_id = -1
            return
        filename = f"temp{sound_id}"
        if not os.path.isfile(f"{filename}.wav"):
            with open(f'{filename}.wem', 'wb') as f:
                f.write(sound_data)
            subprocess.run([VGMSTREAM, "-o", f"{filename}.wav", f"{filename}.wem"], stdout=subprocess.DEVNULL)
            os.remove(f"{filename}.wem")
            
        self.audio_id = sound_id
        self.wave_file = wave.open(f"{filename}.wav")
        self.audio_file = f"{filename}.wav"
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
        self.audio_file = f"{filename}.wav"
        
    def downmix_to_stereo(self, data, channels, channel_width, frame_count):
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
                
        if channels == 6:
            for index, frame in enumerate(arr):
                stereo_array[index][0] = int(0.374107*frame[1] + 0.529067*frame[0] + 0.458186*frame[3] + 0.264534*frame[4] + 0.374107*frame[5])
                stereo_array[index][1] = int(0.374107*frame[1] + 0.529067*frame[2] + 0.458186*frame[4] + 0.264534*frame[3] + 0.374107*frame[5])
        
        return stereo_array.tobytes()
     
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
        if output_file is None: return
        output_file.write(self.get_audio_by_id(file_id).get_data())
        
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

        with open(f"{save_path}.wem", 'wb') as f:
            f.write(self.get_audio_by_id(file_id).get_data())

        subprocess.run(
            [VGMSTREAM, "-o", f"{save_path}.wav", f"{save_path}.wem"], 
            stdout=subprocess.DEVNULL
        )

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
        
    def dump_multiple_as_wav(self, file_ids: list[str], muted: bool = False,
                             with_seq: bool = False):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        
        if not os.path.exists(folder):
            logger.warning("Invalid folder selected, aborting dump")
            return

        progress_window = ProgressWindow(title="Dumping Files", 
                                         max_progress=len(file_ids))
        progress_window.show()


        for i, file_id in enumerate(file_ids, start=0):
            audio: int | None = self.get_audio_by_id(int(file_id))
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
                subprocess.run(
                    [VGMSTREAM, "-o", f"{save_path}.wav", f"{save_path}.wem"],
                    stdout=subprocess.DEVNULL,
                )
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
                    subprocess.run([VGMSTREAM, "-o", f"{save_path}.wav", f"{save_path}.wem"], stdout=subprocess.DEVNULL)
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
            log.logger.warning(f"File name must begin with a number: {n}")
        
    def save_archive_file(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        if os.path.exists(folder):
            self.file_reader.rebuild_headers()
            self.file_reader.to_file(folder)
        else:
            print("Invalid folder selected, aborting save")
            
    def get_audio_by_id(self, file_id):
        try:
            return self.file_reader.audio_sources[file_id] #short_id
        except KeyError:
            pass
        for source in self.file_reader.audio_sources.values(): #resource_id
            if source.resource_id == file_id:
                return source
                
    def get_event_by_id(self, event_id):
        try:
            return self.file_reader.music_track_events[event_id]
        except:
            pass
            
    def get_string_by_id(self, string_id):
        try:
            return self.file_reader.string_entries[language][string_id]
        except:
            pass
        
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
        
    def load_archive_file(self, initialdir: str | None = ''):
        archive_file = askopenfilename(initialdir=initialdir, 
                                       title="Select archive")
        if os.path.splitext(archive_file)[1] in (".stream", ".gpu_resources"):
            archive_file = os.path.splitext(archive_file)[0]
        if os.path.exists(archive_file):
            self.file_reader.from_file(archive_file)
        else:
            print("Invalid file selected, aborting load")   
            return False
        return True
            
            
    def load_patch(self): #TO-DO: only import if DIFFERENT from original audio; makes it possible to import different mods that change the same soundbank
        patch_file_reader = FileReader()
        patch_file = filedialog.askopenfilename(title="Choose patch file to import")
        if os.path.splitext(patch_file)[1] in (".stream", ".gpu_resources"):
            patch_file = os.path.splitext(patch_file)[0]
        if os.path.exists(patch_file):
            patch_file_reader.from_file(patch_file)
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
            old_music_segment = self.file_reader.music_segments[key]
            if (
                not old_music_segment.modified
                or music_segment.entry_marker[1] != old_music_segment.entry_marker_old
                or music_segment.exit_marker[1] != old_music_segment.exit_marker_old
                or music_segment.duration != old_music_segment.duration_old
            ):
                old_music_segment.set_data(duration=music_segment.duration, entry_marker=music_segment.entry_marker[1], exit_marker=music_segment.exit_marker[1])

        for text_data in patch_file_reader.text_banks.values():
            for string_id in text_data.string_ids:
                new_text_data = patch_file_reader.string_entries[language][string_id]
                try:
                    old_text_data = self.file_reader.string_entries[language][string_id]
                except:
                    continue
                old_text_data.set_text(new_text_data.get_text())
        
        progress_window.destroy()
        return True

    def write_patch(self):
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

    def load_wems(self, wems: Union[tuple[str, ...], Literal[""], None] = None): 
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
            audio: str | None = self.get_audio_by_id(file_id)
            if audio == None:
                continue
            with open(wem, 'rb') as f:
                audio.set_data(f.read())
            progress_window.step()
        progress_window.destroy()
      

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
        self.text_box = Text(self.frame, width=50, font=('Arial', 8), wrap=WORD)
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
        
class AudioSourceWindow:
    
    def __init__(self, parent, play, update_modified):
        self.frame = Frame(parent)
        self.update_modified = update_modified
        self.fake_image = tkinter.PhotoImage(width=1, height=1)
        self.play = play
        self.title_label = Label(self.frame, font=('Segoe UI', 14))
        self.revert_button = ttk.Button(self.frame, text='\u21b6', image=self.fake_image, compound='c', width=2, command=self.revert)
        self.play_button = ttk.Button(self.frame, text= '\u23f5', image=self.fake_image, compound='c', width=2)
        self.play_at_text_var = tkinter.StringVar(self.frame)
        self.duration_text_var = tkinter.StringVar(self.frame)
        self.start_offset_text_var = tkinter.StringVar(self.frame)
        self.end_offset_text_var = tkinter.StringVar(self.frame)
        
        self.play_at_label = Label(self.frame,
                                   text="Play At (ms)",
                                   font=('Segoe UI', 12))
        self.play_at_text = Entry(self.frame, textvariable=self.play_at_text_var, font=('Segoe UI', 12), width=50)
        
        
        self.duration_label = Label(self.frame,
                                    text="Duration (ms)",
                                    font=('Segoe UI', 12))
        self.duration_text = Entry(self.frame, textvariable=self.duration_text_var, font=('Segoe UI', 12), width=50)
        
        
        self.start_offset_label = Label(self.frame,
                                        text="Start Trim (ms)",
                                        font=('Segoe UI', 12))
        self.start_offset_text = Entry(self.frame, textvariable=self.start_offset_text_var, font=('Segoe UI', 12), width=50)
        
        
        self.end_offset_label = Label(self.frame,
                                      text="End Trim (ms)",
                                      font=('Segoe UI', 12))
        self.end_offset_text = Entry(self.frame, textvariable=self.end_offset_text_var, font=('Segoe UI', 12), width=50)

        self.apply_button = ttk.Button(self.frame, text="Apply", command=self.apply_changes)
        
        self.title_label.pack()
       
        
    def set_audio(self, audio):
        self.audio = audio
        self.track_info = audio.get_track_info()
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
        self.play_button.configure(command=partial(press_button, self.play_button, audio.get_short_id(), partial(reset_button_icon, self.play_button)))
        if self.track_info is not None:
            self.play_at_text.delete(0, 'end')
            self.duration_text.delete(0, 'end')
            self.start_offset_text.delete(0, 'end')
            self.end_offset_text.delete(0, 'end')
            self.play_at_text.insert(END, f"{self.track_info.play_at}")
            self.duration_text.insert(END, f"{self.track_info.source_duration}")
            self.start_offset_text.insert(END, f"{self.track_info.begin_trim_offset}")
            self.end_offset_text.insert(END, f"{self.track_info.end_trim_offset}")
            self.play_at_label.pack()
            self.play_at_text.pack()
            self.duration_label.pack()
            self.duration_text.pack()
            self.start_offset_label.pack()
            self.start_offset_text.pack()
            self.end_offset_label.pack()
            self.end_offset_text.pack()
        self.revert_button.pack(side="left")
        self.play_button.pack(side="left")
        if self.track_info is not None:
            self.apply_button.pack(side="left")
        else:
            self.play_at_label.forget()
            self.play_at_text.forget()
            self.duration_label.forget()
            self.duration_text.forget()
            self.start_offset_label.forget()
            self.start_offset_text.forget()
            self.end_offset_label.forget()
            self.end_offset_text.forget()
            self.apply_button.forget()
            
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
        
    def apply_changes(self):
        self.track_info.set_data(play_at=float(self.play_at_text_var.get()), begin_trim_offset=float(self.start_offset_text_var.get()), end_trim_offset=float(self.end_offset_text_var.get()), source_duration=float(self.duration_text_var.get()))
        self.audio.modified = True
        self.update_modified()
        
class MusicSegmentWindow:
    def __init__(self, parent, update_modified):
        self.frame = Frame(parent)
        self.update_modified = update_modified
        
        self.title_label = Label(self.frame, font=('Segoe UI', 14))

        self.duration_text_var = tkinter.StringVar(self.frame)
        self.fade_in_text_var = tkinter.StringVar(self.frame)
        self.fade_out_text_var = tkinter.StringVar(self.frame)
        
        self.duration_label = Label(self.frame,
                                    text="Duration (ms)",
                                    font=('Segoe UI', 12))
        self.duration_text = Entry(self.frame, textvariable=self.duration_text_var, font=('Segoe UI', 12), width=50)
        
        self.fade_in_label = Label(self.frame,
                                   text="End fade-in (ms)",
                                   font=('Segoe UI', 12))
        self.fade_in_text = Entry(self.frame, textvariable=self.fade_in_text_var, font=('Segoe UI', 12), width=50)
        
        self.fade_out_label = Label(self.frame,
                                    text="Start fade-out (ms)",
                                    font=('Segoe UI', 12))
        self.fade_out_text = Entry(self.frame, textvariable=self.fade_out_text_var, font=('Segoe UI', 12), width=50)
        self.revert_button = ttk.Button(self.frame, text="\u21b6", command=self.revert)
        self.apply_button = ttk.Button(self.frame, text="Apply", command=self.apply_changes)
        
        self.title_label.pack()
        
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
        
        self.play_at_label = Label(self.frame,
                                   text="Play At (ms)",
                                   font=('Segoe UI', 12))
        self.play_at_text = Entry(self.frame, textvariable=self.play_at_text_var, font=('Segoe UI', 12), width=50)
        
        self.duration_label = Label(self.frame,
                                    text="Duration (ms)",
                                    font=('Segoe UI', 12))
        self.duration_text = Entry(self.frame, textvariable=self.duration_text_var, font=('Segoe UI', 12), width=50)
        
        self.start_offset_label = Label(self.frame,
                                        text="Start Trim (ms)",
                                        font=('Segoe UI', 12))
        self.start_offset_text = Entry(self.frame, textvariable=self.start_offset_text_var, font=('Segoe UI', 12), width=50)
        
        self.end_offset_label = Label(self.frame,
                                      text="End Trim (ms)",
                                      font=('Segoe UI', 12))
        self.end_offset_text = Entry(self.frame, textvariable=self.end_offset_text_var, font=('Segoe UI', 12), width=50)
        self.revert_button = ttk.Button(self.frame, text="\u21b6", command=self.revert)
        self.apply_button = ttk.Button(self.frame, text="Apply", command=self.apply_changes)
        
        self.title_label.pack()
        
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

class MainWindow:

    dark_mode_bg = "#333333"
    dark_mode_fg = "#ffffff"
    dark_mode_modified_bg = "#ffffff"
    dark_mode_modified_fg = "#333333"
    light_mode_bg = "#ffffff"
    light_mode_fg = "#000000"
    light_mode_modified_bg = "#7CFC00"
    light_mode_modified_fg = "#000000"

    def __init__(self, app_state: cfg.Config, file_handler, sound_handler):
        self.app_state = app_state

        self.file_handler = file_handler
        self.sound_handler = sound_handler
        
        self.root = Tk()
        try:
            self.root.tk.call("source", "azure.tcl")
        except Exception as e:
            logger.critical("Error occurred when loading themes:")
            logger.critical(e)
            logger.critical("Ensure azure.tcl and the themes folder are in the same folder as the executable")
        
        self.fake_image = tkinter.PhotoImage(width=1, height=1)
        
        self.top_bar = Canvas(self.root, width=WINDOW_WIDTH, height=40)
        self.search_text_var = tkinter.StringVar(self.root)
        self.search_bar = Entry(self.top_bar, textvariable=self.search_text_var, font=('Segoe UI', 14))
        self.top_bar.pack(side="top")
        
        self.up_button = ttk.Button(self.top_bar, text='^', 
                                    width=1, command=self.search_up)
        self.down_button = ttk.Button(self.top_bar, text='v',
                                      width=1, command=self.search_down)
        
        self.search_label = ttk.Label(self.top_bar,
                                      width=10,
                                      font=('Segoe UI', 14),
                                      justify="center")
        self.default_bg = "#333333"
        self.default_fg = "#ffffff"
        
        self.top_bar.create_text(WINDOW_WIDTH-430, 4, text="\u2315", 
                                 fill='gray', font=('Arial', 20), anchor='nw')
        self.top_bar.create_window(WINDOW_WIDTH-330, 8, window=self.search_bar, 
                                   anchor='nw')
        self.top_bar.create_window(WINDOW_WIDTH-370, 5, window=self.up_button, 
                                   anchor='nw')
        self.top_bar.create_window(WINDOW_WIDTH-405, 5, window=self.down_button, 
                                   anchor='nw')
        self.top_bar.create_window(WINDOW_WIDTH-110, 5, window=self.search_label, 
                                   anchor='nw')

        self.scroll_bar = ttk.Scrollbar(self.root, orient=VERTICAL)
        
        self.top_bar.pack(side="top")
        
        self.search_results = []
        self.search_result_index = 0

        self.init_workspace()
        
        self.treeview = ttk.Treeview(self.root, columns=("type",), height=WINDOW_HEIGHT-100)
        self.treeview.pack(side="left", padx=8, pady=8)
        self.scroll_bar.pack(side="left", pady=8, fill="y")
        self.treeview.heading("#0", text="File")
        self.treeview.column("#0", width=250)
        self.treeview.column("type", width=100)
        self.treeview.heading("type", text="Type")
        self.treeview.configure(yscrollcommand=self.scroll_bar.set)
        self.treeview.bind("<<TreeviewSelect>>", self.show_info_window)
        self.treeview.bind("<Double-Button-1>", self.treeview_on_double_click)
        self.treeview.bind("<Return>", self.treeview_on_double_click)
        self.scroll_bar['command'] = self.treeview.yview

        self.entry_info_panel = Frame(self.root, width=int(WINDOW_WIDTH/3))
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

        self.load_archive_menu = Menu(self.menu, tearoff=0)
        self.load_archive_menu.add_command(
            label="From HD2 Data Folder",
            command=lambda: self.load_archive(self.app_state.game_data_path)
        )
        self.load_archive_menu.add_command(
            label="From File Explorer",
            command=self.load_archive
        )
        self.file_menu.add_cascade(
            menu=self.load_archive_menu, 
            label="Load Archive"
        )
        self.file_menu.add_command(label="Save Archive", command=self.save_archive)
        self.file_menu.add_command(label="Write Patch", command=self.write_patch)
        self.file_menu.add_command(label="Import Patch File", command=self.load_patch)
        self.file_menu.add_command(label="Import .wems", command=self.load_wems)
        self.file_menu.add_command(label="Refresh Workspace",
                                   command=self.render_workspace)
        self.file_menu.add_command(label="Add a Folder to Workspace",
                                   command=self.add_new_workspace)
        
        self.edit_menu = Menu(self.menu, tearoff=0)
        self.edit_menu.add_command(label="Revert All Changes", command=self.revert_all)
        
        self.dump_menu = Menu(self.menu, tearoff=0)
        self.dump_menu.add_command(label="Dump all as .wav", command=self.dump_all_as_wav)
        self.dump_menu.add_command(label="Dump all as .wem", command=self.dump_all_as_wem)
        
        self.menu.add_cascade(label="File", menu=self.file_menu)
        self.menu.add_cascade(label="Edit", menu=self.edit_menu)
        self.menu.add_cascade(label="Dump", menu=self.dump_menu)
        self.menu.add_cascade(label="View", menu=self.view_menu)
        self.menu.add_cascade(label="Options", menu=self.options_menu)
        self.root.config(menu=self.menu)

        self.treeview.bind("<Button-3>", self.treeview_on_right_click)
        self.workspace.bind("<Button-3>", self.workspace_on_right_click)
        self.search_bar.bind("<Return>", self.search_bar_on_enter_key)

        self.root.resizable(False, False)
        self.root.mainloop()
        
    def search_bar_on_enter_key(self, event):
        self.search()
        
    def set_theme(self):
        theme = self.selected_theme.get()
        try:
            if theme == "dark_mode":
                self.root.tk.call("set_theme", "dark")
            elif theme == "light_mode":
                self.root.tk.call("set_theme", "light")
        except Exception as e:
            logger.error(f"Error occurred when loading themes: {e}. Ensure azure.tcl and the themes folder are in the same folder as the executable")
        self.app_state.theme = theme
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

    def render_workspace(self):
        """
        TO-DO: This should be fine grained diffing instead of tearing the entire
        thing down despite Tkinter already perform some type of rendering and
        display optimization behind the scene.
        """
        self.workspace_inodes.clear()

        for p in self.app_state.get_workspace_paths():
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

    def add_new_workspace(self):
        if self.app_state.add_new_workspace() == 1:
            return
        self.render_workspace()

    def remove_workspace(self, workspace):
        self.app_state.workspace_paths.remove(workspace)
        self.render_workspace()

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
                    command=lambda: self.remove_workspace(values[0]),
                )
                self.workspace_popup_menu.tk_popup(
                    event.x_root, event.y_root
                )
                self.workspace_popup_menu.grab_release()
                return
            if tags[0] == "dir":
                return
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
            command=lambda: self.load_wems(wems=wems)
        )
        self.workspace_popup_menu.tk_popup(event.x_root, event.y_root)
        self.workspace_popup_menu.grab_release()

    def init_workspace(self):
        self.workspace = ttk.Treeview(self.root, height=WINDOW_HEIGHT - 100)
        self.workspace.heading("#0", text="Workspace Folders")
        self.workspace.column("#0", width=256+16)
        self.workspace.pack(side="left", padx=8, pady=8)
        self.workspace_inodes: list[fileutil.INode] = []
        self.workspace_popup_menu = Menu(self.workspace, tearoff=0)
        self.workspace_scroll_bar = ttk.Scrollbar(self.root, orient=VERTICAL)
        self.workspace_scroll_bar['command'] = self.workspace.yview
        self.workspace_scroll_bar.pack(side="left", pady=8, fill="y")
        self.workspace.configure(yscrollcommand=self.workspace_scroll_bar.set)
        self.render_workspace() 

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

    def show_info_window(self, event):
        if len(self.treeview.selection()) != 1:
            return
        selection_type = self.treeview.item(self.treeview.selection(), option="values")[0]
        selection_id = int(self.treeview.item(self.treeview.selection(), option="tags")[0])
        for child in self.entry_info_panel.winfo_children():
            child.forget()
        if selection_type == "String":
            self.string_info_panel.set_string_entry(self.file_handler.get_string_by_id(selection_id))
            self.string_info_panel.frame.pack()
        elif selection_type == "Audio Source":
            self.audio_info_panel.set_audio(self.file_handler.get_audio_by_id(selection_id))
            self.audio_info_panel.frame.pack()
        elif selection_type == "Event":
            self.event_info_panel.set_track_info(self.file_handler.get_event_by_id(selection_id))
            self.event_info_panel.frame.pack()
        elif selection_type == "Music Segment":
            self.segment_info_panel.set_segment_info(self.file_handler.get_music_segment_by_id(selection_id))
            self.segment_info_panel.frame.pack()
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
            self.file_handler.dump_as_wem(self.right_click_id)
        else:
            self.file_handler.dump_multiple_as_wem([int(self.treeview.item(i, option="tags")[0]) for i in self.treeview.selection()])
        
    def dump_as_wav(self, muted: bool = False, with_seq: int = False):
        if len(self.treeview.selection()) == 1:
            self.file_handler.dump_as_wav(self.right_click_id, muted=muted)
            return
        self.file_handler.dump_multiple_as_wav(
            [int(self.treeview.item(i, option="tags")[0]) for i in self.treeview.selection()],
            muted=muted,
            with_seq=with_seq
        )
        
    def create_treeview_entry(self, entry, parentItem=""):
        if entry is None: return
        tree_entry = self.treeview.insert(parentItem, END, tag=entry.get_id())
        if isinstance(entry, WwiseBank):
            name = entry.dep.data.split('/')[-1]
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
                if isinstance(hierarchy_entry, MusicSegment):
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
                elif isinstance(hierarchy_entry, Sound):
                    if hierarchy_entry.sources[0].plugin_id == VORBIS:
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
        if self.treeview.item(item, option="values")[0] == "String":
            string_entry = self.file_handler.get_string_by_id(int(self.treeview.item(item, option="tags")[0]))
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

    def load_archive(self, initialdir: str | None = ''):
        self.sound_handler.kill_sound()
        if self.file_handler.load_archive_file(initialdir=initialdir):
            self.clear_search()
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
            if self.selected_view.get() == "SourceView":
                self.create_source_view()
            else:
                self.create_hierarchy_view()
            for child in self.entry_info_panel.winfo_children():
                child.forget()
        
    def save_archive(self):
        self.sound_handler.kill_sound()
        self.file_handler.save_archive_file()
            
        
    def clear_treeview_background(self, item):
        bg_color = self.get_colors()[0]
        self.treeview.tag_configure(self.treeview.item(item)['tags'][0],
                                    background=bg_color)
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
        for audio in self.file_handler.get_audio().values():
            is_modified = audio.modified or audio.get_track_info() is not None \
                    and audio.get_track_info().modified
            bg, fg = self.get_colors(modified=is_modified)
            self.treeview.tag_configure(audio.get_id(),
                                        background=bg,
                                        foreground=fg)
            if not is_modified:
                continue

            items = self.treeview.tag_has(audio.get_id())
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
                self.treeview.tag_configure(string.get_id(), 
                                            background=bg,
                                            foreground=fg)
                if not string.modified:
                    continue
                item = self.treeview.tag_has(string.get_id())
                parent = self.treeview.parent(item)
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
        
    def dump_all_as_wem(self):
        self.sound_handler.kill_sound()
        self.file_handler.dump_all_as_wem()
        
    def dump_all_as_wav(self):
        self.sound_handler.kill_sound()
        self.file_handler.dump_all_as_wav()
        
    def play_audio(self, file_id: int, callback=None):
        audio = self.file_handler.get_audio_by_id(file_id)
        self.sound_handler.play_audio(audio.get_short_id(), audio.get_data(), callback)
        
    def revert_audio(self, file_id):
        self.file_handler.revert_audio(file_id)
        
    def revert_all(self):
        self.sound_handler.kill_sound()
        self.file_handler.revert_all()
        self.check_modified()
        
    def write_patch(self):
        self.sound_handler.kill_sound()
        self.file_handler.write_patch()
        
    def load_patch(self):
        self.sound_handler.kill_sound()
        if self.file_handler.load_patch():
            self.check_modified()

if __name__ == "__main__":
    app_state: cfg.Config | None = cfg.load_config()
    if app_state == None:
        exit(1)
    GAME_FILE_LOCATION = app_state.game_data_path

    system = platform.system()
    if system == "Windows":
        VGMSTREAM = "vgmstream-win64/vgmstream-cli.exe"
        FFMPEG = "ffmpeg.exe"
    elif system == "Linux":
        VGMSTREAM = "vgmstream-linux/vgmstream-cli"
        FFMPEG = "ffmpeg"
    elif system == "Darwin":
        VGMSTREAM = "vgmstream-macos/vgmstream-cli"
        FFMPEG = "ffmpeg"
        
    if not os.path.exists(VGMSTREAM):
        logger.error(f"Cannot find vgmstream distribution! Ensure the {os.path.dirname(VGMSTREAM)} folder is in the same folder as the executable")
        
    language = language_lookup("English (US)")
    sound_handler = SoundHandler()
    file_handler = FileHandler()
    window = MainWindow(app_state, file_handler, sound_handler)
    
    app_state.save_config()

