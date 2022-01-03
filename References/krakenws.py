#!/usr/bin/env python

# Kraken WebSocket API
# 
# Usage: ./krakenws.py feed/endpoint [parameters]
# Example: ./krakenws.py ticker XBT/USD
# Example: ./krakenws.py spread XBT/USD XBT/EUR ETH/USD LTC/EUR
# Example: ./krakenws.py book XBT/USD XBT/EUR 10
# Example: ./krakenws.py openOrders
# Example: ./krakenws.py ownTrades
# Example: ./krakenws.py addOrder pair=XBT/EUR type=sell ordertype=limit price=7500 volume=0.125
# Example: ./krakenws.py cancelOrder txid=OADMSD-7AGC3-IMB46A,OD6VRE-HCSPM-CKORER
# 
# For account management and trading, a valid WebSocket authentication token (from the REST API GetWebSocketsToken endpoint) must be provided in a plain text file named WS_Token.

import sys
import signal
from websocket import create_connection

def timeoutfunction(signalnumber, frame):
	raise KeyboardInterrupt

signal.signal(signal.SIGALRM, timeoutfunction)

api_status = {"ping"}
api_public = {"trade", "book", "ticker", "spread", "ohlc"}
api_private = {"openOrders", "ownTrades", "balances"}
api_trading = {"addOrder", "cancelOrder", "cancelAll", "cancelAllOrdersAfter"}
api_domain_public = "wss://ws.kraken.com/"
api_domain_private = "wss://ws-auth.kraken.com/"
api_symbols = ""
api_number = 0

if len(sys.argv) < 2:
	api_feed = "ping"
else:
	api_feed = sys.argv[1]

if api_feed in api_status:
	api_domain = api_domain_public
	api_data = '{"event":"%(feed)s"}' % {"feed":api_feed}
	signal.alarm(3)
elif api_feed in api_public:
	if len(sys.argv) < 3:
		print("Usage: %s feed/endpoint [parameters]" % sys.argv[0])
		print("Example: %s ticker XBT/USD" % sys.argv[0])
		sys.exit(1)
	for count in range(2, len(sys.argv)):
		if sys.argv[count].isdecimal() == True:
			api_number = int(sys.argv[count])
		else:
			if len(api_symbols) == 0:
				api_symbols += sys.argv[count].upper()
			else:
				api_symbols += '","' + sys.argv[count].upper()
	if api_feed == 'book':
		api_data = '{"event":"subscribe", "subscription":{"name":"%(feed)s", "depth":%(depth)d}, "pair":["%(symbols)s"]}' % {"feed":api_feed, "symbols":api_symbols, "depth":api_number if api_number != 0 else 10}
	elif api_feed == 'ohlc':
		api_data = '{"event":"subscribe", "subscription":{"name":"%(feed)s", "interval":%(interval)d}, "pair":["%(symbols)s"]}' % {"feed":api_feed, "symbols":api_symbols, "interval":api_number if api_number != 0 else 1}
	else:
		api_data = '{"event":"subscribe", "subscription":{"name":"%(feed)s"}, "pair":["%(symbols)s"]}' % {"feed":api_feed, "symbols":api_symbols}
	api_domain = api_domain_public
elif api_feed in api_private:
	api_domain = api_domain_private
	try:
		api_token = open("WS_Token").read().strip()
	except:
		print("WebSocket authentication token missing (WS_Token)")
		sys.exit(1)
	if len(sys.argv) >= 3:
		if api_feed == 'openOrders':
			api_data = '{"event":"subscribe", "subscription":{"name":"%(feed)s", "ratecounter":%(ratecounter)s, "token":"%(token)s"}}' % {"feed":api_feed, "ratecounter":sys.argv[2].split('=')[1], "token":api_token}
		elif api_feed == 'ownTrades':
			api_data = '{"event":"subscribe", "subscription":{"name":"%(feed)s", "snapshot":%(snapshot)s, "token":"%(token)s"}}' % {"feed":api_feed, "snapshot":sys.argv[2].split('=')[1], "token":api_token}
		else:
			api_data = '{"event":"subscribe", "subscription":{"name":"%(feed)s", "token":"%(token)s"}}' % {"feed":api_feed, "token":api_token}
	else:
		api_data = '{"event":"subscribe", "subscription":{"name":"%(feed)s", "token":"%(token)s"}}' % {"feed":api_feed, "token":api_token}
elif api_feed in api_trading:
	api_domain = api_domain_private
	try:
		api_token = open("WS_Token").read().strip()
	except:
		print("WebSocket authentication token missing (WS_Token)")
		sys.exit(1)
	api_data = '{"event":"%(feed)s", "token":"%(token)s"' % {"feed":api_feed, "token":api_token}
	for count in range(2, len(sys.argv)):
		if sys.argv[count].split('=')[0] == 'txid':
			api_data = api_data + ', "%(name)s":["%(value)s"]' % {"name":sys.argv[count].split('=')[0], "value":sys.argv[count].split('=')[1].replace(',', '","')}
		elif sys.argv[count].split('=')[0] == 'reqid':
			api_data = api_data + ', "%(name)s":%(value)s' % {"name":sys.argv[count].split('=')[0], "value":sys.argv[count].split('=')[1]}
		elif sys.argv[count].split('=')[0] == 'timeout':
			api_data = api_data + ', "%(name)s":%(value)s' % {"name":sys.argv[count].split('=')[0], "value":sys.argv[count].split('=')[1]}
		else:
			api_data = api_data + ', "%(name)s":"%(value)s"' % {"name":sys.argv[count].split('=')[0], "value":sys.argv[count].split('=')[1]}
	api_data = api_data + '}'
	signal.alarm(3)
else:
	print("Usage: %s feed/endpoint [parameters]" % sys.argv[0])
	print("Example: %s ticker XBT/USD" % sys.argv[0])
	sys.exit(1)

try:
	ws = create_connection(api_domain)
	print("WebSocket -> Client: %s" % ws.recv())
except Exception as error:
	print("WebSocket connection failed (%s)" % error)
	sys.exit(1)

try:
	print("Client -> WebSocket: %s" % api_data)
	ws.send(api_data)
	print("WebSocket -> Client: %s" % ws.recv())
except Exception as error:
	print("WebSocket subscription/request failed (%s)" % error)
	ws.close()
	sys.exit(1)

while True:
	try:
		print("WebSocket -> Client: %s" % ws.recv())
	except KeyboardInterrupt:
		ws.close()
		sys.exit(0)
	except Exception as error:
		print("WebSocket messages failed (%s)" % error)
		sys.exit(1)

sys.exit(1)
