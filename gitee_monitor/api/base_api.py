"""
抽象API客户端基类，定义标准的API接口
支持多平台扩展（Gitee、GitHub等）
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseAPIClient(ABC):
    """
    抽象API客户端基类
    定义标准的API接口，支持多平台扩展
    """
    
    def __init__(self, api_url: str, access_token: str):
        """
        初始化API客户端
        
        Args:
            api_url: API基础URL
            access_token: 访问令牌
        """
        self.api_url = api_url
        self.access_token = access_token
        self.headers = self._build_headers()
    
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
    def get_pr_labels(self, owner: str, repo: str, pr_id: int) -> Optional[List[Dict[str, Any]]]:
        """
        获取指定PR的标签列表
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            标签列表，出错时返回None
        """
        pass
    
    @abstractmethod
    def get_pr_details(self, owner: str, repo: str, pr_id: int) -> Optional[Dict[str, Any]]:
        """
        获取指定PR的详细信息
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            PR详细信息，出错时返回None
        """
        pass
    
    @abstractmethod
    def get_author_prs(self, owner: str, repo: str, author: str, 
                      state: str = "open", page: int = 1, per_page: int = 20) -> Optional[List[Dict[str, Any]]]:
        """
        获取指定作者在特定仓库的PR列表
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            author: PR创建者用户名
            state: PR状态，可选值为 open, closed, all
            page: 页码
            per_page: 每页数量
            
        Returns:
            PR列表，出错时返回None
        """
        pass
    
    def get_platform_name(self) -> str:
        """
        获取平台名称
        
        Returns:
            平台名称（如 'gitee', 'github'）
        """
        return self.__class__.__name__.lower().replace('apiclient', '')
    
    def validate_config(self) -> bool:
        """
        验证配置是否有效
        
        Returns:
            配置是否有效
        """
        return bool(self.api_url and self.access_token)
