from abc import ABC, abstractmethod
from typing import List, Tuple

class ExchangeAPI(ABC):

    @abstractmethod
    def get_tradeable_pairs(self, tuple_separate=True, remove_singles=True) -> list:
        pass

    @abstractmethod
    def get_pair_spread(self, pair: Tuple[str]) -> Tuple[float]:
        pass

    @abstractmethod
    def get_multiple_spreads(self, pairs: List[tuple]) -> List[Tuple[float]]:
        pass

    @abstractmethod
    def add_price_stream(self, pair:Tuple[str]) -> None:
        pass

    @abstractmethod
    def remove_price_stream(self, pair:Tuple[str]) -> None:
        pass

    @abstractmethod
    def subscribe_all(self, limit:int=None, pairs: List[str]=None) -> None:
        pass

    @abstractmethod
    def stream_listen(self, message) -> None:
        pass