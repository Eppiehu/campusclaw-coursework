import unittest
from tests.test_lesson5_flow import FlowTests
from tests.test_lesson5_sse import StreamingTests
from tests.test_lesson5_wire import WireTests

def suite():
    suite=unittest.TestSuite()
    for kind in (FlowTests,StreamingTests,WireTests):suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(kind))
    return suite
