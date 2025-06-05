"""
Gitee API 客户端模块，处理与 Gitee API 的所有交互
"""
import requests
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class GiteeAPIClient:
    """Gitee API 客户端，处理与 Gitee API 的所有交互"""
    
    def __init__(self, api_url: str, access_token: str):
        """
        初始化 Gitee API 客户端
        
        Args:
            api_url: Gitee API URL
            access_token: Gitee Access Token
        """
        self.api_url = api_url
        self.access_token = access_token
        self.headers = {"Authorization": f"token {access_token}"} if access_token else {}
        
    def get_pr_labels(self, owner: str, repo: str, pr_id: int) -> Optional[List[Dict[str, Any]]]:
        """
        获取指定 PR 的标签列表
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            标签列表，出错时返回 None
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_id}/labels"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            labels = response.json()
            logger.debug(f"获取 PR #{pr_id} 标签成功: {[label.get('name', '') for label in labels]}")
            return labels
        except requests.RequestException as e:
            logger.error(f"获取 PR #{pr_id} 标签失败: {e}")
            return None
    
    def get_pr_details(self, owner: str, repo: str, pr_id: int) -> Optional[Dict[str, Any]]:
        """
        获取指定 PR 的详细信息
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            PR 详细信息，出错时返回 None
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            pr_details = response.json()
            logger.debug(f"获取 PR #{pr_id} 详情成功")
            return pr_details
        except requests.RequestException as e:
            logger.error(f"获取 PR #{pr_id} 详情失败: {e}")
            return None
