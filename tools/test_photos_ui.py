#!/usr/bin/env python3
"""Tests for the photo manager's rules. Run: python3 tools/test_photos_ui.py"""
import os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos_ui as ui
import sync


class Names(unittest.TestCase):
    def test_phone_names_are_plain(self):
        self.assertEqual(sync.photo_name("My Photo (1).JPG"), "My_Photo__1__JPG.jpg")
        self.assertEqual(sync.photo_name("-rf;x.jpg"), "rf_x_jpg.jpg")
        self.assertEqual(sync.photo_name("---"), "photo.jpg")

    def test_base_of(self):
        for f in ("a_jpg.jpg", "a_jpg.bw.jpg", "a_jpg.blur.jpg", "a_jpg.bw.blur.jpg"):
            self.assertEqual(sync.base_of(f), "a_jpg")
        for f in ("notes.txt", "a b.jpg", "x;rm.jpg", ".jpg"):
            self.assertIsNone(sync.base_of(f))

    def test_picture_extension(self):
        self.assertEqual(ui.picture_extension("../a.HEIC"), ".heic")
        self.assertEqual(ui.picture_extension("C:\\x\\b.Jpg"), ".jpg")
        self.assertIsNone(ui.picture_extension("notes.txt"))
        self.assertIsNone(ui.picture_extension("noext"))


class PhotoList(unittest.TestCase):
    def test_reads_what_write_produces(self):
        real = sync.WEB
        sync.WEB = tempfile.mkdtemp()
        try:
            sync.write_photos_js(["photos/a.jpg"], {"photos/a.jpg": {"hue": 1}})
            with open(os.path.join(sync.WEB, "photos.js")) as f:
                self.assertEqual(sync.parse_photo_list(f.read()), (["photos/a.jpg"], {"photos/a.jpg": {"hue": 1}}))
        finally:
            shutil.rmtree(sync.WEB)
            sync.WEB = real

    def test_phone_line_endings_and_short_form(self):
        self.assertEqual(sync.parse_photo_list('var PHOTOS = ["photos/a.jpg"];\r\nvar PHOTO_INFO = {};\r\n'), (["photos/a.jpg"], {}))
        self.assertEqual(sync.parse_photo_list("var PHOTOS = [];\n"), ([], {}))

    def test_a_bad_read_is_never_an_empty_list(self):
        for bad in ("", "TIMEOUT after 20s", "error: device offline", "var PHOTOS = [broken"):
            self.assertIsNone(sync.parse_photo_list(bad))


class Sorting(unittest.TestCase):
    FILES = {"a.jpg": "10", "a.bw.jpg": "5", "a.blur.jpg": "1", "a.bw.blur.jpg": "1", "b.jpg": "20", "c.jpg": "30", "notes.txt": "1"}

    def test_the_list_decides_what_shows_and_keeps_its_order(self):
        shown, hidden = ui.sort_photos(["photos/c.jpg", "photos/a.jpg"], self.FILES)
        self.assertEqual([p["name"] for p in shown], ["c", "a"])
        self.assertEqual(hidden, [{"name": "b", "v": "20"}])

    def test_listed_but_gone_is_left_out(self):
        self.assertEqual(ui.sort_photos(["photos/zz.jpg", "photo.jpg"], {"a.jpg": "1"}), ([], [{"name": "a", "v": "1"}]))


class Requests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp()
        self.phone = ui.Phone(self.work)
        self.phone.state = {"checked": True, "connected": True, "shown": [{"name": "a", "v": "1"}], "hidden": [{"name": "b", "v": "2"}], "at": "1"}

    def tearDown(self):
        shutil.rmtree(self.work)

    def test_only_real_photos_can_be_named(self):
        self.phone.check_names(["a", "b"])
        for bad in (["../x"], ["a;rm -rf x"], ["other"], [5], [], None, "a"):
            with self.assertRaises(ui.Refused):
                self.phone.check_names(bad)

    def test_nothing_is_accepted_while_the_phone_is_away(self):
        self.phone.state["connected"] = False
        with self.assertRaises(ui.Refused):
            self.phone.ask("hide", ["a"])
        self.assertTrue(self.phone.jobs.empty())

    def test_thumbnail_refuses_unknown_names(self):
        for bad in ("../../etc/passwd", "zz", ""):
            with self.assertRaises(ui.Refused):
                self.phone.thumbnail(bad, "1")


class Dropped(unittest.TestCase):
    def test_only_files_on_this_computer(self):
        for bad in ("https://example.com/a.jpg", "file://other/a.jpg", 5):
            with self.assertRaises(ui.Refused):
                ui.dropped_paths([bad])

    def test_folder_means_the_pictures_in_it(self):
        d = tempfile.mkdtemp()
        try:
            for n in ("a b.JPG", "c.heic", "notes.txt"):
                open(os.path.join(d, n), "w").close()
            got = ui.dropped_paths(["file://" + ui.urllib.parse.quote(d)])
            self.assertEqual([os.path.basename(p) for p in got], ["a b.JPG", "c.heic"])
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
