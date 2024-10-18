"""
The WsDataUtil is a lightweight, highly compatible Python module for processing WebSocket data.
The parsing, building and masking of WebSocket frames is implemented in C to increase performance.

The core of the module is the <Frame> object as an interface to the C api.
This serves as the result value from parsing and as the parameter for building a WebSocket frame.
A frame is not checked for plausibility or according to the specification RFC6455.
This should be implemented later if required.

For the sake of completeness, the <HandshakeRequest> object is available.
"""

from __future__ import annotations

from typing import Literal, NamedTuple
from base64 import b64encode
from collections import OrderedDict
from hashlib import sha1
from uuid import uuid4

from . import _wsframecoder


__version__ = "0.1"


def _make_accept_key(b64key: bytes):
    """The WebSocket Key conversion:

        - `<String-In>` can be any base64 string.
        - On the server side, the static string ``258EAFA5-E914-47DA-95CA-C5AB0DC85B11`` is appended to the `<String-In>`.
        - The result is hashed with the SHA-1 function.
        - A base64 string is then created from the digest and returned as `<String-Out>`.
    """
    return b64encode(
        sha1(
            b64key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        ).digest()
    )


class HeaderObj(OrderedDict[bytes, bytes]):

    l1: bytes

    def __init__(self, l1: bytes):
        self.l1 = l1
        OrderedDict.__init__(self)

    def to_streamdata(self):
        return self.l1 + b"\r\n" + bytes(b"\r\n").join(
            b"%s: %s" % (k, v)
            for k, v in self.items()
        ) + b"\r\n\r\n"

    @classmethod
    def from_streamdata(cls, data: bytes):
        new = cls(b"")
        data = data.strip().split(b"\r\n")
        new.l1 = data[0]
        for line in data[1:]:
            k, v = line.split(b": ")
            new[k.strip()] = v
        return new


class HandshakeRequest(HeaderObj):
    """
    minimum client request::

        GET /<URL> HTTP/1.1
        Upgrade: websocket
        Connection: Upgrade
        Sec-WebSocket-Key: <String-In>
        Sec-WebSocket-Version: <Version-in>

    minimum server response::

        HTTP/1.1 101 Switching Protocols
        Upgrade: websocket
        Connection: Upgrade
        Sec-WebSocket-Accept: <String-Out>
        Sec-WebSocket-Version: <Version-out>

    ****

    The WebSocket Key conversion:

        - `<String-In>` can be any base64 string.
        - On the server side, the static string ``258EAFA5-E914-47DA-95CA-C5AB0DC85B11`` is appended to the `<String-In>`.
        - The result is hashed with the SHA-1 function.
        - A base64 string is then created from the digest and returned as `<String-Out>`.
    """
    def __init__(
            self,
            websocket_b64key: bytes = b64encode(uuid4().__str__().encode()),
            websocket_version: bytes = b"13",
            websocket_protocols: bytes | None = None,
            resource: bytes = b"/",
            http_version: bytes = b"1.1"
    ):
        super().__init__(b"GET %s HTTP/%s" % (resource, http_version))
        self[b"Connection"] = b"Upgrade"
        self[b"Upgrade"] = b"websocket"
        self[b"Sec-WebSocket-Key"] = websocket_b64key
        self[b"Sec-WebSocket-Version"] = websocket_version
        if websocket_protocols:
            self[b"Sec-WebSocket-Protocol"] = websocket_protocols

    def make_response(
            self,
            websocket_version: bytes = b"13",
            websocket_protocols: bytes | None = None,
            http_version: bytes = b"1.1",
    ) -> HeaderObj:
        h = HeaderObj(b"HTTP/%s 101 Switching Protocols" % http_version)
        h[b"Upgrade"] = b"websocket"
        h[b"Connection"] = b"Upgrade"
        h[b"Sec-WebSocket-Accept"] = _make_accept_key(self[b"Sec-WebSocket-Key"])
        h[b"Sec-WebSocket-Version"] = websocket_version
        if websocket_protocols:
            self[b"Sec-WebSocket-Protocol"] = websocket_protocols
        return h


class OPCODES:
    CONTINUE = 0
    TEXT = 1
    BINARY = 2
    CLOSE = 8
    PING = 9
    PONG = 10


class CloseCode(int):

    def to_payload(self, message_maximal123bytes: bytes = b"") -> bytes:
        """According to RFC6455, the payload must not exceed a total length of 125 bytes,
        of which the first two bytes are reserved for the numeric code and the rest for
        a text message. The transmission of an additional message to the code is usually omitted.
        """
        return self.to_bytes(2, "big") + message_maximal123bytes


class CLOSECODES:
    _0to999_UNUSED = range(0, 1000)
    NORMAL_CLOSURE = CloseCode(1000)
    GOING_AWAY = CloseCode(1001)
    PROTOCOL_ERROR = CloseCode(1002)
    UNSUPPORTED_DATA = CloseCode(1003)
    _1004_UNUSED = CloseCode(1004)
    NO_STATUS_RCVD = CloseCode(1005)
    ABNORMAL_CLOSURE = CloseCode(1006)
    INVALID_DATA = CloseCode(1007)
    POLICY_VIOLATION = CloseCode(1008)
    MESSAGE_TOO_BIG = CloseCode(1009)
    MANDATORY_EXTENSION = CloseCode(1010)
    INTERNAL_ERROR = CloseCode(1011)
    SERVICE_RESTART = CloseCode(1012)
    TRY_AGAIN_LATER = CloseCode(1013)
    BAD_GATEWAY = CloseCode(1014)
    TLS_HANDSHAKE = CloseCode(1015)
    _1016to2999_forExtensions = range(1016, 3000)
    _3000to3999_forApplicationsRegIANA = range(3000, 4000)
    UNAUTHORIZED = CloseCode(3000)
    FORBIDDEN = CloseCode(3003)
    TIMEOUT = CloseCode(3008)
    _4000to4999_forApplications = range(4000, 5000)


def get_close_code_and_message_from_frame(frame: Frame) -> tuple[int, bytes]:
    """According to RFC6455, the payload must not exceed a total length of 125 bytes,
    of which the first two bytes are reserved for the numeric code and the rest for
    a text message. The transmission of an additional message to the code is usually omitted.
    """
    return int.from_bytes(frame.payload[:2], "big"), frame.payload[2:]


class Frame(NamedTuple):
    """
    WebSocket-Frame::

                         0                   1                   2                   3
                         0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
                        |               |               |               |               |
         HEADER         +-+-+-+-+-------+-+-------------+-------------------------------+
                        |F|R|R|R|   op- |M| amount_spec | ... amount (extended I)       |
                        |I|S|S|S|  code |A|             | if amount_spec == (126|127)   |
                        |N|V|V|V|       |S|             |                               |
                        | |1|2|3|  (4)  |K|    (7)      |          (16|64)              |
                        +-+-+-+-+-------+-+-------------+— — — — — — — — — — — — — — — —+
                        | ... amount (extended II) if amount_spec == 127                |
                        +— — — — — — — — — — — — — — — —+-------------------------------+
                        |                               | masking_key if MASK == 1      |
                        +-------------------------------+-------------------------------+
                        | ... masking_key               |
                        +-------------------------------+

         BUFFER                                         +-------------------------------+
                                                        | payload                       |
                        +-------------------------------+— — — — — — — — — — — — — — — —+
                        : ... payload                                                   :
                        +— — — — — — — — — — — — — — — —+— — — — — — — — — — — — — — — —+
                        | ... payload                                                   |
                        +-------------------------------+-------------------------------+

    Fields:
    -------

    **note**: the fields `amount` and `amount_spec` are set by ``from_streamdata`` but are irrelevant for ``to_streamdata``.

    - `payload`: bytes
    - `opcode`: int = OPCODES.TEXT
        message type
    - `mask`: bytes | None = None
        Set with the masking key if the payload is masked
        (according to RFC6455, only messages from the client to the server may be masked).
    - `fin`: Literal[0, 1] | int = 1
        Is used in combination with opcode 0 (continue) and can be used for fragmentation:

            ::

                fin=1 opcode>0: not fragmented
                fin=0 opcode>0: first fragment
                fin=0 opcode=0: further fragment
                fin=1 opcode=0: last fragment
    - `rsv1`: Literal[0, 1] | int = 0
        reserved for extension of the specification
    - `rsv2`: Literal[0, 1] | int = 0
        reserved for extension of the specification
    - `rsv3`: Literal[0, 1] | int = 0
        reserved for extension of the specification
    - `amount_spec`: Literal[126, 127] | int = None
        From a payload size of 126 bytes, the header is increased by 2 bytes
        which contains the actual size specification, amount_spec is then 126;
        from a payload length of 65536 by six more, amount_spec is then 127.
        Smaller payload lengths are displayed directly in this field.
    - `amount`: int = None
        the actual payload size (regardless of the size type)
    """

    payload: bytes
    opcode: int = OPCODES.TEXT
    """message type"""
    mask: bytes | None = None
    """Set with the masking key if the payload is masked 
    (according to RFC6455, only messages from the client to the server may be masked)."""
    fin: Literal[0, 1] | int = 1
    """Is used in combination with opcode 0 (continue) and can be used for fragmentation:
    ::
        fin=1 opcode>0: not fragmented
        fin=0 opcode>0: first fragment
        fin=0 opcode=0: further fragment
        fin=1 opcode=0: last fragment
    """
    rsv1: Literal[0, 1] | int = 0
    """reserved for extension of the specification"""
    rsv2: Literal[0, 1] | int = 0
    """reserved for extension of the specification"""
    rsv3: Literal[0, 1] | int = 0
    """reserved for extension of the specification"""
    amount_spec: Literal[126, 127] | int = None
    """From a payload size of 126 bytes, the header is increased by 2 bytes 
    which contains the actual size specification, amount_spec is then 126; 
    from a payload length of 65536 by six more, amount_spec is then 127.
    Smaller payload lengths are displayed directly in this field."""
    amount: int = None
    """the actual payload size (regardless of the size type)"""

    @classmethod
    def from_streamdata(cls, data: bytes, auto_demask: bool = True) -> Frame:
        """Create the frame object from stream data.
        If `auto_demask` is ``True`` and the mask bit is set,
        unmask the payload directly.
        """
        (
            fin,
            rsv1,
            rsv2,
            rsv3,
            opcode,
            masked,
            amount_spec,
            amount,
            mask,
            payload,
        ) = _wsframecoder.parse(data, auto_demask)
        return Frame(
            payload,
            opcode,
            (mask if masked else None),
            fin,
            rsv1,
            rsv2,
            rsv3,
            amount_spec,
            amount
        )

    def to_streamdata(self) -> bytes:
        """Generate stream data from the frame object.
        Mask the payload if `self.mask` is set.
        """
        return _wsframecoder.build(
            self.fin,
            self.rsv1,
            self.rsv2,
            self.rsv3,
            self.opcode,
            self.mask or b"",
            self.payload,
        )

    def masked_payload(self) -> bytes:
        """Apply the `self.mask` to the `self.payload`.
        """
        return _wsframecoder.masking(self.payload, self.mask or b"")


class FrameFactory:
    @staticmethod
    def TextDataFrame(message: bytes, mask: bytes | None = None, fragment: Literal["first", "continue", "final"] | None = None) -> Frame:
        if fragment == "first":
            opcode = OPCODES.TEXT
            fin = 0
        elif fragment == "continue":
            opcode = OPCODES.CONTINUE
            fin = 0
        elif fragment == "final":
            opcode = OPCODES.CONTINUE
            fin = 1
        else:
            opcode = OPCODES.TEXT
            fin = 1
        return Frame(message, opcode, mask, fin)

    @staticmethod
    def BinaryDataFrame(message: bytes, mask: bytes | None = None, fragment: Literal["first", "continue", "final"] | None = None) -> Frame:
        if fragment == "first":
            opcode = OPCODES.BINARY
            fin = 0
        elif fragment == "continue":
            opcode = OPCODES.CONTINUE
            fin = 0
        elif fragment == "final":
            opcode = OPCODES.CONTINUE
            fin = 1
        else:
            opcode = OPCODES.BINARY
            fin = 1
        return Frame(message, opcode, mask, fin)

    @staticmethod
    def PingFrame() -> Frame:
        return Frame(b'', OPCODES.PING)

    @staticmethod
    def PongFrame() -> Frame:
        return Frame(b'', OPCODES.PONG)

    @staticmethod
    def CloseFrame(close_code: CloseCode, message_maximal123bytes: bytes = b"") -> Frame:
        return Frame(close_code.to_payload(message_maximal123bytes[:123]), OPCODES.CLOSE)
