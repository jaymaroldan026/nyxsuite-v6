import os

from core.task_store import TaskStore

def get_queue_store():
    return TaskStore(db_path=os.getenv("TASK_DB_PATH"))
