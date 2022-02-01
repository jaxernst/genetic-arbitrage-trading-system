# Genetic Arbitrage Trading System Overview
A modular swap trading system to automate trading on cryptocurrency exchanges.

## Project Overview
This project aims to implement a flexible trading system that can operate unsupervised on centralized and decentralized cryptocurrency exchanges simultaneously. The trading system utilizes a plugin style architecture that allows various trading strategies to be tested and traded with, but the current implementation focusses solely on identifying and trading arbitrage opportunities (inter-exchange and intra-exchange).

## Development
This is a personal project of mine, and while the project is still very young (~3 months), I spend much of my free time adding features, optimizing, and solving issues that arise. I am currently the sole contributor to the project, thus the documentation is limited. As the project matures, I hope to provide more extensive documentation and open it up for contribution.

## System Architecture
The system can be broken down into several layers: The API layer, the Data Management layer, the Trading Layer, and the Account layer. The following ULM class diagram provides an overview of these layers and the components involved:


![SystemArchitecureDiagram](https://github.com/jaxernst/GenticArbitrageTradingSystem/blob/main/SystemArch.png?raw=true)
(functions and attributes to be added)


## Use of this repository
My intent of making this public is NOT for someone to use this system for their own trading as is. While all the code is there for someone to live trade on an exchange, I highly advise against this because this is not a mature project, and there are still plenty of problems to work through. This code is here for anyone to read, learn from, and borrow from. 
