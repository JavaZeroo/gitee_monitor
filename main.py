"""
Gitee PR Monitor 主程序入口
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import threading
import argparse

from gitee_monitor.config.config_manager import Config
from gitee_monitor.api.gitee_api import GiteeAPIClient
from gitee_monitor.services.pr_monitor import PRMonitor
from gitee_monitor.web.webapp import WebApp

# 默认配置文件路径
DEFAULT_CONFIG_FILE = "config.json"

def setup_logging(log_level=logging.INFO):
    """
    设置日志记录
    
    Args:
        log_level: 日志级别
    """
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "gitee_monitor.log")
    
    # 创建处理器
    file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024*10, backupCount=5)
    console_handler = logging.StreamHandler()
    
    # 设置格式
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # 减少第三方库的日志级别
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    
    return root_logger

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='Gitee PR Monitor')
    parser.add_argument('-c', '--config', default=DEFAULT_CONFIG_FILE,
                        help=f'配置文件路径 (默认: {DEFAULT_CONFIG_FILE})')
    parser.add_argument('-p', '--port', type=int, default=5000,
                        help='Web 服务器端口 (默认: 5000)')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='启用调试模式')
    parser.add_argument('-l', '--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        default='INFO', help='日志级别 (默认: INFO)')
    return parser.parse_args()

def main():
    """主程序入口"""
    # 解析命令行参数
    args = parse_args()
    
    # 设置日志
    log_level = getattr(logging, args.log_level)
    logger = setup_logging(log_level)
    logger.info("Gitee PR Monitor 启动中...")
    
    # 初始化配置
    config = Config(args.config)
    
    # 初始化 API 客户端
    api_client = GiteeAPIClient(
        api_url=config.get("GITEA_URL"),
        access_token=config.get("ACCESS_TOKEN")
    )
    
    # 初始化 PR 监控服务
    pr_monitor = PRMonitor(config, api_client)
    
    # 启动 PR 监控服务
    pr_monitor.start()
    
    # 初始化 Web 应用
    webapp = WebApp(config, pr_monitor)
    
    try:
        # 运行 Web 应用
        logger.info(f"Web 服务器启动在 http://0.0.0.0:{args.port}")
        webapp.run(port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        logger.info("收到退出信号，正在关闭...")
    finally:
        # 停止 PR 监控服务
        pr_monitor.stop()
        logger.info("Gitee PR Monitor 已关闭")

if __name__ == "__main__":
    main()
