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
        return bytes(newData)

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

class TocEntry:
    '''
    Modified from https://github.com/kboykboy2/io_scene_helldivers2 with permission from kboykboy
    '''

    def __init__(self):
        self.FileID = self.TypeID = self.TocDataOffset = self.Unknown1 = self.GpuResourceOffset = self.Unknown2 = self.TocDataSize = self.GpuResourceSize = self.EntryIndex = self.StreamSize = self.StreamOffset = 0
        self.Unknown3 = 16
        self.Unknown4 = 64

        self.TocData =  self.TocData_OLD = b""
        self.GpuData =  self.GpuData_OLD = b""
        self.StreamData =  self.StreamData_OLD = b""
        self.Modified = False
        
    # -- Load TocEntry -- #
    def Load(self, TocFile):
        self.FileID             = TocFile.uint64Read()
        self.TypeID             = TocFile.uint64Read()
        self.TocDataOffset      = TocFile.uint64Read()
        self.StreamOffset       = TocFile.uint64Read()
        self.GpuResourceOffset  = TocFile.uint64Read()
        self.Unknown1           = TocFile.uint64Read()
        self.Unknown2           = TocFile.uint64Read()
        self.TocDataSize        = TocFile.uint32Read()
        self.StreamSize         = TocFile.uint32Read()
        self.GpuResourceSize    = TocFile.uint32Read()
        self.Unknown3           = TocFile.uint32Read()
        self.Unknown4           = TocFile.uint32Read()
        self.EntryIndex         = TocFile.uint32Read()
        return self
        
    def LoadData(self, TocFile, GpuFile, StreamFile):

        TocFile.seek(self.TocDataOffset)
        self.TocData = bytearray(self.TocDataSize)
        self.TocData = TocFile.bytes(self.TocData)
        if self.GpuResourceSize > 0:
            GpuFile.seek(self.GpuResourceOffset)
            self.GpuData = bytearray(self.GpuResourceSize)
            self.GpuData = GpuFile.bytes(self.GpuData)
        if self.StreamSize > 0:
            StreamFile.seek(self.StreamOffset)
            self.StreamData = bytearray(self.StreamSize)
            self.StreamData = StreamFile.bytes(self.StreamData)
            
    def Save(self, TocFile):
        TocFile.write(self.FileID.to_bytes(8, byteorder="little"))
        TocFile.write(self.TypeID.to_bytes(8, byteorder="little"))
        TocFile.write(self.TocDataOffset.to_bytes(8, byteorder="little"))
        TocFile.write(self.StreamOffset.to_bytes(8, byteorder="little"))
        TocFile.write(self.GpuResourceOffset.to_bytes(8, byteorder="little"))
        TocFile.write(self.Unknown1.to_bytes(8, byteorder="little"))
        TocFile.write(self.Unknown2.to_bytes(8, byteorder="little"))
        TocFile.write(self.TocDataSize.to_bytes(4, byteorder="little"))
        TocFile.write(self.StreamSize.to_bytes(4, byteorder="little"))
        TocFile.write(self.GpuResourceSize.to_bytes(4, byteorder="little"))
        TocFile.write(self.Unknown3.to_bytes(4, byteorder="little"))
        TocFile.write(self.Unknown4.to_bytes(4, byteorder="little"))
        TocFile.write(self.EntryIndex.to_bytes(4, byteorder="little"))
        
    def SaveData(self, TocFile, GpuFile, StreamFile):
        TocFile.seek(self.TocDataOffset)
        TocFile.write(PadTo16ByteAlign(self.TocData))
        if self.GpuResourceSize > 0:
            GpuFile.seek(self.GpuResourceOffset)
            GpuFile.write(self.GpuData)
        if self.StreamSize > 0:
            StreamFile.seek(self.StreamOffset)
            StreamFile.write(self.StreamData)
            
    def SetData(self, TocData, GpuData, StreamData):
        if not self.Modified:
            self.TocData_OLD = self.TocData
            self.GpuData_OLD = self.GpuData
            self.StreamData_OLD = self.StreamData
            self.Modified = True
        if TocData is not None:
            self.TocData = TocData
            self.TocDataSize = len(TocData)
        if StreamData is not None:
            self.StreamData = StreamData
            self.StreamSize = len(StreamData)
        if GpuData is not None:
            self.GpuData = GpuData
            self.GpuResourceSize = len(GpuData)
            
            
    def RevertModifications(self):
        if self.Modified:
            self.TocData = self.TocData_OLD
            self.TocDataSize = len(self.TocData)
            self.GpuData = self.GpuData_OLD
            self.GpuResourceSize = len(self.GpuData)
            self.StreamData = self.StreamData_OLD
            self.StreamSize = len(self.StreamData)
            self.Modified = False
            

class TocFileType:
    '''
    Modified from https://github.com/kboykboy2/io_scene_helldivers2 with permission from kboykboy
    '''

    def __init__(self, ID=0, NumFiles=0):
        self.unk1     = 0
        self.TypeID   = ID
        self.NumFiles = NumFiles
        self.unk2     = 16
        self.unk3     = 64
    def Load(self, TocFile):
        self.unk1     = TocFile.uint64Read()
        self.TypeID   = TocFile.uint64Read()
        self.NumFiles = TocFile.uint64Read()
        self.unk2     = TocFile.uint32Read()
        self.unk3     = TocFile.uint32Read()
        return self
    def Save(self, TocFile):
        TocFile.write(self.unk1.to_bytes(8, byteorder="little"))
        TocFile.write(self.TypeID.to_bytes(8, byteorder="little"))
        TocFile.write(self.NumFiles.to_bytes(8, byteorder="little"))
        TocFile.write(self.unk2.to_bytes(4, byteorder="little"))
        TocFile.write(self.unk3.to_bytes(4, byteorder="little"))

class StreamToc:
    '''
    Modified from https://github.com/kboykboy2/io_scene_helldivers2 with permission from kboykboy
    '''

    def __init__(self):
        self.magic      = self.numTypes = self.numFiles = self.unknown = 0
        self.unk4Data   = bytearray(56)
        self.TocTypes   = []
        self.TocEntries = {}
        self.Path = ""
        self.Name = ""
        self.LocalName = ""

    def LoadFile(self):
        self.magic      = self.TocFile.uint32Read()
        if self.magic != 4026531857: return False

        self.numTypes   = self.TocFile.uint32Read()
        self.numFiles   = self.TocFile.uint32Read()
        self.unknown    = self.TocFile.uint32Read()
        self.unk4Data   = self.TocFile.bytes(self.unk4Data, 56)
        self.TocTypes   = [TocFileType() for n in range(self.numTypes)]
        #self.TocEntries = [TocEntry() for n in range(self.numFiles)]
        # serialize Entries in correct order
        self.TocTypes   = [Entry.Load(self.TocFile) for Entry in self.TocTypes]
        TocEntryStart   = self.TocFile.tell()
        #entryList = [TocEntryFactory.CreateTocEntry(self.TocFile) for n in range(self.numFiles)]
        entryList = list(TocEntryFactory.CreateTocEntries(self.numFiles, self.TocFile))
        idList = [entry.FileID for entry in entryList]
        self.TocEntries = { id:entry for (id, entry) in zip(idList, entryList) }
        for key in sorted(self.TocEntries.keys()):
            self.TocEntries[key].LoadData(self.TocFile, self.GpuFile, self.StreamFile)
        return True

    def SaveFile(self):
        self.TocFile = MemoryStream()
        self.GpuFile = MemoryStream()
        self.StreamFile = MemoryStream()
        self.TocFile.write(self.magic.to_bytes(4, byteorder="little"))
        
        self.TocFile.write(self.numTypes.to_bytes(4, byteorder="little"))
        self.TocFile.write(self.numFiles.to_bytes(4, byteorder="little"))
        self.TocFile.write(self.unknown.to_bytes(4, byteorder="little"))
        self.TocFile.write(self.unk4Data)

        # serialize Entries in correct order
        for entry in self.TocTypes:
            entry.Save(self.TocFile)
            
        for id in sorted(self.TocEntries.keys()):
            self.TocEntries[id].Save(self.TocFile)
        for id in sorted(self.TocEntries.keys()):
            self.TocEntries[id].SaveData(self.TocFile, self.GpuFile, self.StreamFile)

    def UpdateTypes(self):
        self.TocTypes = []
        for Entry in self.TocEntries.values():
            exists = False
            for Type in self.TocTypes:
                if Type.TypeID == Entry.TypeID:
                    Type.NumFiles += 1; exists = True
                    break
            if not exists:
                self.TocTypes.append(TocFileType(Entry.TypeID, 1))

    def UpdatePath(self, path):
        self.Path = path
        self.Name = Path(path).name
        
    def GetEntryByID(self, fileID):
        if fileID in self.TocEntries.keys():
            return self.TocEntries[fileID]
        else:
            for entry in self.TocEntries.values():
                if isinstance(entry, TocBankEntry):
                    if fileID in entry.Wems.keys():
                        return entry.Wems[fileID]
                
    def GetEntryByIndex(self, entryIndex):
        for id, entry in self.TocEntries:
            if entry.EntryIndex == entryIndex:
                return entry
                
    def SetEntryByIndex(self, entryIndex, newEntry):
        for id, entry in self.TocEntries:
            if entry.EntryIndex == entryIndex:
                self.TocEntries[id] = newEntry
                
    def SetEntryByID(self, fileID, newEntry):
        self.TocEntries[fileID] = newEntry
                
    def RevertModifications(self):
        for entry in self.TocEntries.values():
            entry.RevertModifications()
        self.RebuildEntryHeaders()
                
    def RebuildEntryHeaders(self):
        tocOffset = 80 + 32 * len(self.TocTypes) + 80 * len(self.TocEntries)
        streamOffset = 0
        gpuOffset = 0
        for key in sorted(self.TocEntries.keys()):
            entry = self.TocEntries[key]
            entry.TocDataOffset = tocOffset
            entry.GpuResourceOffset = gpuOffset
            entry.StreamOffset = streamOffset
            streamOffset += _16ByteAlign(entry.StreamSize)
            tocOffset += _16ByteAlign(entry.TocDataSize)
            gpuOffset += _16ByteAlign(entry.GpuResourceSize)
                        
    def FromFile(self, path):
        self.UpdatePath(path)
        with open(path, 'r+b') as f:
            self.TocFile = MemoryStream(f.read())

        self.GpuFile    = MemoryStream()
        self.StreamFile = MemoryStream()
        if os.path.isfile(path+".gpu_resources"):
            with open(path+".gpu_resources", 'r+b') as f:
                self.GpuFile = MemoryStream(f.read())
        if os.path.isfile(path+".stream"):
            with open(path+".stream", 'r+b') as f:
                self.StreamFile = MemoryStream(f.read())
        return self.LoadFile()
        
    def ToFile(self, path):
        self.UpdateTypes()
        self.SaveFile()
        with open(path+"/"+self.Name, 'wb') as f:
            f.write(self.TocFile.Data)
        if len(self.GpuFile.Data) > 0:
            with open(path+"/"+self.Name+".gpu_resources", 'wb') as f:
                f.write(self.GpuFile.Data)
        if len(self.StreamFile.Data) > 0:
            with open(path+"/"+self.Name+".stream", 'wb') as f:
                f.write(self.StreamFile.Data)
            
class TocEntryFactory:
    @classmethod
    def CreateTocEntries(cls, n, TocFile):
        num = 0
        while num < n:
            num += 1
            TypeID = 0
            Entry = TocEntry()
            startPosition = TocFile.tell()
            TocFile.uint64Read()
            TypeID = TocFile.uint64Read()
            TocFile.seek(startPosition)
            match TypeID:
                case 5785811756662211598:
                    Entry = TocEntry()
                    yield Entry.Load(TocFile)
                case 6006249203084351385:
                    Entry = TocBankEntry()
                    yield Entry.Load(TocFile)
                case _:
                    TocFile.read(80) #skip making a TocEntry if it isn't an audio type
        #return Entry.Load(TocFile)
            
class TocBankEntry(TocEntry):

    def __init__(self):
        super().__init__()
        self.TocDataHeader = b""
        self.BankHeader = b""
        self.PostData = b""
        self.dataSectionSize = 0
        self.dataSectionStart = 0
        self.PostDataSize = 0
        self.Wems = {}

    def LoadData(self, TocFile, GpuFile, StreamFile):
        super().LoadData(TocFile, GpuFile, StreamFile)
        if TocFile.IsReading(): self.LoadBank()
        
        
    def LoadBank(self):
        tempData = MemoryStream()
        tempData.write(self.TocData)
        tempData.seek(0)
        self.TocDataHeader = TocDataHeader(tempData.read(16))
        self.BankHeader = b""
        self.PostDataSection = b""
        self.dataSectionSize = 0
        self.dataSectionStart = 0
        self.PostDataSize = 0
        self.Wems = {}
        
        #BKHD section
        tag = tempData.read(4).decode('utf-8')
        size = tempData.uint32Read()
        if tag != "BKHD":
            print("Error reading .bnk, invalid header")
            return
        self.BankHeader = tempData.read(size)
        
        #DIDX section
        tag = tempData.read(4).decode('utf-8')
        size = tempData.uint32Read()
        if tag != "DIDX":
            #print("Error reading .bnk, no Data Index")
            return
        for x in range(int(size/12)):
            wem = BankWem(tempData.read(12))
            self.Wems[wem.FileID] = wem
        
        #DATA section
        tag = tempData.read(4).decode('utf-8')
        size = tempData.uint32Read()
        if tag != "DATA":
            print("Error reading .bnk, DATA section not in expected location")
            return    
        self.dataSectionStart = tempData.tell()
        for wem in self.Wems.values():
            tempData.seek(self.dataSectionStart + wem.DataOffset)
            wem.LoadData(tempData.read(wem.DataSize))
            wem.Parent = self
        self.dataSectionSize = tempData.tell() - self.dataSectionStart
        
        #Any other sections (i.e. HIRC)
        self.PostData = tempData.read() #for now just store everything past the end of the data section
        self.PostDataSize = len(self.PostData)
        
    def GetWems(self):
        return self.Wems.values()
        
    def GetWemByID(self, fileID):
        return self.Wems[fileID]
        
    def SetWem(self, wemIndex, wemData, rebuildToc=True):
        self.Modified = True
        originalBankSize = self.TocDataHeader.TocFileSize
        originalWemSize = self.Wems[wemIndex].DataSize
        if wemIndex == len(self.Wems)-1: #each wem is padded to 16 bytes EXCEPT THE LAST ONE IN A BANK!!!
            newBankSize = originalBankSize - originalWemSize + len(wemData)
            self.dataSectionSize = self.dataSectionSize - originalWemSize + len(wemData)
        else:
            newBankSize = originalBankSize - _16ByteAlign(originalWemSize) + _16ByteAlign(len(wemData))
            self.dataSectionSize = self.dataSectionSize - _16ByteAlign(originalWemSize) + _16ByteAlign(len(wemData))
        self.TocDataHeader.TocFileSize = newBankSize
        self.Wems[wemIndex].SetData(wemData)
        if rebuildToc:
            self.RebuildTocData() #rebuildToc should be False if you intend to call SetWem many times as a performance optimization
            
    def RevertModifications(self):
        self.Modified = False
        for wem in self.Wems.values():
            wem.RevertModifications()
        self.RebuildTocData()
        
    def RebuildTocData(self):
        offset = 0
        originalDataSize = self.dataSectionSize
        self.dataSectionSize = 0
        for index, wem in enumerate(self.Wems.values()):
            if index != len(self.Wems)-1:
                self.dataSectionSize += _16ByteAlign(wem.DataSize)
            else:
                self.dataSectionSize += wem.DataSize
            wem.DataOffset = offset
            offset += _16ByteAlign(wem.DataSize)
        self.TocDataHeader.TocFileSize = self.TocDataHeader.TocFileSize - originalDataSize + self.dataSectionSize
        tempData = MemoryStream()
        tempData.write("BKHD".encode('utf-8'))
        tempData.write(len(self.BankHeader).to_bytes(4, byteorder='little'))
        tempData.write(self.BankHeader)
        tempData.write("DIDX".encode('utf-8'))
        tempData.write((12*len(self.Wems)).to_bytes(4, byteorder='little'))
        for key in sorted(self.Wems.keys()):
            tempData.write(self.Wems[key].GetDataIndexEntry())
        tempData.write("DATA".encode('utf-8'))
        tempData.write(self.dataSectionSize.to_bytes(4, byteorder='little'))
        for index, key in enumerate(sorted(self.Wems.keys())): #each wem is padded to 16 bytes EXCEPT THE LAST ONE IN A BANK!!!
            wem = self.Wems[key]
            if index == len(self.Wems)-1:
                tempData.write(wem.GetData())
            else:
                tempData.write(PadTo16ByteAlign(wem.GetData()))
        tempData.write(self.PostData)
        self.TocData = self.TocDataHeader.Get() + tempData.Data
        self.TocDataSize = len(self.TocData)
            

class BankWem:
    
    def __init__(self, DataIndexEntry):
        self.Load(DataIndexEntry)
        self.Modified = False
        self.Data = self.Data_OLD = None
        self.Parent = None
        
    def Load(self, DataIndexEntry):
        self.FileID = int.from_bytes(DataIndexEntry[0:4], byteorder='little')
        self.DataOffset = int.from_bytes(DataIndexEntry[4:8], byteorder='little')
        self.DataSize = int.from_bytes(DataIndexEntry[8:], byteorder='little')
        
    def LoadData(self, Data):
        self.Data = Data
        
    def SetData(self, data):
        if not self.Modified:
            self.Data_OLD = self.Data
        self.Data = data
        self.Modified = True
        self.DataSize = len(data)
        
    def RevertModifications(self):
        if self.Modified:
            self.Data = self.Data_OLD
            self.DataSize = len(self.Data)
            self.Modified = False
            
    def GetData(self):
        return self.Data
        
    def GetDataIndexEntry(self):
        return self.FileID.to_bytes(4, byteorder='little') + self.DataOffset.to_bytes(4, byteorder='little') + self.DataSize.to_bytes(4, byteorder='little')
        
        
class TocDataHeader():

    def __init__(self, header):
        self.Tag = header[0:4]
        self.TocFileSize = int.from_bytes(header[4:8], byteorder='little')
        self.FileID = int.from_bytes(header[8:], byteorder="little")
        
    def Get(self):
        return self.Tag + self.TocFileSize.to_bytes(4, byteorder="little") + self.FileID.to_bytes(8, byteorder="little")
            
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
        
    def PlayWem(self, soundIndex, soundData, callback=None):
        self.KillSound()
        self.callback = callback
        if self.audioID == soundIndex:
            self.audioID = -1
            return
        filename = f"temp{soundIndex}"
        if not os.path.isfile(f"{filename}.wav"):
            with open(f'{filename}.wem', 'wb') as f:
                f.write(soundData)
            subprocess.run(["vgmstream-win64/vgmstream-cli.exe", "-o", f"{filename}.wav", f"{filename}.wem"], stdout=subprocess.DEVNULL)
            os.remove(f"{filename}.wem")
            
        self.audioID = soundIndex
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

    def __init__(self, streamToc):
        self.streamToc = streamToc

    def DumpSelected():
        pass
        
    def DumpAll():
        pass
        
    def RevertAll(self):
        self.GetToc().RevertModifications()
        
    def RevertEntry(self, fileID):
        entry = self.GetToc().GetEntryByID(fileID)
        entry.RevertModifications()

    def DumpAllAsWem(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        
        maxProgress = 0
        for entry in self.GetTocEntries().values():
            if entry.TypeID == 5785811756662211598:
                maxProgress = maxProgress + 1
            elif entry.TypeID == 6006249203084351385:
                maxProgress = maxProgress + len(entry.Wems)

        progressWindow = ProgressWindow(title="Dumping Files", maxProgress=maxProgress)
        progressWindow.Show()
        
        if os.path.exists(folder):
            for entry in self.GetTocEntries().values():
                if entry.TypeID == 5785811756662211598:
                    savePath = os.path.join(folder, str(entry.FileID) + ".wem")
                    progressWindow.SetText("Dumping " + os.path.basename(savePath))
                    with open(savePath, "wb") as f:
                        f.write(entry.StreamData)
                    progressWindow.Step()
                elif entry.TypeID == 6006249203084351385:
                    wemIndex = 0
                    for wem in entry.Wems.values():
                        savePath = os.path.join(folder, str(wem.FileID) + ".wem")
                        progressWindow.SetText("Dumping " + os.path.basename(savePath))
                        wemIndex = wemIndex + 1
                        with open(savePath, "wb") as f:
                            f.write(wem.GetData())
                        progressWindow.Step()
        else:
            print("Invalid folder selected, aborting dump")
            
        progressWindow.Destroy()
    
    def DumpAllAsWav(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        
        maxProgress = 0
        for entry in self.GetTocEntries().values():
            if entry.TypeID == 5785811756662211598:
                maxProgress = maxProgress + 1
            elif entry.TypeID == 6006249203084351385:
                maxProgress = maxProgress + len(entry.Wems)

        progressWindow = ProgressWindow(title="Dumping Files", maxProgress=maxProgress)
        progressWindow.Show()
        
        if os.path.exists(folder):
            for entry in self.GetTocEntries().values():
                if entry.TypeID == 5785811756662211598:
                    savePath = os.path.join(folder, str(entry.FileID))
                    progressWindow.SetText("Dumping " + os.path.basename(savePath) + ".wav")
                    with open(savePath+".wem", "wb") as f:
                        f.write(entry.StreamData)
                    subprocess.run(["vgmstream-win64/vgmstream-cli.exe", "-o", f"{savePath}.wav", f"{savePath}.wem"], stdout=subprocess.DEVNULL)
                    os.remove(f"{savePath}.wem")
                    progressWindow.Step()
                elif entry.TypeID == 6006249203084351385:
                    wemIndex = 0
                    for wem in entry.Wems.values():
                        savePath = os.path.join(folder, str(wem.FileID))
                        progressWindow.SetText("Dumping " + os.path.basename(savePath) + ".wav")
                        wemIndex = wemIndex + 1
                        with open(savePath+".wem", "wb") as f:
                            f.write(wem.GetData())
                        subprocess.run(["vgmstream-win64/vgmstream-cli.exe", "-o", f"{savePath}.wav", f"{savePath}.wem"], stdout=subprocess.DEVNULL)
                        os.remove(f"{savePath}.wem")
                        progressWindow.Step()
        else:
            print("Invalid folder selected, aborting dump")
            
        progressWindow.Destroy()
        
    def DumpAllBnks():
        pass
        
    def GetFileNumberPrefix(self, n):
        number = ''.join(takewhile(str.isdigit, n or ""))
        try:
            return int(number)
        except:
            print("File name must begin with a number: "+n)
        
    def GetToc(self):
        return self.streamToc
        
    def GetTocEntries(self):
        return self.streamToc.TocEntries
        
    def SaveArchiveFile(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        if os.path.exists(folder):
            self.streamToc.ToFile(folder)
        else:
            print("Invalid folder selected, aborting save")
        
    def LoadArchiveFile(self):
        archiveFile = askopenfilename(title="Select archive")
        if os.path.splitext(archiveFile)[1] in (".stream", ".gpu_resources"):
            archiveFile = os.path.splitext(archiveFile)[0]
        if os.path.exists(archiveFile):
            self.streamToc.FromFile(archiveFile)
        else:
            print("Invalid file selected, aborting load")
            
    def LoadPatch(self):
        patchToc = StreamToc()
        patchFile = filedialog.askopenfilename(title="Choose patch file to import")
        if os.path.splitext(patchFile)[1] in (".stream", ".gpu_resources"):
            patchFile = os.path.splitext(patchFile)[0]
        if os.path.exists(patchFile):
            patchToc.FromFile(patchFile)
        else:
            print("Invalid file selected, aborting load")
            return
            
        progressWindow = ProgressWindow(title="Loading Files", maxProgress=len(patchToc.TocEntries))
        progressWindow.Show()
        
        for patchEntry in patchToc.TocEntries.values():
            entry = self.streamToc.GetEntryByID(patchEntry.FileID)
            if entry is None:
                print("Could not find matching file ID in archive! Aborting load")
                break
            if isinstance(entry, TocEntry):
                entry.SetData(TocData=patchEntry.TocData, GpuData=patchEntry.GpuData, StreamData=patchEntry.StreamData)
            elif isinstance(entry, BankWem):
                entry.SetData(patchEntry.GetData())
            progressWindow.Step()
            
            
        self.GetToc().RebuildEntryHeaders()
        progressWindow.Destroy()

    def WritePatch(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        if os.path.exists(folder):
            patchedToc = StreamToc()
            patchedToc.Name = self.streamToc.Name + ".patch_0"
            patchedToc.LocalName = self.streamToc.LocalName
            patchedToc.magic = self.streamToc.magic
            patchedToc.numTypes = 0
            patchedToc.numFiles = 0
            patchedToc.unknown = self.streamToc.unknown
            patchedToc.unk4Data = self.streamToc.unk4Data
            patchedToc.TocTypes = []
            patchedToc.TocEntries = {}
            for id, entry in self.GetTocEntries().items():
                if entry.Modified:
                    patchedToc.TocEntries[id] = entry
                    patchedToc.numFiles = patchedToc.numFiles + 1
            patchedToc.UpdateTypes()
            patchedToc.numTypes = len(patchedToc.TocTypes)
            patchedToc.RebuildEntryHeaders()
            patchedToc.ToFile(folder)
        else:
            print("Invalid folder selected, aborting save")

    def LoadWems(self):
        wems = filedialog.askopenfilenames(title="Choose .wem files to import")
        modifiedBankEntries = set()
        
        progressWindow = ProgressWindow(title="Loading Files", maxProgress=len(wems))
        progressWindow.Show()
        
        for file in wems:
            progressWindow.SetText("Loading "+os.path.basename(file))
            fileID = self.GetFileNumberPrefix(os.path.basename(file))
            entry = self.GetToc().GetEntryByID(fileID)
            if isinstance(entry, BankWem):
                with open(file, 'rb') as f:
                    entry.SetData(f.read())
                    entry.Parent.Modified = True
                    modifiedBankEntries.add(entry.Parent)
            elif isinstance(entry, TocBankEntry):
                with open(file, 'rb') as f:
                    entry.SetData(TocData=f.read(), GpuData=None, StreamData=None)
            elif isinstance(entry, TocEntry):
                with open(file, 'rb') as f:
                    streamData = f.read()
                    tocData = entry.TocData
                    tocData[8:12] = len(streamData).to_bytes(4, byteorder="little")
                    entry.SetData(TocData=tocData, GpuData=None, StreamData=streamData)
            progressWindow.Step()
        
        progressWindow.Destroy()
        progressWindow = ProgressWindow(title="Loading Files", maxProgress=len(modifiedBankEntries))
        progressWindow.Show()
        progressWindow.SetText("Rebuilding soundbanks")
        
        self.GetToc().RebuildEntryHeaders()
        for entry in modifiedBankEntries:
            entry.RebuildTocData()
            progressWindow.Step()
        
        progressWindow.Destroy()
        
    def LoadBnks():
        pass
        
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
        
    def _on_mousewheel(self, event):
        self.mainCanvas.yview_scroll(int(-1*(event.delta/120)), 'units')
        
    def CreateTableRow(self, tocEntry):
        
        info = TableInfo()
    
        fillColor = "lawn green" if tocEntry.Modified else "white"
        info.rectangles.append(self.mainCanvas.create_rectangle(0, 0, 335, 30, fill=fillColor, tags=(tocEntry.FileID, "rect")))
        info.rectangles.append(self.mainCanvas.create_rectangle(0, 0, 80, 30, fill=fillColor, tags=(tocEntry.FileID, "rect")))
        
        name = str(tocEntry.FileID) + (".wem" if tocEntry.TypeID == 5785811756662211598 else ".bnk")

        info.text.append(self.mainCanvas.create_text(0, 0, text=name, fill='black', font=('Arial', 16, 'bold'), anchor='nw', tags=(tocEntry.FileID, "name")))
        info.text.append(self.mainCanvas.create_text(0, 0, text=tocEntry.EntryIndex, fill='black', font=('Arial', 16, 'bold'), anchor='nw', tag=tocEntry.FileID))
        
        #create revert button
        revert = Button(self.mainCanvas, text='\u21b6', fg='black', font=('Arial', 14, 'bold'), command=partial(self.RevertEntry, tocEntry.FileID), image=self.fakeImage, compound='c', height=20, width=20)
        
        info.revertButton = self.mainCanvas.create_window(0, 0, window=revert, anchor='nw', tag=tocEntry.FileID)
        info.buttons.append(info.revertButton)
        
        if tocEntry.TypeID == 5785811756662211598:
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
                self.PlayWemFromStream(fileID, callback)
            play.configure(command=partial(pressButton, play, tocEntry.FileID, partial(resetButtonIcon, play)))
            info.buttons.append(self.mainCanvas.create_window(0, 0, window=play, anchor='nw', tag=tocEntry.FileID))
        else:
            info._type = TableInfo.BANK
            #create expand button
            def pressButton(button, bankId):
                if button['text'] == "v":
                    button.configure(text=">")
                    #hide
                    entry = self.fileHandler.GetToc().GetEntryByID(bankId)
                    for wem in entry.Wems.values():
                        self.UpdateTableEntry(wem.FileID, action="hide")
                else:
                    button.configure(text="v")
                    #show
                    entry = self.fileHandler.GetToc().GetEntryByID(bankId)
                    for wem in entry.Wems.values():
                        self.UpdateTableEntry(wem.FileID, action="show")
                self.Update()
            expand = Button(self.mainCanvas, text=">", font=('Arial', 14, 'bold'), height=20, width=20, image=self.fakeImage, compound='c')
            expand.configure(command=partial(pressButton, expand, tocEntry.FileID))
            info.buttons.append(self.mainCanvas.create_window(0, 0, window=expand, anchor='nw', tag=tocEntry.FileID))
        

        self.tableInfo[tocEntry.FileID] = info
        
    def CreateBankSubtableRow(self, bankWem):
    
        info = TableInfo()
        info.hidden = True
        info._type = TableInfo.BANK_WEM
    
        fillColor = "lawn green" if bankWem.Modified else "white"
        info.rectangles.append(self.mainCanvas.create_rectangle(0, 0, 305, 30, fill=fillColor, tags=(bankWem.FileID, "rect")))
        name = str(bankWem.FileID) + ".wem"
        info.text.append(self.mainCanvas.create_text(0, 0, text=name, fill='black', font=('Arial', 16, 'bold'), anchor='nw', tags=(bankWem.FileID, "name")))
        
        
        #create revert button
        revert = Button(self.mainCanvas, text='\u21b6', fg='black', font=('Arial', 14, 'bold'), command=partial(self.RevertEntry, bankWem.FileID), image=self.fakeImage, compound='c', height=20, width=20)
        
        info.revertButton = self.mainCanvas.create_window(0, 0, window=revert, anchor='nw', tag=bankWem.FileID)
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
            self.PlayWemFromBank(fileID, callback)
        play.configure(command=partial(pressButton, play, bankWem.FileID, partial(resetButtonIcon, play)))
        info.buttons.append(self.mainCanvas.create_window(0, 0, window=play, anchor='nw', tag=bankWem.FileID))
        
        self.tableInfo[bankWem.FileID] = info
            
    def CreateTable(self, toc):
        for child in self.mainCanvas.winfo_children():
            child.destroy()
        self.mainCanvas.delete("all")
        self.tableInfo = {}
        validTypes = [5785811756662211598, 6006249203084351385]
        draw_y = 0
        for key in sorted(toc.TocEntries.keys()):
            entry = toc.TocEntries[key]
            name = str(entry.FileID) + (".wem" if entry.TypeID == 5785811756662211598 else ".bnk")
            if entry.TypeID in validTypes:
                self.CreateTableRow(entry)
                draw_y += 30
                if entry.TypeID == 6006249203084351385:
                    for id, wem in entry.Wems.items():
                        self.CreateBankSubtableRow(wem)
                        draw_y += 30               
        self.mainCanvas.configure(scrollregion=(0,0,500,draw_y + 5))
    
    def UpdateTableEntry(self, fileID, action="update"):
        if action == "update":
            entry = self.fileHandler.GetToc().GetEntryByID(fileID)
            self.tableInfo[fileID].modified = entry.Modified
            for rect in self.tableInfo[fileID].rectangles:
                if entry.Modified:
                    self.mainCanvas.itemconfigure(rect, fill="lawn green")
                else:
                    self.mainCanvas.itemconfigure(rect, fill="white")
        elif action == "show":
            self.tableInfo[fileID].hidden = False
        elif action == "hide":
            self.tableInfo[fileID].hidden = True
            
    def UpdateTableEntries(self):
        for fileID in self.fileHandler.GetTocEntries().keys():
            self.UpdateTableEntry(fileID)
            
    def DrawTableRow(self, fileID, x, y):
        rowInfo = self.tableInfo[fileID]
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
                self.mainCanvas.moveto(rowInfo.revertButton, -1000, -1000)
        else:
            for button in rowInfo.buttons:
                self.mainCanvas.moveto(button, -1000, -1000)
            for rect in rowInfo.rectangles:
                self.mainCanvas.moveto(rect, -1000, -1000)
            for text in rowInfo.text:
                self.mainCanvas.moveto(text, -1000, -1000)
        
    def RedrawTable(self, toc):
        draw_y = 0
        draw_x = 0
        for key in sorted(toc.TocEntries.keys()):
            draw_x = 0
            entry = toc.TocEntries[key]
            self.DrawTableRow(entry.FileID, draw_x, draw_y)
            if not self.tableInfo[key].hidden: draw_y += 30 
            if entry.TypeID == 6006249203084351385:
                for id in entry.Wems.keys():
                    self.DrawTableRow(id, draw_x, draw_y)
                    if not self.tableInfo[id].hidden: draw_y += 30       
        self.mainCanvas.configure(scrollregion=(0,0,1280,draw_y + 5))

    def Search(self, searchText):
        for fileID, info in self.tableInfo.items():
            
            name = str(fileID) + (".bnk" if info._type == TableInfo.BANK else ".wem")
            if name.startswith(searchText.get()) or name.endswith(searchText.get()):
                self.UpdateTableEntry(fileID, action="show")
                if info._type == TableInfo.BANK_WEM:
                    self.UpdateTableEntry(self.fileHandler.GetToc().GetEntryByID(fileID).Parent.FileID, action="show")
            else:
                self.UpdateTableEntry(fileID, action="hide")
        self.RedrawTable(self.fileHandler.GetToc())
    
    def Update(self):
        self.RedrawTable(self.fileHandler.GetToc())
        
    def LoadArchive(self):
        self.soundHandler.KillSound()
        self.fileHandler.LoadArchiveFile()
        self.expandedBanks.clear()
        self.CreateTable(self.fileHandler.GetToc())
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
        
    def PlayWemFromStream(self, fileID, callback):
        self.soundHandler.PlayWem(fileID, self.fileHandler.GetToc().GetEntryByID(fileID).StreamData, callback)
        
    def PlayWemFromBank(self, wemID, callback):
        self.soundHandler.PlayWem(wemID, self.fileHandler.GetToc().GetEntryByID(wemID).GetData(), callback)
        
    def RevertEntry(self, fileID):
        self.soundHandler.KillSound()
        self.fileHandler.RevertEntry(fileID)
        self.UpdateTableEntry(fileID)
        self.Update()
        
    def RevertWem(self, fileID, wemIndex):
        self.soundHandler.KillSound()
        self.fileHandler.RevertBankWem(fileID, wemIndex)
        self.UpdateTableEntry(fileID)
        self.Update()
        
    def RevertAll(self):
        self.soundHandler.KillSound()
        self.fileHandler.RevertAll()
        self.UpdateTableEntries()
        self.Update()
        
    def WritePatch(self):
        self.soundHandler.KillSound()
        self.fileHandler.WritePatch()
        #self.Update()
        
    def LoadPatch(self):
        self.soundHandler.KillSound()
        self.fileHandler.LoadPatch()
        self.UpdateTableEntries()
        self.Update()
    
def exitHandler():
    soundHandler.audio.terminate()
    

if __name__ == "__main__":
    toc = StreamToc()
    soundHandler = SoundHandler()
    fileHandler = FileHandler(toc)
    atexit.register(exitHandler)
    window = MainWindow(fileHandler, soundHandler)