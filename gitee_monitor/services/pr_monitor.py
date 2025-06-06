"""
PR 监控服务模块，处理 PR 标签的监控和通知
"""
import time
import logging
import threading
from typing import Dict, Any, Set, List, Optional
from datetime import datetime, timedelta

from ..api.gitee_api import GiteeAPIClient
from ..config.config_manager import Config

logger = logging.getLogger(__name__)

class PRCache:
    """PR 数据缓存，避免频繁 API 调用"""
    
    def __init__(self, ttl: int = 300):
        """
        初始化缓存
        
        Args:
            ttl: 缓存生存时间（秒）
        """
        self.cache: Dict[str, Dict[str, Any]] = {}  # 使用字符串key支持多仓库
        self.ttl = ttl
    
    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的 PR 数据
        
        Args:
            cache_key: 缓存键，格式为 "owner/repo#pr_id"
            
        Returns:
            缓存的 PR 数据，如果缓存不存在或已过期则返回 None
        """
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if datetime.now() < entry["expires"]:
                return entry["data"]
        return None
    
    def set(self, cache_key: str, data: Dict[str, Any]) -> None:
        """
        设置 PR 数据缓存
        
        Args:
            cache_key: 缓存键，格式为 "owner/repo#pr_id"
            data: PR 数据
        """
        self.cache[cache_key] = {
            "data": data,
            "expires": datetime.now() + timedelta(seconds=self.ttl)
        }
    
    def invalidate(self, cache_key: str) -> None:
        """
        使指定 PR 的缓存失效
        
        Args:
            cache_key: 缓存键，格式为 "owner/repo#pr_id"
        """
        if cache_key in self.cache:
            del self.cache[cache_key]


class PRMonitor:
    """PR 监控服务，监控 PR 标签变化并发送通知"""
    
    def __init__(self, config: Config, api_client: GiteeAPIClient):
        """
        初始化 PR 监控服务
        
        Args:
            config: 配置管理器
            api_client: Gitee API 客户端
        """
        self.config = config
        self.api_client = api_client
        self.cache = PRCache(ttl=self.config.get("CACHE_TTL", 300))
        self.pr_labels: Dict[str, Set[str]] = {}  # 保存每个 PR 的最新标签，key格式为 "owner/repo#pr_id"
        self.running = False
        self.poll_thread = None
        
    def start(self) -> None:
        """启动 PR 监控服务"""
        if self.running:
            logger.warning("PR 监控服务已经在运行")
            return
            
        self.running = True
        self.poll_thread = threading.Thread(target=self._poll_loop)
        self.poll_thread.daemon = True
        self.poll_thread.start()
        logger.info("PR 监控服务已启动")
    
    def stop(self) -> None:
        """停止 PR 监控服务"""
        self.running = False
        if self.poll_thread:
            self.poll_thread.join(timeout=1.0)
        logger.info("PR 监控服务已停止")
    
    def get_pr_details(self, owner: str, repo: str, pr_id: int, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取 PR 的详细信息，优先使用缓存
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            force_refresh: 是否强制刷新缓存
            
        Returns:
            PR 详细信息
        """
        cache_key = f"{owner}/{repo}#{pr_id}_details"
        
        if force_refresh:
            self.cache.invalidate(cache_key)
            
        # 检查缓存
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data
            
        # 缓存不存在，从 API 获取
        access_token = self.config.get("ACCESS_TOKEN")
        
        if not access_token:
            logger.warning("无法获取 PR 详情：ACCESS_TOKEN 未配置")
            return None
            
        pr_details = self.api_client.get_pr_details(owner, repo, pr_id)
        if pr_details:
            self.cache.set(cache_key, pr_details)
            return pr_details
        return None
    
    def get_pr_labels(self, owner: str, repo: str, pr_id: int, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        获取 PR 的标签，优先使用缓存
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            force_refresh: 是否强制刷新缓存
            
        Returns:
            PR 标签列表
        """
        cache_key = f"{owner}/{repo}#{pr_id}"
        
        if force_refresh:
            self.cache.invalidate(cache_key)
            
        # 检查缓存
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data
            
        # 缓存不存在，从 API 获取
        access_token = self.config.get("ACCESS_TOKEN")
        
        if not access_token:
            logger.warning("无法获取 PR 标签：ACCESS_TOKEN 未配置")
            return []
            
        labels = self.api_client.get_pr_labels(owner, repo, pr_id)
        if labels:
            self.cache.set(cache_key, labels)
            return labels
        return []
    
    def get_all_pr_labels(self, force_refresh: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有监控的 PR 的标签
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            PR key 到标签列表的映射，key格式为 "owner/repo#pr_id"
        """
        result = {}
        for pr_config in self.config.get_pr_lists():
            owner = pr_config.get("OWNER")
            repo = pr_config.get("REPO")
            pr_id = pr_config.get("PULL_REQUEST_ID")
            
            if owner and repo and pr_id:
                cache_key = f"{owner}/{repo}#{pr_id}"
                result[cache_key] = self.get_pr_labels(owner, repo, pr_id, force_refresh)
                
        return result
    
    def _poll_loop(self) -> None:
        """轮询 PR 标签的后台线程"""
        while self.running:
            try:
                self._check_all_prs()
                time.sleep(self.config.get("POLL_INTERVAL", 60))
            except Exception as e:
                logger.error(f"轮询 PR 标签时出错: {e}")
                time.sleep(10)  # 出错后短暂休眠，避免频繁错误
    
    def _check_all_prs(self) -> None:
        """检查所有监控的 PR 的标签变化"""
        for pr_config in self.config.get_pr_lists():
            owner = pr_config.get("OWNER")
            repo = pr_config.get("REPO")
            pr_id = pr_config.get("PULL_REQUEST_ID")
            
            if owner and repo and pr_id:
                self._check_pr(owner, repo, pr_id)
    
    def _check_pr(self, owner: str, repo: str, pr_id: int) -> None:
        """
        检查单个 PR 的标签变化
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
        """
        labels = self.get_pr_labels(owner, repo, pr_id, force_refresh=True)
        label_names = {label.get("name", "") for label in labels}
        
        cache_key = f"{owner}/{repo}#{pr_id}"
        
        # 检查标签变化
        if cache_key in self.pr_labels:
            old_labels = self.pr_labels[cache_key]
            if old_labels != label_names:
                added = label_names - old_labels
                removed = old_labels - label_names
                self._notify_label_change(owner, repo, pr_id, added, removed)
        
        # 更新保存的标签
        self.pr_labels[cache_key] = label_names
    
    def _notify_label_change(self, owner: str, repo: str, pr_id: int, added: Set[str], removed: Set[str]) -> None:
        """
        处理标签变化通知
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            added: 新增的标签
            removed: 移除的标签
        """
        if not self.config.get("ENABLE_NOTIFICATIONS", False):
            return
            
        change_str = []
        if added:
            change_str.append(f"添加标签: {', '.join(added)}")
        if removed:
            change_str.append(f"移除标签: {', '.join(removed)}")
            
        message = f"PR #{pr_id} ({owner}/{repo}) 标签变化: {' '.join(change_str)}"
        logger.info(message)
        
        # TODO: 实现实际的通知功能，如邮件、Webhook 等
