import struct

from util import *


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
        self.sources = []
        self.track_info = []
        self.soundbank: Any = None # WwiseBank
        self.misc: bytearray = bytearray()
        self.modified_children: int = 0
        self.modified: bool = False
        self.parent_id: int = 0
        self.parent: HircEntry | None = None
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


class Container(HircEntry):
    """
    bIsOverrideParentFx 8 bits
    uNumFx 8 bits
    bitsFxBypass 8 bits
    fxChunks uNumFx * 7 bytes

    bIsOverrideParentMetadata 8 bits
    uNumFxMetadata 8 bits
    fxChunksMetadata uNumFxMetadata * 6 bytes

    bOverrideAttachmentParams 8 bits

    OverrideBusId 32 bits

    DirectParentID 32 bits

    byBitVectorA 8 bits

    AuxParams

    AdvSetting

    StateParams

    ulNumRTPC u16
    RTPC
    """

    def __init__(self):
        super().__init__()

        self.bIsOverrideParentFx: int = 0
        self.uNumFx: int = 0
        self.bitsFxBypass = 0
        self.fxChunks: list[FxChunk] = []

        self.bIsOverrideParentMetadata: int = 0
        self.uNumFxMetadata: int = 0
        self.fxChunksMetadata: list[FxChunkMetadata] = []

        self.bOverrideAttachmentParams: int = 0

        self.OverrideBusId: int = 0

        self.DirectParentID: int = 0

        self.byBitVectorA: int = 0

        self.PropBundle = PropBundle()

        self.positioningParamContent: bytearray = bytearray()

        self.RangePropBundle = RangedPropBundle()

        self.AuxParams = AuxParams()

        self.AdvSetting = AdvSetting()

        self.StateParams = StateParams()

        self.ulNumRTPC: int = 0
        self.RTPCs: list[RTPC] = []

        self.unused_sections = []


class RandomSequenceContainer(Container):
    """
    numChildren u32
    contents numChildren * tid
    """
    import_values = ["unused_sections", "contents", "parent_id"]
    
    def __init__(self):
        super().__init__()

        self.CntrPlayListSetting = CntrPlayListSetting()

        self.numChildren = 0
        self.children: list[int] = []

        self.ulPlayListItem = 0
        self.PlayListItems: list[PlayListItem] = []

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
            entry.children.append(stream.uint32_read())

        entry.unused_sections.append(stream.read(entry.size - (stream.tell()-start_position)))
        return entry
        
    def get_data(self):
        return (
            b"".join([
                struct.pack("<BII", self.hierarchy_type, self.size, self.hierarchy_id),
                self.unused_sections[0],
                len(self.children).to_bytes(4, byteorder="little"),
                b"".join([x.to_bytes(4, byteorder="little") for x in self.children]),
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
    
    import_values = ["misc", "sources", "parent_id"]
    
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
        return struct.pack(f"<BII14s{len(self.misc)}s", self.hierarchy_type, self.size, self.hierarchy_id, self.sources[0].get_data(), self.misc)
        
        
class HircEntryFactory:
    
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        hierarchy_type = stream.uint8_read()
        stream.seek(stream.tell()-1)
        if hierarchy_type == 2: # sound
            return Sound.from_memory_stream(stream)
        elif hierarchy_type == 0x05: # random / sequence container
            if os.environ["TEST"] == "1":
                return new_cntr(stream)
            else:
                return RandomSequenceContainer.from_memory_stream(stream)
        elif hierarchy_type == 0x0A: #music segment
            return MusicSegment.from_memory_stream(stream)
        elif hierarchy_type == 0X0B: #music track
            return MusicTrack.from_memory_stream(stream)
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

    def __init__(self, cProps: int = 0, pIDs: list[int] = [], pValues: list[bytearray] = []):
        self.cProps = cProps
        self.pIDs = pIDs
        self.pValues = pValues
        if self.cProps != len(self.pIDs) != len(self.pValues):
            raise AssertionError("PropBundle.cProps != len(PropBundle.pIDs) != len(PropBundle.pValues) fails")

    def to_bytes(self):
        if self.cProps != len(self.pIDs) != len(self.pValues):
            raise AssertionError("PropBundle.cProps != len(PropBundle.pIDs) != len(PropBundle.pValues) fails")
        b = struct.pack("<B", self.cProps)
        for pID in self.pIDs:
            b += struct.pack("<B", pID)
        for pValue in self.pValues:
            b += struct.pack("<4s", pValue)
        return b


class RangedPropBundle:
    """
    cProps - u8i
    pIDs[cProps] - cProps * u8i
    rangedValues[cProps] - cProps * (uni [4 bytes] + uni [4 bytes])
    """

    def __init__(
        self,
        cProps: int = 0,
        pIDs: list[int] = [],
        rangedValues: list[tuple[float, float]] = []
    ):
        self.cProps = cProps
        self.pIDs = pIDs
        self.rangedValues = rangedValues
        if self.cProps != len(self.pIDs) != len(self.rangedValues):
            raise AssertionError("PropBundle.cProps != len(PropBundle.pIDs) != len(PropBundle.pValues) fails")

    def to_bytes(self):
        if self.cProps != len(self.pIDs) != len(self.rangedValues):
            raise AssertionError("PropBundle.cProps != len(PropBundle.pIDs) != len(PropBundle.pValues) fails")
        b = struct.pack("<B", self.cProps)
        for pID in self.pIDs:
            b += struct.pack("<B", pID)
        for rangeValue in self.rangedValues:
            b += struct.pack("<ff", rangeValue[0], rangeValue[1])
        return b


class AuxParams:
    """
    byBitVectorAux - U8x
    auxIDs - 4 * tid if byBitVectorAux & 0b0000_1000
    reflectionAuxBus - tid
    """

    def __init__(self, byBitVectorAux: int = 0, auxIDs: list[int] = [], reflectionAuxBus: int = 0):
        self.byBitVectorAux = byBitVectorAux
        self.has_aux = self.byBitVectorAux & 0b0000_1000
        self.auxIDs = auxIDs
        self.reflectionAuxBus = reflectionAuxBus
        if not self.has_aux and len(auxIDs) > 0:
            raise AssertionError("AuxParams.has_aux and len(auxIDs) > 0 fails")
        if self.has_aux and len(auxIDs) != 4:
            raise AssertionError("AuxParams.has_aux and len(auxIDs) != 4 fails")

    def to_bytes(self):
        if not self.has_aux and len(self.auxIDs) > 0:
            raise AssertionError("AuxParams.has_aux and len(self.auxIDs) > 0 fails")
        if self.has_aux and len(self.auxIDs) != 4:
            raise AssertionError("AuxParams.has_aux and len(auxIDs) != 4 fails")
        b = struct.pack("<B", self.byBitVectorAux)
        if self.has_aux:
            for auxID in self.auxIDs:
                b += struct.pack("<I", auxID)
        b += struct.pack("<I", self.reflectionAuxBus)
        return b


class AdvSetting:
    """
    byBitVectorAdv U8x
    eVirtualQueueBehavior U8x
    u16MaxNumInstance u16
    eBelowThresholdBehavior U8x
    byBitVectorHDR U8x
    """

    def __init__(
        self, 
        byBitVectorAdv: int = 0,
        eVirtualQueueBehavior: int = 0,
        u16MaxNumInstance: int = 0,
        eBelowThresholdBehavior: int = 0,
        byBitVectorHDR: int = 0
    ):
        self.byBitVectorAdv = byBitVectorAdv
        self.eVirtualQueueBehavior = eVirtualQueueBehavior
        self.u16MaxNumInstance = u16MaxNumInstance
        self.eBelowThresholdBehavior = eBelowThresholdBehavior
        self.byBitVectorHDR = byBitVectorHDR

    def to_bytes(self):
        return struct.pack(
            "<BBHBB",
            self.byBitVectorAdv,
            self.eVirtualQueueBehavior,
            self.u16MaxNumInstance,
            self.eBelowThresholdBehavior,
            self.byBitVectorHDR
        )


class StateProp:
    """
    PropertyId var 8 bits
    accumType U8x
    inDb bool U8x 
    """

    def __init__(self, PropertyId: int = 0, accumType: int = 0, inDb: int = 0):
        self.PropertyId = PropertyId
        self.accumType = accumType
        self.inDb = inDb

    def to_bytes(self):
        return struct.pack("<3B", self.PropertyId, self.accumType, self.inDb)


class StateGroupState:
    """
    ulStateID tid
    ulStateInstanceID tid
    """

    def __init__(self, ulStateID: int = 0, ulStateInstanceID: int = 0):
       self.ulStateID = ulStateID 
       self.ulStateInstanceID = ulStateInstanceID

    def to_bytes(self):
        return struct.pack("<II", self.ulStateID, self.ulStateInstanceID)


class StateGroup:
    """
    ulStateGroupID tid
    eStateSyncType U8x
    ulNumStates var 8 bits
    """

    def __init__(
        self, 
        ulStateGroupID: int = 0,
        eStateSyncType: int = 0,
        ulNumStates: int = 0,
        states: list[StateGroupState] = []
    ):
        self.ulStateGroupID = ulStateGroupID
        self.eStateSyncType = eStateSyncType
        self.ulNumStates = ulNumStates
        self.states = states
        if self.ulNumStates != len(self.states):
            raise AssertionError("StateGroup.ulNumStates != len(StateGroup.states) fails")

    def to_bytes(self):
        if self.ulNumStates != len(self.states):
            raise AssertionError("StateGroup.ulNumStates != len(StateGroup.states) fails")
        b = struct.pack(
            "<IBB", self.ulStateGroupID, self.eStateSyncType, self.ulNumStates
        )
        for state in self.states:
            b += state.to_bytes()
        return b


class StateParams:
    """
    ulNumStatesProps var 8 bits
    stateProps ulNumStateProps * 3 bytes
    ulNumStateGroups var 8 bits
    stateGroups
    """

    def __init__(
        self, 
        ulNumStateProps: int = 0, 
        stateProps: list[StateProp] = [],
        ulNumStateGroups: int = 0,
        stateGroups: list[StateGroup] = []
    ):
        self.ulNumStateProps = ulNumStateProps
        self.stateProps = stateProps
        self.ulNumStateGroups = ulNumStateGroups
        self.stateGroups = stateGroups
        if self.ulNumStateProps != len(self.stateProps):
            raise AssertionError(
                "StateParams.ulNumStateProps != len(StateParams.stateProps) fails"
            )
        if self.ulNumStateGroups != len(self.stateGroups):
            raise AssertionError(
                "StateParams.ulNumStateGroups != len(StateParams.stateGroups) fails"
            )

    def to_bytes(self):
        if self.ulNumStateProps != len(self.stateProps):
            raise AssertionError(
                "StateParams.ulNumStateProps != len(StateParams.stateProps) fails"
            )
        if self.ulNumStateGroups != len(self.stateGroups):
            raise AssertionError(
                "StateParams.ulNumStateGroups != len(StateParams.stateGroups) fails"
            )
        b = struct.pack("<B", self.ulNumStateProps)
        for stateProp in self.stateProps:
            b += stateProp.to_bytes()
        b += struct.pack("<B", self.ulNumStateGroups)
        for stateGroup in self.stateGroups:
            b += stateGroup.to_bytes()
        return b


class RTPCGraphPoint:
    """
    f32 From
    f32 To
    U32 Interp
    """

    def __init__(self, From: float = 0.0, To: float = 0.0, Interp: int = 0):
        self.From = From
        self.To = To
        self.Interp = Interp

    def to_bytes(self):
        return struct.pack("<ffI", self.From, self.To, self.Interp)


class RTPC:
    """
    tid RTPCID
    U8x rtpcType
    U8x rtpcAccum
    var 8 bits ParamID
    sid rtpcCurveID
    U8x eScaling 
    u16 ulSize
    RTPCInterpPoints
    """

    def __init__(
        self, 
        RTPCID: int = 0,
        rtpcType: int = 0,
        rtpcAccum: int = 0,
        ParamID: int = 0,
        rtpcCurveID: int = 0,
        eScaling: int = 0,
        ulSize: int = 0,
        RTPCGraphPoints: list[RTPCGraphPoint] = []
    ):
        self.RTPCID = RTPCID
        self.rtpcType = rtpcType
        self.rtpcAccum = rtpcAccum
        self.ParamID = ParamID
        self.rtpcCurveID = rtpcCurveID
        self.eScaling = eScaling
        self.ulSize = ulSize
        self.RTPCGraphPoints = RTPCGraphPoints
        if self.ulSize != len(self.RTPCGraphPoints):
            raise AssertionError("RTPC.ulSize != len(RTPC.RTPCGraphPoints) fails")

    def to_bytes(self):
        if self.ulSize != len(self.RTPCGraphPoints):
            raise AssertionError("RTPC.ulSize != len(RTPC.RTPCGraphPoints) fails")
        b = struct.pack(
            "<IBBBIBH",
            self.RTPCID, self.rtpcType, self.rtpcAccum, self.ParamID, 
            self.rtpcCurveID, self.eScaling, self.ulSize
        )
        for p in self.RTPCGraphPoints:
            b += p.to_bytes()
        return b


class CntrPlayListSetting:
    """
    sLoopCount u16
    sLoopModMin u16
    sLoopModMax u16
    fTransitionTime f32
    fTransitionTimeModMin f32
    fTransitionTimeModMax f32
    wAvoidReaptCount u16
    eTransitionMode U8x
    eRandomMode U8x
    eMode U8x
    byBitVectorPlayList U8x
    """

    def __init__(
        self,
        sLoopCount: int = 0,
        sLoopModMin: int = 0,
        sLoopModMax: int = 0,
        fTransitionTime: float = 0,
        fTransitionTimeModMin: float = 0,
        fTransitionTimeModMax: float = 0,
        wAvoidReaptCount: int = 0,
        eTransitionMode: int = 0,
        eRandomMode: int = 0,
        eMode: int = 0,
        byBitVectorPlayList: int = 0
    ):
        self.sLoopCount = sLoopCount 
        self.sLoopModMin = sLoopModMin 
        self.sLoopModMax = sLoopModMax 
        self.fTransitionTime = fTransitionTime 
        self.fTransitionTimeModMin = fTransitionTimeModMin 
        self.fTransitionTimeModMax = fTransitionTimeModMax 
        self.wAvoidReaptCount = wAvoidReaptCount 
        self.eTransitionMode = eTransitionMode 
        self.eRandomMode = eRandomMode 
        self.eMode = eMode 
        self.byBitVectorPlayList = byBitVectorPlayList 

    def to_bytes(self):
        return struct.pack(
            "<HHHfffHBBBB",
            self.sLoopCount,
            self.sLoopModMin,
            self.sLoopModMax,
            self.fTransitionTime,
            self.fTransitionTimeModMin,
            self.fTransitionTimeModMax,
            self.wAvoidReaptCount,
            self.eTransitionMode,
            self.eRandomMode,
            self.eMode,
            self.byBitVectorPlayList,
        )


class PlayListItem:
    """
    ulPlayID tid
    weight s32
    """

    def __init__(self, ulPlayID: int, weight: int):
        self.ulPlayID = ulPlayID
        self.weight = weight

    def to_bytes(self):
        return struct.pack("<II", self.ulPlayID, self.weight)


class LayerContainer(RandomSequenceContainer):

    def __init__(self):
        super().__init__()

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        cntr = LayerContainer()

        cntr.hierarchy_type = stream.uint8_read()

        cntr.size = stream.uint32_read()

        head = stream.tell()

        cntr.hierarchy_id = stream.uint32_read()

        set_hierarchy_params(cntr, stream)

        #

        tail = stream.tell()

        if cntr.size != (tail - head):
            raise AssertionError("LayerContainer.size != (tail - head) fails")

        return cntr


def new_cntr(stream: MemoryStream):
    cntr = RandomSequenceContainer()

    cntr.hierarchy_type = stream.uint8_read()

    cntr.size = stream.uint32_read()

    head = stream.tell()

    cntr.hierarchy_id = stream.uint32_read()

    set_hierarchy_params(cntr, stream)

    # [PlayList Setting]
    cntr.CntrPlayListSetting.sLoopCount = stream.uint16_read()
    cntr.CntrPlayListSetting.sLoopModMin = stream.uint16_read()
    cntr.CntrPlayListSetting.sLoopModMax = stream.uint16_read()
    cntr.CntrPlayListSetting.fTransitionTime = stream.float_read()
    cntr.CntrPlayListSetting.fTransitionTimeModMin = stream.float_read()
    cntr.CntrPlayListSetting.fTransitionTimeModMax = stream.float_read()
    cntr.CntrPlayListSetting.wAvoidReaptCount = stream.uint16_read()
    cntr.CntrPlayListSetting.eTransitionMode = stream.uint8_read()
    cntr.CntrPlayListSetting.eRandomMode = stream.uint8_read()
    cntr.CntrPlayListSetting.eMode = stream.uint8_read()
    cntr.CntrPlayListSetting.byBitVectorPlayList = stream.uint8_read()

    # [Children]
    cntr.numChildren = stream.uint32_read()
    for _ in range(cntr.numChildren):
        cntr.children.append(stream.uint32_read())

    # [PlayListItem]
    cntr.ulPlayListItem = stream.uint16_read()
    cntr.PlayListItems = [
        PlayListItem(stream.uint32_read(), stream.int32_read())
        for _ in range(cntr.ulPlayListItem)
    ]

    tail = stream.tell()

    if cntr.size != (tail - head):
        raise AssertionError("RandomSequenceContainer.size != (tail - head) fails")

    return cntr


def set_hierarchy_params(
    entry: RandomSequenceContainer | LayerContainer,
    stream: MemoryStream
):
    # [Fx]
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

    # [Metadata Fx]
    entry.bIsOverrideParentMetadata = stream.uint8_read()
    entry.uNumFxMetadata = stream.uint8_read()
    if entry.uNumFxMetadata > 0:
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

    entry.DirectParentID = stream.uint32_read()

    entry.byBitVectorA = stream.uint8_read()

    # [Properties - No Modulator]
    entry.PropBundle.cProps = stream.uint8_read()
    entry.PropBundle.pIDs = [
        stream.uint8_read() for _ in range(entry.PropBundle.cProps)
    ]
    entry.PropBundle.pValues = [
        stream.read(4) for _ in range(entry.PropBundle.cProps)
    ]

    # [Range Based Properties - No Modulator]
    entry.RangePropBundle.cProps = stream.uint8_read()
    entry.RangePropBundle.pIDs = [
        stream.uint8_read() for _ in range(entry.RangePropBundle.cProps)
    ]
    entry.RangePropBundle.rangedValues = [
        (stream.float_read(), stream.float_read()) 
        for _ in range(entry.RangePropBundle.cProps)
    ]

    # [Skip Positioning Param]
    positioningParamStart = stream.tell()
    if stream.uint8_read() & 0b0000_0010: # positioning bit vector
        if stream.uint8_read() & 0b0100_0000: # relative pathing bit vector
            stream.advance(5)
            stream.advance(16*stream.uint32_read())
            stream.advance(20*stream.uint32_read())
    positioningParamContenSize = stream.tell() - positioningParamStart
    stream.seek(positioningParamStart)
    entry.positioningParamContent = stream.read(positioningParamContenSize)

    # [Aux Params]
    entry.AuxParams.byBitVectorAux = stream.uint8_read()
    entry.AuxParams.has_aux = entry.AuxParams.byBitVectorAux & 0b0000_1000 
    if entry.AuxParams.has_aux:
        auxIDs: list[int] = [stream.uint32_read() for _ in range(4)] 
        entry.AuxParams.auxIDs = auxIDs
    entry.AuxParams.reflectionAuxBus = stream.uint32_read()

    # [Adv Setting Params]
    entry.AdvSetting.byBitVectorAdv = stream.uint8_read()
    entry.AdvSetting.eVirtualQueueBehavior = stream.uint8_read()
    entry.AdvSetting.u16MaxNumInstance = stream.uint16_read()
    entry.AdvSetting.eBelowThresholdBehavior = stream.uint8_read()
    entry.AdvSetting.byBitVectorHDR = stream.uint8_read()

    # [State]
    entry.StateParams.ulNumStateProps = stream.uint8_read()
    entry.StateParams.stateProps = [
        StateProp(
            stream.uint8_read(),
            stream.uint8_read(),
            stream.uint8_read()
        ) for _ in range(entry.StateParams.ulNumStateProps)
    ]
    entry.StateParams.ulNumStateGroups = stream.uint8_read()
    stateGroups: list[StateGroup] = []
    for _ in range(entry.StateParams.ulNumStateGroups):
        ulStateGroupID = stream.uint32_read()
        eStateSyncType = stream.uint8_read()
        ulNumStates = stream.uint8_read()
        states: list[StateGroupState] = [
            StateGroupState(stream.uint32_read(), stream.uint32_read())
            for _ in range(ulNumStates)
        ]
        stateGroups.append(StateGroup(
            ulStateGroupID,
            eStateSyncType,
            ulNumStates,
            states
        ))
    entry.StateParams.stateGroups = stateGroups

    # [RTPC No Modulator]
    entry.ulNumRTPC = stream.uint16_read()
    RTPCs: list[RTPC] = []
    for _ in range(entry.ulNumRTPC):
        RTPCID = stream.uint32_read()
        rtpcType = stream.uint8_read()
        rtpcAccum = stream.uint8_read()
        ParamID = stream.uint8_read()
        rtpcCurveID = stream.uint32_read()
        eScaling  = stream.uint8_read()
        ulSize = stream.uint16_read()
        RTPCGraphPoints: list[RTPCGraphPoint] = [
            RTPCGraphPoint(
                stream.float_read(), 
                stream.float_read(), 
                stream.uint32_read()
            )
            for _ in range(ulSize)
        ]
        RTPCs.append(RTPC(
            RTPCID, rtpcType, rtpcAccum, ParamID, rtpcCurveID, eScaling, ulSize, 
            RTPCGraphPoints
        ))
    entry.RTPCs = RTPCs


def pack_hierarchy_params(entry: RandomSequenceContainer | LayerContainer,):
    b = b""

    # [Fx]
    if entry.uNumFx != len(entry.fxChunks):
        raise AssertionError("RandomSequenceContainer.uNumFx != len(RandomSequenceContainer.fxChunks) fails")
    if entry.uNumFx > 0:
        b += struct.pack("<B", entry.bitsFxBypass)
        for fxChunk in entry.fxChunks:
            b += fxChunk.to_bytes()

    # [Metadata Fx]
    if entry.uNumFxMetadata != len(entry.fxChunksMetadata):
        raise AssertionError("RandomSequenceContainer.uNumFxMetadata != len(RandomSequenceContainer.fxChunksMetadata) fails")
    b += struct.pack("<BB", entry.bIsOverrideParentMetadata, entry.uNumFxMetadata)
    if entry.uNumFxMetadata > 0:
        for fxChunkMetadata in entry.fxChunksMetadata:
            b += fxChunkMetadata.to_bytes()

    b += struct.pack(
        "<BIIB", 
        entry.bOverrideAttachmentParams,
        entry.OverrideBusId,
        entry.DirectParentID,
        entry.byBitVectorA
    )

    b += entry.PropBundle.to_bytes()

    b += entry.RangePropBundle.to_bytes()
    
    b += struct.pack(f"<{len(entry.positioningParamContent)}s", entry.positioningParamContent)

    b += entry.AuxParams.to_bytes()

    b += entry.AdvSetting.to_bytes()

    b += entry.StateParams.to_bytes()

    b += struct.pack("<H", entry.ulNumRTPC)
    if entry.ulNumRTPC != len(entry.RTPCs):
        raise AssertionError("RandomSequenceContainer.ulNumRTPC != len(RandomSequenceContainer.RTPCs) fails")
    for rtpc in entry.RTPCs:
        b += rtpc.to_bytes()

    return b


def pack_cntr(cntr: RandomSequenceContainer):
    b = struct.pack("<BII", cntr.hierarchy_type, cntr.size, cntr.hierarchy_id)
    b += struct.pack("<BB", cntr.bIsOverrideParentFx, cntr.uNumFx)

    b += pack_hierarchy_params(cntr)

    b += cntr.CntrPlayListSetting.to_bytes()

    if cntr.numChildren != len(cntr.children):
        raise AssertionError("RandomSequenceContainer.numChildren != len(RandomSequenceContainer.contents) fails")
    b += struct.pack("<I", cntr.numChildren)
    for child in cntr.children:
        b += struct.pack("<I", child)

    if cntr.ulPlayListItem != len(cntr.PlayListItems):
        raise AssertionError("RandomSequenceContainer.ulPlayListItem != len(RandomSequenceContainer.PlayListItems) fails")
    b += struct.pack("<H", cntr.ulPlayListItem)
    for playListItem in cntr.PlayListItems:
        b += playListItem.to_bytes()

    if cntr.size != len(b) - 5:
        raise AssertionError(f"Packing size mismatch with specified size: {cntr.size} and {len(b) - 5}")

    return b
