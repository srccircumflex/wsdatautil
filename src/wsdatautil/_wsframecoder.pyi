from typing import Literal


def parse(
        streamdata: bytes,
        auto_demask: bool
) -> tuple[int, int, int, int, int, int, int, int, bytes, bytes]:
    """
    parse [and decode] a WebSocket frame

    returns: (
        - fin: 0|1,
        - rsv1: 0|1,
        - rsv2: 0|1,
        - rsv3: 0|1,
        - opcode: int,
        - masked: 0|1,
        - len_spec: int,
        - len: int,
        - mask: 4 bytes,
        - masked/de-masked payload: bytes,
    )
    """
    ...

def build(
        fin: Literal[0, 1] | int,
        rsv1: Literal[0, 1] | int,
        rsv2: Literal[0, 1] | int,
        rsv3: Literal[0, 1] | int,
        opcode: Literal[1, 2, 8, 9, 10] | int,
        mask: bytes,
        payload: bytes,
        /
) -> bytes:
    """
    create a WebSocket frame

    - fin: 0|1
    - rsv1: 0|1
    - rsv2: 0|1
    - rsv3: 0|1
    - opcode: int
    - mask: empty or 4 bytes
    - payload: bytes
    """
    ...

def masking(
        payload: bytes,
        mask: bytes,
        /
) -> bytes:
    """
    apply masking to a WebSocket payload

    - payload: bytes
    - mask: empty or 4 bytes
    """
    ...
