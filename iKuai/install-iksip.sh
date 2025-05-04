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

# 检查必要配置项
required_configs=("ikuai_url" "username" "password" "china_ip_url" "last_ip_file" "timeout" "chunk_size" "isp_name" "schedule_type" "schedule_time" "schedule_day" "schedule_date")
for key in "${required_configs[@]}"; do
    if ! python3 -c "import json; data=json.load(open('config.json')); assert '$key' in data" >/dev/null 2>&1; then
        log_error "config.json 缺少必需配置项: $key"
    fi
done

# 验证 schedule_type
schedule_type=$(python3 -c "import json; print(json.load(open('config.json'))['schedule_type'].lower())")
if [[ ! "$schedule_type" =~ ^(d|w|m)$ ]]; then
    log_error "config.json 中的 schedule_type 必须为 d（每天）, w（每周）或 m（每月）"
fi

# 创建安装目录
log_info "创建安装目录: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR" || log_error "创建目录 $INSTALL_DIR 失败"

# 复制脚本和配置文件
log_info "复制 ikuai-ip-update.py 和 config.json 到 $INSTALL_DIR"
cp "ikuai-ip-update.py" "$INSTALL_DIR/" || log_error "复制 ikuai-ip-update.py 失败"
cp "config.json" "$INSTALL_DIR/" || log_error "复制 config.json 失败"

# 设置文件权限
log_info "设置文件权限"
chmod 755 "$INSTALL_DIR/ikuai-ip-update.py" || log_error "设置 ikuai-ip-update.py 权限失败"
chmod 600 "$INSTALL_DIR/config.json" || log_error "设置 config.json 权限失败"
chown nobody:nogroup "$INSTALL_DIR/ikuai-ip-update.py" "$INSTALL_DIR/config.json" || log_error "设置文件所有者失败"

# 安装 Python 依赖
log_info "安装 Python 依赖"
pip3 install requests tenacity schedule || log_error "安装 Python 依赖失败"

# 创建 systemd 服务文件
log_info "创建 systemd 服务文件: $SYSTEMD_SERVICE_FILE"
cat > "$SYSTEMD_SERVICE_FILE" << EOF
[Unit]
Description=iKuai IP Bypass Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 $INSTALL_DIR/ikuai-ip-update.py
WorkingDirectory=$INSTALL_DIR
Restart=always
User=nobody
Group=nogroup

[Install]
WantedBy=multi-user.target
EOF

if [ $? -ne 0 ]; then
    log_error "创建 systemd 服务文件失败"
fi

# 重新加载 systemd 配置
log_info "重新加载 systemd 配置"
systemctl daemon-reload || log_error "重新加载 systemd 配置失败"

# 启用并启动服务
log_info "启用并启动 $SERVICE_NAME 服务"
systemctl enable "$SERVICE_NAME" || log_error "启用 $SERVICE_NAME 服务失败"
systemctl start "$SERVICE_NAME" || log_error "启动 $SERVICE_NAME 服务失败"

# 检查服务状态
log_info "检查 $SERVICE_NAME 服务状态"
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_info "$SERVICE_NAME 服务已成功启动"
else
    log_error "$SERVICE_NAME 服务启动失败，请检查日志: journalctl -u $SERVICE_NAME"
fi

log_info "安装完成！"
log_info "服务日志位于: $INSTALL_DIR/ikuai-ip-update.log"
log_info "配置文件位于: $INSTALL_DIR/config.json"
log_info "管理服务命令："
log_info "  - 查看状态: systemctl status $SERVICE_NAME"
log_info "  - 停止服务: systemctl stop $SERVICE_NAME"
log_info "  - 重启服务: systemctl restart $SERVICE_NAME"