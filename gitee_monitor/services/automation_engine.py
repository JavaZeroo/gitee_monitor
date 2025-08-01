"""
自动化引擎模块，处理自动化规则的执行和管理
"""
import re
import time
import asyncio
import logging
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import requests
import json

from ..models.automation import (
    AutomationRule, Condition, Action, ExecutionRecord, AutomationConfig,
    TriggerType, ConditionType, ActionType, OperatorType
)
from ..api.base_api import BaseAPIClient

logger = logging.getLogger(__name__)


class ConditionEvaluator:
    """条件评估器"""
    
    @staticmethod
    def evaluate(condition: Condition, pr_data: dict, context: dict = None) -> bool:
        """
        评估单个条件
        
        Args:
            condition: 条件对象
            pr_data: PR数据
            context: 上下文数据
            
        Returns:
            条件是否满足
        """
        try:
            field_value = ConditionEvaluator._get_field_value(condition, pr_data, context)
            return ConditionEvaluator._compare_values(
                condition.operator, field_value, condition.value
            )
        except Exception as e:
            logger.error(f"条件评估失败: {condition.type}, 错误: {e}")
            return False
    
    @staticmethod
    def _get_field_value(condition: Condition, pr_data: dict, context: dict = None) -> Any:
        """获取字段值"""
        condition_type = condition.type
        
        if condition_type == ConditionType.HAS_LABEL.value:
            labels = pr_data.get('labels', [])
            return [label.get('name', '') for label in labels]
        
        elif condition_type == ConditionType.NOT_HAS_LABEL.value:
            labels = pr_data.get('labels', [])
            return [label.get('name', '') for label in labels]
        
        elif condition_type == ConditionType.STATUS_IS.value:
            return pr_data.get('state', '')
        
        elif condition_type == ConditionType.STATUS_NOT.value:
            return pr_data.get('state', '')
        
        elif condition_type == ConditionType.AUTHOR_IS.value:
            return pr_data.get('user', {}).get('login', '')
        
        elif condition_type == ConditionType.AUTHOR_NOT.value:
            return pr_data.get('user', {}).get('login', '')
        
        elif condition_type == ConditionType.PLATFORM_IS.value:
            return context.get('platform', '') if context else ''
        
        elif condition_type == ConditionType.REPO_IS.value:
            return f"{pr_data.get('base', {}).get('repo', {}).get('full_name', '')}"
        
        elif condition_type == ConditionType.BRANCH_MATCHES.value:
            return pr_data.get('head', {}).get('ref', '')
        
        elif condition_type == ConditionType.TITLE_CONTAINS.value:
            return pr_data.get('title', '')
        
        elif condition_type == ConditionType.BODY_CONTAINS.value:
            return pr_data.get('body', '') or ''
        
        elif condition_type == ConditionType.IS_DRAFT.value:
            return pr_data.get('draft', False)
        
        elif condition_type == ConditionType.IS_NOT_DRAFT.value:
            return pr_data.get('draft', False)
        
        elif condition_type == ConditionType.TIME_RANGE.value:
            return datetime.now().time()
        
        else:
            # 使用字段名直接获取值
            if condition.field:
                return pr_data.get(condition.field, '')
            return ''
    
    @staticmethod
    def _compare_values(operator: str, field_value: Any, condition_value: Any) -> bool:
        """比较值"""
        if operator == OperatorType.EQUALS.value:
            return field_value == condition_value
        
        elif operator == OperatorType.NOT_EQUALS.value:
            return field_value != condition_value
        
        elif operator == OperatorType.CONTAINS.value:
            if isinstance(field_value, (list, tuple)):
                return condition_value in field_value
            elif isinstance(field_value, str):
                return condition_value in field_value
            return False
        
        elif operator == OperatorType.NOT_CONTAINS.value:
            if isinstance(field_value, (list, tuple)):
                return condition_value not in field_value
            elif isinstance(field_value, str):
                return condition_value not in field_value
            return True
        
        elif operator == OperatorType.IN.value:
            if isinstance(condition_value, (list, tuple)):
                return field_value in condition_value
            return False
        
        elif operator == OperatorType.NOT_IN.value:
            if isinstance(condition_value, (list, tuple)):
                return field_value not in condition_value
            return True
        
        elif operator == OperatorType.MATCHES.value:
            if isinstance(field_value, str):
                return bool(re.search(condition_value, field_value))
            return False
        
        elif operator == OperatorType.NOT_MATCHES.value:
            if isinstance(field_value, str):
                return not bool(re.search(condition_value, field_value))
            return True
        
        elif operator == OperatorType.GREATER_THAN.value:
            try:
                return float(field_value) > float(condition_value)
            except (ValueError, TypeError):
                return False
        
        elif operator == OperatorType.LESS_THAN.value:
            try:
                return float(field_value) < float(condition_value)
            except (ValueError, TypeError):
                return False
        
        elif operator == OperatorType.GREATER_EQUAL.value:
            try:
                return float(field_value) >= float(condition_value)
            except (ValueError, TypeError):
                return False
        
        elif operator == OperatorType.LESS_EQUAL.value:
            try:
                return float(field_value) <= float(condition_value)
            except (ValueError, TypeError):
                return False
        
        return False


class ActionExecutor:
    """动作执行器"""
    
    def __init__(self, api_clients: Dict[str, BaseAPIClient]):
        self.api_clients = api_clients
    
    async def execute(self, action: Action, pr_data: dict, context: dict = None) -> bool:
        """
        执行单个动作
        
        Args:
            action: 动作对象
            pr_data: PR数据
            context: 上下文数据
            
        Returns:
            执行是否成功
        """
        try:
            if action.delay > 0:
                logger.info(f"延迟 {action.delay} 秒执行动作: {action.type}")
                await asyncio.sleep(action.delay)
            
            success = await self._execute_action(action, pr_data, context)
            
            if not success and action.retry_count > 0:
                for retry in range(action.retry_count):
                    logger.info(f"重试执行动作 {action.type}, 第 {retry + 1} 次")
                    await asyncio.sleep(action.retry_interval)
                    success = await self._execute_action(action, pr_data, context)
                    if success:
                        break
            
            return success
            
        except Exception as e:
            logger.error(f"执行动作失败: {action.type}, 错误: {e}")
            return False
    
    async def _execute_action(self, action: Action, pr_data: dict, context: dict = None) -> bool:
        """执行具体动作"""
        action_type = action.type
        platform = context.get('platform', 'gitee') if context else 'gitee'
        api_client = self.api_clients.get(platform)
        
        if not api_client:
            logger.error(f"平台 {platform} 的API客户端不存在")
            return False
        
        try:
            if action_type == ActionType.COMMENT.value:
                return await self._execute_comment(action, pr_data, api_client, context)
            
            elif action_type == ActionType.ADD_LABEL.value:
                return await self._execute_add_label(action, pr_data, api_client, context)
            
            elif action_type == ActionType.REMOVE_LABEL.value:
                return await self._execute_remove_label(action, pr_data, api_client, context)
            
            elif action_type == ActionType.CLOSE_PR.value:
                return await self._execute_close_pr(action, pr_data, api_client, context)
            
            elif action_type == ActionType.WEBHOOK.value:
                return await self._execute_webhook(action, pr_data, context)
            
            elif action_type == ActionType.LOG.value:
                return await self._execute_log(action, pr_data, context)
            
            else:
                logger.warning(f"不支持的动作类型: {action_type}")
                return False
                
        except Exception as e:
            logger.error(f"执行动作 {action_type} 失败: {e}")
            return False
    
    async def _execute_comment(self, action: Action, pr_data: dict, api_client: BaseAPIClient, context: dict) -> bool:
        """执行评论动作"""
        message = action.parameters.get('message', '')
        if not message:
            logger.error("评论消息不能为空")
            return False
        
        # 替换模板变量
        message = self._replace_template_variables(message, pr_data, context)
        
        owner = pr_data.get('base', {}).get('repo', {}).get('owner', {}).get('login', '')
        repo = pr_data.get('base', {}).get('repo', {}).get('name', '')
        pr_number = pr_data.get('number', 0)
        
        if not all([owner, repo, pr_number]):
            logger.error("缺少PR信息，无法添加评论")
            return False
        
        try:
            result = api_client.add_pr_comment(owner, repo, pr_number, message)
            logger.info(f"成功添加评论到 PR {owner}/{repo}#{pr_number}: {message}")
            return result is not None
        except Exception as e:
            logger.error(f"添加评论失败: {e}")
            return False
    
    async def _execute_add_label(self, action: Action, pr_data: dict, api_client: BaseAPIClient, context: dict) -> bool:
        """执行添加标签动作"""
        labels = action.parameters.get('labels', [])
        if not labels:
            logger.error("标签列表不能为空")
            return False
        
        owner = pr_data.get('base', {}).get('repo', {}).get('owner', {}).get('login', '')
        repo = pr_data.get('base', {}).get('repo', {}).get('name', '')
        pr_number = pr_data.get('number', 0)
        
        try:
            result = await api_client.add_pr_labels(owner, repo, pr_number, labels)
            logger.info(f"成功添加标签到 PR {owner}/{repo}#{pr_number}: {labels}")
            return result is not None
        except Exception as e:
            logger.error(f"添加标签失败: {e}")
            return False
    
    async def _execute_remove_label(self, action: Action, pr_data: dict, api_client: BaseAPIClient, context: dict) -> bool:
        """执行移除标签动作"""
        labels = action.parameters.get('labels', [])
        if not labels:
            logger.error("标签列表不能为空")
            return False
        
        owner = pr_data.get('base', {}).get('repo', {}).get('owner', {}).get('login', '')
        repo = pr_data.get('base', {}).get('repo', {}).get('name', '')
        pr_number = pr_data.get('number', 0)
        
        try:
            for label in labels:
                await api_client.remove_pr_label(owner, repo, pr_number, label)
            logger.info(f"成功移除标签从 PR {owner}/{repo}#{pr_number}: {labels}")
            return True
        except Exception as e:
            logger.error(f"移除标签失败: {e}")
            return False
    
    async def _execute_close_pr(self, action: Action, pr_data: dict, api_client: BaseAPIClient, context: dict) -> bool:
        """执行关闭PR动作"""
        owner = pr_data.get('base', {}).get('repo', {}).get('owner', {}).get('login', '')
        repo = pr_data.get('base', {}).get('repo', {}).get('name', '')
        pr_number = pr_data.get('number', 0)
        
        try:
            result = api_client.close_pr(owner, repo, pr_number)
            logger.info(f"成功关闭 PR {owner}/{repo}#{pr_number}")
            return result is not None
        except Exception as e:
            logger.error(f"关闭PR失败: {e}")
            return False
    
    async def _execute_webhook(self, action: Action, pr_data: dict, context: dict) -> bool:
        """执行webhook动作"""
        url = action.parameters.get('url', '')
        method = action.parameters.get('method', 'POST').upper()
        headers = action.parameters.get('headers', {})
        payload = action.parameters.get('payload', {})
        
        if not url:
            logger.error("Webhook URL不能为空")
            return False
        
        # 替换模板变量
        payload_str = json.dumps(payload)
        payload_str = self._replace_template_variables(payload_str, pr_data, context)
        payload = json.loads(payload_str)
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=payload, timeout=30)
            else:
                response = requests.request(method, url, headers=headers, json=payload, timeout=30)
            
            response.raise_for_status()
            logger.info(f"Webhook调用成功: {method} {url}, 状态码: {response.status_code}")
            return True
        except Exception as e:
            logger.error(f"Webhook调用失败: {e}")
            return False
    
    async def _execute_log(self, action: Action, pr_data: dict, context: dict) -> bool:
        """执行日志动作"""
        message = action.parameters.get('message', '')
        level = action.parameters.get('level', 'INFO').upper()
        
        # 替换模板变量
        message = self._replace_template_variables(message, pr_data, context)
        
        if level == 'DEBUG':
            logger.debug(message)
        elif level == 'INFO':
            logger.info(message)
        elif level == 'WARNING':
            logger.warning(message)
        elif level == 'ERROR':
            logger.error(message)
        else:
            logger.info(message)
        
        return True
    
    def _replace_template_variables(self, text: str, pr_data: dict, context: dict) -> str:
        """替换模板变量"""
        variables = {
            '{{pr.number}}': str(pr_data.get('number', '')),
            '{{pr.title}}': pr_data.get('title', ''),
            '{{pr.author}}': pr_data.get('user', {}).get('login', ''),
            '{{pr.state}}': pr_data.get('state', ''),
            '{{pr.url}}': pr_data.get('html_url', ''),
            '{{repo.full_name}}': pr_data.get('base', {}).get('repo', {}).get('full_name', ''),
            '{{repo.name}}': pr_data.get('base', {}).get('repo', {}).get('name', ''),
            '{{repo.owner}}': pr_data.get('base', {}).get('repo', {}).get('owner', {}).get('login', ''),
            '{{branch.head}}': pr_data.get('head', {}).get('ref', ''),
            '{{branch.base}}': pr_data.get('base', {}).get('ref', ''),
            '{{platform}}': context.get('platform', '') if context else '',
            '{{timestamp}}': datetime.now().isoformat(),
        }
        
        for var, value in variables.items():
            text = text.replace(var, str(value))
        
        return text


class AutomationEngine:
    """自动化引擎"""
    
    def __init__(self, api_clients: Dict[str, BaseAPIClient], config_manager, automation_config: AutomationConfig = None):
        """
        初始化自动化引擎
        
        Args:
            api_clients: API客户端字典
            config_manager: 配置管理器实例
            automation_config: 自动化配置
        """
        self.api_clients = api_clients
        self.config_manager = config_manager
        
        # 从配置管理器获取自动化配置
        automation_config_dict = config_manager.get_automation_config()
        self.config = automation_config or AutomationConfig.from_dict(automation_config_dict)
        
        self.rules: List[AutomationRule] = []
        self.execution_history: List[ExecutionRecord] = []
        self.condition_evaluator = ConditionEvaluator()
        self.action_executor = ActionExecutor(api_clients)
        self.thread_pool = ThreadPoolExecutor(max_workers=self.config.max_parallel_executions)
        self._lock = threading.Lock()
        
        # 加载规则
        self.load_rules()
    
    def add_rule(self, rule: AutomationRule) -> bool:
        """
        添加自动化规则
        
        Args:
            rule: 自动化规则
            
        Returns:
            是否添加成功
        """
        with self._lock:
            # 检查规则ID是否已存在
            if any(r.id == rule.id for r in self.rules):
                logger.error(f"规则ID已存在: {rule.id}")
                return False
            
            self.rules.append(rule)
            self.save_rules()
            logger.info(f"添加自动化规则: {rule.name} ({rule.id})")
            return True
    
    def update_rule(self, rule: AutomationRule) -> bool:
        """
        更新自动化规则
        
        Args:
            rule: 自动化规则
            
        Returns:
            是否更新成功
        """
        with self._lock:
            for i, existing_rule in enumerate(self.rules):
                if existing_rule.id == rule.id:
                    rule.updated_at = datetime.now()
                    self.rules[i] = rule
                    self.save_rules()
                    logger.info(f"更新自动化规则: {rule.name} ({rule.id})")
                    return True
            
            logger.error(f"未找到要更新的规则: {rule.id}")
            return False
    
    def remove_rule(self, rule_id: str) -> bool:
        """
        移除自动化规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            是否移除成功
        """
        with self._lock:
            for i, rule in enumerate(self.rules):
                if rule.id == rule_id:
                    removed_rule = self.rules.pop(i)
                    self.save_rules()
                    logger.info(f"移除自动化规则: {removed_rule.name} ({rule_id})")
                    return True
            
            logger.error(f"未找到要移除的规则: {rule_id}")
            return False
    
    def get_rule(self, rule_id: str) -> Optional[AutomationRule]:
        """获取规则"""
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        return None
    
    def get_rules(self, enabled_only: bool = False) -> List[AutomationRule]:
        """获取规则列表"""
        if enabled_only:
            return [rule for rule in self.rules if rule.enabled]
        return self.rules.copy()
    
    def process_event(self, event_type: str, pr_data: dict, context: dict = None) -> List[str]:
        """
        处理事件，执行匹配的规则
        
        Args:
            event_type: 事件类型
            pr_data: PR数据
            context: 上下文数据
            
        Returns:
            执行的规则ID列表
        """
        if not self.config.enabled:
            return []
        
        context = context or {}
        executed_rules = []
        
        # 按优先级排序规则
        sorted_rules = sorted(
            [rule for rule in self.rules if rule.enabled],
            key=lambda r: r.priority,
            reverse=True        )
        
        for rule in sorted_rules:
            if self._should_execute_rule(rule, event_type, pr_data, context):
                self.thread_pool.submit(self._execute_rule_sync, rule, pr_data, context)
                executed_rules.append(rule.id)
        
        return executed_rules
    
    def _should_execute_rule(self, rule: AutomationRule, event_type: str, pr_data: dict, context: dict) -> bool:
        """检查是否应该执行规则"""
        # 检查触发器
        if rule.trigger != event_type:
            return False
        
        # 检查条件
        for condition in rule.conditions:
            if not self.condition_evaluator.evaluate(condition, pr_data, context):
                return False
        
        # 检查时间范围
        if rule.time_range:
            current_time = datetime.now().time()
            if not (rule.time_range.start <= current_time <= rule.time_range.end):
                return False
        
        # 检查冷却时间
        if rule.cooldown > 0 and rule.last_executed:
            elapsed = (datetime.now() - rule.last_executed).total_seconds()
            if elapsed < rule.cooldown:
                return False
        
        # 检查每日执行次数限制
        if rule.max_executions_per_day:
            today_executions = self._get_today_executions(rule.id)
            if today_executions >= rule.max_executions_per_day:
                return False
        
        return True
    
    def _execute_rule_sync(self, rule: AutomationRule, pr_data: dict, context: dict):
        """同步执行规则（在线程池中运行）"""
        asyncio.run(self._execute_rule(rule, pr_data, context))
    
    async def _execute_rule(self, rule: AutomationRule, pr_data: dict, context: dict):
        """执行规则"""
        start_time = time.time()
        executed_actions = []
        success = True
        error_message = None
        
        try:
            logger.info(f"执行自动化规则: {rule.name} ({rule.id})")
            
            for action in rule.actions:
                action_success = await self.action_executor.execute(action, pr_data, context)
                executed_actions.append(f"{action.type}:{action_success}")
                
                if not action_success:
                    success = False
                    logger.error(f"规则 {rule.id} 中的动作 {action.type} 执行失败")
        
        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"执行规则 {rule.id} 失败: {e}")
          # 更新规则统计
        with self._lock:
            rule.update_statistics(success)
        
        # 记录执行历史
        execution_time = time.time() - start_time
        record = ExecutionRecord(
            rule_id=rule.id,
            executed_at=datetime.now(),
            pr_info={
                'platform': context.get('platform', ''),
                'repo': pr_data.get('base', {}).get('repo', {}).get('full_name', ''),
                'pr_number': pr_data.get('number', 0),
                'title': pr_data.get('title', ''),
                'author': pr_data.get('user', {}).get('login', '')
            },
            actions_executed=executed_actions,
            success=success,
            error_message=error_message,
            execution_time=execution_time
        )
        
        with self._lock:
            self.execution_history.append(record)
            # 保持历史记录在合理范围内
            if len(self.execution_history) > 1000:
                self.execution_history = self.execution_history[-800:]
        
        self.save_rules()
        
        if success:
            logger.info(f"规则 {rule.name} 执行成功，耗时 {execution_time:.2f} 秒")
        else:
            logger.error(f"规则 {rule.name} 执行失败: {error_message}")
    
    def _get_today_executions(self, rule_id: str) -> int:
        """获取今日执行次数"""
        today = datetime.now().date()
        count = 0
        for record in self.execution_history:
            if record.rule_id == rule_id and record.executed_at.date() == today:
                count += 1
        return count
    
    def get_execution_history(self, rule_id: str = None, limit: int = 100) -> List[ExecutionRecord]:
        """获取执行历史"""
        history = self.execution_history
        if rule_id:
            history = [record for record in history if record.rule_id == rule_id]
        return history[-limit:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_rules = len(self.rules)
        enabled_rules = len([rule for rule in self.rules if rule.enabled])
        total_executions = sum(rule.execution_count for rule in self.rules)
        total_successes = sum(rule.success_count for rule in self.rules)
        
        return {
            'total_rules': total_rules,
            'enabled_rules': enabled_rules,
            'total_executions': total_executions,
            'total_successes': total_successes,
            'success_rate': total_successes / total_executions if total_executions > 0 else 0,
            'execution_history_count': len(self.execution_history)
        }
    
    def save_rules(self):
        """保存规则到配置文件"""
        try:
            rules_data = [rule.to_dict() for rule in self.rules]
            self.config_manager.set_automation_rules(rules_data)
            self.config_manager.save_config()
            logger.debug("规则已保存到配置文件")
        except Exception as e:
            logger.error(f"保存规则失败: {e}")
    
    def load_rules(self):
        """从配置文件加载规则"""
        try:
            rules_data = self.config_manager.get_automation_rules()
            
            if not rules_data:
                logger.info("配置文件中没有规则，创建默认规则")
                self._create_default_rules()
                return
            
            self.rules = [AutomationRule.from_dict(rule_data) for rule_data in rules_data]
            logger.info(f"从配置文件加载了 {len(self.rules)} 个自动化规则")
            
        except Exception as e:
            logger.error(f"加载规则失败: {e}")
            self.rules = []
    
    def _create_default_rules(self):
        """创建默认规则"""
        # 新PR自动构建规则
        build_rule = AutomationRule(
            id="auto-build-new-pr",
            name="新PR自动构建",
            description="当有新PR添加时自动触发构建",
            trigger=TriggerType.PR_ADDED.value,
            conditions=[
                Condition(
                    type=ConditionType.PLATFORM_IS.value,
                    operator=OperatorType.EQUALS.value,
                    value="gitee"
                )
            ],
            actions=[
                Action(
                    type=ActionType.COMMENT.value,
                    parameters={"message": "/build"}
                )
            ],
            enabled=False  # 默认禁用，需要用户手动启用
        )
        
        # 失败流水线重试规则
        retest_rule = AutomationRule(
            id="retest-failed-pipeline",
            name="失败流水线重试",
            description="检测到pipeline-failed标签时自动重试",
            trigger=TriggerType.LABEL_CHANGED.value,
            conditions=[
                Condition(
                    type=ConditionType.HAS_LABEL.value,
                    operator=OperatorType.CONTAINS.value,
                    value="pipeline-failed"
                )
            ],
            actions=[
                Action(
                    type=ActionType.COMMENT.value,
                    parameters={"message": "/retest"},
                    delay=300  # 延迟5分钟
                )
            ],
            cooldown=3600,  # 1小时冷却时间
            max_executions_per_day=3,
            enabled=False
        )
        
        self.rules = [build_rule, retest_rule]
        self.save_rules()
        logger.info("创建了默认自动化规则")
    
    def shutdown(self):
        """关闭自动化引擎"""
        logger.info("正在关闭自动化引擎...")
        self.thread_pool.shutdown(wait=True)
        self.save_rules()
        logger.info("自动化引擎已关闭")
