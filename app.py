# ... (previous imports and initial setup remain the same)

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
            
            # If command requires network interface info, get it first
            if any(cmd in command.lower() for cmd in ['tcpdump', 'wireshark', 'tshark', 'iftop']):
                # Get list of interfaces
                stdin, stdout, stderr = st.session_state.ssh_client.exec_command('ip link show')
                interfaces_output = stdout.read().decode()
                
                # Parse interfaces
                interfaces = []
                for line in interfaces_output.split('\n'):
                    if ':' in line and '@' not in line:  # Skip virtual interfaces
                        interface = line.split(':')[1].strip()
                        interfaces.append(interface)
                
                if not interfaces:
                    return "No network interfaces found"
                
                # Replace generic interface names with actual interface
                for interface in interfaces:
                    if 'eth0' in command:
                        command = command.replace('eth0', interface)
                        break
                    elif 'enx' in interface.lower() or 'eth' in interface.lower():
                        # Prefer enx or eth interfaces if available
                        command = command.replace('eth0', interface)
                        break
                    else:
                        # Use the first available interface if no preferred interface found
                        command = command.replace('eth0', interfaces[0])
                        break
            
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

    # Main chat interface
    st.title("Linux Admin Assistant")

    # ... (rest of the code remains the same until the OpenAI prompt)

                # Get OpenAI's interpretation of the command using the new API format
                system_prompt = """You are a network administrator, proficient in Linux based systems. 
                Convert the user's request into appropriate Linux commands.
                For commands that require elevated privileges, prefix them with 'sudo'.
                For system monitoring commands like 'top', add the '-b -n 1' flags to ensure batch output.
                For network monitoring commands like tcpdump:
                - Use 'eth0' in the command (the application will automatically replace it with the correct interface)
                - Always add appropriate flags for better output (-n for no DNS resolution, -v for verbose)
                - For packet captures, limit the capture to avoid overwhelming output
                Example: 'sudo tcpdump -i eth0 -n -v -c 50'
                Respond with ONLY the command, no explanations."""
                
                # ... (rest of the code remains the same)
