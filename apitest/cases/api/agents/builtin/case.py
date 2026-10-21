import unittest
from tests.test_platform_seeds import BuiltinApplicationsTests


def suite():
    return unittest.defaultTestLoader.loadTestsFromTestCase(BuiltinApplicationsTests)
