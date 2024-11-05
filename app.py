import streamlit as st
import paramiko
import openai
import pandas as pd
import plotly.express as px
from io import StringIO
import os
from datetime import datetime, timedelta
import json

try:
    # Configure page settings
    st.set_page_config(page_title="Linux Admin Assistant", layout="wide")

    # Set OpenAI API key from Streamlit secrets
    openai.api_key = st.secrets["OPENAI_API_KEY"]

    # Initialize session states
    if 'messages' not in st.session_state:
        st.session_state.messages = {}  # Changed to dict to store messages per host
    if 'ssh_client' not in st.session_state:
        st.session_state.ssh_client = None
    if 'connected' not in st.session_state:
        st.session_state.connected = False
    if 'last_activity' not in st.session_state:
        st.session_state.last_activity = datetime.now()
    if 'connection_info' not in st.session_state:
        st.session_state.connection_info = {
            'host': '',
            'username': '',
            'key_data': None
        }
    if 'connections_history' not in st.session_state:
        st.session_state.connections_history = {}  # Store history of connections

    def process_and_visualize_command(command, output):
        try:
            # For top command
            if "top" in command:
                lines = output.strip().split('\n')
                processes = []
                header_found = False
                
                for line in lines:
                    if 'PID' in line and 'CPU' in line:
                        header_found = True
                        continue
                    if header_found and line.strip():
                        parts = line.split()
                        if len(parts) >= 12:
                            try:
                                cpu_usage = float(parts[8]) if parts[8].replace('.','').isdigit() else 0
                                mem_usage = float(parts[9]) if parts[9].replace('.','').isdigit() else 0
                                processes.append({
                                    'PID': parts[0],
                                    'CPU%': cpu_usage,
                                    'MEM%': mem_usage,
                                    'Command': parts[11]
                                })
                            except (ValueError, IndexError):
                                continue
                
                if processes:
                    df = pd.DataFrame(processes)
                    df = df.nlargest(10, 'CPU%')
                    fig = px.bar(df, x='Command', y=['CPU%', 'MEM%'], 
                                title='Top 10 Processes by Resource Usage',
                                barmode='group')
                    return {'type': 'bar', 'figure': fig}
            
            # For df command
            elif "df" in command:
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    df = pd.read_csv(StringIO(output), delim_whitespace=True)
                    if 'Use%' in df.columns:
                        # Convert Use% to numeric, removing '%' if present
                        df['Use%'] = pd.to_numeric(df['Use%'].str.rstrip('%'), errors='coerce')
                        fig = px.pie(df, values='Use%', names='Filesystem', 
                                   title='Disk Usage by Filesystem')
                        return {'type': 'pie', 'figure': fig}

            # For network statistics (netstat)
            elif "netstat" in command:
                lines = output.strip().split('\n')
                connections = {'ESTABLISHED': 0, 'TIME_WAIT': 0, 'LISTEN': 0, 'CLOSE_WAIT': 0}
                for line in lines:
                    for state in connections.keys():
                        if state in line:
                            connections[state] += 1
                
                df = pd.DataFrame(list(connections.items()), columns=['State', 'Count'])
                fig = px.bar(df, x='State', y='Count', 
                            title='Network Connection States')
                return {'type': 'bar', 'figure': fig}

            # For memory info (free)
            elif "free" in command:
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    columns = lines[0].split()
                    values = lines[1].split()
                    mem_data = {}
                    for i, col in enumerate(columns[1:], 1):
                        try:
                            mem_data[col] = float(values[i]) / 1024  # Convert to MB
                        except (ValueError, IndexError):
                            continue
                    
                    df = pd.DataFrame(list(mem_data.items()), columns=['Type', 'MB'])
                    fig = px.bar(df, x='Type', y='MB',
                                title='Memory Usage (MB)')
                    return {'type': 'bar', 'figure': fig}

            return None
        except Exception as e:
            st.warning(f"Visualization error: {str(e)}")
            return None

    def get_ai_command_suggestion(user_query):
        system_prompt = """You are an experienced Linux system administrator. Based on the user's query, suggest appropriate Linux commands for system/network administration tasks. Provide both the command and a brief explanation of what information it will provide.

        Consider these categories:
        1. System Monitoring:
           - CPU/Memory: top, htop, free
           - Disk: df, du, iotop
           - Processes: ps, pgrep, pkill
           
        2. Network Monitoring:
           - Connectivity: ping, traceroute, netstat
           - Packet Analysis: tcpdump, iftop
           - Network Config: ip addr, ifconfig
           
        3. Log Analysis:
           - System Logs: journalctl, dmesg
           - Application Logs: tail, grep
           
        4. Performance Analysis:
           - System Load: uptime, vmstat
           - Network Load: nethogs, iptraf
           - Disk I/O: iostat

        Return the response in this JSON format:
        {
            "command": "actual command with all necessary flags",
            "explanation": "brief explanation of what the command will show",
            "category": "monitoring/network/logs/performance"
        }"""

        try:
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.7
            )
            
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            return {
                "command": "echo 'Error processing command suggestion'",
                "explanation": str(e),
                "category": "error"
            }

    # Preserve existing helper functions (check_timeout, establish_ssh_connection, disconnect_ssh, execute_ssh_command)
    # [Previous helper functions code here...]

    # Main chat interface
    st.title("Linux Admin Assistant")

    # Sidebar for configuration and connection history
    with st.sidebar:
        st.title("Configuration")
        
        # Connection History Section
        st.subheader("Connection History")
        for host, history in st.session_state.connections_history.items():
            with st.expander(f"📡 {host}"):
                st.write(f"Username: {history['username']}")
                st.write(f"Last Connected: {history['last_connected']}")
                if st.button(f"Reconnect to {host}", key=f"reconnect_{host}"):
                    try:
                        ssh = establish_ssh_connection(
                            host,
                            history['username'],
                            history['key_data']
                        )
                        st.session_state.ssh_client = ssh
                        st.session_state.connected = True
                        st.session_state.last_activity = datetime.now()
                        st.session_state.connection_info = {
                            'host': host,
                            'username': history['username'],
                            'key_data': history['key_data']
                        }
                        st.success(f"Reconnected to {host}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Reconnection failed: {str(e)}")
        
        st.divider()
        
        # New Connection Section
        if not st.session_state.connected:
            st.subheader("New SSH Connection")
            host = st.text_input("Host IP")
            username = st.text_input("Username")
            
            uploaded_file = st.file_uploader("Upload SSH Private Key", type=['pem', 'key'])
            
            if uploaded_file is not None and host and username:
                key_data = uploaded_file.getvalue()
                
                if st.button("Connect"):
                    try:
                        ssh = establish_ssh_connection(host, username, key_data)
                        
                        # Save to session state
                        st.session_state.ssh_client = ssh
                        st.session_state.connected = True
                        st.session_state.last_activity = datetime.now()
                        st.session_state.connection_info = {
                            'host': host,
                            'username': username,
                            'key_data': key_data
                        }
                        
                        # Save to connection history
                        st.session_state.connections_history[host] = {
                            'username': username,
                            'key_data': key_data,
                            'last_connected': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        # Initialize message history for this host if not exists
                        if host not in st.session_state.messages:
                            st.session_state.messages[host] = []
                        
                        st.success("Successfully connected!")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Connection failed: {str(e)}")
        else:
            st.success(f"Connected to: {st.session_state.connection_info['host']}")
            if st.button("Disconnect"):
                disconnect_ssh()
                st.rerun()
            
            if st.session_state.connected:
                time_remaining = 5 - (datetime.now() - st.session_state.last_activity).total_seconds() / 60
                st.info(f"Session timeout in: {time_remaining:.1f} minutes")

    # Main chat area
    if st.session_state.connected:
        current_host = st.session_state.connection_info['host']
        
        # Display chat messages for current connection
        if current_host in st.session_state.messages:
            for idx, message in enumerate(st.session_state.messages[current_host]):
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    if "visualization" in message and message["visualization"]:
                        st.plotly_chart(message["visualization"]["figure"], 
                                      key=f"viz_{current_host}_{idx}")

        if prompt := st.chat_input("What would you like to do?"):
            check_timeout()
            
            if not st.session_state.connected:
                st.error("Session expired. Please reconnect.")
                st.rerun()
            
            # Initialize messages list for this host if not exists
            if current_host not in st.session_state.messages:
                st.session_state.messages[current_host] = []
            
            # Append user message
            st.session_state.messages[current_host].append({"role": "user", "content": prompt})
            
            with st.chat_message("user"):
                st.markdown(prompt)
            
            try:
                # Get AI suggestion for command
                ai_suggestion = get_ai_command_suggestion(prompt)
                command = ai_suggestion["command"]
                
                # Execute command
                output = execute_ssh_command(command)
                st.session_state.last_activity = datetime.now()
                
                # Generate visualization if applicable
                visualization = process_and_visualize_command(command, output)
                
                # Create response content
                response_content = (
                    f"💡 **Suggested Action**: {ai_suggestion['explanation']}\n\n"
                    f"🔍 **Category**: {ai_suggestion['category']}\n\n"
                    f"⚡ **Command executed**: `{command}`\n\n"
                    f"📝 **Output**:\n```\n{output}\n```"
                )
                
                # Create assistant message
                assistant_message = {
                    "role": "assistant",
                    "content": response_content
                }
                if visualization:
                    assistant_message["visualization"] = visualization
                
                # Append assistant message
                st.session_state.messages[current_host].append(assistant_message)
                
                # Display assistant message
                with st.chat_message("assistant"):
                    st.markdown(response_content)
                    if visualization:
                        st.plotly_chart(visualization["figure"], 
                                      key=f"viz_{current_host}_{len(st.session_state.messages[current_host])-1}")

            except Exception as e:
                st.error(f"Error processing request: {str(e)}")

except Exception as e:
    st.error(f"Application error: {str(e)}")
