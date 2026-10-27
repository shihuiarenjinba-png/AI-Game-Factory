# Signal Sprint — offline 2D route puzzle (working prototype)

Run on Windows with Python 3.12+: `python main.py`.
Collect all three gold energy cells and reach EXIT in 30 moves. Use arrows,
WASD or click an adjacent tile. Walls block movement. R restarts; S saves the
round locally; L restores it. U undoes one successful move, including a
collected cell or a losing move; restart/load clears undo history. The language
button switches English/Japanese.

Headless tests: `python -m unittest discover -s tests -p 'test_*.py' -v`.

Windows 3.12 build: from the Factory repository root, run
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-windows.ps1`.
This is the allowlisted entrypoint used by the GAME Provisioner and CI. It
creates `dist/game/SignalSprint.exe` with an isolated temporary build venv;
no Partner Center credentials, OpenAI API key, Store identity or MSIX is used.

Status: source prototype; Windows EXE artifact requires independent CI proof.
The unsigned EXE is **not** an MSIX. No official Partner Center Store Identity
is supplied or guessed. Windows-all-auto MSIX intake and commercial QA remain
HOLD. Market demand has not been validated for this original puzzle concept.
