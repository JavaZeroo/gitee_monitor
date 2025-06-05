# Gitee PR 标签监控工具

一个用于监控 Gitee PR 标签变化的工具，支持 Web 界面和 Webhook 通知。

## 功能

- 监控指定 PR 的标签变化
- Web 界面查看和配置
- Webhook 接收实时通知
- 自动轮询 PR 标签
- 缓存机制避免频繁 API 调用

## 安装

1. 克隆仓库：

```bash
git clone https://github.com/your-username/gitee_monitor.git
cd gitee_monitor
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 配置：

修改 `config.json` 文件或通过 Web 界面配置。

## 使用方法

### 启动服务

```bash
python main.py
```

可选参数：
- `-c, --config`: 配置文件路径（默认：config.json）
- `-p, --port`: Web 服务器端口（默认：5000）
- `-d, --debug`: 启用调试模式
- `-l, --log-level`: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL，默认：INFO）

### Web 界面

访问 `http://localhost:5000` 打开 Web 界面。

- 主页: 查看所有监控的 PR 及其标签
- 配置页: 修改 API 配置和管理监控的 PR

### Webhook

配置 Gitee 仓库的 Webhook 指向 `http://your-server:5000/webhook`。

## 配置项

配置文件 `config.json` 包含以下字段：

- `GITEA_URL`: Gitee API URL
- `ACCESS_TOKEN`: Gitee 访问令牌
- `PULL_REQUEST_LISTS`: 监控的 PR 列表，每个元素包含：
  - `OWNER`: 仓库拥有者
  - `REPO`: 仓库名称
  - `PULL_REQUEST_ID`: PR ID
- `CACHE_TTL`: 缓存生存时间（秒）
- `POLL_INTERVAL`: 轮询间隔（秒）
- `ENABLE_NOTIFICATIONS`: 是否启用通知

### 配置文件示例

```json
{
    "GITEA_URL": "https://gitee.com/api/v5",
    "ACCESS_TOKEN": "your_access_token_here",
    "PULL_REQUEST_LISTS": [
        {
            "OWNER": "mindspore",
            "REPO": "mindformers",
            "PULL_REQUEST_ID": 6344
        },
        {
            "OWNER": "another_owner",
            "REPO": "another_repo",
            "PULL_REQUEST_ID": 123
        }
    ],
    "CACHE_TTL": 300,
    "POLL_INTERVAL": 60,
    "ENABLE_NOTIFICATIONS": false
}
```

## 开发

### 项目结构

```
gitee_monitor/
├── gitee_monitor/
│   ├── api/
│   │   ├── __init__.py
│   │   └── gitee_api.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── config_manager.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── pr_monitor.py
│   ├── web/
│   │   ├── __init__.py
│   │   └── webapp.py
│   └── __init__.py
├── logs/
├── static/
│   ├── css/
│   └── js/
├── templates/
├── config.json
├── main.py
└── requirements.txt
```

### 模块

- `api`: Gitee API 客户端
- `config`: 配置管理
- `services`: PR 监控服务
- `web`: Flask Web 应用
