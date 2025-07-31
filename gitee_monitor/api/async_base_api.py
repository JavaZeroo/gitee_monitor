"""
异步API客户端基类，定义标准的异步API接口
支持多平台扩展（Gitee、GitHub等）
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging
import aiohttp
import asyncio

logger = logging.getLogger(__name__)


class AsyncBaseAPIClient(ABC):
    """
    异步抽象API客户端基类
    定义标准的异步API接口，支持多平台扩展
    """
    
    def __init__(self, api_url: str, access_token: str):
        """
        初始化异步API客户端
        
        Args:
            api_url: API基础URL
            access_token: 访问令牌
        """
        self.api_url = api_url
        self.access_token = access_token
        self.headers = self._build_headers()
        self.session = None
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    @abstractmethod
    def _build_headers(self) -> Dict[str, str]:
        """
        构建请求头
        不同平台可能有不同的认证方式
        
        Returns:
            请求头字典
        """
        pass
    
    @abstractmethod
    async def get_pr_labels(self, owner: str, repo: str, pr_id: int) -> Optional[List[Dict[str, Any]]]:
        """
        异步获取指定PR的标签列表
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            标签列表，出错时返回None
        """
        pass
    
    @abstractmethod
    async def get_pr_details(self, owner: str, repo: str, pr_id: int) -> Optional[Dict[str, Any]]:
        """
        异步获取指定PR的详细信息
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            PR详细信息，出错时返回None
        """
        pass
    
    @abstractmethod
    async def get_author_prs(self, owner: str, repo: str, author: str) -> Optional[List[Dict[str, Any]]]:
        """
        异步获取指定作者在指定仓库的所有PR
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            author: 作者用户名
            
        Returns:
            PR列表，出错时返回None
        """
        pass
    
    async def add_pr_labels(self, owner: str, repo: str, pr_id: int, labels: List[str]) -> Optional[List[Dict[str, Any]]]:
        """
        异步为PR添加标签（基础实现，子类可以重写）
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            labels: 要添加的标签名称列表
            
        Returns:
            更新后的标签列表，出错时返回None
        """
        logger.warning(f"add_pr_labels not implemented for {self.__class__.__name__}")
        return None
    
    async def remove_pr_label(self, owner: str, repo: str, pr_id: int, label: str) -> bool:
        """
        异步移除PR的标签（基础实现，子类可以重写）
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            label: 要移除的标签名称
            
        Returns:
            是否成功移除
        """
        logger.warning(f"remove_pr_label not implemented for {self.__class__.__name__}")
        return False

    async def _make_request(self, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        异步发起HTTP请求的辅助方法
        
        Args:
            method: HTTP方法
            url: 请求URL
            **kwargs: 额外的请求参数
            
        Returns:
            响应数据，出错时返回None
        """
        if not self.session:
            raise RuntimeError("Session not initialized. Use async context manager.")
            
        try:
            async with self.session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Request failed: {method} {url} - {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {method} {url} - {e}")
            return None
