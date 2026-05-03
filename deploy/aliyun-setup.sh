#!/bin/bash
# 阿里云 2核2G 一键部署脚本
# 用法: chmod +x aliyun-setup.sh && sudo bash aliyun-setup.sh

set -e
echo "=== 漫剧视频生成系统 · 阿里云部署 ==="

# 检测系统
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "无法检测操作系统，退出。"
    exit 1
fi
echo "[1/8] 系统: $OS"

# 安装 Python 3.10+
echo "[2/8] 安装 Python 3.10+ ..."
case $OS in
    ubuntu|debian)
        apt-get update -y
        apt-get install -y python3 python3-pip python3-venv nginx git curl
        ;;
    centos|rhel|alinux|anolis|opencloudos)
        yum install -y python3 python3-pip nginx git curl
        ;;
    *)
        echo "不支持的系统: $OS"
        exit 1
        ;;
esac

# 项目目录
PROJECT_DIR=/opt/comic-video
echo "[3/8] 部署到: $PROJECT_DIR"

if [ ! -d "$PROJECT_DIR" ]; then
    git clone https://github.com/your-repo/comic-video.git "$PROJECT_DIR" 2>/dev/null || {
        echo "Git clone 失败，请手动上传代码到 $PROJECT_DIR"
        mkdir -p "$PROJECT_DIR"
    }
fi

# 创建虚拟环境
echo "[4/8] 创建 Python 虚拟环境 ..."
python3 -m venv "$PROJECT_DIR/.venv"
source "$PROJECT_DIR/.venv/bin/activate"

# 安装依赖
if [ -f "$PROJECT_DIR/backend/requirements.txt" ]; then
    pip install -r "$PROJECT_DIR/backend/requirements.txt"
else
    echo "ERROR: requirements.txt 不存在，请确保项目代码已上传"
    exit 1
fi

# 配置环境变量
echo "[5/8] 配置环境变量 ..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo ">>> 请编辑 $PROJECT_DIR/.env 填写 API Key <<<"
fi

# systemd 服务
echo "[6/8] 配置 systemd 服务 ..."
cp "$PROJECT_DIR/deploy/comic-video.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable comic-video

# Nginx 反向代理
echo "[7/8] 配置 Nginx ..."
cp "$PROJECT_DIR/deploy/nginx.conf" /etc/nginx/conf.d/comic-video.conf
# 移除默认配置
rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf 2>/dev/null || true
nginx -t && systemctl reload nginx || echo "Nginx 配置测试未通过，请检查后再启动"

# 防火墙
echo "[8/8] 开放端口 ..."
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --add-service=http --permanent 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
elif command -v ufw &>/dev/null; then
    ufw allow 80/tcp 2>/dev/null || true
fi

# 启动
echo ""
echo "=== 部署完成 ==="
echo "启动服务: systemctl start comic-video"
echo "查看状态: systemctl status comic-video"
echo "访问面板: http://YOUR_SERVER_IP/comic-admin.html"
echo ""
echo "⚠  请先编辑 $PROJECT_DIR/.env 填入 API Key 后再启动服务！"
