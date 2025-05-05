#!/bin/bash

# 遇到任何错误时退出
set -e

# 定义变量
SERVICE_NAME="minichat"
INSTALL_DIR="/opt/miniChat"
PYTHON_VERSION="python3"
MIN_PYTHON_VERSION="3.8"
USER="minichat"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SERVER_PY_URL="https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/miniChat/server.py"
INDEX_HTML_URL="https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/miniChat/index.html"

# 输出颜色设置
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # 无颜色

echo "开始安装 miniChat..."

# 检查是否以 root 权限运行
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}此脚本必须以 root 权限运行${NC}"
   exit 1
fi

# 运行环境检测
echo "正在检测运行环境..."

# 检查是否为基于 Debian/Ubuntu 的系统
if ! command -v apt-get >/dev/null 2>&1; then
    echo -e "${RED}此脚本仅支持基于 Debian/Ubuntu 的系统，请在 Ubuntu 或 Debian 上运行${NC}"
    exit 1
fi

# 检查系统发行版
if ! grep -qi "debian\|ubuntu" /etc/os-release; then
    echo -e "${RED}警告：未检测到 Debian 或 Ubuntu 系统，可能不兼容${NC}"
    read -p "是否继续安装？(y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "安装已取消"
        exit 1
    fi
fi

# 检查 Python 版本
if ! command -v $PYTHON_VERSION >/dev/null 2>&1; then
    echo -e "${RED}未找到 Python3，请先安装 Python3${NC}"
    exit 1
fi

PYTHON_VERSION_CHECK=$($PYTHON_VERSION --version 2>&1 | grep -oP '\d+\.\d+')
if [[ "$(echo "$PYTHON_VERSION_CHECK < $MIN_PYTHON_VERSION" | bc -l)" -eq 1 ]]; then
    echo -e "${RED}Python 版本过低，要求至少 ${MIN_PYTHON_VERSION}，当前版本为 ${PYTHON_VERSION_CHECK}${NC}"
    exit 1
fi

# 检查网络连接
echo "正在检查网络连接..."
if ! curl -Is $SERVER_PY_URL >/dev/null 2>&1; then
    echo -e "${RED}无法连接到 GitHub，请检查网络或 URL 是否正确${NC}"
    exit 1
fi

# 前置安装环境与依赖
echo "正在安装前置环境与依赖..."
apt-get update
apt-get install -y python3 python3-pip python3-venv curl

# 检查 pip 是否可用
if ! $PYTHON_VERSION -m pip --version >/dev/null 2>&1; then
    echo -e "${RED}pip 未正确安装，请检查 Python 环境${NC}"
    exit 1
fi

# 创建运行服务的用户
if ! id -u $USER >/dev/null 2>&1; then
    echo "正在创建用户 ${USER}..."
    useradd -m -s /bin/false $USER
fi

# 创建安装目录
echo "正在创建安装目录 ${INSTALL_DIR}..."
mkdir -p $INSTALL_DIR
chown $USER:$USER $INSTALL_DIR

# 下载应用程序文件
echo "正在下载应用程序文件..."
curl -o $INSTALL_DIR/server.py $SERVER_PY_URL
curl -o $INSTALL_DIR/index.html $INDEX_HTML_URL
chown -R $USER:$USER $INSTALL_DIR

# 验证下载的文件
if [ ! -f "$INSTALL_DIR/server.py" ] || [ ! -f "$INSTALL_DIR/index.html" ]; then
    echo -e "${RED}无法下载所需文件，请检查 URL 和网络连接。${NC}"
    exit 1
fi

# 创建虚拟环境并安装依赖
echo "正在设置 Python 虚拟环境..."
su - $USER -s /bin/bash -c "
    cd $INSTALL_DIR
    $PYTHON_VERSION -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install aiohttp aiohttp-jinja2 jinja2
"

# 验证 Python 依赖是否安装成功
echo "正在验证 Python 依赖..."
if ! su - $USER -s /bin/bash -c "source $INSTALL_DIR/venv/bin/activate && python3 -c 'import aiohttp, aiohttp_jinja2, jinja2'" >/dev/null 2>&1; then
    echo -e "${RED}Python 依赖安装失败，请检查 pip 和网络连接${NC}"
    exit 1
fi

# 创建 systemd 服务文件
echo "正在创建 systemd 服务文件..."
cat > $SERVICE_FILE << EOF
[Unit]
Description=miniChat WebSocket 聊天服务
After=network.target

[Service]
User=$USER
Group=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 设置服务文件权限
chmod 644 $SERVICE_FILE

# 重新加载 systemd 并启用服务
echo "正在配置 systemd 服务..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

# 检查服务状态
echo "正在检查服务状态..."
if systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${GREEN}miniChat 服务已成功安装并运行！${NC}"
else
    echo -e "${RED}无法启动 miniChat 服务，请使用以下命令查看日志：journalctl -u ${SERVICE_NAME}.service${NC}"
    exit 1
fi

echo "安装完成！"
echo "后续步骤："
echo "1. 配置 Nginx 反向代理（参考 README.md 中的配置）"
echo "2. 通过 http://<您的服务器IP>:8080 访问聊天室"
echo "3. 使用以下命令监控服务状态：systemctl status ${SERVICE_NAME}"
echo "4. 使用以下命令查看日志：journalctl -u ${SERVICE_NAME}.service"