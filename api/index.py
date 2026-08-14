"""
Vercel Serverless Entry Point
Imports the Flask app from the parent directory and exposes it for Vercel's WSGI handler.
"""
import sys
import os

# Add the project root to Python path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Vercel looks for an 'app' variable (WSGI application)
