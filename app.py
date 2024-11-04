import streamlit as st
import paramiko
import openai
import pandas as pd
import plotly.express as px
from io import StringIO
import os
from datetime import datetime, timedelta

try:
    # Configure page settings
    st.set_page_config(page_title="Linux Admin Assistant", layout="wide")

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

    # Helper function to check connection timeout
    def check_timeout():
        if st.session_state.connected:
            time_elapsed = datetime.now() - st.session_state.last_activity
            if time_elapsed > timedelta(minutes=5):
                disconnect_ssh()
                st.error("Session timed out after 5 minutes of inactivity. Please reconnect.")
                st.rerun()  # Changed from experimental_rerun to rerun

    # Helper function to establish SSH connection
    def establish_ssh_connection(host, username, key_data):
        try:
            # Save the key data to a temporary file
            key_path = "temp_key.pem"
            with open(key_path, "wb") as f:
                f.write(key_data)
            os.chmod(key_path, 0o600)

            # Initialize SSH client
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect using the SSH key
            private_key = paramiko.RSAKey(filename=key_path)
            ssh.connect(hostname=host, username=username, pkey=private_key)
            
            # Clean up the temporary key file
            os.remove(key_path)
            
            return ssh
        except Exception as e:
            if os.path.exists(key_path):
                os.remove(key_path)
            raise e

    # Helper function to disconnect SSH
    def disconnect_ssh():
        if st.session_state.ssh_client:
            st.session_state.ssh_client.close()
        st.session_state.ssh_client = None
        st.session_state.connected = False
        st.session_state.connection_info = {
            'host': '',
            'username': '',
            'key_data': None
        }

    # Helper function to execute SSH commands
    def execute_ssh_command(command):
        check_timeout()  # Check for timeout before executing command
        
        if not st.session_state.ssh_client:
            try:
                # Attempt to reconnect using saved connection info
                if all(st.session_state.connection_info.values()):
                    st.session_state.ssh_client = establish_ssh_connection(
                        st.session_state.connection_info['host'],
                        st.session_state.connection_info['username'],
                        st.session_state.connection_info['key_data']
                    )
                    st.session_state.connected = True
                else:
                    return "Not connected to SSH server"
            except Exception as e:
                return f"Connection error: {str(e)}"

        try:
            # Update last activity timestamp
            st.session_state.last_activity = datetime.now()
            
            # Execute command
            stdin, stdout, stderr = st.session_state.ssh_client.exec_command(command)
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            return output if output else error
        except Exception as e:
            # If there's an error, try to reconnect once
            try:
                st.session_state.ssh_client = establish_ssh_connection(
                    st.session_state.connection_info['host'],
                    st.session_state.connection_info['username'],
                    st.session_state.connection_info['key_data']
                )
                stdin, stdout, stderr = st.session_state.ssh_client.exec_command(command)
                output = stdout.read().decode()
                error = stderr.read().decode()
                return output if output else error
            except Exception as e:
                return f"Command execution error: {str(e)}"

    # Helper function to process commands that might need visualization
    def process_and_visualize_command(command, output):
        try:
            # Check if output is system metrics from top command
            if "top" in command:
                # Parse top output into a more structured format
                lines = output.strip().split('\n')
                processes = []
                header_found = False
                
                for line in lines:
                    if 'PID' in line and 'CPU' in line:
                        header_found = True
                        continue
                    if header_found and line.strip():
                        parts = line.split()
                        if len(parts) >= 12:  # Ensure we have enough columns
                            processes.append({
                                'PID': parts[0],
                                'CPU%': float(parts[8]) if parts[8].replace('.','').isdigit() else 0,
                                'Command': parts[11]
                            })
                
                if processes:
                    df = pd.DataFrame(processes)
                    df = df.nlargest(10, 'CPU%')  # Show top 10 processes
                    fig = px.bar(df, x='Command', y='CPU%', title='Top CPU Usage by Process')
                    return fig
            
            # Check if output is disk usage
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

    # Main chat interface
    st.title("Linux Admin Assistant")

    # Sidebar for configuration
    with st.sidebar:
        st.title("Configuration")
        
        if not st.session_state.connected:
            # SSH Connection Configuration
            st.subheader("SSH Connection")
            host = st.text_input("Host IP")
            username = st.text_input("Username")
            
            # SSH Key Upload
            uploaded_file = st.file_uploader("Upload SSH Private Key", type=['pem', 'key'])
            
            if uploaded_file is not None and host and username:
                key_data = uploaded_file.getvalue()
                
                # Connect button
                if st.button("Connect"):
                    try:
                        ssh = establish_ssh_connection(host, username, key_data)
                        
                        # Save connection info
                        st.session_state.ssh_client = ssh
                        st.session_state.connected = True
                        st.session_state.last_activity = datetime.now()
                        st.session_state.connection_info = {
                            'host': host,
                            'username': username,
                            'key_data': key_data
                        }
                        
                        st.success("Successfully connected!")
                        st.rerun()  # Changed from experimental_rerun to rerun
                        
                    except Exception as e:
                        st.error(f"Connection failed: {str(e)}")
        else:
            st.success(f"Connected to: {st.session_state.connection_info['host']}")
            if st.button("Disconnect"):
                disconnect_ssh()
                st.rerun()  # Changed from experimental_rerun to rerun
            
            # Show session timeout info
            if st.session_state.connected:
                time_remaining = 5 - (datetime.now() - st.session_state.last_activity).total_seconds() / 60
                st.info(f"Session timeout in: {time_remaining:.1f} minutes")

    # Display connection status in main area
    if st.session_state.connected:
        st.success(f"Connected to {st.session_state.connection_info['host']}")
    else:
        st.info("Please configure SSH connection in the sidebar.")

    # Chat interface
    if st.session_state.connected:
        # Display chat messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                
                # If there's a visualization, display it
                if "visualization" in message:
                    st.plotly_chart(message["visualization"])

        # Chat input
        if prompt := st.chat_input("What would you like to do?"):
            # Check timeout before processing
            check_timeout()
            
            if not st.session_state.connected:
                st.error("Session expired. Please reconnect.")
                st.rerun()  # Changed from experimental_rerun to rerun
            
            # Append user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # Display user message
            with st.chat_message("user"):
                st.markdown(prompt)
            
            try:
                # Get OpenAI's interpretation of the command using the new API format
                system_prompt = """You are a network administrator, proficient in Linux based systems. 
                Convert the user's request into appropriate Linux commands. 
                For commands that require elevated privileges, prefix them with 'sudo'.
                For system monitoring commands like 'top', add the '-b -n 1' flags to ensure batch output.
                Respond with ONLY the command, no explanations."""
                
                response = openai.chat.completions.create(
                    model="gpt-4",  # or your preferred model
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                )
                
                command = response.choices[0].message.content.strip()
                
                # Execute the command
                output = execute_ssh_command(command)
                
                # Update last activity timestamp
                st.session_state.last_activity = datetime.now()
                
                # Check if output can be visualized
                visualization = process_and_visualize_command(command, output)
                
                # Create assistant's response
                response_content = f"Command executed: `{command}`\n\nOutput:\n```\n{output}\n```"
                
                # Append assistant message to chat history
                assistant_message = {
                    "role": "assistant",
                    "content": response_content
                }
                if visualization:
                    assistant_message["visualization"] = visualization
                    
                st.session_state.messages.append(assistant_message)
                
                # Display assistant message
                with st.chat_message("assistant"):
                    st.markdown(response_content)
                    if visualization:
                        st.plotly_chart(visualization)

            except Exception as e:
                st.error(f"Error processing request: {str(e)}")

except Exception as e:
    st.error(f"Application error: {str(e)}")
