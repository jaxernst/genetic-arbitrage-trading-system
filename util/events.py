subscribers = {}

def subscribe(event_type: str, fn):
    if event_type not in subscribers:
        subscribers[event_type] = fn

def post_event(event_type: str, data):
    if not event_type in subscribers:
        return
    subscribers[event_type](data)