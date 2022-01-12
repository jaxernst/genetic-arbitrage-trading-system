subscribers = {}

def subscribe(event_type: str, fn):
    if event_type not in subscribers:
        subscribers[event_type] = [fn]
    else:
        subscribers[event_type].append(fn)

def post_event(event_type: str, data=None):
    if not event_type in subscribers:
        return
    for fn in subscribers[event_type]:
        if data: 
            fn(data)
        else:
            fn()