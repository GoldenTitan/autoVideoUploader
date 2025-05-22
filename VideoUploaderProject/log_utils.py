import os
import logging
from logging.handlers import TimedRotatingFileHandler
from typing import Optional, List, Union

def setup_logger(
    logger_name: str,
    log_dir: str = "logs",
    log_file: str = "app.log",
    log_level: int = logging.INFO,
    log_formats: Optional[List[str]] = None,
    handlers: Optional[List[logging.Handler]] = None
) -> logging.Logger:
    """
    配置日志记录器
    
    参数:
        logger_name: 日志记录器名称
        log_dir: 日志目录路径
        log_file: 日志文件名
        log_level: 日志级别
        log_formats: 日志格式列表(控制台和文件可以不同)
        handlers: 自定义日志处理器列表
    
    返回:
        配置好的日志记录器
    """
    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)
    
    # 默认日志格式
    default_formats = [
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ]
    log_formats = log_formats or default_formats
    
    # 创建 TimedRotatingFileHandler 用于文件日志，每天轮转，保留7天备份
    file_handler = TimedRotatingFileHandler(
        log_path, 
        when="midnight", 
        interval=1, 
        backupCount=7, 
        encoding='utf-8'
    )
    
    # 默认处理器列表修改，使用新的 file_handler
    default_handlers = [
        file_handler,
        logging.StreamHandler()
    ]
    handlers = handlers or default_handlers
    
    # 配置处理器
    for handler, fmt in zip(handlers, log_formats):
        handler.setFormatter(logging.Formatter(fmt))
    
    # 创建并配置日志记录器
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)
    
    # 清除现有处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 添加新处理器
    for handler in handlers:
        logger.addHandler(handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """
    获取已配置的日志记录器
    
    参数:
        name: 日志记录器名称
    
    返回:
        配置好的日志记录器
    """
    return logging.getLogger(name)