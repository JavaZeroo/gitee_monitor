"""
异步GitHub API 客户端模块，处理与 GitHub API 的所有交互
"""
import logging
from typing import List, Dict, Any, Optional

from .async_base_api import AsyncBaseAPIClient

logger = logging.getLogger(__name__)


class AsyncGitHubAPIClient(AsyncBaseAPIClient):
    """异步GitHub API 客户端"""

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GiteeMonitor/1.0",
        }
        if self.access_token:
            headers["Authorization"] = f"token {self.access_token}"
        return headers

    async def get_pr_labels(self, owner: str, repo: str, pr_id: int) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{pr_id}/labels"
        try:
            return await self._make_request("GET", url)
        except Exception as e:
            logger.error(f"异步获取 GitHub PR #{pr_id} 标签失败: {e}")
            return None

    async def get_pr_details(self, owner: str, repo: str, pr_id: int) -> Optional[Dict[str, Any]]:
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_id}"
        try:
            return await self._make_request("GET", url)
        except Exception as e:
            logger.error(f"异步获取 GitHub PR #{pr_id} 详情失败: {e}")
            return None

    async def get_author_prs(
        self,
        owner: str,
        repo: str,
        author: str,
        state: str = "open",
        page: int = 1,
        per_page: int = 20,
    ) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls"
        params = {
            "state": state,
            "sort": "created",
            "direction": "desc",
            "page": page,
            "per_page": per_page,
        }
        try:
            prs = await self._make_request("GET", url, params=params)
            if prs is None:
                return None
            if author:
                prs = [pr for pr in prs if pr.get("user", {}).get("login") == author]
            return prs
        except Exception as e:
            logger.error(f"异步获取作者 {author} 在 {owner}/{repo} 的GitHub PR列表失败: {e}")
            return None

from .async_api_client_factory import AsyncAPIClientFactory

AsyncAPIClientFactory.register_client("github", AsyncGitHubAPIClient)

