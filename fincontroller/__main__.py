"""
FinController module execution entrypoint.
Allows running `python -m fincontroller <command>` cleanly.
"""

from fincontroller.cli.main import app

if __name__ == "__main__":
    app()
