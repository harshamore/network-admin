import streamlit as st
import paramiko
import openai
import pandas as pd
import plotly.express as px
from io import StringIO
import os
from datetime import datetime, timedelta

# Define helper functions first, before any Streamlit commands
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

# Initialize Streamlit page and session states
st.set_page_config(page_title="Linux Admin Assistant", layout="wide")

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

# Rest of your code remains the same...
