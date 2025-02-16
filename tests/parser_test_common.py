import functools
import os

from concurrent.futures import ProcessPoolExecutor as Pool, Future
from collections.abc import Callable

import env

from log import logger


def test_all_archive_multi_process(func: Callable[[str], None], func_name: str):
    os.environ["TEST_RAND"] = "0"
    os.environ["TEST_LAYER"] = "0"
    os.environ["TEST_ACTOR_MIXER"] = "0"

    files = os.scandir(env.get_data_path())

    with Pool(8) as p:
        tests: list[tuple[str, Future]] = []
        for file in files:
            if not file.is_file():
                continue

            archive, ext = os.path.splitext(file.path)
            if ext != ".stream":
                continue

            binding = functools.partial(func, archive)
            tests.append((os.path.basename(archive), p.submit(binding)))

        finished_tests_count = 0
        failed_tests: list[tuple[str, BaseException]] = []
        while finished_tests_count < len(tests):
            for test in tests:
                if not test[1].done():
                    continue
                finished_tests_count += 1
                err = test[1].exception()
                if err != None:
                    failed_tests.append((os.path.basename(test[0]), err))

        if len(failed_tests) > 0:
            logger.critical(f"There are failed tests in {func_name}.")
            for failed_test in failed_tests:
                logger.critical(f"{failed_test[0]}: {failed_test[1]}")

def test_all_archive_sync(func: Callable[[str], None]):
    os.environ["TEST_RAND"] = "0"
    os.environ["TEST_LAYER"] = "0"
    os.environ["TEST_ACTOR_MIXER"] = "0"

    files = os.scandir(env.get_data_path())

    for file in files:
        if not file.is_file():
            continue

        archive, ext = os.path.splitext(file.path)
        if ext != ".stream":
            continue

        binding = functools.partial(func, archive)
        binding()
