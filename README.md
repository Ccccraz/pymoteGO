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

### Internal backup API

The backup API is available only on cogmoteGO's loopback-only internal listener.
The default address is `http://127.0.0.1:9011/api/`; do not expose this listener
through a reverse proxy.

```python
from pymotego import BackupClient, BackupDestination, BackupSource

source = BackupSource(
    root_id="project-data",
    entries=("20260713", "20260714/realdata/result.jsonl"),
)
destination = BackupDestination(
    root_id="lab-nas",
    path="experiments/project/data",
)

with BackupClient() as client:
    created = client.create(source, destination)
    current = client.current()

print(created.id, current.status if current else "no task")
```

The source and Samba root IDs must already be configured in cogmoteGO. Creating
a backup starts an asynchronous task; call `current()` to fetch its latest state.
Before any task has been created, `current()` returns `None`.
