#!/bin/bash

# iKuai IP 同步服务一键安装脚本
# 适用于基于 systemd 的 Linux 系统（如 Ubuntu、CentOS、Debian 12 等）

# 目标安装目录
INSTALL_DIR="/opt/iksip"
SERVICE_NAME="iksip"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_URL="https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/iKuai/ikuai-ip-update.py"
SCRIPT_FILE="$INSTALL_DIR/ikuai-ip-update.py"
CONFIG_FILE="$INSTALL_DIR/config.json"

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
    log_error "此脚本仅支持基于 systemd 的系统（如 Ubuntu、CentOS、Debian）"
fi

# 检查是否为 Debian 12
is_debian_12() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [ "$ID" = "debian" ] && [ "$VERSION_ID" = "12" ]; then
            return 0
        fi
    fi
    return 1
}

# 安装 Python 依赖
install_python_deps() {
    log_info "安装 Python 依赖"
    if is_debian_12; then
        log_info "检测到 Debian 12，执行强制安装 Python 依赖"
        # 安装 Python 3 和 pip
        apt-get update || log_error "更新 apt 源失败"
        apt-get install -y python3 python3-pip python3-venv || log_error "安装 python3 和 pip 失败"
        # 升级 pip
        pip3 install --upgrade pip || log_error "升级 pip 失败"
        # 强制安装依赖（绕过 Debian 12 的 externally-managed 限制）
        pip3 install --break-system-packages requests tenacity schedule || log_error "安装 Python 依赖失败"
    else
        # 非 Debian 12 系统，常规安装
        pip3 install requests tenacity schedule || log_error "安装 Python 依赖失败"
    fi
}

# 检查 Python 3 是否安装
if ! command -v python3 >/dev/null 2>&1; then
    log_warning "Python 3 未安装，尝试安装..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update && apt-get install -y python3 || log_error "安装 Python 3 失败"
    elif command -v yum >/dev/null 2>&1; then
        yum install -y python3 || log_error "安装 Python 3 失败"
    else
        log_error "无法自动安装 Python 3，请手动安装"
    fi
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

# 检查 curl 是否安装（用于下载脚本）
if ! command -v curl >/dev/null 2>&1; then
    log_warning "curl 未安装，尝试安装..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get install -y curl || log_error "安装 curl 失败"
    elif command -v yum >/dev/null 2>&1; then
        yum install -y curl || log_error "安装 curl 失败"
    else
        log_error "无法自动安装 curl，请手动安装"
    fi
fi

# 交互式收集配置
collect_config() {
    echo "请输入 iKuai IP 同步服务配置："
    
    # iKuai 管理地址
    while true; do
        read -p "iKuai 管理地址 (例如 http://10.0.0.1): " ikuai_url
        if [[ "$ikuai_url" =~ ^http(s)?://[0-9a-zA-Z.-]+(:[0-9]+)?$ ]]; then
            break
        else
            echo "无效的 URL 格式，请重新输入"
        fi
    done
    
    # 管理员账号
    read -p "管理员账号: " username
    if [ -z "$username" ]; then
        log_error "管理员账号不能为空"
    fi
    
    # 管理员密码（隐藏输入）
    read -s -p "管理员密码: " password
    echo
    if [ -z "$password" ]; then
        log_error "管理员密码不能为空"
    fi
    
    # ISP 名称
    read -p "ISP 名称 (例如 CN): " isp_name
    if [ -z "$isp_name" ]; then
        log_error "ISP 名称不能为空"
    fi
    
    # 更新周期
    while true; do
        read -p "更新周期 (daily, weekly, monthly): " schedule_type
        schedule_type=$(echo "$schedule_type" | tr '[:upper:]' '[:lower:]')
        if [[ "$schedule_type" == "daily" || "$schedule_type" == "weekly" || "$schedule_type" == "monthly" ]]; then
            break
        else
            echo "无效的更新周期，必须为 daily, weekly 或 monthly"
        fi
    done
    
    # 更新时间
    while true; do
        read -p "更新时间 (HH:MM, 例如 00:00): " schedule_time
        if [[ "$schedule_time" =~ ^[0-2][0-9]:[0-5][0-9]$ ]]; then
            break
        else
            echo "无效的时间格式，必须为 HH:MM"
        fi
    done
    
    # 每周更新时的星期（仅 weekly 需要）
    schedule_day="monday"
    if [ "$schedule_type" == "weekly" ]; then
        while true; do
            read -p "每周更新星期 (1=周一, 2=周二, ..., 7=周日): " day_num
            case "$day_num" in
                1) schedule_day="monday"; break ;;
                2) schedule_day="tuesday"; break ;;
                3) schedule_day="wednesday"; break ;;
                4) schedule_day="thursday"; break ;;
                5) schedule_day="friday"; break ;;
                6) schedule_day="saturday"; break ;;
                7) schedule_day="sunday"; break ;;
                *) echo "无效的星期编号，必须为 1-7" ;;
            esac
        done
    fi
    
    # 每月更新时的日期（仅 monthly 需要）
    schedule_date=1
    if [ "$schedule_type" == "monthly" ]; then
        while true; do
            read -p "每月更新日期 (1-28): " schedule_date
            if [[ "$schedule_date" =~ ^[1-9]$|^[1-2][0-8]$ ]]; then
                break
            else
                echo "无效的日期，必须为 1-28"
            fi
        done
    fi
    
    # 构造配置
    config=$(cat << EOF
{
    "ikuai_url": "$ikuai_url",
    "username": "$username",
    "password": "$password",
    "china_ip_url": "https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/china_ip.txt",
    "last_ip_file": "last_china_ip.json",
    "timeout": 10,
    "chunk_size": 1000,
    "isp_name": "$isp_name",
    "schedule_type": "$schedule_type",
    "schedule_time": "$schedule_time",
    "schedule_day": "$schedule_day",
    "schedule_date": $schedule_date
}
EOF
)
    
    # 显示配置并确认
    while true; do
        echo -e "\n以下是您的配置："
        echo "$config" | python3 -c "import json, sys; print(json.dumps(json.load(sys.stdin), indent=2))"
        read -p "确认配置正确？(y/n): " confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            echo "$config" > "$CONFIG_FILE"
            break
        else
            echo -e "\n重新输入配置："
            collect_config
            return
        fi
    done
}

# 创建安装目录
log_info "创建安装目录: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR" || log_error "创建目录 $INSTALL_DIR 失败"

# 下载 ikuai-ip-update.py
log_info "从 $SCRIPT_URL 下载 ikuai-ip-update.py"
curl -s -o "$SCRIPT_FILE" "$SCRIPT_URL" || log_error "下载 ikuai-ip-update.py 失败"
if [ ! -s "$SCRIPT_FILE" ]; then
    log_error "下载的 ikuai-ip-update.py 文件为空"
fi

# 交互式生成 config.json
log_info "生成 config.json"
collect_config

# 设置文件权限
log_info "设置文件权限"
chmod 755 "$SCRIPT_FILE" || log_error "设置 ikuai-ip-update.py 权限失败"
chmod 600 "$CONFIG_FILE" || log_error "设置 config.json 权限失败"
chown nobody:nogroup "$SCRIPT_FILE" "$CONFIG_FILE" || log_error "设置文件所有者失败"

# 安装 Python 依赖
install_python_deps

# 创建 systemd 服务文件
log_info "创建 systemd 服务文件: $SYSTEMD_SERVICE_FILE"
cat > "$SYSTEMD_SERVICE_FILE" << EOF
[Unit]
Description=iKuai IP Sync Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 $SCRIPT_FILE
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