from pathlib import Path
import tempfile
import unittest

from core.nyxify_task_store import NyxifyTaskStore


ROOT = Path(__file__).resolve().parents[1]


class NyxifySnapboardBridgeTests(unittest.TestCase):
    def test_content_script_polls_pending_adspower_id_updates(self):
        content = (ROOT / "nyxify_extension" / "content.js").read_text(encoding="utf-8")

        self.assertIn("function pollPendingAdspowerUpdate()", content)
        self.assertIn('"/adspower_update/pending"', content)
        self.assertIn('"/adspower_update/result"', content)
        self.assertIn("startAdspowerUpdatePoll();", content)

    def test_task_store_persists_snapboard_row_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = NyxifyTaskStore(Path(tmp) / "tasks.db")

            store.upsert_task(
                row_key="snapboard:505811",
                model="Clea",
                ip_address="198.51.100.10",
                proxy_address="198.51.100.10:9000:user:pass",
                username="cleaopala",
                email="clea@example.com",
                password="KyotoRiver%12",
            )

            row = store.list_tasks()[0]
            self.assertEqual(row["password"], "KyotoRiver%12")

            claimed = store.claim_pending_tasks(limit=1)
            self.assertEqual(claimed[0]["password"], "KyotoRiver%12")

    def test_task_store_updates_snapboard_row_password_on_resync(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = NyxifyTaskStore(Path(tmp) / "tasks.db")

            store.upsert_task(
                row_key="snapboard:505811",
                model="Clea",
                ip_address="198.51.100.10",
                username="cleaopala",
                password="OldPassword1!",
            )
            store.upsert_task(
                row_key="snapboard:505811",
                model="Clea",
                ip_address="198.51.100.10",
                username="cleaopala",
                password="NewPassword2!",
            )

            row = store.list_tasks()[0]
            self.assertEqual(row["password"], "NewPassword2!")

    def test_extension_extracts_and_flushes_snapboard_row_password(self):
        content = (ROOT / "nyxify_extension" / "content.js").read_text(encoding="utf-8")
        background = (ROOT / "nyxify_extension" / "background.js").read_text(encoding="utf-8")

        self.assertIn('["password", "pass", "snap password", "snapchat password", "account password"]', content)
        self.assertIn("password: password", content)
        self.assertIn("const password = String(row.password || \"\").trim();", background)
        self.assertIn("password: entry.password", background)

    def test_content_script_locks_tv_phone_provider(self):
        content = (ROOT / "nyxify_extension" / "content.js").read_text(encoding="utf-8")

        # Lock in TV mirrors Lock in G5 but targets the SMS/phone provider toggle.
        self.assertIn("function findTVProviderButton()", content)
        self.assertIn("function lockProviderToTV()", content)
        self.assertIn('data-provider="textverified"', content)
        self.assertIn("setphoneprovider('textverified')", content)
        self.assertIn("if (config.lockTV)", content)
        self.assertIn("if (config.lockG5)", content)

    def test_content_script_auto_clicks_sign_in_when_logged_out(self):
        content = (ROOT / "nyxify_extension" / "content.js").read_text(encoding="utf-8")

        # Auto-login only clicks Sign In; Chrome supplies the saved credentials.
        self.assertIn("function isLoginScreenVisible()", content)
        self.assertIn("function findSignInButton()", content)
        self.assertIn("function loginCredentialsPrefilled()", content)
        self.assertIn("function attemptAutoLogin()", content)
        self.assertIn('button[type="submit"]', content)
        self.assertIn("startAutoLoginPoll();", content)


if __name__ == "__main__":
    unittest.main()
