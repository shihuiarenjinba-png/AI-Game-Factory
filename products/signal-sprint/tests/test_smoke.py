"""Real puzzle path and save/load tests, independent of Tk display."""
import json
from collections import deque
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Game, START, EXIT, CELLS, WALLS, SIZE, MAX_TURNS, save_game, load_game


class Smoke(unittest.TestCase):
    def test_start_and_restart(self):
        game = Game()
        self.assertEqual(game.status, "PLAYING")
        self.assertTrue(game.move(1, 0))
        game.restart()
        self.assertEqual((game.position, game.turns), (START, 0))

    def test_invalid_move_and_wall(self):
        game = Game()
        self.assertFalse(game.move(-1, 0))
        self.assertFalse(game.move(2, 0))
        game.move(1, 0)
        game.move(1, 0)
        self.assertFalse(game.move(0, 1))
        self.assertEqual(game.turns, 2)

    def test_solvable_real_win(self):
        queue = deque([(START, frozenset(), [])])
        seen = {(START, frozenset())}
        solution = None
        while queue:
            pos, collected, moves = queue.popleft()
            if pos == EXIT and collected == CELLS:
                solution = moves
                break
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                nxt = (pos[0]+dx, pos[1]+dy)
                if not (0 <= nxt[0] < SIZE and 0 <= nxt[1] < SIZE) or nxt in WALLS:
                    continue
                got = collected | ({nxt} if nxt in CELLS else set())
                key = (nxt, frozenset(got))
                if key not in seen:
                    seen.add(key)
                    queue.append((nxt, frozenset(got), moves+[(dx, dy)]))
        self.assertIsNotNone(solution)
        self.assertLess(len(solution), MAX_TURNS)
        game = Game()
        for step in solution:
            self.assertTrue(game.move(*step))
        self.assertEqual(game.status, "WON")
        self.assertFalse(game.move(1, 0))

    def test_loss_and_retry(self):
        game = Game()
        for _ in range(MAX_TURNS//2):
            game.move(1, 0)
            game.move(-1, 0)
        self.assertEqual(game.status, "LOST")
        self.assertFalse(game.move(1, 0))
        game.restart()
        self.assertEqual(game.status, "PLAYING")

    def test_save_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"save.json"
            game = Game()
            game.move(1, 0)
            save_game(game, path)
            restored = Game()
            load_game(restored, path)
            self.assertEqual(restored.snapshot(), game.snapshot())

    def test_invalid_save_preserves_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"save.json"
            game = Game()
            game.move(1, 0)
            original = game.snapshot()
            for position, turns, status in (([2, 1], 1, "PLAYING"),
                                            ([0, 0], 1, "WON"),
                                            ([0, 0], 30, "PLAYING")):
                path.write_text(json.dumps({"version": 1, "position": position,
                    "collected": [], "turns": turns, "status": status}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_game(game, path)
                self.assertEqual(game.snapshot(), original)


if __name__ == "__main__":
    unittest.main()
