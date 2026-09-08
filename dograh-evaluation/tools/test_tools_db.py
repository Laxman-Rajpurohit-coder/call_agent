import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("dograh-evaluation/tools"))
from crm_bridge import exec_tag_customer, exec_save_call_note, exec_schedule_callback, get_records, init_db

class TestCRMToolPersistence(unittest.TestCase):
    def setUp(self):
        init_db()

    def test_tag_customer_persistence(self):
        res = exec_tag_customer("cust_001", "urgent", "Customer requested immediate assistance with application")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["tag"], "urgent")

        # Verify direct DB query
        tags = get_records("customer_tags")
        self.assertTrue(len(tags) > 0)
        self.assertEqual(tags[0]["tag"], "urgent")
        print("  [PASS] tag_customer persisted into database.")

    def test_save_call_note_persistence(self):
        res = exec_save_call_note("call_test_101", "Caller inquired about Balotra office opening hours and location.", "Send SMS with address details", "cust_001")
        self.assertEqual(res["status"], "SUCCESS")

        notes = get_records("call_notes")
        self.assertTrue(len(notes) > 0)
        self.assertEqual(notes[0]["call_id"], "call_test_101")
        print("  [PASS] save_call_note persisted into database.")

    def test_schedule_callback_persistence(self):
        res = exec_schedule_callback("cust_001", "+919876543210", "2026-08-23T10:00:00Z")
        self.assertEqual(res["status"], "SUCCESS")

        cbs = get_records("scheduled_callbacks")
        self.assertTrue(len(cbs) > 0)
        self.assertEqual(cbs[0]["phone_number"], "+919876543210")
        print("  [PASS] schedule_callback persisted into database.")

if __name__ == "__main__":
    unittest.main()
