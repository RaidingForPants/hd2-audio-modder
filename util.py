from typing import Any
import struct
import os

LANGUAGE_MAPPING = ({
    "English (US)" : 0x03f97b57,
    "English (UK)" : 0x6f4515cb,
    "Français" : 4271961631,
    "Português 1": 1861586415,
    "Português 2": 1244441033,
    "Polski": 260593578,
    "日本語": 2427891497,
    "中文（繁體）": 2663028010,
    "中文（简体）": 2189905090,
    "Nederlands": 291057413,
    "한국어": 3151476177,
    "Español 1": 830498882,
    "Español 2": 3854981686,
    "Deutsch": 3124347884,
    "Italiano": 3808107213,
    "Русский": 3317373165
})

class MemoryStream:
    '''
    Modified from https://github.com/kboykboy2/io_scene_helldivers2 with permission from kboykboy
    '''
    def __init__(self, Data=b"", io_mode = "read"):
        self.location = 0
        self.data = bytearray(Data)
        self.io_mode = io_mode
        self.endian = "<"

    def open(self, Data, io_mode = "read"): # Open Stream
        self.data = bytearray(Data)
        self.io_mode = io_mode

    def set_read_mode(self):
        self.io_mode = "read"

    def set_write_mode(self):
        self.io_mode = "write"

    def is_reading(self):
        return self.io_mode == "read"

    def is_writing(self):
        return self.io_mode == "write"

    def seek(self, location): # Go To Position In Stream
        self.location = location
        if self.location > len(self.data):
            missing_bytes = self.location - len(self.data)
            self.data += bytearray(missing_bytes)

    def tell(self): # Get Position In Stream
        return self.location

    def read(self, length=-1): # read Bytes From Stream
        if length == -1:
            length = len(self.data) - self.location
        if self.location + length > len(self.data):
            raise Exception("reading past end of stream")

        newData = self.data[self.location:self.location+length]
        self.location += length
        return bytearray(newData)
        
    def advance(self, offset):
        self.location += offset
        if self.location < 0:
            self.location = 0
        if self.location > len(self.data):
            missing_bytes = self.location - len(self.data)
            self.data += bytearray(missing_bytes)

    def write(self, bytes): # Write Bytes To Stream
        length = len(bytes)
        if self.location + length > len(self.data):
            missing_bytes = (self.location + length) - len(self.data)
            self.data += bytearray(missing_bytes)
        self.data[self.location:self.location+length] = bytearray(bytes)
        self.location += length

    def read_format(self, format, size):
        format = self.endian+format
        return struct.unpack(format, self.read(size))[0]
        
    def bytes(self, value, size = -1):
        if size == -1:
            size = len(value)
        if len(value) != size:
            value = bytearray(size)

        if self.is_reading():
            return bytearray(self.read(size))
        elif self.is_writing():
            self.write(value)
            return bytearray(value)
        return value
        
    def int8_read(self):
        return self.read_format('b', 1)

    def uint8_read(self):
        return self.read_format('B', 1)

    def int16_read(self):
        return self.read_format('h', 2)

    def uint16_read(self):
        return self.read_format('H', 2)

    def int32_read(self):
        return self.read_format('i', 4)

    def uint32_read(self):
        return self.read_format('I', 4)

    def int64_read(self):
        return self.read_format('q', 8)

    def uint64_read(self):
        return self.read_format('Q', 8)
        
def pad_to_16_byte_align(data):
    b = bytearray(data)
    l = len(b)
    new_len = ceil(l/16)*16
    return b + bytearray(new_len-l)
    
def _16_byte_align(addr):
    return ceil(addr/16)*16
    
def bytes_to_long(bytes):
    assert len(bytes) == 8
    return sum((b << (k * 8) for k, b in enumerate(bytes)))

def murmur64_hash(data: Any, seed: int = 0):

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
	
def list_files_recursive(path="."):
    files = []
    if os.path.isfile(path):
        return [path]
    else:
        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                files.extend(list_files_recursive(full_path))
            else:
                files.append(full_path)
        return files

def language_lookup(lang_string):
    try:
        return LANGUAGE_MAPPING[lang_string]
    except:
        return int(lang_string)
    
def strip_patch_index(filename):
    split = filename.split(".")
    for n in range(len(split)):
        if "patch_" in split[n]:
            del split[n]
            break
    filename = ".".join(split)
    return filename