# HS Code Search Tool

This project provides a Python-based search utility for HS Codes using SQLite with FTS5 for full-text search.
It cleans and normalizes HS codes (e.g., removing trailing `.00`) and provides fast query functionality.

## Features
- Cleans HS codes to avoid duplicates like `6301.10.00` vs `6301.10.00.00`
- Uses SQLite with FTS5 for efficient full-text search
- Modular and easy to maintain
- Ready to deploy and run locally

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/hscode-search.git
cd hscode-search
```

2. Create a virtual environment (optional but recommended):
```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
venv\Scripts\activate   # On Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the script:
```bash
python HScode.py
```

## Project Structure
```
hscode-search/
├── data/                # Contains raw or cleaned database files
├── src/                 # Contains main Python scripts
│   └── HScode.py        # Main program file
├── requirements.txt     # Dependencies
├── README.md            # Project documentation
└── .gitignore           # Ignored files for Git
```

## License
This project is licensed under the MIT License.
