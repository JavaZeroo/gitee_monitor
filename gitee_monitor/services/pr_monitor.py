"""
PR 监控服务模块，处理 PR 标签的监控和通知
"""
import time
import logging
import threading
from typing import Dict, Any, Set, List, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import functools

from ..api.api_client_factory import APIClientFactory
from ..api.base_api import BaseAPIClient
from ..models import PullRequest
from ..config.config_manager import Config
from .automation_engine import AutomationEngine, AutomationConfig
from ..models.automation import TriggerType

# 确保API客户端已注册到工厂
from ..api import gitee_api
from ..api import github_api

logger = logging.getLogger(__name__)


def rate_limit(calls_per_second: float = 2.0):
    """
    速率限制装饰器，用于控制API调用频率
    
    Args:
        calls_per_second: 每秒允许的调用次数
    """
    min_interval = 1.0 / calls_per_second
    
    def decorator(func):
        last_called = [0.0]
        lock = threading.Lock()
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                elapsed = time.time() - last_called[0]
                left_to_wait = min_interval - elapsed
                if left_to_wait > 0:
                    time.sleep(left_to_wait)
                last_called[0] = time.time()
            return func(*args, **kwargs)
        return wrapper
    return decorator

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
    
    def __init__(self, config: Config, platforms: List[str] = None):
        """
        初始化 PR 监控服务
        
        Args:
            config: 配置管理器
            platforms: 支持的平台列表，如 ['gitee', 'github']，如果为None则自动检测
        """
        self.config = config
        
        # 线程池配置
        self.max_workers = self.config.get("MAX_WORKERS", 5)  # 最大并发线程数
        self.enable_parallel = self.config.get("ENABLE_PARALLEL_PROCESSING", True)  # 是否启用并行处理
        self.rate_limit_per_second = self.config.get("RATE_LIMIT_PER_SECOND", 1.5)  # API调用速率限制
        
        if self.enable_parallel:
            self.thread_pool = ThreadPoolExecutor(max_workers=self.max_workers)
            logger.info(f"已启用并行处理，最大线程数: {self.max_workers}, 速率限制: {self.rate_limit_per_second}/s")
        else:
            self.thread_pool = None
            logger.info("并行处理已禁用，将使用串行处理")
        
        # 如果没有指定平台，则自动检测配置中需要的平台
        if platforms is None:
            detected_platforms = set()
            
            # 从PR列表中检测平台，但只有在有相应访问令牌时才添加
            for pr_config in self.config.get_pr_lists():
                platform = pr_config.get("PLATFORM", "gitee")
                if platform == "gitee" and self.config.get("ACCESS_TOKEN"):
                    detected_platforms.add(platform)
                elif platform == "github" and self.config.get("GITHUB_ACCESS_TOKEN"):
                    detected_platforms.add(platform)
                
            # 从关注作者列表中检测平台，但只有在有相应访问令牌时才添加
            for author_config in self.config.get_followed_authors():
                platform = author_config.get("PLATFORM", "gitee")
                if platform == "gitee" and self.config.get("ACCESS_TOKEN"):
                    detected_platforms.add(platform)
                elif platform == "github" and self.config.get("GITHUB_ACCESS_TOKEN"):
                    detected_platforms.add(platform)
                
            # 如果没有检测到任何平台，默认添加gitee（如果有令牌）
            if not detected_platforms and self.config.get("ACCESS_TOKEN"):
                detected_platforms.add("gitee")
                
            self.platforms = list(detected_platforms)
            logger.info(f"自动检测到需要的平台: {self.platforms}")
        else:
            self.platforms = platforms
        
        # 创建多个API客户端，支持不同平台
        self.api_clients: Dict[str, BaseAPIClient] = {}
        
        for platform in self.platforms:
            # 根据平台获取相应的配置
            if platform == 'gitee':
                api_url = self.config.get("GITEA_URL")
                access_token = self.config.get("ACCESS_TOKEN")
            elif platform == 'github':
                api_url = self.config.get("GITHUB_URL", "https://api.github.com")
                access_token = self.config.get("GITHUB_ACCESS_TOKEN")
            else:
                logger.warning(f"不支持的平台: {platform}")
                continue
                
            # 检查是否有必要的配置
            if not access_token:
                logger.warning(f"跳过创建{platform}API客户端: 缺少访问令牌")
                continue
                
            logger.info(f"正在创建{platform}API客户端: api_url={api_url}, has_token={bool(access_token)}")
            client = APIClientFactory.create_client(platform, api_url, access_token)
            
            if client is None:
                logger.error(f"创建{platform}API客户端失败")
            else:
                logger.info(f"{platform}API客户端创建成功: {type(client)}")
                self.api_clients[platform] = client
        
        self.cache = PRCache(ttl=self.config.get("CACHE_TTL", 300))
        self.pr_labels: Dict[str, Set[str]] = {}  # 保存每个 PR 的最新标签，key格式为 "platform:owner/repo#pr_id"
        self.running = False
        self.poll_thread = None
        
        # 初始化自动化引擎
        automation_config_dict = self.config.get_automation_config()
        automation_config = AutomationConfig.from_dict(automation_config_dict)
        self.automation_engine = AutomationEngine(self.api_clients, self.config, automation_config)
        logger.info("自动化引擎已初始化")
        
    def _get_api_client(self, platform: str) -> Optional[BaseAPIClient]:
        """
        根据平台获取相应的API客户端
        
        Args:
            platform: 平台名称
            
        Returns:
            API客户端实例或None
        """
        return self.api_clients.get(platform)
        
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
        
        # 关闭线程池
        if self.thread_pool:
            self.thread_pool.shutdown(wait=True)
        
        # 关闭自动化引擎
        if hasattr(self, 'automation_engine'):
            self.automation_engine.shutdown()
        
        logger.info("PR 监控服务已停止")
    
    @rate_limit(calls_per_second=1.5)  # 限制每秒1.5次调用
    def get_pr_details(self, platform: str, owner: str, repo: str, pr_id: int, force_refresh: bool = False) -> Optional[PullRequest]:
        """
        获取 PR 的详细信息，优先使用缓存
        
        Args:
            platform: 平台名称（gitee, github等）
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            force_refresh: 是否强制刷新缓存
            
        Returns:
            PR 详细信息对象
        """
        cache_key = f"{platform}:{owner}/{repo}#{pr_id}_details"
        
        if force_refresh:
            self.cache.invalidate(cache_key)
            
        # 检查缓存
        cached_data = self.cache.get(cache_key)
        if cached_data:
            # 确保缓存数据包含平台信息
            if 'platform' not in cached_data:
                cached_data['platform'] = platform
            return PullRequest.from_dict(cached_data)
            
        # 获取对应平台的API客户端
        api_client = self._get_api_client(platform)
        if not api_client:
            logger.warning(f"无法获取 {platform} API客户端")
            return None
            
        pr_data = api_client.get_pr_details(owner, repo, pr_id)
        if pr_data:
            # 确保PR数据包含平台信息
            pr_data['platform'] = platform
            self.cache.set(cache_key, pr_data)
            return PullRequest.from_dict(pr_data)
        return None
    
    @rate_limit(calls_per_second=1.5)  # 限制每秒1.5次调用
    def get_pr_labels(self, platform: str, owner: str, repo: str, pr_id: int, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        获取 PR 的标签，优先使用缓存
        
        Args:
            platform: 平台名称（gitee, github等）
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            force_refresh: 是否强制刷新缓存
            
        Returns:
            PR 标签列表
        """
        cache_key = f"{platform}:{owner}/{repo}#{pr_id}"
        
        if force_refresh:
            self.cache.invalidate(cache_key)
            
        # 检查缓存
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data
            
        # 获取对应平台的API客户端
        api_client = self._get_api_client(platform)
        if not api_client:
            logger.warning(f"无法获取 {platform} API客户端")
            return []
            
        labels = api_client.get_pr_labels(owner, repo, pr_id)
        if labels:
            self.cache.set(cache_key, labels)
            return labels
        return []
    
    def get_all_pr_labels(self, force_refresh: bool = False) -> Dict[str, List[str]]:
        """
        获取所有监控的 PR 的标签（支持并行处理）
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            PR key 到标签名称列表的映射，key格式为 "platform:owner/repo#pr_id"
        """
        result = {}
        pr_configs = self.config.get_pr_lists()
        
        if not pr_configs:
            return result
        
        # 准备任务参数
        tasks = []
        for pr_config in pr_configs:
            platform = pr_config.get("PLATFORM", "gitee")
            owner = pr_config.get("OWNER")
            repo = pr_config.get("REPO")
            pr_id = pr_config.get("PULL_REQUEST_ID")
            
            if owner and repo and pr_id:
                tasks.append((platform, owner, repo, pr_id))
        
        if not tasks:
            return result
        
        # 根据配置选择并行或串行处理
        if self.enable_parallel and self.thread_pool:
            # 并行获取PR标签
            future_to_key = {}
            for platform, owner, repo, pr_id in tasks:
                cache_key = f"{platform}:{owner}/{repo}#{pr_id}"
                future = self.thread_pool.submit(self.get_pr_labels, platform, owner, repo, pr_id, force_refresh)
                future_to_key[future] = cache_key
            
            # 收集结果
            for future in as_completed(future_to_key):
                cache_key = future_to_key[future]
                try:
                    labels = future.result()
                    result[cache_key] = [label.get("name", "") for label in labels]
                except Exception as e:
                    logger.error(f"获取 {cache_key} 标签时出错: {e}")
                    result[cache_key] = []
        else:
            # 串行处理
            for platform, owner, repo, pr_id in tasks:
                cache_key = f"{platform}:{owner}/{repo}#{pr_id}"
                try:
                    labels = self.get_pr_labels(platform, owner, repo, pr_id, force_refresh)
                    result[cache_key] = [label.get("name", "") for label in labels]
                except Exception as e:
                    logger.error(f"获取 {cache_key} 标签时出错: {e}")
                    result[cache_key] = []
                
        return result
        
    def get_followed_author_prs(self, force_refresh: bool = False, auto_add_to_monitor: bool = True) -> List[PullRequest]:
        """
        获取所有关注作者的PR列表（并行处理），并可选择自动将其添加到监控列表中
        
        Args:
            force_refresh: 是否强制刷新缓存
            auto_add_to_monitor: 是否自动将关注作者的PR添加到监控列表中
            
        Returns:
            所有关注作者的PR对象列表
        """
        all_prs = []
        author_configs = self.config.get_followed_authors()
        
        if not author_configs:
            return all_prs
        
        # 准备任务参数
        tasks = []
        cached_prs = []  # 存储缓存中的PR
        
        for author_config in author_configs:
            author = author_config.get("AUTHOR")
            repo_full = author_config.get("REPO")
            platform = author_config.get("PLATFORM", "gitee")
            
            if author and repo_full and "/" in repo_full:
                owner, repo = repo_full.split("/", 1)
                cache_key = f"{platform}:{author}@{owner}/{repo}"
                
                if force_refresh:
                    self.cache.invalidate(cache_key)
                
                # 检查缓存
                cached_data = self.cache.get(cache_key)
                if cached_data:
                    # 直接使用缓存数据
                    for pr_data in cached_data:
                        # 确保PR数据包含平台信息
                        pr_data['platform'] = platform
                        pr = PullRequest.from_dict(pr_data)
                        cached_prs.append(pr)
                        self._add_pr_to_monitor_if_needed(pr, owner, repo, platform, auto_add_to_monitor)
                else:
                    # 需要从API获取
                    tasks.append((platform, author, owner, repo))
        
        # 添加缓存中的PR
        all_prs.extend(cached_prs)
        
        if not tasks:
            return all_prs
        
        # 根据配置选择并行或串行处理
        if self.enable_parallel and self.thread_pool:
            # 并行获取作者PR
            future_to_task = {}
            for platform, author, owner, repo in tasks:
                future = self.thread_pool.submit(self._get_author_prs_single, platform, author, owner, repo)
                future_to_task[future] = (platform, author, owner, repo)
            
            # 收集线程池结果
            for future in as_completed(future_to_task):
                platform, author, owner, repo = future_to_task[future]
                try:
                    prs_data = future.result()
                    self._process_author_prs_data(prs_data, platform, author, owner, repo, auto_add_to_monitor, all_prs)
                except Exception as e:
                    logger.error(f"获取作者 {author} 在 {platform}:{owner}/{repo} 的PR时出错: {e}")
        else:
            # 串行处理
            for platform, author, owner, repo in tasks:
                try:
                    prs_data = self._get_author_prs_single(platform, author, owner, repo)
                    self._process_author_prs_data(prs_data, platform, author, owner, repo, auto_add_to_monitor, all_prs)
                except Exception as e:
                    logger.error(f"获取作者 {author} 在 {platform}:{owner}/{repo} 的PR时出错: {e}")
        
        # 保存配置以保存自动添加的PR
        if auto_add_to_monitor and all_prs:
            self.config.save_config()
            
        return all_prs
    
    @rate_limit(calls_per_second=1.0)  # 获取作者PR的调用频率稍低
    def _get_author_prs_single(self, platform: str, author: str, owner: str, repo: str) -> List[Dict[str, Any]]:
        """
        获取单个作者在单个仓库的PR列表（线程池中执行）
        
        Args:
            platform: 平台名称
            author: 作者名称
            owner: 仓库拥有者
            repo: 仓库名称
            
        Returns:
            PR数据列表
        """
        api_client = self._get_api_client(platform)
        if not api_client:
            logger.warning(f"无法获取 {platform} API客户端")
            return []
        
        return api_client.get_author_prs(owner, repo, author) or []
    
    def _process_author_prs_data(self, prs_data: List[Dict[str, Any]], platform: str, author: str, owner: str, repo: str, auto_add_to_monitor: bool, all_prs: List[PullRequest]):
        """
        处理获取到的作者PR数据
        
        Args:
            prs_data: PR数据列表
            platform: 平台名称
            author: 作者名称
            owner: 仓库拥有者
            repo: 仓库名称
            auto_add_to_monitor: 是否自动添加到监控
            all_prs: 所有PR列表（会被修改）
        """
        if prs_data:
            cache_key = f"{platform}:{author}@{owner}/{repo}"
            self.cache.set(cache_key, prs_data)
            
            # 将PR数据转换为PullRequest对象
            for pr_data in prs_data:
                # 确保PR数据包含平台信息
                pr_data['platform'] = platform
                pr = PullRequest.from_dict(pr_data)
                all_prs.append(pr)
                self._add_pr_to_monitor_if_needed(pr, owner, repo, platform, auto_add_to_monitor)
    
    def _add_pr_to_monitor_if_needed(self, pr: PullRequest, owner: str, repo: str, platform: str, auto_add_to_monitor: bool):
        """
        如果需要，将PR添加到监控列表
        
        Args:
            pr: PR对象
            owner: 仓库拥有者
            repo: 仓库名称
            platform: 平台名称
            auto_add_to_monitor: 是否自动添加到监控
        """
        if not auto_add_to_monitor:
            return
            
        # 检查PR是否已在监控列表中
        is_monitored = False
        for pr_config in self.config.get_pr_lists():
            if (pr_config.get("PLATFORM", "gitee") == platform and
                pr_config.get("OWNER") == owner and 
                pr_config.get("REPO") == repo and 
                pr_config.get("PULL_REQUEST_ID") == pr.number):
                is_monitored = True
                break
        
        # 如果不在监控列表中，则添加
        if not is_monitored:
            self.add_pr_to_monitor(platform, owner, repo, pr.number)
            logger.info(f"自动添加关注作者的 {platform} PR #{pr.number} ({owner}/{repo}) 到监控列表")
    
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
        """检查所有监控的 PR 的标签变化（支持并行处理）"""
        pr_configs = self.config.get_pr_lists()
        
        if not pr_configs:
            return
        
        # 准备任务参数
        tasks = []
        for pr_config in pr_configs:
            platform = pr_config.get("PLATFORM", "gitee")
            owner = pr_config.get("OWNER")
            repo = pr_config.get("REPO")
            pr_id = pr_config.get("PULL_REQUEST_ID")
            
            if owner and repo and pr_id:
                tasks.append((platform, owner, repo, pr_id))
        
        if not tasks:
            return
        
        # 根据配置选择并行或串行处理
        if self.enable_parallel and self.thread_pool:
            # 并行检查PR
            future_to_task = {}
            for platform, owner, repo, pr_id in tasks:
                future = self.thread_pool.submit(self._check_pr, platform, owner, repo, pr_id)
                future_to_task[future] = (platform, owner, repo, pr_id)
            
            # 等待所有任务完成
            for future in as_completed(future_to_task):
                platform, owner, repo, pr_id = future_to_task[future]
                try:
                    future.result()  # 获取结果，如果有异常会抛出
                except Exception as e:
                    logger.error(f"检查 {platform}:{owner}/{repo}#{pr_id} 时出错: {e}")
        else:
            # 串行处理
            for platform, owner, repo, pr_id in tasks:
                try:
                    self._check_pr(platform, owner, repo, pr_id)
                except Exception as e:
                    logger.error(f"检查 {platform}:{owner}/{repo}#{pr_id} 时出错: {e}")
    
    def _check_pr(self, platform: str, owner: str, repo: str, pr_id: int) -> None:
        """
        检查单个 PR 的标签变化
        
        Args:
            platform: 平台名称
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
        """
        labels = self.get_pr_labels(platform, owner, repo, pr_id, force_refresh=True)
        label_names = {label.get("name", "") for label in labels}
        
        cache_key = f"{platform}:{owner}/{repo}#{pr_id}"
        
        # 检查标签变化
        if cache_key in self.pr_labels:
            old_labels = self.pr_labels[cache_key]
            if old_labels != label_names:
                added = label_names - old_labels
                removed = old_labels - label_names
                self._notify_label_change(platform, owner, repo, pr_id, added, removed)
        
        # 更新保存的标签
        self.pr_labels[cache_key] = label_names
    
    def _notify_label_change(self, platform: str, owner: str, repo: str, pr_id: int, added: Set[str], removed: Set[str]) -> None:
        """
        处理标签变化通知
        
        Args:
            platform: 平台名称
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
            
        message = f"{platform.upper()} PR #{pr_id} ({owner}/{repo}) 标签变化: {' '.join(change_str)}"
        logger.info(message)
        
        # 触发自动化规则
        self._trigger_automation(TriggerType.LABEL_CHANGED.value, platform, owner, repo, pr_id, {
            'added_labels': list(added),
            'removed_labels': list(removed)
        })
        
        # TODO: 实现实际的通知功能，如邮件、Webhook 等
    
    def _trigger_automation(self, event_type: str, platform: str, owner: str, repo: str, pr_id: int, extra_context: dict = None) -> None:
        """
        触发自动化规则
        
        Args:
            event_type: 事件类型
            platform: 平台名称
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            extra_context: 额外的上下文信息
        """
        try:
            # 获取PR详细信息
            pr = self.get_pr_details(platform, owner, repo, pr_id)
            if not pr:
                logger.warning(f"无法获取PR详情进行自动化处理: {platform}:{owner}/{repo}#{pr_id}")
                return
            
            # 转换为API格式的数据
            pr_data = pr.to_dict()
            
            # 构建上下文
            context = {
                'platform': platform,
                'event_type': event_type,
                'timestamp': datetime.now().isoformat()
            }
            
            if extra_context:
                context.update(extra_context)
            
            # 触发自动化引擎处理
            executed_rules = self.automation_engine.process_event(event_type, pr_data, context)
            
            if executed_rules:
                logger.info(f"为事件 {event_type} 执行了 {len(executed_rules)} 个自动化规则: {executed_rules}")
            
        except Exception as e:
            logger.error(f"触发自动化规则时出错: {e}")
    
    def add_pr_to_monitor(self, platform: str, owner: str, repo: str, pr_id: int) -> bool:
        """
        添加PR到监控列表并触发自动化
        
        Args:
            platform: 平台名称
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            是否添加成功
        """
        try:
            # 添加到配置
            success = self.config.add_pr(owner, repo, pr_id, platform)
            
            if success:
                logger.info(f"成功添加PR到监控列表: {platform}:{owner}/{repo}#{pr_id}")
                
                # 触发PR添加事件
                self._trigger_automation(TriggerType.PR_ADDED.value, platform, owner, repo, pr_id)
                
                return True
            else:
                logger.warning(f"PR已存在于监控列表中: {platform}:{owner}/{repo}#{pr_id}")
                return False
                
        except Exception as e:
            logger.error(f"添加PR到监控列表失败: {e}")
            return False
    
    def remove_pr_from_monitor(self, platform: str, owner: str, repo: str, pr_id: int) -> bool:
        """
        从监控列表中移除PR
        
        Args:
            platform: 平台名称
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            
        Returns:
            是否移除成功
        """
        try:
            success = self.config.remove_pr(owner, repo, pr_id, platform)
            
            if success:
                logger.info(f"成功从监控列表移除PR: {platform}:{owner}/{repo}#{pr_id}")
                
                # 清理缓存
                cache_key = f"{platform}:{owner}/{repo}#{pr_id}"
                if cache_key in self.pr_labels:
                    del self.pr_labels[cache_key]
                
                self.cache.invalidate(cache_key)
                self.cache.invalidate(f"{cache_key}_details")
                
                return True
            else:
                logger.warning(f"PR不在监控列表中: {platform}:{owner}/{repo}#{pr_id}")
                return False
                
        except Exception as e:
            logger.error(f"从监控列表移除PR失败: {e}")
            return False
    
    def get_automation_engine(self):
        """获取自动化引擎实例"""
        return self.automation_engine
    
    def get_multiple_pr_details(self, pr_list: List[Dict[str, Any]], force_refresh: bool = False) -> List[Optional[PullRequest]]:
        """
        并行获取多个PR的详细信息
        
        Args:
            pr_list: PR信息列表，每个元素包含 platform, owner, repo, pr_id
            force_refresh: 是否强制刷新缓存
            
        Returns:
            PR详细信息对象列表
        """
        if not pr_list:
            return []
        
        # 根据配置选择并行或串行处理
        if self.enable_parallel and self.thread_pool:
            # 并行获取PR详情
            future_to_index = {}
            for i, pr_info in enumerate(pr_list):
                platform = pr_info.get("platform", "gitee")
                owner = pr_info.get("owner")
                repo = pr_info.get("repo")
                pr_id = pr_info.get("pr_id")
                
                if owner and repo and pr_id:
                    future = self.thread_pool.submit(self.get_pr_details, platform, owner, repo, pr_id, force_refresh)
                    future_to_index[future] = i
            
            # 收集结果，保持原始顺序
            results = [None] * len(pr_list)
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except Exception as e:
                    pr_info = pr_list[index]
                    logger.error(f"获取PR详情时出错 {pr_info.get('platform')}:{pr_info.get('owner')}/{pr_info.get('repo')}#{pr_info.get('pr_id')}: {e}")
                    results[index] = None
            
            return results
        else:
            # 串行处理
            results = []
            for pr_info in pr_list:
                platform = pr_info.get("platform", "gitee")
                owner = pr_info.get("owner")
                repo = pr_info.get("repo")
                pr_id = pr_info.get("pr_id")
                
                if owner and repo and pr_id:
                    try:
                        pr = self.get_pr_details(platform, owner, repo, pr_id, force_refresh)
                        results.append(pr)
                    except Exception as e:
                        logger.error(f"获取PR详情时出错 {platform}:{owner}/{repo}#{pr_id}: {e}")
                        results.append(None)
                else:
                    results.append(None)
            
            return results
    
    def get_multiple_pr_labels_batch(self, pr_list: List[Dict[str, Any]], force_refresh: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """
        并行获取多个PR的标签信息
        
        Args:
            pr_list: PR信息列表，每个元素包含 platform, owner, repo, pr_id
            force_refresh: 是否强制刷新缓存
            
        Returns:
            PR标签字典，key为 "platform:owner/repo#pr_id"
        """
        if not pr_list:
            return {}
        
        # 根据配置选择并行或串行处理
        if self.enable_parallel and self.thread_pool:
            # 并行获取PR标签
            future_to_key = {}
            for pr_info in pr_list:
                platform = pr_info.get("platform", "gitee")
                owner = pr_info.get("owner")
                repo = pr_info.get("repo")
                pr_id = pr_info.get("pr_id")
                
                if owner and repo and pr_id:
                    cache_key = f"{platform}:{owner}/{repo}#{pr_id}"
                    future = self.thread_pool.submit(self.get_pr_labels, platform, owner, repo, pr_id, force_refresh)
                    future_to_key[future] = cache_key
            
            # 收集结果
            results = {}
            for future in as_completed(future_to_key):
                cache_key = future_to_key[future]
                try:
                    results[cache_key] = future.result()
                except Exception as e:
                    logger.error(f"获取PR标签时出错 {cache_key}: {e}")
                    results[cache_key] = []
            
            return results
        else:
            # 串行处理
            results = {}
            for pr_info in pr_list:
                platform = pr_info.get("platform", "gitee")
                owner = pr_info.get("owner")
                repo = pr_info.get("repo")
                pr_id = pr_info.get("pr_id")
                
                if owner and repo and pr_id:
                    cache_key = f"{platform}:{owner}/{repo}#{pr_id}"
                    try:
                        labels = self.get_pr_labels(platform, owner, repo, pr_id, force_refresh)
                        results[cache_key] = labels
                    except Exception as e:
                        logger.error(f"获取PR标签时出错 {cache_key}: {e}")
                        results[cache_key] = []
            
            return results
    
    def refresh_all_cache(self) -> None:
        """
        刷新所有缓存（并行处理）
        """
        logger.info("开始刷新所有缓存...")
        
        # 刷新PR标签缓存
        start_time = time.time()
        self.get_all_pr_labels(force_refresh=True)
        pr_time = time.time() - start_time
        
        # 刷新关注作者PR缓存
        start_time = time.time()
        self.get_followed_author_prs(force_refresh=True, auto_add_to_monitor=False)
        author_time = time.time() - start_time
        
        logger.info(f"缓存刷新完成 - PR标签: {pr_time:.2f}s, 关注作者PR: {author_time:.2f}s")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        获取性能统计信息
        
        Returns:
            性能统计字典
        """
        return {
            "max_workers": self.max_workers,
            "parallel_processing_enabled": self.enable_parallel,
            "rate_limit_per_second": self.rate_limit_per_second,
            "active_platforms": list(self.api_clients.keys()),
            "monitored_prs": len(self.config.get_pr_lists()),
            "followed_authors": len(self.config.get_followed_authors()),
            "cache_entries": len(self.cache.cache),
            "cache_ttl": self.cache.ttl,
            "thread_pool_active": self.thread_pool is not None and not self.thread_pool._shutdown if self.thread_pool else False,
            "monitor_running": self.running
        }
