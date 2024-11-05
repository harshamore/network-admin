import streamlit as st
import paramiko
import openai
import pandas as pd
import plotly.express as px
from io import StringIO
import os
from datetime import datetime, timedelta

# [Previous imports and initial setup remain the same]

# Enhance session state to include system information
if 'system_info' not in st.session_state:
    st.session_state.system_info = {
        'network_interfaces': [],
        'os_version': '',
        'cpu_info': '',
        'memory_total': '',
        'disk_devices': [],
        'package_manager': '',
        'init_system': '',
        'kernel_version': '',
        'available_commands': []
    }

def get_system_info(ssh_client):
    """Gather comprehensive system information"""
    system_info = {}
    
    try:
        # Get network interfaces
        stdin, stdout, stderr = ssh_client.exec_command('ip link show')
        output = stdout.read().decode()
        interfaces = []
        for line in output.split('\n'):
            if ':' in line and '@' not in line:
                interface = line.split(':')[1].strip()
                interfaces.append(interface)
        system_info['network_interfaces'] = interfaces

        # Get OS version
        stdin, stdout, stderr = ssh_client.exec_command('cat /etc/os-release')
        os_info = stdout.read().decode()
        system_info['os_version'] = os_info

        # Get CPU info
        stdin, stdout, stderr = ssh_client.exec_command('lscpu')
        cpu_info = stdout.read().decode()
        system_info['cpu_info'] = cpu_info

        # Get memory info
        stdin, stdout, stderr = ssh_client.exec_command('free -h')
        memory_info = stdout.read().decode()
        system_info['memory_total'] = memory_info

        # Get disk devices
        stdin, stdout, stderr = ssh_client.exec_command('lsblk')
        disk_info = stdout.read().decode()
        system_info['disk_devices'] = disk_info

        # Determine package manager
        package_managers = {
            'apt': 'apt-get -v',
            'dnf': 'dnf --version',
            'yum': 'yum --version',
            'pacman': 'pacman --version',
            'zypper': 'zypper --version'
        }
        
        for pm, cmd in package_managers.items():
            stdin, stdout, stderr = ssh_client.exec_command(cmd)
            if stdout.read():
                system_info['package_manager'] = pm
                break

        # Get init system
        stdin, stdout, stderr = ssh_client.exec_command('ps -p 1')
        init_output = stdout.read().decode()
        if 'systemd' in init_output:
            system_info['init_system'] = 'systemd'
        elif 'init' in init_output:
            system_info['init_system'] = 'sysvinit'
        else:
            system_info['init_system'] = 'unknown'

        # Get kernel version
        stdin, stdout, stderr = ssh_client.exec_command('uname -r')
        system_info['kernel_version'] = stdout.read().decode().strip()

        # Get available commands
        stdin, stdout, stderr = ssh_client.exec_command('compgen -c | sort -u')
        available_commands = stdout.read().decode().split('\n')
        system_info['available_commands'] = [cmd for cmd in available_commands if cmd]

        return system_info
    except Exception as e:
        st.error(f"Error gathering system information: {str(e)}")
        return {}

def establish_ssh_connection(host, username, key_data):
    try:
        key_path = "temp_key.pem"
        with open(key_path, "wb") as f:
            f.write(key_data)
        os.chmod(key_path, 0o600)

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        private_key = paramiko.RSAKey(filename=key_path)
        ssh.connect(hostname=host, username=username, pkey=private_key)
        
        # Get comprehensive system information
        system_info = get_system_info(ssh)
        st.session_state.system_info = system_info
        
        os.remove(key_path)
        return ssh
    except Exception as e:
        if os.path.exists(key_path):
            os.remove(key_path)
        raise e

def create_system_context():
    """Create a detailed system context for OpenAI"""
    info = st.session_state.system_info
    
    # Extract relevant CPU information
    cpu_details = "Unknown CPU"
    for line in info['cpu_info'].split('\n'):
        if "Model name" in line:
            cpu_details = line.split(':')[1].strip()
            break

    # Extract memory information
    memory_details = "Unknown memory"
    for line in info['memory_total'].split('\n'):
        if "Mem:" in line:
            memory_details = line.split()[1]
            break

    # Parse OS information
    os_details = "Unknown OS"
    for line in info['os_version'].split('\n'):
        if "PRETTY_NAME" in line:
            os_details = line.split('=')[1].strip().strip('"')
            break

    context = f"""You are a Linux system administrator managing a system with the following specifications:

OS: {os_details}
Kernel: {info['kernel_version']}
CPU: {cpu_details}
Memory: {memory_details}
Package Manager: {info['package_manager']}
Init System: {info['init_system']}
Network Interfaces: {', '.join(info['network_interfaces'])}

When generating commands:
1. Use {info['package_manager']} for package management
2. Use {info['init_system']} syntax for service management
3. Use available network interfaces: {', '.join(info['network_interfaces'])}
4. Consider the system's resources when suggesting commands:
   - Memory-intensive commands should be mindful of the {memory_details} total RAM
   - For disk operations, available devices: {info['disk_devices']}

System has these commands available: {', '.join(info['available_commands'][:100])}... (truncated)

Convert user requests into appropriate Linux commands that:
1. Use the correct package manager syntax
2. Use the correct service management commands
3. Use appropriate network interfaces
4. Consider system resources
5. Use available commands only
6. Add sudo when necessary

Respond with ONLY the command, no explanations."""

    return context

# [Previous helper functions remain the same]

if st.session_state.connected:
    # Display system information in sidebar
    with st.sidebar:
        st.subheader("System Information")
        st.write(f"OS: {st.session_state.system_info.get('os_version', '').split('\n')[0]}")
        st.write(f"Kernel: {st.session_state.system_info.get('kernel_version', '')}")
        st.write(f"Package Manager: {st.session_state.system_info.get('package_manager', '')}")
        st.write("Network Interfaces:")
        for interface in st.session_state.system_info.get('network_interfaces', []):
            st.write(f"- {interface}")

    # Update the OpenAI interaction to use system context
    if prompt := st.chat_input("What would you like to do?"):
        try:
            system_context = create_system_context()
            
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_context},
                    {"role": "user", "content": prompt}
                ]
            )
            
            command = response.choices[0].message.content.strip()
            
            # Execute and display results as before
            # [Rest of the execution code remains the same]
        except Exception as e:
            st.error(f"An error occurred: {e}")
