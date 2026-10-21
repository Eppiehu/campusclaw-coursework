import unittest
from tests.test_platform import PlatformTests


def suite():
    return unittest.TestSuite(PlatformTests(name) for name in [
        "test_real_mcp_initialize_discover_call_and_schema",
        "test_check5_model_tool_call_mcp_result_and_second_request",
        "test_unbound_model_tool_rejected_and_stream_closed",
    ])
