import pprint
import socket
import threading
import unittest
import webbrowser
from pathlib import Path
from sys import argv
from time import perf_counter_ns

from wsdatautil import _wsframecoder
from wsdatautil import Frame, OPCODES, CLOSECODES, StreamReader
from wsdatautil import get_close_code_and_message_from_frame
from wsdatautil import HandshakeRequest


class TestWebSocketFrame(unittest.TestCase):

    def test_frame_creation(self):
        # Basic test for frame creation with default settings
        payload = b'Hello, WebSocket!'
        frame = Frame(payload=payload, opcode=OPCODES.TEXT, fin=1)

        # Check attribute values
        self.assertEqual(frame.payload, payload)
        self.assertEqual(frame.opcode, OPCODES.TEXT)
        self.assertEqual(frame.fin, 1)
        self.assertEqual(frame.rsv1, 0)
        self.assertEqual(frame.rsv2, 0)
        self.assertEqual(frame.rsv3, 0)
        self.assertIsNone(frame.mask)

    def test_all_length_combinations(self):
        # Test all combinations of length types (small, 16-bit extended, 64-bit extended),
        # masked/unmasked, with different opcodes and flag variations.

        # List of payloads for different length types
        payloads = {
            "small": b'short payload',
            "extended_16": b'a' * 200,  # > 125 bytes, should use 16-bit extended length
            "extended_64": b'b' * 70000  # > 65535 bytes, should use 64-bit extended length
        }

        # List of opcodes to test
        opcodes = [OPCODES.TEXT, OPCODES.BINARY, OPCODES.PING, OPCODES.PONG]

        # Flags for fin and RSV bits
        flags = [
            {"fin": 1, "rsv1": 0, "rsv2": 0, "rsv3": 0},  # No RSV flags set
            {"fin": 0, "rsv1": 1, "rsv2": 0, "rsv3": 0},  # RSV1 set
            {"fin": 0, "rsv1": 0, "rsv2": 1, "rsv3": 0},  # RSV2 set
            {"fin": 0, "rsv1": 0, "rsv2": 0, "rsv3": 1},  # RSV3 set
            {"fin": 1, "rsv1": 1, "rsv2": 1, "rsv3": 1}  # All RSV flags set
        ]

        # Test each combination of payload length, masking, opcode, and flags
        for length_type, payload in payloads.items():
            for masked in [True, False]:
                for opcode in opcodes:
                    for flag_combination in flags:
                        with self.subTest(length_type=length_type, masked=masked, opcode=opcode, flags=flag_combination):
                            # Create the frame with given parameters
                            frame = Frame(
                                payload=payload,
                                opcode=opcode,
                                fin=flag_combination["fin"],
                                rsv1=flag_combination["rsv1"],
                                rsv2=flag_combination["rsv2"],
                                rsv3=flag_combination["rsv3"],
                                mask=b'\x01\x02\x03\x04' if masked else None
                            )

                            # Convert to byte stream
                            stream_data = frame.to_streamdata()

                            # Parse back the frame from byte stream
                            parsed_frame = Frame.from_streamdata(stream_data)

                            # Assertions to validate frame properties
                            self.assertEqual(parsed_frame.payload, payload)
                            self.assertEqual(parsed_frame.opcode, opcode)
                            self.assertEqual(parsed_frame.fin, flag_combination["fin"])
                            self.assertEqual(parsed_frame.rsv1, flag_combination["rsv1"])
                            self.assertEqual(parsed_frame.rsv2, flag_combination["rsv2"])
                            self.assertEqual(parsed_frame.rsv3, flag_combination["rsv3"])

                            # Verify length specifications based on payload length
                            if length_type == "small":
                                self.assertLessEqual(len(payload), 125)
                                self.assertEqual(parsed_frame.amount_spec, len(payload))
                            elif length_type == "extended_16":
                                self.assertGreater(len(payload), 125)
                                self.assertLessEqual(len(payload), 65535)
                                self.assertEqual(parsed_frame.amount_spec, 126)
                            elif length_type == "extended_64":
                                self.assertGreater(len(payload), 65535)
                                self.assertEqual(parsed_frame.amount_spec, 127)

                            # Check mask if it was set
                            if masked:
                                self.assertIsNotNone(parsed_frame.mask)
                                self.assertEqual(len(parsed_frame.mask), 4)
                            else:
                                self.assertIsNone(parsed_frame.mask)

    def test_close_code_parsing(self):
        # Test parsing of close code and optional close reason
        close_code = CLOSECODES.NORMAL_CLOSURE
        reason = b'Normal closure'
        payload = close_code.to_bytes(2, "big") + reason
        frame = Frame(payload=payload, opcode=OPCODES.CLOSE)

        # Extract the close code and reason
        code, extracted_reason = get_close_code_and_message_from_frame(frame)
        self.assertEqual(code, close_code)
        self.assertEqual(extracted_reason, reason)

    def test_to_streamdata(self):
        payload = b'Hello, WebSocket!'
        frame = Frame(payload=payload, opcode=OPCODES.TEXT, fin=1)
        stream_data = frame.to_streamdata()

        self.assertIsInstance(stream_data, bytes)
        self.assertGreater(len(stream_data), 0)

    def test_from_streamdata(self):
        payload = b'Hello, WebSocket!'
        original_frame = Frame(payload=payload, opcode=OPCODES.TEXT, fin=1)
        stream_data = original_frame.to_streamdata()

        parsed_frame = Frame.from_streamdata(stream_data)

        self.assertEqual(parsed_frame.payload, original_frame.payload)
        self.assertEqual(parsed_frame.opcode, original_frame.opcode)
        self.assertEqual(parsed_frame.fin, original_frame.fin)

    def test_masking(self):
        payload = b'Hello, WebSocket!'
        mask_key = b'\x01\x02\x03\x04'
        frame = Frame(payload=payload, mask=mask_key)

        masked_payload = frame.masked_payload()
        self.assertNotEqual(masked_payload, payload)

        demasked_payload = _wsframecoder.masking(masked_payload, mask_key)
        self.assertEqual(demasked_payload, payload)

    def test_rsv_bits_set(self):
        payload = b'Test message with RSV bits'
        frame = Frame(payload=payload, opcode=OPCODES.TEXT, fin=1, rsv1=1, rsv2=1, rsv3=1)
        stream_data = frame.to_streamdata()

        parsed_frame = Frame.from_streamdata(stream_data)

        self.assertEqual(parsed_frame.rsv1, 1)
        self.assertEqual(parsed_frame.rsv2, 1)
        self.assertEqual(parsed_frame.rsv3, 1)

    def test_constant_byte_parsing(self):
        test_cases = [
            # Small payload, no masking, TEXT frame, fin set, no RSV bits
            {
                "name": "small_unmasked_text",
                "bytes": b'\x81\x0dHello, World!',
                "expected": {
                    "opcode": OPCODES.TEXT,
                    "fin": 1,
                    "rsv1": 0,
                    "rsv2": 0,
                    "rsv3": 0,
                    "payload": b'Hello, World!',
                    "masked": False
                }
            },
            # Small payload, masked, BINARY frame, fin unset, RSV1 set
            {
                "name": "small_masked_binary_rsv1",
                "bytes": b'\x42\x8c\x01\x02\x03\x04\x49\x67\x6f\x68\x6e\x2e\x23\x56\x52\x54\x32\x25',
                "expected": {
                    "opcode": OPCODES.BINARY,
                    "fin": 0,
                    "rsv1": 1,
                    "rsv2": 0,
                    "rsv3": 0,
                    "payload": b'Hello, RSV1!',
                    "masked": True
                }
            },
            # Extended 16-bit length, unmasked, PING frame
            {
                "name": "extended_16_unmasked_ping",
                "bytes": b'\x89\x7e\x00\x7e' + (pl := b'a' * 126),
                "expected": {
                    "opcode": OPCODES.PING,
                    "fin": 1,
                    "rsv1": 0,
                    "rsv2": 0,
                    "rsv3": 0,
                    "payload": pl,
                    "masked": False
                }
            },
            # Extended 64-bit length, masked, PONG frame, all RSV bits set
            {
                "name": "extended_64_masked_pong_all_rsv",
                "bytes": b'\xfA\xfe\x01\x10' + b'\x01\x02\x00\x04' + (b'\x00\x55\xff\x04' * (272 // 4)),
                "expected": {
                    "opcode": OPCODES.PONG,
                    "fin": 1,
                    "rsv1": 1,
                    "rsv2": 1,
                    "rsv3": 1,
                    "payload": (b'\x01\x57\xff\x00' * (272 // 4)),
                    "masked": True
                }
            }
        ]

        for case in test_cases:
            with self.subTest(case=case["name"]):
                # Parse the byte string into a Frame object
                frame = Frame.from_streamdata(case["bytes"])

                # Validate the parsed frame attributes against expected values
                self.assertEqual(frame.opcode, case["expected"]["opcode"])
                self.assertEqual(frame.fin, case["expected"]["fin"])
                self.assertEqual(frame.rsv1, case["expected"]["rsv1"])
                self.assertEqual(frame.rsv2, case["expected"]["rsv2"])
                self.assertEqual(frame.rsv3, case["expected"]["rsv3"])
                self.assertEqual(frame.payload, case["expected"]["payload"])

                # Check if masking is correctly applied/absent
                if case["expected"]["masked"]:
                    self.assertIsNotNone(frame.mask)
                    self.assertEqual(len(frame.mask), 4)
                else:
                    self.assertIsNone(frame.mask)

                # Rebuild the frame and check if the result matches the original bytes
                rebuilt_frame = frame.to_streamdata()
                self.assertEqual(rebuilt_frame, case["bytes"])

    def test_extended_length(self):
        payload_126 = b'a' * 200
        frame_126 = Frame(payload=payload_126, opcode=OPCODES.BINARY, fin=1)
        stream_data_126 = frame_126.to_streamdata()
        parsed_frame_126 = Frame.from_streamdata(stream_data_126)

        self.assertEqual(parsed_frame_126.payload, payload_126)
        self.assertEqual(parsed_frame_126.amount_spec, 126)
        self.assertEqual(parsed_frame_126.amount, len(payload_126))

        payload_127 = b'b' * 70000
        frame_127 = Frame(payload=payload_127, opcode=OPCODES.BINARY, fin=1)
        stream_data_127 = frame_127.to_streamdata()
        parsed_frame_127 = Frame.from_streamdata(stream_data_127)

        self.assertEqual(parsed_frame_127.payload, payload_127)
        self.assertEqual(parsed_frame_127.amount_spec, 127)
        self.assertEqual(parsed_frame_127.amount, len(payload_127))

    def test_1MB_payload(self):
        mb_amount = 10 ** 6
        payload = b'm' * mb_amount
        mask_key = b'\x01\x02\x03\x04'

        frame = Frame(payload=payload, opcode=OPCODES.BINARY, fin=1, mask=mask_key)
        stream_data = frame.to_streamdata()
        parsed_frame = Frame.from_streamdata(stream_data)

        self.assertEqual(parsed_frame.payload, payload)
        self.assertEqual(parsed_frame.amount_spec, 127)
        self.assertEqual(parsed_frame.amount, mb_amount)


if __name__ == '__main__':
    flags = str().join(argv[1:]).upper()

    if not flags:
        unittest.main()

    if "H" in flags:
        print(
            str("\n").join((
                "Outsourced Tests:",
                "--flags----------",
                "   G   :(Gigabyte)         test 1GB payload",
                "   P   :(Perf. and Mem)    test 2048 byte payload (2048 * 2048) times",
                "   Q   :(Quick)            test set",
                "   E   :(Exceptions)       test exceptions raised by the c implementation",
                "   C   :(Communication)    test communication to a javascript WebSocket",
                "-----------------",
                "$ python test.py [flag(s)]\n"
            ))
        )
        exit()

    if "G" in flags:
        t = perf_counter_ns()
        print("[ Test 1GB payload ] start")

        gb_amount = 10 ** 9
        payload = b'g' * gb_amount
        mask_key = b'\x01\x02\x03\x04'

        masked_frame = Frame(payload=payload, opcode=OPCODES.BINARY, fin=1, mask=mask_key)
        masked_stream_data = masked_frame.to_streamdata()
        parsed_masked_frame = Frame.from_streamdata(masked_stream_data)

        assert parsed_masked_frame.payload == payload, "parsed_masked_frame.payload == payload"
        assert parsed_masked_frame.amount_spec == 127, "parsed_masked_frame.amount_spec == 127"
        assert parsed_masked_frame.amount == gb_amount, "parsed_masked_frame.amount == gb_amount"

        frame = Frame(payload=payload, opcode=OPCODES.BINARY, fin=1)
        stream_data = frame.to_streamdata()
        parsed_frame = Frame.from_streamdata(stream_data)

        assert parsed_frame.payload == payload, "parsed_frame.payload == payload"
        assert parsed_frame.amount_spec == 127, "parsed_frame.amount_spec == 127"
        assert parsed_frame.amount == gb_amount, "parsed_frame.amount == gb_amount"

        print(f"[ Test 1GB payload ] done in {((perf_counter_ns() - t) / 1e+9):.3f}s", )

    if "P" in flags:
        t = perf_counter_ns()
        print("[ Test 2048 byte payload (2048 * 2048) times ] start")

        payload = b'p' * 2048
        mask_key = b'\x01\x02\x03\x04'
        for i in range(2048 * 2048):
            Frame.from_streamdata(Frame(payload=payload, opcode=OPCODES.BINARY, fin=1, mask=mask_key).to_streamdata())

        print(f"[ Test 2048 byte payload (2048 * 2048) times ] done in {((perf_counter_ns() - t) / 1e+9):.3f}s", )

    if "Q" in flags:
        t = perf_counter_ns()
        print("[ Quick Test ] start")

        mb_amount = 10 ** 6
        payload = b'm\x00' * (mb_amount // 2)
        mask_key = b'\x01\x00\x03m'

        masked_frame = Frame(payload=payload, opcode=OPCODES.BINARY, fin=1, mask=mask_key)
        masked_stream_data = masked_frame.to_streamdata()
        parsed_masked_frame = Frame.from_streamdata(masked_stream_data)

        assert parsed_masked_frame.to_streamdata() == masked_stream_data, "parsed_masked_frame.to_streamdata() == masked_stream_data"
        assert parsed_masked_frame.payload == payload, "parsed_masked_frame.payload == payload"
        assert parsed_masked_frame.amount_spec == 127, "parsed_masked_frame.amount_spec == 127"
        assert parsed_masked_frame.amount == mb_amount, "parsed_masked_frame.amount == mb_amount"

        unmasked_frame = Frame(payload=payload, opcode=OPCODES.BINARY, fin=1)
        unmasked_stream_data = unmasked_frame.to_streamdata()
        parsed_unmasked_frame = Frame.from_streamdata(unmasked_stream_data)

        assert parsed_unmasked_frame.payload == payload, "parsed_unmasked_frame.payload == payload"
        assert parsed_unmasked_frame.amount_spec == 127, "parsed_unmasked_frame.amount_spec == 127"
        assert parsed_unmasked_frame.amount == mb_amount, "parsed_unmasked_frame.amount == mb_amount"

        masked_frame2 = Frame(payload=payload, opcode=OPCODES.BINARY, fin=1, mask=mask_key)
        masked_payload = masked_frame2.masked_payload()
        parsed_masked_frame2 = Frame.from_streamdata(masked_stream_data, auto_demask=False)

        assert masked_payload == parsed_masked_frame2.payload, "masked_payload == parsed_masked_frame2.payload"

        unmask_payload = Frame(payload=masked_payload, opcode=OPCODES.BINARY, fin=1, mask=mask_key).masked_payload()

        assert unmask_payload == payload, "unmask_payload == payload"

        print(f"[ Quick Test ] done in {((perf_counter_ns() - t) / 1e+9):.3f}s", )

    if "E" in flags:
        t = perf_counter_ns()
        print("[ Test Exceptions ] start")

        try:
            Frame(payload=b'12', mask=b'123').to_streamdata()
        except ValueError as e:
            print(e)
        else:
            assert False
        try:
            Frame(payload=b'12', mask=b'123').masked_payload()
        except ValueError as e:
            print(e)
        else:
            assert False
        try:
            Frame(payload=b'12', mask=b'12345').to_streamdata()
        except ValueError as e:
            print(e)
        else:
            assert False
        try:
            Frame(payload=b'12', mask=b'12345').masked_payload()
        except ValueError as e:
            print(e)
        else:
            assert False
        try:
            Frame.from_streamdata(b'1')
        except ValueError as e:
            print(e)
        else:
            assert False
        try:
            Frame.from_streamdata(b'\x00\x01')
        except ValueError as e:
            print(e)
        else:
            assert False

        print(f"[ Test Exceptions ] done in {((perf_counter_ns() - t) / 1e+9):.3f}s", )

    if "C" in flags:

        def s():
            print("[ Test Communication ] start")

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

                sock.bind(("localhost", 7890))
                print("# Socket bound to <localhost:7890>")

                sock.listen(1)
                con, addr = sock.accept()
                print("# New connection from <%s:%d>" % addr)

                request = con.recv(1024)
                header = HandshakeRequest.from_streamdata(request)
                print("# Header received:")
                for ln in pprint.pformat(header).splitlines():
                    print("<", ln)

                print("# Send response:")
                response = header.make_response()
                for ln in pprint.pformat(response).splitlines():
                    print(">", ln)
                con.send(response.to_streamdata())

                sr = StreamReader(payloads_masked=True)

                for _ in range(2):
                    val = 2
                    while isinstance(val, int):
                        val = sr.progressive_read(con.recv(val))

                    print("# Message received:")
                    print("<", val)

                print("# Send message:")
                msg = Frame(b"Hello World!", mask=b"")
                print(">", msg)
                con.send(msg.to_streamdata())

                print("# Send ping:")
                msg = Frame(b"", OPCODES.PING)
                print(">", msg)
                con.send(msg.to_streamdata())

                msg = con.recv(1024)
                print("# Pong received:")
                print("<", Frame.from_streamdata(msg))

                print("# Send first part of a fragmented message:")
                msg = Frame(b"Foo", mask=b"1234", fin=0)
                print(">", msg)
                con.send(msg.to_streamdata())
                print("# Send final part of a fragmented message:")
                msg = Frame(b"Bar", OPCODES.CONTINUE, mask=b"", fin=1)
                print(">", msg)
                con.send(msg.to_streamdata())

                print("# Send close:")
                msg = Frame(CLOSECODES.NORMAL_CLOSURE.to_payload(b"Goodbye!"), OPCODES.CLOSE)
                print(">", msg)
                con.send(msg.to_streamdata())

                input("\nPress Any Key")

                print("[ Test Communication ] done")


        threading.Thread(target=s).start()

        webbrowser.open(f"file://{Path(__file__).parent.__str__()}/test.html")
