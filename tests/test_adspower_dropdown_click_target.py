"""Regression tests for the AdsPower search-dropdown click target on macOS.

The operator reported that the Nyxify temp-name search ("Name contains <temp>")
was clicking *beside* the suggestion row, and that it got worse when the AdsPower
window was zoomed in/out. ``AdsPowerUIController._dropdown_click_target`` is pure
geometry, so we can prove the click lands on the correct "Name contains" row at
many resolutions / zoom levels and dropdown layouts without a live AdsPower.

Coordinate tuples match the live collector: ``(top, left, right, bottom, label)``
with the label already lower-cased. The returned value is ``(x, y)`` in the same
screen-point space the real clicker uses.
"""
import unittest

from core.adspower_ui import AdsPowerUIController


def _scaled(elem, scale, off_x, off_y):
    top, left, right, bottom, label = elem
    return (
        int(round(top * scale)) + off_y,
        int(round(left * scale)) + off_x,
        int(round(right * scale)) + off_x,
        int(round(bottom * scale)) + off_y,
        label,
    )


def _bbox(elems):
    top = min(e[0] for e in elems)
    left = min(e[1] for e in elems)
    right = max(e[2] for e in elems)
    bottom = max(e[3] for e in elems)
    return top, left, right, bottom


def _point_in(elem, x, y):
    return elem[1] <= x <= elem[2] and elem[0] <= y <= elem[3]


# Each layout is (name_row_elems, id_row_elems) at 100% zoom, top-left origin.
# The Name row sits above the Profile-ID row, matching AdsPower's ordering.
_LAYOUTS = {
    # Snapchat renders the whole suggestion as one Text node.
    "combined": (
        [(120, 60, 260, 140, "name contains xyz")],
        [(150, 60, 260, 170, "profile id is xyz")],
    ),
    # Field / operator / value split across three Text nodes.
    "split3": (
        [(120, 60, 100, 140, "name"),
         (120, 108, 190, 140, "contains"),
         (120, 198, 250, 140, "xyz")],
        [(150, 60, 150, 170, "profile id"),
         (150, 158, 185, 170, "is"),
         (150, 193, 245, 170, "xyz")],
    ),
    # "Name contains" as one node, the echoed value as another.
    "field_op_combined": (
        [(120, 60, 200, 140, "name contains"),
         (120, 208, 260, 140, "xyz")],
        [(150, 60, 190, 170, "profile id is"),
         (150, 198, 250, 170, "xyz")],
    ),
    # Zoomed-out: rows only ~4px apart — the case the old 12px merge broke.
    "tight": (
        [(120, 60, 260, 130, "name contains xyz")],
        [(134, 60, 260, 144, "profile id is xyz")],
    ),
}

# 0.7 ~ zoomed out / low-res, 1.8 ~ zoomed in / hi-DPI. Offsets emulate different
# window placements (incl. the slightly off-screen top-left AdsPower can use).
_SCALES = (0.7, 1.0, 1.3, 1.8)
_OFFSETS = ((0, 0), (200, 80), (-8, -8))


class DropdownClickTargetTests(unittest.TestCase):
    def _layout(self, key, scale, off_x, off_y):
        name_row, id_row = _LAYOUTS[key]
        name_s = [_scaled(e, scale, off_x, off_y) for e in name_row]
        id_s = [_scaled(e, scale, off_x, off_y) for e in id_row]
        return name_s, id_s, name_s + id_s

    def test_name_search_lands_on_name_row_across_zoom_and_resolution(self):
        for key in _LAYOUTS:
            for scale in _SCALES:
                for off_x, off_y in _OFFSETS:
                    name_s, id_s, items = self._layout(key, scale, off_x, off_y)
                    with self.subTest(layout=key, scale=scale, offset=(off_x, off_y)):
                        target = AdsPowerUIController._dropdown_click_target(
                            items, field="Name", operator="contains", value="xyz"
                        )
                        self.assertIsNotNone(
                            target, f"no target for {key} @ {scale}x")
                        x, y = target

                        # On the Name row's bounding box...
                        top, left, right, bottom = _bbox(name_s)
                        self.assertTrue(left <= x <= right and top <= y <= bottom,
                                        f"{key} @ {scale}x: {target} off the Name row")

                        # ...on a real Name-row text node (never in a seam)...
                        self.assertTrue(
                            any(_point_in(e, x, y) for e in name_s),
                            f"{key} @ {scale}x: {target} not on any Name text node")

                        # ...and clearly above the Profile-ID row (no merge drift).
                        id_top = min(e[0] for e in id_s)
                        self.assertLess(
                            y, id_top,
                            f"{key} @ {scale}x: click drifted toward the ID row")

    def test_tight_rows_are_not_merged_when_zoomed_out(self):
        # Directly exercises the reported failure: two suggestions <12px apart.
        name_s, id_s, items = self._layout("tight", 0.7, 0, 0)
        target = AdsPowerUIController._dropdown_click_target(
            items, field="Name", operator="contains", value="xyz"
        )
        self.assertIsNotNone(target)
        _x, y = target
        name_top, _l, _r, name_bottom = _bbox(name_s)
        self.assertTrue(name_top <= y <= name_bottom)

    def test_profile_id_search_still_targets_the_id_row(self):
        # Nyx's Profile-ID search must keep working unchanged.
        for key in ("combined", "split3", "field_op_combined"):
            id_layout = {
                "combined": [(150, 60, 320, 170, "profile id is k1e0mqys")],
                "split3": [(150, 60, 150, 170, "profile id"),
                           (150, 158, 185, 170, "is"),
                           (150, 193, 320, 170, "k1e0mqys")],
                "field_op_combined": [(150, 60, 190, 170, "profile id is"),
                                      (150, 198, 320, 170, "k1e0mqys")],
            }[key]
            name_row = _LAYOUTS[key][0]
            items = list(name_row) + list(id_layout)
            with self.subTest(layout=key):
                target = AdsPowerUIController._dropdown_click_target(
                    items, field="Profile ID", operator="is", value="k1e0mqys"
                )
                self.assertIsNotNone(target)
                x, y = target
                top, left, right, bottom = _bbox(id_layout)
                self.assertTrue(left <= x <= right and top <= y <= bottom,
                                f"{key}: {target} off the Profile-ID row")

    def test_no_match_returns_none(self):
        items = [(150, 60, 260, 170, "profile id is xyz")]
        self.assertIsNone(
            AdsPowerUIController._dropdown_click_target(
                items, field="Name", operator="contains", value="xyz"
            )
        )

    def test_value_token_disambiguates_between_rows(self):
        # Two Name-contains rows; only the one echoing the searched value wins.
        items = [
            (120, 60, 260, 140, "name contains abc"),
            (160, 60, 260, 180, "name contains xyz"),
        ]
        target = AdsPowerUIController._dropdown_click_target(
            items, field="Name", operator="contains", value="xyz"
        )
        self.assertIsNotNone(target)
        _x, y = target
        self.assertTrue(160 <= y <= 180, f"picked the wrong value row: {target}")


if __name__ == "__main__":
    unittest.main()
