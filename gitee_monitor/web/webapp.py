"""
Flask Web 应用模块，处理 Web 界面和 API 请求
"""
import logging
import re
from flask import Flask, request, render_template, redirect, url_for, jsonify

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
            pr_data = {}
            for pr_config in self.config.get_pr_lists():
                owner = pr_config.get("OWNER")
                repo = pr_config.get("REPO")
                pr_id = pr_config.get("PULL_REQUEST_ID")
                
                if owner and repo and pr_id:
                    cache_key = f"{owner}/{repo}#{pr_id}"
                    labels = self.pr_monitor.get_pr_labels(owner, repo, pr_id)
                    pr_data[cache_key] = {
                        "current_labels": labels,  # 传递完整的标签对象，包含颜色信息
                        "owner": owner,
                        "repo": repo,
                        "pr_id": pr_id
                    }
            return render_template('index.html', pr_data=pr_data)
        
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
                if error:
                    return render_template('config.html', config=self.config, error=error)
                return redirect(url_for('config_page'))
            
            if request.args.get('action') == 'delete_pr':
                owner = request.args.get('owner')
                repo = request.args.get('repo')
                pr_id = request.args.get('pr_id')
                
                if owner and repo and pr_id and pr_id.isdigit():
                    pr_id = int(pr_id)
                    self.config.remove_pr(owner, repo, pr_id)
                    self.config.save_config()
                    logger.info(f"删除 PR #{pr_id} ({owner}/{repo}) 从监控列表")
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
                    pr_data[cache_key] = {
                        "current_labels": labels,  # 传递完整的标签对象，包含颜色信息
                        "owner": owner,
                        "repo": repo,
                        "pr_id": pr_id
                    }
            return jsonify(pr_data)
        
        # 添加 PR API 端点
        @self.app.route('/api/add_pr', methods=['POST'])
        def api_add_pr():
            data = request.get_json()
            pr_url = data.get('pr_url', '').strip()
            
            if not pr_url:
                return jsonify({'success': False, 'error': '请输入有效的 PR URL！'}), 400
            
            # 使用正则表达式解析 PR URL
            pattern = r'https://gitee\.com/([^/]+)/([^/]+)/pulls/(\d+)'
            match = re.match(pattern, pr_url)
            
            if not match:
                return jsonify({'success': False, 'error': 'URL 格式不正确！请使用格式：https://gitee.com/{owner}/{repo}/pulls/{pr_id}'}), 400
            
            owner = match.group(1)
            repo = match.group(2)
            pr_id = int(match.group(3))
            
            self.config.add_pr(owner, repo, pr_id)
            self.config.save_config()
            logger.info(f"通过 API 添加 PR #{pr_id} ({owner}/{repo}) 到监控列表")
            
            # 获取新添加PR的标签信息
            try:
                labels = self.pr_monitor.get_pr_labels(owner, repo, pr_id)
                current_labels = labels  # 传递完整的标签对象
            except Exception as e:
                logger.warning(f"获取新添加PR的标签失败: {e}")
                current_labels = []
            
            return jsonify({
                'success': True, 
                'message': 'PR 添加成功',
                'pr_data': {
                    'owner': owner,
                    'repo': repo,
                    'pr_id': pr_id,
                    'current_labels': current_labels
                }
            })
        
        # 删除 PR API 端点
        @self.app.route('/api/delete_pr', methods=['DELETE'])
        def api_delete_pr():
            data = request.get_json()
            owner = data.get('owner')
            repo = data.get('repo')
            pr_id = data.get('pr_id')
            
            if not owner or not repo or not pr_id:
                return jsonify({'success': False, 'error': '缺少必要参数'}), 400
            
            try:
                pr_id = int(pr_id)
                self.config.remove_pr(owner, repo, pr_id)
                self.config.save_config()
                logger.info(f"通过 API 删除 PR #{pr_id} ({owner}/{repo}) 从监控列表")
                return jsonify({'success': True, 'message': 'PR 删除成功'})
            except ValueError:
                return jsonify({'success': False, 'error': 'PR ID 必须是数字'}), 400
        
        # 更新API配置 API 端点
        @self.app.route('/api/update_api', methods=['POST'])
        def api_update_api():
            data = request.get_json()
            access_token = data.get('access_token', '').strip()
            
            if not access_token:
                return jsonify({'success': False, 'error': 'ACCESS_TOKEN 是必填的！'}), 400
            
            self.config.update({
                "ACCESS_TOKEN": access_token
            })
            self.config.save_config()
            logger.info("通过 API 更新 API 配置")
            
            return jsonify({'success': True, 'message': 'API 配置更新成功'})
        
    def run(self, host: str = '0.0.0.0', port: int = 5000, debug: bool = False) -> None:
        """
        运行 Web 应用
        
        Args:
            host: 主机地址
            port: 端口号
            debug: 是否启用调试模式
        """
        self.app.run(host=host, port=port, debug=debug)
