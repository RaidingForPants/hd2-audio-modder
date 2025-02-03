import asyncio
import locale
import os
import posixpath as xpath 
import subprocess
import xml.etree.ElementTree as etree

from collections.abc import Iterable
from subprocess import CalledProcessError

from const import DEFAULT_CONVERSION_SETTING, WWISE_SUPPORTED_SYSTEMS
from env import DEFAULT_WWISE_PROJECT, VGMSTREAM, SYSTEM, TMP, WWISE_CLI
from log import logger
from fileutil import to_posix


async def to_wav(file_path: str):
    if not os.path.exists(file_path):
        raise OSError(f"Wave file {file_path} does not exists.")

    file_path = to_posix(file_path)
    file_path_wave = xpath.join(
        TMP, f"{xpath.splitext(xpath.basename(file_path))[0]}.wav"
    )

    proc = await asyncio.subprocess.create_subprocess_exec(
        *[VGMSTREAM, "-o", f"{file_path_wave}", f"{file_path}"],
        stdout = None,
        stderr = None
    )

    rcode = await proc.wait()

    return file_path, file_path_wave, rcode 


async def to_wave_batch(file_paths: Iterable[str]):
    result = await asyncio.gather(
        *[to_wav(file_path) for file_path in file_paths]
    )
    return result


async def wwise_project_migration(wwise_project: str):
    if not os.path.exists(wwise_project):
        raise OSError(f"Wwise project {wwise_project} does not exists.")

    proc = await asyncio.subprocess.create_subprocess_exec(
        *[WWISE_CLI, "migrate", wwise_project, "--quiet"]
    )

    rcode = await proc.wait()

    return rcode


async def wwise_conversion(
    source_list: str, 
    wwise_project: str = DEFAULT_WWISE_PROJECT
):
    if not os.path.exists(wwise_project):
        raise OSError(f"Wwise project {wwise_project} does not exists.")
    if not os.path.exists(source_list):
        raise OSError(f"Source list: {source_list} does not exists.")

    proc = await asyncio.create_subprocess_exec(
        *[
            WWISE_CLI, "convert-external-source", wwise_project,
            "--platform", "Windows",
            "--source-file", source_list,
            "--output", TMP,
         ]
    )

    rcode = await proc.wait()

    return rcode


async def convert_wav_to_wem(
    wavs: list[str], 
    wwise_project: str = DEFAULT_WWISE_PROJECT,
    conversion_setting: str = DEFAULT_CONVERSION_SETTING
):
    """
    @exception
    - CalledProcessError
    - OSError
    - NotImplementedError
    """
    if not os.path.exists(wwise_project):
        raise OSError(f"Wwise project {wwise_project} does not exists.")
    if len(wavs) <= 0:
        return None
    if SYSTEM not in WWISE_SUPPORTED_SYSTEMS:
        raise NotImplementedError(
            "The current operating system does not support this feature."
        )
    source_list = create_external_sources_list(wavs, conversion_setting)

    rcode = await wwise_project_migration(wwise_project)
    if rcode != 0:
        raise CalledProcessError(rcode, f"{WWISE_CLI} migrate")

    convert_dest = xpath.join(TMP, SYSTEM)

    rcode = await wwise_conversion(source_list, wwise_project)
    if rcode != 0:
        raise CalledProcessError(rcode, f"{WWISE_CLI} convert-external-source")

    try:
        os.remove(source_list)
    except OSError as err:
        logger.error(err)

    return convert_dest


async def get_wem_length(file_path: str):
    """
    @exception
    - CalledProcessError
    - OSError
    - RuntimeError
    """
    if not os.path.exists(file_path):
        raise OSError(f"Wem file {file_path} does not exists.")

    proc = await asyncio.subprocess.create_subprocess_exec(
        *[ VGMSTREAM, "-m", file_path ],
        stdout = asyncio.subprocess.PIPE,
        stderr = asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    rcode = await proc.wait()
    if rcode != 0:
        raise CalledProcessError(
            rcode, 
            f"{VGMSTREAM} -m", 
            stderr = stderr.decode(locale.getpreferredencoding())
        )

    lines = stdout.decode(locale.getpreferredencoding()).split("\n")
    sample_rate = -1.0
    total_samples = -1
    for line in lines:
        if "sample rate" in line:
            sample_rate = float(line[13:line.index("Hz") - 1])
        if "stream total samples" in line:
            total_samples = int(line[22:line.index("(") - 1])
    if sample_rate < 0.0:
        raise RuntimeError(f"Failed obtain sample rate of wem file {file_path}")
    if total_samples < 0:
        raise RuntimeError(f"Failed to obtain total samples of wem file {file_path}")

    return total_samples * 1000 / sample_rate


def get_wem_length_sync(file_path: str):
    """
    @description
    - For testing
    """
    sample_rate = -1.0
    total_samples = -1

    process = subprocess.run([VGMSTREAM, "-m", file_path], capture_output=True)
    process.check_returncode()

    for line in process.stdout.decode(locale.getpreferredencoding()).split("\n"):
        if "sample rate" in line:
            sample_rate = float(line[13:line.index("Hz")-1])
        if "stream total samples" in line:
            total_samples = int(line[22:line.index("(")-1])

    if sample_rate < 0.0:
        raise RuntimeError(f"Failed obtain sample rate of wem file {file_path}")
    if total_samples < 0:
        raise RuntimeError(f"Failed to obtain total samples of wem file {file_path}")

    return total_samples * 1000 / sample_rate


def create_external_sources_list(
    sources: Iterable[str], 
    conversion_setting: str = DEFAULT_CONVERSION_SETTING
):
    root = etree.Element("ExternalSourcesList", attrib={
        "SchemaVersion": "1",
        "Root": __file__
    })

    file = etree.ElementTree(root)

    for source in sources:
        etree.SubElement(root, "Source", attrib={
            "Path": to_posix(source),
            "Conversion": conversion_setting,
            "Destination": xpath.basename(source)
        })

    file.write(xpath.join(TMP, "external_sources.wsources"))
    
    return xpath.join(TMP, "external_sources.wsources")
