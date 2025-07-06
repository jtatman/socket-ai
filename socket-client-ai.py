import socket
import threading
import time
import random
import select
from typing import List

from openai import OpenAI

HOST = '127.0.0.1'
PORT = 65432

# Maximum bytes to read per recv
RECV_CHUNK = 4096

client = OpenAI(base_url="http://10.209.1.96:11434/v1", api_key="ollama")  # or real OpenAI key

def get_ai_reply(history):
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

def receive_loop(sock: socket.socket, history: List[dict], lock: threading.Lock):
    """Continuously pull data from *sock* and append complete lines to *history*.

    Uses *select* for responsiveness and correctly handles TCP packet
    boundaries by buffering until a newline is seen.
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

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        print("🤖 AI client connected to server.")
        # Disable Nagle to reduce latency in small messages
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        history_lock = threading.Lock()
        history: List[dict] = [
            {
                "role": "system",
                "content": (
                    "You are a japanese sex robot in a chatroom full of other star wars characters from the star wars universe."
                ),
            }
        ]

        threading.Thread(
            target=receive_loop, args=(s, history, history_lock), daemon=True
        ).start()

        try:
            while True:
                # Short random delay mimics thinking and prevents flooding
                time.sleep(random.uniform(3, 7))
                with history_lock:
                    context = history[-10:]
                print(f"current context is: {context}")
                reply = get_ai_reply(context)
                print(f"\n[R2D2 says] {reply}")
                # Ensure newline terminator for server's line parsing
                s.sendall((reply + "\n").encode())
                with history_lock:
                    history.append({"role": "assistant", "content": reply})
        except KeyboardInterrupt:
            print("[Client shutting down]")

if __name__ == "__main__":
    main()