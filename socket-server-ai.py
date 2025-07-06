"""Socket-based AI Chat Server

This module implements a multi-client chat server with AI integration. It allows
multiple clients to connect and chat in real-time, with an AI bot that can
respond to messages. The server uses TCP sockets for communication and supports
concurrent client connections using threads.

Example:
    Start the server:
    ```
    python socket-server-ai.py
    ```

    Connect clients using:
    ```
    python socket-client-ai.py
    ```

Note:
    The server requires an OpenAI-compatible API endpoint to be configured.
"""

import socket
import threading
import queue
import time
import random
from typing import Dict, Optional, Tuple

from openai import OpenAI

# Server configuration
HOST = '0.0.0.0'  # Listen on all available network interfaces
PORT = 65432      # Default port for the chat server

# Mapping of socket -> (addr, last_seen)
# Global state
clients: Dict[socket.socket, Tuple[str, float]] = {}
"""Active client connections with their address and last activity timestamp.

Keys:
    socket.socket: The client socket object

Values:
    Tuple containing (address: str, last_seen: float)
"""

clients_lock = threading.Lock()
"""Thread lock to synchronize access to the clients dictionary."""

# Thread-safe queue used to fan-out messages to all connected clients
message_queue: "queue.Queue[str]" = queue.Queue(maxsize=1000)
"""Queue for broadcasting messages to all connected clients.

Messages are added to this queue and processed by the dispatcher thread.
"""

# Initialize OpenAI client with local Ollama server
client = OpenAI(base_url="http://10.209.1.96:11434/v1", api_key="ollama")

def get_ai_response(user_msg: str) -> str:
    """Generate an AI response to the given user message.
    
    Args:
        user_msg: The user's message to respond to.
        
    Returns:
        str: The AI's generated response, or an error message if the request fails.
        
    Example:
        >>> get_ai_response("Hello, how are you?")
        "I'm doing well, thank you for asking! How can I assist you today?"
    """
    try:
        completion = client.chat.completions.create(
            model="llama3.2:3b",  # or any available local/remote model
            #model="llava-phi3:latest",  # or any available local/remote model
            #model="deepseek-r1:1.5b",  # or any available local/remote model
            messages=[
                {"role": "system", "content": "You are a lively, but psychotic bartender hosting a chatroom in the star wars universe."},
                {"role": "user", "content": user_msg}
            ]
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"[AI error]: {e}"

def broadcast(message: str, sender_conn: Optional[socket.socket] = None) -> None:
    """Send a message to all connected clients.
    
    Args:
        message: The message to broadcast.
        sender_conn: Optional client socket to exclude from the broadcast
                    (to avoid echoing back to the sender).
                    
    Note:
        Automatically removes any clients that cause socket errors during sending.
    """
    with clients_lock:
        dead = []
        for conn, _ in clients.items():
            if sender_conn is not None and conn is sender_conn:
                continue
            try:
                conn.sendall(message.encode())
            except OSError:
                dead.append(conn)
        # prune dead sockets outside loop to avoid mutation during iteration
        for d in dead:
            try:
                d.close()
            finally:
                clients.pop(d, None)

def handle_client(conn: socket.socket, addr: Tuple[str, int]) -> None:
    """Handle communication with a single connected client.
    
    This function runs in a separate thread for each client connection.
    It reads incoming messages, broadcasts them to all clients, and optionally
    generates AI responses.
    
    Args:
        conn: The client socket object.
        addr: Tuple containing the client's (IP address, port).
        
    Note:
        The client socket will be closed when this function returns.
    """
    print(f"[+] Connected: {addr}")
    with clients_lock:
        clients[conn] = (addr, time.time())

    try:
        with conn:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                user_msg = data.decode(errors="ignore").strip()
                if not user_msg:
                    continue
                print(user_msg)
                # Update heartbeat
                with clients_lock:
                    clients[conn] = (addr, time.time())

                # Queue the user's public message first
                message_queue.put_nowait(f"[{addr}] {user_msg}\n")

                # Generate and queue AI reply (non-blocking to user)
                try:
                    ai_reply = get_ai_response(user_msg)
                    print(ai_reply)
                except Exception as exc:
                    ai_reply = f"[AI error]: {exc}"

                message_queue.put_nowait(f"[C-K40 → {addr}]: {ai_reply}\n")
    finally:
        print(f"[-] Disconnected: {addr}")
        with clients_lock:
            clients.pop(conn, None)
        try:
            conn.close()
        except OSError:
            pass

def dispatcher_loop() -> None:
    """Continuously process and broadcast messages from the message queue.
    
    This function runs in a dedicated thread and is responsible for taking
    messages from the message queue and broadcasting them to all connected
    clients.
    """
    while True:
        msg = message_queue.get()
        broadcast(msg)

def reaper_loop(timeout: int = 10) -> None:
    """Periodically clean up inactive client connections.
    
    This function runs in a dedicated thread and removes clients that haven't
    sent any data within the specified timeout period.
    
    Args:
        timeout: Number of seconds of inactivity before a client is disconnected.
    """
    while True:
        time.sleep(timeout)
        now = time.time()
        with clients_lock:
            stale = [conn for conn, (_, last) in clients.items() if now - last > timeout]
        for conn in stale:
            try:
                conn.shutdown(socket.SHUT_RDWR)
                conn.close()
            except OSError:
                pass
            with clients_lock:
                clients.pop(conn, None)

def start_server() -> None:
    """Start the chat server and initialize worker threads.
    
    This function sets up the server socket, starts the dispatcher and reaper
    threads, and enters the main accept loop to handle incoming connections.
    
    The server runs until interrupted by a keyboard interrupt (Ctrl+C).
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen()
    print(f"[*] AI Broadcast Server listening on {HOST}:{PORT}")

    # Start dispatcher and reaper threads
    threading.Thread(target=dispatcher_loop, daemon=True, name="Dispatcher").start()
    threading.Thread(target=reaper_loop, daemon=True, name="Reaper").start()

    try:
        while True:
            try:
                conn, addr = server_sock.accept()
            except KeyboardInterrupt:
                # Ctrl-C pressed – break the accept loop so the program can exit.
                print("\n[!] Ctrl-C detected, shutting down server …")
                break
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    finally:
        server_sock.close()
        print("[*] Server socket closed. Bye!")

if __name__ == "__main__":
    start_server()