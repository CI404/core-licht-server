#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lichter_wire.py -- 《核芯：利希特》/ Crystalfall (com.tw99.no23.an v0.1.38)
TCP game-protocol codec for the mock/offline server.

Everything here is derived from static evidence:
  * libil2cpp.so (arm64) disassembly of:
      Onecore.OnecoreEngine.Base.SNPacketData.GenC2SPacket   @ 0x1585D1C
      Onecore.OnecoreEngine.Base.SNPacketData.ProcessS2CPacket @ 0x1585EE4
      Onecore.OnecoreEngine.Base.SNBuffer.{BeginPacket,EndPacket,
                     WritePacketUInt16,ReadPacketUInt16,PeekPacketSize}
      Onecore.OnecoreEngine.Game.SNTCPClient.{Send,Receive,OnConnectedCB}
  * global-metadata.dat -> XorCode._passArr (256-byte default value blob of
      <PrivateImplementationDetails>.AFDB694BFA892BC872A116B516A86C3A8C1C83EE)

Wire format
-----------
CLIENT -> SERVER (SNPacketData.GenC2SPacket)
    off  size  field
    0    2     length  u16 big-endian == total_frame_len - 2
    2    2     uniq    u16 big-endian, per-connection counter, starts at 100 (ctor sets uniq_=99, GenUnique pre-increments)
    4    1     sId     section id (msgKey "s_m" -> s)
    5    1     mId     method  id (msgKey "s_m" -> m)
    6    n     body    protobuf XOR passArr[(uniq + i) & 0xFF]
    len == 4 + n

SERVER -> CLIENT (mirror of SNPacketData.ProcessS2CPacket)
    off  size  field
    0    2     length  u16 big-endian == total_frame_len - 2
    2    1     sId
    3    1     mId
    4    1     zflag   0 = body is raw, non-zero = body is zlib-deflate
    5    n     body    XOR passArr[(sId*16 + mId + i) & 0xFF]
    then if zflag: zlib.decompress(result)
    len == 3 + n

    NOTE the two directions use *different* XOR seeds:
      C2S seed = (uniq & 0xFF)          <- per-packet counter
      S2C seed = (sId*16 + mId) & 0xFF  <- constant per message type

CONNECT BANNER
    The client immediately sends the raw 2 bytes 01 02
    (SNTCPClient.OnConnectedCB allocates byte[2]={1,2} and writes it with no
    length header and no XOR).  It is fire-and-forget: the client does not wait
    for an answer, so a mock server can ignore it.
"""

import binascii
import zlib

# --------------------------------------------------------------------------
# XorCode._passArr  (256 bytes, extracted from global-metadata.dat)
# --------------------------------------------------------------------------
PASSARR = bytes.fromhex(
    "99eaab7a992536b2298f37756c02907a674f0f94fd552f3409e3d6d45441cf05"
    "070d0efc909c64abe0e4cb954cb867cb136599ada513459a01f0d1a46a76069"
    "def3ff6efdd4451c2953519232b3debc55646740696f4ed51fc55996b041e935"
    "607dc98a99eb7d6c1f0f2330ecc89518b669e9ecb8d11615add51e2559239c6"
    "e9cc24548347e034e91daed5a3d319debd2d14861924e456a3aa948c132f960"
    "cb0149061730c7cd03be166e84051be1162fe0e6ce769c70c3894f27b181a52"
    "c1c79a57d35c3f935ae0a4f3d8891376071f6af42971a01175f77e1ac8562d"
    "73c73a85ebb8d9f5f709c6c82247aeaf7d4d8123ea078f708e8a796495cb8e"
    "8974f3e1"
)
assert len(PASSARR) == 256, len(PASSARR)

CONNECT_BANNER = bytes((0x01, 0x02))


def _xor(buf, seed):
    return bytes(buf[i] ^ PASSARR[(seed + i) & 0xFF] for i in range(len(buf)))


# --------------------------------------------------------------------------
# framing
# --------------------------------------------------------------------------
def decode_c2s(frame):
    """Decode one complete client->server frame.

    Returns dict(sId, mId, uniq, body) where body is the XOR-decoded protobuf
    payload.  Raises ValueError if the frame is not self-consistent.
    """
    if len(frame) < 6:
        raise ValueError("frame too short: %d" % len(frame))
    ln = int.from_bytes(frame[0:2], "big")
    if ln != len(frame) - 2:
        raise ValueError("length field %d != %d" % (ln, len(frame) - 2))
    uniq = int.from_bytes(frame[2:4], "big")
    sId, mId = frame[4], frame[5]
    return {"sId": sId, "mId": mId, "uniq": uniq,
            "body": _xor(frame[6:], uniq & 0xFF)}


def encode_s2c(sId, mId, body, compress=False):
    """Encode one server->client frame.

    sId/mId  : message key numbers ("1_1" -> 1, 1)
    body     : raw protobuf bytes (not yet XORed / compressed)
    compress : set the zlib flag (optional - the client handles both)
    """
    if compress:
        body = zlib.compress(body)
        zflag = 1
    else:
        zflag = 0
    payload = bytes((sId, mId, zflag)) + _xor(body, (sId * 16 + mId) & 0xFF)
    return len(payload).to_bytes(2, "big") + payload


def decode_s2c(frame, raw_body=None):
    """Reference decoder (what the client itself does) - handy for unit tests."""
    ln = int.from_bytes(frame[0:2], "big")
    assert ln == len(frame) - 2
    sId, mId, zflag = frame[2], frame[3], frame[4]
    if raw_body is None:
        pt = _xor(frame[5:], (sId * 16 + mId) & 0xFF)
    else:
        pt = raw_body
    if zflag:
        pt = zlib.decompress(pt)
    return sId, mId, zflag, pt


class FrameReader:
    """Incremental TCP stream -> frames.  Ignores the 01 02 connect banner."""

    def __init__(self):
        self.buf = bytearray()
        self.saw_banner = False

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            if not self.saw_banner:
                # the banner is exactly the 2 bytes 01 02 sent before any
                # length-prefixed frame; detect it and drop it.
                if len(self.buf) >= 2 and self.buf[0] == 0x01 and self.buf[1] == 0x02:
                    del self.buf[:2]
                self.saw_banner = True
                continue
            if len(self.buf) < 2:
                break
            ln = int.from_bytes(self.buf[0:2], "big")
            if len(self.buf) < ln + 2:
                break
            out.append(bytes(self.buf[:ln + 2]))
            del self.buf[:ln + 2]
        return out


# --------------------------------------------------------------------------
# protobuf helpers (descriptors extracted from the APK)
# --------------------------------------------------------------------------
# 可移植化：proto 目錄優先由專案根的 config.py 決定（config/server.json 的 "proto"）。
# 獨立使用本模組時（沒有 config.py）則退回同專案的 data/proto。
def _default_proto_dir():
    import os as _os
    import sys as _sys
    _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    try:
        if _root not in _sys.path:
            _sys.path.insert(0, _root)
        import config as _cfg
        return _cfg.PROTO
    except Exception:
        return _os.path.join(_root, "data", "proto")


PROTO_DIR = _default_proto_dir()


def load_pool(proto_dir=None):
    """Build a DescriptorPool from <proto_dir>/*.bin (預設 = config 的 proto 目錄)。"""
    import os
    import glob
    from google.protobuf import descriptor_pb2, descriptor_pool

    proto_dir = proto_dir or PROTO_DIR

    def unwrap(raw):
        if raw and raw[0] == 0x0A:            # field 1, length-delimited
            i, shift, ln = 1, 0, 0
            while True:
                b = raw[i]; i += 1
                ln |= (b & 0x7F) << shift; shift += 7
                if not (b & 0x80):
                    break
            if i + ln == len(raw):
                return raw[i:i + ln]
        return raw

    pool = descriptor_pool.DescriptorPool()
    pending = []
    for p in sorted(glob.glob(os.path.join(proto_dir, "*.bin"))):
        fdp = descriptor_pb2.FileDescriptorProto()
        fdp.ParseFromString(unwrap(open(p, "rb").read()))
        pending.append(fdp)
    done, progress = set(), True
    while progress:
        progress = False
        for fdp in pending:
            if fdp.name in done:
                continue
            if all(d in done for d in fdp.dependency):
                try:
                    pool.Add(fdp)
                except Exception:
                    pass                      # unrelated files with bad refs
                done.add(fdp.name)
                progress = True
    return pool


def build_login_auth_s2c(code=0, time_zone=8, serv_id=1, open_time=1700000000,
                         roles=(), pool=None):
    """Return the serialized ZeroProto.login_auth_s2c body.

    roles: iterable of dicts with keys id,name,sex,level,last_login_time
    """
    from google.protobuf import message_factory
    pool = pool or load_pool()
    cls = message_factory.GetMessageClass(
        pool.FindMessageTypeByName("ZeroProto.login_auth_s2c"))
    msg = cls()
    msg.code = code
    msg.time_zone = time_zone
    msg.serv_id = serv_id
    msg.open_time = open_time
    for r in roles:
        e = msg.role_list.add()
        e.id = r.get("id", 0)
        e.name = r.get("name", "")
        e.sex = r.get("sex", 0)
        e.level = r.get("level", 1)
        e.last_login_time = r.get("last_login_time", 0)
    return msg.SerializeToString()


# --------------------------------------------------------------------------
# self-test against the captured frames
# --------------------------------------------------------------------------
if __name__ == "__main__":
    FRAME_A = bytes.fromhex("0102")
    FRAME_B = bytes.fromhex(
        "00de00640101dc1ed743f1f30374cbe83fef14f1f7afcf110b5ced7fd37ba1018ced9b6d12ca4df000da2896e4c5e078ebd91e70e22c14867cb3f9f5e1605af86b9047dd4c20354ee80bdb6ed972698e3b55cc3e3ee050fe340faccb427a1b629bc78851e16f08ab62d486f697fd7b13756d7a97461c8e6502ce4734a6391f40e95bebd9b09194996daead4e23b48c3c23e551856eeb50c1d95955a0eba1a935a3a8b4d99e5ab17302831ec6655a5b34a053754b7bf18e21173429666e708247c50173687d888a9d5483e1d6d8f823db0cbf7c0efcc3942176ae34c6e69c5346")
    FRAME_C = bytes.fromhex("000a00650100afe3d1b2fa32")

    print("banner:", FRAME_A.hex(), "(raw, unframed, ignored)")
    pool = load_pool()
    from google.protobuf import message_factory

    NAMES = {(1, 0): "login_heart_c2s", (1, 1): "login_auth_c2s",
             (1, 2): "login_create_role_c2s"}
    for tag, fr in (("B", FRAME_B), ("C", FRAME_C)):
        d = decode_c2s(fr)
        name = NAMES[(d["sId"], d["mId"])]
        cls = message_factory.GetMessageClass(
            pool.FindMessageTypeByName("ZeroProto." + name))
        m = cls(); m.ParseFromString(d["body"])
        print("\nFrame %s: %s  uniq=%d  seed=%d  body=%d bytes"
              % (tag, name, d["uniq"], d["uniq"] & 0xFF, len(d["body"])))
        print("   protobuf:", d["body"].hex())
        for f, v in m.ListFields():
            print("     %-14s = %r" % (f.name, v))

    body = build_login_auth_s2c(
        code=0, time_zone=8, serv_id=1, open_time=1700000000,
        roles=[dict(id=10001, name="Tester", sex=1, level=42,
                    last_login_time=1700000001)], pool=pool)
    wire = encode_s2c(1, 1, body)
    print("\nlogin_auth_s2c body :", body.hex())
    print("login_auth_s2c wire :", wire.hex())
    print("client-side decode  :", decode_s2c(wire)[:3])
    print("round-trip ok       :", decode_s2c(wire)[3] == body)
