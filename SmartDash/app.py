from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_bootstrap import Bootstrap
import os
import shutil
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import dns.resolver
import time
import subprocess
from datetime import datetime
import threading
import logging
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
Bootstrap(app)

# 配置文件路径
CONFIG_FILE = '/etc/smartdns/smartdns.conf'
CONFIG_BACKUP = '/etc/smartdns/smartdns.conf.bak'
CONFIG_BACKUP_DIR = '/etc/smartdns/backups/'
SERVICE_NAME = 'smartdns'
BASE_CONFIG_PATH = '/etc/smartdns/'

# 确保备份目录存在
if not os.path.exists(CONFIG_BACKUP_DIR):
    os.makedirs(CONFIG_BACKUP_DIR)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 用于记录任务上次执行时间的字典，避免重复执行
last_execution_times = {}

def validate_domains(content):
    """验证内容是否包含有效的域名，支持顶级域名和国际化域名（Punycode）"""
    # 支持顶级域名（如 cn、com）、子域名和 Punycode 编码的国际化域名
    domain_pattern = re.compile(
        r'^(?:(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+)?'
        r'(?:[a-zA-Z]{2,}|xn--[a-zA-Z0-9-]{2,})$',
        re.IGNORECASE
    )
    lines = content.splitlines()
    valid_domains = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if domain_pattern.match(line):
            valid_domains += 1
        else:
            logger.warning(f"无效的域名: {line}")
            return False, f"无效的域名: {line}"
    if valid_domains == 0:
        return False, "没有有效的域名"
    return True, "验证通过"

def generate_domain_filename(friendly_name):
    """生成标准化的域名组文件名"""
    return f"{BASE_CONFIG_PATH}{friendly_name.lower().replace(' ', '_')}_domains.conf"

def infer_server_type(address):
    """根据服务器地址推断服务器类型"""
    address = address.lower().strip()
    if address.startswith('https://'):
        return 'server-https'
    if address.startswith('tls://') or ':853' in address:
        return 'server-tls'
    return 'server'

def read_config():
    """读取配置文件并解析"""
    config = {
        'bind': {'port': '5353', 'tcp_port': '5353'},
        'cache': {
            'enabled': 'yes',
            'size': '32768',
            'persist': 'yes',
            'file': '/etc/smartdns/cache.db',
            'checkpoint_time': '600'
        },
        'prefetch': {'enabled': 'yes'},
        'expired': {
            'enabled': 'yes',
            'ttl': '600',
            'reply_ttl': '1',
            'prefetch_time': '1200'
        },
        'ipv6': {'force_aaaa_soa': 'yes'},
        'servers': [],
        'domain_sets': []
    }
    
    try:
        if not os.path.exists(CONFIG_FILE):
            logger.warning(f"配置文件 {CONFIG_FILE} 不存在")
            return config

        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            i = 0
            raw_servers = []
            while i < len(lines):
                line = lines[i].strip()
                if not line or line.startswith('#'):
                    i += 1
                    continue
                    
                parts = line.split()
                if not parts:
                    i += 1
                    continue
                    
                if parts[0] == 'bind':
                    config['bind']['port'] = parts[1].split(':')[-1] if len(parts) > 1 else '5353'
                elif parts[0] == 'bind-tcp':
                    config['bind']['tcp_port'] = parts[1].split(':')[-1] if len(parts) > 1 else '5353'
                elif parts[0] == 'cache-size':
                    config['cache']['size'] = parts[1] if len(parts) > 1 else '32768'
                    config['cache']['enabled'] = 'yes'
                elif parts[0] == 'cache-persist':
                    config['cache']['persist'] = parts[1] if len(parts) > 1 else 'yes'
                elif parts[0] == 'cache-file':
                    config['cache']['file'] = parts[1] if len(parts) > 1 else '/etc/smartdns/cache.db'
                elif parts[0] == 'cache-checkpoint-time':
                    config['cache']['checkpoint_time'] = parts[1] if len(parts) > 1 else '600'
                elif parts[0] == 'prefetch-domain':
                    config['prefetch']['enabled'] = parts[1] if len(parts) > 1 else 'yes'
                elif parts[0] == 'serve-expired':
                    config['expired']['enabled'] = parts[1] if len(parts) > 1 else 'yes'
                elif parts[0] == 'serve-expired-ttl':
                    config['expired']['ttl'] = parts[1] if len(parts) > 1 else '600'
                elif parts[0] == 'serve-expired-reply-ttl':
                    config['expired']['reply_ttl'] = parts[1] if len(parts) > 1 else '1'
                elif parts[0] == 'serve-expired-prefetch-time':
                    config['expired']['prefetch_time'] = parts[1] if len(parts) > 1 else '1200'
                elif parts[0] == 'force-AAAA-SOA':
                    config['ipv6']['force_aaaa_soa'] = parts[1] if len(parts) > 1 else 'yes'
                elif parts[0].startswith('server'):
                    if len(parts) > 1:
                        server_info = {'address': parts[1], 'type': parts[0], 'group': '通用'}
                        if len(parts) > 2:
                            options = parts[2:]
                            for j in range(len(options)):
                                if options[j] == '-group' and j + 1 < len(options):
                                    server_info['group'] = options[j + 1]
                                    break
                        raw_servers.append(server_info)
                elif parts[0] == 'domain-set':
                    if len(parts) >= 5 and parts[1] == '-name' and parts[3] == '-file':
                        friendly_name = parts[2].split('-')[0] if '-' in parts[2] else parts[2]
                        domain_set_info = {
                            'name': parts[2],
                            'friendly_name': friendly_name,
                            'file': parts[4],
                            'group': friendly_name,
                            'source_url': '',
                            'last_updated': '',
                            'domain_count': 0,
                            'speed_check_mode': 'ping',
                            'response_mode': 'fastest',
                            'address_ipv6': False,
                            'update_schedule': {'frequency': 'none', 'time': '', 'day': ''}  # 确保默认值
                        }
                        while i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if next_line.startswith('# Source ='):
                                domain_set_info['source_url'] = next_line.replace('# Source =', '').strip()
                                i += 1
                            elif next_line.startswith('# Update-Schedule ='):
                                schedule_info = next_line.replace('# Update-Schedule =', '').strip().split(',')
                                if len(schedule_info) >= 2:
                                    domain_set_info['update_schedule']['frequency'] = schedule_info[0].strip()
                                    domain_set_info['update_schedule']['time'] = schedule_info[1].strip()
                                    if len(schedule_info) > 2:
                                        domain_set_info['update_schedule']['day'] = schedule_info[2].strip()
                                i += 1
                            else:
                                break
                        while i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if not next_line.startswith('domain-rules'):
                                break
                            rule_parts = next_line.split()
                            for j in range(len(rule_parts)):
                                if rule_parts[j] == '-speed-check-mode' and j + 1 < len(rule_parts):
                                    domain_set_info['speed_check_mode'] = rule_parts[j + 1]
                                elif rule_parts[j] == '-response-mode' and j + 1 < len(rule_parts):
                                    domain_set_info['response_mode'] = rule_parts[j + 1]
                                elif rule_parts[j] == '-address' and j + 1 < len(rule_parts) and rule_parts[j + 1] == '-6':
                                    domain_set_info['address_ipv6'] = True
                            i += 1
                        try:
                            if os.path.exists(domain_set_info['file']):
                                domain_count = 0
                                with open(domain_set_info['file'], 'r', encoding='utf-8') as df:
                                    for line in df:
                                        if line.strip() and not line.startswith('#'):
                                            domain_count += 1
                                domain_set_info['domain_count'] = domain_count
                                mtime = os.path.getmtime(domain_set_info['file'])
                                domain_set_info['last_updated'] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                            else:
                                domain_set_info['last_updated'] = '文件不存在'
                                domain_set_info['domain_count'] = 0
                        except Exception as e:
                            logger.error(f"读取域名文件 {domain_set_info['file']} 出错: {str(e)}")
                            domain_set_info['last_updated'] = '读取失败'
                            domain_set_info['domain_count'] = 0
                        config['domain_sets'].append(domain_set_info)
                i += 1

            server_dict = {}
            for server in raw_servers:
                key = (server['group'], server['type'])
                if key not in server_dict:
                    server_dict[key] = {
                        'type': server['type'],
                        'group': server['group'],
                        'addresses': []
                    }
                server_dict[key]['addresses'].append(server['address'])
            
            config['servers'] = list(server_dict.values())
    except Exception as e:
        logger.error(f"读取配置文件出错: {str(e)}")
    
    return config

def write_config(config):
    """将配置写入文件"""
    try:
        shutil.copy2(CONFIG_FILE, CONFIG_BACKUP)
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write("# SmartDNS 配置文件\n")
            f.write(f"bind [::]:{config['bind']['port']}\n")
            f.write(f"bind-tcp [::]:{config['bind']['tcp_port']}\n\n")
            if config['cache']['enabled'] == 'yes':
                f.write("# 缓存设置\n")
                f.write(f"cache-size {config['cache']['size']}\n")
                f.write(f"cache-persist {config['cache']['persist']}\n")
                f.write(f"cache-file {config['cache']['file']}\n")
                f.write(f"cache-checkpoint-time {config['cache']['checkpoint_time']}\n\n")
            f.write(f"# 缓存预获取\n")
            f.write(f"prefetch-domain {config['prefetch']['enabled']}\n")
            f.write(f"# 乐观缓存\n")
            f.write(f"serve-expired {config['expired']['enabled']}\n")
            f.write(f"serve-expired-ttl {config['expired']['ttl']}\n")
            f.write(f"serve-expired-reply-ttl {config['expired']['reply_ttl']}\n")
            f.write(f"serve-expired-prefetch-time {config['expired']['prefetch_time']}\n\n")
            f.write(f"# 全局禁用 IPv6\n")
            f.write(f"force-AAAA-SOA {config['ipv6']['force_aaaa_soa']}\n\n")
            f.write("# 非通用组服务器\n")
            for server in sorted([s for s in config['servers'] if s['group'] != '通用'], key=lambda x: x['group']):
                for address in server['addresses']:
                    f.write(f"# 所属域名组：{server['group']}\n")
                    f.write(f"{server['type']} {address} -group {server['group']} -exclude-default-group\n")
            f.write("\n# 通用组服务器\n")
            for server in [s for s in config['servers'] if s['group'] == '通用']:
                for address in server['addresses']:
                    f.write(f"{server['type']} {address}\n")
            f.write("\n# 域名组设置\n")
            for domain_set in config['domain_sets']:
                f.write(f"# {domain_set['group']}域名组文件路径和延迟测试方法 / IPv6是否启用等设置\n")
                f.write(f"domain-set -name {domain_set['name']} -file {domain_set['file']}\n")
                if domain_set.get('source_url'):
                    f.write(f"# Source = {domain_set['source_url']}\n")
                schedule = domain_set.get('update_schedule', {})
                if schedule.get('frequency') != 'none':
                    schedule_str = f"{schedule['frequency']},{schedule['time']}"
                    if schedule['frequency'] == 'weekly' and schedule.get('day'):
                        schedule_str += f",{schedule['day']}"
                    f.write(f"# Update-Schedule = {schedule_str}\n")
                rule = f"domain-rules /domain-set:{domain_set['name']}/ -c none -nameserver {domain_set['group']}"
                if domain_set['speed_check_mode'] != 'none':
                    rule += f" -speed-check-mode {domain_set['speed_check_mode']}"
                if domain_set['response_mode'] != 'none':
                    rule += f" -response-mode {domain_set['response_mode']}"
                if domain_set['address_ipv6']:
                    rule += f" -address -6"
                f.write(f"{rule}\n")
    except Exception as e:
        logger.error(f"写入配置文件出错: {str(e)}")
        raise

def update_domain_content_by_index(index, url, restart=True):
    """更新指定域名组的内容"""
    try:
        config = read_config()
        if 0 <= index < len(config['domain_sets']):
            session = requests.Session()
            retries = Retry(total=5, backoff_factor=2, status_forcelist=[502, 503, 504, 403, 429])
            session.mount('https://', HTTPAdapter(max_retries=retries))
            domain = url.split('/')[2] if '//' in url else url.split('/')[0]
            ip = resolve_domain_with_local_dns(domain)
            response = None
            if ip:
                logger.info(f"解析 {domain} 到 {ip}")
                try:
                    if '//' in url:
                        parts = url.split('//')
                        path = parts[1].split('/', 1)[1] if len(parts[1].split('/')) > 1 else ''
                        new_url = f"{parts[0]}//{ip}/{path}"
                    else:
                        path = url.split('/', 1)[1] if len(url.split('/')) > 1 else ''
                        new_url = f"{ip}/{path}"
                    headers = {'Host': domain}
                    response = session.get(new_url, timeout=30, headers=headers, verify=False)
                    if response.status_code == 200:
                        logger.info(f"从 IP {ip} 成功获取内容")
                    else:
                        logger.warning(f"IP 请求失败，状态码 {response.status_code}，回退到域名")
                        response = None
                except Exception as ip_error:
                    logger.error(f"IP 请求失败: {str(ip_error)}，回退到域名")
            if not response or response.status_code != 200:
                response = session.get(url, timeout=30)
            if response.status_code == 200:
                content = response.text
                is_valid, validation_message = validate_domains(content)
                if not is_valid:
                    logger.error(f"域名验证失败: {validation_message}")
                    return False, validation_message, False
                try:
                    with open(config['domain_sets'][index]['file'], 'w', encoding='utf-8') as f:
                        f.write(content)
                    mtime = os.path.getmtime(config['domain_sets'][index]['file'])
                    config['domain_sets'][index]['last_updated'] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                    config['domain_sets'][index]['domain_count'] = len([line for line in content.splitlines() if line.strip() and not line.startswith('#')])
                    write_config(config)
                    restarted = False
                    restart_message = ""
                    if restart:
                        def delayed_restart():
                            time.sleep(1)
                            success, restart_message = restart_service()
                            if not success:
                                logger.error(f"服务重启失败: {restart_message}")
                        threading.Thread(target=delayed_restart, daemon=True).start()
                        restarted = True
                    logger.info(f"成功更新域名组 {config['domain_sets'][index]['name']}")
                    return True, "更新成功", restarted
                except Exception as e:
                    logger.error(f"保存文件内容出错: {str(e)}")
                    return False, f"保存文件内容出错：{str(e)}", False
            else:
                logger.error(f"从 URL 获取内容失败，状态码: {response.status_code}")
                return False, f"从URL获取内容失败，状态码：{response.status_code}", False
        else:
            logger.error("无效的域名组索引")
            return False, "无效的域名组索引", False
    except Exception as e:
        logger.error(f"更新内容出错: {str(e)}")
        return False, f"更新内容出错: {str(e)}", False

def matches_current_time(schedule_info):
    """检查当前时间是否匹配设置的更新时间"""
    current_time = datetime.now()
    current_hour_minute = current_time.strftime("%H:%M")
    current_day = current_time.strftime("%A").lower()  # 如 'monday'

    frequency = schedule_info.get('frequency', 'none')
    set_time = schedule_info.get('time', '')
    set_day = schedule_info.get('day', '').lower()

    if frequency == 'none' or not set_time:
        return False

    # 检查时间是否匹配
    if current_hour_minute != set_time:
        return False

    # 对于每周频率，额外检查星期几
    if frequency == 'weekly' and set_day:
        if current_day != set_day:
            return False

    return True

def run_custom_scheduler():
    """自定义调度器，每分钟检查当前时间与设置时间的一致性"""
    logger.info("自定义调度器线程启动")
    while True:
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            config = read_config()
            for index, domain_set in enumerate(config['domain_sets']):
                schedule_info = domain_set.get('update_schedule', {})
                source_url = domain_set.get('source_url', '')
                name = domain_set.get('name', '未知')

                if schedule_info.get('frequency', 'none') == 'none' or not source_url:
                    continue

                # 检查当前时间是否匹配设置时间
                if matches_current_time(schedule_info):
                    # 检查是否已在本周期内执行过
                    last_exec_key = f"{name}_{schedule_info['frequency']}_{schedule_info.get('day', '')}"
                    last_exec_time = last_execution_times.get(last_exec_key)
                    current_day = datetime.now().strftime("%Y-%m-%d")
                    if last_exec_time and last_exec_time.startswith(current_day):
                        logger.info(f"任务 {name} 今天已执行，跳过")
                        continue

                    logger.info(f"时间匹配，执行更新任务 for {name} at {current_time}")
                    success, message, restarted = update_domain_content_by_index(index, source_url)
                    if success:
                        logger.info(f"更新任务 {name} 成功: {message}")
                        last_execution_times[last_exec_key] = current_time
                    else:
                        logger.error(f"更新任务 {name} 失败: {message}")
                #else:
                #    logger.debug(f"时间不匹配 for {name}: 当前 {current_time}, 设置 {schedule_info}")
            time.sleep(30)  # 每半分钟检查一次
        except Exception as e:
            logger.error(f"自定义调度器出错: {str(e)}")
            time.sleep(30)

# 启动自定义调度器线程
scheduler_thread = threading.Thread(target=run_custom_scheduler, daemon=True)
scheduler_thread.start()

def resolve_domain_with_local_dns(domain):
    """通过本机DNS解析域名"""
    try:
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['127.0.0.1']
        resolver.port = 53
        logger.info(f"使用 127.0.0.1:53 解析 {domain}")
        answers = resolver.resolve(domain, 'A')
        if answers:
            return answers[0].address
    except Exception as e:
        logger.error(f"解析域名 {domain} 出错: {str(e)}")
    return None

def restart_service():
    """重启 SmartDNS 服务"""
    try:
        subprocess.run(['systemctl', 'restart', SERVICE_NAME], check=True)
        return True, "服务重启成功"
    except Exception as e:
        return False, f"服务重启失败: {str(e)}"

def backup_config():
    """备份配置文件"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(CONFIG_BACKUP_DIR, f'smartdns_{timestamp}.bak')
        shutil.copy2(CONFIG_FILE, backup_path)
        return True, f"配置已备份到 {backup_path}"
    except Exception as e:
        return False, f"备份失败: {str(e)}"

def restore_config(backup_file):
    """从备份文件还原配置"""
    try:
        backup_path = os.path.join(CONFIG_BACKUP_DIR, backup_file)
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, CONFIG_FILE)
            def delayed_restart():
                time.sleep(1)
                success, restart_message = restart_service()
                if not success:
                    logger.error(f"服务重启失败: {restart_message}")
            threading.Thread(target=delayed_restart, daemon=True).start()
            return True, "配置还原成功，服务正在重启"
        else:
            return False, "备份文件不存在"
    except Exception as e:
        return False, f"还原失败: {str(e)}"

def test_dns_resolution(domain="www.google.com"):
    """测试 DNS 解析"""
    try:
        result = subprocess.run(['nslookup', domain, '127.0.0.1'], capture_output=True, text=True, timeout=5)
        output = result.stdout
        logger.info(f"DNS 测试输出已获取")
        ip_addresses = []
        found_answer_section = False
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Non-authoritative answer:"):
                found_answer_section = True
                continue
            if found_answer_section and line.startswith("Address:"):
                ip = line.split()[-1]
                if ip != "127.0.0.1" and "#53" not in ip:
                    ip_addresses.append(ip)
        if ip_addresses:
            # 限制最多显示前两个 IP 地址
            displayed_ips = ip_addresses[:2]
            total_ips = len(ip_addresses)
            if total_ips > 2:
                return True, f"DNS 解析成功: {domain} to {', '.join(displayed_ips)} (共 {total_ips} 个结果，仅显示前 2 个)"
            return True, f"DNS 解析成功: {domain} to {', '.join(displayed_ips)}"
        return False, f"DNS 解析失败: 没有有效结果\n{output}"
    except subprocess.TimeoutExpired:
        return False, "DNS 解析失败: 请求超时"
    except Exception as e:
        logger.error(f"DNS 测试出错: {str(e)}")
        return False, f"DNS 解析失败: {str(e)}"


@app.route('/')
def index():
    config = read_config()
    return render_template('index.html', config=config)

@app.route('/get_domain_content/<int:index>', methods=['GET'])
def get_domain_content(index):
    try:
        config = read_config()
        if 0 <= index < len(config['domain_sets']):
            domain_set = config['domain_sets'][index]
            if domain_set['domain_count'] > 1000:
                return jsonify({'status': 'error', 'message': '域名表过大,无法加载'})
            if os.path.exists(domain_set['file']):
                with open(domain_set['file'], 'r', encoding='utf-8') as f:
                    content = f.read()
                return jsonify({'status': 'success', 'content': content})
            else:
                return jsonify({'status': 'error', 'message': '文件不存在'})
        else:
            return jsonify({'status': 'error', 'message': '无效的域名组索引'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'加载内容出错: {str(e)}'})

@app.route('/update', methods=['POST'])
def update_config():
    try:
        config = read_config()
        config['bind']['port'] = request.form.get('bind_port', '5353')
        config['bind']['tcp_port'] = request.form.get('bind_tcp_port', '5353')
        config['cache']['enabled'] = request.form.get('cache_enabled', 'no')
        config['cache']['size'] = request.form.get('cache_size', '32768')
        config['cache']['persist'] = request.form.get('cache_persist', 'yes')
        config['cache']['file'] = request.form.get('cache_file', '/etc/smartdns/cache.db')
        config['cache']['checkpoint_time'] = request.form.get('cache_checkpoint_time', '600')
        config['prefetch']['enabled'] = request.form.get('prefetch_enabled', 'yes')
        config['expired']['enabled'] = request.form.get('expired_enabled', 'yes')
        config['expired']['ttl'] = request.form.get('expired_ttl', '600')
        config['expired']['reply_ttl'] = request.form.get('expired_reply_ttl', '1')
        config['expired']['prefetch_time'] = request.form.get('expired_prefetch_time', '1200')
        config['ipv6']['force_aaaa_soa'] = request.form.get('force_aaaa_soa', 'yes')
        write_config(config)
        def delayed_restart():
            time.sleep(1)
            success, restart_message = restart_service()
            if not success:
                logger.error(f"服务重启失败: {restart_message}")
        threading.Thread(target=delayed_restart, daemon=True).start()
        flash('配置更新成功，SmartDNS 服务已重启！', 'success')
    except Exception as e:
        flash(f'更新配置出错：{str(e)}', 'success')
    return redirect(url_for('index'))

@app.route('/add_server', methods=['POST'])
def add_server():
    try:
        config = read_config()
        server_address = request.form.get('server_address')
        server_group = request.form.get('server_group', '通用')
        if server_address:
            server_type = infer_server_type(server_address)
            for server in config['servers']:
                if server['group'] == server_group and server['type'] == server_type:
                    server['addresses'].append(server_address)
                    break
            else:
                config['servers'].append({
                    'type': server_type,
                    'group': server_group,
                    'addresses': [server_address]
                })
            write_config(config)
            def delayed_restart():
                time.sleep(1)
                success, restart_message = restart_service()
                if not success:
                    logger.error(f"服务重启失败: {restart_message}")
            threading.Thread(target=delayed_restart, daemon=True).start()
            flash('服务器添加成功，SmartDNS 服务已重启！', 'success')
        else:
            flash('服务器地址不能为空！', 'success')
    except Exception as e:
        flash(f'添加服务器出错：{str(e)}', 'success')
    return redirect(url_for('index'))

@app.route('/delete_server/<int:index>')
def delete_server(index):
    try:
        config = read_config()
        if 0 <= index < len(config['servers']):
            config['servers'].pop(index)
            write_config(config)
            def delayed_restart():
                time.sleep(1)
                success, restart_message = restart_service()
                if not success:
                    logger.error(f"服务重启失败: {restart_message}")
            threading.Thread(target=delayed_restart, daemon=True).start()
            flash('服务器删除成功，SmartDNS 服务已重启！', 'success')
        else:
            flash('无效的服务器索引！', 'success')
    except Exception as e:
        flash(f'删除服务器出错：{str(e)}', 'success')
    return redirect(url_for('index'))

@app.route('/update_server/<int:index>', methods=['POST'])
def update_server(index):
    try:
        config = read_config()
        if 0 <= index < len(config['servers']):
            addresses = request.form.get('addresses', '').split(',')
            addresses = [addr.strip() for addr in addresses if addr.strip()]
            group = request.form.get('group', '通用')
            if not addresses:
                return jsonify({'status': 'error', 'message': '服务器地址不能为空', 'restarted': False})
            server_type = infer_server_type(addresses[0])
            config['servers'][index] = {
                'type': server_type,
                'group': group,
                'addresses': addresses
            }
            write_config(config)
            def delayed_restart():
                time.sleep(1)
                success, restart_message = restart_service()
                if not success:
                    logger.error(f"服务重启失败: {restart_message}")
            threading.Thread(target=delayed_restart, daemon=True).start()
            return jsonify({'status': 'success', 'message': '已保存，服务正在重启', 'restarted': True})
        else:
            return jsonify({'status': 'error', 'message': '无效的服务器索引', 'restarted': False})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'更新服务器出错: {str(e)}', 'restarted': False})

@app.route('/add_domain_set', methods=['POST'])
def add_domain_set():
    try:
        config = read_config()
        friendly_name = request.form.get('friendly_name')
        source_url = request.form.get('source_url', '')
        speed_check_mode = request.form.get('speed_check_mode', 'ping')
        response_mode = request.form.get('response_mode', 'fastest')
        address_ipv6 = request.form.get('address_ipv6', 'no') == 'yes'
        update_frequency = request.form.get('update_frequency', 'none')
        update_time = request.form.get('update_time', '')
        update_day = request.form.get('update_day', '')
        if friendly_name:
            name = f"{friendly_name.lower().replace(' ', '-')}-domain-list"
            file_path = generate_domain_filename(friendly_name)
            domain_set = {
                'name': name,
                'friendly_name': friendly_name,
                'file': file_path,
                'group': friendly_name,
                'source_url': source_url,
                'domain_count': 0,
                'last_updated': '尚未更新',
                'speed_check_mode': speed_check_mode,
                'response_mode': response_mode,
                'address_ipv6': address_ipv6,
                'update_schedule': {
                    'frequency': update_frequency,
                    'time': update_time,
                    'day': update_day if update_frequency == 'weekly' else ''
                }
            }
            config['domain_sets'].append(domain_set)
            write_config(config)
            def delayed_restart():
                time.sleep(1)
                success, restart_message = restart_service()
                if not success:
                    logger.error(f"服务重启失败: {restart_message}")
            threading.Thread(target=delayed_restart, daemon=True).start()
            flash('域名组添加成功，SmartDNS 服务已重启！', 'success')
        else:
            flash('域名组名称不能为空！', 'success')
    except Exception as e:
        flash(f'添加域名组出错：{str(e)}', 'success')
    return redirect(url_for('index'))

@app.route('/delete_domain_set/<int:index>')
def delete_domain_set(index):
    try:
        config = read_config()
        if 0 <= index < len(config['domain_sets']):
            config['domain_sets'].pop(index)
            write_config(config)
            def delayed_restart():
                time.sleep(1)
                success, restart_message = restart_service()
                if not success:
                    logger.error(f"服务重启失败: {restart_message}")
            threading.Thread(target=delayed_restart, daemon=True).start()
            flash('域名组删除成功，SmartDNS 服务已重启！', 'success')
        else:
            flash('无效的域名组索引！', 'success')
    except Exception as e:
        flash(f'删除域名组出错：{str(e)}', 'success')
    return redirect(url_for('index'))

@app.route('/update_domain_set/<int:index>', methods=['POST'])
def update_domain_set(index):
    try:
        config = read_config()
        if 0 <= index < len(config['domain_sets']):
            friendly_name = request.form.get('friendly_name', '')
            if not friendly_name:
                return jsonify({'status': 'error', 'message': '域名组名称不能为空', 'restarted': False})
            update_frequency = request.form.get('update_frequency', 'none')
            update_time = request.form.get('update_time', '')
            update_day = request.form.get('update_day', '')
            config['domain_sets'][index]['friendly_name'] = friendly_name
            config['domain_sets'][index]['name'] = f"{friendly_name.lower().replace(' ', '-')}-domain-list"
            config['domain_sets'][index]['file'] = generate_domain_filename(friendly_name)
            config['domain_sets'][index]['source_url'] = request.form.get('source_url', '')
            config['domain_sets'][index]['group'] = friendly_name
            config['domain_sets'][index]['speed_check_mode'] = request.form.get('speed_check_mode', 'ping')
            config['domain_sets'][index]['response_mode'] = request.form.get('response_mode', 'fastest')
            config['domain_sets'][index]['address_ipv6'] = request.form.get('address_ipv6', 'no') == 'yes'
            config['domain_sets'][index]['update_schedule'] = {
                'frequency': update_frequency,
                'time': update_time,
                'day': update_day if update_frequency == 'weekly' else ''
            }
            content = request.form.get('content', '')
            if content and config['domain_sets'][index]['domain_count'] <= 1000:
                is_valid, validation_message = validate_domains(content)
                if not is_valid:
                    return jsonify({'status': 'error', 'message': validation_message, 'restarted': False})
                try:
                    with open(config['domain_sets'][index]['file'], 'w', encoding='utf-8') as f:
                        f.write(content)
                    mtime = os.path.getmtime(config['domain_sets'][index]['file'])
                    config['domain_sets'][index]['last_updated'] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                    config['domain_sets'][index]['domain_count'] = len([line for line in content.splitlines() if line.strip() and not line.startswith('#')])
                except Exception as e:
                    return jsonify({'status': 'error', 'message': f'保存文件内容出错：{str(e)}', 'restarted': False})
            write_config(config)
            def delayed_restart():
                time.sleep(1)
                success, restart_message = restart_service()
                if not success:
                    logger.error(f"服务重启失败: {restart_message}")
            threading.Thread(target=delayed_restart, daemon=True).start()
            return jsonify({'status': 'success', 'message': '已保存，服务正在重启', 'restarted': True})
        else:
            return jsonify({'status': 'error', 'message': '无效的域名组索引', 'restarted': False})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'更新域名组出错: {str(e)}', 'restarted': False})

@app.route('/update_domain_content/<int:index>', methods=['POST'])
def update_domain_content(index):
    try:
        config = read_config()
        if 0 <= index < len(config['domain_sets']):
            url = request.form.get('url', '')
            if not url:
                return jsonify({'status': 'error', 'message': 'URL 不能为空', 'restarted': False})
            success, message, restarted = update_domain_content_by_index(index, url)
            if success:
                content = ''
                if os.path.exists(config['domain_sets'][index]['file']):
                    with open(config['domain_sets'][index]['file'], 'r', encoding='utf-8') as f:
                        content = f.read()
                return jsonify({'status': 'success', 'message': message + (', 服务正在重启' if restarted else ''), 'content': content, 'restarted': restarted})
            else:
                return jsonify({'status': 'error', 'message': message, 'restarted': False})
        else:
            return jsonify({'status': 'error', 'message': '无效的域名组索引', 'restarted': False})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'更新内容出错: {str(e)}', 'restarted': False})

@app.route('/backup', methods=['POST'])
def backup():
    success, message = backup_config()
    flash(message, 'success')
    return redirect(url_for('index'))

@app.route('/restore', methods=['POST'])
def restore():
    backup_file = request.form.get('backup_file', '')
    if not backup_file:
        flash("未选择备份文件！", 'success')
        return redirect(url_for('index'))
    success, message = restore_config(backup_file)
    flash(message, 'success')
    return redirect(url_for('index'))

@app.route('/restart', methods=['POST'])
def restart():
    success, message = restart_service()
    flash(message, 'success')
    return redirect(url_for('index'))

@app.route('/test_dns', methods=['POST'])
def test_dns():
    domain = request.form.get('test_domain', 'www.google.com')
    success, message = test_dns_resolution(domain)
    flash(message, 'success')
    return redirect(url_for('index'))

@app.route('/backups', methods=['GET'])
def list_backups():
    try:
        backups = os.listdir(CONFIG_BACKUP_DIR)
        return jsonify({'status': 'success', 'backups': backups})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    logger.info("应用启动，启动自定义调度器")
    app.run(host='0.0.0.0', port=8088, debug=True)