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
import simpleaudio
import subprocess
import time
import atexit
from itertools import takewhile
import copy

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
            
    def SetData(self, tocData, gpuData, streamData):
        if not self.Modified:
            self.TocData_OLD = self.TocData
            self.GpuData_OLD = self.GpuData
            self.StreamData_OLD = self.StreamData
            self.Modified = True
        if tocData is not None:
            self.TocData = tocData
            self.TocDataSize = len(tocData)
        if streamData is not None:
            self.StreamData = streamData
            self.StreamSize = len(streamData)
        if gpuData is not None:
            self.GpuData = gpuData
            self.GpuResourceSize = len(gpuData)
            
            
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
        self.TocEntries = []
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
        self.TocEntries = [TocEntryFactory.CreateTocEntry(self.TocFile) for n in range(self.numFiles)]
        for Entry in self.TocEntries:
            Entry.LoadData(self.TocFile, self.GpuFile, self.StreamFile)
            
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
            
        for entry in self.TocEntries:
            entry.Save(self.TocFile)
        for entry in self.TocEntries:
            entry.SaveData(self.TocFile, self.GpuFile, self.StreamFile)

    def UpdateTypes(self):
        self.TocTypes = []
        for Entry in self.TocEntries:
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
        for entry in self.TocEntries:
            if entry.FileID == fileID:
                return entry
                
    def GetEntryByIndex(self, entryIndex):
        for entry in self.TocEntries:
            if entry.EntryIndex == entryIndex:
                return entry
                
    def SetEntryByIndex(self, entryIndex, newEntry):
        for entry in self.TocEntries:
            if entry.EntryIndex == entryIndex:
                self.TocEntries[self.TocEntries.index(entry)] = newEntry
                
    def SetEntryByID(self, fileID, newEntry):
        for entry in self.TocEntries:
            if entry.FileID == fileID:
                self.TocEntries[self.TocEntries.index(entry)] = newEntry
                
    def RebuildEntryHeaders(self):
        tocOffset = 80 + 32 * len(self.TocTypes) + 80 * len(self.TocEntries)
        streamOffset = 0
        gpuOffset = 0
        for entry in self.TocEntries:
            entry.TocDataOffset = tocOffset
            entry.GpuResourceOffset = gpuOffset
            entry.StreamOffset = streamOffset
            streamOffset += _16ByteAlign(entry.StreamSize)
            tocOffset += _16ByteAlign(entry.TocDataSize)
            gpuOffset += _16ByteAlign(entry.GpuResourceSize)
                
    def SetEntryData(self, entryIndex, tocData=None, gpuData=None, streamData=None, rebuildHeaders=True):
        self.TocEntries[entryIndex].SetData(tocData, gpuData, streamData)
        if rebuildHeaders:
            self.RebuildEntryHeaders()
                        
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
    def CreateTocEntry(cls, TocFile):
        TypeID = 0
        Entry = TocEntry()
        startPosition = TocFile.tell()
        TocFile.uint64Read()
        TypeID = TocFile.uint64Read()
        TocFile.seek(startPosition)
        match TypeID:
            case 5785811756662211598:
                Entry = TocEntry()
            case 6006249203084351385:
                Entry = TocBankEntry()
        return Entry.Load(TocFile)
            
class TocBankEntry(TocEntry):

    def __init__(self):
        super().__init__()
        self.TocDataHeader = b""
        self.BankHeader = b""
        self.PostData = b""
        self.dataSectionSize = 0
        self.dataSectionStart = 0
        self.PostDataSize = 0
        self.Wems = []

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
        self.Wems = []
        
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
        for x in range(int(size/12)): self.Wems.append(BankWem(tempData.read(12)))
        
        #DATA section
        tag = tempData.read(4).decode('utf-8')
        size = tempData.uint32Read()
        if tag != "DATA":
            print("Error reading .bnk, DATA section not in expected location")
            return    
        self.dataSectionStart = tempData.tell()
        for wem in self.Wems:
            tempData.seek(self.dataSectionStart + wem.DataOffset)
            wem.LoadData(tempData.read(wem.DataSize))
        self.dataSectionSize = tempData.tell() - self.dataSectionStart
        
        #Any other sections (i.e. HIRC)
        self.PostData = tempData.read() #for now just store everything past the end of the data section
        self.PostDataSize = len(self.PostData)
        
    def GetWems(self):
        return self.Wems
        
    def GetWemByID(self, fileID):
        for wem in self.GetWems():
            if wem.FileID == fileID:
                return wem
        
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
            self.RebuildTocData() #rebuildToc could be False if you intend to call SetWem many times as a performance optimization
        
        
    def RebuildTocData(self):
        offset = 0
        for wem in self.Wems:
            wem.DataOffset = offset
            offset += _16ByteAlign(wem.DataSize)
        tempData = MemoryStream()
        tempData.write("BKHD".encode('utf-8'))
        tempData.write(len(self.BankHeader).to_bytes(4, byteorder='little'))
        tempData.write(self.BankHeader)
        tempData.write("DIDX".encode('utf-8'))
        tempData.write((12*len(self.Wems)).to_bytes(4, byteorder='little'))
        for wem in self.Wems:
            tempData.write(wem.GetDataIndexEntry())
        tempData.write("DATA".encode('utf-8'))
        tempData.write(self.dataSectionSize.to_bytes(4, byteorder='little'))
        for wem in self.Wems: #each wem is padded to 16 bytes EXCEPT THE LAST ONE IN A BANK!!!
            if wem == self.Wems[-1]:
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
        
    def Revert(self):
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
        self.tempFiles = []
        self.audioProcess = None
        self.waveObject = None
        self.audioID = -1
        
    def KillSound(self):
        simpleaudio.stop_all()
        
    def PlayWem(self, soundIndex, soundData):
        self.KillSound()
        if self.audioID == soundIndex:
            self.audioID = -1
            return
        filename = f"temp{soundIndex}"
        if not os.path.isfile(f"{filename}.wav"):
            with open(f'{filename}.wem', 'wb') as f:
                f.write(soundData)
            subprocess.run(["vgmstream-win64/vgmstream-cli.exe", "-o", f"{filename}.wav", f"{filename}.wem"], stdout=subprocess.DEVNULL)
            if not f"{filename}.wav" in self.tempFiles:
                self.tempFiles.append(f"{filename}.wav")
            os.remove(f"{filename}.wem")
        self.audioID = soundIndex
        self.waveObject = simpleaudio.WaveObject.from_wave_file(f"{filename}.wav")
        self.audioProcess = self.waveObject.play()
        os.remove(f"{filename}.wav")
        

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
    
    def DumpAllWems(self):
        folder = filedialog.askdirectory(title="Select folder to save files to")
        maxProgress = 0
        for entry in self.GetTocEntries():
            if entry.TypeID == 5785811756662211598:
                maxProgress = maxProgress + 1
            elif entry.TypeID == 6006249203084351385:
                maxProgress = maxProgress + len(entry.Wems)
        progressWindow = ProgressWindow(title="Dumping Files", maxProgress=maxProgress)
        progressWindow.Show()
        if os.path.exists(folder):
            for entry in self.GetTocEntries():
                if entry.TypeID == 5785811756662211598:
                    savePath = os.path.join(folder, str(entry.EntryIndex))
                    progressWindow.SetText("Dumping " + os.path.basename(savePath) + ".wav")
                    with open(savePath+".wem", "wb") as f:
                        f.write(entry.StreamData)
                    subprocess.run(["vgmstream-win64/vgmstream-cli.exe", "-o", f"{savePath}.wav", f"{savePath}.wem"], stdout=subprocess.DEVNULL)
                    os.remove(f"{savePath}.wem")
                    progressWindow.Step()
                elif entry.TypeID == 6006249203084351385:
                    wemIndex = 0
                    for wem in entry.Wems:
                        savePath = os.path.join(folder, str(entry.EntryIndex)+"-"+str(wemIndex))
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
        for patchEntry in patchToc.TocEntries:
            entry = self.streamToc.GetEntryByID(patchEntry.FileID)
            if entry is None:
                print("Could not find matching file ID in archive! Aborting load")
                break
            gpuData = streamData = tocData = None
            tocData = patchEntry.TocData
            if patchEntry.GpuResourceSize > 0:
                gpuData = patchEntry.GpuData
            if patchEntry.StreamSize > 0:
                streamData = patchEntry.StreamData
            self.GetToc().SetEntryData(entryIndex=patchEntry.EntryIndex, tocData=tocData, streamData=streamData, gpuData=gpuData, rebuildHeaders=False)
            if isinstance(entry, TocBankEntry):
                progressWindow.SetText("Loading "+str(patchEntry.EntryIndex)+" .bnk")
            else:
                progressWindow.SetText("Loading "+str(patchEntry.EntryIndex)+" .wem")
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
            patchedToc.TocEntries = []
            for entry in self.GetTocEntries():
                if entry.Modified:
                    patchedToc.TocEntries.append(copy.deepcopy(entry))
                    patchedToc.numFiles = patchedToc.numFiles + 1
            patchedToc.UpdateTypes()
            patchedToc.numTypes = len(patchedToc.TocTypes)
            patchedToc.RebuildEntryHeaders()
            patchedToc.ToFile(folder)
        else:
            print("Invalid folder selected, aborting save")

    def LoadWems(self):
        wems = filedialog.askopenfilenames(title="Choose .wem files to import")
        modifiedBankEntries = {}
        progressWindow = ProgressWindow(title="Loading Files", maxProgress=len(wems))
        progressWindow.Show()
        for file in wems:
            progressWindow.SetText("Loading "+os.path.basename(file))
            index = self.GetFileNumberPrefix(os.path.basename(file))
            entry = self.streamToc.GetEntryByIndex(index)
            if "-" not in os.path.basename(file): #not part of a bank!
                if isinstance(entry, TocBankEntry): #accidentally trying to replace a .bnk with a .wem!
                    print("When importing \"" + os.path.basename(file) + "\", tried to import .wem in place of .bnk. Check filename")
                    continue
                with open(file, 'rb') as f:
                    streamData = f.read()
                    tocData = entry.TocData
                    tocData[8:12] = len(streamData).to_bytes(4, byteorder="little")
                    self.GetToc().SetEntryData(entryIndex=index, tocData=tocData, streamData=streamData, rebuildHeaders=False)
            else: #part of a bank!
                if not isinstance(entry, TocBankEntry):
                    #either wrong index for a bank or someone accidentally put a - in the filename for a loose wem
                    print("When importing \"" + os.path.basename(file) + "\", no matching soundbank found. Check filename.")
                    continue
                modifiedBankEntries[entry.FileID] = entry
                wemIndex = self.GetFileNumberPrefix(os.path.basename(file).split("-")[1])
                with open(file, 'rb') as f:
                    entry.SetWem(wemIndex, f.read(), False)
            progressWindow.Step()
        progressWindow.Destroy()
        
        progressWindow = ProgressWindow(title="Loading Files", maxProgress=len(modifiedBankEntries.values()))
        progressWindow.Show()
        progressWindow.SetText("Rebuilding soundbanks")
        self.GetToc().RebuildEntryHeaders()
        for entry in modifiedBankEntries.values():
            entry.RebuildTocData()
            progressWindow.Step()
        progressWindow.Destroy()
        
    def LoadBnks():
        pass

class MainWindow:

    def __init__(self, fileHandler, soundHandler):
        self.fileHandler = fileHandler
        self.soundHandler = soundHandler
        self.savedEntries = set()
        self.unsavedEntries = set()
        
        self.root = Tk()
        self.titleCanvas = Canvas(self.root, width=1280, height=30)
    
        self.titleCanvas.create_rectangle(35, 0, 335, 30, fill="white")
        self.titleCanvas.create_rectangle(335, 0, 635, 30, fill="white")
        self.titleCanvas.create_rectangle(635, 0, 935, 30, fill="white")
        self.titleCanvas.create_rectangle(935, 0, 1235, 30, fill="white")
        
        self.titleCanvas.create_text(40, 5, text="Name", fill='black', font=('Arial', 16, 'bold'), anchor='nw')
        self.titleCanvas.create_text(340, 5, text="Id", fill='black', font=('Arial', 16, 'bold'), anchor='nw')
        self.titleCanvas.create_text(640, 5, text="File Offset", fill='black', font=('Arial', 16, 'bold'), anchor='nw')
        self.titleCanvas.create_text(940, 5, text="File Size", fill='black', font=('Arial', 16, 'bold'), anchor='nw')
        
        self.scrollBar = Scrollbar(self.root, orient=VERTICAL)
        self.mainCanvas = Canvas(self.root, width=1280, height=720, yscrollcommand=self.scrollBar.set)
        self.scrollBar['command'] = self.mainCanvas.yview
        
        self.titleCanvas.pack(side="top")
        self.scrollBar.pack(side="right", fill="y")
        self.mainCanvas.pack(side="left")
        
        self.root.title("Helldivers 2 Audio Modder")
        self.root.geometry("1280x720")
        self.drawBankSubWindows = {}

        self.menu = Menu(self.root)
        
        self.fileMenu = Menu(self.menu)
        self.fileMenu.add_command(label="Load Archive", command=self.LoadArchive)
        self.fileMenu.add_command(label="Save Archive", command=self.SaveArchive)
        self.fileMenu.add_command(label="Write Patch", command=self.WritePatch)
        self.fileMenu.add_command(label="Import Patch File", command=self.LoadPatch)
        self.fileMenu.add_command(label="Import .wems", command=self.LoadWems)
        
        self.dumpMenu = Menu(self.menu)
        self.dumpMenu.add_command(label="Dump all .wems", command=self.DumpAllWems)
        
        self.menu.add_cascade(label="File", menu=self.fileMenu)
        self.menu.add_cascade(label="Dump", menu=self.dumpMenu)
        self.root.config(menu=self.menu)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.resizable(False, False)
        self.root.mainloop()
        
    def _on_mousewheel(self, event):
        self.mainCanvas.yview_scroll(int(-1*(event.delta/120)), 'units')
        
    def UpdateTable(self, toc):
        for child in self.mainCanvas.winfo_children():
            child.destroy()
        self.mainCanvas.delete("all")
        rows = []
        for entry in toc.TocEntries:
            if entry.TypeID == 5785811756662211598:
                row = {}
                row['name'] = str(entry.EntryIndex) + ".wem"
                row['ID'] = entry.FileID
                row['Size'] = entry.StreamSize
                row['File Offset'] = entry.StreamOffset
                row['EntryIndex'] = entry.EntryIndex
                row['Unsaved'] = entry.Modified
                rows.append(row)
            if entry.TypeID == 6006249203084351385:
                row = {}
                row['name'] = str(entry.EntryIndex) + ".bnk"
                row['expand'] = True
                row['ID'] = entry.FileID
                row['Size'] = entry.TocDataSize
                row['File Offset'] = entry.TocDataOffset
                row['EntryIndex'] = entry.EntryIndex
                row['Unsaved'] = entry.Modified
                rows.append(row)
        self.draw_height = 0
        self.mainCanvas.configure(scrollregion=(0,0,1280,len(rows)*30+5))
        scrollregionSize = len(rows)*30+5
        for row in rows:
            fillColor = "lawn green" if row['Unsaved'] else "white"
            self.mainCanvas.create_rectangle(35, self.draw_height, 335, self.draw_height+30, fill=fillColor)
            self.mainCanvas.create_rectangle(335, self.draw_height, 635, self.draw_height+30, fill=fillColor)
            self.mainCanvas.create_rectangle(635, self.draw_height, 935, self.draw_height+30, fill=fillColor)
            self.mainCanvas.create_rectangle(935, self.draw_height, 1235, self.draw_height+30, fill=fillColor)
            if "expand" in row:
                t = ">"
                try:
                    if self.drawBankSubWindows[row['ID']]:
                        t = "v"
                except KeyError:
                    pass
                expand = Button(self.mainCanvas, text=t,command=partial(self.ExpandBank, row['ID']))
                self.mainCanvas.create_window(15, self.draw_height+3, window=expand, anchor='nw')
            else:
                #Play: unicode 23f5 or 25B6. Stop: 23f9
                play = Button(self.mainCanvas, text= '\u23f5', fg='green', font=('Arial', 10, 'bold'), command=partial(self.PlayWemFromStream, row['ID']))
                self.mainCanvas.create_window(10, self.draw_height+3, window=play, anchor='nw')
            self.mainCanvas.create_text(40, self.draw_height+5, text=row['name'], fill='black', font=('Arial', 16, 'bold'), anchor='nw')
            self.mainCanvas.create_text(340, self.draw_height+5, text=row['ID'], fill='black', font=('Arial', 16, 'bold'), anchor='nw')
            self.mainCanvas.create_text(640, self.draw_height+5, text=row['File Offset'], fill='black', font=('Arial', 16, 'bold'), anchor='nw')
            self.mainCanvas.create_text(940, self.draw_height+5, text=row['Size'], fill='black', font=('Arial', 16, 'bold'), anchor='nw')
            self.draw_height = self.draw_height + 30
            try: #add bank subwindows
                if self.drawBankSubWindows[row['ID']]:
                    bankEntry = self.fileHandler.GetToc().GetEntryByID(row['ID'])
                    wem_count = 0
                    for wem in bankEntry.Wems:#construct a row
                        fillColor = "lawn green" if wem.Modified else "white"
                        self.mainCanvas.create_rectangle(65, self.draw_height, 335, self.draw_height+30, fill=fillColor)
                        self.mainCanvas.create_rectangle(335, self.draw_height, 635, self.draw_height+30, fill=fillColor)
                        self.mainCanvas.create_rectangle(635, self.draw_height, 935, self.draw_height+30, fill=fillColor)
                        self.mainCanvas.create_rectangle(935, self.draw_height, 1235, self.draw_height+30, fill=fillColor)
                        self.mainCanvas.create_text(70, self.draw_height+5, text=(str(row['EntryIndex']) + "-" + str(wem_count) + ".wem"), fill='black', font=('Arial', 16, 'bold'), anchor='nw')
                        self.mainCanvas.create_text(340, self.draw_height+5, text=wem.FileID, fill='black', font=('Arial', 16, 'bold'), anchor='nw')
                        self.mainCanvas.create_text(640, self.draw_height+5, text=wem.DataOffset, fill='black', font=('Arial', 16, 'bold'), anchor='nw')
                        self.mainCanvas.create_text(940, self.draw_height+5, text=wem.DataSize, fill='black', font=('Arial', 16, 'bold'), anchor='nw')
                        play = Button(self.mainCanvas, text= '\u23f5', fg='green', font=('Arial', 10, 'bold'), command=partial(self.PlayWemFromBank, row['ID'], wem_count))
                        self.mainCanvas.create_window(40, self.draw_height+3, window=play, anchor='nw')
                        self.draw_height = self.draw_height + 30
                        scrollregionSize = scrollregionSize + 30
                        wem_count = wem_count + 1
                    self.mainCanvas.configure(scrollregion=(0,0,1280,scrollregionSize))
            except KeyError:
                pass
                

    def ExpandBank(self, bankIdx):
        try:
            if self.drawBankSubWindows[bankIdx]:
                self.drawBankSubWindows[bankIdx] = False
                self.Update()
                return
        except KeyError:
            pass
        self.drawBankSubWindows[bankIdx] = True
        self.Update()
    
    def Update(self):
        self.UpdateTable(self.fileHandler.GetToc())
        
    def LoadArchive(self):
        self.soundHandler.KillSound()
        self.fileHandler.LoadArchiveFile()
        self.drawBankSubWindows = {}
        self.Update()
        
    def SaveArchive(self):
        #clear modifications?
        self.soundHandler.KillSound()
        self.fileHandler.SaveArchiveFile()
        self.Update()
        
    def LoadWems(self):
        self.soundHandler.KillSound()
        self.fileHandler.LoadWems()
        self.Update()
        
    def DumpAllWems(self):
        self.soundHandler.KillSound()
        self.fileHandler.DumpAllWems()
        
    def PlayWemFromStream(self, fileID):
        self.soundHandler.PlayWem(fileID, self.fileHandler.GetToc().GetEntryByID(fileID).StreamData)
        
    def PlayWemFromBank(self, bankID, wemID):
        self.soundHandler.PlayWem(int(str(bankID) + str(wemID)), self.fileHandler.GetToc().GetEntryByID(bankID).GetWems()[wemID].GetData())
        
    def WritePatch(self):
        #clear modifications?
        self.soundHandler.KillSound()
        self.fileHandler.WritePatch()
        self.Update()
        
    def LoadPatch(self):
        self.soundHandler.KillSound()
        self.fileHandler.LoadPatch()
        self.Update()
    
def exitHandler():
    pass
    

if __name__ == "__main__":
    toc = StreamToc()
    soundHandler = SoundHandler()
    fileHandler = FileHandler(toc)
    atexit.register(exitHandler)
    window = MainWindow(fileHandler, soundHandler)