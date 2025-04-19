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
            'enabled': 'no',
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
            print(f"Config file {CONFIG_FILE} does not exist")
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
                            'address_ipv6': False
                        }
                        if i + 1 < len(lines) and lines[i + 1].strip().startswith('# Source ='):
                            domain_set_info['source_url'] = lines[i + 1].strip().replace('# Source =', '').strip()
                            i += 1
                        # 解析 domain-rules
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
                                # 只计算 domain_count，不加载 content
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
                            print(f"Error reading domain file {domain_set_info['file']}: {str(e)}")
                            domain_set_info['last_updated'] = '读取失败'
                            domain_set_info['domain_count'] = 0
                        config['domain_sets'].append(domain_set_info)
                i += 1

            # 合并同一组和类型的服务器
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
        print(f"Error reading config file: {str(e)}")
    
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
                rule = f"domain-rules /domain-set:{domain_set['name']}/ -c none -nameserver {domain_set['group']}"
                if domain_set['speed_check_mode'] != 'none':
                    rule += f" -speed-check-mode {domain_set['speed_check_mode']}"
                if domain_set['response_mode'] != 'none':
                    rule += f" -response-mode {domain_set['response_mode']}"
                if domain_set['address_ipv6']:
                    rule += f" -address -6"
                f.write(f"{rule}\n")
    except Exception as e:
        print(f"Error writing config file: {str(e)}")
        raise

def resolve_domain_with_local_dns(domain):
    """通过本机DNS解析域名"""
    try:
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['127.0.0.1']
        resolver.port = 53
        print(f"Resolving {domain} using 127.0.0.1:53")
        answers = resolver.resolve(domain, 'A')
        if answers:
            return answers[0].address
    except Exception as e:
        print(f"Error resolving domain {domain}: {str(e)}")
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
            return True, "配置还原成功"
        else:
            return False, "备份文件不存在"
    except Exception as e:
        return False, f"还原失败: {str(e)}"

def test_dns_resolution(domain="www.google.com"):
    """测试 DNS 解析"""
    try:
        result = subprocess.run(['nslookup', domain, '127.0.0.1'], capture_output=True, text=True, timeout=5)
        output = result.stdout
        print(f"nslookup output for {domain}:\n{output}")
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
            return True, f"DNS 解析成功: {domain} -> {', '.join(ip_addresses)}"
        return False, f"DNS 解析失败: 没有有效结果\n{output}"
    except subprocess.TimeoutExpired:
        return False, "DNS 解析失败: 请求超时"
    except Exception as e:
        print(f"Error during nslookup for {domain}: {str(e)}")
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
        flash('配置更新成功！', 'success')
    except Exception as e:
        flash(f'更新配置出错：{str(e)}', 'danger')
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
            flash('服务器添加成功！', 'success')
        else:
            flash('服务器地址不能为空！', 'danger')
    except Exception as e:
        flash(f'添加服务器出错：{str(e)}', 'danger')
    return redirect(url_for('index'))

@app.route('/delete_server/<int:index>')
def delete_server(index):
    try:
        config = read_config()
        if 0 <= index < len(config['servers']):
            config['servers'].pop(index)
            write_config(config)
            flash('服务器删除成功！', 'success')
        else:
            flash('无效的服务器索引！', 'danger')
    except Exception as e:
        flash(f'删除服务器出错：{str(e)}', 'danger')
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
                return jsonify({'status': 'error', 'message': '服务器地址不能为空'})
            server_type = infer_server_type(addresses[0])
            config['servers'][index] = {
                'type': server_type,
                'group': group,
                'addresses': addresses
            }
            write_config(config)
            return jsonify({'status': 'success', 'message': '已保存'})
        else:
            return jsonify({'status': 'error', 'message': '无效的服务器索引'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'更新服务器出错: {str(e)}'})

@app.route('/add_domain_set', methods=['POST'])
def add_domain_set():
    try:
        config = read_config()
        friendly_name = request.form.get('friendly_name')
        source_url = request.form.get('source_url', '')
        speed_check_mode = request.form.get('speed_check_mode', 'ping')
        response_mode = request.form.get('response_mode', 'fastest')
        address_ipv6 = request.form.get('address_ipv6', 'no') == 'yes'
        if friendly_name:
            name = f"{friendly_name.lower().replace(' ', '-')}-domain-list"
            file_path = generate_domain_filename(friendly_name)
            config['domain_sets'].append({
                'name': name,
                'friendly_name': friendly_name,
                'file': file_path,
                'group': friendly_name,
                'source_url': source_url,
                'domain_count': 0,
                'last_updated': '尚未更新',
                'speed_check_mode': speed_check_mode,
                'response_mode': response_mode,
                'address_ipv6': address_ipv6
            })
            write_config(config)
            flash('域名组添加成功！', 'success')
        else:
            flash('域名组名称不能为空！', 'danger')
    except Exception as e:
        flash(f'添加域名组出错：{str(e)}', 'danger')
    return redirect(url_for('index'))

@app.route('/delete_domain_set/<int:index>')
def delete_domain_set(index):
    try:
        config = read_config()
        if 0 <= index < len(config['domain_sets']):
            config['domain_sets'].pop(index)
            write_config(config)
            flash('域名组删除成功！', 'success')
        else:
            flash('无效的域名组索引！', 'danger')
    except Exception as e:
        flash(f'删除域名组出错：{str(e)}', 'danger')
    return redirect(url_for('index'))

@app.route('/update_domain_set/<int:index>', methods=['POST'])
def update_domain_set(index):
    try:
        config = read_config()
        if 0 <= index < len(config['domain_sets']):
            friendly_name = request.form.get('friendly_name', '')
            if not friendly_name:
                return jsonify({'status': 'error', 'message': '域名组名称不能为空'})
            config['domain_sets'][index]['friendly_name'] = friendly_name
            config['domain_sets'][index]['name'] = f"{friendly_name.lower().replace(' ', '-')}-domain-list"
            config['domain_sets'][index]['file'] = generate_domain_filename(friendly_name)
            config['domain_sets'][index]['source_url'] = request.form.get('source_url', '')
            config['domain_sets'][index]['group'] = friendly_name
            config['domain_sets'][index]['speed_check_mode'] = request.form.get('speed_check_mode', 'ping')
            config['domain_sets'][index]['response_mode'] = request.form.get('response_mode', 'fastest')
            config['domain_sets'][index]['address_ipv6'] = request.form.get('address_ipv6', 'no') == 'yes'
            content = request.form.get('content', '')
            # 只在 domain_count <= 1000 且 content 非空时更新内容
            if content and config['domain_sets'][index]['domain_count'] <= 1000:
                try:
                    with open(config['domain_sets'][index]['file'], 'w', encoding='utf-8') as f:
                        f.write(content)
                    mtime = os.path.getmtime(config['domain_sets'][index]['file'])
                    config['domain_sets'][index]['last_updated'] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                    config['domain_sets'][index]['domain_count'] = len([line for line in content.splitlines() if line.strip() and not line.startswith('#')])
                except Exception as e:
                    return jsonify({'status': 'error', 'message': f'保存文件内容出错：{str(e)}'})
            write_config(config)
            return jsonify({'status': 'success', 'message': '已保存'})
        else:
            return jsonify({'status': 'error', 'message': '无效的域名组索引'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'更新域名组出错: {str(e)}'})

@app.route('/update_domain_content/<int:index>', methods=['POST'])
def update_domain_content(index):
    try:
        config = read_config()
        if 0 <= index < len(config['domain_sets']):
            url = request.form.get('url', '')
            if not url:
                return jsonify({'status': 'error', 'message': 'URL 不能为空'})
            session = requests.Session()
            retries = Retry(total=5, backoff_factor=2, status_forcelist=[502, 503, 504, 403, 429])
            session.mount('https://', HTTPAdapter(max_retries=retries))
            domain = url.split('/')[2] if '//' in url else url.split('/')[0]
            ip = resolve_domain_with_local_dns(domain)
            response = None
            if ip:
                print(f"Resolved {domain} to {ip}")
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
                        print(f"Successfully fetched content from IP {ip}")
                    else:
                        print(f"IP request failed with status {response.status_code}, falling back to domain")
                        response = None
                except Exception as ip_error:
                    print(f"IP request failed: {str(ip_error)}, falling back to domain")
            if not response or response.status_code != 200:
                response = session.get(url, timeout=30)
            if response.status_code == 200:
                content = response.text
                try:
                    with open(config['domain_sets'][index]['file'], 'w', encoding='utf-8') as f:
                        f.write(content)
                    mtime = os.path.getmtime(config['domain_sets'][index]['file'])
                    config['domain_sets'][index]['last_updated'] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                    config['domain_sets'][index]['domain_count'] = len([line for line in content.splitlines() if line.strip() and not line.startswith('#')])
                    write_config(config)
                    return jsonify({'status': 'success', 'message': '更新成功', 'content': content})
                except Exception as e:
                    return jsonify({'status': 'error', 'message': f'保存文件内容出错：{str(e)}'})
            else:
                return jsonify({'status': 'error', 'message': f'从URL获取内容失败，状态码：{response.status_code}'})
        else:
            return jsonify({'status': 'error', 'message': '无效的域名组索引'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'更新内容出错: {str(e)}'})

@app.route('/backup', methods=['POST'])
def backup():
    success, message = backup_config()
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    return redirect(url_for('index'))

@app.route('/restore', methods=['POST'])
def restore():
    backup_file = request.form.get('backup_file', '')
    if not backup_file:
        flash("未选择备份文件！", 'danger')
        return redirect(url_for('index'))
    success, message = restore_config(backup_file)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    return redirect(url_for('index'))

@app.route('/restart', methods=['POST'])
def restart():
    success, message = restart_service()
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    return redirect(url_for('index'))

@app.route('/test_dns', methods=['POST'])
def test_dns():
    domain = request.form.get('test_domain', 'www.google.com')
    success, message = test_dns_resolution(domain)
    flash(message, 'success' if success else 'danger')
    return redirect(url_for('index'))

@app.route('/backups', methods=['GET'])
def list_backups():
    try:
        backups = os.listdir(CONFIG_BACKUP_DIR)
        return jsonify({'status': 'success', 'backups': backups})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8088, debug=True)