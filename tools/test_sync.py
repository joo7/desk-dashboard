#!/usr/bin/env python3
"""Tests for the to-do logic in sync.py. Run: python3 tools/test_sync.py"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync


def item(t, done=False):
    return {"t": t, "done": done}


class Parse(unittest.TestCase):
    def test_round_trip(self):
        items = [item("Buy milk"), item("Call [bank]", True)]
        self.assertEqual(sync.parse_todo(sync.format_todo(items).splitlines()), items)

    def test_blank_and_bare_lines(self):
        self.assertEqual(sync.parse_todo(["", "  plain  ", "[X] big"]), [item("plain"), item("big", True)])


class Diff(unittest.TestCase):
    def changes(self, old, new):
        ops = sync.diff_ops(old, new, 7)
        self.assertEqual([o["id"] for o in ops], list(range(7, 7 + len(ops))))
        self.assertEqual(sync.apply_ops(old, ops), new)   # the changes must rebuild the new list
        return [(o["op"], o["t"]) for o in ops]

    def test_each_command(self):
        a, b = item("a"), item("b")
        self.assertEqual(self.changes([a, b], [a, b, item("c")]), [("add", "c")])
        self.assertEqual(self.changes([a, b], [item("a", True), b]), [("done", "a")])
        self.assertEqual(self.changes([item("a", True)], [a]), [("undone", "a")])
        self.assertEqual(self.changes([a, b], [b]), [("rm", "a")])
        self.assertEqual(self.changes([a], [a]), [])

    def test_item_deleted_on_phone_can_be_added_again(self):
        self.assertEqual(sync.apply_ops([], [{"op": "add", "t": "x", "id": 1}]), [item("x")])

    def test_stale_change_is_harmless(self):
        self.assertEqual(sync.apply_ops([item("a")], [{"op": "rm", "t": "gone", "id": 1}, {"op": "done", "t": "gone", "id": 2}]), [item("a")])


class PickHue(unittest.TestCase):
    def test_colourful_beats_grey(self):
        hue, sat = sync.pick_hue([(6000, 120, 120, 120), (3000, 200, 30, 180), (1000, 240, 240, 240)])
        self.assertTrue(290 < hue < 320 and sat > 50)

    def test_specks_and_extremes_are_ignored(self):
        hue, _ = sync.pick_hue([(5, 255, 0, 0), (5000, 30, 80, 160), (5000, 2, 2, 2)])
        self.assertTrue(200 < hue < 230)

    def test_empty_falls_back(self):
        self.assertEqual(sync.pick_hue([]), (200, 0))


class PhotoName(unittest.TestCase):
    def test_plain_and_stable(self):
        self.assertEqual(sync.photo_name("My trip (1).JPEG"), "My_trip__1__JPEG.jpg")

    def test_same_stem_does_not_collide(self):
        self.assertNotEqual(sync.photo_name("a.png"), sync.photo_name("a.jpg"))


if __name__ == "__main__":
    unittest.main()
