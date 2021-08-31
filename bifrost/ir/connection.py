"""
Internal representations (IR) for internal use
"""
from dataclasses import dataclass
from typing import Generic, TypeVar

from bifrost.ir.layer import Layer


class Connector:
    pass

@dataclass
class AllToAllConnector(Connector):
    """Also Known As DenseConnector"""

@dataclass
class MatrixConnector(Connector):
    weights_key: str = "weights"

@dataclass
class DenseConnector(Connector):
    weights_key: str = "weights"

@dataclass
class ConvolutionConnector(Connector):
    weights_key: str = "weights"
    padding_key: str = "padding"


From = TypeVar("From", Layer, Layer)
To = TypeVar("To", Layer, Layer)


@dataclass
class Connection(Generic[From, To]):
    pre: From
    post: To
    connector: Connector

    def variable(self, channel: int) -> str:
        return f"c_{self.pre.name}_{self.post.name}_{channel}"
