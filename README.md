## pymoteGO

`python` binding for `cogmoteGO`

## Installation

```sh
pip install pymotego
```

or

```sh
uv add pymotego
```

## Usage
### Data broadcast

```python
from pymotego.broadcast import Broadcast
from datetime import datetime, timedelta
from time import sleep
import random

broadcast = Broadcast()

results = ["correct", "incorrect", "timeout"]

for i in range(10):
    start_time = datetime.now() - timedelta(seconds=random.randint(1, 60))
    
    duration = random.randint(1, 5)
    stop_time = start_time + timedelta(seconds=duration)
    
    result = random.choice(results)
    
    correct_rate = 1.0 if result == "correct" else 0.0
    
    data = {
        "trial_id": i + 1,
        "trial_start_time": start_time.isoformat(),
        "trial_stop_time": stop_time.isoformat(),
        "result": result,
        "correct_rate": correct_rate
    }
    
    future = broadcast.send(data)
    print(future.result())

    sleep(duration)
```