"""
GitHub API 客户端模块，处理与 GitHub API 的所有交互
"""
import logging
from typing import List, Dict, Any, Optional
import aiohttp

from .base_api import BaseAPIClient
from .api_client_factory import APIClientFactory

logger = logging.getLogger(__name__)

class GitHubAPIClient(BaseAPIClient):
    """GitHub API 客户端，处理与 GitHub API 的所有交互"""
    
    def _build_headers(self) -> Dict[str, str]:
        """
        构建GitHub API请求头
        
        Returns:
            请求头字典
        """
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GiteeMonitor/1.0"
        }
        if self.access_token:
            headers["Authorization"] = f"token {self.access_token}"
        return headers
        
    async def get_pr_labels(self, owner: str, repo: str, pr_id: int) -> Optional[List[Dict[str, Any]]]:
        """
        获取指定 PR 的标签列表
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            标签列表，出错时返回 None
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{pr_id}/labels"
        result = await self._make_request("GET", url)
        if result is not None:
            logger.debug(f"获取 GitHub PR #{pr_id} 标签成功: {[label.get('name', '') for label in result]}")
        return result
    
    async def get_pr_details(self, owner: str, repo: str, pr_id: int) -> Optional[Dict[str, Any]]:
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
        result = await self._make_request("GET", url)
        if result is not None:
            logger.debug(f"获取 GitHub PR #{pr_id} 详情成功")
        return result
            
    async def get_author_prs(self, owner: str, repo: str, author: str, state: str = "open", page: int = 1, per_page: int = 20) -> Optional[List[Dict[str, Any]]]:
        """
        获取指定作者在特定仓库的PR列表
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            author: PR创建者用户名
            state: PR状态，可选值为 open, closed, all，默认为 open
            page: 页码，默认为1
            per_page: 每页数量，默认为20
            
        Returns:
            PR列表，出错时返回 None
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls"
        params = {
            "state": state,
            "sort": "created",
            "direction": "desc",
            "page": page,
            "per_page": per_page
        }
        
        result = await self._make_request("GET", url, params=params)
        if result is not None:
            if author:
                result = [pr for pr in result if pr.get('user', {}).get('login') == author]
            logger.debug(f"获取作者 {author} 在 {owner}/{repo} 的GitHub PR列表成功，共 {len(result)} 个")
            return result
        logger.error(f"获取作者 {author} 在 {owner}/{repo} 的GitHub PR列表失败")
        return None


# 注册GitHubAPIClient到工厂
APIClientFactory.register_client("github", GitHubAPIClient)
