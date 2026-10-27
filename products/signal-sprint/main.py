"""Signal Sprint: offline, deterministic 2D puzzle; engine tests need no GUI."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile

SIZE = 8
START, EXIT = (0, 0), (7, 7)
MAX_TURNS = 30
WALLS = frozenset({(2, y) for y in range(1, 7) if y != 3}
                  | {(5, y) for y in range(1, 7) if y != 5}
                  | {(x, 4) for x in range(3, 5)})
CELLS = frozenset({(1, 5), (4, 1), (6, 6)})
DIRECTIONS = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0),
              "Right": (1, 0), "w": (0, -1), "s": (0, 1),
              "a": (-1, 0), "d": (1, 0)}


class Game:
    def __init__(self):
        self.restart()

    def restart(self):
        self.position = START
        self.collected = set()
        self.turns = 0
        self.status = "PLAYING"
        self.message = "Collect three cells, then reach EXIT."

    def move(self, dx, dy):
        if self.status != "PLAYING" or (dx, dy) not in DIRECTIONS.values():
            return False
        target = (self.position[0] + dx, self.position[1] + dy)
        if (not 0 <= target[0] < SIZE or not 0 <= target[1] < SIZE
                or target in WALLS):
            self.message = "Blocked. Choose another route."
            return False
        self.position = target
        self.turns += 1
        if target in CELLS:
            self.collected.add(target)
        if target == EXIT and self.collected == CELLS:
            self.status, self.message = "WON", "Circuit complete! Press R to restart."
        elif self.turns >= MAX_TURNS:
            self.status, self.message = "LOST", "Out of moves. Press R to retry."
        elif target == EXIT:
            self.message = "EXIT locked: collect all three cells first."
        else:
            self.message = "Find the shortest safe route."
        return True

    def snapshot(self):
        return {"version": 1, "position": list(self.position),
                "collected": [list(p) for p in sorted(self.collected)],
                "turns": self.turns, "status": self.status}

    def restore(self, state):
        if not isinstance(state, dict) or set(state) != {
            "version", "position", "collected", "turns", "status"
        } or state["version"] != 1:
            raise ValueError("Unsupported save")
        def point(value):
            if (not isinstance(value, list) or len(value) != 2
                    or any(type(n) is not int or not 0 <= n < SIZE for n in value)):
                raise ValueError("Invalid coordinates")
            return tuple(value)
        pos = point(state["position"])
        cells = state["collected"]
        if not isinstance(cells, list) or len(cells) > 3:
            raise ValueError("Invalid cells")
        got = [point(c) for c in cells]
        turns, status = state["turns"], state["status"]
        if (pos in WALLS or len(got) != len(set(got)) or not set(got) <= CELLS
                or type(turns) is not int or not 0 <= turns <= MAX_TURNS
                or status not in ("PLAYING", "WON", "LOST")
                or (status == "WON") != (pos == EXIT and set(got) == CELLS)
                or (status == "LOST") != (turns == MAX_TURNS and status != "WON")
                or (status == "PLAYING" and turns == MAX_TURNS)
                or turns < len(got)):
            raise ValueError("Inconsistent save")
        self.position, self.collected = pos, set(got)
        self.turns, self.status = turns, status
        self.message = "Saved round loaded. Press R to restart after game over."


def save_path():
    return Path.home() / ".signal-sprint" / "save.json"


def save_game(game, path=None):
    path = Path(path) if path is not None else save_path()
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Linked save path")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".save-", delete=False) as handle:
            temporary = handle.name
            json.dump(game.snapshot(), handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def load_game(game, path=None):
    path = Path(path) if path is not None else save_path()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
        raise ValueError("Missing, linked or oversized save")
    game.restore(json.loads(path.read_text(encoding="utf-8")))


def launch():
    import tkinter as tk
    root = tk.Tk()
    root.title("Signal Sprint | Offline 2D Puzzle")
    root.geometry("1024x768")
    root.minsize(820, 640)
    root.configure(bg="#101827")
    game = Game()
    language = ["EN"]
    labels = {
        "EN": ("SIGNAL SPRINT", "Collect 3 energy cells, then reach EXIT.",
               "Arrows / WASD / click adjacent tile", "Moves left", "Cells",
               "Restart (R)", "Save (S)", "Load (L)", "日本語"),
        "JP": ("SIGNAL SPRINT", "3つのエネルギーを集めて出口に到達しよう。",
               "矢印 / WASD / 隣のマスをクリック", "残り手数", "回収",
               "最初から (R)", "保存 (S)", "読込 (L)", "English"),
    }
    heading = tk.Label(root, bg="#101827", fg="#e9f4ff",
                       font=("Segoe UI", 26, "bold"))
    heading.pack(pady=(16, 4))
    subtitle = tk.Label(root, bg="#101827", fg="#a8bed5",
                        font=("Segoe UI", 12))
    subtitle.pack()
    frame = tk.Frame(root, bg="#101827")
    frame.pack(fill="both", expand=True, padx=18, pady=12)
    canvas = tk.Canvas(frame, width=585, height=585, bg="#172338",
                       highlightthickness=0)
    canvas.pack(side="left", padx=(0, 20))
    panel = tk.Frame(frame, bg="#101827")
    panel.pack(side="left", fill="both", expand=True)
    info = tk.Label(panel, bg="#101827", fg="#e2f2ff",
                    font=("Segoe UI", 17, "bold"), justify="left")
    info.pack(anchor="w", pady=(18, 14))
    controls = tk.Label(panel, bg="#101827", fg="#9eb5cb",
                        wraplength=280, justify="left")
    controls.pack(anchor="w", pady=(0, 20))
    message = tk.Label(panel, bg="#1d3047", fg="#fff", wraplength=270,
                       justify="left", padx=12, pady=18)
    message.pack(fill="x", pady=(0, 18))
    buttons = []

    def draw():
        words = labels[language[0]]
        heading.config(text=words[0])
        subtitle.config(text=words[1])
        controls.config(text=words[2])
        info.config(text=f"{words[3]}: {MAX_TURNS-game.turns}\n{words[4]}: {len(game.collected)}/3")
        message.config(text=game.status + "\n\n" + game.message,
                       fg="#6de5ba" if game.status == "WON" else
                          "#ff9e9e" if game.status == "LOST" else "#fff")
        for button, title in zip(buttons, words[5:]):
            button.config(text=title)
        canvas.delete("all")
        for y in range(SIZE):
            for x in range(SIZE):
                pos = (x, y)
                left, top = 32 + x*65, 32 + y*65
                color = "#273b53"
                if pos in WALLS:
                    color = "#3b4353"
                elif pos == EXIT:
                    color = "#20786f" if game.collected == CELLS else "#596174"
                elif pos in CELLS - game.collected:
                    color = "#9e7029"
                canvas.create_rectangle(left, top, left+62, top+62,
                                        fill=color, outline="")
                if pos in CELLS - game.collected:
                    canvas.create_oval(left+19, top+19, left+43, top+43,
                                       fill="#ffdf7d", outline="")
                if pos == EXIT:
                    canvas.create_text(left+31, top+31, text="EXIT", fill="white")
                if pos == game.position:
                    canvas.create_oval(left+12, top+12, left+50, top+50,
                                       fill="#64dcff", outline="#efffff", width=2)

    def move(dx, dy):
        game.move(dx, dy)
        draw()

    def restart():
        game.restart()
        draw()

    def save():
        try:
            save_game(game)
            game.message = "Saved on this computer."
        except (OSError, ValueError) as exc:
            game.message = "Save failed: " + type(exc).__name__
        draw()

    def load():
        try:
            load_game(game)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            game.message = "Load failed: " + type(exc).__name__
        draw()

    def toggle():
        language[0] = "JP" if language[0] == "EN" else "EN"
        draw()

    for action in (restart, save, load, toggle):
        button = tk.Button(panel, command=action, bg="#24577d", fg="white",
                           activebackground="#367aa7", activeforeground="white",
                           font=("Segoe UI", 12, "bold"), relief="flat",
                           padx=12, pady=11)
        button.pack(fill="x", pady=5)
        buttons.append(button)

    def key(event):
        if event.keysym in DIRECTIONS:
            move(*DIRECTIONS[event.keysym])
        elif event.keysym.lower() == "r":
            restart()
        elif event.keysym.lower() == "s":
            save()
        elif event.keysym.lower() == "l":
            load()

    def click(event):
        x, y = (event.x-32)//65, (event.y-32)//65
        if 0 <= x < SIZE and 0 <= y < SIZE:
            move(x-game.position[0], y-game.position[1])

    root.bind("<Key>", key)
    canvas.bind("<Button-1>", click)
    draw()
    root.mainloop()


if __name__ == "__main__":
    launch()
