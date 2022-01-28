# Genetic Arbitrage Trading System Overview
A genetic algorithm based swap trading system to automate trading on cryptocurrency exchanges.

## Overview
This is a modular trading system designed to be operated with 'ArbitrageEngines', which are plugin-style modules that identify artbitrage opportunities across and within exchanges. To provide real-time exchange order feeds to the system, exchange websocket feeds are utilized. 


This project is named after its primary (and first developed) ArbitrageEngine, which utilizes a genetic algorithm to identify arbitrage opporunties in cryptocurrency markets. This type of arbitrage stems from triangular arbitrage, but allows for swap-sequences between more than 3 currencies. The genetic algorithm performs best with a large number of assets to swap between, as it gains an edge over competion when the perumations of tradeable sequences are very large. The source modules also include full functionality for API/Websocket authentication and trade automation (only Kucoin supported currently).



## Use of this repository
My intent of making this public is NOT for someone to use this system for their own trading as is. While all the code is there for someone to live trade on an exchange, I highly advise against this because this is not a mature project, and there are still plenty of problems to work through. I am actively developing this application, so files and modules will be frequently modifi3ed and added to.
