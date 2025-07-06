"""Socket-based AI Chat Client

This module implements a client for the AI chat server. It connects to a server,
sends user messages, and displays messages from other clients and the AI.
The client runs two threads: one for user input and another for receiving messages.

Example:
    Connect to the default server:
    ```
    python socket-client-ai.py
    ```
    
    Or specify host and port:
    ```
    python socket-client-ai.py --host 127.0.0.1 --port 65432
    ```
"""

import socket
import threading
import time
import random
import select
import argparse
from typing import List, Dict, Any, Optional

from openai import OpenAI

# Default connection settings
HOST = '127.0.0.1'  # Default server host
PORT = 65432        # Default server port

# Network configuration
RECV_CHUNK = 4096  # Maximum bytes to read per recv() call

# Initialize OpenAI client with local Ollama server
client = OpenAI(base_url="http://10.209.1.96:11434/v1", api_key="ollama")

def get_ai_reply(history: List[Dict[str, str]]) -> str:
    """Generate an AI response based on the conversation history.
    
    Args:
        history: List of message dictionaries with 'role' and 'content' keys
                representing the conversation history.
                
    Returns:
        str: The AI's generated response, or an error message if the request fails.
        
    Example:
        >>> history = [
        ...     {"role": "user", "content": "Hello"},
        ... ]
        >>> get_ai_reply(history)
        "Hello! How can I assist you today?"
    """
    try:
        response = client.chat.completions.create(
            model="llama3.2:3b",  # or your preferred model
            #model="llava-phi3:latest",  # or your preferred model
            #model="deepseek-r1:1.5b",  # or your preferred model
            messages=history
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[AI error]: {e}"

def receive_loop(sock: socket.socket, history: List[Dict[str, str]], 
                lock: threading.Lock) -> None:
    """Continuously receive and process data from the server.
    
    This function runs in a separate thread and handles incoming messages
    from the server. It properly handles message boundaries and updates
    the conversation history in a thread-safe manner.
    
    Args:
        sock: Connected socket to receive data from
        history: List to store conversation history
        lock: Thread lock to protect access to the history list
        
    Note:
        This function runs until the socket is closed or an error occurs.
    """
    buffer = b""
    while True:
        try:
            # Wait until the socket is readable or 1-s timeout to allow shutdown.
            rdy, _, _ = select.select([sock], [], [], 1.0)
            if not rdy:
                continue
            chunk = sock.recv(RECV_CHUNK)
            if not chunk:
                print("[Connection closed by server]")
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                decoded = line.decode(errors="ignore").strip()
                if decoded:
                    print(f"\n[Received] {decoded}")
                    with lock:
                        history.append({"role": "user", "content": decoded})
        except (OSError, ValueError):
            break

def parse_args() -> argparse.Namespace:
    """Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(description='AI Chat Client')
    parser.add_argument('--host', default=HOST, help='Server hostname or IP')
    parser.add_argument('--port', type=int, default=PORT, help='Server port')
    return parser.parse_args()

def main() -> None:
    """Main function to start the chat client.
    
    Handles connection setup, thread management, and user input.
    The client runs until the user types 'quit' or an error occurs.
    
    The main function performs the following steps:
    1. Parse command line arguments
    2. Connect to the server
    3. Start the receive thread
    4. Handle user input
    """
    # Parse command line arguments
    args = parse_args()
    
    # Connect to server
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((args.host, args.port))
        print(f"Connected to {args.host}:{args.port}")
    except ConnectionRefusedError:
        print(f"Error: Could not connect to {args.host}:{args.port}")
        return
    
    print("🤖 AI client connected to server.")
    # Disable Nagle to reduce latency in small messages
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    # Start receive thread
    history: List[Dict[str, str]] = []
    lock = threading.Lock()
    recv_thread = threading.Thread(
        target=receive_loop, args=(sock, history, lock), daemon=True
    )
    recv_thread.start()
    
    print("\nType your message and press Enter. Type 'quit' to exit.\n")

    try:
        while True:
            # Short random delay mimics thinking and prevents flooding
            time.sleep(random.uniform(3, 7))
            with lock:
                context = history[-10:] if history else []
            print(f"current context is: {context}")
            reply = get_ai_reply(context)
            print(f"\n[R2D2 says] {reply}")
            # Ensure newline terminator for server's line parsing
            sock.sendall((reply + "\n").encode())
            with lock:
                history.append({"role": "assistant", "content": reply})
    except KeyboardInterrupt:
        print("\n[Client shutting down]")
    finally:
        sock.close()

if __name__ == "__main__":
    main()