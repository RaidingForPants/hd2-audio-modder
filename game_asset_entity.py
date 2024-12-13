import struct
from typing import Literal

from const_global import BANK, MUSIC_TRACK, PREFETCH_STREAM, SOUND, VORBIS
from ui_window_component import ProgressWindow
from xstruct import MemoryStream


class Subscriber:
    def __init__(self):
        pass
        
    def update(self, content):
        pass
        
    def raise_modified(self):
        pass
        
    def lower_modified(self):
        pass


class TocHeader:

    def __init__(self):
        pass
        
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

    def __init__(self, toc_header: TocHeader):
        self.data = ""
        self.toc_header = toc_header
        
    def from_memory_stream(self, stream: MemoryStream):
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
                

class TextBank:
    
    def __init__(self, toc_header: TocHeader):
        self.toc_header = toc_header
        self.data = b''
        self.string_ids = []
        self.language = 0
        self.modified = False
        
    def set_data(self, data):
        self.string_ids.clear()
        num_entries = int.from_bytes(data[8:12], byteorder='little')
        id_section_start = 16
        offset_section_start = id_section_start + 4 * num_entries
        ids = data[id_section_start:offset_section_start]
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
            text_bytes = entries[i].text.encode('utf-8') + b'\x00'
            stream.write(text_bytes)
            offset += len(text_bytes)
            stream.seek(initial_position)
        self.data = stream.data
        self.toc_header.toc_data_size = len(self.data)
        
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


class WwiseBank(Subscriber):

    class HircReader:
        
        def __init__(self, soundbank = None):
            self.entries = {}
            self.soundbank = soundbank
            
        def load(self, hierarchy_data):
            self.entries.clear()
            reader = MemoryStream()
            reader.write(hierarchy_data)
            reader.seek(0)
            num_items = reader.uint32_read()
            for _ in range(num_items):
                entry = HircEntryFactory.from_memory_stream(reader)
                entry.soundbank = self.soundbank
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

    
    def __init__(self, toc_header: TocHeader):
        self.data = b""
        self.bank_header = b""
        self.toc_data_header: bytearray = bytearray()
        self.bank_misc_data = b""
        self.modified = False
        self.toc_header = toc_header
        self.dep: WwiseDep | None = None
        self.modified_count = 0
        self.hierarchy: WwiseBank.HircReader | None = None
        self.content = []
        
    def add_content(self, content):
        content.subscribers.add(self)
        if content.track_info is not None:
            content.track_info.soundbanks.add(self)
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
            
        try:
            content.track_info.soundbanks.remove(self)
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
        if self.dep != None:
            return self.dep.data
        return "Unknown Soundbank Name"

    def get_id(self):
        return self.toc_header.file_id
            
    def get_type_id(self):
        return self.toc_header.type_id
            
    def get_data(self):
        return self.data
            
    def generate(self, audio_sources, eventTrackInfo):
        data = bytearray()
        data += self.bank_header
        
        offset = 0
        
        #regenerate soundbank from the hierarchy information
        max_progress = 0

        if self.hierarchy != None:
            for entry in self.hierarchy.entries.values():
                if entry.hierarchy_type == SOUND:
                    max_progress += 1
                elif entry.hierarchy_type == MUSIC_TRACK:
                    max_progress += len(entry.sources)
                    
        
        bank_generation_progress_window = ProgressWindow("Generating Soundbanks", max_progress)
        bank_generation_progress_window.show()
        bank_generation_progress_window.set_text(f"Generating {self.get_name()}")
        
        didx_array = []
        data_array = []
        
        if self.hierarchy != None:
            for entry in self.hierarchy.entries.values():
                for index, info in enumerate(entry.track_info):
                    if info.event_id != 0:
                        entry.track_info[index] = eventTrackInfo[info.event_id]
                for source in entry.sources:
                    bank_generation_progress_window.step()
                    if source.plugin_id == VORBIS:
                        if source.source_id not in audio_sources:
                            continue

                        audio = audio_sources[source.source_id]
                        try:
                            count = 0
                            for info in entry.track_info:
                                if info.source_id == source.source_id:
                                    break
                                count += 1
                            if audio.get_track_info() is not None: #is this needed?
                                entry.track_info[count] = audio.get_track_info()
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
            
        if self.hierarchy == None:
            return

        hierarchy_section = self.hierarchy.get_data()
        data += "HIRC".encode('utf-8') 
        data += len(hierarchy_section).to_bytes(4, byteorder="little")
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

    def __init__(self, toc_header: TocHeader):
        self.content = None
        self.modified = False
        self.toc_header = toc_header
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


class HircEntry:
    
    def __init__(self):
        self.size = self.hierarchy_type = self.hierarchy_id = 0
        self.misc: Literal[b""] | bytearray = b""
        self.sources = []
        self.track_info = []
        self.soundbank = None
    
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        entry = HircEntry()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
        entry.hierarchy_id = stream.uint32_read()
        entry.misc = stream.read(entry.size - 4)
        return entry
        
    def get_id(self):
        return self.hierarchy_id
        
    def raise_modified(self):
        self.soundbank.raise_modified()
        
    def lower_modified(self):
        self.soundbank.lower_modified()
        
    def get_data(self):
        return self.hierarchy_type.to_bytes(1, byteorder="little") + \
               self.size.to_bytes(4, byteorder="little") + \
               self.hierarchy_id.to_bytes(4, byteorder="little") + \
               self.misc
        

class HircEntryFactory:
    
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
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
        self.soundbanks = set()
        
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
            self.raise_modified()
        if play_at is not None: self.play_at = play_at
        if begin_trim_offset is not None: self.begin_trim_offset = begin_trim_offset
        if end_trim_offset is not None: self.end_trim_offset = end_trim_offset
        if source_duration is not None: self.source_duration = source_duration
        self.modified = True
        
    def revert_modifications(self):
        if self.modified:
            self.lower_modified()
            self.play_at = self.play_at_old
            self.begin_trim_offset = self.begin_trim_offset_old
            self.end_trim_offset = self.end_trim_offset_old
            self.source_duration = self.source_duration_old
            self.modified = False
            
    def raise_modified(self):
        for bank in self.soundbanks:
            bank.raise_modified()
        
    def lower_modified(self):
        for bank in self.soundbanks:
            bank.lower_modified()
        
    def get_data(self):
        return struct.pack("<IIIdddd", self.track_id, self.source_id, self.event_id, self.play_at, self.begin_trim_offset, self.end_trim_offset, self.source_duration)
            

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
        if self.track_info is not None:
            self.track_info.revert_modifications()
        if self.modified:
            self.modified = False
            if self.data_OLD != b"":
                self.data = self.data_OLD
                self.data_OLD = b""
            self.size = len(self.data)
            if notify_subscribers:
                for item in self.subscribers:
                    item.lower_modified()
                    item.update(self)


class MusicRandomSequence(HircEntry):
    
    def __init__(self):
        super().__init__()
    
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
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
    def from_memory_stream(cls, stream: MemoryStream):
        entry = MusicSegment()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
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
            self.raise_modified()
        if duration is not None: self.duration = duration
        if entry_marker is not None: self.entry_marker[1] = entry_marker
        if exit_marker is not None: self.exit_marker[1] = exit_marker
        self.modified = True
        
    def revert_modifications(self):
        if self.modified:
            self.lower_modified()
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
        

class MusicTrack(HircEntry):
    
    def __init__(self):
        super().__init__()
        self.bit_flags = 0
        
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
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
    def from_memory_stream(cls, stream: MemoryStream):
        entry = Sound()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
        entry.hierarchy_id = stream.uint32_read()
        entry.sources.append(BankSourceStruct.from_bytes(stream.read(14)))
        entry.misc = stream.read(entry.size - 18)
        return entry

    def get_data(self):
        return struct.pack(f"<BII14s{len(self.misc)}s", 
                           self.hierarchy_type, 
                           self.size, 
                           self.hierarchy_id, 
                           self.sources[0].get_data(), 
                           self.misc)
        

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
