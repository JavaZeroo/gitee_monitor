"""
自动化规则相关的数据模型
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, time
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """触发器类型枚举"""
    PR_ADDED = "pr_added"           # PR被添加到监控
    PR_UPDATED = "pr_updated"       # PR状态更新
    LABEL_CHANGED = "label_changed" # 标签变化
    STATUS_CHANGED = "status_changed" # 状态变化
    SCHEDULED = "scheduled"         # 定时触发
    MANUAL = "manual"              # 手动触发


class ConditionType(Enum):
    """条件类型枚举"""
    HAS_LABEL = "has_label"         # 包含特定标签
    NOT_HAS_LABEL = "not_has_label" # 不包含特定标签
    STATUS_IS = "status_is"         # 状态等于
    STATUS_NOT = "status_not"       # 状态不等于
    TIME_RANGE = "time_range"       # 时间范围内
    AUTHOR_IS = "author_is"         # 作者是
    AUTHOR_NOT = "author_not"       # 作者不是
    BRANCH_MATCHES = "branch_matches" # 分支匹配
    PLATFORM_IS = "platform_is"    # 平台是
    REPO_IS = "repo_is"            # 仓库是
    TITLE_CONTAINS = "title_contains" # 标题包含
    BODY_CONTAINS = "body_contains"   # 描述包含
    IS_DRAFT = "is_draft"           # 是草稿PR
    IS_NOT_DRAFT = "is_not_draft"   # 不是草稿PR


class ActionType(Enum):
    """动作类型枚举"""
    COMMENT = "comment"             # 添加评论
    ADD_LABEL = "add_label"         # 添加标签
    REMOVE_LABEL = "remove_label"   # 移除标签
    CLOSE_PR = "close_pr"           # 关闭PR
    APPROVE_PR = "approve_pr"       # 批准PR
    REQUEST_CHANGES = "request_changes" # 请求更改
    SEND_EMAIL = "send_email"       # 发送邮件
    WEBHOOK = "webhook"             # 调用webhook
    LOG = "log"                     # 记录日志


class OperatorType(Enum):
    """操作符类型枚举"""
    EQUALS = "eq"                   # 等于
    NOT_EQUALS = "ne"               # 不等于
    CONTAINS = "contains"           # 包含
    NOT_CONTAINS = "not_contains"   # 不包含
    IN = "in"                       # 在列表中
    NOT_IN = "not_in"              # 不在列表中
    MATCHES = "matches"             # 正则匹配
    NOT_MATCHES = "not_matches"     # 正则不匹配
    GREATER_THAN = "gt"             # 大于
    LESS_THAN = "lt"               # 小于
    GREATER_EQUAL = "ge"            # 大于等于
    LESS_EQUAL = "le"              # 小于等于


@dataclass
class Condition:
    """自动化条件"""
    type: str                       # 条件类型
    operator: str                   # 操作符
    value: Any                      # 比较值
    field: Optional[str] = None     # 字段名（用于复杂条件）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'type': self.type,
            'operator': self.operator,
            'value': self.value,
            'field': self.field
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Condition':
        """从字典创建条件"""
        return cls(
            type=data['type'],
            operator=data['operator'],
            value=data['value'],
            field=data.get('field')
        )


@dataclass
class Action:
    """自动化动作"""
    type: str                       # 动作类型
    parameters: Dict[str, Any]      # 动作参数
    delay: int = 0                  # 延迟执行（秒）
    retry_count: int = 0           # 重试次数
    retry_interval: int = 60       # 重试间隔（秒）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'type': self.type,
            'parameters': self.parameters,
            'delay': self.delay,
            'retry_count': self.retry_count,
            'retry_interval': self.retry_interval
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Action':
        """从字典创建动作"""
        return cls(
            type=data['type'],
            parameters=data['parameters'],
            delay=data.get('delay', 0),
            retry_count=data.get('retry_count', 0),
            retry_interval=data.get('retry_interval', 60)
        )


@dataclass
class TimeRange:
    """时间范围"""
    start: time                     # 开始时间
    end: time                       # 结束时间
    timezone: str = "local"         # 时区
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'start': self.start.strftime('%H:%M:%S'),
            'end': self.end.strftime('%H:%M:%S'),
            'timezone': self.timezone
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimeRange':
        """从字典创建时间范围"""
        start_time = datetime.strptime(data['start'], '%H:%M:%S').time()
        end_time = datetime.strptime(data['end'], '%H:%M:%S').time()
        return cls(
            start=start_time,
            end=end_time,
            timezone=data.get('timezone', 'local')
        )


@dataclass
class ExecutionRecord:
    """执行记录"""
    rule_id: str
    executed_at: datetime
    pr_info: Dict[str, Any]
    actions_executed: List[str]
    success: bool
    error_message: Optional[str] = None
    execution_time: float = 0.0     # 执行耗时（秒）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'rule_id': self.rule_id,
            'executed_at': self.executed_at.isoformat(),
            'pr_info': self.pr_info,
            'actions_executed': self.actions_executed,
            'success': self.success,
            'error_message': self.error_message,
            'execution_time': self.execution_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionRecord':
        """从字典创建执行记录"""
        return cls(
            rule_id=data['rule_id'],
            executed_at=datetime.fromisoformat(data['executed_at']),
            pr_info=data['pr_info'],
            actions_executed=data['actions_executed'],
            success=data['success'],
            error_message=data.get('error_message'),
            execution_time=data.get('execution_time', 0.0)
        )


@dataclass
class AutomationRule:
    """自动化规则"""
    id: str                         # 规则ID
    name: str                       # 规则名称
    description: str                # 规则描述
    trigger: str                    # 触发器类型
    conditions: List[Condition]     # 条件列表
    actions: List[Action]           # 动作列表
    enabled: bool = True            # 是否启用
    priority: int = 0               # 优先级（数字越大优先级越高）
    time_range: Optional[TimeRange] = None  # 生效时间范围
    cooldown: int = 0              # 冷却时间（秒）
    max_executions_per_day: Optional[int] = None  # 每日最大执行次数
    tags: List[str] = field(default_factory=list)  # 标签
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_executed: Optional[datetime] = None
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    
    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'trigger': self.trigger,
            'conditions': [c.to_dict() for c in self.conditions],
            'actions': [a.to_dict() for a in self.actions],
            'enabled': self.enabled,
            'priority': self.priority,
            'time_range': self.time_range.to_dict() if self.time_range else None,
            'cooldown': self.cooldown,
            'max_executions_per_day': self.max_executions_per_day,
            'tags': self.tags,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_executed': self.last_executed.isoformat() if self.last_executed else None,
            'execution_count': self.execution_count,
            'success_count': self.success_count,
            'failure_count': self.failure_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AutomationRule':
        """从字典创建规则"""
        conditions = [Condition.from_dict(c) for c in data.get('conditions', [])]
        actions = [Action.from_dict(a) for a in data.get('actions', [])]
        time_range = TimeRange.from_dict(data['time_range']) if data.get('time_range') else None
        
        return cls(
            id=data['id'],
            name=data['name'],
            description=data['description'],
            trigger=data['trigger'],
            conditions=conditions,
            actions=actions,
            enabled=data.get('enabled', True),
            priority=data.get('priority', 0),
            time_range=time_range,
            cooldown=data.get('cooldown', 0),
            max_executions_per_day=data.get('max_executions_per_day'),
            tags=data.get('tags', []),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
            updated_at=datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else None,
            last_executed=datetime.fromisoformat(data['last_executed']) if data.get('last_executed') else None,
            execution_count=data.get('execution_count', 0),
            success_count=data.get('success_count', 0),
            failure_count=data.get('failure_count', 0)
        )
    
    def update_statistics(self, success: bool):
        """更新执行统计"""
        self.execution_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.last_executed = datetime.now()
        self.updated_at = datetime.now()


@dataclass
class AutomationConfig:
    """自动化配置"""
    enabled: bool = True
    max_parallel_executions: int = 5
    default_cooldown: int = 300
    max_executions_per_day: int = 100
    log_level: str = "INFO"
    storage_path: str = "automation"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'enabled': self.enabled,
            'max_parallel_executions': self.max_parallel_executions,
            'default_cooldown': self.default_cooldown,
            'max_executions_per_day': self.max_executions_per_day,
            'log_level': self.log_level,
            'storage_path': self.storage_path
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AutomationConfig':
        """从字典创建配置"""
        return cls(
            enabled=data.get('enabled', True),
            max_parallel_executions=data.get('max_parallel_executions', 5),
            default_cooldown=data.get('default_cooldown', 300),
            max_executions_per_day=data.get('max_executions_per_day', 100),
            log_level=data.get('log_level', 'INFO'),
            storage_path=data.get('storage_path', 'automation')
        )
