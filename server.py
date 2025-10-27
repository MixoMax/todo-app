# todo-app/server.py

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import uvicorn
import sys
from datetime import datetime
from enum import Enum
import os
import json
import time

app = FastAPI()

class TodoStatus(str, Enum):
    NOT_STARTED = "not started"
    IN_PROGRESS = "in progress"
    COMPLETED = "completed"

class TodoItem(BaseModel):
    id: int = -1
    title: str
    description: str
    status: TodoStatus
    created_at: float # UNIX timestamp
    to_be_done_by: float # UNIX timestamp

class RepeatingTodo:
    id: int
    def __init__(self, title: str, description: str, status: TodoStatus, interval_seconds: int):
        self.title = title
        self.description = description
        self.status = status
        self.interval_seconds = interval_seconds
        self.next_due_time = time.time() + interval_seconds

    def check_and_create_todo(self):
        current_time = time.time()
        if current_time >= self.next_due_time:
            global next_id
            todo = TodoItem(
                id=next_id,
                title=self.title,
                description=self.description,
                status=self.status,
                created_at=current_time,
                to_be_done_by=current_time + self.interval_seconds
            )
            next_id += 1
            self.next_due_time = current_time + self.interval_seconds
            return todo
        return None

repeating_todos: list[RepeatingTodo] = []
next_repeating_id = 1
todos: dict[int, TodoItem] = {}
next_id = 1



@app.post("/api/v1/todos")
async def create_todo(todo: TodoItem):
    global next_id
    todo.id = next_id
    todos[next_id] = todo
    next_id += 1
    return JSONResponse(status_code=201, content=todo.dict())

@app.get("/api/v1/todos")
async def get_todos():
    # Check and create repeating todos if needed
    for repeating_todo in repeating_todos:
        new_todo = repeating_todo.check_and_create_todo()
        if new_todo:
            todos[new_todo.id] = new_todo
    return list(todos.values())

@app.get("/api/v1/todos/{todo_id}")
async def get_todo(todo_id: int):
    if todo_id in todos:
        return todos[todo_id]
    else:
        raise HTTPException(status_code=404, detail="Todo not found")

@app.put("/api/v1/todos/{todo_id}")
async def update_todo(todo_id: int, updated_todo: TodoItem):
    if todo_id in todos:
        updated_todo.id = todo_id
        todos[todo_id] = updated_todo
        return updated_todo
    else:
        raise HTTPException(status_code=404, detail="Todo not found")

@app.delete("/api/v1/todos/{todo_id}")
async def delete_todo(todo_id: int):
    if todo_id in todos:
        del todos[todo_id]
        return JSONResponse(status_code=204, content={})
    else:
        raise HTTPException(status_code=404, detail="Todo not found")


@app.post("/api/v1/repeating-todos")
async def create_repeating_todo(data: dict):
    global next_repeating_id
    title = data.get("title")
    description = data.get("description")
    status = data.get("status")
    interval_seconds = data.get("interval_seconds")
    if not all([title, description, status, interval_seconds]):
        raise HTTPException(status_code=400, detail="Missing fields in request")
    repeating_todo = RepeatingTodo(title, description, TodoStatus(status), interval_seconds)
    repeating_todo.id = next_repeating_id
    next_repeating_id += 1
    repeating_todos.append(repeating_todo)
    return JSONResponse(status_code=201, content={"id": repeating_todo.id, "title": title, "description": description, "status": status, "interval_seconds": interval_seconds})

@app.get("/api/v1/repeating-todos")
async def get_repeating_todos():
    return [{"id": todo.id, "title": todo.title, "description": todo.description, "status": todo.status, "interval_seconds": todo.interval_seconds} for todo in repeating_todos]

@app.get("/api/v1/repeating-todos/{todo_id}")
async def get_repeating_todo(todo_id: int):
    for todo in repeating_todos:
        if todo.id == todo_id:
            return {"id": todo.id, "title": todo.title, "description": todo.description, "status": todo.status, "interval_seconds": todo.interval_seconds}
    raise HTTPException(status_code=404, detail="Repeating todo not found")

@app.put("/api/v1/repeating-todos/{todo_id}")
async def update_repeating_todo(todo_id: int, data: dict):
    for todo in repeating_todos:
        if todo.id == todo_id:
            todo.title = data.get("title", todo.title)
            todo.description = data.get("description", todo.description)
            todo.status = TodoStatus(data.get("status", todo.status))
            todo.interval_seconds = data.get("interval_seconds", todo.interval_seconds)
            return {"id": todo.id, "title": todo.title, "description": todo.description, "status": todo.status, "interval_seconds": todo.interval_seconds}
    raise HTTPException(status_code=404, detail="Repeating todo not found")

@app.delete("/api/v1/repeating-todos/{todo_id}")
async def delete_repeating_todo(todo_id: int):
    for i, todo in enumerate(repeating_todos):
        if todo.id == todo_id:
            del repeating_todos[i]
            return JSONResponse(status_code=204, content={})
    raise HTTPException(status_code=404, detail="Repeating todo not found")




@app.get("/{path:path}")
async def serve_static(path: str):
    if path == "":
        path = "index.html"
    file_path = os.path.join("static", path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    else:
        raise HTTPException(status_code=404, detail="File not found")



if __name__ == "__main__":
    port = 8000 if len(sys.argv) < 2 else int(sys.argv[1])
    uvicorn.run(app, host="0.0.0.0", port=port)
