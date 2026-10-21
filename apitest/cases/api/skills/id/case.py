import unittest
from tests.test_lesson5_interfaces import InterfaceTests

def suite():return unittest.TestSuite([InterfaceTests('test_agent_skill_crud_scopes_and_student_writes')])
