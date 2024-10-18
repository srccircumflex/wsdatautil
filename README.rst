WsDataUtil (WebSocket Data Util)
################################

The WsDataUtil is a lightweight, highly compatible Python module to process WebSocket data.
The parsing, building and masking of WebSocket frames is implemented in C to increase performance.

The core of the module is the ``Frame`` object as an interface to the C api.
This serves as the result value from parsing and as the parameter for building a WebSocket frame.
A frame is not checked for plausibility or according to the specification RFC6455.
This should be implemented later if required.

For the sake of completeness, the ``HandshakeRequest`` object is available.

Installation::

    python -m pip install wsdatautil --upgrade

Gallery of WebSocket data
=========================

Connection establishment
------------------------

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


The WebSocket Key conversion
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- `<String-In>` can be any base64 string.
- On the server side, the static string ``258EAFA5-E914-47DA-95CA-C5AB0DC85B11`` is appended to the `<String-In>`.
- The result is hashed with the SHA-1 function.
- A base64 string is then created from the digest and returned as `<String-Out>`.

WebSocket-Frame
---------------

::

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

****

Tests
=====

::

    python test.py
    python test.py -h
