class TodoItem:
    def __init__(self, description):
        self.description = description
        self.completed = False

class TodoList:
    def __init__(self):
        self._items = []

    def add(self, description: str) -> None:
        """Add a new todo item."""
        self._items.append(TodoItem(description))

    def remove(self, index: int) -> None:
        """Remove the item at the given index."""
        del self._items[index]

    def list(self) -> list[str]:
        """Return descriptions of all items (completed ones marked with [x])."""
        return [
            f"[x] {item.description}" if item.completed else item.description
            for item in self._items
        ]

    def mark_complete(self, index: int) -> None:
        """Mark the item at the given index as complete."""
        self._items[index].completed = True
