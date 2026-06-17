"""
Vercel serverless entrypoint.

Vercel's Python runtime looks for a WSGI callable named `app` in this file.
All traffic is routed here via vercel.json and forwarded to the Flask app.
"""
import sys
import os

# Ensure the project root is on the path so `main`, `app`, and `src` are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: F401  — Vercel picks up this `app` as the WSGI handler
