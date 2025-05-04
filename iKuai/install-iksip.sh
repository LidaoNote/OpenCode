#!/bin/bash

# iKuai IP 绕过服务一键安装脚本
# 适用于基于 systemd 的 Linux 系统（如 Ubuntu、CentOS 等）

# 目标安装目录
INSTALL_DIR="/opt/ikbyp"
SERVICE_NAME="ikbyp"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # 无颜色

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# 检查是否为 root 用户
if [ "$(id -u)" -ne 0 ]; then
    log_error "请以 root 用户或使用 sudo 运行此脚本"
fi

# 检查系统是否支持 systemd
if ! command -v systemctl >/dev/null 2>&1; then
    log_error "此脚本仅支持基于 systemd 的系统（如 Ubuntu、CentOS）"
fi

# 检查 Python 3 是否安装
if ! command -v python3 >/dev/null 2>&1; then
    log_error "Python 3 未安装，请先安装 Python 3"
fi

# 检查 pip 是否安装
if ! command -v pip3 >/dev/null 2>&1; then
    log_warning "pip3 未安装，尝试安装..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update && apt-get install -y python3-pip || log_error "安装 pip3 失败"
    elif command -v yum >/dev/null 2>&1; then
        yum install -y python3-pip || log_error "安装 pip3 失败"
    else
        log_error "无法自动安装 pip3，请手动安装"
    fi
fi

# 检查当前目录下是否有 ikuai-ip-update.py 和 config.json
if [ ! -f "ikuai-ip-update.py" ]; then
    log_error "当前目录下缺少 ikuai-ip-update.py 文件"
fi

if [ ! -f "config.json" ]; then
    log_error "当前目录下缺少 config.json 文件"
fi

# 验证 config.json 格式
if ! python3 -c "import json; json.load(open('config.json'))" >/dev/null 2>&1; then
    log_error "config.json 格式错误，请检查 JSON 语法"
fi