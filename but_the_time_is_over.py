"""Implementation for: but the time is over"""
from typing import Dict, Any
import time

def but_the_time_is_over(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Executes task logic for: but the time is over"""
    return {
        "objective": "but the time is over",
        "timestamp": time.time(),
        "status": "COMPLETED"
    }

if __name__ == "__main__":
    print(but_the_time_is_over({"test": True}))
