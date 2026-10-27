# Signal Sprint — offline 2D route puzzle (working prototype)

Run on Windows with Python 3.12+: `python main.py`.
Collect all three gold energy cells and reach EXIT in 30 moves. Use arrows,
WASD or click an adjacent tile. Walls block movement. R restarts; S saves the
round locally; L restores it. The language button switches English/Japanese.

Headless tests: `python -m unittest discover -s tests -p 'test_*.py' -v`.

Status: source prototype; Windows EXE artifact requires independent CI proof.
The unsigned EXE is **not** an MSIX. No official Partner Center Store Identity
is supplied or guessed. Windows-all-auto MSIX intake and commercial QA remain
HOLD. Market demand has not been validated for this original puzzle concept.
