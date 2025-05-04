#!/bin/bash

# iKuai IP 更新服务一键安装脚本
# 适用于基于 systemd 的 Linux 系统（如 Ubuntu、CentOS 等）
# 支持从网络下载 ikuai-ip-update.py 或使用本地文件
# 如果缺少 config.json，将交互式生成配置文件
# 中国 IP 列表 URL 支持默认值

# 目标安装目录
INSTALL_DIR="/opt/iksip"
SERVICE_NAME="iksip"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_URL="https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/iKuai/ikuai-ip-update.py"
SCRIPT_NAME="ikuai-ip-update.py"
DEFAULT_CHINA_IP_URL="https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/china_ip.txt"

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
    config_json="{}"
    
    # 收集用户输入
    read -p "请输入 iKuai 路由器地址 (例如 http://10.0.0.1): " ikuai_url
    [ -z "$ikuai_url" ] && log_error "iKuai 路由器地址不能为空"
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['ikuai_url']='$ikuai_url'; print(json.dumps(d))")

    read -p "请输入 iKuai 用户名: " username
    [ -z "$username" ] && log_error "用户名不能为空"
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['username']='$username'; print(json.dumps(d))")

    read -p "请输入 iKuai 密码: " password
    [ -z "$password" ] && log_error "密码不能为空"
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['password']='$password'; print(json.dumps(d))")

    read -p "请输入中国 IP 列表 URL (按 Enter 使用默认 $DEFAULT_CHINA_IP_URL): " china_ip_url
    china_ip_url=${china_ip_url:-$DEFAULT_CHINA_IP_URL}
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['china_ip_url']='$china_ip_url'; print(json.dumps(d))")

    read -p "请输入本地 IP 列表文件名 (例如 last_china_ip.json): " last_ip_file
    [ -z "$last_ip_file" ] && log_error "本地 IP 列表文件名不能为空"
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['last_ip_file']='$last_ip_file'; print(json.dumps(d))")

    read -p "请输入 API 请求超时时间（秒，例如 10）: " timeout
    [ -z "$timeout" ] && log_error "超时时间不能为空"
    if ! [[ "$timeout" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [ "$timeout" -le 0 ]; then
        log_error "超时时间必须为正数"
    fi
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['timeout']=$timeout; print(json.dumps(d))")

    read -p "请输入分块大小（例如 10000，当前 API 无需分块）: " chunk_size
    [ -z "$chunk_size" ] && log_error "分块大小不能为空"
    if ! [[ "$chunk_size" =~ ^[0-9]+$ ]] || [ "$chunk_size" -le 0 ]; then
        log_error "分块大小必须为正整数"
    fi
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['chunk_size']=$chunk_size; print(json.dumps(d))")

    read -p "请输入运营商名称 (例如 CN): " isp_name
    [ -z "$isp_name" ] && log_error "运营商名称不能为空"
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['isp_name']='$isp_name'; print(json.dumps(d))")

    read -p "请输入调度周期 (d=每天, w=每周, m=每月): " schedule_type
    [ -z "$schedule_type" ] && log_error "调度周期不能为空"
    if ! [[ "$schedule_type" =~ ^(d|w|m)$ ]]; then
        log_error "调度周期必须为 d, w 或 m"
    fi
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['schedule_type']='$schedule_type'; print(json.dumps(d))")

    read -p "请输入调度时间 (HH:MM，例如 00:00): " schedule_time
    [ -z "$schedule_time" ] && log_error "调度时间不能为空"
    if ! [[ "$schedule_time" =~ ^[0-2][0-9]:[0-5][0-9]$ ]]; then
        log_error "调度时间必须为 HH:MM 格式"
    fi
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['schedule_time']='$schedule_time'; print(json.dumps(d))")

    read -p "请输入每周调度星期 (monday, tuesday, ..., sunday): " schedule_day
    [ -z "$schedule_day" ] && log_error "调度星期不能为空"
    if ! [[ "$schedule_day" =~ ^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$ ]]; then
        log_error "调度星期必须为 monday, tuesday 等"
    fi
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['schedule_day']='$schedule_day'; print(json.dumps(d))")

    read -p "请输入每月调度日期 (1-28): " schedule_date
    [ -z "$schedule_date" ] && log_error "调度日期不能为空"
    if ! [[ "$schedule_date" =~ ^[0-9]+$ ]] || [ "$schedule_date" -lt 1 ] || [ "$schedule_date" -gt 28 ]; then
        log_error "调度日期必须为 1-28 之间的整数"
    fi
    config_json=$(python3 -c "import json; d=json.loads('$config_json'); d['schedule_date']=$schedule_date; print(json.dumps(d))")

    # 保存 config.json
    echo "$config_json" | python3 -c "import json, sys; json.dump(json.load(sys.stdin), open('config.json', 'w'), indent=4)" || log_error "生成 config.json 失败"
    log_info "已生成 config.json"
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

# 设置文件权限
log_info "设置文件权限"
chmod 755 "$INSTALL_DIR/$SCRIPT_NAME" || log_error "设置 $SCRIPT_NAME 权限失败"
chmod 600 "$INSTALL_DIR/config.json" || log_error "设置 config.json 权限失败"
chown nobody:nogroup "$INSTALL_DIR/$SCRIPT_NAME" "$INSTALL_DIR/config.json" || log_error "设置文件所有者失败"

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
log_info "管理服务命令："
log_info "  - 查看状态: systemctl status $SERVICE_NAME"
log_info "  - 停止服务: systemctl stop $SERVICE_NAME"
log_info "  - 重启服务: systemctl restart $SERVICE_NAME"