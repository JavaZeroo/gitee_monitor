"""
API客户端工厂类，管理不同平台的API客户端创建
"""
from typing import Dict, Type, Optional
import logging

from .base_api import BaseAPIClient

logger = logging.getLogger(__name__)


class APIClientFactory:
    """
    API客户端工厂类
    负责创建和管理不同平台的API客户端
    """
    
    # 注册的API客户端类
    _clients: Dict[str, Type[BaseAPIClient]] = {}
    
    @classmethod
    def register_client(cls, platform: str, client_class: Type[BaseAPIClient]) -> None:
        """
        注册API客户端类
        
        Args:
            platform: 平台名称（如 'gitee', 'github'）
            client_class: API客户端类
        """
        cls._clients[platform.lower()] = client_class
        logger.info(f"注册API客户端: {platform} -> {client_class.__name__}")
    
    @classmethod
    def create_client(cls, platform: str, api_url: str, access_token: str) -> Optional[BaseAPIClient]:
        """
        创建API客户端实例
        
        Args:
            platform: 平台名称（如 'gitee', 'github'）
            api_url: API基础URL
            access_token: 访问令牌
            
        Returns:
            API客户端实例，如果平台不支持则返回None
        """
        platform_key = platform.lower()
        
        if platform_key not in cls._clients:
            logger.error(f"不支持的平台: {platform}. 支持的平台: {list(cls._clients.keys())}")
            return None
        
        client_class = cls._clients[platform_key]
        try:
            client = client_class(api_url, access_token)
            if not client.validate_config():
                logger.error(f"API客户端配置无效: {platform}")
                return None
            
            logger.info(f"成功创建API客户端: {platform}")
            return client
        except Exception as e:
            logger.error(f"创建API客户端失败 ({platform}): {e}")
            return None
    
    @classmethod
    def get_supported_platforms(cls) -> list:
        """
        获取支持的平台列表
        
        Returns:
            支持的平台名称列表
        """
        return list(cls._clients.keys())
    
    @classmethod
    def is_platform_supported(cls, platform: str) -> bool:
        """
        检查平台是否受支持
        
        Args:
            platform: 平台名称
            
        Returns:
            是否支持该平台
        """
        return platform.lower() in cls._clients
