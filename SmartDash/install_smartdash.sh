#!/bin/bash

# 安装目录
INSTALL_DIR="/opt/smartdash"
TEMPLATE_DIR="${INSTALL_DIR}/templates"
SERVICE_NAME="smartdash"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PORT=8088

# 文件下载地址（使用 GitHub 原始链接）
APP_PY_URL="https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/SmartDash/app.py"
INDEX_HTML_URL="https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/SmartDash/templates/index.html"

# 目标文件路径
APP_PY_PATH="${INSTALL_DIR}/app.py"
INDEX_HTML_PATH="${TEMPLATE_DIR}/index.html"

# 所需的 Python 模块
REQUIRED_MODULES=("flask" "flask-bootstrap" "requests" "dnspython" "schedule")

# 颜色输出函数
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
echo_red() { echo -e "${RED}$1${NC}"; }
echo_green() { echo -e "${GREEN}$1${NC}"; }
echo_yellow() { echo -e "${YELLOW}$1${NC}"; }

# 检查系统类型以确定包管理器
PACKAGE_MANAGER=""
if command -v apt &> /dev/null; then
    PACKAGE_MANAGER="apt"
elif command -v yum &> /dev/null; then
    PACKAGE_MANAGER="yum"
elif command -v dnf &> /dev/null; then
    PACKAGE_MANAGER="dnf"
else
    echo_red "错误：未找到支持的包管理器（apt/yum/dnf），无法自动安装依赖。"
    exit 1
fi

# 检查 Python 环境
check_python_env() {
    echo "检查 Python 环境..."
    if ! command -v python3 &> /dev/null; then
        echo_yellow "Python3 未安装，正在尝试安装..."
        if [ "$PACKAGE_MANAGER" = "apt" ]; then
            sudo apt update
            sudo apt install -y python3 python3-pip
        elif [ "$PACKAGE_MANAGER" = "yum" ] || [ "$PACKAGE_MANAGER" = "dnf" ]; then
            sudo $PACKAGE_MANAGER install -y python3 python3-pip
        fi
        if [ $? -ne 0 ]; then
            echo_red "错误：安装 Python3 失败，请手动安装。"
            exit 1
        fi
        echo_green "Python3 安装成功。"
    else
        echo_green "Python3 已安装：$(python3 --version)"
    fi

    if ! command -v pip3 &> /dev/null; then
        echo_yellow "pip3 未安装，正在尝试安装..."
        if [ "$PACKAGE_MANAGER" = "apt" ]; then
            sudo apt update
            sudo apt install -y python3-pip
        elif [ "$PACKAGE_MANAGER" = "yum" ] || [ "$PACKAGE_MANAGER" = "dnf" ]; then
            sudo $PACKAGE_MANAGER install -y python3-pip
        fi
        if [ $? -ne 0 ]; then
            echo_red "错误：安装 pip3 失败，请手动安装。"
            exit 1
        fi
        echo_green "pip3 安装成功。"
    else
        echo_green "pip3 已安装：$(pip3 --version)"
    fi
}

# 检查并安装 Python 模块
check_python_modules() {
    echo "检查必要的 Python 模块..."
    for module in "${REQUIRED_MODULES[@]}"; do
        if ! pip3 show "$module" &> /dev/null; then
            echo_yellow "模块 $module 未安装，正在尝试安装..."
            pip3 install "$module" --user
            if [ $? -ne 0 ]; then
                echo_red "错误：安装 $module 失败，尝试使用 sudo 安装..."
                sudo pip3 install "$module"
                if [ $? -ne 0 ]; then
                    echo_red "错误：安装 $module 失败，请手动安装。"
                    exit 1
                fi
            fi
            echo_green "模块 $module 安装成功。"
        else
            echo_green "模块 $module 已安装。"
        fi
    done
}

# 检查服务是否存在
check_service() {
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo_yellow "警告：服务 ${SERVICE_NAME} 已存在且正在运行。"
        return 1
    elif [ -f "$SERVICE_FILE" ]; then
        echo_yellow "警告：服务 ${SERVICE_NAME} 已存在但未运行。"
        return 1
    else
        echo_green "服务 ${SERVICE_NAME} 未存在，可以安装。"
        return 0
    fi
}

# 检查端口是否被占用
check_port() {
    if lsof -i :$PORT &> /dev/null; then
        echo_yellow "警告：端口 ${PORT} 已被占用。"
        echo_yellow "占用端口的进程信息："
        lsof -i :$PORT
        return 1
    else
        echo_green "端口 ${PORT} 未被占用，可以使用。"
        return 0
    fi
}

# 安装 SmartDash 服务
install_service() {
    echo "正在安装 ${SERVICE_NAME} 服务..."
    if [ ! -f "$APP_PY_PATH" ]; then
        echo_red "错误：应用文件 ${APP_PY_PATH} 不存在，请先安装应用。"
        return 1
    fi

    # 创建服务文件
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=SmartDash - SmartDNS Configuration Web Interface
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 ${APP_PY_PATH}
Restart=always
RestartSec=10
SyslogIdentifier=SmartDash
Environment=FLASK_ENV=production

[Install]
WantedBy=multi-user.target
EOF

    if [ $? -ne 0 ]; then
        echo_red "错误：创建服务文件失败，请检查权限。"
        return 1
    fi

    # 重新加载服务配置
    sudo systemctl daemon-reload
    if [ $? -ne 0 ]; then
        echo_red "错误：重新加载服务配置失败。"
        return 1
    fi

    # 启用服务
    sudo systemctl enable "$SERVICE_NAME"
    if [ $? -ne 0 ]; then
        echo_red "错误：启用服务失败。"
        return 1
    fi

    # 启动服务
    sudo systemctl start "$SERVICE_NAME"
    if [ $? -ne 0 ]; then
        echo_red "错误：启动服务失败，请查看日志：journalctl -u ${SERVICE_NAME}"
        return 1
    fi

    echo_green "服务 ${SERVICE_NAME} 安装并启动成功！"
    echo_green "访问地址：http://<你的IP>:${PORT}"
    return 0
}

# 卸载 SmartDash 服务
uninstall_service() {
    echo "正在卸载 ${SERVICE_NAME} 服务..."
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        sudo systemctl stop "$SERVICE_NAME"
        if [ $? -ne 0 ]; then
            echo_red "错误：停止服务失败，请手动停止。"
        else
            echo_green "服务已停止。"
        fi
    fi

    if [ -f "$SERVICE_FILE" ]; then
        sudo systemctl disable "$SERVICE_NAME"
        sudo rm -f "$SERVICE_FILE"
        sudo systemctl daemon-reload
        if [ $? -ne 0 ]; then
            echo_red "错误：卸载服务失败，请手动删除 ${SERVICE_FILE}。"
        else
            echo_green "服务文件已删除。"
        fi
    else
        echo_yellow "服务文件不存在，无需卸载服务。"
    fi

    echo "是否删除应用文件和目录 ${INSTALL_DIR}？(y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        sudo rm -rf "$INSTALL_DIR"
        if [ $? -ne 0 ]; then
            echo_red "错误：删除应用目录失败，请手动删除。"
        else
            echo_green "应用目录已删除。"
        fi
    fi
    echo_green "服务卸载完成！"
}

# 安装应用文件
install_app() {
    # 检查安装目录是否存在
    if [ -d "$INSTALL_DIR" ]; then
        echo_yellow "警告：安装目录 ${INSTALL_DIR} 已存在。"
        echo_yellow "继续安装可能导致同名文件被覆盖。是否继续？(y/n)"
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            echo_red "安装已取消。"
            return 1
        fi
    else
        echo "创建安装目录 ${INSTALL_DIR}..."
        mkdir -p "$INSTALL_DIR"
        if [ $? -ne 0 ]; then
            echo_red "错误：无法创建目录 ${INSTALL_DIR}，请检查权限。"
            return 1
        fi
    fi

    # 检查模板目录是否存在
    if [ ! -d "$TEMPLATE_DIR" ]; then
        echo "创建模板目录 ${TEMPLATE_DIR}..."
        mkdir -p "$TEMPLATE_DIR"
        if [ $? -ne 0 ]; then
            echo_red "错误：无法创建目录 ${TEMPLATE_DIR}，请检查权限。"
            return 1
        fi
    fi

    # 检查 Python 环境和模块
    check_python_env
    check_python_modules

    # 检查是否安装了 curl 或 wget
    DOWNLOAD_TOOL=""
    if command -v curl &> /dev/null; then
        DOWNLOAD_TOOL="curl"
    elif command -v wget &> /dev/null; then
        DOWNLOAD_TOOL="wget"
    else
        echo_red "错误：未找到 curl 或 wget，无法下载文件。请先安装其中一个工具。"
        return 1
    fi

    # 下载 app.py
    echo "正在下载 app.py 到 ${APP_PY_PATH}..."
    if [ "$DOWNLOAD_TOOL" = "curl" ]; then
        curl -sS -o "$APP_PY_PATH" "$APP_PY_URL"
    elif [ "$DOWNLOAD_TOOL" = "wget" ]; then
        wget -q -O "$APP_PY_PATH" "$APP_PY_URL"
    fi
    if [ $? -ne 0 ]; then
        echo_red "错误：下载 app.py 失败，请检查网络连接或 URL 是否有效。"
        return 1
    fi
    echo_green "app.py 下载完成。"

    # 下载 index.html
    echo "正在下载 index.html 到 ${INDEX_HTML_PATH}..."
    if [ "$DOWNLOAD_TOOL" = "curl" ]; then
        curl -sS -o "$INDEX_HTML_PATH" "$INDEX_HTML_URL"
    elif [ "$DOWNLOAD_TOOL" = "wget" ]; then
        wget -q -O "$INDEX_HTML_PATH" "$INDEX_HTML_URL"
    fi
    if [ $? -ne 0 ]; then
        echo_red "错误：下载 index.html 失败，请检查网络连接或 URL 是否有效。"
        return 1
    fi
    echo_green "index.html 下载完成。"

    # 设置文件权限
    echo "设置文件权限..."
    chmod 755 "$APP_PY_PATH"
    if [ $? -ne 0 ]; then
        echo_yellow "警告：设置 app.py 权限失败，请手动检查。"
    fi
    chmod 644 "$INDEX_HTML_PATH"
    if [ $? -ne 0 ]; then
        echo_yellow "警告：设置 index.html 权限失败，请手动检查。"
    fi

    echo_green "应用文件安装完成！文件已下载到以下位置："
    echo_green "  - ${APP_PY_PATH}"
    echo_green "  - ${INDEX_HTML_PATH}"
    return 0
}

# 主菜单
show_menu() {
    echo ""
    echo "===== SmartDash 安装与管理工具 ====="
    echo "1. 安装 SmartDash 应用文件"
    echo "2. 安装 SmartDash 为系统服务"
    echo "3. 卸载 SmartDash 服务"
    echo "4. 退出"
    echo "====================================="
    echo "请选择操作（1-4）："
}

# 主程序
while true; do
    show_menu
    read -r choice
    case $choice in
        1)
            install_app
            ;;
        2)
            echo "检查服务和端口..."
            check_service
            service_exists=$?
            check_port
            port_free=$?
            if [ $service_exists -eq 1 ] || [ $port_free -eq 1 ]; then
                echo_yellow "警告：服务或端口存在冲突，是否继续安装服务？(y/n)"
                read -r response
                if [[ ! "$response" =~ ^[Yy]$ ]]; then
                    echo_red "服务安装已取消。"
                    continue
                fi
            fi
            install_service
            ;;
        3)
            uninstall_service
            ;;
        4)
            echo_green "退出程序。"
            exit 0
            ;;
        *)
            echo_red "无效选项，请选择 1-4。"
            ;;
    esac
done
