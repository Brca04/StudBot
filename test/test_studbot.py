"""Unit tests for StudBot. Run with:  py -m unittest test/test_studbot.py"""
import os
import sys
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "alpha"))
import StudBot  # noqa: E402


class TestParseDateString(unittest.TestCase):
    def test_date_only_with_trailing_dot(self):
        # Format from "Datum objave"
        self.assertEqual(
            StudBot.parse_date_string("15.04.2026."),
            datetime(2026, 4, 15),
        )

    def test_date_with_time(self):
        # Format from "Oglas vrijedi do"
        self.assertEqual(
            StudBot.parse_date_string("24.04.2026. 09:49"),
            datetime(2026, 4, 24, 9, 49),
        )

    def test_unparseable_returns_none(self):
        self.assertIsNone(StudBot.parse_date_string("next tuesday"))
        self.assertIsNone(StudBot.parse_date_string(""))


class TestCleanupOldJobs(unittest.TestCase):
    def test_valid_job_kept(self):
        future = (datetime.now() + timedelta(days=5)).isoformat()
        jobs = [{"title": "A", "expires": future, "message_id": "1", "tier": "green"}]
        kept = StudBot.cleanup_old_jobs(jobs)
        self.assertEqual(len(kept), 1)

    @patch.object(StudBot, "delete_webhook_message", return_value=True)
    def test_expired_job_triggers_delete(self, mock_delete):
        past = (datetime.now() - timedelta(days=1)).isoformat()
        jobs = [{"title": "Stale", "expires": past, "message_id": "123", "tier": "green"}]
        kept = StudBot.cleanup_old_jobs(jobs)
        self.assertEqual(kept, [])
        mock_delete.assert_called_once()
        # Webhook URL and message_id forwarded
        self.assertEqual(mock_delete.call_args[0][1], "123")

    @patch.object(StudBot, "delete_webhook_message")
    def test_expired_without_message_id_does_not_call_delete(self, mock_delete):
        past = (datetime.now() - timedelta(days=1)).isoformat()
        jobs = [{"title": "Legacy", "expires": past}]  # no message_id / tier
        kept = StudBot.cleanup_old_jobs(jobs)
        self.assertEqual(kept, [])
        mock_delete.assert_not_called()


class TestEnrichWithDates(unittest.TestCase):
    @patch.object(StudBot, "fetch_job_dates")
    @patch.object(StudBot.time, "sleep", lambda *_: None)
    def test_skips_already_expired(self, mock_fetch):
        # Site still listed a job past its own "Oglas vrijedi do"
        mock_fetch.return_value = ("01.01.2020.", "31.01.2020. 12:00")
        jobs = [{"title": "Zombie", "link": "https://x", "pay": "9 eur/h"}]
        result = StudBot.enrich_with_dates(jobs)
        self.assertEqual(result, [])  # dropped, would have been infinite-loop bait

    @patch.object(StudBot, "fetch_job_dates")
    @patch.object(StudBot.time, "sleep", lambda *_: None)
    def test_uses_scraped_expiry(self, mock_fetch):
        future_year = datetime.now().year + 1
        mock_fetch.return_value = ("01.01.2026.", f"31.12.{future_year}. 23:59")
        jobs = [{"title": "Fresh", "link": "https://x", "pay": "12 eur/h"}]
        result = StudBot.enrich_with_dates(jobs)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["expires"].startswith(f"{future_year}-12-31"))


class TestGetTier(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(StudBot.get_tier(10.00), "purple")
        self.assertEqual(StudBot.get_tier(9.99), "green")
        self.assertEqual(StudBot.get_tier(8.00), "green")
        self.assertEqual(StudBot.get_tier(7.99), "red")
        self.assertEqual(StudBot.get_tier(6.06), "red")
        self.assertIsNone(StudBot.get_tier(6.05))
        self.assertIsNone(StudBot.get_tier(0))


class TestParsePay(unittest.TestCase):
    def test_comma_decimal(self):
        self.assertEqual(StudBot.parse_pay("10,50 eur/h"), 10.5)

    def test_dot_decimal(self):
        self.assertEqual(StudBot.parse_pay("8.25 eur/h"), 8.25)

    def test_garbage_returns_zero(self):
        self.assertEqual(StudBot.parse_pay("N/A"), 0.0)
        self.assertEqual(StudBot.parse_pay(""), 0.0)


class TestSortJobs(unittest.TestCase):
    def test_sorted_by_pay_then_posted_desc(self):
        jobs = [
            {"pay": "7,00 eur/h", "posted_iso": "2026-04-10"},
            {"pay": "12,00 eur/h", "posted_iso": "2026-04-05"},
            {"pay": "12,00 eur/h", "posted_iso": "2026-04-15"},  # newer, same pay
        ]
        ordered = StudBot.sort_jobs(jobs)
        self.assertEqual(ordered[0]["posted_iso"], "2026-04-15")  # newest of top-pay first
        self.assertEqual(ordered[1]["posted_iso"], "2026-04-05")
        self.assertEqual(ordered[2]["pay"], "7,00 eur/h")


class TestCleanupEdgeCases(unittest.TestCase):
    def test_unparseable_expires_kept(self):
        jobs = [{"title": "X", "expires": "whenever"}]
        self.assertEqual(len(StudBot.cleanup_old_jobs(jobs)), 1)

    def test_missing_expires_kept(self):
        jobs = [{"title": "Legacy"}]
        self.assertEqual(len(StudBot.cleanup_old_jobs(jobs)), 1)


class TestFetchJobDates(unittest.TestCase):
    HTML = """
    <html><body>
      <p class="font-medium">Datum objave:</p><span>15.04.2026.</span>
      <div>Oglas vrijedi do <strong>15.05.2026. 12:07</strong></div>
    </body></html>
    """

    @patch.object(StudBot, "requests")
    def test_scrapes_both_dates(self, mock_requests):
        mock_requests.get.return_value = MagicMock(text=self.HTML)
        publish, expires = StudBot.fetch_job_dates("https://x")
        self.assertEqual(publish, "15.04.2026.")
        self.assertEqual(expires, "15.05.2026. 12:07")

    @patch.object(StudBot, "requests")
    def test_missing_fields_returns_empty(self, mock_requests):
        mock_requests.get.return_value = MagicMock(text="<html></html>")
        self.assertEqual(StudBot.fetch_job_dates("https://x"), ("", ""))

    @patch.object(StudBot, "requests")
    def test_network_error_returns_empty(self, mock_requests):
        mock_requests.get.side_effect = Exception("boom")
        self.assertEqual(StudBot.fetch_job_dates("https://x"), ("", ""))


class TestDeleteWebhookMessage(unittest.TestCase):
    @patch.object(StudBot.requests, "delete")
    def test_success_204(self, mock_del):
        mock_del.return_value = MagicMock(status_code=204)
        self.assertTrue(StudBot.delete_webhook_message("https://wh", "42"))
        mock_del.assert_called_once()
        self.assertIn("/messages/42", mock_del.call_args[0][0])

    @patch.object(StudBot.requests, "delete")
    def test_failure_status(self, mock_del):
        mock_del.return_value = MagicMock(status_code=404)
        self.assertFalse(StudBot.delete_webhook_message("https://wh", "42"))

    @patch.object(StudBot.requests, "delete", side_effect=Exception("net"))
    def test_network_exception(self, _):
        self.assertFalse(StudBot.delete_webhook_message("https://wh", "42"))


class TestSendToWebhook(unittest.TestCase):
    @patch.object(StudBot.time, "sleep", lambda *_: None)
    @patch.object(StudBot.requests, "post")
    def test_stores_message_id_and_tier(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"id": "msg-abc"},
        )
        jobs = [{"title": "T", "link": "L", "pay": "9 eur/h", "date": "15.04.2026.", "posted_iso": ""}]
        StudBot.send_to_webhook("https://wh", jobs, "green")
        self.assertEqual(jobs[0]["message_id"], "msg-abc")
        self.assertEqual(jobs[0]["tier"], "green")
        # wait=true is required to get the id back
        self.assertIn("wait=true", mock_post.call_args[0][0])

    @patch.object(StudBot.time, "sleep", lambda *_: None)
    @patch.object(StudBot.requests, "post")
    def test_non_2xx_does_not_set_id(self, mock_post):
        mock_post.return_value = MagicMock(status_code=429, json=lambda: {})
        jobs = [{"title": "T", "link": "L", "pay": "9 eur/h", "date": "15.04.2026.", "posted_iso": ""}]
        StudBot.send_to_webhook("https://wh", jobs, "green")
        self.assertNotIn("message_id", jobs[0])


class TestBackupIfStale(unittest.TestCase):
    @patch.object(StudBot, "shutil")
    @patch.object(StudBot.os.path, "exists")
    def test_noop_when_no_jobs_file(self, mock_exists, mock_shutil):
        mock_exists.side_effect = lambda p: False
        StudBot.backup_if_stale()
        mock_shutil.copy2.assert_not_called()

    @patch.object(StudBot, "shutil")
    @patch.object(StudBot.os.path, "getmtime")
    @patch.object(StudBot.os.path, "exists")
    def test_copies_when_backup_missing(self, mock_exists, mock_mtime, mock_shutil):
        mock_exists.side_effect = lambda p: p == "jobs.json"
        StudBot.backup_if_stale()
        mock_shutil.copy2.assert_called_once_with("jobs.json", "backup.json")
        mock_mtime.assert_not_called()

    @patch.object(StudBot, "shutil")
    @patch.object(StudBot.os.path, "getmtime")
    @patch.object(StudBot.os.path, "exists", return_value=True)
    def test_skips_when_backup_fresh(self, _exists, mock_mtime, mock_shutil):
        mock_mtime.return_value = time.time() - 60  # 1 minute old
        StudBot.backup_if_stale()
        mock_shutil.copy2.assert_not_called()

    @patch.object(StudBot, "shutil")
    @patch.object(StudBot.os.path, "getmtime")
    @patch.object(StudBot.os.path, "exists", return_value=True)
    def test_copies_when_backup_stale(self, _exists, mock_mtime, mock_shutil):
        mock_mtime.return_value = time.time() - (StudBot.BACKUP_INTERVAL_SECONDS + 10)
        StudBot.backup_if_stale()
        mock_shutil.copy2.assert_called_once_with("jobs.json", "backup.json")


if __name__ == "__main__":
    unittest.main()
