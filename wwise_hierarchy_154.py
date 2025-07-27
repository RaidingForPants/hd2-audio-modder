"""
Bank Version 140
"""

import copy
import uuid
from collections.abc import Callable
from typing import Union

from backend.db import SQLiteDatabase
from log import logger
from util import *
import wwise_hierarchy_140

HircType = {
    0x01: "State",
    0x02: "Sound",
    0x03: "Action",
    0x04: "Event",
    0x05: "Random/Sequence Container",
    0x06: "Switch Container",
    0x07: "Actor-Mixer",
    0x08: "Audio Bus",
    0x09: "Layer Container",
    0x0a: "Music Segment",
    0x0b: "Music Track",
    0x0c: "Music Switch",
    0x0d: "Music Random Sequence",
    0x0e: "Attenuation",
    0x0f: "Dialogue Event",
    0x10: "Fx Share Set",
    0x11: "Fx Custom",
    0x12: "Auxiliary Bus",
    0x13: "LFO",
    0x14: "Envelope",
    0x15: "Audio Device",
    0x16: "Time Mod",
}


class HircEntry:
    """
    Must Have:
    hierarchy_type - U8
    size - U32
    hierarchy_id - tid
    """
    
    import_values = ["misc"]
    import_objects = []
    
    def __init__(self):
        # Trasnlation of hierarchy binary data
        self.size: int = 0
        self.hierarchy_type: int = 0
        self.hierarchy_id: int = 0
        self.baseParam: BaseParam | None = None
        self.misc: bytearray = bytearray()
        self.unused_sections = []

        # Bookkeeping data - external from hierarchy binary data 
        self.soundbanks: list[WwiseBank] = [] # WwiseBank
        self.modified_children: int = 0
        self.modified: bool = False
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
      
    def get_base_param(self):
        """
        This interface is used for getting base parameter with exception raising
        """
        raise NotImplementedError("This interface is not implemented")

    def get_data(self):
        """
        Include header
        """
        return self.hierarchy_type.to_bytes(1, byteorder="little") + self.size.to_bytes(4, byteorder="little") + self.hierarchy_id.to_bytes(4, byteorder="little") + self.misc

    def get_parent_id(self):
        if self.baseParam != None:
            return self.baseParam.directParentID
        return None

    def reload_parent(self):
        try:
            self.parent = self.soundbanks[0].hierarchy.get_entry(self.get_parent_id())
            if self.get_id() == 434245467:
                print(self.parent)
        except KeyError:
            self.parent = None

    def has_modified_children(self):
        return self.modified_children != 0

    def import_entry(self, new_entry: 'HircEntry'):
        if (
            (self.modified and new_entry.get_data() != self.data_old)
            or
            (not self.modified and new_entry.get_data() != self.get_data())
        ):
            self.set_data(new_entry)
        
    def set_data(self, entry = None, **data):
        if self.soundbanks == []:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            for bank in self.soundbanks:
                bank.raise_modified()
        if entry:
            for value in self.import_values:
                try:
                    setattr(self, value, getattr(entry, value))
                except AttributeError:
                    pass
        else:
            for name, value in data.items():
                setattr(self, name, value)
        self.modified = True
        self.size = len(self.get_data())-5
        try:
            self.parent = self.soundbanks[0].hierarchy.get_entry(self.parent_id)
        except:
            self.parent = None

    def revert_modifications(self):
        if self.soundbanks == []:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        if self.modified:
            self.set_data(self.from_bytes(self.data_old))
            self.data_old = b""
            self.modified = False
            if self.parent:
                self.parent.lower_modified()
            for bank in self.soundbanks:
                bank.lower_modified()
        
    def get_id(self):
        return self.hierarchy_id
        
    def raise_modified(self):
        if self.soundbanks == []:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        self.modified_children+=1
        if self.parent:
            self.parent.raise_modified()
        
    def lower_modified(self):
        if self.soundbanks == []:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        self.modified_children-=1
        if self.parent:
            self.parent.lower_modified()
                      
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

class MusicSegment(HircEntry):
    
    import_values = ["parent_id", "tracks", "duration", "entry_marker", "exit_marker", "markers"]
    import_objects = ["base_params"]

    def __init__(self):
        super().__init__()
        self.tracks: list[int] = []
        self.duration = 0
        self.bit_flags = 0
        self.entry_marker = None
        self.exit_marker = None
        self.unused_sections = []
        self.markers = []
        self.modified = False
        self.parent_id = 0
        self.base_params: BaseParam = None
    
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        entry = MusicSegment()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
        entry.hierarchy_id = stream.uint32_read()
        entry.bit_flags = stream.uint8_read()
        entry.base_params = BaseParam.from_memory_stream(stream)
        entry.parent_id = entry.base_params.directParentID
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

    def get_parent_id(self):
        return self.parent_id
      
    def set_data(self, entry = None, **data):
        if self.soundbanks == []:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            for bank in self.soundbanks:
                bank.raise_modified()
        if entry:
            for value in self.import_values:
                try:
                    setattr(self, value, getattr(entry, value))
                except AttributeError:
                    pass
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
            self.parent = self.soundbanks[0].hierarchy.get_entry(self.parent_id)
            #potentially problematic, might need better way of getting the parent
        except:
            self.parent = None
        
    def get_data(self):
        return (
            b"".join([
                struct.pack("<BIIB", self.hierarchy_type, self.size, self.hierarchy_id, self.bit_flags),
                self.base_params.get_data(),
                len(self.tracks).to_bytes(4, byteorder="little"),
                b"".join([x.to_bytes(4, byteorder="little") for x in self.tracks]),
                self.unused_sections[0],
                self.unused_sections[1],
                struct.pack("<d", self.duration),
                len(self.markers).to_bytes(4, byteorder="little"),
                b"".join([b"".join([x[0].to_bytes(4, byteorder="little"), struct.pack("<d", x[1]), x[2]]) for x in self.markers])
            ])
        )

class ActionException:
    """
    ulID tid
    bIsBus U8x
    """

    def __init__(self):
        self.ulID: int = 0
        self.bIsBus: int = 0

    @staticmethod
    def from_memory_stream(s: MemoryStream):
        head = s.tell()

        a = ActionException()

        a.ulID = s.uint32_read()
        a.bIsBus = s.uint8_read()

        tail = s.tell()

        assert_equal("ActionExceptionList expect 5 bytes of data", 5, tail - head)

        return a

    def get_data(self):
        return self.ulID.to_bytes(4, byteorder="little", signed=False) + \
               self.bIsBus.to_bytes(1, byteorder="little", signed=False)


class Action(HircEntry):
    """
    ulActionType U16
    idExt tid
    idExt_4 U8x
    propBundle sizeof(PropBundle)
    rangePropBundle sizeof(RangedPropBundle)
    actionParamData sizeof(actionParamData)
    """

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle",
        "actionParamData"
    ]

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

        cls.parse_action_base(a, s)

        a.actionParamData = stream.read(a.size - (s.tell() - head))

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for Action {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    @staticmethod
    def parse_action_base(a: 'Action', s: MemoryStream):
        a.hierarchy_id = s.uint32_read()

        a.ulActionType = s.uint16_read()

        a.idExt = s.uint32_read()
        a.idExt_4 = s.uint8_read()

        a.propBundle = PropBundle.from_memory_stream(s)
        a.rangePropBundle = RangedPropBundle.from_memory_stream(s)

    def get_data(self):
        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for Action {self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def set_data(self, entry: Union['Action', None] = None, **data):
        assert len(self.soundbanks) > 0, f"No WwiseBank is attached to Action {self.hierarchy_id}"

        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            for bank in self.soundbanks:
                bank.raise_modified()
        if entry:
            for value in self.import_values:
                try:
                    setattr(self, value, getattr(entry, value))
                except AttributeError:
                    pass
        else:
            for name, value in data.items():
                setattr(self, name, value)

        self.modified = True
        self.update_size()

        hierarchy: WwiseHierarchy_154 = self.soundbanks[0].hierarchy
        parent_id = self.get_parent_id()
        if parent_id != None and hierarchy.has_entry(parent_id):
            self.parent = hierarchy.get_entry(parent_id)
        else:
            self.parent = None

    def _pack(self):
        data = self._pack_action_base()

        data += self.actionParamData

        return data

    def _pack_action_base(self):
        data = struct.pack(
            "<IHIB",
            self.hierarchy_id,
            self.ulActionType,
            self.idExt,
            self.idExt_4
        )

        data += self.propBundle.get_data()
        data += self.rangePropBundle.get_data()

        return data
        

class TrackInfoStruct:
    
    def __init__(self):
        self.track_id = self.source_id = self.cache_id = self.event_id = self.play_at = self.begin_trim_offset = self.end_trim_offset = self.source_duration = 0

    @classmethod
    def from_bytes(cls, bytes: bytes | bytearray):
        t = TrackInfoStruct()
        t.track_id, t.source_id, t.cache_id, t.event_id, t.play_at, t.begin_trim_offset, t.end_trim_offset, t.source_duration = struct.unpack("<IIIIdddd", bytes)
        return t

    def import_entry(self, track_info):
        try:
            self.track_id = track_info.track_id
        except AttributeError:
            pass
        try:
            self.source_id = track_info.source_id
        except AttributeError:
            pass
        try:
            self.cache_id = track_info.cache_id
        except AttributeError:
            pass
        try:
            self.event_id = track_info.event_id
        except AttributeError:
            pass
        try:
            self.play_at = track_info.play_at
        except AttributeError:
            pass
        try:
            self.begin_trim_offset = track_info.begin_trim_offset
        except AttributeError:
            pass
        try:
            self.end_trim_offset = track_info.end_trim_offset
        except AttributeError:
            pass
        try:
            self.source_duration = track_info.source_duration
        except AttributeError:
            pass
        
    def get_id(self):
        if self.source_id != 0:
            return self.source_id
        else:
            return self.event_id

    def get_data(self):
        return struct.pack("<IIIIdddd", self.track_id, self.source_id, self.cache_id, self.event_id, self.play_at, self.begin_trim_offset, self.end_trim_offset, self.source_duration)
            

class ClipAutomationStruct:
    
    def __init__(self):
        self.graph_points = []
        self.clip_index = self.auto_type = self.num_graph_points = 0
        
    @classmethod
    def from_memory_stream(cls, stream):
        s = ClipAutomationStruct()
        s.clip_index, s.auto_type, s.num_graph_points = struct.unpack("<III", stream.read(12))
        for _ in range(s.num_graph_points):
            s.graph_points.append(struct.unpack("<ffI", stream.read(12)))
        return s
            
    def get_data(self):
        return struct.pack("<III", self.clip_index, self.auto_type, self.num_graph_points) + b"".join([struct.pack("<ffI", point[0], point[1], point[2]) for point in self.graph_points])
        

class MusicTrack(HircEntry):

    #import_values = ["bit_flags", "parent_id", "clip_automations", "unk1", "unk2", "misc"]
    import_values = ["clip_automations"]

    def __init__(self):
        super().__init__()
        self.bit_flags = 0
        self.unused_sections = []
        self.clip_automations = []
        self.sources: list[BankSourceStruct] = []
        self.track_info: list[TrackInfoStruct] = []
        self.parent_id = 0
        self.unk1 =  bytearray()
        self.unk2 =  bytearray()
        self.base_params: BaseParam = None

    def set_data(self, entry = None, **data):
        if self.soundbanks == []:
            raise AssertionError(
                "No WwiseBank object is attached to this instance WwiseHierarchy"
            )

        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            for bank in self.soundbanks:
                bank.raise_modified()
        if entry:
            for value in self.import_values:
                try:
                    setattr(self, value, getattr(entry, value))
                except AttributeError:
                    pass
            for track in self.track_info:
                for t in entry.track_info:
                    # if track.track_id != 0 and track.track_id == t.track_id:
                    #    track.import_entry(t)
                    #    break
                    if track.source_id != 0 and track.source_id == t.source_id:
                        track.import_entry(t)
                        break
                    if track.event_id != 0 and track.event_id == t.event_id:
                        track.import_entry(t)
                        break
        else:
            for name, value in data.items():
                setattr(self, name, value)

        self.modified = True
        self.size = len(self.get_data())-5
        try:
            self.parent = self.soundbanks[0].hierarchy.get_entry(self.parent_id)
        except:
            self.parent = None

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        entry = MusicTrack()
        entry.hierarchy_type = stream.uint8_read()
        entry.size = stream.uint32_read()
        start_position = stream.tell()
        entry.hierarchy_id = stream.uint32_read()
        num_sources = stream.uint32_read()
        for _ in range(num_sources):
            source = BankSourceStruct.from_memory_stream(stream)
            entry.sources.append(source)
        entry.bit_flags = stream.uint8_read()
        num_track_info = stream.uint32_read()
        for _ in range(num_track_info):
            track = TrackInfoStruct.from_bytes(stream.read(48))
            entry.track_info.append(track)
        entry.unk1 = stream.read(4)
        num_clip_automations = stream.uint32_read()
        for _ in range(num_clip_automations):
            entry.clip_automations.append(ClipAutomationStruct.from_memory_stream(stream))
        entry.unk2 = stream.read(4)
        entry.override_bus_id = stream.uint32_read()
        entry.parent_id = stream.uint32_read()
        entry.misc = stream.read(entry.size - (stream.tell()-start_position))
        return entry
        
    def get_parent_id(self):
        return self.parent_id

    def get_data(self):
        b = b"".join([source.get_data() for source in self.sources])
        t = b"".join([track.get_data() for track in self.track_info])
        clips = b"".join([clip.get_data() for clip in self.clip_automations])
        payload = b + self.bit_flags.to_bytes(1, "little") + len(self.track_info).to_bytes(4, byteorder="little") + t + self.unk1 + len(self.clip_automations).to_bytes(4, byteorder="little") + clips + self.unk2 + self.override_bus_id.to_bytes(4, byteorder="little") + self.parent_id.to_bytes(4, byteorder="little") + self.misc
        self.size = 8 + len(payload)
        return struct.pack("<BIII", self.hierarchy_type, self.size, self.hierarchy_id, len(self.sources)) + payload

class ActionStop(Action):
    """
    fadeCurveBitVector U8x
    stopBitVector U8x
    ulExceptionListSize var (assume 8 bits, can be more)
    actionExceptionList ulExceptionListSize * size(ActionException)
    """

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle",
        "fadeCurveBitVector",
        "stopBitVector",
        "ulExceptionListSize",
        "actionExceptionList"
    ]
       
    def __init__(self):
        super().__init__()
        self.fadeCurveBitVector = 0
        self.stopBitVector = 0
        self.ulExceptionListSize = 0
        self.actionExceptionList: list[ActionException] = []

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = ActionStop()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        cls.parse_action_base(a, s)

        # Active Action Param
        a.fadeCurveBitVector = s.uint8_read()

        # Stop Action Specific Param
        a.stopBitVector = s.uint8_read()

        # Action Except Param
        a.ulExceptionListSize = s.uint8_read()

        a.actionExceptionList = [
            ActionException.from_memory_stream(s) for _ in range(a.ulExceptionListSize)
        ]

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for ActionStop {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    def get_data(self):
        assert_equal(
            f"Unique exception list size does not match up # of action exception "
            f"in the list for ActionStop {self.hierarchy_id}",
            self.ulExceptionListSize,
            self.actionExceptionList
        )

        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for ActionStop {self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = self._pack_action_base()

        data += struct.pack(
            "<BBB",
            self.fadeCurveBitVector,
            self.stopBitVector,
            self.ulExceptionListSize
        )

        for a in self.actionExceptionList:
            data += a.get_data()

        return data


class ActionPause(Action):
    """
    fadeCurveBitVector U8x
    pauseBitVector U8x
    ulExceptionListSize var (assume 8 bits, can be more)
    actionExceptionList ulExceptionListSize * size(ActionException)
    """

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle",
        "fadeCurveBitVector",
        "pauseBitVector",
        "ulExceptionListSize",
        "actionExceptionList"
    ]
        
    def __init__(self):
        super().__init__()
        self.fadeCurveBitVector = 0
        self.pauseBitVector = 0
        self.ulExceptionListSize = 0
        self.actionExceptionList: list[ActionException] = []

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = ActionPause()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        cls.parse_action_base(a, s)

        # Active Action Param
        a.fadeCurveBitVector = s.uint8_read()

        # Action Pause Specific Param
        a.pauseBitVector = s.uint8_read()

        # Action Except Param
        a.ulExceptionListSize = s.uint8_read()

        a.actionExceptionList = [
            ActionException.from_memory_stream(s) for _ in range(a.ulExceptionListSize)
        ]

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for ActionPause {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    def get_data(self):
        assert_equal(
            f"Unique exception list size does not match up # of action exception "
            f"in the list for ActionPause {self.hierarchy_id}",
            self.ulExceptionListSize,
            self.actionExceptionList
        )

        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for ActionPause {self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = self._pack_action_base()

        data += struct.pack(
            "<BBB",
            self.fadeCurveBitVector,
            self.pauseBitVector,
            self.ulExceptionListSize
        )

        for a in self.actionExceptionList:
            data += a.get_data()

        return data


class ActionResume(Action):
    """
    fadeCurveBitVector U8x
    resumeBitVector U8x
    ulExceptionListSize var (assume 8 bits, can be more)
    actionExceptionList ulExceptionListSize * size(ActionException)
    """

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle",
        "fadeCurveBitVector",
        "resumeBitVector",
        "ulExceptionListSize",
        "actionExceptionList"
    ]
        
    def __init__(self):
        super().__init__()
        self.fadeCurveBitVector = 0
        self.resumeBitVector = 0
        self.ulExceptionListSize = 0
        self.actionExceptionList: list[ActionException] = []

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = ActionResume()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        cls.parse_action_base(a, s)

        # Active Action Param
        a.fadeCurveBitVector = s.uint8_read()

        # Action Resume Specific Param
        a.resumeBitVector = s.uint8_read()

        # Action Except Param
        a.ulExceptionListSize = s.uint8_read()

        a.actionExceptionList = [
            ActionException.from_memory_stream(s) for _ in range(a.ulExceptionListSize)
        ]

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for ActionResume {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    def get_data(self):
        assert_equal(
            f"Unique exception list size does not match up # of action exception "
            f"in the list for ActionResume {self.hierarchy_id}",
            self.ulExceptionListSize,
            self.actionExceptionList
        )

        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for ActionResume {self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = self._pack_action_base()

        data += struct.pack(
            "<BBB",
            self.fadeCurveBitVector,
            self.resumeBitVector,
            self.ulExceptionListSize
        )

        for a in self.actionExceptionList:
            data += a.get_data()

        return data


class ActionPlay(Action):
    """
    fadeCurveBitVector U8x
    bankID tid
    """

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle",
        "fadeCurveBitVector",
        "bankID"
    ]

    def __init__(self):
        super().__init__()
        self.fadeCurveBitVector: int = 0
        self.bankID: int = 0

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = ActionPlay()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        cls.parse_action_base(a, s)

        # Active Action Param
        a.fadeCurveBitVector = s.uint8_read()

        # Bank ID
        a.bankID = s.uint32_read()

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for ActionPlay {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    def get_data(self):
        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for ActionPlay {self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = self._pack_action_base()

        data += struct.pack("<BI", self.fadeCurveBitVector, self.bankID)

        return data


class ActionPlayAndContinue(ActionPlay):

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle",
        "fadeCurveBitVector",
        "bankID"
    ]

    def __init__(self):
        super().__init__()


class ActionSetSimpleValue(Action):
    """
    fadeCurveBitVector U8x
    ulExceptionListSize var (assume 8 bits, can be more)
    actionExceptionList ulExceptionListSize * size(ActionException)
    """

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle",
        "fadeCurveBitVector",
        "ulExceptionListSize",
        "actionExceptionList"
    ]

    def __init__(self):
        super().__init__()
        self.fadeCurveBitVector: int = 0
        self.ulExceptionListSize = 0
        self.actionExceptionList: list[ActionException] = []

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = ActionSetSimpleValue()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        cls.parse_action_base(a, s)

        # Active Action Param
        a.fadeCurveBitVector = s.uint8_read()

        # Action Except Param
        a.ulExceptionListSize = s.uint8_read()

        a.actionExceptionList = [
            ActionException.from_memory_stream(s) for _ in range(a.ulExceptionListSize)
        ]

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for ActionSetSimpleValue "
            f"(type: {a.ulActionType}) {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    def get_data(self):
        assert_equal(
            f"Unique exception list size does not match up # of action exception "
            f"in the list for ActionSetSimpleValue (type: {self.ulActionType}) "
            f"{self.hierarchy_id}",
            self.ulExceptionListSize,
            self.actionExceptionList
        )

        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for ActionSetSimpleValue "
            f"(type: {self.ulActionType}) {self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = self._pack_action_base()

        data += struct.pack(
            "<BB", self.fadeCurveBitVector, self.ulExceptionListSize
        )

        for a in self.actionExceptionList:
            data += a.get_data()

        return data


class RandomModifier:
    """
    base f32
    min f32
    max f32
    """

    def __init__(self):
        self.base: float = 0
        self.min: float = 0
        self.max: float = 0

    @staticmethod
    def from_memory_stream(s: MemoryStream):
        r = RandomModifier()

        r.base = s.float_read()
        r.min = s.float_read()
        r.max = s.float_read()

        return r

    def get_data(self):
        return struct.pack("<fff", self.base, self.min, self.max)


class ActionSetProp(Action):
    """
    fadeCurveBitVector U8x
    eValueMeaning U8x
    randomModifier sizeof(RandomModifier)
    ulExceptionListSize var (assume 8 bits, can be more)
    actionExceptionList ulExceptionListSize * size(ActionException)
    """

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle",
        "fadeCurveBitVector",
        "eValueMeaning",
        "randomModifier",
        "ulExceptionListSize",
        "actionExceptionList"
    ]

    def __init__(self):
        super().__init__()
        self.fadeCurveBitVector: int = 0
        self.eValueMeaning: int = 0
        self.randomModifier: RandomModifier = RandomModifier()
        self.ulExceptionListSize = 0
        self.actionExceptionList: list[ActionException] = []

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = ActionSetProp()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        cls.parse_action_base(a, s)

        # Active Action Param
        a.fadeCurveBitVector = s.uint8_read()

        # ActionSetProp Specific
        a.eValueMeaning = s.uint8_read()
        a.randomModifier = RandomModifier.from_memory_stream(s)

        # Action Except Param
        a.ulExceptionListSize = s.uint8_read()

        a.actionExceptionList = [
            ActionException.from_memory_stream(s) for _ in range(a.ulExceptionListSize)
        ]

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for ActionSetProp {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    def get_data(self):
        assert_equal(
            f"Unique exception list size does not match up # of action exception "
            f"in the list for ActionSetProp {self.hierarchy_id}",
            self.ulExceptionListSize,
            len(self.actionExceptionList)
        )

        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for ActionSetProp "
            f"{self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = self._pack_action_base()

        data += struct.pack("<BB", self.fadeCurveBitVector, self.eValueMeaning)
        data += self.randomModifier.get_data()
        data += self.ulExceptionListSize.to_bytes(1, byteorder="little", signed=False)

        for a in self.actionExceptionList:
            data += a.get_data()

        return data


class ActionUseState(Action): 

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle"
    ]

    def __init__(self):
        super().__init__()

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = ActionUseState()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        cls.parse_action_base(a, s)

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for ActionUseState {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    def get_data(self):
        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for ActionUseState "
            f"{self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)
        
        return header + data

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        return self._pack_action_base()


class ActionSetState(Action):
    """
    ulStateGroupID tid
    ulTargetStateID tid
    """

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle"
        "ulStateGroupID",
        "ulTargetStateID"
    ]

    def __init__(self):
        super().__init__()
        self.ulStateGroupID: int = 0
        self.ulTargetStateID: int = 0

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = ActionSetState()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        cls.parse_action_base(a, s)

        a.ulStateGroupID = s.uint32_read()
        a.ulTargetStateID = s.uint32_read()

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for ActionSetState {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    def get_data(self):
        data = self._pack()
        
        assert_equal(
            f"Header size and packed data size mismatch for ActionSetState {self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = self._pack_action_base()

        data += struct.pack(
            "<II", self.ulStateGroupID, self.ulTargetStateID,
        )

        return data


class ActionSetSwitch(Action):
    """
    ulSwitchGroupID - tid
    ulSwitchStateID - tid
    """

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle",
        "fadeCurveBitVector",
        "ulSwitchGroupID",
        "ulSwitchStateID"
    ]

    def __init__(self):
        super().__init__()
        self.ulSwitchGroupID: int = 0
        self.ulSwitchStateID: int = 0

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = ActionSetSwitch()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        cls.parse_action_base(a, s)

        a.ulSwitchGroupID = s.uint32_read()
        a.ulSwitchStateID = s.uint32_read()

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for ActionSetSwitch {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    def get_data(self):
        data = self._pack()
        
        assert_equal(
            f"Header size and packed data size mismatch for ActionSetSwitch {self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = self._pack_action_base()

        data += struct.pack(
            "<II", self.ulSwitchGroupID, self.ulSwitchStateID,
        )

        return data


class ActionSeek(Action):
    """
    bIsSeekRelativeToDuration U8x
    randomModifier sizeof(RandomModifier)
    bSnapToNearestMarker U8x
    ulExceptionListSize var (assume 8 bits, can be more)
    actionExceptionList ulExceptionListSize * size(ActionException)
    """

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle",
        "bIsSeekRelativeToDuration",
        "randomModifier",
        "bSnapToNearestMarker",
        "ulExceptionListSize",
        "actionExceptionList"
    ]

    def __init__(self):
        super().__init__()
        self.bIsSeekRelativeToDuration: int = 0
        self.randomModifier = RandomModifier()
        self.bSnapToNearestMarker: int = 0
        self.ulExceptionListSize: int = 0
        self.actionExceptionList: list[ActionException] = []

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = ActionSeek()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        cls.parse_action_base(a, s)

        a.bIsSeekRelativeToDuration = s.uint8_read()

        a.randomModifier = RandomModifier.from_memory_stream(s)

        a.bSnapToNearestMarker = s.uint8_read()

        a.ulExceptionListSize = s.uint8_read()

        a.actionExceptionList = [
            ActionException.from_memory_stream(s) for _ in range(a.ulExceptionListSize)
        ]

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for ActionSeek {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    def get_data(self):
        assert_equal(
            f"Unique exception list size does not match up # of action exception "
            f"in the list for ActionSeek {self.hierarchy_id}",
            self.ulExceptionListSize,
            self.actionExceptionList
        )

        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for ActionSeek "
            f"{self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = self._pack_action_base()

        data += self.bIsSeekRelativeToDuration.to_bytes(1, byteorder="little", signed=False)

        data += self.randomModifier.get_data()

        data += self.bSnapToNearestMarker.to_bytes(1, byteorder="little", signed=False)

        data += self.ulExceptionListSize.to_bytes(1, byteorder="little", signed=False)

        for a in self.actionExceptionList:
            data += a.get_data()

        return data


class ActionResetPlaylist(Action):
    """
    fadeCurveBitVector U8x
    ulExceptionListSize var (assume 8 bits, can be more)
    actionExceptionList ulExceptionListSize * size(ActionException)
    """

    import_values = [
        "ulActionType",
        "idExt",
        "idExt_4",
        "propBundle",
        "rangePropBundle",
        "fadeCurveBitVector",
        "ulExceptionListSize",
        "actionExceptionList"
    ]
        
    def __init__(self):
        super().__init__()
        self.fadeCurveBitVector = 0
        self.ulExceptionListSize = 0
        self.actionExceptionList: list[ActionException] = []

    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        s = stream

        a = ActionResetPlaylist()

        a.hierarchy_type = s.uint8_read()
        a.size = s.uint32_read()

        head = s.tell()

        cls.parse_action_base(a, s)

        # Active Action Param
        a.fadeCurveBitVector = s.uint8_read()

        # Action Except Param
        a.ulExceptionListSize = s.uint8_read()

        a.actionExceptionList = [
            ActionException.from_memory_stream(s) for _ in range(a.ulExceptionListSize)
        ]

        tail = s.tell()

        assert_equal(
            f"Header size and read data size mismatch for ActionResetPlaylist {a.hierarchy_id}",
            a.size, tail - head
        )

        return a

    def get_data(self):
        assert_equal(
            f"Unique exception list size does not match up # of action exception "
            f"in the list for ActionResetPlaylist {self.hierarchy_id}",
            self.ulExceptionListSize,
            self.actionExceptionList
        )

        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for ActionResetPlaylist {self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        data = self._pack_action_base()

        data += struct.pack(
            "<BB",
            self.fadeCurveBitVector,
            self.ulExceptionListSize
        )

        for a in self.actionExceptionList:
            data += a.get_data()

        return data


def action_factory(t: int, s: MemoryStream) -> Action:
    match t:
        case 0x0100:
            return ActionStop.from_memory_stream(s)
        case 0x0200:
            return ActionPause.from_memory_stream(s)
        case 0x0300:
            return ActionResume.from_memory_stream(s)
        case 0x0400:
            return ActionPlay.from_memory_stream(s)
        case 0x0500:
            return ActionPlayAndContinue.from_memory_stream(s)
        case 0x0600 | 0x0700:
            return ActionSetSimpleValue.from_memory_stream(s)
        case t if 0x0800 <= t and t <= 0x0F00:
            return ActionSetProp.from_memory_stream(s)
        case 0x1000 | 0x1100:
            return ActionUseState.from_memory_stream(s)
        case 0x1200:
            return ActionSetState.from_memory_stream(s)
        case 0x1900:
            return ActionSetSwitch.from_memory_stream(s)
        case 0x1E00:
            return ActionSeek.from_memory_stream(s)
        case 0x2000:
            return ActionSetProp.from_memory_stream(s)
        case 0x2200:
            return ActionResetPlaylist.from_memory_stream(s)
        case 0x3000:
            return ActionSetProp.from_memory_stream(s)
        case _:
            return Action.from_memory_stream(s)


class Event(HircEntry):
    """
    ulActionListSize var (assume 8 bits, can be more)
    ulActionIDs[] tid[ulActionListSize]
    """

    import_values = [
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

        assert_equal(
            f"Header size and read data size mismatch for Event {e.hierarchy_id}",
            e.size, tail - head
        )

        return e

    def get_data(self):
        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for Event {self.hierarchy_id}",
            self.size,
            len(data)
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def set_data(self, entry: Union['Event', None] = None, **data):
        assert len(self.soundbanks) > 0, f"No WwiseBank is attached to Event {self.hierarchy_id}"

        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            for bank in self.soundbanks:
                bank.raise_modified()

        if entry:
            for value in self.import_values:
                try:
                    setattr(self, value, getattr(entry, value))
                except AttributeError:
                    pass
        else:
            for name, value in data.items():
                setattr(self, name, value)

        self.modified = True
        self.update_size()

        hierarchy: WwiseHierarchy_154 = self.soundbanks[0].hierarchy
        parent_id = self.get_parent_id()
        if parent_id != None and hierarchy.has_entry(parent_id):
            self.parent = hierarchy.get_entry(parent_id)
        else:
            self.parent = None

    def update_size(self):
        self.size = len(self._pack())

    def _pack(self):
        assert_equal(
            f"Action list size mismatch with # of unique action IDs in the list"
            f" for Event {self.hierarchy_id}",
            self.ulActionListSize,
            len(self.ulActionIDs)
        )

        data = struct.pack(
            "<IB",
            self.hierarchy_id,
            self.ulActionListSize
        )
        for _id in self.ulActionIDs:
            data += _id.to_bytes(4, "little")
        return data
        


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
        "baseParam",
        "children",
        "playListSetting",
        "ulPlayListItem",
        "playListItems",
    ]
    def __init__(self):
        super().__init__()
        self.children: ContainerChildren = ContainerChildren()
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
        cntr.children.numChildren = stream.uint32_read()
        for _ in range(cntr.children.numChildren):
            cntr.children.children.append(stream.uint32_read())

        # [PlayListItem]
        cntr.ulPlayListItem = stream.uint16_read()
        cntr.playListItems = [
            PlayListItem(stream.uint32_read(), stream.int32_read())
            for _ in range(cntr.ulPlayListItem)
        ]

        tail = stream.tell()

        assert_equal(
            f"Header size and read data size mismatch for RandomSequenceContainer {cntr.hierarchy_id}",
            cntr.size, tail - head
        )

        return cntr

    def get_base_param(self):
        if self.baseParam != None:
            return self.baseParam
        raise AssertionError(
            f"Random / Sequence container {self.hierarchy_id} does not have a "
             "base parameter."
        )

    def get_data(self):
        data = self._pack()
        assert_equal(
            f"Header size and packed data size mismatch for RandomSequenceContainer {self.hierarchy_id}",
            self.size, len(data) 
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data 

    def set_data(self, entry: Union['RandomSequenceContainer', None] = None, **data):
        assert len(self.soundbanks) > 0, f"No WwiseBank is attached to RandomSequenceContainer {self.hierarchy_id}"

        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            for bank in self.soundbanks:
                bank.raise_modified()

        if entry:
            for value in self.import_values:
                try:
                    setattr(self, value, getattr(entry, value))
                except AttributeError:
                    pass
        else:
            for name, value in data.items():
                setattr(self, name, value)

        self.modified = True
        self.update_size()

        hierarchy: WwiseHierarchy_154 = self.soundbanks[0].hierarchy
        parent_id = self.get_parent_id()
        if parent_id != None and hierarchy.has_entry(parent_id):
            self.parent = hierarchy.get_entry(parent_id)
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

        data += self.children.get_data()

        assert_equal(
            "# of playlist item mismatch # of item in the playlist item array",
            self.ulPlayListItem,
            len(self.playListItems)
        )

        data += struct.pack("<H", self.ulPlayListItem)
        for playListItem in self.playListItems:
            data += playListItem.get_data()

        return data
         
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
        self.cache_id: int = 0

        # For some reason, it still work although it's not being updated
        self.mem_size: int = 0 

        self.bit_flags: int = 0
        self.plugin_size: int = 0
        self.plugin_data: bytearray = bytearray()
        
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        b = BankSourceStruct()
        b.plugin_id, b.stream_type, b.source_id, b.cache_id, b.mem_size, b.bit_flags = \
            struct.unpack("<IBIIIB", stream.read(18))
        if (b.plugin_id & 0x0F) == 2:
            if b.plugin_id:
                b.plugin_size = stream.uint32_read()
                if b.plugin_size > 0:
                    b.plugin_data = stream.read(b.plugin_size)
        return b
        
    def get_data(self):
        b = struct.pack(
            "<IBIIIB",
            self.plugin_id,
            self.stream_type,
            self.source_id,
            self.cache_id,
            self.mem_size,
            self.bit_flags
        )
        if (self.plugin_id & 0X0F) == 2:
            if self.plugin_id:
                b += struct.pack(f"<I", self.plugin_size)
                if self.plugin_size > 0:
                    assert_equal(
                        "Plugin size mismatch size of plugin data",
                        self.plugin_size,
                        len(self.plugin_data)
                    )
                    b += struct.pack(f"<{len(self.plugin_data)}s", self.plugin_data)
        return b
            
    
class Sound(HircEntry):
    
    import_values = [
        "sources",
        "baseParam",
    ]
    
    def __init__(self):
        super().__init__()
        self.sources: list[BankSourceStruct] = []
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

        assert_equal(
            f"Header size and read data size mismatch for Sound {sound.hierarchy_id}",
            sound.size, tail - head
        )

        return sound

    def get_base_param(self):
        if self.baseParam != None:
            return self.baseParam
        raise AssertionError(
            f"Sound container {self.hierarchy_id} does not have a "
             "base parameter."
        )

    def get_data(self):
        data = self._pack()
        assert_equal(
            f"Header size and packed data size mismatch for Sound {self.hierarchy_id}",
            self.size, len(data) 
        )
        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def set_data(self, entry: Union['Sound', None] = None, **data):
        assert len(self.soundbanks) > 0, f"No WwiseBank is attached to Sound {self.hierarchy_id}"
        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            for bank in self.soundbanks:
                bank.raise_modified()

        if entry:
            for value in self.import_values:
                try:
                    setattr(self, value, getattr(entry, value))
                except AttributeError:
                    pass
        else:
            for name, value in data.items():
                setattr(self, name, value)

        self.modified = True
        self.update_size()

        hierarchy: WwiseHierarchy_154 = self.soundbanks[0].hierarchy
        parent_id = self.get_parent_id()
        if parent_id != None and hierarchy.has_entry(parent_id):
            self.parent = hierarchy.get_entry(parent_id)
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
        match hierarchy_type:
            case 0x02: # sound
                entry = Sound.from_memory_stream(stream)
            case 0x03:
                stream.advance(1 + 4 + 4)
                action_type: int = stream.uint16_read()
                stream.seek(stream.tell() - 2 - 1 - 4 - 4)
                entry = action_factory(action_type, stream)
            case 0x04:
                entry = Event.from_memory_stream(stream)
            case 0x05:
                entry = RandomSequenceContainer.from_memory_stream(stream)
            case 0x06:
                entry = SwitchContainer.from_memory_stream(stream)
            case 0x07:
                entry = ActorMixer.from_memory_stream(stream)
            case 0x09:
                entry = LayerContainer.from_memory_stream(stream)
            case 0x0A: # music segment
                entry = MusicSegment.from_memory_stream(stream)
            case 0x0B: # music track
                entry = MusicTrack.from_memory_stream(stream)
            case 0x0C:
                entry = MusicSwitchContainer.from_memory_stream(stream)
            case _:
                entry = HircEntry.from_memory_stream(stream)
        return entry
            
class WwiseHierarchy_154:
    
    def __init__(self, soundbank = None):
        self.entries: dict[int, HircEntry] = {}

        self.actions: list[Action] = []
        self.actor_mixers: list[ActorMixer] = []
        self.events: list[Event] = []
        self.layer_container: list[LayerContainer] = []
        self.music_segments: list[MusicSegment] = []
        self.music_tracks: list[MusicTrack] = []
        self.random_sequence_containers: list[RandomSequenceContainer] = []
        self.sounds: list[Sound] = []
        self.switch_containers: list[SwitchContainer] = []
        self.music_switch_containers: list[MusicSwitchContainer] = []
        self.uncategorized: list[HircEntry] = []

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
            entry.soundbanks.append(self.soundbank)
            self.entries[entry.get_id()] = entry

            self._categorized_entry(entry)

        for entry in self.get_entries():
            parent_id = entry.get_parent_id()
            if parent_id != None and parent_id in self.entries:
                entry.parent = self.entries[parent_id]
                
    def import_hierarchy(self, new_hierarchy: 'WwiseHierarchy_154'):
        for entry in new_hierarchy.get_entries():
            if isinstance(entry, (wwise_hierarchy_140.MusicSegment, wwise_hierarchy_140.MusicTrack, MusicSegment, MusicTrack)):
                if entry.hierarchy_id in self.entries:
                    self.entries[entry.hierarchy_id].import_entry(entry)
                #else:
                #    self.add_entry(entry)
                
    def revert_modifications(self, entry_id: int = 0):
        assert_not_none(f"No WwiseBank is attached to entry {self.soundbank}", self.soundbank)

        if entry_id:
            self.get_entry(entry_id).revert_modifications()
        else:
            for entry in self.removed_entries:
                self.entries[entry.hierarchy_id] = entry
                self.soundbank.lower_modified() # type: ignore
                self._categorized_entry(entry)
            self.removed_entries.clear()
            for entry in self.added_entries.copy().values():
                self.remove_entry(entry)
                self.soundbank.lower_modified() # type: ignore
            for entry in self.get_entries():
                entry.revert_modifications()
                
    def add_entry(self, new_entry: HircEntry):
        assert_not_none(f"No WwiseBank is attached to entry {self.soundbank}", self.soundbank)

        self.soundbank.raise_modified() # type: ignore
        self.added_entries[new_entry.hierarchy_id] = new_entry
        self.entries[new_entry.hierarchy_id] = new_entry
        self._categorized_entry(new_entry)
        new_entry.soundbanks.append(self.soundbank)
            
    def remove_entry(self, entry: HircEntry):
        assert_not_none(f"No WwiseBank is attached to entry {self.soundbank}", self.soundbank)

        if entry.hierarchy_id in self.entries:
            if entry.hierarchy_id in self.added_entries:
                del self.added_entries[entry.hierarchy_id]
                self.soundbank.lower_modified() # type: ignore
            else:
                self.removed_entries[entry.hierarchy_id] = entry
                self.soundbank.raise_modified() # type: ignore

            self._remove_categorized_entry(entry)
            
            del self.entries[entry.hierarchy_id]
            entry.soundbanks.remove(self.soundbank)
    
    def has_entry(self, entry_id: int):
        return entry_id in self.entries
            
    def get_entry(self, entry_id: int):
        return self.entries[entry_id]

    def get_actions(self):
        return self.actions

    def get_actor_mixers(self):
        return self.actor_mixers

    def get_actor_mixer_by_id(self, _id: int):
        entry = self.entries[_id]
        if not isinstance(entry, ActorMixer):
            raise AssertionError(
                f"Hierarchy entry {_id} is not an actor mixer"
            )
        return entry

    def get_events(self):
        return self.events

    def get_layer_containers(self):
        return self.layer_container

    def get_layer_container_by_id(self, _id: int):
        entry = self.entries[_id]
        if not isinstance(entry, LayerContainer):
            raise AssertionError(
                f"Hierarchy entry {_id} is not an layer container"
            )
        return entry

    def get_music_segment(self):
        return self.music_segments

    def get_music_tracks(self):
        return self.music_tracks

    def get_random_sequence_containers(self):
        return self.random_sequence_containers

    def get_rand_seq_cntr_by_id(self, _id: int):
        entry = self.entries[_id]
        if not isinstance(entry, RandomSequenceContainer):
            raise AssertionError(
                f"Hierarchy entry {_id} is not a random / sequence container."
            )
        return entry

    def get_sounds(self):
        return self.sounds

    def get_sound_by_id(self, _id: int):
        entry = self.entries[_id]
        if not isinstance(entry, Sound):
            raise AssertionError(
                f"Hierarchy entry {_id} is not a Sound."
            )
        return entry

    def get_switches_container(self):
        return self.switch_containers
        
    def get_music_switch_containers(self):
        return self.music_switch_containers

    def get_entries(self):
        return self.entries.values()
        
    def get_data(self):
        old_child_lists = {}
        old_size = {}
        for mixer in self.get_actor_mixers() + self.get_switches_container() + self.get_random_sequence_containers() + self.get_layer_containers() + self.get_music_switch_containers():
            old_child_lists[mixer.hierarchy_id] = mixer.children
            old_size[mixer.hierarchy_id] = mixer.size
            new_child_list = copy.deepcopy(mixer.children)
            old_num_children = new_child_list.numChildren
            new_list = []
            for child in new_child_list.children:
                if child in self.entries.keys():
                    new_list.append(child)
            new_child_list.children = new_list
            new_child_list.numChildren = len(new_list)
            mixer.children = new_child_list
            mixer.size = mixer.size - 4*old_num_children + 4*new_child_list.numChildren
            
        arr = [entry.get_data() for entry in self.entries.values()]
        
        for mixer in self.get_actor_mixers() + self.get_switches_container() + self.get_random_sequence_containers() + self.get_layer_containers() + self.get_music_switch_containers():
            mixer.children = old_child_lists[mixer.hierarchy_id]
            mixer.size = old_size[mixer.hierarchy_id]
        
        return len(arr).to_bytes(4, byteorder="little") + b"".join(arr)

    def _categorized_entry(self, entry: HircEntry):
        match entry.hierarchy_type:
            case 0x02:
                assert(isinstance(entry, Sound))
                self.sounds.append(entry)
            case 0x03:
                assert(isinstance(entry, Action))
                self.actions.append(entry)
            case 0x04:
                assert(isinstance(entry, Event))
                self.events.append(entry)
            case 0x05:
                assert(isinstance(entry, RandomSequenceContainer))
                self.random_sequence_containers.append(entry)
            case 0x06:
                assert(isinstance(entry, SwitchContainer))
                self.switch_containers.append(entry)
            case 0x07:
                assert(isinstance(entry, ActorMixer))
                self.actor_mixers.append(entry)
            case 0x09:
                assert(isinstance(entry, LayerContainer))
                self.layer_container.append(entry)
            case 0x0A:
                assert(isinstance(entry, MusicSegment))
                self.music_segments.append(entry)
            case 0x0B:
                assert(isinstance(entry, MusicTrack))
                self.music_tracks.append(entry)
            case 0x0C:
                assert(isinstance(entry, MusicSwitchContainer))
                self.music_switch_containers.append(entry)
            case _:
                self.uncategorized.append(entry)

    def _remove_categorized_entry(self, entry: HircEntry):
        match entry.hierarchy_type:
            case 0x02:
                assert(isinstance(entry, Sound))
                self.sounds.remove(entry)
            case 0x03:
                assert(isinstance(entry, Action))
                self.actions.remove(entry)
            case 0x04:
                assert(isinstance(entry, Event))
                self.events.remove(entry)
            case 0x05:
                assert(isinstance(entry, RandomSequenceContainer))
                self.random_sequence_containers.remove(entry)
            case 0x06:
                assert(isinstance(entry, SwitchContainer))
                self.switch_containers.remove(entry)
            case 0x07:
                assert(isinstance(entry, ActorMixer))
                self.actor_mixers.remove(entry)
            case 0x09:
                assert(isinstance(entry, LayerContainer))
                self.layer_container.remove(entry)
            case 0x0A:
                assert(isinstance(entry, MusicSegment))
                self.music_segments.remove(entry)
            case 0x0B:
                assert(isinstance(entry, MusicTrack))
                self.music_tracks.remove(entry)
            case 0x0C:
                assert(isinstance(entry, MusicSwitchContainer))
                self.music_switch_containers.remove(entry)
            case _:
                self.uncategorized.remove(entry)

class FxChunk:
    """
    uFxIndex - U8i
    fxId - tid
    bIsShareSet - U8x
    bIsRendered - U8x
    """

    def __init__(
        self, uFxIndex: int, fxId: int, bitVector: int
    ):
        self.uFxIndex: int = uFxIndex # U8i
        self.fxId: int = fxId # tid
        self.bitVector: int = bitVector # U8x

    def get_data(self):
        return struct.pack(
            "<BIB", self.uFxIndex, self.fxId, self.bitVector
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
        assert_equal("# of props != # of prop. IDs", self.cProps, len(self.pIDs))
        assert_equal("# of props != # of prop. values", self.cProps, len(self.pValues))
        assert_equal("# of prop. IDs != # of prop. values", len(self.pIDs), len(self.pValues))

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
        assert_equal("# of props != # of prop. IDs", self.cProps, len(self.pIDs))
        assert_equal("# of props != # of prop. values", self.cProps, len(self.pValues))
        assert_equal("# of prop. IDs != # of prop. values", len(self.pIDs), len(self.pValues))
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
        assert_equal("# of props != # of prop. IDs", self.cProps, len(self.pIDs))
        assert_equal("# of props != # of prop. values", self.cProps, len(self.rangedValues))
        assert_equal("# of prop. IDs != # of prop. values", len(self.pIDs), len(self.rangedValues))
    
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
        assert_equal("# of props != # of prop. IDs", self.cProps, len(self.pIDs))
        assert_equal("# of props != # of prop. values", self.cProps, len(self.rangedValues))
        assert_equal("# of prop. IDs != # of prop. values", len(self.pIDs), len(self.rangedValues))
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
    propertyId var (assume 8 bits, can be more)
    accumType U8x
    inDb bool U8x 
    """

    def __init__(self, propertyId: int = 0, accumType: int = 0, inDb: int = 0):
        self.propertyId = propertyId
        self.accumType = accumType
        self.inDb = inDb

    def to_bytes(self):
        return struct.pack("<3B", self.propertyId, self.accumType, self.inDb)

class AkPropBundle:
    def __init__(self, pID: int, pValue: float):
        self.pID = pID
        self.pValue = pValue

    def get_data(self):
        return struct.pack("<Hf", self.pID, self.pValue)

class StateGroupState:
    """
    ulStateID tid
    cProps u16
    pProps AkPropBundle[]
    """

    def __init__(self, ulStateID: int = 0, cProps: int = 0, pProps: list[AkPropBundle] = []):
       self.ulStateID = ulStateID
       self.cProps = cProps
       self.pProps = pProps

    def get_data(self):
        b = struct.pack("<IH", self.ulStateID, self.cProps)
        for pProp in self.pProps:
            b += pProp.get_data()
        return b


class StateGroup:
    """
    ulStateGroupID tid
    eStateSyncType U8x
    states StateGroupState[]
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
        assert_equal(
            "# of states != # of states in the array",
            self.ulNumStates,
            len(self.states)
        )

    def get_data(self):
        assert_equal(
            "# of states != # of states in the array",
            self.ulNumStates,
            len(self.states)
        )
        b = struct.pack(
            "<IBB", self.ulStateGroupID, self.eStateSyncType, self.ulNumStates
        )
        for state in self.states:
            b += state.get_data()
        return b


class StateParams:
    """
    ulNumStatesProps var (assume 8 bits, can be more)
    stateProps ulNumStateProps * sizeof(StateProp)
    ulNumStateGroups var (assume 8 bits, can be more)
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
        assert_equal(
            "# of state props != # of state props in the array",
            self.ulNumStateProps,
            len(self.stateProps)
        )
        assert_equal(
            "# of state groups != # of state groups in the array",
            self.ulNumStateGroups,
            len(self.stateGroups)
        )

    def get_data(self):
        assert_equal(
            "# of state props != # of state props in the array",
            self.ulNumStateProps,
            len(self.stateProps)
        )
        assert_equal(
            "# of state groups != # of state groups in the array",
            self.ulNumStateGroups,
            len(self.stateGroups)
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
    paramID var (assume 8 bits, can be more)
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
        assert_equal(
            "# RTPC graph pts != # of RTPC graph ptr in the aray",
            self.ulSize,
            len(self.rtpcGraphPoints)
        )

    def get_data(self):
        assert_equal(
            "# RTPC graph pts != # of RTPC graph ptr in the aray",
            self.ulSize,
            len(self.rtpcGraphPoints)
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
        self.bBypassAll = 0
        self.fxChunks: list[FxChunk] = []

        self.bIsOverrideParentMetadata: int = 0
        self.uNumFxMetadata: int = 0
        self.fxChunksMetadata: list[FxChunkMetadata] = []

        self.overrideBusId: int = 0
        self.directParentID: int = 0
        self.byBitVectorA: int = 0

        self.propBundle = PropBundle()

        self.positioningParamData: bytearray = bytearray()

        self.rangePropBundle = RangedPropBundle()

        self.auxParams = AuxParams()

        self.advSetting = AdvSetting()

        self.stateParams = StateParams()

        self.uNumCurves: int = 0
        self.rtpcs: list[RTPC] = []

    def import_entry(self, param):
        pass

    @staticmethod
    def from_memory_stream(stream: MemoryStream):
        # [Fx]
        baseParam = BaseParam()

        baseParam.bIsOverrideParentFx = stream.uint8_read()
        baseParam.uNumFx = stream.uint8_read()
        if baseParam.uNumFx > 0:
            baseParam.bPypassAll = stream.uint8_read()
            baseParam.fxChunks = [
                FxChunk(
                    stream.uint8_read(),
                    stream.uint32_read(),
                    stream.uint8_read(),
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
            states: list[StateGroupState] = []
            for _ in range(ulNumStates):
                ulStateID = stream.uint32_read()
                cProps = stream.uint16_read()
                pProps = [
                    AkPropBundle(stream.uint16_read(), stream.float_read())
                    for _ in range(cProps)
                ]
                states.append(StateGroupState(ulStateID, cProps, pProps))
            stateGroups.append(StateGroup(
                ulStateGroupID,
                eStateSyncType,
                ulNumStates,
                states
            ))
        baseParam.stateParams.stateGroups = stateGroups

        # [RTPC No Modulator]
        baseParam.uNumCurves = stream.uint16_read()
        rtpcs: list[RTPC] = []
        for _ in range(baseParam.uNumCurves):
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
        assert_equal(
            "# of FX != # of FX in the array",
            self.uNumFx, len(self.fxChunks)
        )
        if self.uNumFx > 0:
            b += struct.pack("<B", self.bBypassAll)
            for fxChunk in self.fxChunks:
                b += fxChunk.get_data()

        # [Metadata Fx]
        assert_equal(
            "# of metadata FX != # of metadata FX in the array",
            self.uNumFxMetadata, len(self.fxChunksMetadata)
        )

        b += struct.pack("<BB", self.bIsOverrideParentMetadata, self.uNumFxMetadata)
        if self.uNumFxMetadata > 0:
            for fxChunkMetadata in self.fxChunksMetadata:
                b += fxChunkMetadata.to_bytes()

        b += struct.pack(
            "<IIB",
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

        b += struct.pack("<H", self.uNumCurves)
        assert_equal(
            "# of RTPC != # of RTPC in the array",
            self.uNumCurves, len(self.rtpcs)
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
        assert_equal(
            "# of children != # of children in the array",
            self.numChildren,
            len(self.children)
        )
        b = struct.pack("<I", self.numChildren)
        for child in self.children:
            b += struct.pack("<I", child)
        assert_equal(
            "Packed data does not have the correct data size",
            4 + 4 * self.numChildren,
            len(b),
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

        assert_equal(
            f"Header size and read data size mismatch for LayerContainer {l.hierarchy_id}",
            l.size, tail - head
        )

        return l

    def get_base_param(self):
        if self.baseParam != None:
            return self.baseParam
        raise AssertionError(
            f"Layer container {self.hierarchy_id} does not have a "
            "base parameter."
        )

    def get_data(self):
        data = self._pack() 

        assert_equal(
            f"Header size and packed data size mismatch for LayerContainer {self.hierarchy_id}",
            self.size, len(data) 
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def set_data(self, entry: Union['LayerContainer', None] = None, **data):
        assert len(self.soundbanks) > 0, f"No WwiseBank is attached to LayerContainer {self.hierarchy_id}"

        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            for bank in self.soundbanks:
                bank.raise_modified()

        if entry:
            for value in self.import_values:
                try:
                    setattr(self, value, getattr(entry, value))
                except AttributeError:
                    pass
        else:
            for name, value in data.items():
                setattr(self, name, value)

        self.modified = True
        self.update_size()

        hierarchy: WwiseHierarchy_154 = self.soundbanks[0].hierarchy
        parent_id = self.get_parent_id()
        if parent_id != None and hierarchy.has_entry(parent_id):
            self.parent = hierarchy.get_entry(parent_id)
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

        assert_equal(
            f"Header size and read data size mismatch for ActorMixer {mixer.hierarchy_id}",
            mixer.size, tail - head
        )

        return mixer

    def update_size(self):
        self.size = len(self._pack())

    def get_base_param(self):
        if self.baseParam != None:
            return self.baseParam
        raise AssertionError(
            f"ActorMixer {self.hierarchy_id} does not have a base parameter."
        )

    def get_data(self):
        data = self._pack()
        assert_equal(
            f"Header size and packed data size mismatch for ActorMixer {self.hierarchy_id}",
            self.size, len(data) 
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)

        return header + data

    def set_data(self, entry: Union['ActorMixer', None] = None, **data):
        assert len(self.soundbanks) > 0, f"No WwiseBank is attached to Actor-Mixer {self.hierarchy_id}"

        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            for bank in self.soundbanks:
                bank.raise_modified()

        if entry:
            for value in self.import_values:
                try:
                    setattr(self, value, getattr(entry, value))
                except AttributeError:
                    pass
        else:
            for name, value in data.items():
                setattr(self, name, value)

        self.modified = True
        self.update_size()

        hierarchy: WwiseHierarchy_154 = self.soundbanks[0].hierarchy
        parent_id = self.get_parent_id()
        if parent_id != None and hierarchy.has_entry(parent_id):
            self.parent = hierarchy.get_entry(parent_id)
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

        assert_equal(
            "# of SwitchGroup nodes mismatch # of SwitchGroup nodes in the list",
            group.ulNumItems,
            len(group.nodeList)
        )

        return group

    def get_data(self):
        b = struct.pack("<II", self.ulSwitchID, self.ulNumItems)
        for nodeId in self.nodeList:
            b += struct.pack("<I", nodeId)
        assert_equal(
            "Packed SwitchGroup data does not have the correct data size!",
            len(b),
            4 + 4 + 4 * self.ulNumItems
        )
        return b


class SwitchParam:
    """
    ulNodeID tid
    byBitVector U8x
    fadeOutTime s32
    fadeInTime s32
    """

    def __init__(self):
        self.ulNodeID: int = 0
        self.byBitVector: int = 0
        self.fadeOutTime: int = 0
        self.fadeInTime: int = 0

    @staticmethod
    def from_memory_stream(stream: MemoryStream):
        param = SwitchParam()

        param.ulNodeID = stream.uint32_read()
        param.byBitVector = stream.uint8_read()
        param.fadeOutTime = stream.int32_read()
        param.fadeInTime = stream.int32_read()

        return param

    def get_data(self):
        b = struct.pack(
            "<IBii",
            self.ulNodeID,
            self.byBitVector,
            self.fadeOutTime,
            self.fadeInTime
        )
        assert_equal(
            "Packed SwitchParam data does not have the correct data size!",
            len(b),
            4 + 1 + 4 + 4
        )
        return b
        
        
class MusicSwitchContainer(HircEntry):
    
    import_values = [
        "unused_sections",
        "children",
        "baseParam"
    ]
    
    def __init__(self):
        super().__init__()
        self.baseParam: BaseParam | None = None
        self.children: ContainerChildren = ContainerChildren()
        self.unused_sections = []
        
    @classmethod
    def from_memory_stream(cls, stream: MemoryStream):
        c = MusicSwitchContainer()
        
        c.hierarchy_type = stream.uint8_read()
        c.size = stream.uint32_read()
        
        start = stream.tell()
        
        c.hierarchy_id = stream.uint32_read()
        
        c.unused_sections.append(stream.read(1))
        
        c.baseParam = BaseParam.from_memory_stream(stream)
        
        # [Children]
        c.children.numChildren = stream.uint32_read()
        c.children.children = [
            stream.uint32_read() for _ in range(c.children.numChildren)
        ]
        
        c.unused_sections.append(stream.read(c.size-(stream.tell()-start)))
        
        return c
        
    def get_parent_id(self):
        if self.baseParam != None:
            return self.baseParam.directParentID
        return None
        
    def get_data(self):
        return b"".join([
            struct.pack("<BII", self.hierarchy_type, self.size, self.hierarchy_id),
            self.unused_sections[0],
            self.baseParam.get_data(),
            self.children.get_data(),
            self.unused_sections[1]
        ])
    


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

        assert_equal(
            f"Header size and read data size mismatch for SwitchContainer {s.hierarchy_id}",
            s.size, tail - head
        )

        return s

    def get_base_param(self):
        if self.baseParam != None:
            return self.baseParam
        raise AssertionError(
            f"SwitchContainer {self.hierarchy_id} does not have a base parameter."
        )

    def get_data(self):
        data = self._pack()

        assert_equal(
            f"Header size and packed data size mismatch for SwitchContainer {self.hierarchy_id}",
            self.size, len(data) 
        )

        header = struct.pack("<BI", self.hierarchy_type, self.size)
        return header + data

    def set_data(self, entry: Union['SwitchContainer', None] = None, **data):
        assert len(self.soundbanks) > 0, f"No WwiseBank is attached to SwitchContainer {self.hierarchy_id}"

        if not self.modified:
            self.data_old = self.get_data()
            if self.parent:
                self.parent.raise_modified()
            for bank in self.soundbanks:
                bank.raise_modified()

        if entry:
            for value in self.import_values:
                try:
                    setattr(self, value, getattr(entry, value))
                except AttributeError:
                    pass
        else:
            for name, value in data.items():
                setattr(self, name, value)

        self.modified = True
        self.update_size()

        hierarchy: WwiseHierarchy_154 = self.soundbanks[0].hierarchy
        parent_id = self.get_parent_id()
        if parent_id != None and hierarchy.has_entry(parent_id):
            self.parent = hierarchy.get_entry(parent_id)
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

        assert_equal(
            "# of unique SwitchGroup mismatch # of SwitchGroup in the list",
            self.ulNumSwitchGroups,
            len(self.switchGroups)
        )

        for switchGroup in self.switchGroups:
            data += switchGroup.get_data()

        data += struct.pack("<I", self.ulNumSwitchParams)

        assert_equal(
            "# of SwitchParameter counter mismatch # of SwitchParameter in the "
            "list",
            self.ulNumSwitchParams,
            len(self.switchParms)
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
        uBits3d = stream.uint8_read() # U8x type: ignore
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
