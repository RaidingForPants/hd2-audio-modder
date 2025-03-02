import struct
import uuid

from collections.abc import Callable
from typing import Union

from backend.db import SQLiteDatabase
from log import logger
from util import *


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

    def import_entry(self, new_entry):
        if (
            (self.modified and new_entry.get_data() != self.data_old)
            or
            (not self.modified and new_entry.get_data() != self.get_data())
        ):
            self.set_data(new_entry)
        
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

        hierarchy: WwiseHierarchy = self.soundbank.hierarchy
        if hierarchy.has_entry(self.parent_id):
            self.parent = hierarchy.get_entry(self.parent_id)
        else:
            self.parent = None

    def get_data(self):
        """
        Include header
        """
        return self.hierarchy_type.to_bytes(1, byteorder="little") + self.size.to_bytes(4, byteorder="little") + self.hierarchy_id.to_bytes(4, byteorder="little") + self.misc
        
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

    def raise_modified(self):
        if self.soundbank == None:
            raise AssertionError(
                "No WwiseBank object is attached to this instance wiseHierarchy"
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

    def update_size(self):
        """
        Interface contract and usage:
        - Must call this after modifying an hierarhcy object
        - Otherwise, get_data will most likely fail due to assertion
        """
        raise NotImplementedError("This interface is not implemented!")

    def modifier(self, callback: Callable):
        """
        A helper function that receive and call a callback which make some 
        changes in a hierarchy entry. Then it will automatically call 
        `update_size` and `raise_modified`.

        This helper function is intended to use with the classes that enforce 
        size and intergity checking using header information when getting / 
        setting data.
        """
        callback()
        self.update_size()
        self.raise_modified()
        
    def get_id(self):
        return self.hierarchy_id


class Action(HircEntry):
    """
    ulActionType U16
    idExt tid
    idExt_4 U8x
    """

    def __init__(self):
        super().__init__()

        self.ulActionType = 0
        self.idExt = 0
        self.idExt_4 = 0
        self.propBundle: PropBundle = PropBundle()
        self.rangePropBundle: RangedPropBundle = RangedPropBundle()
        self.actionParamData: bytearray = bytearray()

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = Action()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        a.hierarchy_id = s.uint32_read()

        a.ulActionType = s.uint16_read()

        a.idExt = s.uint32_read()
        a.idExt_4 = s.uint8_read()

        a.propBundle = PropBundle.from_memory_stream(s)
        a.rangePropBundle = RangedPropBundle.from_memory_stream(s)

        a.actionParamData = stream.read(a.size - (s.tell() - head))

        tail = s.tell()

        if a.size != (tail - head):
            raise AssertionError(
                f"Action {a.hierarchy_id} header size != read data size"
            )

        return a

    def get_data(self):
        data = self._pack()

        if self.size != len(data):
            raise AssertionError(
                f"Action {self.hierarchy_id} header size != packed data size"
            )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def _pack(self):
        data = struct.pack(
            "<IHIB",
            self.hierarchy_id,
            self.ulActionType,
            self.idExt,
            self.idExt_4
        )

        data += self.propBundle.get_data()
        data += self.rangePropBundle.get_data()

        data += self.actionParamData

        return data


class Event(HircEntry):
    """
    ulActionListSize var
    ulActionIDs[] tid[ulActionListSize]
    """

    import_values = [
        "parent_id",
        "ulActionListSize",
        "ulActionIDs"
    ]

    def __init__(self):
        super().__init__()
        self.ulActionListSize: int = 0
        self.ulActionIDs: list[int] = []

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        e = Event()

        e.hierarchy_type = s.uint8_read()

        e.size = s.uint32_read()

        head = s.tell()

        e.hierarchy_id = s.uint32_read()

        e.ulActionListSize = s.uint8_read()

        e.ulActionIDs = [s.uint32_read() for _ in range(e.ulActionListSize)]

        tail = s.tell()

        if e.size != (tail - head):
            raise AssertionError(
                f"Event {e.hierarchy_id} header size != read data size"
            )

        return e

    def get_data(self):
        data = self._pack()

        if self.size != len(data):
            raise AssertionError(
                f"Event {self.hierarchy_id} header size != packed data size"
            )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def set_data(self, entry: Union['Event', None] = None, **data):
        if self.soundbank == None:
            raise AssertionError(
                f"No WwiseBank object is attached to Event {self.hierarchy_id}"
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
        self.update_size()

        hierarchy: WwiseHierarchy = self.soundbank.hierarchy
        if hierarchy.has_entry(self.parent_id):
            self.parent = hierarchy.get_entry(self.parent_id)
        else:
            self.parent = None

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        if self.ulActionListSize != len(self.ulActionIDs):
            raise AssertionError(
                f"Event {self.hierarchy_id} action list size != # of ul action"
                 "IDs in the list."
            )
        data = struct.pack(
            "<IB",
            self.hierarchy_id,
            self.ulActionListSize
        )
        for _id in self.ulActionIDs:
            data += _id.to_bytes(4, "little")
        return data
        
        
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
    import_values = [
        "parent_id",
        "baseParam",
        "children",
        "containerChildren",
        "playListSetting",
        "ulPlayListItem",
        "playListItems",
    ]
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
            raise AssertionError(
                f"Random Sequence container {cntr.hierarchy_id} assertion break: "
                f"data size specified in header != data size from read data"
            )

        return cntr

    def get_data(self):
        data = self._pack()
        if self.size != len(data):
            raise AssertionError(
                f"Random Sequence container {self.hierarchy_id} assertion break: "
                f"data size specified in header != data size from packed data"
            )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data 

    def set_data(self, entry: Union['RandomSequenceContainer', None] = None, **data):
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
        self.update_size()

        hierarchy: WwiseHierarchy = self.soundbank.hierarchy
        if hierarchy.has_entry(self.parent_id):
            self.parent = hierarchy.get_entry(self.parent_id)
        else:
            self.parent = None

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = struct.pack("<I", self.hierarchy_id)

        if self.baseParam == None:
            raise AssertionError(
                f"Random Sequence container {self.hierarchy_id} does not has a "
                 "base parameter."
            )
        data += self.baseParam.get_data()

        data += self.playListSetting.get_data()

        data += self.containerChildren.get_data()

        if self.ulPlayListItem != len(self.playListItems):
            raise AssertionError(
                f"Random Sequence container {self.hierarchy_id} assertion break: "
                f" # of playlist item != # of item in the playlist item in the "
                f" array"
            )
        data += struct.pack("<H", self.ulPlayListItem)
        for playListItem in self.playListItems:
            data += playListItem.get_data()

        return data
    

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

        hierarchy: WwiseHierarchy = self.soundbank.hierarchy
        if hierarchy.has_entry(self.parent_id):
            self.parent = hierarchy.get_entry(self.parent_id)
        else:
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

        # For some reason, it still work although it's not being updated
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
                            "plugin size != size of plugin data"
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
    
    import_values = [
        "sources",
        "parent_id",
        "baseParam",
    ]
    
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
            raise AssertionError(
                f"Sound {sound.hierarchy_id} assertion break: "
                 "data size specified in header != data size from read data"
            )

        return sound

    def get_data(self):
        data = self._pack()
        if self.size != len(data):
            raise AssertionError(
                f"Sound {self.hierarchy_id} assertion break: "
                f"data size specified in header != data size from packed data"
            )
        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def set_data(self, entry: Union['Sound', None] = None, **data):
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
        self.update_size()

        hierarchy: WwiseHierarchy = self.soundbank.hierarchy
        if hierarchy.has_entry(self.parent_id):
            self.parent = hierarchy.get_entry(self.parent_id)
        else:
            self.parent = None

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = struct.pack("<I", self.hierarchy_id)
        data += self.sources[0].get_data()
        if self.baseParam == None:
            raise AssertionError(
                f"Sound {self.hierarchy_id} does not has a base parameter."
            )
        data += self.baseParam.get_data()

        return data
        
        
class HircEntryFactory:
    
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        hierarchy_type = stream.uint8_read()
        stream.seek(stream.tell()-1)
        if hierarchy_type == 0x02: # sound
            return Sound.from_memory_stream(stream)
        elif hierarchy_type == 0x03:
            return Action.from_memory_stream(stream)
        elif hierarchy_type == 0x04:
            if os.environ["TEST_EVENT"] == "1":
                return Event.from_memory_stream(stream)
            else:
                return Event.from_memory_stream(stream)
        elif hierarchy_type == 0x05: # random / sequence container
            return RandomSequenceContainer.from_memory_stream(stream)
        elif hierarchy_type == 0x06:
            return SwitchContainer.from_memory_stream(stream)
        elif hierarchy_type == 0x07:
            return ActorMixer.from_memory_stream(stream)
        elif hierarchy_type == 0x09:
            return LayerContainer.from_memory_stream(stream)
        elif hierarchy_type == 0x0A: # music segment
            return MusicSegment.from_memory_stream(stream)
        elif hierarchy_type == 0X0B: # music track
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
    
    def has_entry(self, entry_id: int):
        return entry_id in self.entries
            
    def get_entry(self, entry_id: int):
        return self.entries[entry_id]

    def get_actor_mixer_by_id(self, _id: int):
        entry = self.entries[_id]
        if not isinstance(entry, ActorMixer):
            raise AssertionError(
                f"Hierarchy entry {_id} is not an actor mixer"
            )
        return entry

    def get_layer_container_by_id(self, _id: int):
        entry = self.entries[_id]
        if not isinstance(entry, LayerContainer):
            raise AssertionError(
                f"Hierarchy entry {_id} is not an layer container"
            )
        return entry

    def get_rand_seq_cntr_by_id(self, _id: int):
        entry = self.entries[_id]
        if not isinstance(entry, RandomSequenceContainer):
            raise AssertionError(
                f"Hierarchy entry {_id} is not a random / sequence container."
            )
        return entry

    def get_sound_by_id(self, _id: int):
        entry = self.entries[_id]
        if not isinstance(entry, Sound):
            raise AssertionError(
                f"Hierarchy entry {_id} is not a Sound."
            )
        return entry
        
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
            raise AssertionError(
                "# of props specified != # of props stored"
            )

    @staticmethod
    def from_memory_stream(s: MemoryStream):
        p = PropBundle()
        p.cProps = s.uint8_read()
        p.pIDs = [
            s.uint8_read() for _ in range(p.cProps)
        ]
        p.pValues = [
            s.read(4) for _ in range(p.cProps)
        ]
        return p

    def assert_prop_count(self, prop_count):
        if self.cProps != prop_count:
            raise AssertionError(
                f"There are {self.cProps} properties but expected value is "
                f"{prop_count}."
            )
        if len(self.pIDs) != prop_count:
            raise AssertionError(
                f"There are {len(self.pIDs)} property IDs but expected value is "
                f"{prop_count}."
            )
        if len(self.pValues) != prop_count:
            raise AssertionError(
                f"There are {len(self.pValues)} property values but expected "
                f"value is {prop_count}."
            )

    def assert_prop_id(self, pos: int, prop_id: int):
        if self.pIDs[pos] != prop_id:
            raise AssertionError(
                f"Expect property ID at position {pos} but receive "
                f"{self.pIDs[pos]}!"
            )

    def set_prop_value_float_by_pid(self, pID: int, new_value: float):
        pIDs = self.pIDs
        pValues = self.pValues

        for i, _pID in enumerate(pIDs):
            if _pID == pID:
                pValues[i] = bytearray(struct.pack("<f", new_value))
                return

        raise ValueError(
            f"Property ID {pID} does not exist. Please use add_prop_value_float to "
             "add a new property!"
        )

    def add_prop_value_float(self, new_pid: int, new_value: float):
        if self.cProps == 0 or self.pIDs[-1] < new_pid:
            self.pIDs.append(new_pid)
            self.pValues.append(bytearray(struct.pack("<f", new_value)))
            self.cProps += 1 
            if len(self.pIDs) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property IDs."
                )
            if len(self.pValues) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property values."
                )
            if len(self.pIDs) != len(self.pValues):
                raise AssertionError(
                    "# of property IDs does not match up # of property values."
                )
            return

        if self.cProps > 0 and self.pIDs[0] > new_pid:
            self.pIDs.insert(0, new_pid)
            self.pValues.insert(0, bytearray(struct.pack("<f", new_value)))
            self.cProps += 1
            if len(self.pIDs) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property IDs."
                )
            if len(self.pValues) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property values."
                )
            if len(self.pIDs) != len(self.pValues):
                raise AssertionError(
                    "# of property IDs does not match up # of property values."
                )
            return

        l = self.cProps
        pIDs = self.pIDs
        pValues = self.pValues
        for i in range(l):
            if pIDs[l - i - 1] > new_pid:
                continue

            if pIDs[l - i - 1] == new_pid:
                raise AssertionError(
                    f"Property with ID {new_pid} already exists. Please use "
                    "`set_prop_value_float_by_pid instead to set this property!"
                )

            pIDs.insert(l - i, new_pid)
            pValues.insert(l - i, bytearray(struct.pack("<f", new_value)))
            self.cProps += 1

            if len(self.pIDs) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property IDs."
                )
            if len(self.pValues) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property values."
                )
            if len(self.pIDs) != len(self.pValues):
                raise AssertionError(
                    "# of property IDs does not match up # of property values."
                )
            return

        raise AssertionError("Assertion failed. Reached invalid code path.")

    def get_data(self):
        if self.cProps != len(self.pIDs) != len(self.pValues):
            raise AssertionError(
                "# of props specified != # of props stored"
            )
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
            raise AssertionError(
                "# of range props specified != # of range props stored"
            )
    
    @staticmethod
    def from_memory_stream(s: MemoryStream):
        r = RangedPropBundle()
        r.cProps = s.uint8_read()
        r.pIDs = [
            s.uint8_read() for _ in range(r.cProps)
        ]
        r.rangedValues = [
            (s.float_read(), s.float_read()) 
            for _ in range(r.cProps)
        ]
        return r


    def assert_range_prop_count(self, prop_count: int):
        if self.cProps != prop_count:
            raise AssertionError(
                f"There are {self.cProps} properties but expected value is "
                f"{prop_count}."
            )
        if len(self.pIDs) != prop_count:
            raise AssertionError(
                f"There are has {self.pIDs} property IDs but expected value is "
                f"{prop_count}."
            )
        if len(self.rangedValues) != prop_count:
            raise AssertionError(
                f"There are {len(self.rangedValues)} property values but "
                f"expected value is {prop_count}."
            )
    
    def assert_range_prop_id(self, pos: int, prop_id: int):
        if self.pIDs[pos] != prop_id:
            raise AssertionError(
                f"Expect property ID at position {pos} but receive "
                f"{self.pIDs[pos]}!"
            )

    def set_range_prop_value_by_pid(
        self, pID: int, new_values: tuple[float, float]
    ):
        pIDs = self.pIDs
        rangeValues = self.rangedValues

        for i, _pID in enumerate(pIDs):
            if _pID == pID:
                rangeValues[i] = (new_values[0], new_values[1])
                return

        raise ValueError(
            f"Property ID {pID} does not exist. Please use add_range_prop_value to "
             "add a new property!"
        )

    def add_range_prop_value(
        self, new_pid: int, new_values: tuple[float, float]
    ):
        if new_pid < 0:
            raise ValueError(f"Invalid property ID {new_pid}!")

        if self.cProps == 0 or self.pIDs[-1] < new_pid:
            self.pIDs.append(new_pid)
            self.rangedValues.append((new_values[0], new_values[1]))
            self.cProps += 1
            if len(self.pIDs) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property IDs."
                )
            if len(self.rangedValues) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property values."
                )
            if len(self.pIDs) != len(self.rangedValues):
                raise AssertionError(
                    "# of property IDs does not match up # of property values."
                )
            return

        if self.cProps > 0 and self.pIDs[0] > new_pid:
            self.pIDs.insert(0, new_pid)
            self.rangedValues.insert(0, (new_values[0], new_values[1]))
            self.cProps += 1
            if len(self.pIDs) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property IDs."
                )
            if len(self.rangedValues) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property values."
                )
            if len(self.pIDs) != len(self.rangedValues):
                raise AssertionError(
                    "# of property IDs does not match up # of property values."
                )
            return

        l = self.cProps
        pIDs = self.pIDs
        rangeValues = self.rangedValues
        for i in range(l):
            if pIDs[l - i - 1] > new_pid:
                continue
            if pIDs[l - i - 1] == new_pid:
                raise AssertionError(
                    f"Property with ID {new_pid} already exists. Please use "
                     "`set_prop_value_float_by_pid instead to set this property!"
                )
            pIDs.insert(l - i, new_pid)
            rangeValues.insert(l - i, (new_values[0], new_values[1]))
            self.cProps += 1
            if len(self.pIDs) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property IDs."
                )
            if len(self.rangedValues) != self.cProps:
                raise AssertionError(
                    "Property counter does not match up # of property values."
                )
            if len(self.pIDs) != len(self.rangedValues):
                raise AssertionError(
                    "# of property IDs does not match up # of property values."
                )

        raise AssertionError(f"Provided property ID {new_pid} cannot be added.")

    def get_data(self):
        if self.cProps != len(self.pIDs) != len(self.rangedValues):
            raise AssertionError(
                "# of range props specified != # of range props stored"
            )
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
            raise AssertionError("Has No Aux but # of Aux Bus IDs > 0")
        if self.has_aux and len(auxIDs) != 4:
            raise AssertionError("Has Aux but # of Aux Bus IDs != 4")

    def get_data(self):
        if not self.has_aux and len(self.auxIDs) > 0:
            raise AssertionError("Has No Aux but # of Aux Bus IDs > 0")
        if self.has_aux and len(self.auxIDs) != 4:
            raise AssertionError("Has Aux and # of Aux Bus IDs != 4")
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
            raise AssertionError(
                "# of states specified in state group != # of states stored in state group"
            )

    def get_data(self):
        if self.ulNumStates != len(self.states):
            raise AssertionError(
                "# of states specified in state group != # of states stored in state group"
            )
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
                "# of state props sepcified != # of state props stored"
            )
        if self.ulNumStateGroups != len(self.stateGroups):
            raise AssertionError(
                "# of state groups specified != # of state groups stored"
            )

    def get_data(self):
        if self.ulNumStateProps != len(self.stateProps):
            raise AssertionError(
                "# of state props sepcified != # of state props stored"
            )
        if self.ulNumStateGroups != len(self.stateGroups):
            raise AssertionError(
                "# of state groups specified != # of state groups stored"
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
            raise AssertionError(
                "# of RTPC graph points specified != # of RTPC graph points stored"
            )

    def get_data(self):
        if self.ulSize != len(self.rtpcGraphPoints):
            raise AssertionError(
                "# of RTPC graph points specified != # of RTPC graph points stored"
            )
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
        baseParam.propBundle = PropBundle.from_memory_stream(stream)

        # [Range Based Properties - No Modulator]
        baseParam.rangePropBundle = RangedPropBundle.from_memory_stream(stream)

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
            raise AssertionError(
                "# of FX specified != # of FX stored"
            )
        if self.uNumFx > 0:
            b += struct.pack("<B", self.bitsFxBypass)
            for fxChunk in self.fxChunks:
                b += fxChunk.get_data()

        # [Metadata Fx]
        if self.uNumFxMetadata != len(self.fxChunksMetadata):
            raise AssertionError(
                "# of metadata FX specified != # of metadata FX stored"
            )
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
            raise AssertionError(
                "# of RTPC sepcified != # of RTPC stored"
            )
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
                "# of children specified != # of children stored"
            )
        b = struct.pack("<I", self.numChildren)
        for child in self.children:
            b += struct.pack("<I", child)
        if len(b) != 4 + 4 * self.numChildren:
            raise AssertionError(
                "Container children packed data does not have the correct data"
                " size."
            )
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
        return struct.pack("<Ii", self.ulPlayID, self.weight)


class LayerContainer(HircEntry):
    """
    ulNumLayers u32
    """

    import_values = [
        "parent_id",
        "baseParam",
        "children",
        "ulNumLayers",
        "layerData"
    ]

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
            raise AssertionError(
                f"Layer container {l.hierarchy_id} assertion break: "
                f"data size specified in header != data size from read data"
            )

        return l

    def get_data(self):
        data = self._pack() 

        if self.size != len(data):
            raise AssertionError(
                f"Layer container {self.hierarchy_id} assertion break: "
                f"data size specified in header != data size from packed data"
            )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def set_data(self, entry: Union['LayerContainer', None] = None, **data):
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
        self.update_size()

        hierarchy: WwiseHierarchy = self.soundbank.hierarchy
        if hierarchy.has_entry(self.parent_id):
            self.parent = hierarchy.get_entry(self.parent_id)
        else:
            self.parent = None

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = struct.pack("<I", self.hierarchy_id)
        
        if self.baseParam == None:
            raise AssertionError(
                f"Layer container {self.hierarchy_id} does not has a base parameter."
            )
        data += self.baseParam.get_data()

        data += self.children.get_data()

        data += struct.pack(f"<{len(self.layerData)}s", self.layerData)

        return data


class ActorMixer(HircEntry):

    import_values = [
        "parent_id",
        "baseParam",
        "children"
    ]

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
            raise AssertionError(
                f"ActorMixer {mixer.hierarchy_id} assertion break: "
                f"data size specified in header != data size from packed data"
            )

        return mixer

    def update_size(self):
        self.size = len(self._pack())

    def get_data(self):
        data = self._pack()
        if self.size != len(data):
            raise AssertionError(
                f"ActorMixer {self.hierarchy_id} assertion break: "
                f"data size specified in header != data size from packed data"
            )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def set_data(self, entry: Union['ActorMixer', None] = None, **data):
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
        self.update_size()

        hierarchy: WwiseHierarchy = self.soundbank.hierarchy
        if hierarchy.has_entry(self.parent_id):
            self.parent = hierarchy.get_entry(self.parent_id)
        else:
            self.parent = None

    def _pack(self):
        data = struct.pack("<I", self.hierarchy_id)

        if self.baseParam == None:
            raise AssertionError(
                f"ActorMixer {self.hierarchy_id} does not has a base parameter."
            )

        data += self.baseParam.get_data()
        
        data += self.children.get_data()

        return data


class SwitchGroup:
    """
    ulSwitchID sid
    ulNumItems u32
    nodeList[ulNumItems] tid[]
    """

    def __init__(self):
        self.ulSwitchID: int = 0
        self.ulNumItems: int = 0
        self.nodeList: list[int] = []

    @staticmethod
    def from_memory_stream(stream: MemoryStream):
        group = SwitchGroup()

        group.ulSwitchID = stream.uint32_read()
        group.ulNumItems = stream.uint32_read()
        group.nodeList = [stream.uint32_read() for _ in range(group.ulNumItems)]

        if group.ulNumItems != len(group.nodeList):
            raise AssertionError(
                "Switch group node items counter does not equal to # of items "
                "in the node list."
            )

        return group

    def get_data(self):
        b = struct.pack("<II", self.ulSwitchID, self.ulNumItems)
        for nodeId in self.nodeList:
            b += struct.pack("<I", nodeId)
        if len(b) != 4 + 4 + 4 * self.ulNumItems:
            raise AssertionError(
                "Packed switch group data does not have the correct data size!"
            )
        return b


class SwitchParam:
    """
    ulNodeID tid
    byBitVectorPlayBack U8x
    byBitVectorMode U8x
    fadeOutTime s32
    fadeInTime s32
    """

    def __init__(self):
        self.ulNodeID: int = 0
        self.byBitVectorPlayBack: int = 0
        self.byBitVectorMode: int = 0
        self.fadeOutTime: int = 0
        self.fadeInTime: int = 0

    @staticmethod
    def from_memory_stream(stream: MemoryStream):
        param = SwitchParam()

        param.ulNodeID = stream.uint32_read()
        param.byBitVectorPlayBack = stream.uint8_read()
        param.byBitVectorMode = stream.uint8_read()
        param.fadeOutTime = stream.int32_read()
        param.fadeInTime = stream.int32_read()

        return param

    def get_data(self):
        b = struct.pack(
            "<IBBii",
            self.ulNodeID,
            self.byBitVectorPlayBack,
            self.byBitVectorMode,
            self.fadeOutTime,
            self.fadeInTime
        )
        if len(b) != 4 + 1 + 1 + 4 + 4:
            raise AssertionError(
                "Packed switch param data does not have correct data size!"
            )
        return b


class SwitchContainer(HircEntry):
    """
    baseParam BaseParam
    eGroupType U8x
    ulGroupID tid
    ulDefaultSwitch tid
    bIsContinuousValidation U8x
    children ContainerChildren
    ulNumSwitchGroups u32
    switchGroups[ulNumSwitchGroups] SwitchGroup[]
    ulNumSwitchParams u32
    switchParams[ulNumSwitchParams] SwitchParam[]
    """

    import_values = [
        "parent_id",
        "baseParam",
        "eGroupType",
        "ulGroupID",
        "ulDefaultSwitch",
        "bIsContinuousValidation",
        "children",
        "ulNumSwitchGroups",
        "switchGroups",
        "ulNumSwitchParams",
        "switchParams"
    ]

    def __init__(self):
        super().__init__()
        self.baseParam: BaseParam | None = None
        self.eGroupType: int = 0
        self.ulGroupID: int = 0
        self.ulDefaultSwitch: int = 0
        self.bIsContinuousValidation: int = 0
        self.children: ContainerChildren = ContainerChildren()
        self.ulNumSwitchGroups: int = 0
        self.switchGroups: list[SwitchGroup] = []
        self.ulNumSwitchParams: int = 0
        self.switchParms: list[SwitchParam] = []
        
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = SwitchContainer()

        s.hierarchy_type = stream.uint8_read()

        s.size = stream.uint32_read()

        head = stream.tell()

        s.hierarchy_id = stream.uint32_read()

        s.baseParam = BaseParam.from_memory_stream(stream)

        s.eGroupType = stream.uint8_read()
        s.ulGroupID = stream.uint32_read()
        s.ulDefaultSwitch = stream.uint32_read()
        s.bIsContinuousValidation = stream.uint8_read()

        # [Children]
        s.children.numChildren = stream.uint32_read()
        s.children.children = [
            stream.uint32_read() for _ in range(s.children.numChildren)
        ]

        # [Switch Container specific parameter]
        s.ulNumSwitchGroups = stream.uint32_read()
        s.switchGroups = [
            SwitchGroup.from_memory_stream(stream) for _ in range(s.ulNumSwitchGroups)
        ]
        s.ulNumSwitchParams = stream.uint32_read()
        s.switchParms = [
            SwitchParam.from_memory_stream(stream) for _ in range(s.ulNumSwitchParams)
        ]

        tail = stream.tell()

        if s.size != (tail - head):
            raise AssertionError(
                f"Switch container {s.hierarchy_id} assertion break: "
                f"data size specified in header != data size from read data"
            )
        
        return s

    def get_data(self):
        data = self._pack()

        if self.size != len(data):
            raise AssertionError(
                f"Switch container {self.hierarchy_id} assertion break: "
                f"data size specified in header != data size from packed data"
            )

        header = struct.pack("<BI", self.hierarchy_type, self.size)
        return header + data

    def set_data(self, entry: Union['SwitchContainer', None] = None, **data):
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
        self.update_size()

        hierarchy: WwiseHierarchy = self.soundbank.hierarchy
        if hierarchy.has_entry(self.parent_id):
            self.parent = hierarchy.get_entry(self.parent_id)
        else:
            self.parent = None


    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = struct.pack("<I", self.hierarchy_id)
        
        if self.baseParam == None:
            raise AssertionError(
                "Switch container {self.hierarchy_id} does not has a base "
                "parameter."
            )

        data += self.baseParam.get_data()

        data += struct.pack(
            "<BIIB", 
            self.eGroupType,
            self.ulGroupID,
            self.ulDefaultSwitch,
            self.bIsContinuousValidation
        )

        data += self.children.get_data()

        data += struct.pack("<I", self.ulNumSwitchGroups)

        if self.ulNumSwitchGroups != len(self.switchGroups):
            raise AssertionError(
                "Unique switch group counter does not match up # of switch group"
                " in the list"
            )

        for switchGroup in self.switchGroups:
            data += switchGroup.get_data()

        data += struct.pack("<I", self.ulNumSwitchParams)

        if self.ulNumSwitchParams != len(self.switchParms):
            raise AssertionError(
                "Unique switch parameter counter does not match up # of swith "
                "parameter in the list."
            )

        for switchParam in self.switchParms:
            data += switchParam.get_data()

        return data


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


def ak_media_id(db: SQLiteDatabase, retry: int = 32):
    if retry <= 0:
        raise ValueError(f"Invalid retry value: {retry}")
    for _ in range(retry):
        h = fnv_30(uuid.uuid4().bytes)
        if not db.has_audio_source_id(h):
            return h
        logger.info(
            f"{h} media ID is already used. Retrying "
            f"(# of retry remains: {retry})..."
        )
    raise KeyError("Failed to generate media ID. Please try to generate again!")
