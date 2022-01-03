from subprocess import run
import websocket
import json
from threading import Thread
from time import sleep
import tkinter as tk

def on_open(wsapp):
    payload = { "event": "ping"}
    wsapp.send(json.dumps(payload))
def on_message(wsapp, message):
    print(message)  
def on_close(wsapp):
    print("Closing Connection")


url = "wss://ws.kraken.com"
wsapp = websocket.WebSocketApp(url, on_message=on_message, on_open=on_open, on_close=on_close)
wsapp.skip_utf8_validation = True
wst = Thread(target=wsapp.run_forever)
wst.daemon = True
wst.start()

conn_timeout = 5
while not wsapp.sock.connected and conn_timeout:
    sleep(1)
    conn_timeout -= 1

msg_counter = 0

master = tk.Tk()
master.geometry("150x90")
tk.Label(master, text="Add Coin").pack()


def evaluate(event):
    coin = entry.get()
    payload = { "event": "subscribe",
                "pair": [f"{coin.upper()}/USD"],
                "subscription": {"name": "ticker"}}
    wsapp.send(json.dumps(payload))
    label = tk.Label(master, text=f"{coin.upper()} Added").pack()
    print(coin)

entry = tk.Entry(master)
entry.bind("<Return>",evaluate)
entry.pack()

master.mainloop()
