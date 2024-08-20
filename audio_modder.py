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
import time
import atexit
from itertools import takewhile
import copy
import numpy

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
    
def SortContent(content):
    return content.FileID
    
class AudioData:
    
    def __init__(self):
        self.FileID = 0
        self.Data = b""
        self.Offset = 0
        self.Size = 0
        self.Modified = False
        self.Data_OLD = b""
        self.Subscribers = set()
        
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
        
        
    def GetData(self):
        return self.Data
        
    def GetFileID(self):
        return self.FileID
        
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
        self.Offset             = stream.tell()
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
        return (self.FileID.to_bytes(8, byteorder='little')
                + self.TypeID.to_bytes(8, byteorder='little')
                + self.TocDataOffset.to_bytes(8, byteorder='little')
                + self.StreamOffset.to_bytes(8, byteorder='little')
                + self.GpuResourceOffset.to_bytes(8, byteorder='little')
                + self.Unknown1.to_bytes(8, byteorder='little')
                + self.Unknown2.to_bytes(8, byteorder='little')
                + self.TocDataSize.to_bytes(4, byteorder='little')
                + self.StreamSize.to_bytes(4, byteorder='little')
                + self.GpuResourceSize.to_bytes(4, byteorder='little')
                + self.Unknown3.to_bytes(4, byteorder='little')
                + self.Unknown4.to_bytes(4, byteorder='little')
                + self.EntryIndex.to_bytes(4, byteorder='little'))
                
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
                
class Subscriber:
    def __init__(self):
        pass
        
    def Update(self, content):
        pass
        
    def Rebuild(self):
        pass
        
    def RaiseModified(self):
        pass
        
    def LowerModified(self):
        pass
    
class DataIndexEntry(Subscriber):

    def __init__(self):
        self.Size = 0
        self.Offset = 0
        self.Content = None
        self.Modified = False
        self.Parent = None
        
    def RaiseModified(self):
        self.Modified = True
        
    def LowerModified(self):
        self.Modified = False
        
    def GetFileID(self):
        return str(self.Parent.GetFileID()) + "-" + str(self.Content.FileID)
        
    
class WwiseBank(Subscriber):
    
    def __init__(self):
        self.DataIndex = {}
        self.DataSize = 0
        self.BankHeader = b""
        self.TocDataHeader = b""
        self.BankPostData = b""
        self.Modified = False
        self.TocHeader = None
        self.Dep = None
        self.ModifiedCount = 0
        
    def AddContent(self, content):
        content.Subscribers.add(self)
        didxEntry = DataIndexEntry()
        didxEntry.Size = content.Size
        didxEntry.Offset = _16ByteAlign(self.DataSize)
        didxEntry.Content = content
        didxEntry.Parent = self
        content.Subscribers.add(didxEntry)
        self.DataIndex[content.GetFileID()] = didxEntry
        self.DataSize += _16ByteAlign(didxEntry.Size)
        bankSize = self.DataSize + 8 + len(self.BankHeader) + len(self.BankPostData) + 12*len(self.DataIndex) + 8
        self.TocHeader.TocDataSize = bankSize + 16
        self.TocDataHeader[4:8] = bankSize.to_bytes(4, byteorder='little')
        
    def RemoveContent(self, content):
        try:
            content.Subscribers.remove(self)
            content.Subscribers.remove(self.DataIndex[content.GetFileID()])
        except:
            pass
            
        try:
            del self.DataIndex[content.GetFileID()]
        except:
            pass

            
    def Update(self, content, recomputeOffsets=False):
        entry = self.DataIndex[content.GetFileID()]
        self.DataSize -= _16ByteAlign(entry.Size)
        entry.Size = len(content.GetData())
        self.DataSize +=  _16ByteAlign(entry.Size)
        bankSize = self.DataSize + 8 + len(self.BankHeader) + len(self.BankPostData) + 12*len(self.DataIndex) + 8
        self.TocHeader.TocDataSize = bankSize + 16
        self.TocDataHeader[4:8] = bankSize.to_bytes(4, byteorder='little')
        if recomputeOffsets:
            self.Rebuild()
            
    def Rebuild(self):
        offset = 0
        for entry in self.DataIndex.values():
            entry.Offset = offset
            offset += _16ByteAlign(entry.Size)
            
    def GetContent(self):
        return [entry.Content for entry in self.DataIndex.values()]
        
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
        data = bytearray()
        data += self.BankHeader
        
        if len(self.DataIndex) > 0:
            dataSection = "DATA".encode('utf-8') + self.DataSize.to_bytes(4, byteorder='little')
            didxSectionSize = 12*len(self.DataIndex)
            didxSection = "DIDX".encode('utf-8') + didxSectionSize.to_bytes(4, byteorder='little')
            for fileID, entry in self.DataIndex.items():
                didxSection += fileID.to_bytes(4, byteorder='little')
                didxSection += entry.Offset.to_bytes(4, byteorder='little')
                didxSection += entry.Size.to_bytes(4, byteorder='little')
                dataSection += PadTo16ByteAlign(entry.Content.GetData())
            data += didxSection
            data += dataSection
        
        data += self.BankPostData
        return data 
            
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
        self.IDs = b''
        self.StringEntries = {}
        self.Language = ""
        self.Modified = False
        
    def SetData(self, data):
        numEntries = int.from_bytes(data[8:12], byteorder='little')
        self.Language = "English(US)"
        idStart = 16
        offsetStart = idStart + 4 * numEntries
        dataStart = offsetStart + 4 * numEntries
        ids = data[idStart:offsetStart]
        offsets = data[offsetStart:dataStart]
        self.IDs = ids
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
        stream.write(b'\x57\x7B\xf9\x03')
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
        self.numFiles = len(self.WwiseStreams) + len(self.WwiseBanks) + len(self.TextData)
        self.numTypes = 0
        if len(self.WwiseStreams) > 0: self.numTypes += 1
        if len(self.WwiseBanks) > 0: self.numTypes += 1
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
            #tocFile.seek(bank.Dep.Offset)
            #tocFile.write(bank.Dep.GetData())
            
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
        if len(self.WwiseBanks) > 0: self.numTypes += 1
        if len(self.TextData) > 0: self.numTypes += 1
        self.numFiles = len(self.WwiseStreams) + len(self.WwiseBanks) + len(self.TextData)
        streamOffset = 0
        tocOffset = 80 + self.numTypes * 32 + 80 * self.numFiles
        for key, value in self.WwiseStreams.items():
            value.TocHeader.StreamOffset = streamOffset
            value.TocHeader.TocDataOffset = tocOffset
            streamOffset += _16ByteAlign(value.TocHeader.StreamSize)
            tocOffset += _16ByteAlign(value.TocHeader.TocDataSize)
            
        for key, value in self.WwiseBanks.items():
            value.TocHeader.TocDataOffset = tocOffset
            tocOffset += _16ByteAlign(value.DataSize)
            
        for key, value in self.TextData.items():
            value.Update()
            value.TocHeader.TocDataOffset = tocOffset
            tocOffset += _16ByteAlign(value.TocHeader.TocDataSize)
            
        
    def Load(self, tocFile, streamFile):
        self.WwiseStreams = {}
        self.WwiseBanks = {}
        self.AudioData = {}
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
                audio = AudioData()
                entry = WwiseStream()
                entry.TocHeader = tocHeader
                tocFile.seek(tocHeader.TocDataOffset)
                entry.TocData = tocFile.read(tocHeader.TocDataSize)
                streamFile.seek(tocHeader.StreamOffset)
                audio.SetData(streamFile.read(tocHeader.StreamSize), notifySubscribers=False, setModified=False)
                audio.FileID = tocHeader.FileID
                audio.Offset = tocHeader.StreamOffset
                audio.Size = tocHeader.StreamSize
                entry.SetContent(audio)
                self.AudioData[audio.GetFileID()] = audio
                self.WwiseStreams[entry.GetFileID()] = entry
            elif tocHeader.TypeID == 6006249203084351385:
                entry = WwiseBank()
                entry.TocHeader = tocHeader
                tocDataOffset = tocHeader.TocDataOffset
                tocDataSize = tocHeader.TocDataSize
                tocFile.seek(tocDataOffset)
                entry.TocDataHeader = tocFile.read(16)
                tag = tocFile.read(4).decode('utf-8')
                size = tocFile.uint32Read()
                if tag != "BKHD":
                    print("Error reading .bnk, invalid header")
                    continue
                entry.BankHeader = tag.encode('utf-8') + size.to_bytes(4, byteorder='little') + tocFile.read(size)
                
                #DIDX section
                try:
                    tag = tocFile.read(4).decode('utf-8')
                    size = tocFile.uint32Read()
                except: #skip
                    continue
                if tag != "DIDX": #skip empty .bnk
                    continue
                didxStart = tocFile.tell()
                dataStart = didxStart + size + 8
                for x in range(int(size/12)):
                    tocFile.seek(didxStart + 12*x)
                    audioID = tocFile.uint32Read()
                    audioOffset = tocFile.uint32Read()
                    audioSize = tocFile.uint32Read()
                    if audioID not in self.AudioData.keys():
                        audio = AudioData()
                        audio.FileID = audioID
                        audio.Offset = audioOffset
                        audio.Size = audioSize
                        tocFile.seek(dataStart + audio.Offset)
                        audio.SetData(tocFile.read(audio.Size), notifySubscribers=False, setModified=False)
                        self.AudioData[audioID] = audio
                    entry.AddContent(self.AudioData[audioID])
                tocFile.seek(dataStart - 4)
                size = tocFile.uint32Read()
                tocFile.seek(tocFile.tell() + size)
                self.WwiseBanks[entry.GetFileID()] = entry
                #Any other sections (i.e. HIRC)
                entry.BankPostData = tocFile.read(tocDataSize + tocDataOffset - tocFile.tell()) #for now just store everything past the end of the data section
            elif tocHeader.TypeID == 12624162998411505776: #wwise dep
                dep = WwiseDep()
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
                self.KillSound()
                self.audioID = -1
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
        self.root.geometry("410x45")
        self.root.attributes('-topmost', True)
        self.progressBar = tkinter.ttk.Progressbar(self.root, orient=HORIZONTAL, length=400, mode="determinate", maximum=self.maxProgress)
        self.progressBarText = Text(self.root)
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
        
class FileHandler:

    def __init__(self):
        self.FileReader = FileReader()
        
    def RevertAll(self):
        for audio in self.FileReader.AudioData.values():
            audio.RevertModifications()
        
    def RevertAudio(self, fileID):
        audio = self.GetAudioByID(fileID)
        audio.RevertModifications()
        
    def DumpAsWem(self, fileID):
        outputFile = filedialog.asksaveasfile(mode='wb', title="Save As", initialfile=(str(fileID)+".wem"), defaultextension=".wem", filetypes=[("Wwise Audio", "*.wem")])
        if outputFile is None: return
        outputFile.write(self.FileReader.AudioData[fileID].GetData())
        
    def DumpAsWav(self, fileID):
        outputFile = filedialog.asksaveasfilename(title="Save As", initialfile=(str(fileID)+".wav"), defaultextension=".wav", filetypes=[("Wav Audio", "*.wav")])
        if outputFile == "": return
        savePath = os.path.splitext(outputFile)[0]
        with open(f"{savePath}.wem", 'wb') as f:
            f.write(self.FileReader.AudioData[fileID].GetData())
        subprocess.run(["vgmstream-win64/vgmstream-cli.exe", "-o", f"{savePath}.wav", f"{savePath}.wem"], stdout=subprocess.DEVNULL)
        os.remove(f"{savePath}.wem")

    def DumpAllAsWem(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        
        progressWindow = ProgressWindow(title="Dumping Files", maxProgress=len(self.FileReader.AudioData))
        progressWindow.Show()
        
        if os.path.exists(folder):
            for audio in self.FileReader.AudioData.values():
                savePath = os.path.join(folder, str(audio.GetFileID()))
                progressWindow.SetText("Dumping " + os.path.basename(savePath) + ".wem")
                with open(savePath+".wem", "wb") as f:
                    f.write(audio.GetData())
                progressWindow.Step()
        else:
            print("Invalid folder selected, aborting dump")
            
        progressWindow.Destroy()
    
    def DumpAllAsWav(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")

        progressWindow = ProgressWindow(title="Dumping Files", maxProgress=len(self.FileReader.AudioData))
        progressWindow.Show()
        
        if os.path.exists(folder):
            for audio in self.FileReader.AudioData.values():
                savePath = os.path.join(folder, str(audio.GetFileID()))
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
            self.FileReader.ToFile(folder)
        else:
            print("Invalid folder selected, aborting save")
            
    def GetAudioByID(self, fileID):
        return self.FileReader.AudioData[fileID]
        
    def GetWwiseStreams(self):
        return self.FileReader.WwiseStreams
        
    def GetWwiseBanks(self):
        return self.FileReader.WwiseBanks
        
    def GetAudio(self):
        return self.FileReader.AudioData
        
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
            
            
    def LoadPatch(self):
        patchFileReader = FileReader()
        patchFile = filedialog.askopenfilename(title="Choose patch file to import")
        if os.path.splitext(patchFile)[1] in (".stream", ".gpu_resources"):
            patchFile = os.path.splitext(patchFile)[0]
        if os.path.exists(patchFile):
            patchFileReader.FromFile(patchFile)
        else:
            print("Invalid file selected, aborting load")
            return
            
        progressWindow = ProgressWindow(title="Loading Files", maxProgress=len(patchFileReader.AudioData))
        progressWindow.Show()
        
        subscribers = set()
        
        for newAudio in patchFileReader.AudioData.values():
            progressWindow.SetText("Loading "+str(newAudio.GetFileID()))
            oldAudio = self.GetAudioByID(newAudio.GetFileID())
            for item in oldAudio.Subscribers:
                subscribers.add(item)
            oldAudio.SetData(newAudio.GetData())
            progressWindow.Step()
                
        for entry in subscribers:
            entry.Rebuild()
        
        progressWindow.Destroy()

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
            patchedFileReader.AudioData = self.FileReader.AudioData
            patchedFileReader.WwiseBanks = {}
            patchedFileReader.WwiseStreams = {}
            patchedFileReader.TextData = {}
            
            for key, value in self.FileReader.WwiseStreams.items():
                if value.Modified:
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

    def LoadWems(self):
        wems = filedialog.askopenfilenames(title="Choose .wem files to import")
        
        progressWindow = ProgressWindow(title="Loading Files", maxProgress=len(wems))
        progressWindow.Show()
        
        subscribers = set()
        
        for file in wems:
            progressWindow.SetText("Loading "+os.path.basename(file))
            fileID = self.GetFileNumberPrefix(os.path.basename(file))
            audio = self.GetAudioByID(fileID)
            for item in audio.Subscribers:
                subscribers.add(item)
            with open(file, 'rb') as f:
                audio.SetData(f.read())
            progressWindow.Step()
        
        progressWindow.Destroy()
        progressWindow = ProgressWindow(title="Loading Files", maxProgress=len(subscribers))
        progressWindow.Show()
        progressWindow.SetText("Rebuilding soundbanks")
        
        for entry in subscribers:
            entry.Rebuild()
        
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
        self.expandedBanks = set()
        self.tableInfo = {}
        
        self.root = Tk()
        
        self.fakeImage = tkinter.PhotoImage(width=1, height=1)
        
        self.titleCanvas = Canvas(self.root, width=500, height=30)
        self.searchText = tkinter.StringVar(self.root)
        self.searchBar = Entry(self.titleCanvas, textvariable=self.searchText, font=('Arial', 16))
        self.searchText.trace("w", lambda name, index, mode, searchText=self.searchText: self.Search(searchText))
        self.titleCanvas.pack(side="top")
        
        self.titleCanvas.create_text(230, 0, text="\u2315", fill='gray', font=('Arial', 20), anchor='nw')
        self.titleCanvas.create_window(250, 3, window=self.searchBar, anchor='nw')

        self.scrollBar = Scrollbar(self.root, orient=VERTICAL)
        self.mainCanvas = Canvas(self.root, width=500, height=720, yscrollcommand=self.scrollBar.set)
        self.scrollBar['command'] = self.mainCanvas.yview
        
        self.titleCanvas.pack(side="top")
        self.scrollBar.pack(side="right", fill="y")
        self.mainCanvas.pack(side="left")
        
        self.root.title("Helldivers 2 Audio Modder")
        self.root.geometry("500x720")
        
        self.rightClickMenu = Menu(self.root, tearoff=0)
        self.rightClickMenu.add_command(label="Copy File ID", command=self.CopyID)
        self.rightClickMenu.add_command(label="Dump As .wem", command=self.DumpAsWem)
        self.rightClickMenu.add_command(label="Dump As .wav", command=self.DumpAsWav)
        self.rightClickID = 0

        self.menu = Menu(self.root, tearoff=0)
        
        self.fileMenu = Menu(self.menu, tearoff=0)
        self.fileMenu.add_command(label="Load Archive", command=self.LoadArchive)
        self.fileMenu.add_command(label="Save Archive", command=self.SaveArchive)
        self.fileMenu.add_command(label="Write Patch", command=self.WritePatch)
        self.fileMenu.add_command(label="Import Patch File", command=self.LoadPatch)
        self.fileMenu.add_command(label="Import .wems", command=self.LoadWems)
        
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
        self.root.resizable(False, False)
        self.root.mainloop()
        
    def _on_rightclick(self, event):
        try:
            canvas = event.widget
            self.rightClickID = int(canvas.gettags("current")[0])
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
        info.rectangles.append(self.mainCanvas.create_rectangle(0, 0, 305, 30, fill=fillColor))
        #info.text.append(self.mainCanvas.create_text(0, 0, text=stringEntry.GetText(), fill='black', font=('Arial', 16, 'bold'), anchor='nw'))
        self.tableInfo[stringEntry.GetFileID()] = info
        text = tkinter.StringVar(self.mainCanvas)
        textBox = Entry(self.mainCanvas, width=50, textvariable=text, font=('Arial', 8))
        stringEntry.TextVariable = text
        textBox.insert(END, stringEntry.GetText())
        #self.searchBar = Entry(self.titleCanvas, textvariable=self.searchText, font=('Arial', 16))
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
    
        fillColor = "lawn green" if tocEntry.Modified else "white"
        info.rectangles.append(self.mainCanvas.create_rectangle(0, 0, 335, 30, fill=fillColor, tags=(tocEntry.GetFileID(), "rect")))
        info.rectangles.append(self.mainCanvas.create_rectangle(0, 0, 80, 30, fill=fillColor, tags=(tocEntry.GetFileID(), "rect")))
        
        name = str(tocEntry.GetFileID())
        if tocEntry.GetTypeID() == 5785811756662211598:
            name = name + ".wem"
        elif tocEntry.GetTypeID() == 6006249203084351385:
            name = name + ".bnk"
        elif tocEntry.GetTypeID() == 979299457696010195:
            name = name + ".text"
        if tocEntry.GetTypeID() == 6006249203084351385:
            try:
                name = tocEntry.Dep.Data.split('/')[-1]
            except:
                pass

        info.text.append(self.mainCanvas.create_text(0, 0, text=name, fill='black', font=('Arial', 16, 'bold'), anchor='nw', tags=(tocEntry.GetFileID(), "name")))
        info.text.append(self.mainCanvas.create_text(0, 0, text=tocEntry.GetEntryIndex(), fill='black', font=('Arial', 16, 'bold'), anchor='nw', tag=tocEntry.GetFileID()))
        
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
            def pressButton(button, bankId):
                if button['text'] == "v":
                    button.configure(text=">")
                    #hide
                    for entry in self.fileHandler.GetWwiseBanks()[bankId].DataIndex.values():
                        self.UpdateTableEntry(entry, action="hide")
                else:
                    button.configure(text="v")
                    #show
                    for entry in self.fileHandler.GetWwiseBanks()[bankId].DataIndex.values():
                        self.UpdateTableEntry(entry, action="show")
                self.Update()
            expand = Button(self.mainCanvas, text=">", font=('Arial', 14, 'bold'), height=20, width=20, image=self.fakeImage, compound='c')
            expand.configure(command=partial(pressButton, expand, tocEntry.GetFileID()))
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
        
    def CreateBankSubtableRow(self, bankWem, parent):
    
        info = TableInfo()
        info.hidden = True
        info._type = TableInfo.BANK_WEM
    
        fillColor = "lawn green" if bankWem.Modified else "white"
        info.rectangles.append(self.mainCanvas.create_rectangle(0, 0, 305, 30, fill=fillColor, tags=(bankWem.GetFileID(), "rect")))
        name = str(bankWem.GetFileID()) + ".wem"
        info.text.append(self.mainCanvas.create_text(0, 0, text=name, fill='black', font=('Arial', 16, 'bold'), anchor='nw', tags=(bankWem.GetFileID(), "name")))
        
        
        #create revert button
        revert = Button(self.mainCanvas, text='\u21b6', fg='black', font=('Arial', 14, 'bold'), command=partial(self.RevertAudio, bankWem.GetFileID()), image=self.fakeImage, compound='c', height=20, width=20)
        
        info.revertButton = self.mainCanvas.create_window(0, 0, window=revert, anchor='nw', tag=bankWem.GetFileID())
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
        play.configure(command=partial(pressButton, play, bankWem.GetFileID(), partial(resetButtonIcon, play)))
        info.buttons.append(self.mainCanvas.create_window(0, 0, window=play, anchor='nw', tag=bankWem.GetFileID()))
        self.tableInfo[str(parent.GetFileID())+'-'+str(bankWem.GetFileID())] = info
            
    def CreateTable(self):
        for child in self.mainCanvas.winfo_children():
            child.destroy()
        self.mainCanvas.delete("all")
        self.tableInfo = {}
        draw_y = 0
        streamDict = self.fileHandler.GetWwiseStreams()
        for key in streamDict.keys():
            stream = streamDict[key]
            name = str(stream.GetFileID()) + ".wem"
            self.CreateTableRow(stream)
            draw_y += 30
        bankDict = self.fileHandler.GetWwiseBanks()
        for key in bankDict.keys():
            bank = bankDict[key]
            self.CreateTableRow(bank)
            draw_y += 30
            for item in bank.GetContent():
                self.CreateBankSubtableRow(item, bank)
                draw_y += 30
        for entry in self.fileHandler.GetStrings().values():
            self.CreateTableRow(entry)
            for stringEntry in entry.StringEntries.values():
                self.CreateStringSubtableRow(stringEntry)
        self.mainCanvas.configure(scrollregion=(0,0,500,draw_y + 5))
    
    def UpdateTableEntry(self, item, action="update"):
        fileID = item.GetFileID()
        info = self.tableInfo[fileID]
        if action == "update":
            info.modified = item.Modified
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
            for entry in bank.DataIndex.values():
                self.UpdateTableEntry(entry)
            
    def DrawTableRow(self, item, x, y):
        rowInfo = self.tableInfo[item.GetFileID()]
        if not rowInfo.hidden:
            if rowInfo._type == TableInfo.BANK_WEM: x += 30
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
        streamDict = self.fileHandler.GetWwiseStreams()
        for stream in streamDict.values():
            draw_x = 0
            self.DrawTableRow(stream, draw_x, draw_y)
            if not self.tableInfo[stream.GetFileID()].hidden: draw_y += 30
        bankDict = self.fileHandler.GetWwiseBanks()
        for bank in bankDict.values():
            draw_x = 0
            self.DrawTableRow(bank, draw_x, draw_y)
            if not self.tableInfo[bank.GetFileID()].hidden: draw_y += 30
            for item in bank.DataIndex.values():
                self.DrawTableRow(item, draw_x, draw_y)
                if not self.tableInfo[item.GetFileID()].hidden:
                    draw_y += 30
        for entry in self.fileHandler.GetStrings().values():
            self.DrawTableRow(entry, draw_x, draw_y)
            if not self.tableInfo[entry.GetFileID()].hidden: draw_y += 30
            for item in entry.StringEntries.values():
                self.DrawTableRow(item, draw_x, draw_y)
                if not self.tableInfo[item.GetFileID()].hidden:
                    draw_y += 30
        self.mainCanvas.configure(scrollregion=(0,0,1280,draw_y + 5))
        

    def Search(self, searchText):
        for item in self.tableInfo.values():
            item.hidden = True
        for audio in self.fileHandler.GetAudio().values():
            name = str(audio.GetFileID()) + ".wem"
            if name.startswith(searchText.get()) or name.endswith(searchText.get()):
                for subscriber in audio.Subscribers:
                    self.UpdateTableEntry(subscriber, action="show")
        bankDict = self.fileHandler.GetWwiseBanks()
        for bank in bankDict.values():
            name = str(bank.GetFileID()) + ".bnk"
            if name.startswith(searchText.get()) or name.endswith(searchText.get()):
                self.UpdateTableEntry(bank, action="show")
        for item in self.fileHandler.GetStrings().values():
            name = str(item.GetFileID()) + ".text"
            if name.startswith(searchText.get()) or name.endswith(searchText.get()):
                self.UpdateTableEntry(item, action="show")
            for entry in item.StringEntries.values():
                name = entry.TextVariable.get()
                if searchText.get() in name:
                    self.UpdateTableEntry(entry, action="show")
                    self.UpdateTableEntry(entry.Parent, action="show")
        self.RedrawTable()
    
    def Update(self):
        self.RedrawTable()
        
    def LoadArchive(self):
        self.soundHandler.KillSound()
        self.fileHandler.LoadArchiveFile()
        self.expandedBanks.clear()
        self.CreateTable()
        self.Update()
        
    def SaveArchive(self):
        self.soundHandler.KillSound()
        self.fileHandler.SaveArchiveFile()
        
    def LoadWems(self):
        self.soundHandler.KillSound()
        self.fileHandler.LoadWems()
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
        self.fileHandler.LoadPatch()
        self.UpdateTableEntries()
        self.Update()
    
def exitHandler():
    soundHandler.audio.terminate()
    

if __name__ == "__main__":
    soundHandler = SoundHandler()
    fileHandler = FileHandler()
    atexit.register(exitHandler)
    window = MainWindow(fileHandler, soundHandler)