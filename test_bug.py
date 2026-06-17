from app import create_app
from flask import session
from app.models import create_participant, save_response, save_comprehension, mark_completed
import os

os.environ["SECRET_KEY"] = "test"
os.environ["MONGO_URI"] = "mongodb://localhost:27017" # We might need a real or mock DB, but let's just see where it crashes.
