"""
CLI Core Module - Encapsulates main business logic for CLI-friendly interfaces
Provides async interfaces, supports config overrides and resource management
"""

import os
import asyncio
import shutil
from typing import Any

# 导入核心模块
import config as cfg
import db
from core import ModHandler, Mod, GameArchive, SoundHandler
from env import *
from util import *
from log import logger


class CLICore:
    """CLI core functionality encapsulation"""

    def __init__(self):
        self.app_config: cfg.Config | None = None
        self.lookup_store: Any | None = None
        self.mod_handler: ModHandler | None = None
        self.sound_handler: SoundHandler | None = None
        self.temp_dirs: list[str] = []
        self.is_initialized = False
        self.config_overrides: dict[str, Any] = {}

    async def initialize(self, config_overrides: dict[str, Any] | None = None):
        """Initialize CLI core"""
        if self.is_initialized:
            return

        logger.info("Initializing CLI core...")

        # Apply config overrides
        if config_overrides:
            self.config_overrides.update(config_overrides)

        # Load config
        self.app_config = cfg.load_config()
        if not self.app_config:
            raise RuntimeError("Failed to load application config")

        # Apply temporary config overrides
        self._apply_config_overrides()

        # Initialize database
        await self._initialize_database()

        # Initialize ModHandler
        self.mod_handler = ModHandler.get_instance(self.sqlite_db)
        self.mod_handler.create_new_mod("cli_default")

        # Initialize SoundHandler
        self.sound_handler = SoundHandler.get_instance()

        # Create temp directories
        await self._setup_temp_directories()

        self.is_initialized = True
        logger.info("CLI core initialized")

    def _apply_config_overrides(self):
        """Apply config overrides"""
        for key, value in self.config_overrides.items():
            if hasattr(self.app_config, key):
                logger.info(f"Override config: {key} = {value}")
                setattr(self.app_config, key, value)
            else:
                logger.warning(f"Unknown config item: {key}")

    async def _initialize_database(self):
        """Initialize database connection"""
        try:
            # Check if friendly names database exists
            from const import FRIENDLYNAMES_DB
            from backend.db import SQLiteDatabase, config_sqlite_conn

            # Create SQLiteDatabase instance for ModHandler
            if os.path.exists(FRIENDLYNAMES_DB):
                conn_config = config_sqlite_conn(FRIENDLYNAMES_DB)
                self.sqlite_db = SQLiteDatabase(conn_config)
                self.lookup_store = db.FriendlyNameLookup(FRIENDLYNAMES_DB)
                logger.info("Loaded friendly names database")
            else:
                # Create a temporary in-memory database
                import tempfile

                temp_db_path = tempfile.mktemp(suffix=".db")
                conn_config = config_sqlite_conn(temp_db_path)
                self.sqlite_db = SQLiteDatabase(conn_config)
                self.lookup_store = None
                logger.warning("Friendly names database not found, using temporary database, some features may be limited")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            # Create a temporary in-memory database as fallback
            import tempfile

            temp_db_path = tempfile.mktemp(suffix=".db")
            conn_config = config_sqlite_conn(temp_db_path)
            self.sqlite_db = SQLiteDatabase(conn_config)
            self.lookup_store = None

    async def _setup_temp_directories(self):
        """Setup temporary directories"""
        try:
            from const import CACHE, TMP

            # Create cache directory
            if not os.path.exists(CACHE):
                os.makedirs(CACHE, mode=0o777)
                self.temp_dirs.append(CACHE)

            # Create temp directory
            if not os.path.exists(TMP):
                os.makedirs(TMP, mode=0o777)
                self.temp_dirs.append(TMP)

        except Exception as e:
            logger.error(f"Failed to create temporary directories: {e}")
            raise

    async def cleanup(self):
        """Cleanup resources"""
        if not self.is_initialized:
            return

        logger.info("Cleaning up CLI core resources...")

        # Stop audio playback
        if self.sound_handler:
            self.sound_handler.kill_sound()

        # Cleanup temp directories
        for temp_dir in self.temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")

        # Save config (if modified)
        if self.app_config:
            try:
                self.app_config.save_config()
            except Exception as e:
                logger.warning(f"Failed to save config: {e}")

        self.is_initialized = False
        logger.info("CLI core resources cleaned up")

    def get_active_mod(self) -> Mod | None:
        """Get current active Mod"""
        if not self.is_initialized or not self.mod_handler:
            return None
        try:
            return self.mod_handler.get_active_mod()
        except Exception as e:
            logger.error(f"Failed to get active Mod: {e}")
            return None

    async def import_archive(self, archive_path: str) -> bool:
        """Import archive file"""
        if not self.is_initialized:
            raise RuntimeError("CLI core not initialized")

        try:
            logger.info(f"Importing archive: {archive_path}")

            if not os.path.exists(archive_path):
                logger.error(f"Archive file not found: {archive_path}")
                return False

            # Check if it's a patch file
            if ".patch" in os.path.basename(archive_path):
                return await self.import_patch(archive_path)

            mod = self.get_active_mod()
            if not mod:
                logger.error("No active Mod")
                return False

            # Run IO-bound operation in thread pool
            success = await asyncio.get_event_loop().run_in_executor(
                None, mod.load_archive_file, archive_path
            )

            if success:
                logger.info(f"Successfully imported archive: {os.path.basename(archive_path)}")
                return True
            else:
                logger.error(f"Failed to import archive: {archive_path}")
                return False

        except Exception as e:
            logger.error(f"Error occurred while importing archive: {e}")
            return False

    async def import_patch(self, patch_path: str) -> bool:
        """Import patch file"""
        if not self.is_initialized:
            raise RuntimeError("CLI core not initialized")

        try:
            if self.sound_handler:
                self.sound_handler.kill_sound()

            logger.info(f"Importing patch: {patch_path}")

            if not os.path.exists(patch_path):
                logger.error(f"Patch file not found: {patch_path}")
                return False

            # Handle file extension
            if os.path.splitext(patch_path)[1] in (".stream", ".gpu_resources"):
                patch_path = os.path.splitext(patch_path)[0]

            mod = self.get_active_mod()
            if not mod:
                logger.error("No active Mod")
                return False

            # Step 1: Process patch content, find missing soundbanks
            logger.info("Analyzing patch content...")
            (
                missing_soundbank_ids,
                new_archive,
                patch_file,
            ) = await self._process_patch_content(patch_path)

            # Step 2: Find and load missing archives
            await self._load_missing_archives(missing_soundbank_ids, new_archive)

            # Step 3: Apply patch
            logger.info("Applying patch...")
            success = await asyncio.get_event_loop().run_in_executor(
                None, mod.import_patch, patch_file
            )

            if success:
                logger.info(f"Successfully imported patch: {os.path.basename(patch_path)}")
                return True
            else:
                logger.error(f"Failed to import patch: {patch_path}")
                return False

        except Exception as e:
            logger.error(f"Error occurred while importing patch: {e}")
            return False

    async def _process_patch_content(
        self, patch_path: str
    ) -> tuple[list, "GameArchive", str]:
        """Process patch content, return missing soundbank IDs, new archive, and patch file path"""
        from core import GameArchive

        # Run IO-bound operation in thread pool
        def process_patch():
            new_archive = GameArchive.from_file(patch_path)
            mod = self.get_active_mod()
            if not mod:
                raise RuntimeError("No active Mod")
            missing_soundbank_ids = [
                soundbank_id
                for soundbank_id in new_archive.get_wwise_banks().keys()
                if soundbank_id not in mod.get_wwise_banks()
            ]
            return missing_soundbank_ids, new_archive, patch_path

        return await asyncio.get_event_loop().run_in_executor(None, process_patch)

    async def _load_missing_archives(
        self, missing_soundbank_ids: list, new_archive: "GameArchive"
    ) -> None:
        """Load missing archives"""
        archives = set()
        missing_soundbanks = set()

        # Check if base text archive needs to be loaded
        mod = self.get_active_mod()
        if not mod:
            raise RuntimeError("No active Mod")
        if (
            len(new_archive.text_banks) > 0
            and "9ba626afa44a3aa3" not in mod.get_game_archives().keys()
        ):
            archives.add("9ba626afa44a3aa3")
            logger.info("Need to load base text archive: 9ba626afa44a3aa3")

        # Use name_lookup to find archives for missing soundbanks
        if (
            self.lookup_store is not None
            and self.app_config
            and os.path.exists(self.app_config.game_data_path)
        ):
            logger.info(f"Looking up {len(missing_soundbank_ids)} missing soundbanks...")
            for soundbank_id in missing_soundbank_ids:
                try:
                    r = self.lookup_store.lookup_soundbank(soundbank_id)
                    if r.success:
                        archives.add(r.archive)
                        logger.info(
                            f"Found archive for soundbank {soundbank_id}: {r.archive}"
                        )
                    else:
                        missing_soundbanks.add(
                            new_archive.get_wwise_banks()[soundbank_id]
                        )
                        logger.warning(
                            f"Could not find archive for soundbank {soundbank_id}"
                        )
                except Exception as e:
                    logger.warning(f"Error looking up soundbank {soundbank_id}: {e}")
                    missing_soundbanks.add(new_archive.get_wwise_banks()[soundbank_id])
        else:
            logger.warning(
                "name_lookup unavailable or game data path does not exist, cannot auto-find missing archives"
            )
            missing_soundbanks.update(new_archive.get_wwise_banks().values())

        # Log missing soundbanks
        if missing_soundbanks:
            logger.warning(
                f"{len(missing_soundbanks)} soundbanks could not be auto-loaded, patch may be outdated"
            )
            for bank in missing_soundbanks:
                logger.warning(
                    f"Missing soundbank: {bank.dep.data.replace(chr(0), '') if hasattr(bank, 'dep') and hasattr(bank.dep, 'data') else str(bank.get_id())}"
                )

        # Load found archives
        if archives and self.app_config:
            logger.info(f"Loading {len(archives)} archives...")
            for archive_name in archives:
                archive_path = os.path.join(
                    self.app_config.game_data_path, archive_name
                )
                if os.path.exists(archive_path):
                    logger.info(f"Loading archive: {archive_name}")
                    try:
                        success = await asyncio.get_event_loop().run_in_executor(
                            None, mod.load_archive_file, archive_path
                        )
                        if success:
                            logger.info(f"Successfully loaded archive: {archive_name}")
                        else:
                            logger.warning(f"Archive already exists or failed to load: {archive_name}")
                    except Exception as e:
                        logger.error(f"Error loading archive {archive_name}: {e}")
                else:
                    logger.error(f"Archive file not found: {archive_path}")
        else:
            logger.info("No extra archives need to be loaded")

    async def import_audio_files(
        self, file_paths: list[str], target_ids: list[str] | None = None
    ) -> bool:
        """Import audio files"""
        if not self.is_initialized:
            raise RuntimeError("CLI core not initialized")

        try:
            logger.info(f"Importing {len(file_paths)} audio files")

            mod = self.get_active_mod()
            if not mod:
                logger.error("No active Mod")
                return False

            # Construct file dictionary
            file_dict = {}
            for i, file_path in enumerate(file_paths):
                if not os.path.exists(file_path):
                    logger.warning(f"Audio file not found: {file_path}")
                    continue

                # If target IDs are provided, use them; otherwise try to parse from filename
                if target_ids and i < len(target_ids):
                    target_id = target_ids[i]
                    try:
                        target_id = int(target_id)
                    except ValueError:
                        logger.error(f"Invalid target ID: {target_id}")
                        continue
                    file_dict[file_path] = [target_id]
                else:
                    # Try to parse ID from filename
                    from util import parse_filename

                    try:
                        parsed_id = parse_filename(os.path.basename(file_path))
                        file_dict[file_path] = [parsed_id]
                    except Exception as e:
                        logger.warning(f"Could not parse filename ID: {file_path}, error: {e}")
                        continue

            if not file_dict:
                logger.error("No valid audio files to import")
                return False

            # Run IO-bound operation in thread pool
            await asyncio.get_event_loop().run_in_executor(
                None, mod.import_files, file_dict
            )

            logger.info(f"Successfully imported {len(file_dict)} audio files")
            return True

        except Exception as e:
            logger.error(f"Error occurred while importing audio files: {e}")
            return False

    async def write_patch(
        self, output_dir: str, separate_patches: bool = False, output_filename: str = ""
    ) -> bool:
        """Write patch file to specified directory

        Args:
            output_dir: Output directory path
            separate_patches: Whether to generate separate patch files
            output_filename: Specified output filename (optional)

        Returns:
            List of generated file paths
        """
        if not self.is_initialized:
            raise RuntimeError("CLI core not initialized")

        try:
            logger.info(f"Writing patch to directory: {output_dir}")

            mod = self.get_active_mod()
            if not mod:
                logger.error("No active Mod")
                return False

            # Ensure output directory exists
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            # Run IO-bound operation in thread pool
            if separate_patches:
                await asyncio.get_event_loop().run_in_executor(
                    None, mod.write_separate_patches, output_dir
                )
            else:
                await asyncio.get_event_loop().run_in_executor(
                    None, mod.write_patch, output_dir, output_filename
                )

            return True

        except Exception as e:
            logger.error(f"Error occurred while writing patch: {e}")
            return False

    async def dump_audio_files(self, output_dir: str, format: str = "wav") -> bool:
        """Export audio files"""
        if not self.is_initialized:
            raise RuntimeError("CLI core not initialized")

        try:
            logger.info(f"Exporting audio files to: {output_dir}")

            mod = self.get_active_mod()
            if not mod:
                logger.error("No active Mod")
                return False

            # Ensure output directory exists
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            # Run IO-bound operation in thread pool
            if format.lower() == "wav":
                await asyncio.get_event_loop().run_in_executor(
                    None, mod.dump_all_as_wav, output_dir
                )
            else:
                await asyncio.get_event_loop().run_in_executor(
                    None, mod.dump_all_as_wem, output_dir
                )

            logger.info(f"Successfully exported audio files to: {output_dir}")
            return True

        except Exception as e:
            logger.error(f"Error occurred while exporting audio files: {e}")
            return False

    def get_archives_info(self) -> dict[str, Any]:
        """Get loaded archives info"""
        if not self.is_initialized:
            return {}

        mod = self.get_active_mod()
        if not mod:
            return {}

        archives_info = {}
        for name, archive in mod.get_game_archives().items():
            archives_info[name] = {
                "name": archive.name,
                "path": archive.path,
                "num_files": archive.num_files,
                "num_audio_sources": len(archive.audio_sources),
                "num_wwise_banks": len(archive.wwise_banks),
                "num_wwise_streams": len(archive.wwise_streams),
                "num_video_sources": len(archive.video_sources),
                "num_text_banks": len(archive.text_banks),
            }

        return archives_info

    def get_audio_sources_info(self) -> dict[str, Any]:
        """Get audio sources info"""
        if not self.is_initialized:
            return {}

        mod = self.get_active_mod()
        if not mod:
            return {}

        audio_info = {}
        for audio_id, audio_source in mod.get_audio_sources().items():
            audio_info[str(audio_id)] = {
                "id": audio_source.get_id(),
                "short_id": audio_source.get_short_id(),
                "stream_type": audio_source.stream_type,
                "is_modified": audio_source.is_modified(),
                "data_size": len(audio_source.get_data())
                if audio_source.get_data()
                else 0,
            }

        return audio_info

    def get_status_info(self) -> dict[str, Any]:
        """Get status info"""
        if not self.is_initialized:
            return {"status": "uninitialized"}

        mod = self.get_active_mod()
        archives_info = self.get_archives_info()
        audio_info = self.get_audio_sources_info()

        return {
            "status": "initialized",
            "mod_name": mod.name if mod else "None",
            "num_archives": len(archives_info),
            "num_audio_sources": len(audio_info),
            "config": {
                "game_data_path": self.app_config.game_data_path
                if self.app_config
                else None,
                "rad_tools_path": self.app_config.rad_tools_path
                if self.app_config
                else None,
                "theme": self.app_config.theme if self.app_config else None,
            },
            "has_database": self.lookup_store is not None,
            "config_overrides": self.config_overrides,
        }

    def update_config(self, config_updates: dict[str, Any]):
        """Update config"""
        if not self.is_initialized:
            raise RuntimeError("CLI core not initialized")

        self.config_overrides.update(config_updates)
        self._apply_config_overrides()

        logger.info(f"Config updated: {config_updates}")

    async def revert_all_changes(self) -> bool:
        """Revert all changes"""
        if not self.is_initialized:
            raise RuntimeError("CLI core not initialized")

        try:
            mod = self.get_active_mod()
            if not mod:
                logger.error("No active Mod")
                return False

            # Run operation in thread pool
            await asyncio.get_event_loop().run_in_executor(None, mod.revert_all)

            logger.info("All changes reverted")
            return True

        except Exception as e:
            logger.error(f"Error occurred while reverting changes: {e}")
            return False

    async def clear_mod(self) -> bool:
        """Clear current Mod"""
        if not self.is_initialized or not self.mod_handler:
            raise RuntimeError("CLI core not initialized")

        try:
            # Delete current Mod and create new
            self.mod_handler.delete_mod("cli_default")
            self.mod_handler.create_new_mod("cli_default")

            logger.info("Current Mod cleared")
            return True

        except Exception as e:
            logger.error(f"Error occurred while clearing Mod: {e}")
            return False
