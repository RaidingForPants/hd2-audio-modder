from tkinter import *
from tkinter import ttk
from tkinter import filedialog
import os
import struct
from math import ceil
from pathlib import Path
import tkinter
from tkinter.filedialog import askdirectory
from tkinter.filedialog import askopenfilename
from functools import partial
import pyaudio
import wave
import subprocess
import atexit
from itertools import takewhile
import copy
import numpy
import platform

MUSIC_TRACK = 11
SOUND = 2
BANK = 0
PREFETCH_STREAM = 1
STREAM = 2
ROW_HEIGHT = 30
ROW_WIDTH = 800
SUBROW_INDENT = 30
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 720
_GAME_FILE_LOCATION = ""
_DRIVE_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

def LookForSteamInstallWindows():
    path = "C:\\Program Files (x86)\\steam\\steamapps\\common\\Helldivers 2\\data"
    if os.path.exists(path):
        return path
    for letter in _DRIVE_LETTERS:
        path = f"{letter}:\\SteamLibrary\\steamapps\\common\\Helldivers 2\\data"
        if os.path.exists(path):
            return path
    return ""
    
def StripPatchIndex(filename):
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
    def __init__(self, Data=b"", IOMode = "read"):
        self.Location = 0
        self.Data = bytearray(Data)
        self.IOMode = IOMode
        self.Endian = "<"

    def open(self, Data, IOMode = "read"): # Open Stream
        self.Data = bytearray(Data)
        self.IOMode = IOMode

    def SetReadMode(self):
        self.IOMode = "read"

    def SetWriteMode(self):
        self.IOMode = "write"

    def IsReading(self):
        return self.IOMode == "read"

    def IsWriting(self):
        return self.IOMode == "write"

    def seek(self, Location): # Go To Position In Stream
        self.Location = Location
        if self.Location > len(self.Data):
            missing_bytes = self.Location - len(self.Data)
            self.Data += bytearray(missing_bytes)

    def tell(self): # Get Position In Stream
        return self.Location

    def read(self, length=-1): # Read Bytes From Stream
        if length == -1:
            length = len(self.Data) - self.Location
        if self.Location + length > len(self.Data):
            raise Exception("reading past end of stream")

        newData = self.Data[self.Location:self.Location+length]
        self.Location += length
        return bytearray(newData)

    def write(self, bytes): # Write Bytes To Stream
        length = len(bytes)
        if self.Location + length > len(self.Data):
            missing_bytes = (self.Location + length) - len(self.Data)
            self.Data += bytearray(missing_bytes)
        self.Data[self.Location:self.Location+length] = bytearray(bytes)
        self.Location += length

    def read_format(self, format, size):
        format = self.Endian+format
        return struct.unpack(format, self.read(size))[0]
        
    def bytes(self, value, size = -1):
        if size == -1:
            size = len(value)
        if len(value) != size:
            value = bytearray(size)

        if self.IsReading():
            return bytearray(self.read(size))
        elif self.IsWriting():
            self.write(value)
            return bytearray(value)
        return value
        
    def int8Read(self):
        return self.read_format('b', 1)

    def uint8Read(self):
        return self.read_format('B', 1)

    def int16Read(self):
        return self.read_format('h', 2)

    def uint16Read(self):
        return self.read_format('H', 2)

    def int32Read(self):
        return self.read_format('i', 4)

    def uint32Read(self):
        return self.read_format('I', 4)

    def int64Read(self):
        return self.read_format('q', 8)

    def uint64Read(self):
        return self.read_format('Q', 8)
        
def PadTo16ByteAlign(data):
    b = bytearray(data)
    l = len(b)
    new_len = ceil(l/16)*16
    return b + bytearray(new_len-l)
    
def _16ByteAlign(addr):
    return ceil(addr/16)*16
    
def bytes_to_long(bytes):
    assert len(bytes) == 8
    return sum((b << (k * 8) for k, b in enumerate(bytes)))

def murmur64Hash(data, seed = 0):

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
        
    def Update(self, content):
        pass
        
    def RaiseModified(self):
        pass
        
    def LowerModified(self):
        pass
    
class AudioSource:

    def __init__(self):
        self.Data = b""
        self.Size = 0
        self.resourceId = 0
        self.shortId = 0
        self.Modified = False
        self.Data_OLD = b""
        self.Subscribers = set()
        self.streamType = 0
        
    def SetData(self, data, notifySubscribers=True, setModified=True):
        if not self.Modified and setModified:
            self.Data_OLD = self.Data
        self.Data = data
        self.Size = len(self.Data)
        if notifySubscribers:
            for item in self.Subscribers:
                item.Update(self)
                if not self.Modified:
                    item.RaiseModified()
        if setModified:
            self.Modified = True
            
    def GetFileID(self): #for backwards compatibility
        if self.streamType == BANK:
            return self.GetShortId()
        else:
            return self.GetResourceId()
        
    def GetData(self):
        return self.Data
        
    def GetResourceId(self):
        return self.resourceId
        
    def GetShortId(self):
        return self.shortId
        
    def RevertModifications(self, notifySubscribers=True):
        if self.Modified:
            self.Modified = False
            self.Data = self.Data_OLD
            self.Data_OLD = b""
            self.Size = len(self.Data)
            if notifySubscribers:
                for item in self.Subscribers:
                    item.LowerModified()
                    item.Update(self)
                
class TocHeader:

    def __init__(self):
        pass
        
    def FromMemoryStream(self, stream):
        self.FileID             = stream.uint64Read()
        self.TypeID             = stream.uint64Read()
        self.TocDataOffset      = stream.uint64Read()
        self.StreamOffset       = stream.uint64Read()
        self.GpuResourceOffset  = stream.uint64Read()
        self.Unknown1           = stream.uint64Read() #seems to contain duplicate entry index
        self.Unknown2           = stream.uint64Read()
        self.TocDataSize        = stream.uint32Read()
        self.StreamSize         = stream.uint32Read()
        self.GpuResourceSize    = stream.uint32Read()
        self.Unknown3           = stream.uint32Read()
        self.Unknown4           = stream.uint32Read()
        self.EntryIndex         = stream.uint32Read()
        
    def GetData(self):
        return (struct.pack("<QQQQQQQIIIIII",
            self.FileID,
            self.TypeID,
            self.TocDataOffset,
            self.StreamOffset,
            self.GpuResourceOffset,
            self.Unknown1,
            self.Unknown2,
            self.TocDataSize,
            self.StreamSize,
            self.GpuResourceSize,
            self.Unknown3,
            self.Unknown4,
            self.EntryIndex))
                
class WwiseDep:

    def __init__(self):
        self.Data = ""
        
    def FromMemoryStream(self, stream):
        self.Offset = stream.tell()
        self.Tag = stream.uint32Read()
        self.DataSize = stream.uint32Read()
        self.Data = stream.read(self.DataSize).decode('utf-8')
        
    def GetData(self):
        return (self.Tag.to_bytes(4, byteorder='little')
                + self.DataSize.to_bytes(4, byteorder='little')
                + self.Data.encode('utf-8'))
                
class DidxEntry:
    def __init__(self):
        self.id = self.offset = self.size = 0
        
    @classmethod
    def FromBytes(cls, bytes):
        e = DidxEntry()
        e.id, e.offset, e.size = struct.unpack("<III", bytes)
        return e
        
    def GetData(self):
        return struct.pack("<III", self.id, self.offset, self.size)
        
class MediaIndex:

    def __init__(self):
        self.entries = {}
        self.data = {}
        
    def Load(self, didxChunk, dataChunk):
        for n in range(int(len(didxChunk)/12)):
            entry = DidxEntry.FromBytes(didxChunk[12*n : 12*(n+1)])
            self.entries[entry.id] = entry
            self.data[entry.id] = dataChunk[entry.offset:entry.offset+entry.size]
        
    def GetData(self):
        arr = [x.GetData() for x in self.entries.values()]
        dataArr = self.data.values()
        return b"".join(arr) + b"".join(dataArr)
                
class HircEntry:
    
    def __init__(self):
        self.size = self.hType = self.hId = self.misc = 0
    
    @classmethod
    def FromMemoryStream(cls, stream):
        entry = HircEntry()
        entry.hType = stream.uint8Read()
        entry.size = stream.uint32Read()
        entry.hId = stream.uint32Read()
        entry.misc = stream.read(entry.size - 4)
        return entry
        
    def GetId(self):
        return self.hId
        
    def GetData(self):
        return self.hType.to_bytes(1, byteorder="little") + self.size.to_bytes(4, byteorder="little") + self.hId.to_bytes(4, byteorder="little") + self.misc
        
class HircEntryFactory:
    
    @classmethod
    def FromMemoryStream(cls, stream):
        hircType = stream.uint8Read()
        stream.seek(stream.tell()-1)
        if hircType == 2: #sound
            return Sound.FromMemoryStream(stream)
        elif hircType == 11: #music track
            return MusicTrack.FromMemoryStream(stream)
        else:
            return HircEntry.FromMemoryStream(stream)
        
class HircReader:
    
    def __init__(self):
        self.entries = {}
        
    def Load(self, hircData):
        self.entries.clear()
        reader = MemoryStream()
        reader.write(hircData)
        reader.seek(0)
        numItems = reader.uint32Read()
        for item in range(numItems):
            entry = HircEntryFactory.FromMemoryStream(reader)
            self.entries[entry.GetId()] = entry
            
    def GetData(self):
        arr = [entry.GetData() for entry in self.entries.values()]
        return len(arr).to_bytes(4, byteorder="little") + b"".join(arr)
            
class BankParser:
    
    def __init__(self):
        self.Chunks = {}
        
    def Load(self, bankData):
        self.Chunks.clear()
        reader = MemoryStream()
        reader.write(bankData)
        reader.seek(0)
        while True:
            tag = ""
            try:
                tag = reader.read(4).decode('utf-8')
            except:
                break
            size = reader.uint32Read()
            self.Chunks[tag] = reader.read(size)
            
class BankSourceData:

    def __init__(self):
        self.pluginId = 0
        self.streamType = self.sourceId = self.memSize = self.bitFlags = 0
        
    @classmethod
    def FromBytes(cls, bytes):
        b = BankSourceData()
        b.pluginId, b.streamType, b.sourceId, b.memSize, b.bitFlags = struct.unpack("<IBIIB", bytes)
        return b
        
    def GetData(self):
        return struct.pack("<IBIIB", self.pluginId, self.streamType, self.sourceId, self.memSize, self.bitFlags)
        
class TrackInfo:
    
    def __init__(self):
        self.trackId = self.sourceId = self.eventId = self.playAt = self.beginTrimOffset = self.endTrimOffset = self.sourceDuration = 0
        
    @classmethod
    def FromBytes(cls, bytes):
        t = TrackInfo()
        t.trackId, t.sourceId, t.eventId, t.playAt, t.beginTrimOffset, t.endTrimOffset, t.sourceDuration = struct.unpack("<IIIdddd", bytes)
        return t
        
    def GetData(self):
        return struct.pack("<IIIdddd", self.trackId, self.sourceId, self.eventId, self.playAt, self.beginTrimOffset, self.endTrimOffset, self.sourceDuration)
            
class MusicTrack(HircEntry):
    
    def __init__(self):
        super().__init__()
        self.sources = []
        self.trackInfo = []
        self.bitFlags = 0
        
    @classmethod
    def FromMemoryStream(cls, stream):
        entry = MusicTrack()
        entry.hType = stream.uint8Read()
        entry.size = stream.uint32Read()
        startPosition = stream.tell()
        entry.hId = stream.uint32Read()
        entry.bitFlags = stream.uint8Read()
        numSources = stream.uint32Read()
        for _ in range(numSources):
            source = BankSourceData.FromBytes(stream.read(14))
            entry.sources.append(source)
        numTrackInfo = stream.uint32Read()
        for _ in range(numTrackInfo):
            track = TrackInfo.FromBytes(stream.read(44))
            entry.trackInfo.append(track)
        entry.misc = stream.read(entry.size - (stream.tell()-startPosition))
        return entry

    def GetData(self):
        b = b""
        for source in self.sources:
            b = b + source.GetData()
        t = b""
        for track in self.trackInfo:
            t = t + track.GetData()
        return struct.pack(f"<BIIBI", self.hType, self.size, self.hId, self.bitFlags, len(self.sources)) + b + len(self.trackInfo).to_bytes(4, byteorder="little") + t + self.misc
    
class Sound(HircEntry):
    
    def __init__(self):
        super().__init__()
        self.source = None
    
    @classmethod
    def FromMemoryStream(cls, stream):
        entry = Sound()
        entry.hType = stream.uint8Read()
        entry.size = stream.uint32Read()
        entry.hId = stream.uint32Read()
        entry.source = BankSourceData.FromBytes(stream.read(14))
        entry.misc = stream.read(entry.size - 18)
        return entry

    def GetData(self):
        return struct.pack(f"<BII14s{len(self.misc)}s", self.hType, self.size, self.hId, self.source.GetData(), self.misc)
        
class WwiseBank(Subscriber):
    
    def __init__(self):
        self.data = b""
        self.BankHeader = b""
        self.TocDataHeader = b""
        self.BankPostData = b""
        self.Modified = False
        self.TocHeader = None
        self.Dep = None
        self.ModifiedCount = 0
        self.hierarchy = None
        self.Content = []
        
    def AddContent(self, content):
        content.Subscribers.add(self)
        self.Content.append(content)
        
    def RemoveContent(self, content):
        try:
            content.Subscribers.remove(self)
        except:
            pass
            
        try:
            self.Content.remove(content)
        except:
            pass
  
    def GetContent(self):
        return self.Content
        
    def RaiseModified(self):
        self.Modified = True
        self.ModifiedCount += 1
        
    def LowerModified(self):
        if self.Modified:
            self.ModifiedCount -= 1
            if self.ModifiedCount == 0:
                self.Modified = False
        
    def GetName(self):
        return self.Dep.Data
        
    def GetFileID(self):
        try:
            return self.TocHeader.FileID
        except:
            return 0
            
    def GetTypeID(self):
        try:
            return self.TocHeader.TypeID
        except:
            return 0
            
    def GetData(self):
        return self.data
            
    def Generate(self, audioSources):
        data = bytearray()
        data += self.BankHeader
        
        didxSection = b""
        dataSection = b""
        offset = 0
        
        #regenerate soundbank from the hierarchy information
        maxProgress = 0
        for entry in self.hierarchy.entries.values():
            if entry.hType == SOUND:
                maxProgress += 1
            elif entry.hType == MUSIC_TRACK:
                maxProgress += len(entry.sources)
                    
        
        bankGeneration = ProgressWindow("Generating Soundbanks", maxProgress)
        bankGeneration.Show()
        bankGeneration.SetText(f"Generating {self.Dep.Data}")
        
        didxArray = []
        dataArray = []
        
        for entry in self.hierarchy.entries.values():
            if entry.hType == SOUND:
                source = entry.source
                bankGeneration.Step()
                try:
                    audio = audioSources[f"{self.GetFileID()}-{source.sourceId}"]
                except KeyError:
                    continue
                if source.streamType == PREFETCH_STREAM:
                    dataArray.append(audio.GetData()[:source.memSize])
                    didxArray.append(struct.pack("<III", source.sourceId, offset, source.memSize))
                    offset += source.memSize
                elif source.streamType == BANK:
                    dataArray.append(audio.GetData())
                    didxArray.append(struct.pack("<III", source.sourceId, offset, audio.Size))
                    offset += audio.Size
            elif entry.hType == MUSIC_TRACK:
                for index, source in enumerate(entry.sources):
                    bankGeneration.Step()
                    try:
                        audio = audioSources[f"{self.GetFileID()}-{source.sourceId}"]
                    except KeyError:
                        continue
                    #trackInfo = entry.trackInfo[index]
                    if source.streamType == PREFETCH_STREAM:
                        dataArray.append(audio.GetData()[:source.memSize])
                        didxArray.append(struct.pack("<III", source.sourceId, offset, source.memSize))
                        offset += source.memSize
                    elif source.streamType == BANK:
                        dataArray.append(audio.GetData())
                        didxArray.append(struct.pack("<III", source.sourceId, offset, audio.Size))
                        offset += audio.Size
        if len(didxArray) > 0:
            data += "DIDX".encode('utf-8') + (12*len(didxArray)).to_bytes(4, byteorder="little")
            data += b"".join(didxArray)
            data += "DATA".encode('utf-8') + sum([len(x) for x in dataArray]).to_bytes(4, byteorder="little")
            data += b"".join(dataArray)
            
        hircSection = self.hierarchy.GetData()
        data += "HIRC".encode('utf-8') + len(hircSection).to_bytes(4, byteorder="little")
        data += hircSection
        data += self.BankPostData
        self.TocHeader.TocDataSize = len(data) + len(self.TocDataHeader)
        self.TocDataHeader[4:8] = len(data).to_bytes(4, byteorder="little")
        self.data = data
        bankGeneration.Destroy()
                     
    def GetEntryIndex(self):
        try:
            return self.TocHeader.EntryIndex
        except:
            return 0
        
class WwiseStream(Subscriber):

    def __init__(self):
        self.Content = None
        self.Modified = False
        self.TocHeader = None
        self.TocData = bytearray()
        
    def SetContent(self, content):
        try:
            self.Content.Subscribers.remove(self)
        except:
            pass
        self.Content = content
        content.Subscribers.add(self)
        
    def Update(self, content):
        self.TocHeader.StreamSize = content.Size
        self.TocData[8:12] = content.Size.to_bytes(4, byteorder='little')
        
    def RaiseModified(self):
        self.Modified = True
        
    def LowerModified(self):
        self.Modified = False
        
    def GetFileID(self):
        try:
            return self.TocHeader.FileID
        except:
            return 0
        
    def GetTypeID(self):
        try:
            return self.TocHeader.TypeID
        except:
            return 0
            
    def GetEntryIndex(self):
        try:
            return self.TocHeader.EntryIndex
        except:
            return 0
            
    def GetData(self):
        return self.Content.GetData()

class StringEntry:

    def __init__(self):
        self.Text = ""
        self.Offset = 0
        self.FileID = 0
        self.TextVariable = None
        self.Modified = False
        self.Parent = None
        
    def GetFileID(self):
        return self.FileID
        
    def GetText(self):
        return self.Text
    
    def GetOffset(self):
        return self.Offset
        
    def UpdateText(self):
        self.Modified = True
        textLen = len(self.Text)
        self.Text = self.TextVariable.get()
        sizeDifference = len(self.Text) - textLen
        self.Parent.Rebuild(self.FileID, sizeDifference)
        
    def SetText(self, text):
        self.Modified = True
        textLen = len(self.Text)
        self.Text = text
        sizeDifference = len(self.Text) - textLen
        self.TextVariable.set(text)
        self.Parent.Rebuild(self.FileID, sizeDifference)
        
    def __deepcopy__(self, memo):
        newEntry = StringEntry()
        newEntry.Text = self.Text
        newEntry.Offset = self.Offset
        newEntry.FileID = self.FileID
        newEntry.TextVariable = self.TextVariable
        newEntry.Modified = self.Modified
        newEntry.Parent = self.Parent
        return newEntry
        
class TextData:
    
    def __init__(self):
        self.TocHeader = None
        self.Data = b''
        self.StringEntries = {}
        self.Language = ""
        self.Modified = False
        
    def SetData(self, data):
        self.StringEntries.clear()
        numEntries = int.from_bytes(data[8:12], byteorder='little')
        self.Language = "English(US)"
        idStart = 16
        offsetStart = idStart + 4 * numEntries
        dataStart = offsetStart + 4 * numEntries
        ids = data[idStart:offsetStart]
        offsets = data[offsetStart:dataStart]
        for n in range(numEntries):
            entry = StringEntry()
            stringID = int.from_bytes(ids[4*n:+4*(n+1)], byteorder="little")
            stringOffset = int.from_bytes(offsets[4*n:4*(n+1)], byteorder="little")
            entry.FileID = stringID
            entry.Offset = stringOffset
            stopIndex = stringOffset + 1
            while data[stopIndex] != 0:
                stopIndex += 1
            entry.Text = data[stringOffset:stopIndex].decode('utf-8')
            entry.Parent = self
            self.StringEntries[stringID] = entry
            
    def Update(self):
        self.TocHeader.TocData = self.GetData()
        self.TocHeader.TocDataSize = len(self.TocHeader.TocData)
        
    def GetData(self):
        stream = MemoryStream()
        stream.write(b'\xae\xf3\x85\x3e\x01\x00\x00\x00')
        stream.write(len(self.StringEntries).to_bytes(4, byteorder="little"))
        stream.write(b'\x57\x7B\xf9\x03') #Language code
        for entry in self.StringEntries.values():
            stream.write(entry.FileID.to_bytes(4, byteorder="little"))
        for entry in self.StringEntries.values():
            stream.write(entry.Offset.to_bytes(4, byteorder="little"))
        for entry in self.StringEntries.values():
            stream.seek(entry.Offset)
            stream.write(entry.Text.encode('utf-8') + b'\x00')
        return stream.Data
        
    def Rebuild(self, stringID, offsetDifference):
        modifiedEntry = self.StringEntries[stringID]
        for entry in self.StringEntries.values():
            if entry.Offset > modifiedEntry.Offset:
                entry.Offset += offsetDifference
        
    def GetFileID(self):
        try:
            return self.TocHeader.FileID
        except:
            return 0
        
    def GetTypeID(self):
        try:
            return self.TocHeader.TypeID
        except:
            return 0
            
    def GetEntryIndex(self):
        try:
            return self.TocHeader.EntryIndex
        except:
            return 0

class FileReader:
    
    def __init__(self):
        pass
        
    def FromFile(self, path):
        self.Name = os.path.basename(path)
        tocFile = MemoryStream()
        with open(path, 'r+b') as f:
            tocFile = MemoryStream(f.read())

        streamFile = MemoryStream()
        if os.path.isfile(path+".stream"):
            with open(path+".stream", 'r+b') as f:
                streamFile = MemoryStream(f.read())
        self.Load(tocFile, streamFile)
        
    def ToFile(self, path):
        tocFile = MemoryStream()
        streamFile = MemoryStream()
        self.numFiles = len(self.WwiseStreams) + 2*len(self.WwiseBanks) + len(self.TextData)
        self.numTypes = 0
        if len(self.WwiseStreams) > 0: self.numTypes += 1
        if len(self.WwiseBanks) > 0: self.numTypes += 2
        if len(self.TextData) > 0: self.numTypes += 1
        
        tocFile.write(self.magic.to_bytes(4, byteorder="little"))
        
        tocFile.write(self.numTypes.to_bytes(4, byteorder="little"))
        tocFile.write(self.numFiles.to_bytes(4, byteorder="little"))
        tocFile.write(self.unknown.to_bytes(4, byteorder="little"))
        tocFile.write(self.unk4Data)
        
        if len(self.WwiseStreams) > 0:
            unk = 0
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = 5785811756662211598
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = len(self.WwiseStreams)
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = 16
            tocFile.write(unk.to_bytes(4, byteorder='little'))
            unk = 64
            tocFile.write(unk.to_bytes(4, byteorder='little'))
            
        if len(self.WwiseBanks) > 0:
            unk = 0
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = 6006249203084351385
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = len(self.WwiseBanks)
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = 16
            tocFile.write(unk.to_bytes(4, byteorder='little'))
            unk = 64
            tocFile.write(unk.to_bytes(4, byteorder='little'))
            
            #deps
            unk = 0
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = 12624162998411505776
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = len(self.WwiseBanks)
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = 16
            tocFile.write(unk.to_bytes(4, byteorder='little'))
            unk = 64
            tocFile.write(unk.to_bytes(4, byteorder='little'))
            
        if len(self.TextData) > 0:
            unk = 0
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = 979299457696010195
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = len(self.TextData)
            tocFile.write(unk.to_bytes(8, byteorder='little'))
            unk = 16
            tocFile.write(unk.to_bytes(4, byteorder='little'))
            unk = 64
            tocFile.write(unk.to_bytes(4, byteorder='little'))
        
        tocPosition = tocFile.tell()
        for key in self.WwiseStreams.keys():
            tocFile.seek(tocPosition)
            tocPosition += 80
            stream = self.WwiseStreams[key]
            tocFile.write(stream.TocHeader.GetData())
            tocFile.seek(stream.TocHeader.TocDataOffset)
            tocFile.write(PadTo16ByteAlign(stream.TocData))
            streamFile.seek(stream.TocHeader.StreamOffset)
            streamFile.write(PadTo16ByteAlign(stream.Content.GetData()))
            
        for key in self.WwiseBanks.keys():
            tocFile.seek(tocPosition)
            tocPosition += 80
            bank = self.WwiseBanks[key]
            tocFile.write(bank.TocHeader.GetData())
            tocFile.seek(bank.TocHeader.TocDataOffset)
            tocFile.write(PadTo16ByteAlign(bank.TocDataHeader + bank.GetData()))
            
        for key in self.WwiseBanks.keys():
            tocFile.seek(tocPosition)
            tocPosition += 80
            bank = self.WwiseBanks[key]
            tocFile.write(bank.Dep.TocHeader.GetData())
            tocFile.seek(bank.Dep.TocHeader.TocDataOffset)
            tocFile.write(PadTo16ByteAlign(bank.Dep.GetData()))
            
        for key in self.TextData.keys():
            tocFile.seek(tocPosition)
            tocPosition += 80
            entry = self.TextData[key]
            tocFile.write(entry.TocHeader.GetData())
            tocFile.seek(entry.TocHeader.TocDataOffset)
            tocFile.write(PadTo16ByteAlign(entry.GetData()))
            
            
        with open(os.path.join(path, self.Name), 'w+b') as f:
            f.write(tocFile.Data)
            
        if len(streamFile.Data) > 0:
            with open(os.path.join(path, self.Name+".stream"), 'w+b') as f:
                f.write(streamFile.Data)

    def RebuildHeaders(self):
        self.numTypes = 0
        if len(self.WwiseStreams) > 0: self.numTypes += 1
        if len(self.WwiseBanks) > 0: self.numTypes += 2
        if len(self.TextData) > 0: self.numTypes += 1
        self.numFiles = len(self.WwiseStreams) + 2*len(self.WwiseBanks) + len(self.TextData)
        streamOffset = 0
        tocOffset = 80 + self.numTypes * 32 + 80 * self.numFiles
        for key, value in self.WwiseStreams.items():
            value.TocHeader.StreamOffset = streamOffset
            value.TocHeader.TocDataOffset = tocOffset
            streamOffset += _16ByteAlign(value.TocHeader.StreamSize)
            tocOffset += _16ByteAlign(value.TocHeader.TocDataSize)
        
        for key, value in self.WwiseBanks.items():
            value.Generate(self.AudioSources)
            value.TocHeader.TocDataOffset = tocOffset
            tocOffset += _16ByteAlign(value.TocHeader.TocDataSize)
            
        for key, value in self.WwiseBanks.items():
            value.Dep.TocHeader.TocDataOffset = tocOffset
            tocOffset += _16ByteAlign(value.TocHeader.TocDataSize)
            
        for key, value in self.TextData.items():
            value.Update()
            value.TocHeader.TocDataOffset = tocOffset
            tocOffset += _16ByteAlign(value.TocHeader.TocDataSize)
        
    def Load(self, tocFile, streamFile):
        self.WwiseStreams = {}
        self.WwiseBanks = {}
        self.AudioSources = {}
        self.TextData = {}
        self.magic      = tocFile.uint32Read()
        if self.magic != 4026531857: return False

        self.numTypes   = tocFile.uint32Read()
        self.numFiles   = tocFile.uint32Read()
        self.unknown    = tocFile.uint32Read()
        self.unk4Data   = tocFile.read(56)
        tocFile.seek(tocFile.tell() + 32 * self.numTypes)
        tocStart = tocFile.tell()
        for n in range(self.numFiles):
            tocFile.seek(tocStart + n*80)
            tocHeader = TocHeader()
            tocHeader.FromMemoryStream(tocFile)
            entry = None
            if tocHeader.TypeID == 5785811756662211598:
                audio = AudioSource()
                audio.streamType = STREAM
                entry = WwiseStream()
                entry.TocHeader = tocHeader
                tocFile.seek(tocHeader.TocDataOffset)
                entry.TocData = tocFile.read(tocHeader.TocDataSize)
                streamFile.seek(tocHeader.StreamOffset)
                audio.SetData(streamFile.read(tocHeader.StreamSize), notifySubscribers=False, setModified=False)
                audio.resourceId = tocHeader.FileID
                entry.SetContent(audio)
                self.WwiseStreams[entry.GetFileID()] = entry
            elif tocHeader.TypeID == 6006249203084351385:
                entry = WwiseBank()
                entry.TocHeader = tocHeader
                tocDataOffset = tocHeader.TocDataOffset
                tocDataSize = tocHeader.TocDataSize
                tocFile.seek(tocDataOffset)
                entry.TocDataHeader = tocFile.read(16)
                #-------------------------------------
                bank = BankParser()
                bank.Load(tocFile.read(tocHeader.TocDataSize-16))
                entry.BankHeader = "BKHD".encode('utf-8') + len(bank.Chunks["BKHD"]).to_bytes(4, byteorder="little") + bank.Chunks["BKHD"]
                
                hirc = HircReader()
                try:
                    hirc.Load(bank.Chunks['HIRC'])
                except KeyError:
                    continue
                entry.hierarchy = hirc    
                #-------------------------------------
                #Add all bank sources to the source list
                if "DIDX" in bank.Chunks.keys():
                    bankId = entry.TocHeader.FileID
                    mediaIndex = MediaIndex()
                    mediaIndex.Load(bank.Chunks["DIDX"], bank.Chunks["DATA"])
                    for e in hirc.entries.values():
                        if e.hType == SOUND and e.source.pluginId == 0x00040001:
                            if e.source.streamType == BANK and f"{bankId}-{e.source.sourceId}" not in self.AudioSources:
                                audio = AudioSource()
                                audio.streamType = BANK
                                audio.shortId = e.source.sourceId
                                audio.SetData(mediaIndex.data[e.source.sourceId], setModified=False, notifySubscribers=False)
                                self.AudioSources[f"{bankId}-{e.source.sourceId}"] = audio
                                entry.AddContent(audio)
                        elif e.hType == MUSIC_TRACK:
                            for source in e.sources:
                                if source.streamType == BANK and f"{bankId}-{source.sourceId}" not in self.AudioSources:
                                    audio = AudioSource()
                                    audio.streamType = BANK
                                    audio.shortId = source.sourceId
                                    audio.SetData(mediaIndex.data[source.sourceId], setModified=False, notifySubscribers=False)
                                    self.AudioSources[f"{bankId}-{source.sourceId}"] = audio
                                    entry.AddContent(audio)
                
                entry.BankPostData = b''
                for chunk in bank.Chunks.keys():
                    if chunk not in ["BKHD", "DATA", "DIDX", "HIRC"]:
                        entry.BankPostData = entry.BankPostData + chunk.encode('utf-8') + len(bank.Chunks[chunk]).to_bytes(4, byteorder='little') + bank.Chunks[chunk]
                        
                self.WwiseBanks[entry.GetFileID()] = entry
            elif tocHeader.TypeID == 12624162998411505776: #wwise dep
                dep = WwiseDep()
                dep.TocHeader = tocHeader
                tocFile.seek(tocHeader.TocDataOffset)
                dep.FromMemoryStream(tocFile)
                try:
                    self.WwiseBanks[tocHeader.FileID].Dep = dep
                except KeyError:
                    pass
            elif tocHeader.TypeID == 979299457696010195: #stringEntry
                tocFile.seek(tocHeader.TocDataOffset)
                data = tocFile.read(tocHeader.TocDataSize)
                if int.from_bytes(data[12:16], byteorder='little') == 66681687: #English (US)
                    entry = TextData()
                    entry.TocHeader = tocHeader
                    entry.SetData(data)
                    self.TextData[entry.GetFileID()] = entry
        
        
        #check that all banks have valid Dep here, and ask for more data if does not?
        
        for bank in self.WwiseBanks.values():
            if bank.Dep == None: #can be None because older versions didn't save the dep along with the bank
                if not self.LoadDeps():
                    print("Failed to load")
                    self.WwiseStreams.clear()
                    self.WwiseBanks.clear()
                    self.TextData.clear()
                    self.AudioSources.clear()
                    return
                break
        
        if len(self.WwiseBanks) == 0 and len(self.WwiseStreams) > 0: #0 if patch was only for streams
            #print("No banks detected! This patch may have been made in an older version of the audio modding tool!") #make this a pop-up window
            if not self.LoadBanks():
                print("Failed to load")
                self.WwiseStreams.clear()
                self.WwiseBanks.clear()
                self.TextData.clear()
                self.AudioSources.clear()
                return
            
        
        #Once every resource has been loaded, finish constructing the list of audio sources and stuff
        #Add all stream entries to the AudioSource list, using their shortID (requires mapping via the Dep)
        for bank in self.WwiseBanks.values():
            for entry in bank.hierarchy.entries.values():
                if entry.hType == SOUND:
                    if f"{bank.GetFileID()}-{entry.source.sourceId}" not in self.AudioSources and entry.source.streamType in [STREAM, PREFETCH_STREAM]:
                        try:
                            streamResourceId = murmur64Hash((os.path.dirname(bank.Dep.Data) + "/" + str(entry.source.sourceId)).encode('utf-8'))
                            audio = self.WwiseStreams[streamResourceId].Content
                            audio.shortId = entry.source.sourceId
                            self.AudioSources[f"{bank.GetFileID()}-{entry.source.sourceId}"] = audio
                            bank.AddContent(audio)
                        except KeyError:
                            pass
                    elif f"{bank.GetFileID()}-{entry.source.sourceId}" in self.AudioSources:
                        self.AudioSources[f"{bank.GetFileID()}-{entry.source.sourceId}"].resourceId = murmur64Hash((os.path.dirname(bank.Dep.Data) + "/" + str(entry.source.sourceId)).encode('utf-8'))
                elif entry.hType == MUSIC_TRACK:
                    for source in entry.sources:
                        if f"{bank.GetFileID()}-{source.sourceId}" not in self.AudioSources and source.streamType in [STREAM, PREFETCH_STREAM]:
                            try:
                                streamResourceId = murmur64Hash((os.path.dirname(bank.Dep.Data) + "/" + str(source.sourceId)).encode('utf-8'))
                                audio = self.WwiseStreams[streamResourceId].Content
                                audio.shortId = source.sourceId
                                self.AudioSources[f"{bank.GetFileID()}-{source.sourceId}"] = audio
                                bank.AddContent(audio)
                            except KeyError:
                                pass
                        elif f"{bank.GetFileID()}-{source.sourceId}" in self.AudioSources:
                            self.AudioSources[f"{bank.GetFileID()}-{source.sourceId}"].resourceId = murmur64Hash((os.path.dirname(bank.Dep.Data) + "/" + str(source.sourceId)).encode('utf-8'))
                            
                            
        
    def LoadDeps(self):
        if _GAME_FILE_LOCATION != "":
            archiveFile = os.path.join(_GAME_FILE_LOCATION, StripPatchIndex(self.Name))
        if not os.path.exists(archiveFile):
            warning = PopupWindow(message = "This patch may have been created using an older version of the audio modding tool and is missing required data. Please select the original game file to load required data.")
            warning.Show()
            warning.root.wait_window(warning.root)
            archiveFile = askopenfilename(title="Select archive")
            if os.path.splitext(archiveFile)[1] in (".stream", ".gpu_resources"):
                archiveFile = os.path.splitext(archiveFile)[0]
        if not os.path.exists(archiveFile):
            return False
        #self.Name = os.path.basename(path)
        tocFile = MemoryStream()
        with open(archiveFile, 'r+b') as f:
            tocFile = MemoryStream(f.read())

        self.magic      = tocFile.uint32Read()
        if self.magic != 4026531857: return False

        self.numTypes   = tocFile.uint32Read()
        self.numFiles   = tocFile.uint32Read()
        self.unknown    = tocFile.uint32Read()
        self.unk4Data   = tocFile.read(56)
        tocFile.seek(tocFile.tell() + 32 * self.numTypes)
        tocStart = tocFile.tell()
        for n in range(self.numFiles):
            tocFile.seek(tocStart + n*80)
            tocHeader = TocHeader()
            tocHeader.FromMemoryStream(tocFile)
            if tocHeader.TypeID == 12624162998411505776: #wwise dep
                dep = WwiseDep()
                dep.TocHeader = tocHeader
                tocFile.seek(tocHeader.TocDataOffset)
                dep.FromMemoryStream(tocFile)
                try:
                    self.WwiseBanks[tocHeader.FileID].Dep = dep
                except KeyError:
                    pass
        return True
        
    def LoadBanks(self):
        if _GAME_FILE_LOCATION != "":
            archiveFile = os.path.join(_GAME_FILE_LOCATION, StripPatchIndex(self.Name))
        if not os.path.exists(archiveFile):
            warning = PopupWindow(message = "This patch may have been created using an older version of the audio modding tool and is missing required data. Please select the original game file to load required data.")
            warning.Show()
            warning.root.wait_window(warning.root)
            archiveFile = askopenfilename(title="Select archive")
            if os.path.splitext(archiveFile)[1] in (".stream", ".gpu_resources"):
                archiveFile = os.path.splitext(archiveFile)[0]
        if not os.path.exists(archiveFile):
            return False
        tocFile = MemoryStream()
        with open(archiveFile, 'r+b') as f:
            tocFile = MemoryStream(f.read())

        self.magic      = tocFile.uint32Read()
        if self.magic != 4026531857: return False

        self.numTypes   = tocFile.uint32Read()
        self.numFiles   = tocFile.uint32Read()
        self.unknown    = tocFile.uint32Read()
        self.unk4Data   = tocFile.read(56)
        tocFile.seek(tocFile.tell() + 32 * self.numTypes)
        tocStart = tocFile.tell()
        for n in range(self.numFiles):
            tocFile.seek(tocStart + n*80)
            tocHeader = TocHeader()
            tocHeader.FromMemoryStream(tocFile)
            entry = None
            if tocHeader.TypeID == 6006249203084351385:
                entry = WwiseBank()
                entry.TocHeader = tocHeader
                tocDataOffset = tocHeader.TocDataOffset
                tocDataSize = tocHeader.TocDataSize
                tocFile.seek(tocDataOffset)
                entry.TocDataHeader = tocFile.read(16)
                #-------------------------------------
                bank = BankParser()
                bank.Load(tocFile.read(tocHeader.TocDataSize-16))
                entry.BankHeader = "BKHD".encode('utf-8') + len(bank.Chunks["BKHD"]).to_bytes(4, byteorder="little") + bank.Chunks["BKHD"]
                
                hirc = HircReader()
                try:
                    hirc.Load(bank.Chunks['HIRC'])
                except KeyError:
                    continue
                entry.hierarchy = hirc
                #-------------------------------------
                entry.BankPostData = b''
                for chunk in bank.Chunks.keys():
                    if chunk not in ["BKHD", "DATA", "DIDX", "HIRC"]:
                        entry.BankPostData = entry.BankPostData + chunk.encode('utf-8') + len(bank.Chunks[chunk]).to_bytes(4, byteorder='little') + bank.Chunks[chunk]
                        
                self.WwiseBanks[entry.GetFileID()] = entry
            elif tocHeader.TypeID == 12624162998411505776: #wwise dep
                dep = WwiseDep()
                dep.TocHeader = tocHeader
                tocFile.seek(tocHeader.TocDataOffset)
                dep.FromMemoryStream(tocFile)
                try:
                    self.WwiseBanks[tocHeader.FileID].Dep = dep
                except KeyError:
                    pass
        
        #only include banks that contain at least 1 of the streams
        tempBanks = {}
        for key, bank in self.WwiseBanks.items():
            includeBank = False
            for hierEntry in bank.hierarchy.entries.values():
                if hierEntry.hType == SOUND and hierEntry.source.pluginId == 0x00040001:
                    if hierEntry.source.streamType in [STREAM, PREFETCH_STREAM]:
                        streamResourceId = murmur64Hash((os.path.dirname(bank.Dep.Data) + "/" + str(hierEntry.source.sourceId)).encode('utf-8'))
                        for stream in self.WwiseStreams.values():
                            if stream.GetFileID() == streamResourceId:
                                includeBank = True
                                tempBanks[key] = bank
                                break
                elif hierEntry.hType == MUSIC_TRACK:
                    for source in hierEntry.sources:
                        if source.streamType in [STREAM, PREFETCH_STREAM]:
                            streamResourceId = murmur64Hash((os.path.dirname(bank.Dep.Data) + "/" + str(source.sourceId)).encode('utf-8'))
                            for stream in self.WwiseStreams.values():
                                if stream.GetFileID() == streamResourceId:
                                    includeBank = True
                                    tempBanks[key] = bank
                                    break
                        if includeBank:
                            break
                if includeBank:
                    break
        self.WwiseBanks = tempBanks
        
        return True
        
class SoundHandler:
    
    def __init__(self):
        self.audioProcess = None
        self.waveObject = None
        self.audioID = -1
        self.audio = pyaudio.PyAudio()
        
    def KillSound(self):
        if self.audioProcess is not None:
            if self.callback is not None:
                self.callback()
                self.callback = None
            self.audioProcess.close()
            self.waveFile.close()
            try:
                os.remove(self.audioFile)
            except:
                pass
            self.audioProcess = None
        
    def PlayAudio(self, soundID, soundData, callback=None):
        self.KillSound()
        self.callback = callback
        if self.audioID == soundID:
            self.audioID = -1
            return
        filename = f"temp{soundID}"
        if not os.path.isfile(f"{filename}.wav"):
            with open(f'{filename}.wem', 'wb') as f:
                f.write(soundData)
            subprocess.run(["vgmstream-win64/vgmstream-cli.exe", "-o", f"{filename}.wav", f"{filename}.wem"], stdout=subprocess.DEVNULL)
            os.remove(f"{filename}.wem")
            
        self.audioID = soundID
        self.waveFile = wave.open(f"{filename}.wav")
        self.audioFile = f"{filename}.wav"
        self.frameCount = 0
        self.maxFrames = self.waveFile.getnframes()
        
        def readStream(input_data, frame_count, time_info, status):
            self.frameCount += frame_count
            if self.frameCount > self.maxFrames:
                if self.callback is not None:
                    self.callback()
                    self.callback = None
                self.audioID = -1
                self.waveFile.close()
                try:
                    os.remove(self.audioFile)
                except:
                    pass
                return (None, pyaudio.paComplete)
            data = self.waveFile.readframes(frame_count)
            if self.waveFile.getnchannels() > 2:
                data = self.DownmixToStereo(data, self.waveFile.getnchannels(), self.waveFile.getsampwidth(), frame_count)
            return (data, pyaudio.paContinue)

        self.audioProcess = self.audio.open(format=self.audio.get_format_from_width(self.waveFile.getsampwidth()),
                channels = min(self.waveFile.getnchannels(), 2),
                rate=self.waveFile.getframerate(),
                output=True,
                stream_callback=readStream)
        self.audioFile = f"{filename}.wav"
        
    def DownmixToStereo(self, data, channels, channelWidth, frameCount):
        if channelWidth == 2:
            arr = numpy.frombuffer(data, dtype=numpy.int16)
            stereoArr = numpy.zeros(shape=(frameCount, 2), dtype=numpy.int16)
        elif channelWidth == 1:
            arr = numpy.frombuffer(data, dtype=numpy.int8)
            stereoArr = numpy.zeros(shape=(frameCount, 2), dtype=numpy.int8)
        elif channelWidth == 4:
            arr = numpy.frombuffer(data, dtype=numpy.int32)
            stereoArr = numpy.zeros(shape=(frameCount, 2), dtype=numpy.int32)
        arr = arr.reshape((frameCount, channels))
        
        if channels == 4:
            for index, frame in enumerate(arr):
                stereoArr[index][0] = int(0.42265 * frame[0] + 0.366025 * frame[2] + 0.211325 * frame[3])
                stereoArr[index][1] = int(0.42265 * frame[1] + 0.366025 * frame[3] + 0.211325 * frame[2])
                
        if channels == 6:
            for index, frame in enumerate(arr):
                stereoArr[index][0] = int(0.374107*frame[1] + 0.529067*frame[0] + 0.458186*frame[3] + 0.264534*frame[4] + 0.374107*frame[5])
                stereoArr[index][1] = int(0.374107*frame[1] + 0.529067*frame[2] + 0.458186*frame[4] + 0.264534*frame[3] + 0.374107*frame[5])
        
        return stereoArr.tobytes()

class ProgressWindow:
    def __init__(self, title, maxProgress):
        self.title = title
        self.maxProgress = maxProgress
        
    def Show(self):
        self.root = Tk()
        self.root.title(self.title)
        self.root.configure(background="white")
        self.root.geometry("410x45")
        self.root.attributes('-topmost', True)
        self.progressBar = tkinter.ttk.Progressbar(self.root, orient=HORIZONTAL, length=400, mode="determinate", maximum=self.maxProgress)
        self.progressBarText = Text(self.root)
        self.progressBarText.configure(background="white")
        self.progressBar.pack()
        self.progressBarText.pack()
        self.root.resizable(False, False)
        
    def Step(self):
        self.progressBar.step()
        self.root.update_idletasks()
        self.root.update()
        
    def SetText(self, s):
        self.progressBarText.delete('1.0', END)
        self.progressBarText.insert(INSERT, s)
        self.root.update_idletasks()
        self.root.update()
        
    def Destroy(self):
        self.root.destroy()
        
class PopupWindow:
    def __init__(self, message, title="Missing Data!"):
        self.message = message
        self.title = title
        
    def Show(self):
        self.root = Tk()
        self.root.title(self.title)
        self.root.configure(background="white")
        #self.root.geometry("410x45")
        self.root.attributes('-topmost', True)
        self.text = ttk.Label(self.root, text=self.message, background="white", font=('Segoe UI', 12), wraplength=500, justify="left")
        self.button = ttk.Button(self.root, text="OK", command=self.Destroy)
        self.text.pack(padx=20, pady=0)
        self.button.pack(pady=20)
        self.root.resizable(False, False)
        
    def Destroy(self):
        self.root.destroy()
        
class FileHandler:

    def __init__(self):
        self.FileReader = FileReader()
        
    def RevertAll(self):
        for audio in self.FileReader.AudioSources.values():
            audio.RevertModifications()
        
    def RevertAudio(self, fileID):
        audio = self.GetAudioByID(fileID)
        audio.RevertModifications()
        
    def DumpAsWem(self, fileID):
        outputFile = filedialog.asksaveasfile(mode='wb', title="Save As", initialfile=(str(fileID)+".wem"), defaultextension=".wem", filetypes=[("Wwise Audio", "*.wem")])
        if outputFile is None: return
        outputFile.write(self.GetAudioByID(fileID).GetData())
        
    def DumpAsWav(self, fileID):
        outputFile = filedialog.asksaveasfilename(title="Save As", initialfile=(str(fileID)+".wav"), defaultextension=".wav", filetypes=[("Wav Audio", "*.wav")])
        if outputFile == "": return
        savePath = os.path.splitext(outputFile)[0]
        with open(f"{savePath}.wem", 'wb') as f:
            f.write(self.GetAudioByID(fileID).GetData())
        subprocess.run(["vgmstream-win64/vgmstream-cli.exe", "-o", f"{savePath}.wav", f"{savePath}.wem"], stdout=subprocess.DEVNULL)
        os.remove(f"{savePath}.wem")

    def DumpAllAsWem(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        
        progressWindow = ProgressWindow(title="Dumping Files", maxProgress=len(self.FileReader.AudioSources))
        progressWindow.Show()
        
        if os.path.exists(folder):
            for key, audio in self.FileReader.AudioSources.items():
                subfolder = os.path.join(folder, os.path.basename(self.FileReader.WwiseBanks[int(key.split('-')[0])].Dep.Data.replace('\x00', '')))
                if not os.path.exists(subfolder):
                    os.mkdir(subfolder)
                savePath = os.path.join(subfolder, key.split('-')[1])
                progressWindow.SetText("Dumping " + os.path.basename(savePath) + ".wem")
                with open(savePath+".wem", "wb") as f:
                    f.write(audio.GetData())
                progressWindow.Step()
        else:
            print("Invalid folder selected, aborting dump")
            
        progressWindow.Destroy()
    
    def DumpAllAsWav(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")

        progressWindow = ProgressWindow(title="Dumping Files", maxProgress=len(self.FileReader.AudioSources))
        progressWindow.Show()
        
        if os.path.exists(folder):
            for key, audio in self.FileReader.AudioSources.items():
                subfolder = os.path.join(folder, os.path.basename(self.FileReader.WwiseBanks[int(key.split('-')[0])].Dep.Data.replace('\x00', '')))
                if not os.path.exists(subfolder):
                    os.mkdir(subfolder)
                savePath = os.path.join(subfolder, key.split('-')[1])
                progressWindow.SetText("Dumping " + os.path.basename(savePath) + ".wav")
                with open(savePath+".wem", "wb") as f:
                    f.write(audio.GetData())
                subprocess.run(["vgmstream-win64/vgmstream-cli.exe", "-o", f"{savePath}.wav", f"{savePath}.wem"], stdout=subprocess.DEVNULL)
                os.remove(f"{savePath}.wem")
                progressWindow.Step()
        else:
            print("Invalid folder selected, aborting dump")
            
        progressWindow.Destroy()
        
    def GetFileNumberPrefix(self, n):
        number = ''.join(takewhile(str.isdigit, n or ""))
        try:
            return int(number)
        except:
            print("File name must begin with a number: "+n)
        
    def SaveArchiveFile(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        if os.path.exists(folder):
            self.FileReader.RebuildHeaders()
            self.FileReader.ToFile(folder)
        else:
            print("Invalid folder selected, aborting save")
            
    def GetAudioByID(self, fileID):
        #possible inputs: bankId-shortId, bankId-resourceId
        #are there ever any inputs that don't contain the bankId?
        bankId = int(str(fileID).split("-")[0])
        audioId = int(str(fileID).split("-")[1])
        try:
            return self.FileReader.AudioSources[fileID] #str bankId-shortId
        except KeyError:
            pass
        for source in self.FileReader.WwiseBanks[bankId].GetContent(): #bankId-resourceId
            if source.resourceId == audioId:
                return source
        
    def GetWwiseStreams(self):
        return self.FileReader.WwiseStreams
        
    def GetWwiseBanks(self):
        return self.FileReader.WwiseBanks
        
    def GetAudio(self):
        return self.FileReader.AudioSources
        
    def GetStrings(self):
        return self.FileReader.TextData
        
    def LoadArchiveFile(self):
        archiveFile = askopenfilename(title="Select archive")
        if os.path.splitext(archiveFile)[1] in (".stream", ".gpu_resources"):
            archiveFile = os.path.splitext(archiveFile)[0]
        if os.path.exists(archiveFile):
            self.FileReader.FromFile(archiveFile)
        else:
            print("Invalid file selected, aborting load")   
            return False
        return True
            
            
    def LoadPatch(self): #TO-DO: only import if DIFFERENT from original audio; makes it possible to import different mods that change the same soundbank
        patchFileReader = FileReader()
        patchFile = filedialog.askopenfilename(title="Choose patch file to import")
        if os.path.splitext(patchFile)[1] in (".stream", ".gpu_resources"):
            patchFile = os.path.splitext(patchFile)[0]
        if os.path.exists(patchFile):
            patchFileReader.FromFile(patchFile)
        else:
            print("Invalid file selected, aborting load")
            return False
            
        progressWindow = ProgressWindow(title="Loading Files", maxProgress=len(patchFileReader.AudioSources))
        progressWindow.Show()
        
        for bank in patchFileReader.WwiseBanks.values():
            for newAudio in bank.GetContent():
                progressWindow.SetText("Loading "+str(newAudio.GetFileID()))
                oldAudio = self.GetAudioByID(f"{bank.GetFileID()}-{newAudio.GetShortId()}")
                oldAudio.SetData(newAudio.GetData())
                progressWindow.Step()

        for textData in patchFileReader.TextData.values():
            oldTextData = self.GetStrings()[textData.GetFileID()]
            for entry in textData.StringEntries.values():
                oldTextData.StringEntries[entry.GetFileID()].SetText(entry.GetText())
        
        progressWindow.Destroy()
        return True

    def WritePatch(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        if os.path.exists(folder):
            patchedFileReader = FileReader()
            patchedFileReader.Name = self.FileReader.Name + ".patch_0"
            patchedFileReader.magic = self.FileReader.magic
            patchedFileReader.numTypes = 0
            patchedFileReader.numFiles = 0
            patchedFileReader.unknown = self.FileReader.unknown
            patchedFileReader.unk4Data = self.FileReader.unk4Data
            patchedFileReader.AudioSources = self.FileReader.AudioSources
            patchedFileReader.WwiseBanks = {}
            patchedFileReader.WwiseStreams = {}
            patchedFileReader.TextData = {}
            
            for key, value in self.FileReader.WwiseStreams.items():
                if value.Content.Modified:
                    patchedFileReader.WwiseStreams[key] = copy.deepcopy(value)
                    
            for key, value in self.FileReader.WwiseBanks.items():
                if value.Modified:
                    patchedFileReader.WwiseBanks[key] = copy.deepcopy(value)
                    
            for key, value in self.FileReader.TextData.items():
                for entry in value.StringEntries.values():
                    if entry.Modified:
                        patchedFileReader.TextData[key] = copy.deepcopy(value)
                        break
     
            patchedFileReader.RebuildHeaders()
            patchedFileReader.ToFile(folder)
        else:
            print("Invalid folder selected, aborting save")
            return False
        return True

    def LoadWems(self, bankId): 
        wems = filedialog.askopenfilenames(title="Choose .wem files to import")
        
        progressWindow = ProgressWindow(title="Loading Files", maxProgress=len(wems))
        progressWindow.Show()
        
        for file in wems:
            progressWindow.SetText("Loading "+os.path.basename(file))
            fileID = self.GetFileNumberPrefix(os.path.basename(file))
            audio = self.GetAudioByID(f"{bankId}-{fileID}")
            if audio is not None:
                with open(file, 'rb') as f:
                    audio.SetData(f.read())
                progressWindow.Step()
        
        progressWindow.Destroy()
            
class TableInfo:

    WEM = 0
    BANK = 1
    EXPANDED_BANK = 2
    BANK_WEM = 3

    def __init__(self):
        self._type = 0
        self.modified = False
        self.hidden = False
        self.rectangles = []
        self.buttons = []
        self.revertButton = None
        self.text = []

class MainWindow:

    def __init__(self, fileHandler, soundHandler):
        self.fileHandler = fileHandler
        self.soundHandler = soundHandler
        self.tableInfo = {}
        
        self.root = Tk()
        
        self.fakeImage = tkinter.PhotoImage(width=1, height=1)
        
        self.titleCanvas = Canvas(self.root, width=WINDOW_WIDTH, height=30)
        self.searchText = tkinter.StringVar(self.root)
        self.searchBar = Entry(self.titleCanvas, textvariable=self.searchText, font=('Arial', 16))
        self.titleCanvas.pack(side="top")
        
        self.titleCanvas.create_text(WINDOW_WIDTH-275, 0, text="\u2315", fill='gray', font=('Arial', 20), anchor='nw')
        self.titleCanvas.create_window(WINDOW_WIDTH-250, 3, window=self.searchBar, anchor='nw')

        self.scrollBar = Scrollbar(self.root, orient=VERTICAL)
        self.mainCanvas = Canvas(self.root, width=WINDOW_WIDTH, height=WINDOW_HEIGHT, yscrollcommand=self.scrollBar.set)
        self.scrollBar['command'] = self.mainCanvas.yview
        
        self.titleCanvas.pack(side="top")
        self.scrollBar.pack(side="right", fill="y")
        self.mainCanvas.pack(side="left")
        
        self.root.title("Helldivers 2 Audio Modder")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        
        self.rightClickMenu = Menu(self.root, tearoff=0)
        self.rightClickID = 0

        self.menu = Menu(self.root, tearoff=0)
        
        self.fileMenu = Menu(self.menu, tearoff=0)
        self.fileMenu.add_command(label="Load Archive", command=self.LoadArchive)
        self.fileMenu.add_command(label="Save Archive", command=self.SaveArchive)
        self.fileMenu.add_command(label="Write Patch", command=self.WritePatch)
        self.fileMenu.add_command(label="Import Patch File", command=self.LoadPatch)
        #self.fileMenu.add_command(label="Import .wems", command=self.LoadWems)
        self.wemsMenu = Menu(self.fileMenu, tearoff=0)
        self.fileMenu.add_cascade(label="Import .wems", menu=self.wemsMenu)
        
        
        self.editMenu = Menu(self.menu, tearoff=0)
        self.editMenu.add_command(label="Revert All Changes", command=self.RevertAll)
        
        self.dumpMenu = Menu(self.menu, tearoff=0)
        self.dumpMenu.add_command(label="Dump all as .wav", command=self.DumpAllAsWav)
        self.dumpMenu.add_command(label="Dump all as .wem", command=self.DumpAllAsWem)
        
        self.menu.add_cascade(label="File", menu=self.fileMenu)
        self.menu.add_cascade(label="Edit", menu=self.editMenu)
        self.menu.add_cascade(label="Dump", menu=self.dumpMenu)
        self.root.config(menu=self.menu)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.mainCanvas.bind_all("<Button-3>", self._on_rightclick)
        self.searchBar.bind("<Return>", self._on_enter)
        self.root.resizable(False, False)
        self.root.mainloop()
        
    def _on_enter(self, event):
        self.Search()
        
    def _on_rightclick(self, event):
        try:
            canvas = event.widget
            self.rightClickMenu.delete(0, "end")
            self.rightClickID = int(canvas.gettags("current")[0])
            if "bank" in canvas.gettags("current"):
                self.rightClickMenu.add_command(label="Copy File ID", command=self.CopyID)
                self.rightClickMenu.add_command(label="Import .wems to this bank", command=self.ImportToThisBank)
                self.rightClickMenu.tk_popup(event.x_root, event.y_root)
            elif "audio" in canvas.gettags("current"):
                self.rightClickMenu.add_command(label="Copy File ID", command=self.CopyID)
                self.rightClickMenu.add_command(label="Dump As .wem", command=self.DumpAsWem)
                self.rightClickMenu.add_command(label="Dump As .wav", command=self.DumpAsWav)
                self.rightClickMenu.tk_popup(event.x_root, event.y_root)
            elif "text" in canvas.gettags("current"):
                self.rightClickMenu.add_command(label="Copy File ID", command=self.CopyID)
                self.rightClickMenu.tk_popup(event.x_root, event.y_root)
        except (AttributeError, IndexError):
            pass
        finally:
            self.rightClickMenu.grab_release()
            
    def CopyID(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.rightClickID)
        self.root.update()
        
    def DumpAsWem(self):
        self.fileHandler.DumpAsWem(self.rightClickID)
        
    def DumpAsWav(self):
        self.fileHandler.DumpAsWav(self.rightClickID)
        
    def _on_mousewheel(self, event):
        self.mainCanvas.yview_scroll(int(-1*(event.delta/120)), 'units')
        
    def CreateStringSubtableRow(self, stringEntry):
            
        info = TableInfo()
        info.hidden = True
        info._type = TableInfo.BANK_WEM
    
        fillColor = "white"
        info.rectangles.append(self.mainCanvas.create_rectangle(0, 0, ROW_WIDTH-SUBROW_INDENT, ROW_HEIGHT, fill=fillColor))
        self.tableInfo[stringEntry.GetFileID()] = info
        text = tkinter.StringVar(self.mainCanvas)
        textBox = Entry(self.mainCanvas, width=50, textvariable=text, font=('Arial', 8))
        stringEntry.TextVariable = text
        textBox.insert(END, stringEntry.GetText())
        info.text.append(self.mainCanvas.create_window(0, 0, window=textBox, anchor='nw'))
        
        #create revert button
        revert = Button(self.mainCanvas, text='\u21b6', fg='black', font=('Arial', 14, 'bold'), image=self.fakeImage, compound='c', height=20, width=20)
        
        info.revertButton = self.mainCanvas.create_window(0, 0, window=revert, anchor='nw')
        info.buttons.append(info.revertButton)
        
        #create apply button
        apply = Button(self.mainCanvas, text="\u2713", fg='green', font=('Arial', 14, 'bold'), image=self.fakeImage, compound='c', height=20, width=20)
        def applyText(entry):
            entry.UpdateText()
        apply.configure(command=partial(applyText, stringEntry))
        info.buttons.append(self.mainCanvas.create_window(0, 0, window=apply, anchor='nw'))
        
    def CreateTableRow(self, tocEntry):
        
        info = TableInfo()
        
        if tocEntry.GetTypeID() == 6006249203084351385:
            name = tocEntry.Dep.Data.split('/')[-1]
            entryType = "bank"
        elif tocEntry.GetTypeID() == 979299457696010195:
            name = f"{tocEntry.GetFileID()}.text"
            entryType = "text"
    
        fillColor = "lawn green" if tocEntry.Modified else "white"
        info.rectangles.append(self.mainCanvas.create_rectangle(0, 0, ROW_WIDTH, ROW_HEIGHT, fill=fillColor, tags=(tocEntry.GetFileID(), entryType)))
        #info.rectangles.append(self.mainCanvas.create_rectangle(0, 0, 80, 30, fill=fillColor, tags=(tocEntry.GetFileID(), "rect")))
        
        

        info.text.append(self.mainCanvas.create_text(0, 0, text=name, fill='black', font=('Arial', 16, 'bold'), anchor='nw', tags=(tocEntry.GetFileID(), entryType)))
        #info.text.append(self.mainCanvas.create_text(0, 0, text=tocEntry.GetEntryIndex(), fill='black', font=('Arial', 16, 'bold'), anchor='nw', tag=tocEntry.GetFileID()))
        
        #create revert button
        revert = Button(self.mainCanvas, text='\u21b6', fg='black', font=('Arial', 14, 'bold'), command=partial(self.RevertAudio, tocEntry.GetFileID()), image=self.fakeImage, compound='c', height=20, width=20)
        info.revertButton = self.mainCanvas.create_window(0, 0, window=revert, anchor='nw', tag=tocEntry.GetFileID())
        info.buttons.append(info.revertButton)
        
        if tocEntry.GetTypeID() == 5785811756662211598:
            info._type = TableInfo.WEM
            #create play button
            play = Button(self.mainCanvas, text= '\u23f5', fg='green', font=('Arial', 14, 'bold'), image=self.fakeImage, compound='c', height=20, width=20)
            def resetButtonIcon(button):
                button.configure(text= '\u23f5', fg='green')
            def pressButton(button, fileID, callback):
                if button['text'] == '\u23f9':
                    button.configure(text= '\u23f5', fg='green')
                else:
                    button.configure(text= '\u23f9', fg='red')
                self.PlayAudio(fileID, callback)
            play.configure(command=partial(pressButton, play, tocEntry.GetFileID(), partial(resetButtonIcon, play)))
            info.buttons.append(self.mainCanvas.create_window(0, 0, window=play, anchor='nw', tag=tocEntry.GetFileID()))
        elif tocEntry.GetTypeID() == 6006249203084351385:
            def revertBank(bankId):
                for audio in self.fileHandler.GetWwiseBanks()[bankId].GetContent():
                    audio.RevertModifications()
                self.UpdateTableEntries()
                self.Update()
            revert.configure(command=partial(revertBank, tocEntry.GetFileID()))        
            info._type = TableInfo.BANK
            #create expand button
            def pressButton(button, bank):
                if button['text'] == "v":
                    button.configure(text=">")
                    #hide
                    for source in bank.GetContent():
                        self.UpdateBankSubtableEntry(bank, source, action="hide")
                else:
                    button.configure(text="v")
                    #show
                    for source in bank.GetContent():
                        self.UpdateBankSubtableEntry(bank, source, action="show")
                self.Update()
            expand = Button(self.mainCanvas, text=">", font=('Arial', 14, 'bold'), height=20, width=20, image=self.fakeImage, compound='c')
            expand.configure(command=partial(pressButton, expand, tocEntry))
            info.buttons.append(self.mainCanvas.create_window(0, 0, window=expand, anchor='nw', tag=tocEntry.GetFileID()))
        elif tocEntry.GetTypeID() == 979299457696010195:
            #create expand button
            def pressButton(button, textId):
                if button['text'] == "v":
                    button.configure(text=">")
                    #hide
                    for entry in self.fileHandler.GetStrings()[textId].StringEntries.values():
                        self.UpdateTableEntry(entry, action="hide")
                else:
                    button.configure(text="v")
                    #show
                    for entry in self.fileHandler.GetStrings()[textId].StringEntries.values():
                        self.UpdateTableEntry(entry, action="show")
                self.Update()
            expand = Button(self.mainCanvas, text=">", font=('Arial', 14, 'bold'), height=20, width=20, image=self.fakeImage, compound='c')
            expand.configure(command=partial(pressButton, expand, tocEntry.GetFileID()))
            info.buttons.append(self.mainCanvas.create_window(0, 0, window=expand, anchor='nw', tag=tocEntry.GetFileID()))

        self.tableInfo[tocEntry.GetFileID()] = info
        
    def CreateBankSubtableRow(self, audioSource, bank):
    
        info = TableInfo()
        info.hidden = True
        info._type = TableInfo.BANK_WEM
    
        fillColor = "lawn green" if audioSource.Modified else "white"
        info.rectangles.append(self.mainCanvas.create_rectangle(0, 0, ROW_WIDTH-SUBROW_INDENT, ROW_HEIGHT, fill=fillColor, tags=(audioSource.GetFileID(), "audio")))
        name = str(audioSource.GetFileID()) + ".wem"
        info.text.append(self.mainCanvas.create_text(0, 0, text=name, fill='black', font=('Arial', 16, 'bold'), anchor='nw', tags=(audioSource.GetFileID(), "audio")))
        
        #type (sound, music track)
        
        #if music track: also add duration, startTrim, endTrim?
        #need function to update the hierarchy. Need some way to get hId tho (id of hirc entry), not the audio source's Id.
        #little bit scared that two music tracks might include the same audio source
        
        #create revert button
        revert = Button(self.mainCanvas, text='\u21b6', fg='black', font=('Arial', 14, 'bold'), command=partial(self.RevertAudio, f"{bank.GetFileID()}-{audioSource.GetShortId()}"), image=self.fakeImage, compound='c', height=20, width=20)
        
        info.revertButton = self.mainCanvas.create_window(0, 0, window=revert, anchor='nw', tag=audioSource.GetFileID())
        info.buttons.append(info.revertButton)
        
        #create play button
        play = Button(self.mainCanvas, text= '\u23f5', fg='green', font=('Arial', 14, 'bold'), image=self.fakeImage, compound='c', height=20, width=20)
        def resetButtonIcon(button):
            button.configure(text= '\u23f5', fg='green')
        def pressButton(button, fileID, callback):
            if button['text'] == '\u23f9':
                button.configure(text= '\u23f5', fg='green')
            else:
                button.configure(text= '\u23f9', fg='red')
            self.PlayAudio(fileID, callback)
            
        play.configure(command=partial(pressButton, play, f"{bank.GetFileID()}-{audioSource.GetShortId()}", partial(resetButtonIcon, play)))
        info.buttons.append(self.mainCanvas.create_window(0, 0, window=play, anchor='nw', tag=f"{bank.GetFileID()}-{audioSource.GetShortId()}"))
        self.tableInfo[f"{bank.GetFileID()}-{audioSource.GetShortId()}"] = info
            
    def CreateTable(self):
        for child in self.mainCanvas.winfo_children():
            child.destroy()
        self.mainCanvas.delete("all")
        self.tableInfo.clear()
        draw_y = 0
        bankDict = self.fileHandler.GetWwiseBanks()
        for key in bankDict.keys():
            bank = bankDict[key]
            self.CreateTableRow(bank)
            draw_y += ROW_HEIGHT
            for item in bank.GetContent(): #need a way to show the resource ID for the streams and the short ID for the bank data, for backwards compatibility. Maybe do both? No way to tell which I need from just the AudioSource. I'd like to avoid looking through the hierarchy
                self.CreateBankSubtableRow(item, bank)
                draw_y += ROW_HEIGHT
        for entry in self.fileHandler.GetStrings().values():
            self.CreateTableRow(entry)
            for stringEntry in entry.StringEntries.values():
                self.CreateStringSubtableRow(stringEntry)
        self.mainCanvas.configure(scrollregion=(0,0,500,draw_y + 5))
    
    def UpdateTableEntry(self, item, action="update"):
        fileID = item.GetFileID()
        try:
            info = self.tableInfo[fileID]
        except:
            return
        if action == "update":
            info.modified = item.Modified
        elif action == "show":
            info.hidden = False
        elif action == "hide":
            info.hidden = True
            
    def UpdateBankSubtableEntry(self, bank, source, action="update"):
        fileID = f"{bank.GetFileID()}-{source.GetShortId()}"
        try:
            info = self.tableInfo[fileID]
        except:
            return
        if action == "update":
            info.modified = source.Modified
        elif action == "show":
            info.hidden = False
        elif action == "hide":
            info.hidden = True
            
    def UpdateTableEntries(self):
        streamDict = self.fileHandler.GetWwiseStreams()
        for stream in streamDict.values():
            self.UpdateTableEntry(stream)
        bankDict = self.fileHandler.GetWwiseBanks()
        for bank in bankDict.values():
            self.UpdateTableEntry(bank)
            for source in bank.GetContent():
                self.UpdateBankSubtableEntry(bank, source)
                
    def DrawBankSubtableRow(self, bank, source, x, y):
        try:
            rowInfo = self.tableInfo[f"{bank.GetFileID()}-{source.GetShortId()}"]
        except:
            return
        if not rowInfo.hidden:
            x += SUBROW_INDENT
            for button in rowInfo.buttons:
                self.mainCanvas.moveto(button, x, y+3)
                x += 30
            for index, rect in enumerate(rowInfo.rectangles):
                if rowInfo.modified:
                    self.mainCanvas.itemconfigure(rect, fill="lawn green")
                else:
                    self.mainCanvas.itemconfigure(rect, fill="white")
                self.mainCanvas.moveto(rect, x, y)
                self.mainCanvas.moveto(rowInfo.text[index], x + 5, y+5)
                x += (self.mainCanvas.coords(rect)[2]-self.mainCanvas.coords(rect)[0])
            if not rowInfo.modified:
                try:
                    self.mainCanvas.moveto(rowInfo.revertButton, -1000, -1000)
                except:
                    pass
        else:
            for button in rowInfo.buttons:
                self.mainCanvas.moveto(button, -1000, -1000)
            for rect in rowInfo.rectangles:
                self.mainCanvas.moveto(rect, -1000, -1000)
            for text in rowInfo.text:
                self.mainCanvas.moveto(text, -1000, -1000)
            
    def DrawTableRow(self, item, x, y):
        try:
            rowInfo = self.tableInfo[item.GetFileID()]
        except:
            return
        if not rowInfo.hidden:
            if rowInfo._type == TableInfo.BANK_WEM: x += SUBROW_INDENT
            for button in rowInfo.buttons:
                self.mainCanvas.moveto(button, x, y+3)
                x += 30
            for index, rect in enumerate(rowInfo.rectangles):
                if rowInfo.modified:
                    self.mainCanvas.itemconfigure(rect, fill="lawn green")
                else:
                    self.mainCanvas.itemconfigure(rect, fill="white")
                self.mainCanvas.moveto(rect, x, y)
                self.mainCanvas.moveto(rowInfo.text[index], x + 5, y+5)
                x += (self.mainCanvas.coords(rect)[2]-self.mainCanvas.coords(rect)[0])
            if not rowInfo.modified:
                try:
                    self.mainCanvas.moveto(rowInfo.revertButton, -1000, -1000)
                except:
                    pass
        else:
            for button in rowInfo.buttons:
                self.mainCanvas.moveto(button, -1000, -1000)
            for rect in rowInfo.rectangles:
                self.mainCanvas.moveto(rect, -1000, -1000)
            for text in rowInfo.text:
                self.mainCanvas.moveto(text, -1000, -1000)
        
    def RedrawTable(self):
        draw_y = 0
        draw_x = 0
        bankDict = self.fileHandler.GetWwiseBanks()
        for bank in bankDict.values():
            draw_x = 0
            self.DrawTableRow(bank, draw_x, draw_y)
            if not self.tableInfo[bank.GetFileID()].hidden:
                draw_y += 30
            for item in bank.GetContent():
                self.DrawBankSubtableRow(bank, item, draw_x, draw_y)
                if not self.tableInfo[str(bank.GetFileID()) + "-" + str(item.GetShortId())].hidden:
                    draw_y += 30
        for entry in self.fileHandler.GetStrings().values():
            self.DrawTableRow(entry, draw_x, draw_y)
            if not self.tableInfo[entry.GetFileID()].hidden: draw_y += 30
            for item in entry.StringEntries.values():
                self.DrawTableRow(item, draw_x, draw_y)
                if not self.tableInfo[item.GetFileID()].hidden:
                    draw_y += 30
        self.mainCanvas.configure(scrollregion=(0,0,1280,draw_y + 5))
        

    def Search(self):
        text = self.searchText.get()
        for item in self.tableInfo.values():
            item.hidden = True
        for audio in self.fileHandler.GetAudio().values():
            name = str(audio.GetFileID()) + ".wem"
            if name.startswith(text) or name.endswith(text):
                for subscriber in audio.Subscribers:
                    self.UpdateTableEntry(subscriber, action="show")
                    self.UpdateBankSubtableEntry(subscriber, audio, action="show")
        bankDict = self.fileHandler.GetWwiseBanks()
        for bank in bankDict.values():
            name = str(bank.GetFileID()) + ".bnk"
            if name.startswith(text) or name.endswith(text):
                self.UpdateTableEntry(bank, action="show")
        for item in self.fileHandler.GetStrings().values():
            name = str(item.GetFileID()) + ".text"
            if name.startswith(text) or name.endswith(text):
                self.UpdateTableEntry(item, action="show")
            for entry in item.StringEntries.values():
                name = entry.TextVariable.get()
                if text in name:
                    self.UpdateTableEntry(entry, action="show")
                    self.UpdateTableEntry(entry.Parent, action="show")
        self.RedrawTable()
    
    def Update(self):
        self.RedrawTable()
        
    def UpdateImportMenu(self):
        self.wemsMenu.delete(0, "end")
        for bank in self.fileHandler.GetWwiseBanks().values():
            self.wemsMenu.add_command(label=bank.Dep.Data, command=partial(self.LoadWems, bank.GetFileID()))
    
    def ImportToThisBank(self):
        self.LoadWems(self.rightClickID)
    
    def LoadArchive(self):
        self.soundHandler.KillSound()
        if self.fileHandler.LoadArchiveFile():
            self.CreateTable()
            self.Update()
            self.UpdateImportMenu()
        
    def SaveArchive(self):
        self.soundHandler.KillSound()
        self.fileHandler.SaveArchiveFile()
        
    def LoadWems(self, targetBankId):
        self.soundHandler.KillSound()
        self.fileHandler.LoadWems(targetBankId)
        self.UpdateTableEntries()
        self.Update()
        
    def DumpAllAsWem(self):
        self.soundHandler.KillSound()
        self.fileHandler.DumpAllAsWem()
        
    def DumpAllAsWav(self):
        self.soundHandler.KillSound()
        self.fileHandler.DumpAllAsWav()
        
    def PlayAudio(self, fileID, callback):
        self.soundHandler.PlayAudio(fileID, self.fileHandler.GetAudioByID(fileID).GetData(), callback)
        
    def RevertAudio(self, fileID):
        self.soundHandler.KillSound()
        self.fileHandler.RevertAudio(fileID)
        self.UpdateTableEntries()
        self.Update()
        
    def RevertAll(self):
        self.soundHandler.KillSound()
        self.fileHandler.RevertAll()
        self.UpdateTableEntries()
        self.Update()
        
    def WritePatch(self):
        self.soundHandler.KillSound()
        self.fileHandler.WritePatch()
        
    def LoadPatch(self):
        self.soundHandler.KillSound()
        if self.fileHandler.LoadPatch():
            self.UpdateTableEntries()
            self.Update()
    
def exitHandler():
    soundHandler.audio.terminate()
    

if __name__ == "__main__":
    if "Windows" in platform.platform():
        _GAME_FILE_LOCATION = LookForSteamInstallWindows()
    soundHandler = SoundHandler()
    fileHandler = FileHandler()
    atexit.register(exitHandler)
    window = MainWindow(fileHandler, soundHandler)