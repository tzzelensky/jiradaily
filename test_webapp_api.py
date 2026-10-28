#!/usr/bin/env python3
"""Comprehensive test suite for WebApp API and Revolver Drum scheduling."""

import os
import sys
import unittest
import threading
import time
import requests
from datetime import date

# Set working directory to repo
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO_DIR)

import store
import report
import bot
import api_server


class TestWebAppApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start api server on test port 18086
        cls.port = 18086
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server = api_server.run_api_server(host="127.0.0.1", port=cls.port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def test_01_health_endpoint(self):
        resp = requests.get(f"{self.base_url}/api/health", timeout=10)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("status"), "connected")
        self.assertIn("latency_ms", data)
        self.assertIn("jira_base", data)

    def test_02_config_schedule_and_bot_sync(self):
        # 1. Update schedule config via API
        payload = {"personal_time": "10:45", "team_time": "13:15"}
        resp = requests.post(f"{self.base_url}/api/config", json=payload, timeout=5)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data["config"]["personal_time"], "10:45")
        self.assertEqual(data["config"]["team_time"], "13:15")

        # 2. Verify GET /api/config returns updated values
        get_resp = requests.get(f"{self.base_url}/api/config", timeout=5)
        self.assertEqual(get_resp.status_code, 200)
        get_data = get_resp.json()
        self.assertEqual(get_data["config"]["personal_time"], "10:45")
        self.assertEqual(get_data["config"]["team_time"], "13:15")

        # 3. Verify bot help text reflects dynamic schedule
        help_msg = bot.help_text(store.ADMIN_CHAT_ID)
        self.assertIn("10:45 ЕКБ", help_msg)
        self.assertIn("13:15 ЕКБ", help_msg)

        # 4. Verify bot next_scheduled_run calculation uses dynamic time
        now = report.datetime(2026, 10, 29, 9, 0, 0, tzinfo=report.TZ)
        next_run = bot.next_scheduled_run(now)
        self.assertEqual(next_run.hour, 10)
        self.assertEqual(next_run.minute, 45)

        next_team_run = bot.next_team_scheduled_run(now)
        self.assertEqual(next_team_run.hour, 13)
        self.assertEqual(next_team_run.minute, 15)

    def test_03_me_endpoint(self):
        resp = requests.get(f"{self.base_url}/api/me?tg_id={store.ADMIN_CHAT_ID}", timeout=5)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("is_admin"))
        self.assertEqual(data.get("role"), "admin")
        self.assertTrue(data.get("authorized"))
        self.assertTrue(data.get("can_create_team"))

    def test_04_teams_crud_with_colon_unquoting(self):
        # 1. Create team
        t_resp = requests.post(
            f"{self.base_url}/api/teams",
            json={"name": "QA Revolver Unit", "owner_chat_id": store.ADMIN_CHAT_ID},
            timeout=5,
        )
        self.assertEqual(t_resp.status_code, 200)
        team = t_resp.json()["team"]
        team_id = team["id"]

        # 2. Add member with Jira account ID containing colons
        jira_aid = "712020:f5cd43e1-7a96-4216-960f-82a1c60761ea"
        jira_name = "Тимофей Зеленский"
        m_resp = requests.post(
            f"{self.base_url}/api/teams/{team_id}/members",
            json={"jira_account_id": jira_aid, "jira_display_name": jira_name},
            timeout=5,
        )
        self.assertEqual(m_resp.status_code, 200)
        self.assertTrue(m_resp.json()["ok"])

        # 3. Remove member using percent-encoded account ID: /api/teams/:id/members/712020%3A...
        import urllib.parse
        encoded_aid = urllib.parse.quote(jira_aid, safe="")
        del_m_resp = requests.delete(
            f"{self.base_url}/api/teams/{team_id}/members/{encoded_aid}",
            timeout=5,
        )
        self.assertEqual(del_m_resp.status_code, 200)
        self.assertTrue(del_m_resp.json()["ok"])

        # 4. Delete team
        del_t_resp = requests.delete(
            f"{self.base_url}/api/teams/{team_id}?tg_id={store.ADMIN_CHAT_ID}",
            timeout=5,
        )
        self.assertEqual(del_t_resp.status_code, 200)
        self.assertTrue(del_t_resp.json()["ok"])

    def test_05_invites_generator(self):
        resp = requests.post(
            f"{self.base_url}/api/invites",
            json={"label": "Revolver Test Invite", "created_by": store.ADMIN_CHAT_ID},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("token", data)
        self.assertTrue(data["link"].startswith("https://t.me/jirasumbot?start=inv_"))

        # Verify listing
        list_resp = requests.get(f"{self.base_url}/api/invites", timeout=5)
        self.assertEqual(list_resp.status_code, 200)
        invites = list_resp.json().get("invites", [])
        self.assertTrue(any(inv["token"] == data["token"] for inv in invites))

    def test_06_logs_endpoint(self):
        resp = requests.get(f"{self.base_url}/api/logs", timeout=5)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertIsInstance(data.get("logs"), list)


if __name__ == "__main__":
    unittest.main()
