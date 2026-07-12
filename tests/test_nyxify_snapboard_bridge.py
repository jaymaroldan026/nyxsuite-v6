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

    def test_redo_email_and_phone_wait_out_the_cooldown(self):
        content = (ROOT / "nyxify_extension" / "content.js").read_text(encoding="utf-8")

        # The redo (get-new) buttons carry a ~60s cooldown during which they are
        # disabled and clicking is a no-op — reorder must wait it out so the
        # email/number actually changes instead of silently failing.
        self.assertIn("function findRedoEmailButton(rowId)", content)
        self.assertIn("function findRedoPhoneButton(rowId)", content)
        self.assertIn("function readRedoCooldownSeconds(button)", content)
        self.assertIn("function isRedoOnCooldown(button)", content)
        self.assertIn("async function waitForRedoReady(", content)
        # Both reorder paths route through the cooldown wait.
        self.assertIn("waitForRedoReady(function () { return findRedoEmailButton(rowId); })", content)
        self.assertIn("waitForRedoReady(function () { return findRedoPhoneButton(rowId); })", content)

    def test_content_script_types_stored_login_credentials(self):
        content = (ROOT / "nyxify_extension" / "content.js").read_text(encoding="utf-8")

        # Chrome autofill does not reliably fill the SnapBoard login form, so the
        # extension types the stored credentials into any blank field, then
        # submits — and only submits once BOTH fields are populated.
        self.assertIn('var SNAPBOARD_LOGIN_KEY = "nyxifySnapboardLogin";', content)
        self.assertIn("function getSnapboardLoginCredentials()", content)
        self.assertIn("async function fillLoginCredentialsIfNeeded()", content)
        self.assertIn("function submitLoginForm(button)", content)
        self.assertIn("requestSubmit", content)
        # The prefilled gate now requires the password too (no empty submits).
        self.assertIn('var pass = document.getElementById("loginPassword");', content)
        self.assertIn("await fillLoginCredentialsIfNeeded();", content)

    def test_content_script_recovers_a_logged_out_board_on_demand(self):
        content = (ROOT / "nyxify_extension" / "content.js").read_text(encoding="utf-8")

        self.assertIn("async function ensureSnapboardLoggedIn(", content)
        self.assertIn('message.action === "ensure_logged_in"', content)

    def test_background_refresh_and_relogin_recovery(self):
        background = (ROOT / "nyxify_extension" / "background.js").read_text(encoding="utf-8")

        # A failed fetch tries an in-place re-login (typing the stored creds in
        # the content script) before any heavier reload.
        self.assertIn("async function ensureSnapboardLoggedIn(", background)
        self.assertIn('action: "ensure_logged_in"', background)
        self.assertIn("async function snapboardFetchWithRelogin(", background)
        # Only a board that was actually signed out triggers an OTP/SMS retry —
        # a "code not landed yet" empty result must not reload the whole board.
        self.assertIn("recovered.wasLoggedOut && recovered.loggedIn", background)

        def dispatcher_for(action_marker):
            # Which helper wraps this action's bridge fetch.
            tail = background.split(action_marker)[0][-400:]
            call = tail.rsplit("await ", 1)[-1]
            for name in ("snapboardFetchWithRefresh", "snapboardFetchWithRelogin", "sendMessageToSnapboardTab"):
                if name + "(" in call:
                    return name
            return call

        # email/phone can be stale ("no pending order") -> full refresh+relogin.
        self.assertEqual(dispatcher_for('action: "email_fetch"'), "snapboardFetchWithRefresh")
        self.assertEqual(dispatcher_for('action: "phone_fetch"'), "snapboardFetchWithRefresh")
        # otp/sms use the lighter relogin-only recovery (no disruptive reload).
        self.assertEqual(dispatcher_for('action: "otp"'), "snapboardFetchWithRelogin")
        self.assertEqual(dispatcher_for('action: "sms"'), "snapboardFetchWithRelogin")

    def test_options_page_stores_snapboard_login_credentials(self):
        options_html = (ROOT / "nyxify_extension" / "options.html").read_text(encoding="utf-8")
        options_js = (ROOT / "nyxify_extension" / "options.js").read_text(encoding="utf-8")

        self.assertIn('id="snapboardLoginName"', options_html)
        self.assertIn('id="snapboardLoginPassword"', options_html)
        self.assertIn('type="password"', options_html)
        # Stored under a dedicated local key (kept out of the synced runner config).
        self.assertIn('SNAPBOARD_LOGIN_KEY = "nyxifySnapboardLogin"', options_js)
        self.assertIn("chrome.storage.local.set({", options_js)
        self.assertIn("chrome.storage.local.get(SNAPBOARD_LOGIN_KEY", options_js)


if __name__ == "__main__":
    unittest.main()
