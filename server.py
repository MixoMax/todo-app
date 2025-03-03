# todo-app/server/server.py

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.websockets import WebSocket
from pydantic import BaseModel
import uvicorn
import sys
from datetime import datetime
import os
import json
import sqlite3
import time
from typing import List


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove failed connections
                self.disconnect(connection)


SQLITE_CURSOR_LOCK: bool = False
manager = ConnectionManager()



app = FastAPI()

# Todo model
class Todo(BaseModel):
    id: int | None = None
    title: str
    completed: bool = False
    created_at: str | None = None


os.makedirs("./data", exist_ok=True)

conn = sqlite3.connect("./data/todo.db", check_same_thread=False)
c = conn.cursor()

cmd = """
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    completed BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
c.execute(cmd)
conn.commit()



def _wait_for_cursor():
    global SQLITE_CURSOR_LOCK
    while SQLITE_CURSOR_LOCK:
        time.sleep(0.01)
    
    SQLITE_CURSOR_LOCK = True

def _release_cursor():
    global SQLITE_CURSOR_LOCK
    SQLITE_CURSOR_LOCK = False


def get_todos():
    global conn, c
    
    _wait_for_cursor()

    c.execute("SELECT * FROM todos")
    data = c.fetchall()
    todos = []
    for row in data:
        todo = Todo(id=row[0], title=row[1], completed=bool(row[2]), created_at=row[3])
        todos.append(todo)

    _release_cursor()
    return todos

def save_todo(todo: Todo):
    global conn, c

    _wait_for_cursor()

    params = (todo.title, todo.completed, todo.created_at)
    c.execute("INSERT INTO todos (title, completed, created_at) VALUES (?, ?, ?)", params)
    conn.commit()

    _release_cursor()

def update_todo(todo: Todo):
    global conn, c
    
    _wait_for_cursor()

    params = (todo.title, todo.completed, todo.created_at, todo.id)
    c.execute("UPDATE todos SET title = ?, completed = ?, created_at = ? WHERE id = ?", params)
    conn.commit()

    _release_cursor()

def delete_todo(todo_id: int):
    global conn, c

    _wait_for_cursor()

    c.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    conn.commit()

    _release_cursor()

def todo_to_json(todo: Todo) -> dict:
    return {
        "id": todo.id,
        "title": todo.title,
        "completed": todo.completed,
        "created_at": todo.created_at
    }



# WebSocket endpoint replacing the REST API
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial todos list
        todos = get_todos()
        await websocket.send_json({
            "type": "init",
            "data": [todo_to_json(todo) for todo in todos]
        })
        
        # Listen for messages
        while True:
            try:
                message = await websocket.receive_json()
                response = {"type": "error", "message": "Invalid request"}
                
                if "action" in message and "data" in message:
                    if message["action"] == "create":
                        todo_data = message["data"]
                        todo = Todo(**todo_data)
                        todo.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        save_todo(todo)
                        todos = get_todos()
                        todos_json = [todo_to_json(todo) for todo in todos]
                        response = {
                            "type": "update",
                            "data": json.dumps(todos_json)
                        }

                    elif message["action"] == "update":
                        todo_data = message["data"]
                        todo = Todo(**todo_data)
                        update_todo(todo)
                        todos = get_todos()
                        todos_json = [todo_to_json(todo) for todo in todos]
                        response = {
                            "type": "update",
                            "data": json.dumps(todos_json)
                        }

                    elif message["action"] == "delete":
                        todo_id = message["data"]["id"]
                        delete_todo(todo_id)
                        todos = get_todos()
                        todos_json = [todo_to_json(todo) for todo in todos]
                        response = {
                            "type": "update",
                            "data": json.dumps(todos_json)
                        }

                    elif message["action"] == "get":
                        todos = get_todos()
                        todos_json = [todo_to_json(todo) for todo in todos]
                        response = {
                            "type": "update",
                            "data": json.dumps(todos_json)
                        }

                await websocket.send_json(response)
                # Broadcast to other clients
                if message["action"] in ["create", "update", "delete"]:
                    for conn in manager.active_connections:
                        if conn != websocket:  # Don't send to the sender
                            await conn.send_json(response)

            except WebSocketDisconnect:
                manager.disconnect(websocket)
                break
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
    except:
        manager.disconnect(websocket)




@app.get("/")
@app.get("/index.html")
def index():
    return FileResponse("./static/index_ws.html")



if __name__ == "__main__":
    port = 8000 if len(sys.argv) < 2 else int(sys.argv[1])
    uvicorn.run(app, host="0.0.0.0", port=port)
