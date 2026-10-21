import unittest
from tests.test_lesson5_interfaces import InterfaceTests

def suite():return unittest.TestSuite([InterfaceTests('test_skill_parser_rejects_bad_files')])
