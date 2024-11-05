import streamlit as st
import paramiko
import openai
import pandas as pd
import plotly.express as px
from io import StringIO
import os
from datetime import datetime, timedelta

# Define helper functions first
def establish_ssh_connection(host, username, key_data):
    """Establish SSH connection using provided credentials"""
    try:
        key_path = "temp_key.pem"
        with open(key_path, "wb") as f:
            f.write(key_data)
        os.chmod(key_path, 0o600)

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        private_key = paramiko.RSAKey(filename=key_path)
        ssh.connect(hostname=host, username=username, pkey=private_key)
        
        os.remove(key_path)
        return ssh
    except Exception as e:
        if os.path.exists(key_path):
            os.remove(key_path)
        raise e

def disconnect_ssh():
    """Disconnect SSH and reset connection state"""
    if 'ssh_client' in st.session_state and st.session_state.ssh_client:
        st.session_state.ssh_client.close()
    st.session_state.ssh_client = None
    st.session_state.connected = False
    st.session_state.connection_info = {
        'host': '',
        'username': '',
        'key_data': None
    }

def check_timeout():
    """Check if the SSH session has timed out"""
    if st.session_state.get('connected', False):
        time_elapsed = datetime.now() - st.session_state.last_activity
        if time_elapsed > timedelta(minutes=5):
            disconnect_ssh()
            st.error("Session timed out after 5 minutes of inactivity. Please reconnect.")
            st.rerun()


def process_and_visualize_command(command, output):
    """Process command output and create visualization if applicable"""
    try:
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
                        processes.append({
                            'PID': parts[0],
                            'CPU%': float(parts[8]) if parts[8].replace('.','').isdigit() else 0,
                            'Command': parts[11]
                        })
            
            if processes:
                df = pd.DataFrame(processes)
                df = df.nlargest(10, 'CPU%')
                fig = px.bar(df, x='Command', y='CPU%', title='Top CPU Usage by Process')
                return fig
        
        elif "df" in command:
            lines = output.strip().split('\n')
            if len(lines) > 1:
                df = pd.read_csv(StringIO(output), delim_whitespace=True)
                fig = px.pie(df, values='Use%', names='Filesystem', title='Disk Usage')
                return fig
                
        return None
    except Exception as e:
        st.warning(f"Visualization error: {str(e)}")
        return None

# Initialize Streamlit page and session states
st.set_page_config(page_title="Cloud Admin Assistant", layout="wide")

# Set OpenAI API key from Streamlit secrets
openai.api_key = st.secrets["OPENAI_API_KEY"]

# Initialize session states
if 'messages' not in st.session_state:
    st.session_state.messages = []
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

# Main title
st.title("Cloud Admin Assistant")

# Sidebar for SSH configuration
with st.sidebar:
    st.title("Configuration")
    
    if not st.session_state.connected:
        st.subheader("SSH Connection")
        host = st.text_input("Host IP")
        username = st.text_input("Username")
        
        uploaded_file = st.file_uploader("Upload SSH Private Key", type=['pem', 'key'])
        
        if uploaded_file is not None and host and username:
            key_data = uploaded_file.getvalue()
            
            if st.button("Connect"):
                try:
                    ssh = establish_ssh_connection(host, username, key_data)
                    
                    st.session_state.ssh_client = ssh
                    st.session_state.connected = True
                    st.session_state.last_activity = datetime.now()
                    st.session_state.connection_info = {
                        'host': host,
                        'username': username,
                        'key_data': key_data
                    }
                    
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

# Main chat interface
if st.session_state.connected:
    st.success(f"Connected to {st.session_state.connection_info['host']}")
else:
    st.info("Please configure SSH connection in the sidebar.")

# Display chat interface only when connected
if st.session_state.connected:
    # Display chat history
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "visualization" in message:
                st.plotly_chart(message["visualization"], key=f"chart_{idx}")

    # Chat input and processing
    if prompt := st.chat_input("What would you like to do?"):
        check_timeout()
        
        if not st.session_state.connected:
            st.error("Session expired. Please reconnect.")
            st.rerun()
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        try:
            system_prompt = """You are a network administrator, proficient in Linux based systems. 
            Convert the user's request into appropriate Linux commands.
            For commands that require elevated privileges, prefix them with 'sudo'.
            For system monitoring commands like 'top', add the '-b -n 1' flags to ensure batch output.
            For network monitoring commands like tcpdump:
            - Use interface menitoned in the command (the application will automatically replace it with the correct interface)
            - Always add appropriate flags for better output (-n for no DNS resolution, -v for verbose)
            - For packet captures, limit the capture to avoid overwhelming output
            Example: 'sudo tcpdump -i eth0 -n -v -c 50'
            When checking system status or resources:
            - For CPU/memory: use 'top -b -n 1'
            - For disk space: use 'df -h'
            - For network interfaces: use 'ip link show'
            Respond with ONLY the command, no explanations."""
            
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            
            command = response.choices[0].message.content.strip()
            output = execute_ssh_command(command)
            st.session_state.last_activity = datetime.now()
            
            visualization = process_and_visualize_command(command, output)
            response_content = f"Command executed: `{command}`\n\nOutput:\n```\n{output}\n```"
            
            assistant_message = {
                "role": "assistant",
                "content": response_content
            }
            if visualization:
                assistant_message["visualization"] = visualization
                
            st.session_state.messages.append(assistant_message)
            
            with st.chat_message("assistant"):
                st.markdown(response_content)
                if visualization:
                    st.plotly_chart(visualization, key=f"chart_{len(st.session_state.messages)-1}")

        except Exception as e:
            st.error(f"Error processing request: {str(e)}")
