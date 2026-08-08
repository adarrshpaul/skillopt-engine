def binary_search(array, target):
  """
  Performs a binary search on a sorted array.

  Args:
    array: A sorted list of elements.
    target: The element to search for.

  Returns:
    The index of the target element if found, otherwise -1.
  """
  left = 0
  right = len(array) - 1

  while left <= right:
    mid = (left + right) // 2
    if array[mid] == target:
      return mid
    elif array[mid] < target:
      left = mid + 1
    else:
      right = mid - 1

  return -1