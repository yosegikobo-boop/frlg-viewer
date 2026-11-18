"""日本版 第3世代のゲームの文字 ⇔ str"""

_HIRA = ("あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
         "ぁぃぅぇぉゃゅょがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽっ")
_KATA = ("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
         "ァィゥェォャュョガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポッ")
_REST = "０１２３４５６７８９！？。ー・‥『』「」♂♀円．×／"
_UPPER = "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
_LOWER = "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"

CHARS = {0x00: "　"}
for _i, _c in enumerate(_HIRA):
    CHARS[0x01 + _i] = _c
for _i, _c in enumerate(_KATA):
    CHARS[0x51 + _i] = _c
for _i, _c in enumerate(_REST):
    CHARS[0xA1 + _i] = _c
for _i, _c in enumerate(_UPPER):
    CHARS[0xBB + _i] = _c
for _i, _c in enumerate(_LOWER):
    CHARS[0xD5 + _i] = _c
CHARS[0xEF] = "▶"
CHARS[0xF0] = "："

_REVERSE = {v: k for k, v in CHARS.items()}
_HALF = {chr(0x30 + i): chr(0xFF10 + i) for i in range(10)}


def decode_text(data: bytes) -> str:
    out = []
    for b in data:
        if b == 0xFF:
            break
        out.append(CHARS.get(b, "？"))
    return "".join(out)


def encode_text(s: str) -> bytes:
    """終わりの 0xFF は付けない"""
    return bytes(_REVERSE[_HALF.get(c, c)] for c in s)
