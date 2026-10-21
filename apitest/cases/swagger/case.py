import unittest
from tests.test_lesson5_swagger import SwaggerTests

def suite():return unittest.defaultTestLoader.loadTestsFromTestCase(SwaggerTests)
