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
        self._history = []
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
        self._history.append((self.position, frozenset(self.collected), self.turns, self.status))
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

    def undo(self):
        """Reverse one successful move, including collection and game-over state."""
        if not self._history:
            self.message = "No move to undo."
            return False
        self.position, collected, self.turns, self.status = self._history.pop()
        self.collected = set(collected)
        self.message = "Move undone. Choose your next step."
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
        self._history = []  # Save v1 has no history; never undo into another session.
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


# UI-only revision. Game state, movement, save format and fixed source lineage are unchanged.
UI_MESSAGE_JP = {
    "Collect three cells, then reach EXIT.": "3つのエネルギーを集めて出口へ進もう。",
    "Blocked. Choose another route.": "通れません。別の道を選んでください。",
    "Circuit complete! Press R to restart.": "クリア！ Rで最初から遊べます。",
    "Out of moves. Press R to retry.": "手数がなくなりました。Rで再挑戦。",
    "EXIT locked: collect all three cells first.": "出口はまだ開きません。3つすべて回収しよう。",
    "Find the shortest safe route.": "安全な最短ルートを探そう。",
    "No move to undo.": "戻せる手がありません。",
    "Move undone. Choose your next step.": "1手戻しました。次の手を選ぼう。",
    "Saved round loaded. Press R to restart after game over.": "保存データを読み込みました。終了後はRで再挑戦。",
    "Saved on this computer.": "このPCに保存しました。",
}
UI_STATUS_JP = {"PLAYING": "プレイ中", "WON": "クリア", "LOST": "失敗"}


def ui_message(message, language):
    if language != "JP":
        return message
    if message.startswith("Save failed:"):
        return "保存できませんでした: " + message.split(":", 1)[1].strip()
    if message.startswith("Load failed:"):
        return "読み込めませんでした: " + message.split(":", 1)[1].strip()
    return UI_MESSAGE_JP.get(message, message)


def ui_window_size(work_width, work_height):
    """Conservative *client* dimensions; reserve space for window chrome."""
    if work_width < 840 or work_height < 636:
        raise ValueError("Work area too small for the supported game UI")
    return min(900, work_width - 80), min(620, work_height - 96)


def launch():
    import tkinter as tk
    root = tk.Tk()
    root.title("Signal Sprint | EN")
    root.configure(bg="#101827")
    # On Windows use the taskbar-excluding work area rather than full monitor.
    # A reserved chrome margin is deliberate: Tk geometry is client dimensions.
    work_left, work_top = 0, 0
    work_width, work_height = root.winfo_screenwidth(), root.winfo_screenheight()
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class RECT(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]
        rect = RECT()
        if ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(rect), 0):
            work_left, work_top = rect.left, rect.top
            work_width, work_height = rect.right - rect.left, rect.bottom - rect.top
    width, height = ui_window_size(work_width, work_height)
    root.geometry(f"{width}x{height}+{work_left+16}+{work_top+16}")
    root.minsize(760, 540)
    game = Game()
    language = ["EN"]
    labels = {
        "EN": ("SIGNAL SPRINT", "Collect 3 energy cells, then reach EXIT.",
               "Arrows / WASD / click adjacent tile | J: Japanese",
               "Moves left", "Cells", "Restart (R)", "Undo (U)",
               "Save (S)", "Load (L)", "日本語 (J)"),
        "JP": ("SIGNAL SPRINT", "3つのエネルギーを集めて出口に到達しよう。",
               "矢印 / WASD / 隣のマスをクリック | J: English",
               "残り手数", "回収", "最初から (R)", "1手戻す (U)",
               "保存 (S)", "読込 (L)", "English (J)"),
    }
    heading = tk.Label(root, bg="#101827", fg="#e9f4ff",
                       font=("Segoe UI", 22, "bold"))
    heading.pack(pady=(8, 2))
    subtitle = tk.Label(root, bg="#101827", fg="#a8bed5",
                        font=("Segoe UI", 11))
    subtitle.pack()
    frame = tk.Frame(root, bg="#101827")
    frame.pack(fill="both", expand=True, padx=12, pady=8)
    canvas = tk.Canvas(frame, width=480, height=480, bg="#172338",
                       highlightthickness=0)
    canvas.pack(side="left", padx=(0, 12), anchor="n")
    panel = tk.Frame(frame, bg="#101827")
    panel.pack(side="left", fill="both", expand=True)
    info = tk.Label(panel, bg="#101827", fg="#e2f2ff",
                    font=("Segoe UI", 14, "bold"), justify="left")
    info.pack(anchor="w", pady=(6, 10))
    controls = tk.Label(panel, bg="#101827", fg="#9eb5cb",
                        wraplength=270, justify="left")
    controls.pack(anchor="w", pady=(0, 10))
    message = tk.Label(panel, bg="#1d3047", fg="#fff", wraplength=260,
                       justify="left", padx=8, pady=10)
    message.pack(fill="x", pady=(0, 10))
    button_frame = tk.Frame(panel, bg="#101827")
    button_frame.pack(fill="x")
    button_frame.grid_columnconfigure(0, weight=1)
    button_frame.grid_columnconfigure(1, weight=1)
    buttons = []

    def draw():
        words = labels[language[0]]
        root.title("Signal Sprint | " + language[0])
        heading.config(text=words[0])
        subtitle.config(text=words[1])
        controls.config(text=words[2])
        info.config(text=f"{words[3]}: {MAX_TURNS-game.turns}\n{words[4]}: {len(game.collected)}/3")
        status = UI_STATUS_JP.get(game.status, game.status) if language[0] == "JP" else game.status
        message.config(text=status + "\n\n" + ui_message(game.message, language[0]),
                       fg="#6de5ba" if game.status == "WON" else
                          "#ff9e9e" if game.status == "LOST" else "#fff")
        for button, title in zip(buttons, words[5:]):
            button.config(text=title)
        canvas.delete("all")
        for y in range(SIZE):
            for x in range(SIZE):
                pos = (x, y)
                left, top = 24 + x*52, 24 + y*52
                color = "#273b53"
                if pos in WALLS:
                    color = "#3b4353"
                elif pos == EXIT:
                    color = "#20786f" if game.collected == CELLS else "#596174"
                elif pos in CELLS - game.collected:
                    color = "#9e7029"
                canvas.create_rectangle(left, top, left+49, top+49,
                                        fill=color, outline="")
                if pos in CELLS - game.collected:
                    canvas.create_oval(left+14, top+14, left+35, top+35,
                                       fill="#ffdf7d", outline="")
                if pos == EXIT:
                    canvas.create_text(left+24, top+24, text="EXIT", fill="white")
                if pos == game.position:
                    canvas.create_oval(left+10, top+10, left+39, top+39,
                                       fill="#64dcff", outline="#efffff", width=2)

    def move(dx, dy):
        game.move(dx, dy)
        draw()

    def restart():
        game.restart()
        draw()

    def undo():
        game.undo()
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

    for index, action in enumerate((restart, undo, save, load, toggle)):
        button = tk.Button(button_frame, command=action, bg="#24577d", fg="white",
                           activebackground="#367aa7", activeforeground="white",
                           font=("Segoe UI", 10, "bold"), relief="flat",
                           padx=6, pady=6)
        row, col = divmod(index, 2)
        button.grid(row=row, column=col, columnspan=2 if index == 4 else 1,
                    sticky="ew", padx=3, pady=3)
        buttons.append(button)

    def key(event):
        if event.keysym in DIRECTIONS:
            move(*DIRECTIONS[event.keysym])
        elif event.keysym.lower() == "r":
            restart()
        elif event.keysym.lower() == "u":
            undo()
        elif event.keysym.lower() == "s":
            save()
        elif event.keysym.lower() == "l":
            load()
        elif event.keysym.lower() == "j":
            toggle()

    def click(event):
        x, y = (event.x-24)//52, (event.y-24)//52
        if 0 <= x < SIZE and 0 <= y < SIZE:
            move(x-game.position[0], y-game.position[1])

    root.bind("<Key>", key)
    canvas.bind("<Button-1>", click)
    draw()
    root.mainloop()


if __name__ == "__main__":
    launch()
