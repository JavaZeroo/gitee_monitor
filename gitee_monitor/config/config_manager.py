"""
配置管理模块，处理应用配置的加载、存储和访问
"""
import os
import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class Config:
    """配置管理类，处理配置的加载、存储和访问"""
    
    DEFAULT_CONFIG = {
        "GITEA_URL": "https://gitee.com/api/v5",
        "ACCESS_TOKEN": "",
        "GITHUB_ACCESS_TOKEN": "",
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
        self.config = self.DEFAULT_CONFIG.copy()
        self.load_config()
        
    def load_config(self) -> None:
        """从文件加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    
                    # 处理旧配置格式的兼容性
                    if "OWNER" in loaded_config and "REPO" in loaded_config and "PULL_REQUEST_IDS" in loaded_config:
                        # 转换旧格式到新格式
                        owner = loaded_config.get("OWNER", "")
                        repo = loaded_config.get("REPO", "")
                        pr_ids = loaded_config.get("PULL_REQUEST_IDS", [])
                        
                        if owner and repo and pr_ids:
                            self.config["PULL_REQUEST_LISTS"] = []
                            for pr_id in pr_ids:
                                self.config["PULL_REQUEST_LISTS"].append({
                                    "OWNER": owner,
                                    "REPO": repo,
                                    "PULL_REQUEST_ID": pr_id
                                })
                        
                        # 复制其他配置项
                        for key in ["GITEA_URL", "ACCESS_TOKEN", "CACHE_TTL", "POLL_INTERVAL", "ENABLE_NOTIFICATIONS"]:
                            if key in loaded_config:
                                self.config[key] = loaded_config[key]
                                
                        logger.info("检测到旧配置格式，已自动转换为新格式")
                        self.save_config()  # 保存转换后的配置
                    else:
                        # 新格式配置，直接更新
                        for key in self.config:
                            if key in loaded_config:
                                self.config[key] = loaded_config[key]
                                
                        # 如果存在旧的独立规则文件，尝试合并
                        self._migrate_old_rules_if_needed()
                                
                logger.info(f"配置已从 {self.config_file} 加载")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"加载配置文件失败: {e}")
        else:
            logger.warning(f"配置文件 {self.config_file} 不存在，使用默认配置")
            # 检查是否存在旧的独立规则文件
            self._migrate_old_rules_if_needed()
            self.save_config()  # 创建默认配置文件
    
    def _migrate_old_rules_if_needed(self) -> None:
        """如果存在旧的独立规则文件，则迁移到主配置中"""
        old_rules_file = os.path.join(os.path.dirname(self.config_file), "automation", "rules.json")
        
        if os.path.exists(old_rules_file):
            try:
                with open(old_rules_file, 'r', encoding='utf-8') as f:
                    rules_data = json.load(f)
                
                if rules_data and not self.config.get("AUTOMATION_RULES"):
                    self.config["AUTOMATION_RULES"] = rules_data
                    logger.info(f"已从 {old_rules_file} 迁移 {len(rules_data)} 个自动化规则")
                    
                    # 创建备份并删除旧文件
                    backup_file = old_rules_file + ".migrated.bak"
                    os.rename(old_rules_file, backup_file)
                    logger.info(f"旧规则文件已备份到: {backup_file}")
                    
                    # 尝试删除空目录
                    automation_dir = os.path.dirname(old_rules_file)
                    try:
                        os.rmdir(automation_dir)
                        logger.info(f"已删除空目录: {automation_dir}")
                    except OSError:
                        pass  # 目录不为空或其他原因，忽略
                        
            except Exception as e:
                logger.warning(f"迁移旧规则文件失败: {e}")
    
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
    
    def get_pr_ids(self) -> List[int]:
        """
        获取所有监控的 PR ID（兼容性方法，已废弃）
        
        Returns:
            PR ID 列表
        """
        pr_lists = self.config.get("PULL_REQUEST_LISTS", [])
        return [pr.get("PULL_REQUEST_ID") for pr in pr_lists if pr.get("PULL_REQUEST_ID")]
        
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
        followed_authors = self.config.get("FOLLOWED_AUTHORS", [])
        
        # 向后兼容：为没有PLATFORM字段的旧配置项添加默认值
        for author_config in followed_authors:
            if "PLATFORM" not in author_config:
                author_config["PLATFORM"] = "gitee"  # 默认为gitee平台
        
        return followed_authors
    
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
