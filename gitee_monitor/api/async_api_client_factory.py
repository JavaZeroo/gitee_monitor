"""
异步API客户端工厂类，管理不同平台的异步API客户端创建
"""
from typing import Dict, Type, Optional
import logging

from .async_base_api import AsyncBaseAPIClient

logger = logging.getLogger(__name__)


class AsyncAPIClientFactory:
    """异步API客户端工厂类"""

    _clients: Dict[str, Type[AsyncBaseAPIClient]] = {}

    @classmethod
    def register_client(cls, platform: str, client_class: Type[AsyncBaseAPIClient]) -> None:
        cls._clients[platform.lower()] = client_class
        logger.info(f"注册异步API客户端: {platform} -> {client_class.__name__}")

    @classmethod
    def create_client(cls, platform: str, api_url: str, access_token: str) -> Optional[AsyncBaseAPIClient]:
        platform_key = platform.lower()
        if platform_key not in cls._clients:
            logger.error(f"不支持的平台: {platform}. 支持的平台: {list(cls._clients.keys())}")
            return None

        client_class = cls._clients[platform_key]
        try:
            client = client_class(api_url, access_token)
            if not client.validate_config():
                logger.error(f"异步API客户端配置无效: {platform}")
                return None
            logger.info(f"成功创建异步API客户端: {platform}")
            return client
        except Exception as e:
            logger.error(f"创建异步API客户端失败 ({platform}): {e}")
            return None

    @classmethod
    def get_supported_platforms(cls) -> list:
        return list(cls._clients.keys())

    @classmethod
    def is_platform_supported(cls, platform: str) -> bool:
        return platform.lower() in cls._clients
