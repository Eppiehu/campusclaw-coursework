import unittest
from tests.test_platform import PlatformTests


def suite():
    return unittest.TestSuite(PlatformTests(name) for name in [
        "test_template_crud_binding_scope_and_effective_prompt",
        "test_cross_class_template_binding_and_tool_write_denied",
    ])
