# Genetic Arbitrage Trading System Overview
A genetic algorithm based swap trading system to automate trading on cryptocurrency exchanges.

## Project Overview
This project aims to implement a flexible trading system that can operate unsupervised on centralized and decentralized cryptocurrency exchanges simultaneously. The trading system utilizes a plugin style architecture that allows various trading strategies to be tested and traded with, but the current implementation focusses solely on identifying and trading arbitrage opportunities (inter-exchange and intra-exchange).


## System Architecture
The system can be broken down into several layers: The API layer, the Data Management layer, the Trading Layer, and the Account layer. The following ULM class diagram provides an overview of these layers and the components involved:


![alt text](https://github.com/jaxernst/GenticArbitrageTradingSystem/blob/main/SystemArchitecture.png?raw=true)



## Use of this repository
My intent of making this public is NOT for someone to use this system for their own trading as is. While all the code is there for someone to live trade on an exchange, I highly advise against this because this is not a mature project, and there are still plenty of problems to work through. I am actively developing this application, so files and modules will be frequently modifi3ed and added to.
