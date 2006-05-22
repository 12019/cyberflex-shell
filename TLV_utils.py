import binascii, utils, sre

context_FCP = object()
context_FMD = object()
context_FCI = object()
recurse = object()
binary = object()
number = object()
ascii = object()

file_descriptor_byte_descriptions = [
    #byte  mask  no match match
    (0x80, 0x80, None,    "RFU"),
    (0xC0, 0x40, "non shareable", "shareable"),
    
    (0xB8, 0x00, None,    "working EF"),
    (0xB8, 0x08, None,    "internal EF"),
    (0xB8, 0x10, None,    "Reserved for proprietary uses"),
    (0xB8, 0x18, None,    "Reserved for proprietary uses"),
    (0xB8, 0x20, None,    "Reserved for proprietary uses"),
    (0xB8, 0x28, None,    "Reserved for proprietary uses"),
    (0xB8, 0x30, None,    "Reserved for proprietary uses"),
    (0xB8, 0x38, None,    "DF"),
    
    (0x87, 0x00, None,    "No file structure information given"),
    (0x87, 0x01, None,    "Transparent"),
    (0x87, 0x02, None,    "Linear fixed, no further info"),
    (0x87, 0x03, None,    "Linear fixed, SIMPLE-TLV"),
    (0x87, 0x04, None,    "Linear variable, no further info"),
    (0x87, 0x05, None,    "Linear variable, SIMPLE-TLV"),
    (0x87, 0x06, None,    "Cyclic, no further info"),
    (0x87, 0x07, None,    "Cyclic, SIMPLE-TLV"),
]

data_coding_byte_descriptions = [
    (0x60, 0x00, None,    "one-time write"),
    (0x60, 0x20, None,    "proprietary"),
    (0x60, 0x40, None,    "write OR"),
    (0x60, 0x60, None,    "write AND"),
]

def decode_file_descriptor_byte(value, verbose = True):
    result = " %s" % utils.hexdump(value, short=True)
    
    if not verbose:
        attributes = utils.parse_binary(ord(value[0]), file_descriptor_byte_descriptions, False)
        if len(value) > 1:
            attributes.append(
                "data coding byte, behavior of write functions: %s, data unit size in in nibbles: %i" % (
                    "".join( utils.parse_binary(ord(value[1]), data_coding_byte_descriptions) ),
                    2 ** (ord(value[1])&0x07)
                )
            )
        
        if len(value) > 2:
            i = 0
            for j in value[2:3]:
                i = i * 256 + ord(j)
            attributes.append(
                "maximum record length: %s" % i
            )
            if len(value) > 4:
                i = 0
                for j in value[4:5]:
                    i = i * 256 + ord(j)
                attributes.append(
                    "number of records: %s" % i
                )
        
        return result + " (%s)" % "; ".join(attributes)
    else:
        result = result + "\nFile descriptor byte:\n"
        result = result + "\t" + "\n\t".join(
            utils.parse_binary(ord(value[0]), file_descriptor_byte_descriptions, True)
        )
        if len(value) > 1:
            result = result + "\nData coding byte (0x%02X):\n" % ord(value[1])
            result = result + "\tBehavior of write functions: %s\n\tData unit size in in nibbles: %i" % (
                    "".join( utils.parse_binary(ord(value[1]), data_coding_byte_descriptions) ),
                    2 ** (ord(value[1])&0x07)
                )
        if len(value) > 2:
            i = 0
            for j in value[2:3]:
                i = i * 256 + ord(j)
            result = result + "\nMaximum record length: %s" % i
            if len(value) > 4:
                i = 0
                for j in value[4:5]:
                    i = i * 256 + ord(j)
                result = result + "\nNumber of recods: %s" % i
        return result

def parse_oid(value):
    result = []
    def next_arc(data):
        bits = ord(data[0]) & 0x7F
        while ord(data[0]) & 0x80 != 0:
            data = data[1:]
            bits = (bits << 7) + (ord(data[0]) & 0x7F)
        data = data[1:]
        return bits, data
    
    arc, value = next_arc(value)
    if arc < 40:
        result.append( 0 )
        result.append( arc )
    elif arc < 80:
        result.append( 1 )
        result.append( arc-40 )
    else:
        result.append( 2 )
        result.append( arc-80 )
    
    while len(value) > 0:
        arc,value = next_arc(value)
        result.append( arc )
    
    return tuple(result)
    
def decode_oid(value):
    oid = parse_oid(value)
    return " " + ".".join([str(a) for a in oid])

_gtimere = sre.compile(r'(\d{4})(\d\d)(\d\d)(\d\d)(?:(\d\d)(\d\d(?:[.,]\d+)?)?)?(|Z|(?:[+-]\d\d(?:\d\d)?))$')
def decode_generalized_time(value):
    matches = _gtimere.match(value)
    if not matches:
        return " "+value
    else:
        matches = matches.groups()
        result = [" %s-%s-%s %s:" % matches[:4]]
        if matches[4] is not None:
            result.append("%s:" % matches[4])
            if matches[5] is not None:
                result.append("%s" % matches[5])
            else:
                result.append("00")
        else:
            result.append(":00:00")
        
        if matches[6] == "Z":
            result.append(" UTC")
        elif matches[6] != "":
            result.append(" ")
            result.append(matches[6])
            if len(matches[6]) < 5:
                result.append("00")
        
        return "".join(result)

tags = {
    None: {
        0x01: (lambda a: ord(a[0]) == 0 and " False" or " True", "Boolean"),
        0x02: (number, "Integer"),
        0x03: (binary, "Bit string"),
        0x04: (binary, "Octet string"),
        0x05: (lambda a: " Null", "Null"),
        0x06: (decode_oid, "Object identifier"),
        0x12: (ascii, "Numeric string"),
        0x13: (ascii, "Printable string"),
        0x14: (ascii, "Teletex string"), ## FIXME: support escape sequences?
        0x15: (ascii, "Videotex string"), ## dito
        0x16: (ascii, "IA5String"),
        0x18: (decode_generalized_time, "Generalized time"),
        0x30: (recurse, "Sequence", None),
        0x31: (recurse, "Set", None),
        
        0x62: (recurse, "File Control Parameters", context_FCP),
        0x64: (recurse, "File Management Data", context_FMD),
        0x6F: (recurse, "File Control Information", context_FCI),
        0x80: (number, "Number of data bytes in the file, excluding structural information"),
        0x81: (number, "Number of data bytes in the file, including structural information"),
        0x82: (decode_file_descriptor_byte, "File descriptor byte"),
        0x83: (binary, "File identifier"),
        0x84: (binary, "DF name"),
        0x85: (binary, "Proprietary information"),
        0x86: (binary, "Security attributes"),
        0x87: (binary, "Identifier of an EF containing an extension of the FCI"),
        0x88: (binary, "Short EF identifier"),
        0x8A: (binary, "Life cycle status byte"),
        
        0xA5: (recurse, "Proprietary information", None),
    },
}

BER_CLASSES = {
    0x0: "universal",
    0x1: "application",
    0x2: "context-specific",
    0x3: "private",
}

def tlv_unpack(data):
    ber_class = (ord(data[0]) & 0xC0) >> 6
    constructed = (ord(data[0]) & 0x20) != 0 ## 0 = primitive, 0x20 = constructed
    tag = ord(data[0]) 
    data = data[1:]
    if (tag & 0x1F) == 0x1F:
        tag = (tag << 8) | ord(data[0])
        data = data[1:]
        while ord(data[0]) & 0x80 == 0x80:
            tag = tag << 8 + ord(data[0])
            data = data[1:]
    
    length = ord(data[0])
    if length < 0x80:
        data = data[1:]
    elif length == 0x81:
        length = ord(data[1])
        data = data [2:]
    elif length == 0x82:
        length = ord(data[1]) * 256 + ord(data[2])
        data = data[3:]
    else:
        raise ValueError, "Invalid TLV length field"
    
    value = data[:length]
    rest = data[length:]
    
    return ber_class, constructed, tag, length, value, rest

def decode(data, context = None, level = 0):
    result = []
    while len(data) > 0:
        if ord(data[0]) in (0x00, 0xFF):
            data = data[1:]
            continue
        
        ber_class, constructed, tag, length, value, data = tlv_unpack(data)
        
        interpretation = tags.get(context, tags.get(None, {})).get(tag, None)
        if interpretation is None:
            if not constructed: interpretation = [binary, "Unknown field"]
            else: interpretation = [recurse, "Unknown structure", context]
            
            interpretation[1] = "%s (%s class)" % (interpretation[1], BER_CLASSES[ber_class])
            interpretation = tuple(interpretation)
        
        current = ["\t"*level]
        current.append("Tag 0x%02X, Len 0x%02X, '%s':" % (tag, length, interpretation[1]))
        
        if interpretation[0] is recurse:
            current.append("\n")
            current.append( decode(value, interpretation[2], level+1) )
        elif interpretation[0] is number:
            num = 0
            for i in value:
                num = num * 256
                num = num + ord(i)
            current.append( " 0x%02x (%i)" % (num, num))
        elif interpretation[0] is ascii:
            current.append( " %s" % value)
        elif interpretation[0] is binary:
            if len(value) < 0x10:
                current.append( " %s" % utils.hexdump(value, short=True))
            else:
                current.append( "\n" + "\t"*(level+1) )
                current.append( ("\n" + "\t"*(level+1)).join( utils.hexdump(value).splitlines() ) )
        elif callable(interpretation[0]):
            current.append( ("\n"+"\t"*(level+1)).join(interpretation[0](value).splitlines()) )
        
        result.append( "".join(current) )
    
    return "\n".join(result)

if __name__ == "__main__":
    test = binascii.unhexlify("".join(("6f 2b 83 02 2f 00 81 02 01 00 82 03 05 41 26 85" \
        +"02 01 00 86 18 60 00 00 00 ff ff b2 00 00 00 ff" \
        +"ff dc 00 00 00 ff ff e4 10 00 00 ff ff").split()))
    
    decoded = decode(test)
    #print decoded
    print decode(file("c100").read())