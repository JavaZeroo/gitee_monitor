"""
异步Gitee API 客户端模块，处理与 Gitee API 的所有异步交互
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

from .async_base_api import AsyncBaseAPIClient
from .async_api_client_factory import AsyncAPIClientFactory

logger = logging.getLogger(__name__)


class AsyncGiteeAPIClient(AsyncBaseAPIClient):
    """异步Gitee API 客户端，处理与 Gitee API 的所有交互"""
    
    def _build_headers(self) -> Dict[str, str]:
        """
        构建Gitee API请求头
        
        Returns:
            请求头字典
        """
        return {"Authorization": f"token {self.access_token}"} if self.access_token else {}
        
    async def get_pr_labels(self, owner: str, repo: str, pr_id: int) -> Optional[List[Dict[str, Any]]]:
        """
        异步获取指定 PR 的标签列表
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            标签列表，出错时返回 None
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_id}/labels"
        try:
            result = await self._make_request("GET", url)
            if result is not None:
                logger.debug(f"异步获取 PR #{pr_id} 标签成功: {[label.get('name', '') for label in result]}")
            return result
        except Exception as e:
            logger.error(f"异步获取 PR #{pr_id} 标签失败: {e}")
            return None
    
    async def get_pr_details(self, owner: str, repo: str, pr_id: int) -> Optional[Dict[str, Any]]:
        """
        异步获取指定 PR 的详细信息
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            PR详细信息，出错时返回 None
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_id}"
        try:
            result = await self._make_request("GET", url)
            if result is not None:
                logger.debug(f"异步获取 PR #{pr_id} 详情成功: {result.get('title', '')}")
            return result
        except Exception as e:
            logger.error(f"异步获取 PR #{pr_id} 详情失败: {e}")
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
        """
        异步获取指定作者在指定仓库的所有PR
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            author: 作者用户名
            state: PR 状态，可选 open/closed/all
            page: 页码
            per_page: 每页数量
            
        Returns:
            PR列表，出错时返回 None
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls"
        params = {
            "state": state,
            "sort": "created",
            "direction": "desc",
            "page": page,
            "per_page": per_page,
            "author": author,
        }

        if self.access_token:
            params["access_token"] = self.access_token
        
        try:
            result = await self._make_request("GET", url, params=params)
            if result is not None:
                logger.debug(
                    f"异步获取作者 {author} 的PR成功: {len(result)} 个"
                )
            return result
        except Exception as e:
            logger.error(f"异步获取作者 {author} 的PR失败: {e}")
            return None
    
    async def add_pr_labels(self, owner: str, repo: str, pr_id: int, labels: List[str]) -> Optional[List[Dict[str, Any]]]:
        """
        异步为PR添加标签
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            labels: 要添加的标签名称列表
            
        Returns:
            更新后的标签列表，出错时返回None
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_id}/labels"
        data = {"labels": labels}
        
        try:
            result = await self._make_request("POST", url, json=data)
            if result is not None:
                logger.info(f"异步为 PR #{pr_id} 添加标签成功: {labels}")
            return result
        except Exception as e:
            logger.error(f"异步为 PR #{pr_id} 添加标签失败: {e}")
            return None
    
    async def remove_pr_label(self, owner: str, repo: str, pr_id: int, label: str) -> bool:
        """
        异步移除PR的标签
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            label: 要移除的标签名称
            
        Returns:
            是否成功移除
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_id}/labels/{label}"
        
        try:
            result = await self._make_request("DELETE", url)
            success = result is not None
            if success:
                logger.info(f"异步移除 PR #{pr_id} 标签成功: {label}")
            return success
        except Exception as e:
            logger.error(f"异步移除 PR #{pr_id} 标签失败: {e}")
            return False

    async def get_multiple_pr_details(self, pr_requests: List[Dict[str, Any]]) -> List[Optional[Dict[str, Any]]]:
        """
        并发获取多个PR的详细信息
        
        Args:
            pr_requests: PR请求列表，每个元素包含 owner, repo, pr_id
            
        Returns:
            PR详细信息列表，与输入顺序对应
        """
        tasks = []
        for pr_request in pr_requests:
            task = self.get_pr_details(
                pr_request['owner'], 
                pr_request['repo'], 
                pr_request['pr_id']
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 将异常转换为None
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"并发获取PR详情时出现异常: {result}")
                processed_results.append(None)
            else:
                processed_results.append(result)

        return processed_results


# 在工厂中注册
AsyncAPIClientFactory.register_client("gitee", AsyncGiteeAPIClient)
