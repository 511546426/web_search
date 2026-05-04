# 漫剧视频自动化系统

自动抓取热点话题 → AI 生成剧本 → 生成漫画风格视频。

## 功能

- **热点抓取**：自动从微博、抖音等平台抓取热门话题
- **AI 剧本生成**：调用 DeepSeek API 自动撰写剧本
- **分镜生成**：根据剧本自动生成分镜描述和视频提示词
- **视频生成**：通过 Seedance API 生成漫画风格短视频
- **批量处理**：支持批量抓取热点并逐个生成视频
- **视频发布管理**：标记发布状态（微博/抖音/B站/微信）

## 技术栈

- **后端**：Python 3.10+ / FastAPI / SQLAlchemy / SQLite
- **AI**：DeepSeek API（剧本生成）/ Seedance API（视频生成）
- **前端**：纯 HTML + CSS + JS 管理面板

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填写 API Key 等配置
```

### 2. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 3. 启动服务

```bash
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 打开管理面板

浏览器访问：**http://localhost:8000/comic-admin.html**

### 5. 注册账号

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-password"}'
```

### 6. 触发生成

```bash
# 手动指定话题
curl -X POST http://localhost:8000/api/comic/trigger \
  -H "Content-Type: application/json" \
  -d '{"topic":"最近热门电影", "auto_generate_video": true}'

# 自动抓取热点批量生成
curl -X POST http://localhost:8000/api/comic/trigger-batch \
  -H "Content-Type: application/json" \
  -d '{"limit": 3}'
```

API 文档：**http://localhost:8000/docs**

## 项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py                # 入口
│   │   ├── database.py            # SQLite 配置
│   │   ├── models.py              # 数据模型
│   │   ├── schemas.py             # 请求响应模型
│   │   ├── security.py            # 认证鉴权
│   │   ├── routers/
│   │   │   ├── auth.py            # 注册登录
│   │   │   └── comic_videos.py    # 漫剧视频 API
│   │   └── services/
│   │       ├── scraper.py         # 热点抓取
│   │       ├── script_writer.py   # 剧本生成
│   │       ├── deepseek_client.py # DeepSeek API
│   │       ├── seedance_client.py # Seedance 视频 API
│   │       └── video_pipeline.py  # 流水线编排
│   │   └── tasks/
│   │       └── scheduler.py       # 定时任务
│   ├── uploads/                   # 生成视频输出
│   └── requirements.txt
├── frontend/
│   ├── comic-admin.html           # 管理面板
│   ├── css/comic-admin.css
│   └── js/comic-admin.js
├── deploy/                        # 部署脚本
└── .env.example
```

## 部署

参考 `deploy/` 目录下的脚本：

- `aliyun-setup.sh`：阿里云服务器初始化
- `comic-video.service`：systemd 服务配置
- `nginx.conf`：Nginx 反向代理配置
