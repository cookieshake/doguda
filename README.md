# Doguda

**Turn Python functions into CLI commands and HTTP endpoints instantly.**

[![PyPI version](https://badge.fury.io/py/doguda.svg)](https://badge.fury.io/py/doguda)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Installation

```bash
pip install doguda
```

## Quick Start

Create a file (e.g., `my_commands.py`):

```python
from doguda import DogudaApp

app = DogudaApp("MyCommands")

@app.command
def hello(name: str = "World") -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"

@app.command
async def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
```

### CLI Usage

Ensure your module is in the current directory or `DOGUDA_PATH`.

Run commands directly from the command line:

```bash
# Execute a command (automatically discovered)
doguda exec hello --name "Doguda"
# Output: Hello, Doguda!

doguda exec add --a 2 --b 3
# Output: 5
```

### List Available Commands

```bash
doguda list
```

Output:
```
📦 MyCommands
  • hello(name: str)
      Say hello to someone.
  • add(a: int, b: int)
      Add two numbers.
```

### HTTP Server

Start a FastAPI server with your commands as endpoints:

```bash
doguda serve --host 0.0.0.0 --port 8000
```

Then call your functions via HTTP:

```bash
curl -X POST http://localhost:8000/v1/doguda/hello \
  -H "Content-Type: application/json" \
  -d '{"name": "Doguda"}'
```

## Organizing Commands

You can split your commands across multiple files. Valid `DogudaApp` instances with the **same name** will be automatically merged into a single logical app in the CLI.

```python
# users.py
app = DogudaApp("Backend") # Same name

# reports.py
app = DogudaApp("Backend") # Same name
```

When running `doguda list`, these will appear unified under `📦 Backend`.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DOGUDA_PATH` | Path to search for modules | Current directory |

## Response Models

Use Pydantic models for structured responses:

```python
from pydantic import BaseModel
from doguda import DogudaApp

app = DogudaApp()

class UserResponse(BaseModel):
    id: int
    name: str
    email: str

@app.command
def get_user(user_id: int) -> UserResponse:
    """Get user by ID."""
    return UserResponse(id=user_id, name="John", email="john@example.com")
```

## License

MIT License - see [LICENSE](LICENSE) for details.
