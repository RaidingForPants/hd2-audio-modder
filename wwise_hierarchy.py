import util

class HircEntry:
    
    def __init__(self):
        self.size = self.hierarchy_type = self.hierarchy_id = self.misc = 0
        self.sources = []
        self.track_info = []
        self.soundbank = None
        self.modified = False
        self.data_old = None
    
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        entry = HircEntry()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
        entry.hierarchy_id = stream.uint32_read()
        entry.misc = stream.read(entry.size - 4)
        return entry
        
    @classmethod
    def from_bytes(cls, data: bytes | bytearray):
        stream = MemoryStream()
        stream.write(data)
        stream.seek(0)
        return cls.from_memory_stream(stream)
        
    def set_data(self, new_entry: HircEntry):
        if not self.modified:
            self.data_old = self.get_data()
        self.misc = new_entry.misc
        self.size = len(new_entry.misc) + 4
        self.raise_modified()
        
    def revert_modifications(self):
        if self.modified:
            self.set_data(self.from_bytes(self.data_old))
            self.data_old = None
            self.lower_modified()
        
    def import_entry(self, new_entry: HircEntry):
        if (
            (self.modified and new_entry.get_data() != self.data_old)
            or
            (not self.modified and new_entry.get_data() != self.get_data())
        ):
            self.set_data(new_entry)
        
    def get_id(self):
        return self.hierarchy_id
        
    def raise_modified(self):
        if not self.modified:
            self.modified = True
            self.soundbank.raise_modified()
        
    def lower_modified(self):
        if self.modified:
            self.modified = False
            self.soundbank.lower_modified()
        
    def get_data(self):
        return self.hierarchy_type.to_bytes(1, byteorder="little") + self.size.to_bytes(4, byteorder="little") + self.hierarchy_id.to_bytes(4, byteorder="little") + self.misc
        
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
        
    def set_data(self, new_entry: MusicRandomSequence):
        pass
        
class RandomSequenceContainer(HircEntry):
    def __init__(self):
        super().__init__()
        self.unused_sections = []
        self.contents = []
        
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        entry = RandomSequenceContainer()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
        start_position = stream.tell()
        entry.hierarchy_id = stream.uint32_read()

        # ---------------------------------------
        section_start = stream.tell()
        stream.advance(1)
        n = stream.uint8_read() #num fx
        if n == 0:
            stream.advance(12)
        else:
            stream.advance(7*n + 13)
        stream.advance(5*stream.uint8_read()) #number of props
        stream.advance(9*stream.uint8_read()) #number of props (again)
        if stream.uint8_read() & 0b0000_0010: #positioning bit vector
            if stream.uint8_read() & 0b0100_0000: # relative pathing bit vector
                stream.advance(5)
                stream.advance(16*stream.uint32_read())
                stream.advance(20*stream.uint32_read())
        if stream.uint8_read() & 0b0000_1000: #I forget what this is for
            stream.advance(26)
        else:
           stream.advance(10)
        stream.advance(3*stream.uint8_read()) #num state props
        for _ in range(stream.uint8_read()): #num state groups
            stream.advance(5)
            stream.advance(8*stream.uint8_read())
        for _ in range(stream.uint16_read()):  # num RTPC
            stream.advance(12)
            stream.advance(stream.uint16_read()*12)
        section_end = stream.tell()
        # ---------------------------------------

        stream.seek(section_start)
        entry.unused_sections.append(stream.read(section_end-section_start+24))

        for _ in range(stream.uint32_read()): #number of children (tracks)
            entry.contents.append(stream.uint32_read())

        entry.unused_sections.append(stream.read(entry.size - (stream.tell()-start_position)))
        return entry
        
    def set_data(self, new_entry: RandomSequenceContainer):
        self.unused_sections = new_entry.unused_sections
        self.contents = new_entry.contents
        self.size = new_entry.size
        
    def get_data(self):
        return (
            b"".join([
                struct.pack("<BII", self.hierarchy_type, self.size, self.hierarchy_id),
                self.unused_sections[0],
                len(self.contents).to_bytes(4, byteorder="little"),
                b"".join([x.to_bytes(4, byteorder="little") for x in self.contents]),
                self.unused_sections[1]
            ])
        )
    
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
        
    def set_data(self, new_entry: MusicSegment):
        if not self.modified:
            self.data_old = self.get_data()
        self.raise_modified()
        self.duration = new_entry.duration
        self.unused_sections = new_entry.unused_sections
        self.tracks = new_entry.tracks
        self.markers = new_entry.markers
        self.size = new_entry.size
        
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
        
            
class BankSourceStruct:

    def __init__(self):
        self.plugin_id = 0
        self.stream_type = self.source_id = self.mem_size = self.bit_flags = 0
        
    @classmethod
    def from_bytes(cls, bytes: bytes | bytearray):
        b = BankSourceStruct()
        b.plugin_id, b.stream_type, b.source_id, b.mem_size, b.bit_flags = struct.unpack("<IBIIB", bytes)
        return b
        
    def get_data(self):
        return struct.pack("<IBIIB", self.plugin_id, self.stream_type, self.source_id, self.mem_size, self.bit_flags)
        
class TrackInfoStruct:
    
    def __init__(self):
        self.track_id = self.source_id = self.event_id = self.play_at = self.begin_trim_offset = self.end_trim_offset = self.source_duration = 0

    @classmethod
    def from_bytes(cls, bytes: bytes | bytearray):
        t = TrackInfoStruct()
        t.track_id, t.source_id, t.event_id, t.play_at, t.begin_trim_offset, t.end_trim_offset, t.source_duration = struct.unpack("<IIIdddd", bytes)
        return t
        
    def get_id(self):
        if self.source_id != 0:
            return self.source_id
        else:
            return self.event_id

    def get_data(self):
        return struct.pack("<IIIdddd", self.track_id, self.source_id, self.event_id, self.play_at, self.begin_trim_offset, self.end_trim_offset, self.source_duration)
            
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
        
    def set_data(self, new_entry: MusicTrack):
        if not self.modified:
            self.data_old = self.get_data()
        self.size = new_entry.size
        self.bit_flags = new_entry.bit_flags
        self.sources = new_entry.sources
        self.track_info = new_entry.track_info
        self.misc = new_entry.misc
        self.raise_modified()

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
        
    def set_data(self, new_entry: Sound):
        if not self.modified:
            self.data_old = self.get_data()
        self.raise_modified()
        self.sources = new_entry.sources
        self.misc = new_entry.misc
        self.size = new_entry.size

    def get_data(self):
        return struct.pack(f"<BII14s{len(self.misc)}s", self.hierarchy_type, self.size, self.hierarchy_id, self.sources[0].get_data(), self.misc)
        
        
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
        elif hierarchy_type == 0x05: #random sequence container
            return RandomSequenceContainer.from_memory_stream(stream)
        else:
            return HircEntry.from_memory_stream(stream)
            
class WwiseHierarchy:
    
    def __init__(self, soundbank: WwiseBank = None):
        self.entries = {}
        self.type_lists = {}
        self.soundbank = soundbank
        self.added_entries = {}
        self.removed_entries = {}
        
    def load(self, hierarchy_data: bytes | bytearray):
        self.entries.clear()
        reader = MemoryStream()
        reader.write(hierarchy_data)
        reader.seek(0)
        num_items = reader.uint32_read()
        for item in range(num_items):
            entry = HircEntryFactory.from_memory_stream(reader)
            entry.soundbank = self.soundbank
            self.entries[entry.get_id()] = entry
            try:
                self.type_lists[entry.hierarchy_type].append(entry)
            except:
                self.type_lists[entry.hierarchy_type] = [entry]
                
    def import_hierarchy(self, new_hierarchy: WwiseHierarchy):
        for entry in new_hierarchy.get_entries():
            try:
                self.get_entry(entry.get_id()).import_entry(entry)
            except KeyError:
                self.entries[entry.get_id()] = entry
                self.added_entries[entry.get_id()] = entry
                try:
                    self.type_lists[entry.hierarchy_type].append(entry)
                except KeyError:
                    self.type_lists[entry.hierarchy_type] = [entry]
                
    def revert_modifications(self, entry_id: int = 0):
        if entry_id:
            self.get_entry(entry_id).revert_modifications()
        else:
            for entry in self.removed_entries:
                self.entries[entry.hierarchy_id] = entry
                self.soundbank.lower_modified()
            self.removed_entries.clear()
            for entry in self.added_entries:
                self.remove_entry(entry.hierarchy_id)
                self.soundbank.lower_modified()
            for entry in self.get_entries():
                entry.revert_modifications()
                
    def add_entry(self, new_entry: HircEntry):
        self.soundbank.raise_modified()
        self.added_entries[new_entry.hierarchy_id] = new_entry
        self.entries[new_entry.hierarchy_id] = new_entry
        try:
            self.type_lists[new_entry.hierarchy_type].append(new_entry)
        except KeyError:
            self.type_lists[new_entry.hierarchy_type] = [new_entry]
            
    def remove_entry(self, entry: HircEntry):
        if entry.hierarchy_id in self.entries:
            if entry.hierarchy_id in self.added_entries:
                del self.added_entries[entry.hierarchy_id]
                self.soundbank.lower_modified()
            else:
                self.removed_entries[entry.hierarchy_id] = entry
                self.soundbank.raise_modified()
            self.type_lists[entry.hierarchy_type].remove(entry)
            del self.entries[entry.hierarchy_id]
            
    def get_entry(self, entry_id: int):
        return self.entries[entry_id]
        
    def get_entries(self):
        return self.entries.values()
        
    def get_type(self, hirc_type: int):
        return self.types[hirc_type]
            
    def get_data(self):
        arr = [entry.get_data() for entry in self.entries.values()]
        return len(arr).to_bytes(4, byteorder="little") + b"".join(arr)
  