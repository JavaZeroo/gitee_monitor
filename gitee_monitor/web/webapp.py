"""
Flask Web 应用模块，处理 Web 界面和 API 请求
"""
import logging
import re
import json
from flask import Flask, request, render_template, redirect, url_for, jsonify, Response

from ..config.config_manager import Config
from ..services.pr_monitor import PRMonitor

logger = logging.getLogger(__name__)

class WebApp:
    """Flask Web 应用，处理 Web 界面和 API 请求"""
    
    def __init__(self, config: Config, pr_monitor: PRMonitor):
        """
        初始化 Web 应用
        
        Args:
            config: 配置管理器
            pr_monitor: PR 监控服务
        """
        self.config = config
        self.pr_monitor = pr_monitor
        self.app = Flask(__name__, 
                         template_folder='../../templates',
                         static_folder='../../static')
        self._register_routes()
        
    def _register_routes(self) -> None:
        """注册路由"""
        # 主页
        @self.app.route('/')
        def index():
            # 不再预加载PR数据，改为使用流式加载
            return render_template('index.html', pr_data={})
        
        # 配置页面
        @self.app.route('/config', methods=['GET', 'POST'])
        def config_page():
            error = None
            if request.method == 'POST':
                action = request.form.get('action')
                if action == 'update_api':
                    if not request.form.get('access_token'):
                        error = 'ACCESS_TOKEN 是必填的！'
                    else:
                        self.config.update({
                            "ACCESS_TOKEN": request.form.get('access_token')
                        })
                        self.config.save_config()
                        logger.info("API 配置更新完成")
                elif action == 'add_pr':
                    pr_url = request.form.get('pr_url', '').strip()
                    
                    if not pr_url:
                        error = '请输入有效的 PR URL！'
                    else:
                        # 使用正则表达式解析 PR URL
                        pattern = r'https://gitee\.com/([^/]+)/([^/]+)/pulls/(\d+)'
                        match = re.match(pattern, pr_url)
                        
                        if not match:
                            error = 'URL 格式不正确！请使用格式：https://gitee.com/{owner}/{repo}/pulls/{pr_id}'
                        else:
                            owner = match.group(1)
                            repo = match.group(2)
                            pr_id = int(match.group(3))
                            
                            self.config.add_pr(owner, repo, pr_id)
                            self.config.save_config()
                            logger.info(f"通过 URL 添加 PR #{pr_id} ({owner}/{repo}) 到监控列表")
                elif action == 'add_followed_author':
                    platform = request.form.get('platform', '').strip()
                    author = request.form.get('author', '').strip()
                    repo = request.form.get('repo', '').strip()
                    
                    if not platform or not author or not repo:
                        error = '平台、作者和仓库都是必填的！'
                    else:
                        # 验证仓库格式
                        if '/' not in repo:
                            error = '仓库格式不正确，应为 owner/repo 格式'
                        else:
                            self.config.add_followed_author(author, repo, platform)
                            self.config.save_config()
                            logger.info(f"通过表单添加关注作者 {author} 的仓库 {repo} (平台: {platform})")
                if error:
                    return render_template('config.html', config=self.config, error=error)
                return redirect(url_for('config_page'))
            
            if request.args.get('action') == 'delete_pr':
                platform = request.args.get('platform', 'gitee')  # 默认为gitee
                owner = request.args.get('owner')
                repo = request.args.get('repo')
                pr_id = request.args.get('pr_id')
                
                if owner and repo and pr_id and pr_id.isdigit():
                    pr_id = int(pr_id)
                    self.config.remove_pr(owner, repo, pr_id, platform)
                    self.config.save_config()
                    logger.info(f"删除 {platform.upper()} PR #{pr_id} ({owner}/{repo}) 从监控列表")
                return redirect(url_for('config_page'))
                
            if request.args.get('action') == 'delete_followed_author':
                author = request.args.get('author')
                repo = request.args.get('repo')
                
                if author and repo:
                    self.config.remove_followed_author(author, repo)
                    self.config.save_config()
                    logger.info(f"删除关注作者 {author} 的仓库 {repo}")
                return redirect(url_for('config_page'))
            
            return render_template('config.html', config=self.config, error=None)
        
        # Webhook 端点
        @self.app.route('/webhook', methods=['POST'])
        def webhook():
            data = request.json
            if not data:
                return "无效的 Webhook 数据", 400
            
            event = request.headers.get('X-Gitee-Event')
            if event == 'pull_request':
                pr_data = data.get('pull_request', {})
                pr_id = pr_data.get('number')
                repo_data = pr_data.get('base', {}).get('repo', {})
                owner = repo_data.get('owner', {}).get('login', '')
                repo = repo_data.get('name', '')
                
                # 检查是否在监控列表中
                is_monitored = False
                for pr_config in self.config.get_pr_lists():
                    if (pr_config.get("OWNER") == owner and 
                        pr_config.get("REPO") == repo and 
                        pr_config.get("PULL_REQUEST_ID") == pr_id):
                        is_monitored = True
                        break
                
                if is_monitored:
                    labels = pr_data.get('labels', [])
                    logger.info(f"通过 Webhook 收到 PR #{pr_id} ({owner}/{repo}) 标签更新: {[label.get('name', '') for label in labels]}")
            else:
                logger.info(f"收到非 PR 事件: {event}")
            
            return "Webhook 收到", 200
        
        # PR 标签 API 端点
        @self.app.route('/api/pr_labels', methods=['GET'])
        def api_pr_labels():
            force_refresh = request.args.get('refresh', '').lower() == 'true'
            pr_data = {}
            
            for pr_config in self.config.get_pr_lists():
                owner = pr_config.get("OWNER")
                repo = pr_config.get("REPO")
                pr_id = pr_config.get("PULL_REQUEST_ID")
                
                if owner and repo and pr_id:
                    cache_key = f"{owner}/{repo}#{pr_id}"
                    labels = self.pr_monitor.get_pr_labels(owner, repo, pr_id, force_refresh=force_refresh)
                    pr_details = self.pr_monitor.get_pr_details(owner, repo, pr_id, force_refresh=force_refresh)
                    
                    pr_data[cache_key] = {
                        "current_labels": labels,  # 传递完整的标签对象，包含颜色信息
                        "owner": owner,
                        "repo": repo,
                        "pr_id": pr_id,
                        "pr_details": pr_details.to_dict() if pr_details else None  # 使用PullRequest对象的to_dict方法
                    }
            return jsonify(pr_data)
        
        # 新的流式PR标签API端点，支持逐个返回PR数据
        @self.app.route('/api/pr_labels_stream', methods=['GET'])
        def api_pr_labels_stream():
            force_refresh = request.args.get('refresh', '').lower() == 'true'
            
            def generate():
                pr_configs = self.config.get_pr_lists()
                total_prs = len(pr_configs)
                processed = 0
                
                # 发送开始事件
                yield f"event: start\ndata: {json.dumps({'total': total_prs})}\n\n"
                
                for pr_config in pr_configs:
                    platform = pr_config.get("PLATFORM", "gitee")  # 默认为gitee
                    owner = pr_config.get("OWNER")
                    repo = pr_config.get("REPO")
                    pr_id = pr_config.get("PULL_REQUEST_ID")
                    
                    if owner and repo and pr_id:
                        try:
                            cache_key = f"{platform}:{owner}/{repo}#{pr_id}"
                            labels = self.pr_monitor.get_pr_labels(platform, owner, repo, pr_id, force_refresh=force_refresh)
                            pr_details = self.pr_monitor.get_pr_details(platform, owner, repo, pr_id, force_refresh=force_refresh)
                            
                            pr_data = {
                                "cache_key": cache_key,
                                "platform": platform,
                                "current_labels": labels,
                                "owner": owner,
                                "repo": repo,
                                "pr_id": pr_id,
                                "pr_details": pr_details.to_dict() if pr_details else None
                            }
                            
                            # 发送PR数据事件
                            yield f"event: pr_data\ndata: {json.dumps(pr_data)}\n\n"
                            
                        except Exception as e:
                            # 发送错误事件
                            error_data = {
                                "cache_key": f"{platform}:{owner}/{repo}#{pr_id}",
                                "platform": platform,
                                "error": str(e),
                                "owner": owner,
                                "repo": repo,
                                "pr_id": pr_id
                            }
                            yield f"event: pr_error\ndata: {json.dumps(error_data)}\n\n"
                            logger.error(f"获取{platform.upper()}PR数据失败 {owner}/{repo}#{pr_id}: {e}")
                    
                    processed += 1
                    # 发送进度事件
                    progress_data = {
                        "processed": processed,
                        "total": total_prs,
                        "percentage": round((processed / total_prs) * 100, 1) if total_prs > 0 else 100
                    }
                    yield f"event: progress\ndata: {json.dumps(progress_data)}\n\n"
                
                # 发送完成事件
                yield f"event: complete\ndata: {json.dumps({'message': 'All PR data loaded'})}\n\n"
            
            return Response(generate(), mimetype='text/event-stream',
                          headers={
                              'Cache-Control': 'no-cache',
                              'Connection': 'keep-alive',
                              'Access-Control-Allow-Origin': '*'
                          })
        
        # 添加 PR API 端点
        @self.app.route('/api/add_pr', methods=['POST'])
        def api_add_pr():
            data = request.get_json()
            pr_url = data.get('pr_url', '').strip()
            
            if not pr_url:
                return jsonify({'success': False, 'error': '请输入有效的 PR URL！'}), 400
            
            # 解析不同平台的 PR URL
            platform = None
            owner = None
            repo = None
            pr_id = None
            
            # Gitee URL 格式: https://gitee.com/{owner}/{repo}/pulls/{pr_id}
            gitee_pattern = r'https://gitee\.com/([^/]+)/([^/]+)/pulls/(\d+)'
            gitee_match = re.match(gitee_pattern, pr_url)
            
            # GitHub URL 格式: https://github.com/{owner}/{repo}/pull/{pr_id}
            github_pattern = r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)'
            github_match = re.match(github_pattern, pr_url)
            
            if gitee_match:
                platform = "gitee"
                owner = gitee_match.group(1)
                repo = gitee_match.group(2)
                pr_id = int(gitee_match.group(3))
            elif github_match:
                platform = "github"
                owner = github_match.group(1)
                repo = github_match.group(2)
                pr_id = int(github_match.group(3))
            else:
                return jsonify({
                    'success': False, 
                    'error': 'URL 格式不正确！支持的格式：\n- Gitee: https://gitee.com/{owner}/{repo}/pulls/{pr_id}\n- GitHub: https://github.com/{owner}/{repo}/pull/{pr_id}'
                }), 400
            
            self.config.add_pr(owner, repo, pr_id, platform)
            self.config.save_config()
            logger.info(f"通过 API 添加 {platform.upper()} PR #{pr_id} ({owner}/{repo}) 到监控列表")
            
            # 获取新添加PR的标签信息
            try:
                labels = self.pr_monitor.get_pr_labels(platform, owner, repo, pr_id)
                pr_details = self.pr_monitor.get_pr_details(platform, owner, repo, pr_id)
                current_labels = labels  # 传递完整的标签对象
            except Exception as e:
                logger.warning(f"获取新添加{platform.upper()}PR的信息失败: {e}")
                current_labels = []
                pr_details = None
            
            return jsonify({
                'success': True, 
                'message': f'{platform.upper()} PR 添加成功',
                'pr_data': {
                    'platform': platform,
                    'owner': owner,
                    'repo': repo,
                    'pr_id': pr_id,
                    'current_labels': current_labels,
                    'pr_details': pr_details.to_dict() if pr_details else None,
                    'cache_key': f"{platform}:{owner}/{repo}#{pr_id}"
                }
            })
        
        # 删除 PR API 端点
        @self.app.route('/api/delete_pr', methods=['DELETE'])
        def api_delete_pr():
            data = request.get_json()
            platform = data.get('platform', 'gitee')  # 默认为gitee
            owner = data.get('owner')
            repo = data.get('repo')
            pr_id = data.get('pr_id')
            
            if not owner or not repo or not pr_id:
                return jsonify({'success': False, 'error': '缺少必要参数'}), 400
            
            try:
                pr_id = int(pr_id)
                self.config.remove_pr(owner, repo, pr_id, platform)
                self.config.save_config()
                logger.info(f"通过 API 删除 {platform.upper()} PR #{pr_id} ({owner}/{repo}) 从监控列表")
                return jsonify({'success': True, 'message': f'{platform.upper()} PR 删除成功'})
            except ValueError:
                return jsonify({'success': False, 'error': 'PR ID 必须是数字'}), 400
        
        # 更新API配置 API 端点
        @self.app.route('/api/update_api', methods=['POST'])
        def api_update_api():
            data = request.get_json()
            gitee_access_token = data.get('gitee_access_token', '').strip()
            github_access_token = data.get('github_access_token', '').strip()
            
            if not gitee_access_token and not github_access_token:
                return jsonify({'success': False, 'error': '至少需要配置一个平台的访问令牌！'}), 400
            
            # 更新配置
            config_updates = {}
            if gitee_access_token:
                config_updates["ACCESS_TOKEN"] = gitee_access_token
            if github_access_token:
                config_updates["GITHUB_ACCESS_TOKEN"] = github_access_token
                
            self.config.update(config_updates)
            self.config.save_config()
            logger.info("通过 API 更新多平台 API 配置")
            
            return jsonify({'success': True, 'message': 'API 配置更新成功'})
            
        # 获取关注作者的PR列表 API 端点
        @self.app.route('/api/followed_author_prs', methods=['GET'])
        def api_followed_author_prs():
            force_refresh = request.args.get('force_refresh', '').lower() == 'true'
            # 获取关注作者的PR并自动添加到监控列表
            prs = self.pr_monitor.get_followed_author_prs(force_refresh=force_refresh, auto_add_to_monitor=True)
            # 将PullRequest对象转换为字典格式
            prs_data = [pr.to_dict() for pr in prs]
            return jsonify(prs_data)
        
        # 添加关注作者 API 端点
        @self.app.route('/api/add_followed_author', methods=['POST'])
        def api_add_followed_author():
            data = request.get_json()
            platform = data.get('platform', '').strip()
            author = data.get('author', '').strip()
            repo = data.get('repo', '').strip()
            
            if not platform or not author or not repo:
                return jsonify({'success': False, 'error': '平台、作者和仓库都是必填的！'}), 400
            
            # 验证仓库格式
            if '/' not in repo:
                return jsonify({'success': False, 'error': '仓库格式不正确，应为 owner/repo 格式'}), 400
                
            self.config.add_followed_author(author, repo, platform)
            self.config.save_config()
            logger.info(f"通过 API 添加关注作者 {author} 的仓库 {repo} (平台: {platform})")
            
            # 获取新添加作者的PR列表
            try:
                owner, repo_name = repo.split('/', 1)
                # 使用对应平台的API客户端
                from ..api.api_client_factory import APIClientFactory
                api_client = APIClientFactory.create_client(platform)
                if api_client:
                    prs_data = api_client.get_author_prs(owner, repo_name, author)
                    prs = []
                    if prs_data:
                        prs = [pr_data for pr_data in prs_data]  # 保持原始数据格式
                else:
                    prs = []
            except Exception as e:
                logger.warning(f"获取新添加作者的PR列表失败: {e}")
                prs = []
            
            return jsonify({
                'success': True, 
                'message': '关注作者添加成功',
                'author_data': {
                    'platform': platform,
                    'author': author,
                    'repo': repo,
                    'prs': prs or []
                }
            })
        
        # 删除关注作者 API 端点
        @self.app.route('/api/delete_followed_author', methods=['DELETE'])
        def api_delete_followed_author():
            data = request.get_json()
            platform = data.get('platform', 'gitee')  # 默认为gitee以保持向后兼容
            author = data.get('author')
            repo = data.get('repo')
            
            if not author or not repo:
                return jsonify({'success': False, 'error': '缺少必要参数'}), 400
            
            self.config.remove_followed_author(author, repo, platform)
            self.config.save_config()
            logger.info(f"通过 API 删除关注作者 {author} 的仓库 {repo} (平台: {platform})")
            return jsonify({'success': True, 'message': '关注作者删除成功'})
        
        # 更新性能配置 API 端点
        @self.app.route('/api/update_performance', methods=['POST'])
        def api_update_performance():
            try:
                data = request.get_json()
                
                # 提取性能配置参数
                max_workers = data.get('max_workers')
                rate_limit_per_second = data.get('rate_limit_per_second')
                cache_ttl = data.get('cache_ttl')
                enable_parallel_processing = data.get('enable_parallel_processing')
                poll_interval = data.get('poll_interval')
                
                # 验证参数
                if max_workers is not None:
                    if not isinstance(max_workers, int) or max_workers < 1 or max_workers > 20:
                        return jsonify({'success': False, 'error': '最大并发线程数必须在1-20之间'}), 400
                
                if rate_limit_per_second is not None:
                    if not isinstance(rate_limit_per_second, (int, float)) or rate_limit_per_second < 0.1 or rate_limit_per_second > 10.0:
                        return jsonify({'success': False, 'error': 'API调用速率限制必须在0.1-10.0之间'}), 400
                
                if cache_ttl is not None:
                    if not isinstance(cache_ttl, int) or cache_ttl < 60 or cache_ttl > 3600:
                        return jsonify({'success': False, 'error': '缓存生存时间必须在60-3600秒之间'}), 400
                
                if poll_interval is not None:
                    if not isinstance(poll_interval, int) or poll_interval < 30 or poll_interval > 600:
                        return jsonify({'success': False, 'error': '轮询间隔必须在30-600秒之间'}), 400
                
                # 更新配置
                config_updates = {}
                if max_workers is not None:
                    config_updates['MAX_WORKERS'] = max_workers
                if rate_limit_per_second is not None:
                    config_updates['RATE_LIMIT_PER_SECOND'] = rate_limit_per_second
                if cache_ttl is not None:
                    config_updates['CACHE_TTL'] = cache_ttl
                if enable_parallel_processing is not None:
                    config_updates['ENABLE_PARALLEL_PROCESSING'] = bool(enable_parallel_processing)
                if poll_interval is not None:
                    config_updates['POLL_INTERVAL'] = poll_interval
                
                # 保存配置
                for key, value in config_updates.items():
                    self.config.set(key, value)
                self.config.save_config()
                
                logger.info(f"通过 API 更新性能配置: {config_updates}")
                
                # 检查是否需要重启PR监控服务以应用新配置
                restart_needed = any(key in ['MAX_WORKERS', 'ENABLE_PARALLEL_PROCESSING', 'RATE_LIMIT_PER_SECOND'] 
                                   for key in config_updates.keys())
                
                message = '性能配置更新成功'
                if restart_needed:
                    message += '（部分配置需要重启服务才能生效）'
                
                return jsonify({
                    'success': True, 
                    'message': message,
                    'restart_needed': restart_needed
                })
                
            except Exception as e:
                logger.error(f"更新性能配置时出错: {e}")
                return jsonify({'success': False, 'error': f'更新性能配置失败: {str(e)}'}), 500
        
        # 自动化规则管理页面
        @self.app.route('/automation')
        def automation_page():
            return render_template('automation.html')
        
        # 自动化规则API端点
        @self.app.route('/api/automation/rules', methods=['GET'])
        def api_get_automation_rules():
            try:
                automation_engine = self.pr_monitor.get_automation_engine()
                rules = automation_engine.get_rules()
                rules_data = [rule.to_dict() for rule in rules]
                return jsonify(rules_data)
            except Exception as e:
                logger.error(f"获取自动化规则失败: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/automation/rules', methods=['POST'])
        def api_create_automation_rule():
            try:
                data = request.get_json()
                automation_engine = self.pr_monitor.get_automation_engine()
                
                # 生成规则ID
                import uuid
                rule_id = str(uuid.uuid4())[:8]
                data['id'] = rule_id
                
                from ..models.automation import AutomationRule
                rule = AutomationRule.from_dict(data)
                
                success = automation_engine.add_rule(rule)
                if success:
                    return jsonify({'success': True, 'rule_id': rule_id})
                else:
                    return jsonify({'error': '规则ID已存在'}), 400
                    
            except Exception as e:
                logger.error(f"创建自动化规则失败: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/automation/rules/<rule_id>', methods=['PUT'])
        def api_update_automation_rule(rule_id):
            try:
                data = request.get_json()
                data['id'] = rule_id
                
                automation_engine = self.pr_monitor.get_automation_engine()
                from ..models.automation import AutomationRule
                rule = AutomationRule.from_dict(data)
                
                success = automation_engine.update_rule(rule)
                if success:
                    return jsonify({'success': True})
                else:
                    return jsonify({'error': '规则不存在'}), 404
                    
            except Exception as e:
                logger.error(f"更新自动化规则失败: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/automation/rules/<rule_id>', methods=['DELETE'])
        def api_delete_automation_rule(rule_id):
            try:
                automation_engine = self.pr_monitor.get_automation_engine()
                success = automation_engine.remove_rule(rule_id)
                
                if success:
                    return jsonify({'success': True})
                else:
                    return jsonify({'error': '规则不存在'}), 404
                    
            except Exception as e:
                logger.error(f"删除自动化规则失败: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/automation/rules/<rule_id>/toggle', methods=['POST'])
        def api_toggle_automation_rule(rule_id):
            try:
                automation_engine = self.pr_monitor.get_automation_engine()
                rule = automation_engine.get_rule(rule_id)
                
                if not rule:
                    return jsonify({'error': '规则不存在'}), 404
                
                rule.enabled = not rule.enabled
                success = automation_engine.update_rule(rule)
                
                if success:
                    return jsonify({'success': True, 'enabled': rule.enabled})
                else:
                    return jsonify({'error': '更新规则状态失败'}), 500
                    
            except Exception as e:
                logger.error(f"切换自动化规则状态失败: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/automation/statistics', methods=['GET'])
        def api_get_automation_statistics():
            try:
                automation_engine = self.pr_monitor.get_automation_engine()
                stats = automation_engine.get_statistics()
                return jsonify(stats)
            except Exception as e:
                logger.error(f"获取自动化统计失败: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/automation/history', methods=['GET'])
        def api_get_automation_history():
            try:
                automation_engine = self.pr_monitor.get_automation_engine()
                rule_id = request.args.get('rule_id')
                limit = int(request.args.get('limit', 100))
                
                history = automation_engine.get_execution_history(rule_id, limit)
                history_data = [record.to_dict() for record in history]
                return jsonify(history_data)
            except Exception as e:
                logger.error(f"获取自动化执行历史失败: {e}")
                return jsonify({'error': str(e)}), 500
        
    def run(self, host: str = '0.0.0.0', port: int = 5000, debug: bool = False) -> None:
        """
        运行 Web 应用
        
        Args:
            host: 主机地址
            port: 端口号
            debug: 是否启用调试模式
        """
        self.app.run(host=host, port=port, debug=debug)
