import asyncio
import posixpath as xpath 

from collections.abc import Iterable

from env import VGMSTREAM, TMP
from fileutil import to_posix


async def to_wav(file_path: str):
    file_path = to_posix(file_path)
    file_path_wave = xpath.join(
        TMP, f"{xpath.splitext(xpath.basename(file_path))[0]}.wav"
    )
    proc = await asyncio.subprocess.create_subprocess_exec(
        *[f"{VGMSTREAM}", "-o", f"{file_path_wave}", f"{file_path}"],
        stdout = None,
        stderr = None
    )

    rcode = await proc.wait()

    return file_path_wave, rcode 


async def to_wave_batch(file_paths: Iterable[str]):
    result = await asyncio.gather(
        *[to_wav(file_path) for file_path in file_paths]
    )
    return result
