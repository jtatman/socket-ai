import socket
import threading
import queue
import time
import random
from typing import Dict

from openai import OpenAI

HOST = '0.0.0.0'
PORT = 65432

# Mapping of socket -> (addr, last_seen)
clients: Dict[socket.socket, tuple[str, float]] = {}
clients_lock = threading.Lock()

# Thread-safe queue used to fan-out messages to all connected clients
message_queue: "queue.Queue[str]" = queue.Queue(maxsize=1000)

client = OpenAI(base_url="http://10.209.1.96:11434/v1", api_key="ollama")  # Or real key if OpenAI

def get_ai_response(user_msg):
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

def broadcast(message: str, sender_conn: socket.socket | None = None) -> None:
    """Send *message* to all currently connected clients.

    If *sender_conn* is provided, the sender will be skipped so the echo is
    not returned to them. Any socket failures cause immediate removal of the
    offending connection.
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

def handle_client(conn: socket.socket, addr):
    """Read loop for each connected client.

    Reads incoming lines and posts them to *message_queue*. Also requests an
    LLM response which is likewise queued.
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
    """Continuously broadcast messages taken from *message_queue*."""
    while True:
        msg = message_queue.get()
        broadcast(msg)

def reaper_loop(timeout: int = 10) -> None:
    """Periodically cull clients that haven’t sent anything for *timeout* seconds."""
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

def start_server():
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