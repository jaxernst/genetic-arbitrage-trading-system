from subprocess import run
import websocket
import json
from threading import Thread
from time import sleep

def on_open(wsapp):
    payload = { "event": "ping"}
    wsapp.send(json.dumps(payload))
def on_message(wsapp, message):
    print(message)  
def on_close(wsapp):
    print("Closing Connection")


url = "wss://ws.kraken.com"
wsapp = websocket.WebSocketApp(url, on_message=on_message, on_open=on_open, on_close=on_close)

wst = Thread(target=wsapp.run_forever)

wst.daemon = True
wst.start()
print(wsapp.sock.connected)
while not wsapp.sock.connected:
    sleep(3)
    print("Connecting...")


msg_counter = 0
while wsapp.sock.connected:
    sleep(1)
    msg_counter += 1
    resp = input()
    
    payload = { "event": "subscribe",
                "pair": [f"{resp}/USD"],
                "subscription": {"name": "ticker"}}
    wsapp.send(json.dumps(payload))

print("Passed")