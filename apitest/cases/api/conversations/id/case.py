import unittest
from tests.test_lesson5_flow import FlowTests

def suite():return unittest.TestSuite([FlowTests('test_title_first24_and_disabled_locked_agent')])
