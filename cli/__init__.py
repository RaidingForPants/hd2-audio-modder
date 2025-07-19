"""
CLI Main Module - Implements workflow mode audio modder
Supports command line argument parsing and workflow mode execution
"""

import argparse
import json
import os
import asyncio
from typing import Any

# Delayed import to avoid circular import
from log import logger


class CLIMain:
    """CLI Main Controller"""

    def __init__(self):
        self.cli_core = None
        self.context = None
        self.commands = None

    def _lazy_init(self):
        """Delayed initialization to avoid circular import"""
        if self.cli_core is None:
            from .core import CLICore
            from .context import CLIContext
            from .commands import CLICommands

            self.cli_core = CLICore()
            self.context = CLIContext()
            self.commands = CLICommands(self.cli_core, self.context)

    def parse_arguments(self) -> argparse.Namespace:
        """Parse command line arguments"""
        parser = argparse.ArgumentParser(
            description="Audio Modder - CLI Mode",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Example usage:
  # Workflow mode - from file
  python audio_modder.py workflow example_workflow.json
  
  # Workflow mode - inline JSON
  python audio_modder.py workflow --inline '{"steps":[{"command":"configure","args":{"game_data_path":"./game"}}]}'
  
  # Interactive mode
  python audio_modder.py interactive
            """,
        )

        subparsers = parser.add_subparsers(dest="mode", help="Run mode")

        # Workflow mode
        workflow_parser = subparsers.add_parser("workflow", help="Workflow mode execution")
        workflow_group = workflow_parser.add_mutually_exclusive_group(required=True)
        workflow_group.add_argument("workflow_file", nargs="?", help="Workflow config file path")
        workflow_group.add_argument("--inline", help="Inline workflow JSON string")
        workflow_parser.add_argument(
            "--verbose", "-v", action="store_true", help="Verbose output"
        )
        workflow_parser.add_argument(
            "--dry-run", action="store_true", help="Show steps to be executed only, do not actually execute"
        )
        workflow_parser.add_argument(
            "--set", action="append", help="Set variable (key=value)"
        )

        # Interactive mode
        interactive_parser = subparsers.add_parser("interactive", help="Interactive mode")
        interactive_parser.add_argument(
            "--verbose", "-v", action="store_true", help="Verbose output"
        )

        # Help and version
        parser.add_argument(
            "--version", action="version", version="HD2 Audio Modder CLI v1.0.0"
        )

        return parser.parse_args()

    def parse_workflow_file(self, workflow_file: str) -> dict[str, Any]:
        """Parse workflow file"""
        if not os.path.exists(workflow_file):
            raise FileNotFoundError(f"Workflow file not found: {workflow_file}")

        with open(workflow_file, "r", encoding="utf-8") as f:
            workflow = json.load(f)

        return workflow

    def parse_inline_workflow(self, inline_json: str) -> dict[str, Any]:
        """Parse inline workflow JSON"""
        try:
            workflow = json.loads(inline_json)
            return workflow
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")

    def replace_variables(self, value: Any, context_vars: dict[str, Any]) -> Any:
        """Replace variable placeholders"""
        if isinstance(value, str):
            # Replace {variable} format variables
            for var_name, var_value in context_vars.items():
                placeholder = f"{{{var_name}}}"
                if placeholder in value:
                    value = value.replace(placeholder, str(var_value))
            return value
        elif isinstance(value, dict):
            return {k: self.replace_variables(v, context_vars) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.replace_variables(item, context_vars) for item in value]
        else:
            return value

    def evaluate_condition(self, condition: str, context_vars: dict[str, Any]) -> bool:
        """Evaluate condition expression"""
        if not condition:
            return True

        try:
            # Replace variables
            for var_name, var_value in context_vars.items():
                condition = condition.replace(f"{{{var_name}}}", repr(var_value))

            # Safely evaluate condition
            allowed_names = {
                'os': os,
                'path': os.path,
                'exists': os.path.exists,
                'isfile': os.path.isfile,
                'isdir': os.path.isdir,
                'True': True,
                'False': False,
                'None': None
            }
            
            # Use eval but restrict available names
            result = eval(condition, {"__builtins__": {}}, allowed_names)
            return bool(result)
        except Exception as e:
            logger.warning(f"Condition evaluation failed '{condition}': {e}")
            return False

    async def execute_workflow(self, workflow: dict[str, Any], dry_run: bool = False, set_vars: list[str] | None = None) -> bool:
        """Execute workflow"""
        self._lazy_init()

        # Get workflow info
        description = workflow.get("description", "Unnamed workflow")
        context_vars = workflow.get("context", {})
        steps = workflow.get("steps", [])

        logger.info(f"Starting workflow: {description}")
        logger.info(f"Total {len(steps)} steps")

        # Handle variables set by command line
        if set_vars:
            for var_str in set_vars:
                if "=" in var_str:
                    key, value = var_str.split("=", 1)
                    context_vars[key.strip()] = value.strip()

        if dry_run:
            logger.info("Dry-run mode, showing steps to be executed:")
            for i, step in enumerate(steps):
                name = step.get("name", f"Step {i+1}")
                command = step.get("command", "Unknown command")
                args = step.get("args", {})
                condition = step.get("condition", "")
                
                logger.info(f"  {i + 1}. {name} ({command})")
                logger.info(f"      Args: {args}")
                if condition:
                    logger.info(f"      Condition: {condition}")
            return True

        # Initialize CLI core
        try:
            if self.cli_core is None:
                raise RuntimeError("CLI core not initialized")
            await self.cli_core.initialize()
        except Exception as e:
            logger.error(f"Failed to initialize CLI core: {e}")
            return False

        # Execute steps
        for i, step in enumerate(steps):
            name = step.get("name", f"Step {i+1}")
            command = step.get("command", "")
            args = step.get("args", {})
            condition = step.get("condition", "")
            on_error = step.get("on_error", "stop")
            description = step.get("description", "")

            logger.info(f"Executing step {i + 1}/{len(steps)}: {name}")
            if description:
                logger.info(f"  Description: {description}")

            # Check condition
            if condition:
                if not self.evaluate_condition(condition, context_vars):
                    logger.info(f"  Condition not met, skipping step: {condition}")
                    continue

            # Replace variables
            args = self.replace_variables(args, context_vars)

            try:
                if self.commands is None:
                    raise RuntimeError("CLI commands not initialized")
                success = await self.commands.execute_command(command, args)
                if not success:
                    logger.error(f"Step {i + 1} failed")
                    if on_error == "stop":
                        if self.cli_core is not None:
                            await self.cli_core.cleanup()
                        return False
                    elif on_error == "continue":
                        logger.warning("Continuing to next step")
                        continue
                else:
                    logger.info(f"Step {i + 1} succeeded")
            except Exception as e:
                logger.error(f"Error executing step {i + 1}: {e}")
                if on_error == "stop":
                    if self.cli_core is not None:
                        await self.cli_core.cleanup()
                    return False
                elif on_error == "continue":
                    logger.warning("Continuing to next step")
                    continue

        # Cleanup resources
        if self.cli_core is not None:
            await self.cli_core.cleanup()
        logger.info("Workflow execution completed")
        return True

    async def interactive_mode(self) -> bool:
        """Interactive mode"""
        self._lazy_init()

        logger.info("Entering interactive mode")

        try:
            if self.cli_core is None:
                raise RuntimeError("CLI core not initialized")
            await self.cli_core.initialize()
        except Exception as e:
            logger.error(f"Failed to initialize CLI core: {e}")
            return False

        print("=== HD2 Audio Modder CLI Interactive Mode ===")
        print("Type 'help' to see available commands")
        print("Type 'exit' or 'quit' to exit")
        print()

        while True:
            try:
                command_input = input("audio_modder> ").strip()

                if not command_input:
                    continue

                if command_input.lower() in ["exit", "quit"]:
                    break

                if command_input.lower() == "help":
                    self._show_help()
                    continue

                # Parse command - support JSON format and simple format
                try:
                    if command_input.startswith("{") and command_input.endswith("}"):
                        # JSON format
                        command_data = json.loads(command_input)
                        command = command_data.get("command", "")
                        args = command_data.get("args", {})
                    elif ":" in command_input:
                        # Simple format: command:arg
                        command, arg = command_input.split(":", 1)
                        args = arg.strip()
                    else:
                        # Command without arguments
                        command = command_input
                        args = {}

                    if self.commands is None:
                        raise RuntimeError("CLI commands not initialized")
                    success = await self.commands.execute_command(command, args)
                    if success:
                        print("✓ Command executed successfully")
                    else:
                        print("✗ Command execution failed")
                except json.JSONDecodeError:
                    print("✗ Invalid JSON format")
                except Exception as e:
                    print(f"✗ Error: {e}")

            except KeyboardInterrupt:
                print("\nInterrupt signal, exiting interactive mode")
                break
            except Exception as e:
                print(f"✗ Error: {e}")

        if self.cli_core is not None:
            await self.cli_core.cleanup()
        logger.info("Exiting interactive mode")
        return True

    def _show_help(self):
        """Show help information"""
        print("""
Available command formats:

1. JSON format (recommended):
   {"command": "configure", "args": {"game_data_path": "./game"}}
   {"command": "import_archive", "args": {"path": "./base.patch_0"}}

2. Simple format:
   configure:{"game_data_path":"./game"}
   import_archive:./base.patch_0

3. Command without arguments:
   status
   list_archives
   list_audio

Available commands:
  configure                   - Configure settings
  import_archive              - Import archive file
  import_patch                - Import patch file
  import_audio                - Import audio file
  write_patch                 - Write patch file
  list_archives               - List loaded archives
  list_audio                  - List audio sources
  status                      - Show status information
  set_variable                - Set variable
  get_variable                - Get variable
  list_variables              - List all variables
  export_session              - Export session
  import_session              - Import session
  help                        - Show this help
  exit/quit                   - Exit interactive mode

Examples:
  {"command": "configure", "args": {"game_data_path": "./game"}}
  {"command": "import_archive", "args": {"path": "./base.patch_0"}}
  {"command": "import_audio", "args": {"file_path": "./custom.wav"}}
  {"command": "write_patch", "args": {"path": "./output.patch_0"}}
        """)


def main() -> int:
    """Main function"""
    cli = CLIMain()

    try:
        args = cli.parse_arguments()

        if args.verbose:
            from log import enable_verbose_mode, set_log_level
            import logging
            enable_verbose_mode()
            set_log_level(logging.DEBUG)

        if args.mode == "workflow":
            # Parse workflow
            if args.inline:
                workflow = cli.parse_inline_workflow(args.inline)
            else:
                workflow = cli.parse_workflow_file(args.workflow_file)

            success = asyncio.run(cli.execute_workflow(workflow, args.dry_run, args.set))
        elif args.mode == "interactive":
            success = asyncio.run(cli.interactive_mode())
        else:
            print("Error: Please specify run mode (workflow, interactive)")
            return 1

        return 0 if success else 1

    except KeyboardInterrupt:
        logger.info("User interrupted")
        return 1
    except Exception as e:
        logger.error(f"CLI execution error: {e}")
        return 1
