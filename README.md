# Employee Wellness Management Analytics

A comprehensive Flask-based web application for managing employee wellness, tracking health risks, and generating personalized health recommendations.

## Prerequisites

Before you begin, ensure you have the following installed on your system:
- [Python 3.8+](https://www.python.org/downloads/)
- `pip` (Python package installer, usually bundled with Python)

## Setup Instructions

Follow these steps to set up and run the project locally.

### 1. Open your terminal / command prompt
Navigate to the directory where you downloaded the project files.
```bash
cd "path/to/project 2"
```

### 2. (Optional but Recommended) Create a Virtual Environment
Creating a virtual environment keeps your project dependencies isolated.
```bash
# For Windows:
python -m venv venv
venv\Scripts\activate

# For Mac/Linux:
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
Install the required Python packages for the application.
```bash
pip install -r requirements.txt
```

### 4. Run the Application
Start the Flask development server.
```bash
python app.py
```

### 5. Access the Platform
Once the server is running, open your web browser and navigate to:
**http://127.0.0.1:5000**

## Default Accounts
If the database (`wellness.db`) is generated fresh, a default administrator account is typically created.
- **Admin Username**: `admin`
- **Admin Password**: `admin123` (or as configured in `database.py`)

## Troubleshooting
- **Database Errors**: If you encounter errors related to missing tables, ensure the `database.py` file has automatically initialized `wellness.db`. If you need to reset the database, you can simply delete `wellness.db` and run `python app.py` again.
- **Port 5000 in Use**: If you get an error that the port is already in use, you can stop the other service, or modify the `app.run(debug=True, port=5000)` line at the bottom of `app.py` to use a different port (e.g., `5001`).
