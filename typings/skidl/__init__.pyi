"""Local type stub for the slice of SKiDL that pigtail uses.

SKiDL ships no py.typed marker. This declares only what pigtail touches -- the
boundary of "SKiDL owns electrical connectivity".
"""

from collections.abc import Iterable

NETLIST: str
SKIDL: str

class Pin:
    class types:
        PASSIVE: int

    part: Part
    name: str
    num: int
    net: Net
    def __init__(self, *, num: int = ..., name: str = ..., func: object = ...) -> None: ...
    def connect(self, *others: object) -> None: ...

class Net:
    name: str
    circuit: Circuit
    pins: list[Pin]
    def __init__(self, name: str = ..., *args: object) -> None: ...
    def connect(self, *others: object) -> None: ...
    def is_attached(self, other: Net) -> bool: ...
    def get_nets(self) -> list[Net]: ...
    def get_pins(self) -> list[Pin]: ...

class Bus:
    name: str
    def __init__(self, name: str = ..., *args: Net) -> None: ...

class Part:
    ref: str
    def __init__(
        self,
        *,
        name: str = ...,
        ref_prefix: str = ...,
        ref: str = ...,
        tool: object = ...,
        dest: object = ...,
        tag: str = ...,
        footprint: str = ...,
        pins: Iterable[Pin] = ...,
    ) -> None: ...
    def __getitem__(self, key: str) -> Pin: ...

class Circuit:
    parts: list[Part]
    nets: list[Net]
    def __enter__(self) -> Circuit: ...
    def __exit__(self, *exc: object) -> None: ...
    def get_nets(self) -> list[Net]: ...
    def generate_netlist(self, *, file_: str = ...) -> None: ...
    def generate_dot(self, *, file_: str = ..., **kwargs: object) -> object: ...
    def generate_graph(self, *, file_: str = ..., **kwargs: object) -> object: ...
