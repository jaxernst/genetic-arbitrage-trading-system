import base64
import hashlib
import hmac
import time
import requests
from util.obj_funcs import load_json

class KucoinAuthenticator:
    unlocked = False
    key = load_json("Kucoin_API_Key.json")
    API_KEY = key["API_KEY"]
    API_SECRET = key["API_SECRET"]
    if "PASSPHRASE" in key:
        PASSPHRASE = key["PASSPHRASE"]
    else:
        PASSPHRASE = None

    def __init__(self, server):
        self.SERVER = server
        self.unlock()

    def unlock(self):
        if not self.PASSPHRASE:
            self.PASSPHRASE = input("Enter your Kucoin API Passphrase: ")
        self.unlocked = True
    
    def request(self, endpoint, type, data=None):
        URL = self.SERVER + endpoint
        now = int(time.time() * 1000)
        
        str_to_sign = str(now) + type.upper() + endpoint

        if data:
            str_to_sign += data

        signature = self.encode(str_to_sign)
        
        if not self.unlocked:
            self.unlock()

        passphrase = self.encode(self.PASSPHRASE)
        headers = {
                    "KC-API-SIGN": signature,
                    "KC-API-TIMESTAMP": str(now),
                    "KC-API-KEY": self.API_KEY,
                    "KC-API-PASSPHRASE": passphrase,
                    "KC-API-KEY-VERSION": "2"
                   }

        if type.upper() == "POST":
            headers["Content-Type"] = "application/json"
            return requests.request('post', URL, headers=headers, data=data)

        if type.upper() == "GET":
            return requests.request('get', URL, headers=headers)    

    def encode(self, msg):
        return base64.b64encode(hmac.new(self.API_SECRET.encode('utf-8'), msg.encode('utf-8'), hashlib.sha256).digest())
    

