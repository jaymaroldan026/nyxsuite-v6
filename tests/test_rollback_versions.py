"""Roll Back must offer every published version, not just local snapshots.

v6.0.7 changed the updater so Roll Back can restore any release ever shipped:
``list_all_releases`` enumerates them (newest first) and ``get_release_by_version``
resolves a specific one for download. Local snapshot retention was also raised so
rolling back isn't limited to the previous one or two builds.
"""
import unittest
from unittest import mock

from core import release_updater, update_backup


def _fake_releases():
    # Newest first, mixed asset presence + a draft that must be skipped.
    return [
        {"tag_name": "v6.0.6", "name": "NyxSuite 6.0.6", "draft": False,
         "assets": [{"name": "NyxSuite-v6.0.6.zip", "browser_download_url": "https://x/6.0.6.zip", "size": 10}]},
        {"tag_name": "v6.0.5", "name": "NyxSuite 6.0.5", "draft": True,
         "assets": [{"name": "NyxSuite-v6.0.5.zip", "browser_download_url": "https://x/6.0.5.zip", "size": 10}]},
        {"tag_name": "v6.0.4", "name": "NyxSuite 6.0.4", "draft": False,
         "assets": [{"name": "notes.txt", "browser_download_url": "https://x/notes.txt", "size": 1}]},
        {"tag_name": "v6.0.3", "name": "NyxSuite 6.0.3", "draft": False,
         "assets": [{"name": "NyxSuite-v6.0.3.zip", "browser_download_url": "https://x/6.0.3.zip", "size": 10}]},
    ]


class ListReleasesTests(unittest.TestCase):
    def test_lists_published_releases_with_matching_asset(self):
        with mock.patch.object(release_updater, "_github_request_list", return_value=_fake_releases()):
            infos = release_updater.list_all_releases("owner/repo", "NyxSuite-v*.zip")
        tags = [i.tag_name for i in infos]
        # Draft (6.0.5) and asset-less (6.0.4) releases are excluded; order kept.
        self.assertEqual(tags, ["v6.0.6", "v6.0.3"])
        self.assertEqual(infos[0].asset_url, "https://x/6.0.6.zip")

    def test_get_release_by_version_matches_with_or_without_v(self):
        with mock.patch.object(release_updater, "_github_request_list", return_value=_fake_releases()):
            rel = release_updater.get_release_by_version("owner/repo", "NyxSuite-v*.zip", "6.0.3")
            self.assertEqual(rel.tag_name, "v6.0.3")
            rel2 = release_updater.get_release_by_version("owner/repo", "NyxSuite-v*.zip", "v6.0.6")
            self.assertEqual(rel2.tag_name, "v6.0.6")

    def test_get_release_by_version_raises_for_unknown(self):
        with mock.patch.object(release_updater, "_github_request_list", return_value=_fake_releases()):
            with self.assertRaises(RuntimeError):
                release_updater.get_release_by_version("owner/repo", "NyxSuite-v*.zip", "5.0.0")


class KeepBackupsTests(unittest.TestCase):
    def test_default_retention_is_generous(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("NYX_KEEP_BACKUPS", None)
            self.assertGreaterEqual(update_backup._default_keep_backups(), 10)

    def test_env_override_wins(self):
        import os
        with mock.patch.dict(os.environ, {"NYX_KEEP_BACKUPS": "7"}):
            self.assertEqual(update_backup._default_keep_backups(), 7)


if __name__ == "__main__":
    unittest.main()
