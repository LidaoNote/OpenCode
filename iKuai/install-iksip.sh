#!/bin/bash

# iKuai IP 更新服务一键安装脚本
# 适用于基于 systemd 的 Linux 系统（如 Ubuntu、CentOS 等）
# 支持从网络下载 ikuai-ip-update.py 或使用本地文件
# 如果缺少 config.json，将交互式生成标准 JSON 配置文件，仅要求用户输入必要字段
# username 和 isp_name 支持默认值，其他字段使用默认值，配置说明在 config.json.example 中

# 目标安装目录
INSTALL_DIR="/opt/iksip"
SERVICE_NAME="iksip"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_URL="https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/iKuai/ikuai-ip-update.py"
SCRIPT_NAME="ikuai-ip-update.py"
DEFAULT_CHINA_IP_URL="https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/china_ip.txt"
DEFAULT_LAST_IP_FILE="last_sync_ip.json"
DEFAULT_TIMEOUT=30
DEFAULT_CHUNK_SIZE=10000
DEFAULT_USERNAME="admin"
DEFAULT_ISP_NAME="CN"
DEFAULT_SCHEDULE_TYPE="d"
DEFAULT_SCHEDULE_TIME="05:00"
DEFAULT_SCHEDULE_DAY="monday"
DEFAULT_SCHEDULE_DATE=1

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

# 检查并获取 ikuai-ip-update.py
if [ -f "$SCRIPT_NAME" ]; then
    log_info "找到本地 $SCRIPT_NAME 文件，将使用本地文件"
else
    log_info "未找到本地 $SCRIPT_NAME 文件，尝试从 $SCRIPT_URL 下载"
    if command -v curl >/dev/null 2>&1; then
        curl -o "$SCRIPT_NAME" "$SCRIPT_URL" || log_error "下载 $SCRIPT_NAME 失败"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$SCRIPT_NAME" "$SCRIPT_URL" || log_error "下载 $SCRIPT_NAME 失败"
    else
        log_error "未安装 curl 或 wget，请安装后重试"
    fi
    log_info "成功下载 $SCRIPT_NAME"
fi

# 验证 ikuai-ip-update.py 是否可执行
if ! head -n 1 "$SCRIPT_NAME" | grep -q "^#!/usr/bin/env python3"; then
    log_error "$SCRIPT_NAME 文件格式错误，缺少 Python shebang 行"
fi

# 交互式生成 config.json（如果不存在）
if [ ! -f "config.json" ]; then
    log_warning "未找到 config.json，将通过交互式输入生成配置文件"
    
    # 收集用户输入
    read -p "请输入 iKuai 路由器地址 (例如 http://10.0.0.1): " ikuai_url
    [ -z "$ikuai_url" ] && log_error "iKuai 路由器地址不能为空"

    read -p "请输入 iKuai 用户名 (按 Enter 使用默认 $DEFAULT_USERNAME): " username
    username=${username:-$DEFAULT_USERNAME}

    read -p "请输入 iKuai 密码: " password
    [ -z "$password" ] && log_error "密码不能为空"

    read -p "请输入运营商名称 (按 Enter 使用默认 $DEFAULT_ISP_NAME): " isp_name
    isp_name=${isp_name:-$DEFAULT_ISP_NAME}

    # 使用 Python 生成 config.json，确保正确处理特殊字符
    python3 - << EOF || log_error "生成 config.json 失败，请检查输入值（可能包含特殊字符，如引号或换行符）"
import json
config = {
    "ikuai_url": "$ikuai_url",
    "username": "$username",
    "password": "$password",
    "china_ip_url": "$DEFAULT_CHINA_IP_URL",
    "last_ip_file": "$DEFAULT_LAST_IP_FILE",
    "timeout": $DEFAULT_TIMEOUT,
    "chunk_size": $DEFAULT_CHUNK_SIZE,
    "isp_name": "$isp_name",
    "schedule_type": "$DEFAULT_SCHEDULE_TYPE",
    "schedule_time": "$DEFAULT_SCHEDULE_TIME",
    "schedule_day": "$DEFAULT_SCHEDULE_DAY",
    "schedule_date": $DEFAULT_SCHEDULE_DATE
}
with open("config.json", "w") as f:
    json.dump(config, f, indent=4)
EOF
    log_info "已生成 config.json"

    # 生成 config.json.example，包含注释
    python3 - << EOF || log_error "生成 config.json.example 失败"
import json
config = {
    "ikuai_url": "$ikuai_url",
    "username": "$username",
    "password": "$password",
    "china_ip_url": "$DEFAULT_CHINA_IP_URL",
    "last_ip_file": "$DEFAULT_LAST_IP_FILE",
    "timeout": $DEFAULT_TIMEOUT,
    "chunk_size": $DEFAULT_CHUNK_SIZE,
    "isp_name": "$isp_name",
    "schedule_type": "$DEFAULT_SCHEDULE_TYPE",
    "schedule_time": "$DEFAULT_SCHEDULE_TIME",
    "schedule_day": "$DEFAULT_SCHEDULE_DAY",
    "schedule_date": $DEFAULT_SCHEDULE_DATE
}
comments = {
    "ikuai_url": "iKuai 路由器地址，例如 http://10.0.0.1，必须是有效的 URL",
    "username": "iKuai 管理员用户名，不能为空，默认为 admin",
    "password": "iKuai 管理员密码，不能为空",
    "china_ip_url": "IP 列表的 URL，默认为中国 IP 列表，可改为其他 IP 列表的 URL（如 https://example.com/other_ip.txt）",
    "last_ip_file": "本地保存的 IP 列表文件名，首次运行时生成，可改为其他文件名（如 my_ip_list.json）",
    "timeout": "API 请求超时时间（秒），正数，可根据网络情况调整（如 10, 60），默认为 30",
    "chunk_size": "分块大小（当前 API 无需分块），正整数，可根据需要调整（如 5000, 20000），默认为 10000",
    "isp_name": "运营商名称，用于 iKuai 路由器，不能为空，默认为 CN",
    "schedule_type": "调度周期：d=每天，w=每周，m=每月，默认为 d（每天）",
    "schedule_time": "调度时间，格式 HH:MM（如 05:00），表示每天/每周/每月的运行时间，默认为 05:00（凌晨 5 点）",
    "schedule_day": "每周调度星期，仅在 schedule_type=w 时有效，可为 monday, tuesday, wednesday, thursday, friday, saturday, sunday，默认为 monday",
    "schedule_date": "每月调度日期，仅在 schedule_type=m 时有效，范围 1-28，默认为 1（每月 1 号）"
}
# 生成带注释的 JSON 字符串
output = []
for key, value in config.items():
    output.append({"// {}".format(key): comments[key]})
    output.append({key: value})
with open("config.json.example", "w") as f:
    json.dump(output, f, indent=4, ensure_ascii=False)
EOF
    log_info "已生成 config.json.example，包含配置项说明"
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
log_info "复制 $SCRIPT_NAME 和 config.json 到 $INSTALL_DIR"
cp "$SCRIPT_NAME" "$INSTALL_DIR/" || log_error "复制 $SCRIPT_NAME 失败"
cp "config.json" "$INSTALL_DIR/" || log_error "复制 config.json 失败"
cp "config.json.example" "$INSTALL_DIR/" 2>/dev/null || log_info "未找到 config.json.example，跳过复制"

# 设置文件权限
log_info "设置文件权限"
chmod 755 "$INSTALL_DIR/$SCRIPT_NAME" || log_error "设置 $SCRIPT_NAME 权限失败"
chmod 600 "$INSTALL_DIR/config.json" || log_error "设置 config.json 权限失败"
chmod 644 "$INSTALL_DIR/config.json.example" 2>/dev/null || true
chown nobody:nogroup "$INSTALL_DIR/$SCRIPT_NAME" "$INSTALL_DIR/config.json" || log_error "设置文件所有者失败"
chown nobody:nogroup "$INSTALL_DIR/config.json.example" 2>/dev/null || true

# 安装 Python 依赖
log_info "安装 Python 依赖"
pip3 install requests tenacity schedule || log_error "安装 Python 依赖失败"

# 创建 systemd 服务文件
log_info "创建 systemd 服务文件: $SYSTEMD_SERVICE_FILE"
cat > "$SYSTEMD_SERVICE_FILE" << EOF
[Unit]
Description=iKuai IP Update Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 $INSTALL_DIR/$SCRIPT_NAME
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
log_info "配置说明位于: $INSTALL_DIR/config.json.example"
log_info "您可以编辑 $INSTALL_DIR/config.json 修改以下默认配置："
log_info "  - IP 列表 URL: $DEFAULT_CHINA_IP_URL"
log_info "  - 本地 IP 列表文件名: $DEFAULT_LAST_IP_FILE"
log_info "  - API 请求超时时间: $DEFAULT_TIMEOUT 秒"
log_info "  - 分块大小: $DEFAULT_CHUNK_SIZE（当前 API 无需分块）"
log_info "  - 调度周期: $DEFAULT_SCHEDULE_TYPE（每天）"
log_info "  - 调度时间: $DEFAULT_SCHEDULE_TIME（凌晨 5 点）"
log_info "  - 每周调度星期: $DEFAULT_SCHEDULE_DAY（仅每周有效）"
log_info "  - 每月调度日期: $DEFAULT_SCHEDULE_DATE（仅每月有效）"
log_info "管理服务命令："
log_info "  - 查看状态: systemctl status $SERVICE_NAME"
log_info "  - 停止服务: systemctl stop $SERVICE_NAME"
log_info "  - 重启服务: systemctl restart $SERVICE_NAME"