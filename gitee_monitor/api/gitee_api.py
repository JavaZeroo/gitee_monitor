"""
Gitee API 客户端模块，处理与 Gitee API 的所有交互
"""
import logging
from typing import List, Dict, Any, Optional
import aiohttp

from .base_api import BaseAPIClient
from .api_client_factory import APIClientFactory

logger = logging.getLogger(__name__)

class GiteeAPIClient(BaseAPIClient):
    """Gitee API 客户端，处理与 Gitee API 的所有交互"""
    
    def _build_headers(self) -> Dict[str, str]:
        """
        构建Gitee API请求头
        
        Returns:
            请求头字典
        """
        return {"Authorization": f"token {self.access_token}"} if self.access_token else {}
        

    async def get_pr_labels(self, owner: str, repo: str, pr_id: int) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_id}/labels"
        result = await self._make_request("GET", url)
        if result is not None:
            logger.debug(f"异步获取 PR #{pr_id} 标签成功: {[l.get('name','') for l in result]}")
        return result

    async def get_pr_details(self, owner: str, repo: str, pr_id: int) -> Optional[Dict[str, Any]]:
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_id}"
        result = await self._make_request("GET", url)
        if result is not None:
            logger.debug(f"异步获取 PR #{pr_id} 详情成功: {result.get('title','')}")
        return result

    async def get_author_prs(self, owner: str, repo: str, author: str) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls"
        params = {
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": 100
        }
        result = await self._make_request("GET", url, params=params)
        if result is not None:
            author_prs = [pr for pr in result if pr.get('user', {}).get('login') == author]
            logger.debug(f"异步获取作者 {author} 的PR成功: {len(author_prs)} 个PR")
            return author_prs
        return None

    async def add_pr_labels(self, owner: str, repo: str, pr_id: int, labels: List[str]) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_id}/labels"
        data = {"labels": labels}
        result = await self._make_request("POST", url, json=data)
        if result is not None:
            logger.info(f"异步为 PR #{pr_id} 添加标签成功: {labels}")
        return result

    async def remove_pr_label(self, owner: str, repo: str, pr_id: int, label: str) -> bool:
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_id}/labels/{label}"
        result = await self._make_request("DELETE", url)
        success = result is not None
        if success:
            logger.info(f"异步移除 PR #{pr_id} 标签成功: {label}")
        return success


# 注册GiteeAPIClient到工厂
APIClientFactory.register_client("gitee", GiteeAPIClient)
