import streamlit as st
import paramiko
import openai
import pandas as pd
import plotly.express as px
from io import StringIO
import os

try:
    # Configure page settings
    st.set_page_config(page_title="AI based Linux Admin Assistant", layout="wide")

    # Set OpenAI API key from Streamlit secrets
    openai.api_key = st.secrets["OPENAI_API_KEY"]

    # Initialize session states
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'ssh_client' not in st.session_state:
        st.session_state.ssh_client = None
    if 'connected' not in st.session_state:
        st.session_state.connected = False

    # Helper function to execute SSH commands
    def execute_ssh_command(command):
        if st.session_state.ssh_client is None:
            return "Not connected to SSH server"
        
        stdin, stdout, stderr = st.session_state.ssh_client.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()
        
        return output if output else error

    # Helper function to process commands that might need visualization
    def process_and_visualize_command(command, output):
        try:
            # Check if output is system metrics
            if "top" in command or "ps" in command:
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    df = pd.read_csv(StringIO(output), delim_whitespace=True)
                    fig = px.bar(df, x=df.columns[0], y=df.columns[1])
                    return fig
            
            # Check if output is disk usage
            elif "df" in command:
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    df = pd.read_csv(StringIO(output), delim_whitespace=True)
                    fig = px.pie(df, values='Use%', names='Filesystem')
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
        
        # SSH Connection Configuration
        st.subheader("SSH Connection")
        host = st.text_input("Host IP")
        username = st.text_input("Username")
        
        # SSH Key Upload
        uploaded_file = st.file_uploader("Upload SSH Private Key", type=['pem', 'key'])
        
        if uploaded_file is not None and host and username:
            # Save the uploaded key to a temporary file
            key_path = "temp_key.pem"
            with open(key_path, "wb") as f:
                f.write(uploaded_file.getvalue())
            os.chmod(key_path, 0o600)
            
            # Connect button
            if st.button("Connect"):
                try:
                    # Initialize SSH client
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                    # Connect using the SSH key
                    private_key = paramiko.RSAKey(filename=key_path)
                    ssh.connect(hostname=host, username=username, pkey=private_key)
                    
                    st.session_state.ssh_client = ssh
                    st.session_state.connected = True
                    st.success("Successfully connected!")
                    
                except Exception as e:
                    st.error(f"Connection failed: {str(e)}")
                finally:
                    # Clean up the temporary key file
                    if os.path.exists(key_path):
                        os.remove(key_path)

    # Display connection status
    if st.session_state.connected:
        st.success("Connected to server")
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
            # Append user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # Display user message
            with st.chat_message("user"):
                st.markdown(prompt)
            
            try:
                # Get OpenAI's interpretation of the command
                system_prompt = """You are a network administrator, proficient in Linux based systems. 
                Convert the user's request into appropriate Linux commands. 
                Respond with ONLY the command, no explanations."""
                
                response = openai.ChatCompletion.create(
                    model="gpt-4-0-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                )
                
                command = response.choices[0].message.content.strip()
                
                # Execute the command
                output = execute_ssh_command(command)
                
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

# Cleanup connection when app is closed
if hasattr(st.session_state, 'ssh_client') and st.session_state.ssh_client:
    st.session_state.ssh_client.close()
    st.session_state.connected = False
