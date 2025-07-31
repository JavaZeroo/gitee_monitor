"""
异步PR 监控服务模块，处理 PR 标签的并发监控和通知
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from ..api.async_gitee_api import AsyncGiteeAPIClient
from ..config.config_manager import Config

logger = logging.getLogger(__name__)


class AsyncPRCache:
    """异步PR 数据缓存，避免频繁 API 调用"""
    
    def __init__(self, ttl: int = 300):
        """
        初始化缓存
        
        Args:
            ttl: 缓存生存时间（秒）
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl
        self._lock = asyncio.Lock()
    
    async def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的 PR 数据
        
        Args:
            cache_key: 缓存键，格式为 "owner/repo#pr_id"
            
        Returns:
            缓存的 PR 数据，如果缓存不存在或已过期则返回 None
        """
        async with self._lock:
            if cache_key in self.cache:
                entry = self.cache[cache_key]
                if datetime.now() < entry["expires"]:
                    return entry["data"]
                else:
                    # 清除过期缓存
                    del self.cache[cache_key]
            return None
    
    async def set(self, cache_key: str, data: Dict[str, Any]) -> None:
        """
        设置 PR 数据缓存
        
        Args:
            cache_key: 缓存键，格式为 "owner/repo#pr_id"
            data: PR 数据
        """
        async with self._lock:
            self.cache[cache_key] = {
                "data": data,
                "expires": datetime.now() + timedelta(seconds=self.ttl)
            }
    
    async def invalidate(self, cache_key: str) -> None:
        """
        使指定 PR 的缓存失效
        
        Args:
            cache_key: 缓存键，格式为 "owner/repo#pr_id"
        """
        async with self._lock:
            if cache_key in self.cache:
                del self.cache[cache_key]

    async def clear_expired(self) -> None:
        """清除所有过期的缓存条目"""
        async with self._lock:
            now = datetime.now()
            expired_keys = [
                key for key, entry in self.cache.items() 
                if now >= entry["expires"]
            ]
            for key in expired_keys:
                del self.cache[key]
            if expired_keys:
                logger.debug(f"清除了 {len(expired_keys)} 个过期缓存条目")


class AsyncPRMonitor:
    """
    异步PR监控器，使用异步编程提升性能
    """
    
    def __init__(self, config: Config):
        """
        初始化异步PR监控器
        
        Args:
            config: 配置对象
        """
        self.config = config
        self.cache = AsyncPRCache(ttl=config.get('cache_ttl', 300))
        self.api_url = config.get('api_url', 'https://gitee.com/api/v5')
        self.access_token = config.get('access_token', '')
        
        # 并发控制
        self.max_concurrent_requests = config.get('max_concurrent_requests', 10)
        self.semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        
        # 速率限制
        self.requests_per_second = config.get('requests_per_second', 5.0)
        self.min_request_interval = 1.0 / self.requests_per_second
        self.last_request_time = 0.0
        self._rate_limit_lock = asyncio.Lock()
    
    async def _rate_limit(self):
        """异步速率限制"""
        async with self._rate_limit_lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            if time_since_last < self.min_request_interval:
                sleep_time = self.min_request_interval - time_since_last
                await asyncio.sleep(sleep_time)
            self.last_request_time = time.time()
    
    async def get_pr_info_async(self, owner: str, repo: str, pr_id: int) -> Optional[Dict[str, Any]]:
        """
        异步获取PR信息（带缓存和速率限制）
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            PR信息字典，包含 pr_details 字段
        """
        cache_key = f"{owner}/{repo}#{pr_id}"
        
        # 先尝试从缓存获取
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            logger.debug(f"从缓存获取 PR #{pr_id} 信息")
            return cached_data
        
        # 使用信号量控制并发数
        async with self.semaphore:
            # 应用速率限制
            await self._rate_limit()
            
            # 创建异步API客户端
            async with AsyncGiteeAPIClient(self.api_url, self.access_token) as client:
                pr_details = await client.get_pr_details(owner, repo, pr_id)
                
                if pr_details:
                    # 构建返回数据（与同步版本保持一致）
                    pr_info = {
                        "pr_details": pr_details,
                        "last_updated": datetime.now().isoformat()
                    }
                    
                    # 缓存结果
                    await self.cache.set(cache_key, pr_info)
                    logger.debug(f"异步获取并缓存 PR #{pr_id} 信息成功")
                    return pr_info
                else:
                    logger.warning(f"异步获取 PR #{pr_id} 信息失败")
                    return None
    
    async def get_multiple_pr_info_async(self, pr_list: List[Dict[str, Any]]) -> List[Optional[Dict[str, Any]]]:
        """
        并发获取多个PR的信息
        
        Args:
            pr_list: PR列表，每个元素包含 owner, repo, pr_id
            
        Returns:
            PR信息列表，与输入顺序对应
        """
        start_time = time.time()
        
        # 创建并发任务
        tasks = []
        for pr_item in pr_list:
            task = self.get_pr_info_async(
                pr_item['owner'], 
                pr_item['repo'], 
                pr_item['pr_id']
            )
            tasks.append(task)
        
        # 并发执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"获取 PR 信息时出现异常: {result}")
                processed_results.append(None)
            else:
                processed_results.append(result)
        
        end_time = time.time()
        elapsed = end_time - start_time
        success_count = sum(1 for r in processed_results if r is not None)
        
        logger.info(f"并发获取 {len(pr_list)} 个PR信息完成: {success_count} 成功, 耗时 {elapsed:.2f}s")
        
        return processed_results
    
    async def get_author_prs_async(self, owner: str, repo: str, author: str) -> List[Dict[str, Any]]:
        """
        异步获取指定作者的所有PR信息
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            author: 作者用户名
            
        Returns:
            PR信息列表
        """
        async with self.semaphore:
            await self._rate_limit()
            
            async with AsyncGiteeAPIClient(self.api_url, self.access_token) as client:
                prs = await client.get_author_prs(owner, repo, author)
                
                if not prs:
                    return []
                
                # 准备PR信息列表
                pr_list = [
                    {"owner": owner, "repo": repo, "pr_id": pr.get('number')}
                    for pr in prs if pr.get('number')
                ]
                
                # 并发获取所有PR的详细信息
                pr_info_list = await self.get_multiple_pr_info_async(pr_list)
                
                # 过滤掉失败的请求
                valid_pr_info = [info for info in pr_info_list if info is not None]
                
                logger.info(f"异步获取作者 {author} 的 {len(valid_pr_info)} 个PR信息完成")
                return valid_pr_info
    
    async def refresh_cache_async(self) -> None:
        """异步刷新缓存，清除过期条目"""
        await self.cache.clear_expired()
        logger.debug("异步缓存刷新完成")
    
    async def add_pr_labels_async(self, owner: str, repo: str, pr_id: int, labels: List[str]) -> bool:
        """
        异步为PR添加标签
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            labels: 要添加的标签列表
            
        Returns:
            是否成功
        """
        async with self.semaphore:
            await self._rate_limit()
            
            async with AsyncGiteeAPIClient(self.api_url, self.access_token) as client:
                result = await client.add_pr_labels(owner, repo, pr_id, labels)
                success = result is not None
                
                if success:
                    # 使缓存失效以强制刷新
                    cache_key = f"{owner}/{repo}#{pr_id}"
                    await self.cache.invalidate(cache_key)
                
                return success
    
    async def remove_pr_label_async(self, owner: str, repo: str, pr_id: int, label: str) -> bool:
        """
        异步移除PR标签
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            label: 要移除的标签
            
        Returns:
            是否成功
        """
        async with self.semaphore:
            await self._rate_limit()
            
            async with AsyncGiteeAPIClient(self.api_url, self.access_token) as client:
                success = await client.remove_pr_label(owner, repo, pr_id, label)
                
                if success:
                    # 使缓存失效以强制刷新
                    cache_key = f"{owner}/{repo}#{pr_id}"
                    await self.cache.invalidate(cache_key)
                
                return success
