import struct

from util import *
from log import logger


class HircEntry:
    """
    Must Have:
    hierarchy_type - U8
    size - U32
    hierarchy_id - tid
    """
    
    import_values = ["misc", "parent_id"]
    
    def __init__(self):
        self.size: int = 0
        self.hierarchy_type: int = 0
        self.hierarchy_id: int = 0
        self.sources: list[BankSourceStruct] = []
        self.track_info = []
        self.soundbank: Any = None # WwiseBank
        self.misc: bytearray = bytearray()
        self.modified_children: int = 0
        self.modified: bool = False
        self.parent_id: int = 0
        self.parent: HircEntry | None = None
        self.data_old: bytes | bytearray = b""
        self.unused_sections = []
    
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
    """
    Data from container plus the following:
        baseParam sizeof(BaseParam)
        children sizeof(ContainerChildren)
        sCntrPlayListSetting izeof(CntrPlayListSetting)
        ulPlayListItem u16
        playListItem ulPlayListItem * sizeof(PlayListItem)
    """
    import_values = ["unused_sections", "contents", "parent_id"]
    def __init__(self):
        super().__init__()
        self.baseParam: BaseParam | None = None
        self.children: list[int] = []
        self.containerChildren: ContainerChildren = ContainerChildren()
        self.playListSetting = PlayListSetting()
        self.ulPlayListItem = 0
        self.playListItems: list[PlayListItem] = []

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        cntr = RandomSequenceContainer()

        cntr.hierarchy_type = stream.uint8_read()

        cntr.size = stream.uint32_read()

        head = stream.tell()

        cntr.hierarchy_id = stream.uint32_read()

        cntr.baseParam = BaseParam.from_memory_stream(stream)

        # [PlayList Setting]
        cntr.playListSetting.sLoopCount = stream.uint16_read()
        cntr.playListSetting.sLoopModMin = stream.uint16_read()
        cntr.playListSetting.sLoopModMax = stream.uint16_read()
        cntr.playListSetting.fTransitionTime = stream.float_read()
        cntr.playListSetting.fTransitionTimeModMin = stream.float_read()
        cntr.playListSetting.fTransitionTimeModMax = stream.float_read()
        cntr.playListSetting.wAvoidReaptCount = stream.uint16_read()
        cntr.playListSetting.eTransitionMode = stream.uint8_read()
        cntr.playListSetting.eRandomMode = stream.uint8_read()
        cntr.playListSetting.eMode = stream.uint8_read()
        cntr.playListSetting.byBitVectorPlayList = stream.uint8_read()

        # [Children]
        cntr.containerChildren.numChildren = stream.uint32_read()
        for _ in range(cntr.containerChildren.numChildren):
            cntr.containerChildren.children.append(stream.uint32_read())

        # [PlayListItem]
        cntr.ulPlayListItem = stream.uint16_read()
        cntr.playListItems = [
            PlayListItem(stream.uint32_read(), stream.int32_read())
            for _ in range(cntr.ulPlayListItem)
        ]

        tail = stream.tell()

        if cntr.size != (tail - head):
            raise AssertionError("RandomSequenceContainer.size != (tail - head) fails")

        return cntr


    def get_data(self):
        b = struct.pack("<BII", self.hierarchy_type, self.size, self.hierarchy_id)

        if self.baseParam == None:
            raise AssertionError(
                f"Random / Sequence container {self.hierarchy_id} does not has a base parameter."
            )
        b += self.baseParam.get_data()

        b += self.playListSetting.get_data()

        b += self.containerChildren.get_data()

        if self.ulPlayListItem != len(self.playListItems):
            raise AssertionError("RandomSequenceContainer.ulPlayListItem != len(RandomSequenceContainer.PlayListItems) fails")
        b += struct.pack("<H", self.ulPlayListItem)
        for playListItem in self.playListItems:
            b += playListItem.get_data()

        if self.size != len(b) - 5:
            raise AssertionError(f"Random / Sequence container: packing size mismatch with specified size: {self.size} and {len(b) - 5}")

        return b
    

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
    plugin_id U32
    stream_type U8x
    source_id tid
    mem_size U32
    bit_flags U8x
    plugin_size U32
    plugin_contents plugin_size
    """

    def __init__(self):
        self.plugin_id: int = 0
        self.stream_type: int = 0
        self.source_id: int = 0
        self.mem_size: int = 0
        self.bit_flags: int = 0
        self.plugin_size: int = 0
        self.plugin_data: bytearray = bytearray()
        
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        b = BankSourceStruct()
        b.plugin_id, b.stream_type, b.source_id, b.mem_size, b.bit_flags = \
            struct.unpack("<IBIIB", stream.read(14))
        if (b.plugin_id & 0x0F) == 2:
            if b.plugin_id:
                b.plugin_size = stream.uint32_read()
                if b.plugin_size > 0:
                    b.plugin_data = stream.read(b.plugin_size)
        return b
        
    def get_data(self):
        b = struct.pack(
            "<IBIIB",
            self.plugin_id,
            self.stream_type,
            self.source_id,
            self.mem_size,
            self.bit_flags
        )
        if (self.plugin_id & 0X0F) == 2:
            if self.plugin_id:
                b += struct.pack(f"<I", self.plugin_size)
                if self.plugin_size > 0:
                    if self.plugin_size != len(self.plugin_data):
                        raise AssertionError(
                            "BankSourceStruct.plugin_size != len(BankSourceStruct.plugin_data)",
                            " fails"
                        )
                    b += struct.pack(f"<{len(self.plugin_data)}s", self.plugin_data)
        return b
        

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
            source = BankSourceStruct.from_memory_stream(stream)
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

        self.baseParam: BaseParam | None = None 
    
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        sound = Sound()

        sound.hierarchy_type = stream.uint8_read()

        sound.size = stream.uint32_read()

        head = stream.tell()

        sound.hierarchy_id = stream.uint32_read()

        sound.sources.append(BankSourceStruct.from_memory_stream(stream))

        sound.baseParam = BaseParam.from_memory_stream(stream)

        tail = stream.tell()

        if sound.size != (tail - head):
            raise AssertionError("Sound.size != (tail - head) fails")

        return sound

    def get_data(self):
        b = struct.pack("<BII", self.hierarchy_type, self.size, self.hierarchy_id)
        b += self.sources[0].get_data()
        if self.baseParam == None:
            raise AssertionError(
                f"Sound {self.hierarchy_id} does not has a base parameter."
            )
        b += self.baseParam.get_data()
        return b
        
        
class HircEntryFactory:
    
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        hierarchy_type = stream.uint8_read()
        stream.seek(stream.tell()-1)
        if hierarchy_type == 0x02: # sound
            return Sound.from_memory_stream(stream)
        elif hierarchy_type == 0x05: # random / sequence container
            return RandomSequenceContainer.from_memory_stream(stream)
        elif hierarchy_type == 0x07:
            return ActorMixer.from_memory_stream(stream)
        elif hierarchy_type == 0x09:
            return LayerContainer.from_memory_stream(stream)
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
    """

    def __init__(
        self, uFxIndex: int, fxId: int, bIsShareSet: int, bIsRendered: int
    ):
        self.uFxIndex: int = uFxIndex # U8i
        self.fxId: int = fxId # tid
        self.bIsShareSet: int = bIsShareSet # U8x
        self.bIsRendered: int = bIsRendered # U8x

    def get_data(self):
        return struct.pack(
            "<BIBB", self.uFxIndex, self.fxId, self.bIsShareSet, self.bIsRendered
        )


class FxChunkMetadata:
    """
    uFxIndex - u8i
    fxId - tid
    bIsShareSet - U8x
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
    pValues[cProps] - cProps * tid / uni
    """

    def __init__(
        self,
        cProps: int = 0,
        pIDs: list[int] = [],
        pValues: list[bytearray] = []
    ):
        self.cProps = cProps
        self.pIDs = pIDs
        self.pValues = pValues
        if self.cProps != len(self.pIDs) != len(self.pValues):
            raise AssertionError("PropBundle.cProps != len(PropBundle.pIDs) != len(PropBundle.pValues) fails")

    def get_data(self):
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
    rangedValues[cProps] - cProps * (uni + uni)
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

    def get_data(self):
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

    def __init__(
        self,
        byBitVectorAux: int = 0,
        auxIDs: list[int] = [],
        reflectionAuxBus: int = 0
    ):
        self.byBitVectorAux = byBitVectorAux
        self.has_aux = self.byBitVectorAux & 0b0000_1000
        self.auxIDs = auxIDs
        self.reflectionAuxBus = reflectionAuxBus
        if not self.has_aux and len(auxIDs) > 0:
            raise AssertionError("AuxParams.has_aux and len(auxIDs) > 0 fails")
        if self.has_aux and len(auxIDs) != 4:
            raise AssertionError("AuxParams.has_aux and len(auxIDs) != 4 fails")

    def get_data(self):
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

    def get_data(self):
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
    propertyId var (8 bits)
    accumType U8x
    inDb bool U8x 
    """

    def __init__(self, propertyId: int = 0, accumType: int = 0, inDb: int = 0):
        self.propertyId = propertyId
        self.accumType = accumType
        self.inDb = inDb

    def to_bytes(self):
        return struct.pack("<3B", self.propertyId, self.accumType, self.inDb)


class StateGroupState:
    """
    ulStateID tid
    ulStateInstanceID tid
    """

    def __init__(self, ulStateID: int = 0, ulStateInstanceID: int = 0):
       self.ulStateID = ulStateID 
       self.ulStateInstanceID = ulStateInstanceID

    def get_data(self):
        return struct.pack("<II", self.ulStateID, self.ulStateInstanceID)


class StateGroup:
    """
    ulStateGroupID tid
    eStateSyncType U8x
    ulNumStates var (8 bits)
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

    def get_data(self):
        if self.ulNumStates != len(self.states):
            raise AssertionError("StateGroup.ulNumStates != len(StateGroup.states) fails")
        b = struct.pack(
            "<IBB", self.ulStateGroupID, self.eStateSyncType, self.ulNumStates
        )
        for state in self.states:
            b += state.get_data()
        return b


class StateParams:
    """
    ulNumStatesProps var (8 bits)
    stateProps ulNumStateProps * sizeof(StateProp)
    ulNumStateGroups var (8 bits)
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

    def get_data(self):
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
            b += stateGroup.get_data()
        return b


class RTPCGraphPoint:
    """
    from f32
    to f32
    interp U32
    """

    def __init__(self, _from: float = 0.0, to: float = 0.0, interp: int = 0):
        self._from = _from
        self.to = to
        self.interp = interp

    def get_data(self):
        return struct.pack("<ffI", self._from, self.to, self.interp)


class RTPC:
    """
    rtpcID tid
    rtpcType U8x
    rtpcAccum U8x
    paramID var (8 bits)
    rtpcCurveID sid
    eScaling  U8x
    ulSize u16
    rtpcGraphPoints ulSize * sizeof(RTPCGraphPoint)
    """

    def __init__(
        self, 
        rtpcID: int = 0,
        rtpcType: int = 0,
        rtpcAccum: int = 0,
        paramID: int = 0,
        rtpcCurveID: int = 0,
        eScaling: int = 0,
        ulSize: int = 0,
        rtpcGraphPoints: list[RTPCGraphPoint] = []
    ):
        self.rtpcID = rtpcID
        self.rtpcType = rtpcType
        self.rtpcAccum = rtpcAccum
        self.paramID = paramID
        self.rtpcCurveID = rtpcCurveID
        self.eScaling = eScaling
        self.ulSize = ulSize
        self.rtpcGraphPoints = rtpcGraphPoints
        if self.ulSize != len(self.rtpcGraphPoints):
            raise AssertionError("RTPC.ulSize != len(RTPC.RTPCGraphPoints) fails")

    def get_data(self):
        if self.ulSize != len(self.rtpcGraphPoints):
            raise AssertionError("RTPC.ulSize != len(RTPC.RTPCGraphPoints) fails")
        b = struct.pack(
            "<IBBBIBH",
            self.rtpcID, self.rtpcType, self.rtpcAccum, self.paramID, 
            self.rtpcCurveID, self.eScaling, self.ulSize
        )
        for p in self.rtpcGraphPoints:
            b += p.get_data()
        return b


class BaseParam:

    def __init__(self):
        self.bIsOverrideParentFx: int = 0
        self.uNumFx: int = 0
        self.bitsFxBypass = 0
        self.fxChunks: list[FxChunk] = []

        self.bIsOverrideParentMetadata: int = 0
        self.uNumFxMetadata: int = 0
        self.fxChunksMetadata: list[FxChunkMetadata] = []

        self.bOverrideAttachmentParams: int = 0
        self.overrideBusId: int = 0
        self.directParentID: int = 0
        self.byBitVectorA: int = 0

        self.propBundle = PropBundle()

        self.positioningParamData: bytearray = bytearray()

        self.rangePropBundle = RangedPropBundle()

        self.auxParams = AuxParams()

        self.advSetting = AdvSetting()

        self.stateParams = StateParams()

        self.ulNumRTPC: int = 0
        self.rtpcs: list[RTPC] = []

    @staticmethod
    def from_memory_stream(stream: MemoryStream):
        # [Fx]
        baseParam = BaseParam()

        baseParam.bIsOverrideParentFx = stream.uint8_read()
        baseParam.uNumFx = stream.uint8_read()
        if baseParam.uNumFx > 0:
            baseParam.bitsFxBypass = stream.uint8_read()
            baseParam.fxChunks = [
                FxChunk(
                    stream.uint8_read(),
                    stream.uint32_read(),
                    stream.uint8_read(),
                    stream.uint8_read()
                )
                for _ in range(baseParam.uNumFx)
            ]

        # [Metadata Fx]
        baseParam.bIsOverrideParentMetadata = stream.uint8_read()
        baseParam.uNumFxMetadata = stream.uint8_read()
        if baseParam.uNumFxMetadata > 0:
            baseParam.fxChunksMetadata = [
                FxChunkMetadata(
                    stream.uint8_read(),
                    stream.uint32_read(),
                    stream.uint8_read()
                )
                for _ in range(baseParam.uNumFxMetadata)
            ]

        baseParam.bOverrideAttachmentParams = stream.uint8_read()

        baseParam.overrideBusId = stream.uint32_read()

        baseParam.directParentID = stream.uint32_read()

        baseParam.byBitVectorA = stream.uint8_read()

        # [Properties - No Modulator]
        baseParam.propBundle.cProps = stream.uint8_read()
        baseParam.propBundle.pIDs = [
            stream.uint8_read() for _ in range(baseParam.propBundle.cProps)
        ]
        baseParam.propBundle.pValues = [
            stream.read(4) for _ in range(baseParam.propBundle.cProps)
        ]

        # [Range Based Properties - No Modulator]
        baseParam.rangePropBundle.cProps = stream.uint8_read()
        baseParam.rangePropBundle.pIDs = [
            stream.uint8_read() for _ in range(baseParam.rangePropBundle.cProps)
        ]
        baseParam.rangePropBundle.rangedValues = [
            (stream.float_read(), stream.float_read()) 
            for _ in range(baseParam.rangePropBundle.cProps)
        ]

        # [Positioning Param]
        baseParam.positioningParamData = parse_positioning_params(stream)

        # [Aux Params]
        baseParam.auxParams.byBitVectorAux = stream.uint8_read()
        baseParam.auxParams.has_aux = baseParam.auxParams.byBitVectorAux & 0b0000_1000 
        if baseParam.auxParams.has_aux:
            auxIDs: list[int] = [stream.uint32_read() for _ in range(4)] 
            baseParam.auxParams.auxIDs = auxIDs
        baseParam.auxParams.reflectionAuxBus = stream.uint32_read()

        # [Adv Setting Params]
        baseParam.advSetting.byBitVectorAdv = stream.uint8_read()
        baseParam.advSetting.eVirtualQueueBehavior = stream.uint8_read()
        baseParam.advSetting.u16MaxNumInstance = stream.uint16_read()
        baseParam.advSetting.eBelowThresholdBehavior = stream.uint8_read()
        baseParam.advSetting.byBitVectorHDR = stream.uint8_read()

        # [State]
        baseParam.stateParams.ulNumStateProps = stream.uint8_read()
        baseParam.stateParams.stateProps = [
            StateProp(
                stream.uint8_read(),
                stream.uint8_read(),
                stream.uint8_read()
            ) for _ in range(baseParam.stateParams.ulNumStateProps)
        ]
        baseParam.stateParams.ulNumStateGroups = stream.uint8_read()
        stateGroups: list[StateGroup] = []
        for _ in range(baseParam.stateParams.ulNumStateGroups):
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
        baseParam.stateParams.stateGroups = stateGroups

        # [RTPC No Modulator]
        baseParam.ulNumRTPC = stream.uint16_read()
        rtpcs: list[RTPC] = []
        for _ in range(baseParam.ulNumRTPC):
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
            rtpcs.append(RTPC(
                RTPCID, rtpcType, rtpcAccum, ParamID, rtpcCurveID, eScaling, ulSize, 
                RTPCGraphPoints
            ))
        baseParam.rtpcs = rtpcs

        return baseParam


    def get_data(self):
        b = struct.pack("<BB", self.bIsOverrideParentFx, self.uNumFx)

        # [Fx]
        if self.uNumFx != len(self.fxChunks):
            raise AssertionError("RandomSequenceContainer.uNumFx != len(RandomSequenceContainer.fxChunks) fails")
        if self.uNumFx > 0:
            b += struct.pack("<B", self.bitsFxBypass)
            for fxChunk in self.fxChunks:
                b += fxChunk.get_data()

        # [Metadata Fx]
        if self.uNumFxMetadata != len(self.fxChunksMetadata):
            raise AssertionError("RandomSequenceContainer.uNumFxMetadata != len(RandomSequenceContainer.fxChunksMetadata) fails")
        b += struct.pack("<BB", self.bIsOverrideParentMetadata, self.uNumFxMetadata)
        if self.uNumFxMetadata > 0:
            for fxChunkMetadata in self.fxChunksMetadata:
                b += fxChunkMetadata.to_bytes()

        b += struct.pack(
            "<BIIB", 
            self.bOverrideAttachmentParams,
            self.overrideBusId,
            self.directParentID,
            self.byBitVectorA
        )

        b += self.propBundle.get_data()

        b += self.rangePropBundle.get_data()
        
        b += struct.pack(f"<{len(self.positioningParamData)}s", self.positioningParamData)

        b += self.auxParams.get_data()

        b += self.advSetting.get_data()

        b += self.stateParams.get_data()

        b += struct.pack("<H", self.ulNumRTPC)
        if self.ulNumRTPC != len(self.rtpcs):
            raise AssertionError("RandomSequenceContainer.ulNumRTPC != len(RandomSequenceContainer.RTPCs) fails")
        for rtpc in self.rtpcs:
            b += rtpc.get_data()

        return b


class ContainerChildren:
    """
    numChildren u32
    children numChildren * tid
    """

    def __init__(self):
        self.numChildren = 0
        self.children: list[int] = []

    def get_data(self):
        if self.numChildren != len(self.children):
            raise AssertionError(
                "ContainerChildren.numChildren != len(ContainerChildren.contents) "
                "fails"
            )
        b = struct.pack("<I", self.numChildren)
        for child in self.children:
            b += struct.pack("<I", child)
        return b


class PlayListSetting:
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

    def get_data(self):
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

    def get_data(self):
        return struct.pack("<II", self.ulPlayID, self.weight)


class LayerContainer(HircEntry):
    """
    ulNumLayers u32
    """

    def __init__(self):
        super().__init__()
        self.baseParam: BaseParam | None = None
        self.children: ContainerChildren = ContainerChildren()
        self.ulNumLayers: int = 0
        self.layerData: bytearray = bytearray()

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        l = LayerContainer()

        l.hierarchy_type = stream.uint8_read()

        l.size = stream.uint32_read()

        head = stream.tell()

        l.hierarchy_id = stream.uint32_read()

        l.baseParam = BaseParam.from_memory_stream(stream)

        # [Children]
        l.children.numChildren = stream.uint32_read()
        for _ in range(l.children.numChildren):
            l.children.children.append(stream.uint32_read())

        # [Skip Layer]
        l.layerData = stream.read(l.size - (stream.tell() - head))

        tail = stream.tell()

        if l.size != (tail - head):
            raise AssertionError("LayerContainer.size != (tail - head) fails")

        return l

    def get_data(self):
        b = struct.pack("<BII", self.hierarchy_type, self.size, self.hierarchy_id)

        if self.baseParam == None:
            raise AssertionError(
                f"Layer container {self.hierarchy_id} does not has a base parameter."
            )
        b += self.baseParam.get_data()

        b += self.children.get_data()

        b += struct.pack(f"<{len(self.layerData)}s", self.layerData)

        if self.size != len(b) - 5:
            raise AssertionError(f"LayerContainer: packing size mismatch with specified size: {self.size} and {len(b) - 5}")

        return b


class ActorMixer(HircEntry):

    def __init__(self):
        super().__init__()
        self.baseParam: BaseParam | None = None
        self.children: ContainerChildren = ContainerChildren()

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        mixer = ActorMixer()

        mixer.hierarchy_type = stream.uint8_read()

        mixer.size = stream.uint32_read()

        head = stream.tell()

        mixer.hierarchy_id = stream.uint32_read()

        mixer.baseParam = BaseParam.from_memory_stream(stream)

        # [Children]
        mixer.children.numChildren = stream.uint32_read()
        for _ in range(mixer.children.numChildren):
            mixer.children.children.append(stream.uint32_read())

        tail = stream.tell()

        if mixer.size != (tail - head):
            raise AssertionError("ActorMixer.size != (tail - head) fails")

        return mixer

    def get_data(self):
        b = struct.pack("<BII", self.hierarchy_type, self.size, self.hierarchy_id)

        if self.baseParam == None:
            raise AssertionError(
                "Layer container does not has a base parameter."
            )

        b += self.baseParam.get_data()
        
        b += self.children.get_data()

        if self.size != len(b) - 5:
            raise AssertionError(f"ActorMixer: packing size mismatch with specified size: {self.size} and {len(b) - 5}")
       
        return b


def parse_positioning_params(stream: MemoryStream):
    """
    Keep this algorithm here but the data is not used currently
    """
    head = stream.tell()

    uBitsPositioning = stream.uint8_read() # U8x
    has_positioning = (uBitsPositioning >> 0) & 1

    has_3d = False
    if has_positioning:
        has_3d = (uBitsPositioning >> 1) & 1

    if has_positioning and has_3d:
        uBits3d = stream.uint8_read() # U8x
        eType = 0

        e3DPositionType = (uBitsPositioning >> 5) & 3
        has_automation = (e3DPositionType != 0)

        if has_automation:
            ePathMode = stream.uint8_read() # U8x
            TransitionTime = stream.int32_read() # s32

            ulNumVertices = stream.uint32_read() # u32
            vertices: list[tuple[float, float, float, int]] = [
                (
                    stream.float_read(),
                    stream.float_read(),
                    stream.float_read(),
                    stream.int32_read()
                ) for _ in range(ulNumVertices)
            ]

            ulNumPlayListItem = stream.uint32_read() # u32
            playListItems: list[tuple[int, int]] = [
                (stream.uint32_read(), stream.uint32_read())
                for _ in range(ulNumPlayListItem)
            ]

            _3DAutomationParams: list[tuple[float, float, float]] = [
                (stream.float_read(), stream.float_read(), stream.float_read())
                for _ in range(ulNumPlayListItem)
            ]

    tail = stream.tell()

    stream.seek(head)

    return stream.read(tail - head)
