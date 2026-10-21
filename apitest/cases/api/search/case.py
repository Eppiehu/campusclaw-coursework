import unittest
from tests.test_lesson5_storage import StorageTests
from tests.test_lesson5_interfaces import InterfaceTests

def suite():
    return unittest.TestSuite([StorageTests('test_rrf_qdrant_scope_and_id_consistency'),InterfaceTests('test_conversation_creation_private_and_hidden_agents')])
