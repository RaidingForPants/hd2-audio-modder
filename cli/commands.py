"""
CLI Command Module - Implements the execution logic for various CLI commands
Provides commands such as configure, import_archive, write_patch, import_audio, dump_audio, etc.
"""

import json
from typing import Any

from .core import CLICore
from .context import CLIContext
from log import logger


class CLICommands:
    """CLI Command Executor"""

    def __init__(self, cli_core: CLICore, context: CLIContext):
        self.cli_core = cli_core
        self.context = context

        # Command mapping
        self.commands = {
            "configure": self.configure,
            "import_archive": self.import_archive,
            "import_patch": self.import_patch,
            "import_audio": self.import_audio,
            "write_patch": self.write_patch,
            "dump_audio": self.dump_audio,
            "list_archives": self.list_archives,
            "list_audio": self.list_audio,
            "status": self.status,
            "revert_all": self.revert_all,
            "clear_mod": self.clear_mod,
            "set_variable": self.set_variable,
            "get_variable": self.get_variable,
            "list_variables": self.list_variables,
            "export_session": self.export_session,
            "import_session": self.import_session,
            "help": self.help,
        }

    async def execute_command(self, command: str, args: Any) -> bool:
        """Execute command"""
        if command not in self.commands:
            logger.error(f"Unknown command: {command}")
            self.context.record_command_execution(
                command, args, False, f"Unknown command: {command}"
            )
            return False

        try:
            logger.info(f"Executing command: {command}")
            logger.debug(f"Command args: {args}")

            # Execute command
            result = await self.commands[command](args)

            # Record command execution result
            self.context.record_command_execution(command, args, result, "")

            return result

        except Exception as e:
            error_msg = f"Command execution failed: {e}"
            logger.error(error_msg)
            self.context.record_command_execution(command, args, False, error_msg)
            return False

    async def configure(self, args: dict[str, Any] | str) -> bool:
        """Configure command"""
        try:
            if isinstance(args, str):
                # If it's a string, try to parse it as JSON
                if args.startswith("{") and args.endswith("}"):
                    config_dict = json.loads(args)
                else:
                    logger.error("Config parameter must be in JSON format")
                    return False
            elif isinstance(args, dict):
                config_dict = args
            else:
                logger.error("Invalid config parameter format")
                return False

            logger.info(f"Applying config: {config_dict}")

            # Update CLI core config
            self.cli_core.update_config(config_dict)

            # Update context variables
            self.context.update_variables(config_dict)

            logger.info("Config update completed")
            return True

        except Exception as e:
            logger.error(f"Config update failed: {e}")
            return False

    async def import_archive(self, args: str | dict[str, Any]) -> bool:
        """Import archive command"""
        try:
            if isinstance(args, dict):
                archive_path = args.get("path", "")
            else:
                archive_path = str(args)

            if not archive_path:
                logger.error("Archive path not specified")
                return False

            # Expand variables
            archive_path = self.context.expand_variables(archive_path)

            logger.info(f"Importing archive: {archive_path}")

            success = await self.cli_core.import_archive(archive_path)

            if success:
                logger.info(f"Successfully imported archive: {archive_path}")
                return True
            else:
                logger.error(f"Failed to import archive: {archive_path}")
                return False

        except Exception as e:
            logger.error(f"Error occurred while importing archive: {e}")
            return False

    async def import_patch(self, args: str | dict[str, Any]) -> bool:
        """Import patch command"""
        try:
            if isinstance(args, dict):
                patch_path = args.get("path", "")
            else:
                patch_path = str(args)

            if not patch_path:
                logger.error("Patch path not specified")
                return False

            # Expand variables
            patch_path = self.context.expand_variables(patch_path)

            logger.info(f"Importing patch: {patch_path}")

            success = await self.cli_core.import_patch(patch_path)

            if success:
                logger.info(f"Successfully imported patch: {patch_path}")
                return True
            else:
                logger.error(f"Failed to import patch: {patch_path}")
                return False

        except Exception as e:
            logger.error(f"Error occurred while importing patch: {e}")
            return False

    async def import_audio(self, args: str | dict[str, Any]) -> bool:
        """Import audio command"""
        try:
            if isinstance(args, dict):
                file_paths = args.get("files", [])
                target_ids = args.get("targets", [])
            else:
                # Simple format: single file path
                file_paths = [str(args)]
                target_ids = []

            if not file_paths:
                logger.error("Audio file path not specified")
                return False

            # Expand variables
            expanded_paths = [
                self.context.expand_variables(path) for path in file_paths
            ]

            logger.info(f"Importing audio files: {expanded_paths}")

            success = await self.cli_core.import_audio_files(expanded_paths, target_ids)

            if success:
                logger.info(f"Successfully imported audio files: {expanded_paths}")
                return True
            else:
                logger.error(f"Failed to import audio files: {expanded_paths}")
                return False

        except Exception as e:
            logger.error(f"Error occurred while importing audio files: {e}")
            return False

    async def write_patch(self, args: str | dict[str, Any]) -> bool:
        """Write patch command"""
        try:
            if isinstance(args, dict):
                output_dir = args.get("output_dir", "")
                output_filename = args.get("output_filename", "")
                separate_patches = args.get("separate", False)
            else:
                output_dir = str(args)
                output_filename = ""
                separate_patches = False

            if not output_dir:
                logger.error("Output directory not specified")
                return False

            # Expand variables
            output_dir = self.context.expand_variables(output_dir)
            output_filename = self.context.expand_variables(output_filename)

            logger.info(f"Writing patch to directory: {output_dir}")
            if output_filename:
                logger.info(f"Specified filename: {output_filename}")

            return await self.cli_core.write_patch(output_dir, separate_patches, output_filename)

        except Exception as e:
            logger.error(f"Error occurred while writing patch: {e}")
            return False

    async def dump_audio(self, args: str | dict[str, Any]) -> bool:
        """Export audio command"""
        try:
            if isinstance(args, dict):
                output_dir = args.get("output_dir", "")
                format = args.get("format", "wav")
            else:
                output_dir = str(args)
                format = "wav"

            if not output_dir:
                logger.error("Output directory not specified")
                return False

            # Expand variables
            output_dir = self.context.expand_variables(output_dir)

            logger.info(f"Exporting audio files to: {output_dir}")

            success = await self.cli_core.dump_audio_files(output_dir, format)

            if success:
                logger.info(f"Successfully exported audio files to: {output_dir}")
                return True
            else:
                logger.error(f"Failed to export audio files: {output_dir}")
                return False

        except Exception as e:
            logger.error(f"Error occurred while exporting audio files: {e}")
            return False

    async def list_archives(self, args: Any) -> bool:
        """List archives command"""
        try:
            archives_info = self.cli_core.get_archives_info()

            if not archives_info:
                logger.info("No loaded archives")
                return True

            logger.info("Loaded archives:")
            for name, info in archives_info.items():
                logger.info(f"  {name}:")
                logger.info(f"    Path: {info['path']}")
                logger.info(f"    File count: {info['num_files']}")
                logger.info(f"    Audio sources: {info['num_audio_sources']}")
                logger.info(f"    Wwise Banks: {info['num_wwise_banks']}")
                logger.info(f"    Wwise Streams: {info['num_wwise_streams']}")
                logger.info(f"    Video sources: {info['num_video_sources']}")
                logger.info(f"    Text banks: {info['num_text_banks']}")

            return True

        except Exception as e:
            logger.error(f"Error occurred while listing archives: {e}")
            return False

    async def list_audio(self, args: Any) -> bool:
        """List audio sources command"""
        try:
            audio_info = self.cli_core.get_audio_sources_info()

            if not audio_info:
                logger.info("No loaded audio sources")
                return True

            logger.info(f"Loaded audio sources (total {len(audio_info)}):")
            for audio_id, info in audio_info.items():
                status = "Modified" if info["is_modified"] else "Unmodified"
                logger.info(
                    f"  {audio_id}: {info['short_id']} - {status} ({info['data_size']} bytes)"
                )

            return True

        except Exception as e:
            logger.error(f"Error occurred while listing audio sources: {e}")
            return False

    async def status(self, args: Any) -> bool:
        """Status command"""
        try:
            status_info = self.cli_core.get_status_info()
            context_info = self.context.get_context_info()

            logger.info("=== System Status ===")
            logger.info(f"CLI Status: {status_info['status']}")
            logger.info(f"Active Mod: {status_info['mod_name']}")
            logger.info(f"Loaded Archives: {status_info['num_archives']}")
            logger.info(f"Audio Source Count: {status_info['num_audio_sources']}")
            logger.info(
                f"Database Status: {'Connected' if status_info['has_database'] else 'Not Connected'}"
            )

            logger.info("\n=== Config Info ===")
            config = status_info["config"]
            logger.info(f"Game Data Path: {config['game_data_path']}")
            logger.info(f"RAD Tools Path: {config['rad_tools_path']}")
            logger.info(f"Theme: {config['theme']}")

            if status_info["config_overrides"]:
                logger.info(f"Config Overrides: {status_info['config_overrides']}")

            logger.info("\n=== Session Info ===")
            logger.info(f"Session ID: {context_info['session_id']}")
            logger.info(f"Session Duration: {context_info['session_duration']:.1f}s")
            logger.info(f"Command Count: {context_info['command_count']}")
            logger.info(f"Success Count: {context_info['success_count']}")
            logger.info(f"Error Count: {context_info['error_count']}")
            logger.info(f"Variable Count: {context_info['variables_count']}")
            logger.info(f"Temporary File Count: {context_info['temporary_files_count']}")

            return True

        except Exception as e:
            logger.error(f"Error occurred while getting status: {e}")
            return False

    async def revert_all(self, args: Any) -> bool:
        """Revert all changes command"""
        try:
            logger.info("Reverting all changes...")

            success = await self.cli_core.revert_all_changes()

            if success:
                logger.info("All changes reverted")
                return True
            else:
                logger.error("Failed to revert changes")
                return False

        except Exception as e:
            logger.error(f"Error occurred while reverting changes: {e}")
            return False

    async def clear_mod(self, args: Any) -> bool:
        """Clear Mod command"""
        try:
            logger.info("Clearing current Mod...")

            success = await self.cli_core.clear_mod()

            if success:
                logger.info("Current Mod cleared")
                return True
            else:
                logger.error("Failed to clear Mod")
                return False

        except Exception as e:
            logger.error(f"Error occurred while clearing Mod: {e}")
            return False

    async def set_variable(self, args: str | dict[str, Any]) -> bool:
        """Set variable command"""
        try:
            if isinstance(args, dict):
                for name, value in args.items():
                    self.context.set_variable(name, value)
                    logger.info(f"Set variable: {name} = {value}")
            else:
                # Parse name=value format
                args_str = str(args)
                if "=" in args_str:
                    name, value = args_str.split("=", 1)
                    self.context.set_variable(name.strip(), value.strip())
                    logger.info(f"Set variable: {name.strip()} = {value.strip()}")
                else:
                    logger.error("Variable format should be name=value")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error occurred while setting variable: {e}")
            return False

    async def get_variable(self, args: str | dict[str, Any]) -> bool:
        """Get variable command"""
        try:
            if isinstance(args, dict):
                name = args.get("name", "")
            else:
                name = str(args)

            if not name:
                logger.error("Variable name not specified")
                return False

            value = self.context.get_variable(name)

            if value is not None:
                logger.info(f"Variable {name} = {value}")
                return True
            else:
                logger.info(f"Variable {name} not set")
                return False

        except Exception as e:
            logger.error(f"Error occurred while getting variable: {e}")
            return False

    async def list_variables(self, args: Any) -> bool:
        """List variables command"""
        try:
            variables = self.context.get_all_variables()

            if not variables:
                logger.info("No variables set")
                return True

            logger.info("Set variables:")
            for name, value in variables.items():
                logger.info(f"  {name} = {value}")

            return True

        except Exception as e:
            logger.error(f"Error occurred while listing variables: {e}")
            return False

    async def export_session(self, args: str | dict[str, Any]) -> bool:
        """Export session command"""
        try:
            if isinstance(args, dict):
                output_file = args.get("file", "")
            else:
                output_file = str(args) if args else ""

            # Expand variables
            if output_file:
                output_file = self.context.expand_variables(output_file)

            exported_file = self.context.export_session_data(output_file)
            logger.info(f"Session data exported to: {exported_file}")

            return True

        except Exception as e:
            logger.error(f"Error occurred while exporting session: {e}")
            return False

    async def import_session(self, args: str | dict[str, Any]) -> bool:
        """Import session command"""
        try:
            if isinstance(args, dict):
                input_file = args.get("file", "")
            else:
                input_file = str(args)

            if not input_file:
                logger.error("Session file not specified")
                return False

            # Expand variables
            input_file = self.context.expand_variables(input_file)

            self.context.import_session_data(input_file)
            logger.info(f"Session data imported from {input_file}")

            return True

        except Exception as e:
            logger.error(f"Error occurred while importing session: {e}")
            return False

    async def help(self, args: Any) -> bool:
        """Help command"""
        try:
            logger.info("=== CLI Command Help ===")
            logger.info("Available commands:")
            logger.info("  configure:<config>          - Configure system settings")
            logger.info("  import_archive:<path>       - Import archive file")
            logger.info("  import_patch:<path>         - Import patch file")
            logger.info("  import_audio:<path>         - Import audio file")
            logger.info("  write_patch:<dir_path>          - Write patch file")
            logger.info("  write_patch:{'output_dir': '<path>', 'output_filename': '<filename>'} - Write patch file to specified directory and filename")
            logger.info("  dump_audio:<dir>            - Export audio files")
            logger.info("  list_archives               - List loaded archives")
            logger.info("  list_audio                  - List audio sources")
            logger.info("  status                      - Show system status")
            logger.info("  revert_all                  - Revert all changes")
            logger.info("  clear_mod                   - Clear current Mod")
            logger.info("  set_variable:<name=value>   - Set variable")
            logger.info("  get_variable:<name>         - Get variable")
            logger.info("  list_variables              - List all variables")
            logger.info("  export_session:<file>       - Export session data")
            logger.info("  import_session:<file>       - Import session data")
            logger.info("  help                        - Show this help")

            logger.info("\n=== Config Example ===")
            logger.info('  configure:{"game_data_path":"./game","theme":"dark"}')
            logger.info("  configure:game_data_path=./game")

            logger.info("\n=== Variable Usage ===")
            logger.info("  Use {variable_name} in command arguments to reference variables")
            logger.info("  Example: import_archive:{game_data_path}/base.patch_0")

            return True

        except Exception as e:
            logger.error(f"Error occurred while showing help: {e}")
            return False

    def get_available_commands(self) -> list[str]:
        """Get available command list"""
        return list(self.commands.keys())

    def get_command_description(self, command: str) -> str:
        """Get command description"""
        descriptions = {
            "configure": "Configure system settings",
            "import_archive": "Import archive file",
            "import_patch": "Import patch file",
            "import_audio": "Import audio file",
            "write_patch": "Write patch file",
            "dump_audio": "Export audio files",
            "list_archives": "List loaded archives",
            "list_audio": "List audio sources",
            "status": "Show system status",
            "revert_all": "Revert all changes",
            "clear_mod": "Clear current Mod",
            "set_variable": "Set variable",
            "get_variable": "Get variable",
            "list_variables": "List all variables",
            "export_session": "Export session data",
            "import_session": "Import session data",
            "help": "Show help information",
        }
        return descriptions.get(command, "Unknown command")
