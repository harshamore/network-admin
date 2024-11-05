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
    if 'chart_counter' not in st.session_state:
        st.session_state.chart_counter = 0

    # Helper function to get unique chart key
    def get_unique_chart_key():
        st.session_state.chart_counter += 1
        return f"chart_{st.session_state.chart_counter}"

    # [Previous helper functions remain the same until process_and_visualize_command]

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
                    return {'fig': fig, 'type': 'cpu_usage'}
            
            # Check if output is disk usage
            elif "df" in command:
                lines = output.strip().split('\n')
                if len(lines) > 1:
                    df = pd.read_csv(StringIO(output), delim_whitespace=True)
                    fig = px.pie(df, values='Use%', names='Filesystem', title='Disk Usage')
                    return {'fig': fig, 'type': 'disk_usage'}
                    
            return None
        except Exception as e:
            st.warning(f"Visualization error: {str(e)}")
            return None

    # [Previous code remains the same until the chat interface section]

    # Chat interface
    if st.session_state.connected:
        # Display chat messages
        for idx, message in enumerate(st.session_state.messages):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                
                # If there's a visualization, display it with a unique key
                if "visualization" in message:
                    st.plotly_chart(message["visualization"]["fig"], 
                                  key=f"{message['visualization']['type']}_{idx}")

        # Chat input
        if prompt := st.chat_input("What would you like to do?"):
            # Check timeout before processing
            check_timeout()
            
            if not st.session_state.connected:
                st.error("Session expired. Please reconnect.")
                st.rerun()
            
            # Append user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # Display user message
            with st.chat_message("user"):
                st.markdown(prompt)
            
            try:
                # [OpenAI API call and command execution remain the same]
                
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
                        st.plotly_chart(visualization["fig"], 
                                      key=f"{visualization['type']}_{len(st.session_state.messages)-1}")

            except Exception as e:
                st.error(f"Error processing request: {str(e)}")

except Exception as e:
    st.error(f"Application error: {str(e)}")
