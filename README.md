# 情侣记录站 💕

记录两个人的点点滴滴，对象打开网页就能看到你们的时光轴、纪念日、相册和悄悄话。

## 选型说明：网页 vs App

**推荐使用网页 + PWA：**

- **对象使用**：发一个链接即可打开，无需下载
- **跨设备**：手机、平板、电脑都能用
- **PWA**：支持「添加到主屏幕」，用起来像 App

## 功能

- **我们在一起第 N 天**：根据「在一起的日子」纪念日自动计算
- **纪念日**：添加重要日期，显示倒计时或已过天数
- **时光轴**：按时间线记录文字与图片
- **相册**：上传照片并写描述
- **悄悄话**：写给对方的小句子

## 技术栈

- **后端**：Python 3.10+ / FastAPI / SQLAlchemy / SQLite
- **前端**：单页 HTML + CSS + JS，浪漫风格，支持 PWA

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 启动服务

在项目根目录执行（以便正确找到 `frontend` 目录）：

```bash
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

或从项目根目录：

```bash
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

注意：uvicorn 的当前工作目录会影响 `FRONTEND_DIR` 的解析。若前端页面打不开，请从 `backend` 目录启动，并把 `frontend` 复制到 `backend/../frontend`（即与 `backend` 同级），或修改 `main.py` 中 `FRONTEND_DIR` 为你的实际路径。

### 3. 打开网页

浏览器访问：**http://localhost:8000**

- 首页会显示「我们在一起第 N 天」（需先添加纪念日）
- 切换标签可查看：纪念日、时光轴、相册、悄悄话

### 4. 添加数据（API 示例）

首次使用需要往数据库里加一点内容，可以用下面的方式。

**添加「在一起的日子」纪念日（用于显示天数）：**

```bash
curl -X POST http://localhost:8000/api/anniversaries \
  -H "Content-Type: application/json" \
  -d '{"name":"在一起的日子","date":"2024-01-01","repeat_yearly":true}'
```

**添加一条时光轴：**

```bash
curl -X POST http://localhost:8000/api/memories \
  -H "Content-Type: application/json" \
  -d '{"content":"今天一起看了日落，想和你一直这样看下去。","mood":"开心"}'
```

**添加悄悄话：**

```bash
curl -X POST http://localhost:8000/api/notes \
  -H "Content-Type: application/json" \
  -d '{"content":"每天都要更爱你一点","is_public":true}'
```

**上传照片（需 multipart）：**

```bash
curl -X POST http://localhost:8000/api/photos \
  -F "file=@/path/to/photo.jpg" \
  -F "description=第一次约会"
```

API 文档：**http://localhost:8000/docs**

### 5. 可选：写入示例数据

在 `backend` 目录下执行（需已安装依赖）：

```bash
cd backend && python scripts/seed_demo.py
```

刷新页面即可看到示例纪念日、时光轴和悄悄话。

## 项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py          # 入口、挂载前端与 /uploads
│   │   ├── database.py      # SQLite 与建表
│   │   ├── models.py        # 记忆 / 纪念日 / 相册 / 悄悄话
│   │   ├── schemas.py       # 请求响应模型
│   │   └── routers/         # 各模块 API
│   ├── uploads/             # 上传的图片（自动创建）
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   ├── js/app.js
│   ├── manifest.json        # PWA
│   └── sw.js                # Service Worker
├── docs/
│   └── DESIGN.md            # 设计方案
└── README.md
```

## 部署建议

- 将本仓库部署到一台有公网 IP 或域名的服务器（或云函数 + 对象存储等）。
- 使用 **HTTPS**，这样 PWA 的 Service Worker 才能生效。
- 若多人共用或需要隐私，可在后端加简单鉴权（如密码或邀请码），再在前端登录后带 token 请求 API。

## 设计文档

更完整的设计说明与选型理由见 [docs/DESIGN.md](docs/DESIGN.md)。

---

祝你们记录下更多美好瞬间 💕
