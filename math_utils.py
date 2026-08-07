# math_utils.py

def add(a, b):
    """Return the sum of a and b."""
    return a + b

def subtract(a, b):
    """Return the difference of a and b."""
    return a - b
```

```python
# test_math_utils.py

import math_utils

# Test add(3, 4)
result_add = math_utils.add(3, 4)
assert result_add == 7, f"add(3, 4) failed: expected 7, got {result_add}"
print(f"add(3, 4) = {result_add} ✓")

# Test subtract(10, 3)
result_sub = math_utils.subtract(10, 3)
assert result_sub == 7, f"subtract(10, 3) failed: expected 7, got {result_sub}"
print(f"subtract(10, 3) = {result_sub} ✓")

print("All tests passed.")