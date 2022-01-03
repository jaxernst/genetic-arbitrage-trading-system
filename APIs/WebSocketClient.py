from threading import Thread
import json
import websocket
from time import sleep

from APIs import abstract

class WebSocketClient:
    def __init__(self, parentExchange: abstract, url: str):
        self.ws = websocket.WebSocketApp(url, on_message=self.on_message, 
                                            on_open=self.on_open, 
                                            on_close=self.on_close)
        self.connected =  False
        self.parentExchange  = parentExchange
        self.socket_open = False
        self.thread_started = False

    def on_open(self, wsapp):
        self.socket_open = True
        print("Socket opened")

    def on_message(self, wsapp, message):
        self.parentExchange.stream_listen(message) 

    def on_close(self, wsapp):
        self.connected = False
        print("Closing Connection")

    def send(self, payload:json):
        # Connect if not already connected
        if not self.thread_started:
            self.connect()

        # Send subcription request if connection is active
        if self.ws.sock.connected:
            self.ws.send(payload)
        else:
            Exception()
        
    def connect(self):
        # Setup thread 
        wst = Thread(target=self.ws.run_forever)
        wst.daemon = True
        print("Starting socket thread...")
        self.thread_started = True
        wst.start()
    
        self.wait_for_connection()
    
    def wait_for_connection(self):
        error = False
        conn_timeout = 5
        while not self.ws.sock and conn_timeout: # Wait for socket to be created
            sleep(.5)
            print("Waiting for socket initialization...")
            conn_timeout -= 1
            if conn_timeout == 0:
                error = True
                print("Connection failed")

        while not self.ws.sock.connected and conn_timeout:
            sleep(1)
            print("Connecting...")
            conn_timeout -= 1
            if conn_timeout == 0:
                error = True
                print("Connection failed,  trying again...")
                self.wait_for_connection()
        print("Socket Connected")
