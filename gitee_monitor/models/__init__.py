"""
PR相关的数据模型定义
使用dataclass提供结构化的数据管理
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class PRLabel:
    """PR标签数据模型"""
    id: int
    name: str
    color: str
    description: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PRLabel':
        """从字典创建PRLabel实例"""
        return cls(
            id=data.get('id', 0),
            name=data.get('name', ''),
            color=data.get('color', ''),
            description=data.get('description')
        )


@dataclass
class PRUser:
    """PR用户数据模型"""
    id: int
    login: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    html_url: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PRUser':
        """从字典创建PRUser实例"""
        return cls(
            id=data.get('id', 0),
            login=data.get('login', ''),
            name=data.get('name'),
            avatar_url=data.get('avatar_url'),
            html_url=data.get('html_url')
        )


@dataclass
class PRRepository:
    """PR仓库数据模型"""
    id: int
    name: str
    full_name: str
    owner: PRUser
    html_url: Optional[str] = None
    description: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PRRepository':
        """从字典创建PRRepository实例"""
        owner_data = data.get('owner', {})
        return cls(
            id=data.get('id', 0),
            name=data.get('name', ''),
            full_name=data.get('full_name', ''),
            owner=PRUser.from_dict(owner_data),
            html_url=data.get('html_url'),
            description=data.get('description')
        )


@dataclass
class PRBranch:
    """PR分支数据模型"""
    ref: str
    sha: str
    repo: PRRepository
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PRBranch':
        """从字典创建PRBranch实例"""
        repo_data = data.get('repo', {})
        return cls(
            ref=data.get('ref', ''),
            sha=data.get('sha', ''),
            repo=PRRepository.from_dict(repo_data)
        )


@dataclass
class PullRequest:
    """PR数据模型"""
    id: int
    number: int
    title: str
    body: Optional[str]
    state: str  # open, closed, merged
    user: PRUser
    base: PRBranch
    head: PRBranch
    html_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None
    merged_at: Optional[str] = None
    labels: List[PRLabel] = field(default_factory=list)
    
    # 新增字段用于缓存处理
    owner: str = field(init=False)
    repo: str = field(init=False)
    platform: str = field(default="gitee")  # 添加平台信息
    
    def __post_init__(self):
        """初始化后处理"""
        # 从base分支提取owner和repo信息
        if self.base and self.base.repo:
            repo_parts = self.base.repo.full_name.split('/')
            if len(repo_parts) == 2:
                self.owner = repo_parts[0]
                self.repo = repo_parts[1]
            else:
                self.owner = self.base.repo.owner.login
                self.repo = self.base.repo.name
        else:
            self.owner = ''
            self.repo = ''
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PullRequest':
        """从字典创建PullRequest实例"""
        # 处理用户信息
        user_data = data.get('user', {})
        user = PRUser.from_dict(user_data)
        
        # 处理分支信息
        base_data = data.get('base', {})
        head_data = data.get('head', {})
        base = PRBranch.from_dict(base_data) if base_data else None
        head = PRBranch.from_dict(head_data) if head_data else None
          # 处理标签信息
        labels_data = data.get('labels', [])
        labels = [PRLabel.from_dict(label) for label in labels_data]
        
        return cls(
            id=data.get('id', 0),
            number=data.get('number', 0),
            title=data.get('title', ''),
            body=data.get('body'),
            state=data.get('state', 'open'),
            user=user,
            base=base,
            head=head,
            html_url=data.get('html_url'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            closed_at=data.get('closed_at'),
            merged_at=data.get('merged_at'),
            labels=labels,
            platform=data.get('platform', 'gitee')  # 添加平台信息处理
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'id': self.id,
            'number': self.number,
            'title': self.title,
            'body': self.body,
            'state': self.state,
            'user': {
                'id': self.user.id,
                'login': self.user.login,
                'name': self.user.name,
                'avatar_url': self.user.avatar_url,
                'html_url': self.user.html_url
            },
            'base': {
                'ref': self.base.ref,
                'sha': self.base.sha,
                'repo': {
                    'id': self.base.repo.id,
                    'name': self.base.repo.name,
                    'full_name': self.base.repo.full_name,
                    'html_url': self.base.repo.html_url,
                    'description': self.base.repo.description,
                    'owner': {
                        'id': self.base.repo.owner.id,
                        'login': self.base.repo.owner.login,
                        'name': self.base.repo.owner.name,
                        'avatar_url': self.base.repo.owner.avatar_url,
                        'html_url': self.base.repo.owner.html_url
                    }
                }
            } if self.base else None,
            'head': {
                'ref': self.head.ref,
                'sha': self.head.sha,
                'repo': {
                    'id': self.head.repo.id,
                    'name': self.head.repo.name,
                    'full_name': self.head.repo.full_name,
                    'html_url': self.head.repo.html_url,
                    'description': self.head.repo.description,
                    'owner': {
                        'id': self.head.repo.owner.id,
                        'login': self.head.repo.owner.login,
                        'name': self.head.repo.owner.name,
                        'avatar_url': self.head.repo.owner.avatar_url,
                        'html_url': self.head.repo.owner.html_url
                    }
                }
            } if self.head else None,            'html_url': self.html_url,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'closed_at': self.closed_at,
            'merged_at': self.merged_at,
            'platform': self.platform,  # 添加平台信息
            'labels': [
                {
                    'id': label.id,
                    'name': label.name,
                    'color': label.color,
                    'description': label.description
                } for label in self.labels
            ]
        }
    
    def get_cache_key(self) -> str:
        """获取缓存键"""
        return f"{self.owner}/{self.repo}#{self.number}"
    
    def get_label_names(self) -> List[str]:
        """获取标签名称列表"""
        return [label.name for label in self.labels]
    
    def has_label(self, label_name: str) -> bool:
        """检查是否包含指定标签"""
        return label_name in self.get_label_names()
    
    def is_open(self) -> bool:
        """检查PR是否为开放状态"""
        return self.state == 'open'
    
    def is_closed(self) -> bool:
        """检查PR是否为关闭状态"""
        return self.state in ['closed', 'merged']
