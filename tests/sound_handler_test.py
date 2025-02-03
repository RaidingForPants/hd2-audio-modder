import asyncio
import functools
import posixpath as xpath
import time
import unittest

from typing import Callable, Literal
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

from core import SoundHandler, Mod
from env import get_data_path
from log import logger

class TestSoundHandler(unittest.TestCase):

    @staticmethod
    def play_sound_callback(
        lock: Lock,
        sound_id: int,
        audio_data: bytearray | Literal[b""],
        sound_handler: SoundHandler,
        callback: Callable | None = None
    ):
        if audio_data == b"":
            return
        lock.acquire()
        asyncio.run(sound_handler.play_audio_async(sound_id, audio_data, callback))
        lock.release()
        logger.info("Release lock.")

    # def test_sound_handler(self):
    #     sound_handler = SoundHandler.get_instance()
    #     mod = Mod("test_sound_handler")
    #     mod.load_archive_file(xpath.join(get_data_path(), "2c26bc4c6592fa14"))
    #     lock = Lock()
    #     with ThreadPoolExecutor(max_workers = 8) as p:
    #         while True:
    #             try:
    #                 audio_source_id = int(input("Input audio source ID: ").strip())
    #                 binding = functools.partial(
    #                     TestSoundHandler.play_sound_callback,
    #                     lock,
    #                     audio_source_id,
    #                     mod.get_audio_source(audio_source_id).get_data(),
    #                     sound_handler,
    #                 )
    #                 p.submit(binding)
    #             except (EOFError, KeyboardInterrupt):
    #                 break

    def test_sound_handler_thread_compete(self):
        sound_handler = SoundHandler.get_instance()
        mod = Mod("test_sound_handler")
        mod.load_archive_file(xpath.join(get_data_path(), "2c26bc4c6592fa14"))
        lock = Lock()
        with ThreadPoolExecutor(max_workers = 8) as p:
            counter = 8
            while counter > 0:
                binding = functools.partial(
                    TestSoundHandler.play_sound_callback,
                    lock,
                    987563718, # Should last for more than 2 second
                    mod.get_audio_source(987563718).get_data(),
                    sound_handler
                )
                p.submit(binding)
                counter -= 1
                time.sleep(2)
