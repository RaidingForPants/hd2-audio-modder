from util import *
import struct


class HircEntry:
    """
    Must Have:
    hierarchy_type - U8
    size - U32
    hierarchy_id - tid
    -------------------
    1 + 4 + 4 = 9 bytes
    """
    
    import_values = ["misc", "parent_id"]
    
    def __init__(self):
        self.size: int = 0
        self.hierarchy_type: int = 0
        self.hierarchy_id: int = 0
        self.sources: list[BankSourceStruct] = []
        self.track_info = []
        self.soundbank = None # WwiseBank
        self.misc: bytearray = bytearray()
        self.modified_children: int = 0
        self.modified: bool = False
        self.parent_id: int = 0
        self.parent = None
        self.data_old: bytes | bytearray = b""
    
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
        
    def has_modified_children(self):
        return self.modified_children != 0
        
    def set_data(self, entry = None, **data):
        if self.soundbank == None:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            else:
                self.soundbank.raise_modified()
        if entry:
            for value in self.import_values:
                setattr(self, value, getattr(entry, value))
        else:
            for name, value in data.items():
                setattr(self, name, value)
        self.modified = True
        self.size = len(self.get_data())-5
        try:
            self.parent = self.soundbank.hierarchy.get_entry(self.parent_id)
        except:
            self.parent = None

    def revert_modifications(self):
        if self.soundbank == None:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        if self.modified:
            self.set_data(self.from_bytes(self.data_old))
            self.data_old = b""
            self.modified = False
            if self.parent:
                self.parent.lower_modified()
            else:
                self.soundbank.lower_modified()
        
    def import_entry(self, new_entry):
        if (
            (self.modified and new_entry.get_data() != self.data_old)
            or
            (not self.modified and new_entry.get_data() != self.get_data())
        ):
            self.set_data(new_entry)
        
    def get_id(self):
        return self.hierarchy_id
        
    def raise_modified(self):
        if self.soundbank == None:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        self.modified_children+=1
        if self.parent:
            self.parent.raise_modified()
        else:
            self.soundbank.raise_modified()
        
    def lower_modified(self):
        if self.soundbank == None:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        self.modified_children-=1
        if self.parent:
            self.parent.lower_modified()
        else:
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
        return b""


class RandomSequenceContainer(HircEntry):
    
    import_values = ["unused_sections", "contents", "parent_id"]
    
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
        if stream.uint8_read() & 0b0000_1000: #I forget what this is for (if HAS AUX)
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
    
    import_values = ["parent_id", "tracks", "duration", "entry_marker", "exit_marker", "unused_sections", "markers"]

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
        entry.unused_sections.append(stream.read(10))
        entry.parent_id = stream.uint32_read()
        entry.unused_sections.append(stream.read(1))
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
        
    def set_data(self, entry = None, **data):
        if self.soundbank == None:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            else:
                self.soundbank.raise_modified()
        if entry:
            for value in self.import_values:
                setattr(self, value, getattr(entry, value))
        else:
            for name, value in data.items():
                if name == "entry_marker":
                    self.entry_marker[1] = value
                elif name == "exit_marker":
                    self.exit_marker[1] = value
                else:
                    setattr(self, name, value)
        self.modified = True
        self.size = len(self.get_data()) - 5
        try:
            self.parent = self.soundbank.hierarchy.get_entry(self.parent_id)
        except:
            self.parent = None
        
    def get_data(self):
        return (
            b"".join([
                struct.pack("<BII", self.hierarchy_type, self.size, self.hierarchy_id),
                self.unused_sections[0],
                self.parent_id.to_bytes(4, byteorder="little"),
                self.unused_sections[1],
                self.unused_sections[2],
                self.unused_sections[3],
                len(self.tracks).to_bytes(4, byteorder="little"),
                b"".join([x.to_bytes(4, byteorder="little") for x in self.tracks]),
                self.unused_sections[4],
                self.unused_sections[5],
                struct.pack("<d", self.duration),
                len(self.markers).to_bytes(4, byteorder="little"),
                b"".join([b"".join([x[0].to_bytes(4, byteorder="little"), struct.pack("<d", x[1]), x[2]]) for x in self.markers])
            ])
        )
        
            
class BankSourceStruct:
    """
    plugin_id - U32
        - one unsigned 16 bits is codec type / plugin id
        - one 12 bits is company name
        - one 4 bits is plugin type
    stream_type - U8x
    source_id - tid
    mem_size - U32
    bits_flag - U8x
        - bIsLanguageSpecific, bit 0
        - bPrefetch, bit 1
        - bNonCachable, bit 3
        - bHasSource, bit 7
    plugin_size - U32
    plugin_contents - plugin_size
    """

    def __init__(self):
        self.plugin_id: int = 0
        self.stream_type: int = 0
        self.source_id: int = 0
        self.mem_size: int = 0
        self.bit_flags: int = 0
        self.plugin_size: int = 0
        self.plugin_contents: bytearray = bytearray()
        
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
    
    import_values = ["bit_flags", "unused_sections", "parent_id", "sources", "track_info", "misc"]
    
    def __init__(self):
        super().__init__()
        self.bit_flags = 0
        self.unused_sections = []
        
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
        start = stream.tell()
        _ = stream.uint32_read()
        num_clip_automations = stream.uint32_read()
        for _ in range(num_clip_automations):
            stream.advance(8)
            num_graph_points = stream.uint32_read()
            for _ in range(num_graph_points):
                stream.advance(12)
        stream.advance(5)
        end_position = stream.tell()
        stream.seek(start)
        entry.unused_sections.append(stream.read(end_position - start))
        entry.override_bus_id = stream.uint32_read()
        entry.parent_id = stream.uint32_read()
        entry.misc = stream.read(entry.size - (stream.tell()-start_position))
        return entry

    def get_data(self):
        b = b"".join([source.get_data() for source in self.sources])
        t = b"".join([track.get_data() for track in self.track_info])
        return struct.pack("<BIIBI", self.hierarchy_type, self.size, self.hierarchy_id, self.bit_flags, len(self.sources)) + b + len(self.track_info).to_bytes(4, byteorder="little") + t + self.unused_sections[0] + self.override_bus_id.to_bytes(4, byteorder="little") + self.parent_id.to_bytes(4, byteorder="little") + self.misc

    
class Sound(HircEntry):
    """
    bIsOverriderParentFx - U8x
    uNumFx - u8i 
    bitsFxBypass - U8x
    fxChunks - uNumFx * 7 bytes
    bIsOverrideParentMetadata - U8x
    uNumFxMetadata - u8i
    fxChunksMetadata - uNumFxMetadata * FxChunkMetadata
    bOverrideAttachmentParams - U8x
    OverrideBusId - tid
    DirectParentId - tid
    byBitVectorA - U8x
    cProps - u8i
    """
    
    import_values = ["misc", "sources", "parent_id"]
    
    def __init__(self):
        super().__init__()

        self.bIsOverrideParentFx: int = 0
        self.uNumFx: int = 0
        self.bitsFxBypass: int = 0
        self.fxChunks: list[FxChunk] = []
        self.bIsOverrideParentMetadata: int = 0
        self.uNumFxMetadata: int = 0
        self.fxChunksMetadata: list[FxChunkMetadata] = []
        self.bOverrideAttachmentParams: int = 0
        self.OverrideBusId: int = 0
        self.DirectParentId: int = 0
        self.byBitVectorA: int = 0
        self.PropBundles: PropBundle = PropBundle(0, [], [])
        self.RangePropBundles: RangedPropBundles = RangedPropBundles(0, [], [])
    
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
        return struct.pack(f"<BII14s{len(self.misc)}s", self.hierarchy_type, self.size, self.hierarchy_id, self.sources[0].get_data(), self.misc)
        
        
class HircEntryFactory:
    
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        hierarchy_type = stream.uint8_read()
        stream.seek(stream.tell()-1)
        if hierarchy_type == 2: #sound
            if os.environ["TEST_FLAG"] == "True":
                return new_sound(stream)
            else:
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
    
    def __init__(self, soundbank = None):
        self.entries: dict[int, HircEntry] = {}
        self.type_lists: dict[int, list[HircEntry]] = {}
        self.soundbank = soundbank # WwiseBank
        self.added_entries = {}
        self.removed_entries = {}
        
    def load(self, hierarchy_data: bytes | bytearray):
        self.entries.clear()
        reader = MemoryStream()
        reader.write(hierarchy_data)
        reader.seek(0)
        num_items = reader.uint32_read()
        for _ in range(num_items):
            entry = HircEntryFactory.from_memory_stream(reader)
            entry.soundbank = self.soundbank
            self.entries[entry.get_id()] = entry
            try:
                self.type_lists[entry.hierarchy_type].append(entry)
            except:
                self.type_lists[entry.hierarchy_type] = [entry]
        for entry in self.get_entries():
            try:
                entry.parent = self.get_entry(entry.parent_id)
            except:
                pass
                
    def import_hierarchy(self, new_hierarchy):
        for entry in new_hierarchy.get_entries():
            try:
                self.get_entry(entry.get_id()).import_entry(entry)
            except KeyError:
                pass
                self.entries[entry.get_id()] = entry
                self.added_entries[entry.get_id()] = entry
                try:
                    self.type_lists[entry.hierarchy_type].append(entry)
                except KeyError:
                    self.type_lists[entry.hierarchy_type] = [entry]
                
    def revert_modifications(self, entry_id: int = 0):
        if self.soundbank == None:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

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
        if self.soundbank == None:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        self.soundbank.raise_modified()
        self.added_entries[new_entry.hierarchy_id] = new_entry
        self.entries[new_entry.hierarchy_id] = new_entry
        try:
            self.type_lists[new_entry.hierarchy_type].append(new_entry)
        except KeyError:
            self.type_lists[new_entry.hierarchy_type] = [new_entry]
            
    def remove_entry(self, entry: HircEntry):
        if self.soundbank == None:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

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
        try:
            return self.type_lists[hirc_type]
        except KeyError:
            return []
            
    def get_data(self):
        arr = [entry.get_data() for entry in self.entries.values()]
        return len(arr).to_bytes(4, byteorder="little") + b"".join(arr)


"""
## NodeElement, NodeObject 
- 

## Parser Implementation Reference (Wwiser)

- Sound bank chunk parser entry point (header, media index, data index, hierarchy) 
    - https://github.com/bnnm/wwiser/blob/b99fc48d0861349c396a4f7cebbf199dd0339ccf/wwiser/parser/wparser.py#L3785
- Hierarchy chunk parser entry point (`CAkBankMgr__ProcessHircChunk`)
    - https://github.com/bnnm/wwiser/blob/b99fc48d0861349c396a4f7cebbf199dd0339ccf/wwiser/parser/wparser.py#L3148 

## How to Read Hierarchy Parser Reference Implementation

1. At hierarchy chunk parser entry point, it will obtain the available hierachy 
entry parsers available based on the given sound bank version first.
2. Obtain # of releasable hierarchy item -> (# of hierarchy entry)
3. Obtain the type of hierarchy entry
    - When wwiser parser encounter an hierarchy entry, it will dispatch a 
    hierarchy entry parser based on the type of a hierarchy entry. 
    - The parser for each of hierarchy entry parser is obtained through 
    `get_hirc_dispatch` function 
    (https://github.com/bnnm/wwiser/blob/master/wwiser/parser/wparser.py#L3095)
4. Obtain the type of hierarchy entry parser based on the type of hierarchy entry
5. Dispatch the hierarchy entry parser

AH bank version 141
"""


class FxChunk:
    """
    uFxIndex - U8i
    fxId - tid
    bIsShareSet - U8x
    bIsRendered - U8x
    1 + 4 + 1 + 1 = 7 bytes
    """

    def __init__(self, uFxIndex: int, fxId: int, bIsShareSet: int, bIsRendered: int):
        self.uFxIndex: int = uFxIndex # U8i
        self.fxId: int = fxId # tid
        self.bIsShareSet: int = bIsShareSet # U8x
        self.bIsRendered: int = bIsRendered # U8x

    def to_bytes(self):
        return struct.pack(
            "<BIBB", self.uFxIndex, self.fxId, self.bIsShareSet, self.bIsRendered
        )


class FxChunkMetadata:
    """
    uFxIndex - u8i
    fxId - tid
    bIsShareSet - U8x
    1 + 4 + 1 = 6 bytes
    """

    def __init__(self, uFxIndex: int, fxId: int, bIsShareSet: int):
        self.uFxIndex = uFxIndex
        self.fxId = fxId
        self.bIsShareSet = bIsShareSet

    def to_bytes(self):
        return struct.pack("<BIB", self.uFxIndex, self.fxId, self.bIsShareSet)


class PropBundle:
    """
    cProps - u8i
    pIDs[cProps] - cProps * u8i
    pValues[cProps] - cProps * tid / uni (4 bytes)
    """

    def __init__(self, cProps: int, pIDs: list[int], pValues: list[bytearray]):
        self.cProps = cProps
        self.pIDs = pIDs
        self.pValues = pValues

    def to_bytes(self):
        b = struct.pack("<B", self.cProps)
        for pID in self.pIDs:
            b += struct.pack("<B", pID)
        for pValue in self.pValues:
            b += struct.pack("<4s", pValue)
        return b


class RangedPropBundles:
    """
    cProps - u8i
    pIDs[cProps] - cProps * u8i
    rangedValues[cProps] - cProps * (uni [4 bytes] + uni [4 bytes])
    """

    def __init__(
        self,
        cProps: int,
        pIDs: list[int],
        rangedValues: list[tuple[float, float]]
    ):
        self.cProps = cProps
        self.pIDs = pIDs
        self.rangedValues = rangedValues

    def to_bytes(self):
        b = struct.pack("<B", self.cProps)
        for pID in self.pIDs:
            b += struct.pack("<B", pID)
        for rangeValue in self.rangedValues:
            b += struct.pack("<ff", rangeValue[0], rangeValue[1])
        return b


def new_sound(stream: MemoryStream):
    """
    CAkSound Parser Implementation Reference: https://github.com/bnnm/wwiser/blob/b99fc48d0861349c396a4f7cebbf199dd0339ccf/wwiser/parser/wparser.py#L1068
    """

    entry = Sound()
    entry.hierarchy_type = stream.uint8_read()
    entry.size = stream.uint32_read() # exclude hierarchy type and size

    head = stream.tell()

    entry.hierarchy_id = stream.uint32_read()

    # CAkBankMgr__LoadSource
    # https://github.com/bnnm/wwiser/blob/b99fc48d0861349c396a4f7cebbf199dd0339ccf/wwiser/parser/wparser.py#L175
    b = BankSourceStruct.from_bytes(stream.read(14))

    # [Parsing Plugin Content - Read off the size and skip]
    # https://github.com/bnnm/wwiser/blob/b99fc48d0861349c396a4f7cebbf199dd0339ccf/wwiser/parser/wparser.py#L38
    if (b.plugin_id & 0X0F) == 2:
        if b.plugin_id:
            b.plugin_size = stream.uint32_read()
            if b.plugin_size > 0:
                b.plugin_contents = stream.read(b.plugin_size)

    entry.sources.append(b)

    # [Parsing FX]
    entry.bIsOverrideParentFx = stream.uint8_read()
    entry.uNumFx = stream.uint8_read()
    if entry.uNumFx > 0:
        entry.bitsFxBypass = stream.uint8_read()
        entry.fxChunks = [
            FxChunk(
                stream.uint8_read(), 
                stream.uint32_read(),
                stream.uint8_read(),
                stream.uint8_read()
            )
            for _ in range(entry.uNumFx)
        ]

    # [Parsing Metadata]
    entry.bIsOverrideParentMetadata = stream.uint8_read()
    entry.uNumFxMetadata = stream.uint8_read()
    entry.fxChunksMetadata = [
        FxChunkMetadata(
            stream.uint8_read(),
            stream.uint32_read(),
            stream.uint8_read()
        )
        for _ in range(entry.uNumFxMetadata)
    ]

    entry.bOverrideAttachmentParams = stream.uint8_read()
    entry.OverrideBusId = stream.uint32_read()
    entry.DirectParentId = stream.uint32_read()
    entry.byBitVectorA = stream.uint8_read()

    # [Parsing Properties - No Modulator]
    entry.PropBundles.cProps = stream.uint8_read()
    entry.PropBundles.pIDs = [
        stream.uint8_read() for _ in range(entry.PropBundles.cProps)
    ]
    entry.PropBundles.pValues = [
        stream.read(4) for _ in range(entry.PropBundles.cProps)
    ]

    # [Parsing Range Based Properties - No Modulator]
    entry.RangePropBundles.cProps = stream.uint8_read()
    entry.RangePropBundles.pIDs = [
        stream.uint8_read() for _ in range(entry.RangePropBundles.cProps)
    ]
    entry.RangePropBundles.rangedValues = [
        (stream.float_read(), stream.float_read()) 
        for _ in range(entry.RangePropBundles.cProps)
    ]

    entry.misc = stream.read(entry.size - (stream.tell() - head))

    return entry


def pack_sound(sound: Sound):
    b = struct.pack(
        "<BII", sound.hierarchy_type, sound.size, sound.hierarchy_id,
    )

    b += pack_bank_source_struct(sound.sources[0])

    b += struct.pack("<BB", sound.bIsOverrideParentFx, sound.uNumFx)
    if sound.uNumFx > 0:
        b += struct.pack("<B", sound.bitsFxBypass)
        for fxChunk in sound.fxChunks:
            b += fxChunk.to_bytes()

    b += struct.pack("<BB", sound.bIsOverrideParentMetadata, sound.uNumFxMetadata)
    for fxChunkMetadata in sound.fxChunksMetadata:
        b += fxChunkMetadata.to_bytes()

    b += struct.pack(
        "<BIIB",
        sound.bOverrideAttachmentParams,
        sound.OverrideBusId,
        sound.DirectParentId,
        sound.byBitVectorA
    )

    b += sound.PropBundles.to_bytes()
    b += sound.RangePropBundles.to_bytes()

    b += struct.pack(f"{len(sound.misc)}s", sound.misc)

    return b


def pack_bank_source_struct(bank_source_struct: BankSourceStruct):
    b = struct.pack(
        "<IBIIB", 
        bank_source_struct.plugin_id,
        bank_source_struct.stream_type,
        bank_source_struct.source_id,
        bank_source_struct.mem_size,
        bank_source_struct.bit_flags
    )
    if (bank_source_struct.plugin_id & 0X0F) == 2:
        if bank_source_struct.plugin_id:
            b += struct.pack(f"<I", bank_source_struct.plugin_size)
            if bank_source_struct.plugin_size > 0:
                b += struct.pack(
                    f"<{len(bank_source_struct.plugin_contents)}s",
                    bank_source_struct.plugin_contents
                )
    return b
