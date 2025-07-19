import logging
import os
import sys
from typing import Optional, Dict, Any


class CLIFriendlyFormatter(logging.Formatter):
    """CLI友好的日志格式化器"""
    
    def __init__(self, format_style: str = "cli", include_timestamp: bool = True, include_location: bool = False):
        """
        初始化CLI友好的格式化器
        
        Args:
            format_style: 格式样式 ("cli", "json", "detailed")
            include_timestamp: 是否包含时间戳
            include_location: 是否包含文件位置信息
        """
        self.format_style = format_style
        self.include_timestamp = include_timestamp
        self.include_location = include_location
        
        # 定义不同的格式模板
        self.formats = {
            "cli": self._get_cli_format(),
            "json": self._get_json_format(),
            "detailed": self._get_detailed_format(),
            "minimal": self._get_minimal_format()
        }
        
        super().__init__(self.formats[format_style])
    
    def _get_cli_format(self) -> str:
        """获取CLI友好的格式"""
        parts = []
        
        if self.include_timestamp:
            parts.append("%(asctime)s")
        
        parts.append("[%(levelname)s]")
        
        if self.include_location:
            parts.append("(%(filename)s:%(lineno)d)")
        
        parts.append("%(message)s")
        
        return " ".join(parts)
    
    def _get_json_format(self) -> str:
        """获取JSON格式"""
        return (
            "{time:\"%(asctime)s\","
            "level:\"%(levelname)s\","
            "filename:\"%(filename)s\","
            "function:\"%(funcName)s\"," 
            "lineno:%(lineno)d,"
            "msg:\"%(message)s\"}"
        )
    
    def _get_detailed_format(self) -> str:
        """获取详细格式"""
        return "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(funcName)s() - %(message)s"
    
    def _get_minimal_format(self) -> str:
        """获取最小格式"""
        return "%(levelname)s: %(message)s"
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        # 根据日志级别调整颜色（仅在CLI模式下）
        if self.format_style == "cli" and hasattr(record, 'levelno'):
            record.levelname = self._colorize_level(record.levelname, record.levelno)
        
        return super().format(record)
    
    def _colorize_level(self, level_name: str, level_no: int) -> str:
        """为日志级别添加颜色"""
        if not sys.stdout.isatty():  # 如果不是终端，不添加颜色
            return level_name
        
        colors = {
            logging.DEBUG: "\033[36m",    # 青色
            logging.INFO: "\033[32m",     # 绿色
            logging.WARNING: "\033[33m",  # 黄色
            logging.ERROR: "\033[31m",    # 红色
            logging.CRITICAL: "\033[35m"  # 紫色
        }
        
        reset = "\033[0m"
        color = colors.get(level_no, "")
        
        return f"{color}{level_name}{reset}"


class LoggerManager:
    """日志管理器"""
    
    def __init__(self):
        self.logger: Optional[logging.Logger] = None
        self.handlers: Dict[str, logging.Handler] = {}
        self.config = {
            "format_style": "cli",
            "include_timestamp": True,
            "include_location": False,
            "log_level": logging.INFO,
            "log_file": "log.txt",
            "enable_file_logging": True,
            "enable_console_logging": True
        }
    
    def configure(self, **kwargs) -> None:
        """配置日志设置"""
        self.config.update(kwargs)
        
        # 如果logger已经初始化，重新配置
        if self.logger is not None:
            self._reconfigure_logger()
    
    def _reconfigure_logger(self) -> None:
        """重新配置logger"""
        if self.logger is None:
            return
        
        # 清除现有处理器
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # 重新添加处理器
        self._setup_handlers()
    
    def _setup_handlers(self) -> None:
        """设置日志处理器"""
        if self.logger is None:
            return
        
        # 创建格式化器
        formatter = CLIFriendlyFormatter(
            format_style=self.config["format_style"],
            include_timestamp=self.config["include_timestamp"],
            include_location=self.config["include_location"]
        )
        
        # 文件处理器
        if self.config["enable_file_logging"]:
            file_handler = logging.FileHandler(self.config["log_file"], encoding='utf-8')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            self.handlers["file"] = file_handler
        
        # 控制台处理器
        if self.config["enable_console_logging"]:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            self.handlers["console"] = console_handler
    
    def get_logger(self) -> logging.Logger:
        """获取logger实例"""
        if self.logger is None:
            self.logger = logging.getLogger("hd2_audio_modder")
            self.logger.setLevel(self.config["log_level"])
            self._setup_handlers()
        
        return self.logger
    
    def set_level(self, level: int) -> None:
        """设置日志级别"""
        self.config["log_level"] = level
        if self.logger is not None:
            self.logger.setLevel(level)
    
    def enable_cli_mode(self) -> None:
        """启用CLI模式"""
        self.configure(
            format_style="cli",
            include_timestamp=True,
            include_location=False,
            enable_console_logging=True,
            enable_file_logging=True
        )
    
    def enable_json_mode(self) -> None:
        """启用JSON模式"""
        self.configure(
            format_style="json",
            include_timestamp=True,
            include_location=True,
            enable_console_logging=True,
            enable_file_logging=True
        )
    
    def enable_minimal_mode(self) -> None:
        """启用最小模式"""
        self.configure(
            format_style="minimal",
            include_timestamp=False,
            include_location=False,
            enable_console_logging=True,
            enable_file_logging=False
        )
    
    def enable_verbose_mode(self) -> None:
        """启用详细模式"""
        self.configure(
            format_style="detailed",
            include_timestamp=True,
            include_location=True,
            enable_console_logging=True,
            enable_file_logging=True
        )


# 全局日志管理器实例
_logger_manager = LoggerManager()


def configure_logging(**kwargs) -> None:
    """配置日志设置"""
    _logger_manager.configure(**kwargs)


def get_logger() -> logging.Logger:
    """获取logger实例"""
    return _logger_manager.get_logger()


def set_log_level(level: int) -> None:
    """设置日志级别"""
    _logger_manager.set_level(level)


def enable_cli_mode() -> None:
    """启用CLI模式"""
    _logger_manager.enable_cli_mode()


def enable_json_mode() -> None:
    """启用JSON模式"""
    _logger_manager.enable_json_mode()


def enable_minimal_mode() -> None:
    """启用最小模式"""
    _logger_manager.enable_minimal_mode()


def enable_verbose_mode() -> None:
    """启用详细模式"""
    _logger_manager.enable_verbose_mode()


# 检查环境变量来设置默认模式
def _setup_default_mode():
    """根据环境变量设置默认模式"""
    mode = os.environ.get("HD2_LOG_MODE", "cli").lower()
    
    if mode == "json":
        enable_json_mode()
    elif mode == "minimal":
        enable_minimal_mode()
    elif mode == "verbose":
        enable_verbose_mode()
    else:
        enable_cli_mode()


# 初始化默认模式
_setup_default_mode()

# 导出logger实例
logger = get_logger()
