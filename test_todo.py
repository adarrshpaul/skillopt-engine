from todo_app import TodoList

def test_add_item():
    """Test adding a single item."""
    tl = TodoList()
    tl.add('Buy milk')
    assert len(tl.list()) == 1
    assert tl.list() == ['Buy milk']

def test_add_multiple_items():
    """Test adding multiple items."""
    tl = TodoList()
    tl.add('Task A')
    tl.add('Task B')
    tl.add('Task C')
    assert len(tl.list()) == 3
    assert tl.list() == ['Task A', 'Task B', 'Task C']

def test_mark_complete():
    """Test marking an item as complete."""
    tl = TodoList()
    tl.add('Write report')
    tl.mark_complete(0)
    assert tl.list() == ['[x] Write report']

def test_remove_item():
    """Test removing an item by index."""
    tl = TodoList()
    tl.add('Task 1')
    tl.add('Task 2')
    tl.remove(0)
    assert len(tl.list()) == 1
    assert tl.list() == ['Task 2']

def test_list_empty():
    """Test listing an empty todo list."""
    tl = TodoList()
    assert tl.list() == []

def test_remove_last_item():
    """Test removing the last item."""
    tl = TodoList()
    tl.add('Task 1')
    tl.add('Task 2')
    tl.remove(1)
    assert len(tl.list()) == 1
    assert tl.list() == ['Task 1']
