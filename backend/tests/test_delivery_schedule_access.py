"""The frozen schedule uses the same access rules as the live schedule."""

from datetime import date
import unittest
from unittest.mock import patch

import delivery_schedule


class DeliveryScheduleAccessTest(unittest.TestCase):
    def test_only_registered_admins_outside_preview_have_access(self):
        users = (
            ({'role': 'admin', 'is_registered': 1}, True),
            ({'role': 'admin', 'is_registered': 0}, False),
            ({'role': 'admin', 'is_registered': 1, 'preview_role': 'boss'}, False),
            ({'role': 'boss', 'is_registered': 1}, False),
            ({'role': 'employee', 'is_registered': 1}, False),
        )
        for frozen_date in (None, date(2026, 11, 21)):
            with patch.object(delivery_schedule, 'FROZEN_REVIEW_DATE', frozen_date):
                for user, allowed in users:
                    with self.subTest(frozen_date=frozen_date, user=user):
                        self.assertEqual(delivery_schedule.can_view_delivery_schedule(user), allowed)
