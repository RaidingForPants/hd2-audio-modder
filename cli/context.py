"""
CLI Context Manager - Manages CLI session state and variables
Provides variable management, state tracking, and session history functionality
"""

import os
import time
import json
from typing import Any
from datetime import datetime, timedelta
from log import logger


class CLIContext:
    """CLI Context Manager"""

    def __init__(self):
        self.variables: dict[str, Any] = {}
        self.session_history: list[dict[str, Any]] = []
        self.session_start_time: float = time.time()
        self.session_id: str = f"cli_{int(self.session_start_time)}"
        self.current_directory: str = os.getcwd()
        self.temporary_files: list[str] = []
        self.error_count: int = 0
        self.success_count: int = 0

        # Initialize default variables
        self._initialize_default_variables()

    def _initialize_default_variables(self):
        """Initialize default variables"""
        self.variables.update(
            {
                "session_id": self.session_id,
                "session_start_time": self.session_start_time,
                "current_directory": self.current_directory,
                "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S"),
            }
        )

    def set_variable(self, name: str, value: Any):
        """Set variable"""
        old_value = self.variables.get(name)
        self.variables[name] = value

        logger.debug(f"Set variable: {name} = {value} (original value: {old_value})")

        # Record variable change history
        self.session_history.append(
            {
                "timestamp": time.time(),
                "action": "set_variable",
                "name": name,
                "value": value,
                "old_value": old_value,
            }
        )

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get variable"""
        return self.variables.get(name, default)

    def get_all_variables(self) -> dict[str, Any]:
        """Get all variables"""
        return self.variables.copy()

    def update_variables(self, variables: dict[str, Any]):
        """Batch update variables"""
        for name, value in variables.items():
            self.set_variable(name, value)

    def delete_variable(self, name: str) -> bool:
        """Delete variable"""
        if name in self.variables:
            old_value = self.variables.pop(name)
            logger.debug(f"Deleted variable: {name} (original value: {old_value})")

            # Record variable deletion history
            self.session_history.append(
                {
                    "timestamp": time.time(),
                    "action": "delete_variable",
                    "name": name,
                    "old_value": old_value,
                }
            )
            return True
        return False

    def update_context(self, context: dict[str, Any]):
        """Update context"""
        logger.info(f"Update context: {context}")
        self.update_variables(context)

    def expand_variables(self, text: str) -> str:
        """Expand variable references in text

        Supported formats:
        - {variable_name} - Simple variable replacement
        - $(command) - Command replacement (not supported yet)
        """
        result = text

        # Replace {variable_name} format variables
        for name, value in self.variables.items():
            placeholder = f"{{{name}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))

        return result

    def add_temporary_file(self, file_path: str):
        """Add temporary file path"""
        if file_path not in self.temporary_files:
            self.temporary_files.append(file_path)
            logger.debug(f"Added temporary file: {file_path}")

    def cleanup_temporary_files(self):
        """Clean up temporary files"""
        cleaned_count = 0
        for file_path in self.temporary_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    cleaned_count += 1
                    logger.debug(f"Cleaned up temporary file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {file_path}: {e}")

        self.temporary_files.clear()
        logger.info(f"Cleanup completed, cleaned {cleaned_count} temporary files")

    def record_command_execution(
        self, command: str, args: Any, success: bool, message: str = ""
    ):
        """Record command execution"""
        record = {
            "timestamp": time.time(),
            "action": "command_execution",
            "command": command,
            "args": args,
            "success": success,
            "message": message,
        }

        self.session_history.append(record)

        if success:
            self.success_count += 1
        else:
            self.error_count += 1

        logger.debug(f"Recorded command execution: {command} -> {'Success' if success else 'Failed'}")

    def get_session_summary(self) -> dict[str, Any]:
        """Get session summary"""
        current_time = time.time()
        session_duration = current_time - self.session_start_time

        command_history = [
            record
            for record in self.session_history
            if record.get("action") == "command_execution"
        ]

        return {
            "session_id": self.session_id,
            "session_duration": session_duration,
            "session_duration_formatted": str(timedelta(seconds=int(session_duration))),
            "start_time": datetime.fromtimestamp(self.session_start_time).isoformat(),
            "current_time": datetime.fromtimestamp(current_time).isoformat(),
            "total_commands": len(command_history),
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": (self.success_count / max(1, len(command_history))) * 100,
            "total_variables": len(self.variables),
            "temporary_files": len(self.temporary_files),
        }

    def get_command_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get command history"""
        command_history = [
            record
            for record in self.session_history
            if record.get("action") == "command_execution"
        ]

        # Return recent commands
        return command_history[-limit:] if limit > 0 else command_history

    def get_variable_history(
        self, variable_name: str | None = None
    ) -> list[dict[str, Any]]:
        """Get variable change history"""
        variable_history = [
            record
            for record in self.session_history
            if record.get("action") in ["set_variable", "delete_variable"]
        ]

        if variable_name is not None:
            variable_history = [
                record
                for record in variable_history
                if record.get("name") == variable_name
            ]

        return variable_history

    def export_session_data(self, output_file: str | None = None) -> str:
        """Export session data"""
        if not output_file:
            output_file = f"session_{self.session_id}.json"

        session_data = {
            "session_info": self.get_session_summary(),
            "variables": self.get_all_variables(),
            "command_history": self.get_command_history(),
            "variable_history": self.get_variable_history(),
            "temporary_files": self.temporary_files,
        }

        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"Session data exported to: {output_file}")
            return output_file
        except Exception as e:
            logger.error(f"Failed to export session data: {e}")
            raise

    def import_session_data(self, input_file: str):
        """Import session data"""
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Session data file not found: {input_file}")

        try:
            with open(input_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)

            # Import variables
            if "variables" in session_data:
                self.update_variables(session_data["variables"])

            # Import history records
            if "command_history" in session_data:
                self.session_history.extend(session_data["command_history"])

            # Import variable history
            if "variable_history" in session_data:
                self.session_history.extend(session_data["variable_history"])

            logger.info(f"Session data imported from {input_file}")

        except Exception as e:
            logger.error(f"Failed to import session data: {e}")
            raise

    def clear_history(self):
        """Clear history records"""
        self.session_history.clear()
        self.success_count = 0
        self.error_count = 0
        logger.info("History records cleared")

    def reset_session(self):
        """Reset session"""
        self.variables.clear()
        self.clear_history()
        self.cleanup_temporary_files()
        self.session_start_time = time.time()
        self.session_id = f"cli_{int(self.session_start_time)}"
        self._initialize_default_variables()
        logger.info(f"Session reset, new session ID: {self.session_id}")

    def get_context_info(self) -> dict[str, Any]:
        """Get context information"""
        return {
            "session_id": self.session_id,
            "current_directory": self.current_directory,
            "variables_count": len(self.variables),
            "temporary_files_count": len(self.temporary_files),
            "session_duration": time.time() - self.session_start_time,
            "command_count": len(
                [
                    r
                    for r in self.session_history
                    if r.get("action") == "command_execution"
                ]
            ),
            "success_count": self.success_count,
            "error_count": self.error_count,
        }

    def __str__(self) -> str:
        """String representation"""
        summary = self.get_session_summary()
        return f"CLIContext(session_id={self.session_id}, duration={summary['session_duration_formatted']}, commands={summary['total_commands']}, success_rate={summary['success_rate']:.1f}%)"

    def __repr__(self) -> str:
        return self.__str__()
