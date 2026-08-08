import pytest
import os
import sys

# Add workspace root to path
sys.path.insert(0, '/Users/adarrsh/workspace')

@pytest.fixture
def tmp_graph_db(tmp_path):
    """Provides an isolated graph.db for testing."""
    import graph_store
    original = graph_store.DB_FILE
    graph_store.DB_FILE = str(tmp_path / 'test_graph.db')
    graph_store.init_db()
    yield graph_store.DB_FILE
    graph_store.DB_FILE = original

@pytest.fixture
def tmp_checkpoint_file(tmp_path):
    """Provides an isolated checkpoints.json for testing."""
    import p2_worker_stub as p2
    original = p2.CHECKPOINT_FILE
    p2.CHECKPOINT_FILE = str(tmp_path / 'test_checkpoints.json')
    yield p2.CHECKPOINT_FILE
    p2.CHECKPOINT_FILE = original
