import struct
import os
#import lz4.block
from lz4 import block
import sys

def read_int(file):
	return struct.unpack("<I", file.read(4))[0]
    
def read_long(file):
    return struct.unpack("<Q", file.read(8))[0]
    
def read_short(file):
    return struct.unpack("<H", file.read(2))[0]
    
def read_char(file):
    return struct.unpack("<B", file.read(1))[0]
    
def to_int(byte_data):
    return int.from_bytes(byte_data, "little")


# chunk type flags
CONTINUE = 0x04
START = 0x02
UNK = 0x01

# compression
UNCOMPRESSED = 0x00
COMPRESSED = 0x03

# package type
LEGACY = 3
BUNDLED = 2
DSAR = 1
UNKNOWN = 0

done_init = False
package_contents = {}

def is_slim_version(file_path):
    return not os.path.exists(os.path.join(file_path, "9ba626afa44a3aa3"))
    
def decompress_dsar(file_path):
    
    # decompresses entire bundle file
    
    bundle = open(file_path, 'rb')

    bundle.seek(8)
    num_chunks = read_int(bundle) # num data chunks
    data = bytearray()
    file_count = 0

    for i in range(num_chunks):
        bundle.seek(0x20 + i * 0x20)
        uncompressed_offset = read_long(bundle)
        compressed_offset =   read_long(bundle)
        uncompressed_size =   read_int(bundle)
        compressed_size =     read_int(bundle)
        compression_type =    read_char(bundle)
        chunk_type =          read_char(bundle)
        
        bundle.seek(compressed_offset)
        
        # read and decompress data
        temp_data = bundle.read(compressed_size)
        if compression_type == COMPRESSED:
            temp_data = block.decompress(temp_data, uncompressed_size=uncompressed_size)
        data += temp_data

    bundle.close()
    
    return data
    
def get_resource_from_bundle(bundle_path: str, resource_file_offset: int):
    
    # returns resource from bundle file; resource determined by file offset in uncompressed bundle
    # handles resources split into multiple compressed chunks to return complete resource
    
    bundle = open(bundle_path, 'rb')
    
    bundle.seek(8)
    num_chunks = read_int(bundle) # num data chunks
    data = bytearray()
    found_resource = False

    for i in range(num_chunks):
        bundle.seek(0x20 + i * 0x20)
        uncompressed_offset = read_long(bundle)
        if uncompressed_offset != resource_file_offset and not found_resource: continue
        found_resource = True
        compressed_offset =   read_long(bundle)
        uncompressed_size =   read_int(bundle)
        compressed_size =     read_int(bundle)
        compression_type =    read_char(bundle)
        chunk_type =          read_char(bundle)
        
        bundle.seek(compressed_offset)
        
        if chunk_type & START and len(data) > 0:
            bundle.close()
            return data
        
        # read and decompress data
        temp_data = bundle.read(compressed_size)
        if compression_type == COMPRESSED:
            temp_data = block.decompress(temp_data, uncompressed_size=uncompressed_size)
        data += temp_data
        
        if i == num_chunks - 1:
            bundle.close()
            return data
    
    bundle.close()
    
class Package:
    
    def __init__(self):
        self.size = 0
        self.name = ""
        self.entries = []
    
class BundleEntry:
    
    def __init__(self):
        self.start_offset = self.bundle_index = self.original_archive_offset = 0
        

def init_bundle_mapping(game_data_folder: str):
    bundle_contents = decompress_dsar(os.path.join(game_data_folder, "bundles.nxa"))
    
    num_packages = to_int(bundle_contents[0x10:0x14])
    num_bundles = to_int(bundle_contents[0x0C:0x10])
    
    bundle_location = 0
    bundles = [[] for _ in range(num_bundles)]
    
    global package_contents
    
    # check name of each package to find the right one
    for n in range(num_packages):
        bundle_location = 0x18 + n * 0x18
        bundle_size = to_int(bundle_contents[bundle_location:bundle_location+8])
        name_offset = to_int(bundle_contents[bundle_location+8:bundle_location+12])
        i = 0
        while bundle_contents[name_offset+i] != 0:
            i += 1
        name = bundle_contents[name_offset:name_offset+i].decode()
        # parse all BundleEntries for each package
        items_count = to_int(bundle_contents[bundle_location+12:bundle_location+16])
        items_offset = to_int(bundle_contents[bundle_location+16:bundle_location+20])
        for i in range(items_count):
            bundle_entry = BundleEntry()
            original_archive_offset = to_int(bundle_contents[items_offset + 0x10*i:items_offset + 0x10*i + 8])
            uncompressed_bundle_offset = to_int(bundle_contents[items_offset + 0x10*i + 8:items_offset + 0x10*i + 12])
            bundle_index = (bundle_contents[items_offset + 0x10*i + 0x0F])
            bundle_entry.bundle_index = bundle_index
            bundle_entry.start_offset = uncompressed_bundle_offset
            bundle_entry.original_archive_offset = original_archive_offset
            try:
                package_contents[name].entries.append(bundle_entry)
            except KeyError:
                package_contents[name] = Package()
                package_contents[name].name = name
                package_contents[name].size = bundle_size
                package_contents[name].entries = [bundle_entry]
    
    
def get_resources_from_bundle(bundle_path: str, start_offset: int, size: int):
    
    

    # returns resource from bundle file; resource determined by file offset in uncompressed bundle
    # handles resources split into multiple compressed chunks to return complete resource
    
    current_size = 0
    resources = []
    
    while current_size < size:
        resource = get_resource_from_bundle(bundle_path, start_offset + current_size)
        current_size += len(resource)
        resources.append(resource)
    return resources

    
def load_package(package_name: str, game_data_folder: str, toc_only = False):
    
    if not package_contents:
        init_bundle_mapping(game_data_folder)
    
    full_path = os.path.join(game_data_folder, package_name)
    
    package_type = 0
    
    if os.path.exists(full_path):
        with open(full_path, 'rb') as f:
            magic = int.from_bytes(f.read(4), "little")
            if magic == 1380012868: # compressed DSAR file
                package_type = DSAR
            else:
                package_type = LEGACY
    else:
        package_type = BUNDLED
        
    toc_data = bytearray()
    gpu_data = bytearray()
    stream_data = bytearray()
        
    if package_type == BUNDLED:
        content = reconstruct_package_from_bundles(package_name, game_data_folder)
        if content: toc_data = content
        
        if not toc_only:
            content = reconstruct_package_from_bundles(f"{package_name}.gpu_resources", game_data_folder)
            if content: gpu_data = content
                    
            content = reconstruct_package_from_bundles(f"{package_name}.stream", game_data_folder)
            if content: stream_data = content
        
    elif package_type == DSAR:
        toc_data = decompress_dsar(full_path)
        if not toc_only:
            if os.path.exists(full_path+".gpu_resources"):
                gpu_data = decompress_dsar(full_path+".gpu_resources")
            if os.path.exists(full_path+".stream"):
                stream_data = decompress_dsar(full_path+".stream")
        
    elif package_type == LEGACY:
        with open(full_path, 'rb') as f:
            toc_data = f.read()
        if not toc_only:
            if os.path.exists(full_path+".gpu_resources"):
                with open(full_path+".gpu_resources", 'rb') as f:
                    gpu_data = f.read()
            if os.path.exists(full_path+".stream"):
                with open(full_path+".stream", 'rb') as f:
                    stream_data = f.read()
                
    if toc_only: return toc_data
    return toc_data, gpu_data, stream_data
    
def reconstruct_package_from_bundles(package_name: str, game_data_folder: str):
    
    # reconstructs a package file from compressed bundle files
    package_name = os.path.basename(package_name)
    
    global package_contents
    
    package = package_contents[package_name]
    
    package_data = bytearray(package.size)
    size = 0
    for i, item in enumerate(package.entries):
        try:
            item_size = package.entries[i+1].original_archive_offset - item.original_archive_offset
        except IndexError:
            item_size = package.size - item.original_archive_offset
        size += item_size
        resources = get_resources_from_bundle(os.path.join(game_data_folder, f"bundles.{item.bundle_index:02d}.nxa"), item.start_offset, item_size)
        combined_data = b"".join(resources)
        package_data[item.original_archive_offset:item.original_archive_offset+len(combined_data)] = combined_data
    return package_data
    
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: <game data folder> <package name> [<output folder>]")
        sys.exit()
    game_data_folder = sys.argv[1]
    package_name = sys.argv[2]
    if len(sys.argv) == 3:
        output_folder = "."
    else:
        output_folder = sys.argv[3]
    init_bundle_mapping(game_data_folder)
    content = reconstruct_package_from_bundles(package_name, game_data_folder)
    if content:
        with open(os.path.join(output_folder, package_name), 'wb') as f:
            f.write(content)
            
    content = reconstruct_package_from_bundles(f"{package_name}.gpu_resources", game_data_folder)
    if content:
        with open(os.path.join(output_folder, f"{package_name}.gpu_resources"), 'wb') as f:
            f.write(content)
            
    content = reconstruct_package_from_bundles(f"{package_name}.stream", game_data_folder)
    if content:
        with open(os.path.join(output_folder, f"{package_name}.stream"), 'wb') as f:
            f.write(content)