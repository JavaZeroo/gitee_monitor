"""
配置管理模块，处理应用配置的加载、存储和访问
"""
import os
import json
import logging
import copy
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class Config:
    """配置管理类，处理配置的加载、存储和访问"""
    
    DEFAULT_CONFIG = {
        "PLATFORM": [
            {
                "NAME": "gitee",
                "API_URL": "https://gitee.com/api/v5",
                "ACCESS_TOKEN": ""
            },
            {
                "NAME": "github",
                "API_URL": "https://api.github.com",
                "ACCESS_TOKEN": ""
            }
        ],
        "PULL_REQUEST_LISTS": [],  # PR监控列表，每个元素包含OWNER、REPO、PULL_REQUEST_ID
        "FOLLOWED_AUTHORS": [],  # 关注的PR创建者列表，每个元素包含AUTHOR、REPO
        "CACHE_TTL": 300,  # 缓存生存时间（秒）
        "POLL_INTERVAL": 60,  # 轮询间隔（秒）
        "ENABLE_NOTIFICATIONS": False,  # 是否启用通知
        "MAX_WORKERS": 5,  # 最大并发线程数
        "RATE_LIMIT_PER_SECOND": 1.5,  # API调用速率限制（每秒调用次数）
        "ENABLE_PARALLEL_PROCESSING": True,  # 是否启用并行处理
        "AUTOMATION_RULES": [],  # 自动化规则列表
        "AUTOMATION_CONFIG": {  # 自动化引擎配置
            "enabled": True,
            "max_parallel_executions": 5,
            "default_cooldown": 300,
            "max_executions_per_day": 100,
            "log_level": "INFO"
        }
    }
    
    def __init__(self, config_file: str):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config = copy.deepcopy(self.DEFAULT_CONFIG)
        self.load_config()
        
    def load_config(self) -> None:
        """从文件加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)

                    for key in self.config:
                        if key in loaded_config:
                            self.config[key] = loaded_config[key]
                                
                logger.info(f"配置已从 {self.config_file} 加载")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"加载配置文件失败: {e}")
        else:
            logger.warning(f"配置文件 {self.config_file} 不存在，使用默认配置")
            self.save_config()  # 创建默认配置文件
    def save_config(self) -> None:
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info(f"配置已保存到 {self.config_file}")
        except IOError as e:
            logger.error(f"保存配置文件失败: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项
        
        Args:
            key: 配置项名称
            default: 默认值，如果配置项不存在
            
        Returns:
            配置项值
        """
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置项
        
        Args:
            key: 配置项名称
            value: 配置项值
        """
        self.config[key] = value
        
    def update(self, config_dict: Dict[str, Any]) -> None:
        """
        批量更新配置
        
        Args:
            config_dict: 包含多个配置项的字典
        """
        for key, value in config_dict.items():
            if key in self.config:
                self.config[key] = value

    def get_platforms(self) -> List[Dict[str, Any]]:
        """获取所有平台配置列表"""
        return self.config.get("PLATFORM", [])

    def get_platform_config(self, name: str) -> Dict[str, Any]:
        """根据名称获取单个平台配置"""
        for p in self.get_platforms():
            if p.get("NAME") == name:
                return p
        return {}

    def set_platform_config(self, name: str, api_url: str = None, access_token: str = None) -> None:
        """设置或更新单个平台配置"""
        platforms = self.get_platforms()
        for p in platforms:
            if p.get("NAME") == name:
                if api_url is not None:
                    p["API_URL"] = api_url
                if access_token is not None:
                    p["ACCESS_TOKEN"] = access_token
                self.config["PLATFORM"] = platforms
                return
        new_entry = {"NAME": name, "API_URL": api_url or "", "ACCESS_TOKEN": access_token or ""}
        platforms.append(new_entry)
        self.config["PLATFORM"] = platforms

    def get_access_token(self, name: str) -> str:
        """获取指定平台的访问令牌"""
        return self.get_platform_config(name).get("ACCESS_TOKEN", "")

    def get_api_url(self, name: str) -> str:
        """获取指定平台的API URL"""
        return self.get_platform_config(name).get("API_URL", "")
    
    def add_pr(self, owner: str, repo: str, pr_id: int, platform: str = "gitee") -> None:
        """
        添加 PR 到监控列表
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            platform: 平台名称（默认为gitee）
        """
        pr_lists = self.config.get("PULL_REQUEST_LISTS", [])
        
        # 检查是否已存在相同的PR
        for existing_pr in pr_lists:
            if (existing_pr.get("PLATFORM", "gitee") == platform and
                existing_pr.get("OWNER") == owner and 
                existing_pr.get("REPO") == repo and 
                existing_pr.get("PULL_REQUEST_ID") == pr_id):
                logger.warning(f"{platform.upper()} PR #{pr_id} ({owner}/{repo}) 已存在于监控列表中")
                return
        
        # 添加新PR
        pr_lists.append({
            "PLATFORM": platform,
            "OWNER": owner,
            "REPO": repo,
            "PULL_REQUEST_ID": pr_id
        })
        self.config["PULL_REQUEST_LISTS"] = pr_lists
        logger.info(f"添加 {platform.upper()} PR #{pr_id} ({owner}/{repo}) 到监控列表")
    
    def remove_pr(self, owner: str, repo: str, pr_id: int, platform: str = "gitee") -> None:
        """
        从监控列表中移除 PR
        
        Args:
            owner: 仓库拥有者
            repo: 仓库名称
            pr_id: PR ID
            platform: 平台名称（默认为gitee）
        """
        pr_lists = self.config.get("PULL_REQUEST_LISTS", [])
        
        for i, existing_pr in enumerate(pr_lists):
            if (existing_pr.get("PLATFORM", "gitee") == platform and
                existing_pr.get("OWNER") == owner and 
                existing_pr.get("REPO") == repo and 
                existing_pr.get("PULL_REQUEST_ID") == pr_id):
                pr_lists.pop(i)
                self.config["PULL_REQUEST_LISTS"] = pr_lists
                logger.info(f"从监控列表中移除 {platform.upper()} PR #{pr_id} ({owner}/{repo})")
                return
        
        logger.warning(f"未找到要移除的 {platform.upper()} PR #{pr_id} ({owner}/{repo})")
    
    def get_pr_lists(self) -> List[Dict[str, Any]]:
        """
        获取所有监控的 PR 列表
        
        Returns:
            PR 列表，每个元素包含 OWNER、REPO、PULL_REQUEST_ID
        """
        return self.config.get("PULL_REQUEST_LISTS", [])
    
        
    def add_followed_author(self, author: str, repo: str, platform: str = "gitee") -> None:
        """
        添加关注的PR创建者
        
        Args:
            author: PR创建者用户名
            repo: 仓库名称，格式为 owner/repo
            platform: 平台名称，gitee 或 github
        """
        followed_authors = self.config.get("FOLLOWED_AUTHORS", [])
        
        # 检查是否已存在相同的关注
        for existing_author in followed_authors:
            if (existing_author.get("AUTHOR") == author and 
                existing_author.get("REPO") == repo and
                existing_author.get("PLATFORM") == platform):
                logger.warning(f"作者 {author} 的仓库 {repo} 在平台 {platform} 已存在于关注列表中")
                return
        
        # 添加新关注
        followed_authors.append({
            "AUTHOR": author,
            "REPO": repo,
            "PLATFORM": platform
        })
        self.config["FOLLOWED_AUTHORS"] = followed_authors
        logger.info(f"添加作者 {author} 的仓库 {repo} 到关注列表 (平台: {platform})")
    
    def remove_followed_author(self, author: str, repo: str, platform: str = "gitee") -> None:
        """
        从关注列表中移除PR创建者
        
        Args:
            author: PR创建者用户名
            repo: 仓库名称，格式为 owner/repo
            platform: 平台名称，gitee 或 github
        """
        followed_authors = self.config.get("FOLLOWED_AUTHORS", [])
        
        for i, existing_author in enumerate(followed_authors):
            if (existing_author.get("AUTHOR") == author and 
                existing_author.get("REPO") == repo and
                existing_author.get("PLATFORM") == platform):
                followed_authors.pop(i)
                self.config["FOLLOWED_AUTHORS"] = followed_authors
                logger.info(f"从关注列表中移除作者 {author} 的仓库 {repo} (平台: {platform})")
                return
        
        logger.warning(f"未找到要移除的作者 {author} 的仓库 {repo} (平台: {platform})")
    
    def get_followed_authors(self) -> List[Dict[str, Any]]:
        """
        获取所有关注的PR创建者列表
        
        Returns:
            关注列表，每个元素包含 AUTHOR、REPO、PLATFORM
        """
        return self.config.get("FOLLOWED_AUTHORS", [])
    
    def get_automation_rules(self) -> List[Dict[str, Any]]:
        """
        获取所有自动化规则
        
        Returns:
            自动化规则列表
        """
        return self.config.get("AUTOMATION_RULES", [])
    
    def set_automation_rules(self, rules: List[Dict[str, Any]]) -> None:
        """
        设置自动化规则列表
        
        Args:
            rules: 自动化规则列表
        """
        self.config["AUTOMATION_RULES"] = rules
    
    def get_automation_config(self) -> Dict[str, Any]:
        """
        获取自动化引擎配置
        
        Returns:
            自动化引擎配置
        """
        return self.config.get("AUTOMATION_CONFIG", {
            "enabled": True,
            "max_parallel_executions": 5,
            "default_cooldown": 300,
            "max_executions_per_day": 100,
            "log_level": "INFO"
        })
    
    def update_automation_config(self, automation_config: Dict[str, Any]) -> None:
        """
        更新自动化引擎配置
        
        Args:
            automation_config: 自动化引擎配置
        """
        current_config = self.get_automation_config()
        current_config.update(automation_config)
        self.config["AUTOMATION_CONFIG"] = current_config
