import sys
import struct
import re
import textwrap

DEBUG = True
DEBUG_CONTENT = True
global_indents = 0

TAB = "\t"


def main():
    FMT = [
        "Test",
        ">>INDENT<<",
        Item("test_uint32_t_string",    Uint32_t),
        Item("test_int32_t_string ",     Int32_t),
        Item("test_uint16_t_string",    Uint16_t),
        Item("test_int16_t_string ",     Int16_t),
        Item("test_uint8_t_string ",     Uint8_t),
        Item("test_int8_t_string  ",      Int8_t),
        ">>UNINDENT<<",
    ]


    global global_indents, TAB
    if len(sys.argv) == 1:
        filename = "stream.txt"
    else:
        filename = sys.argv[1]

    with open(filename) as f:
        content = f.read().strip()
        content = re.sub("#.*(\n|$)", "", content)
        content = re.sub("[\n\s]", "", content)
        if DEBUG_CONTENT:print(content)
        print(len(content.strip())/2, "bytes")

    def process_items(items, content):
        global global_indents
        idx = 0
        for item in items:
            if isinstance(item, str):
                if item == ">>INDENT<<":
                    global_indents += 1
                elif item == ">>UNINDENT<<":
                    global_indents -= 1
                elif item == ">>RESETINDENT<<":
                    global_indents = 0
                else:
                    print(f"{TAB*global_indents}[{item}]")
                continue
            elif isinstance(item, list):
                process_items(item, content)
                continue
            
            process_byte(item, content, idx)
            idx += item.size_byte*2

    def process_byte(item, content, idxStart):
        dataStr = content[idxStart:]
        dataByte = bytearray.fromhex(dataStr)

        itemStr = item.get_str(dataByte)
        print(f"{TAB*global_indents} {itemStr}")

    process_items(FMT, content)

class StrFmtWithEndian(str):
    pass
class StrFmtWithOutEndian(str):
    pass

class Type:
    def __init__(self, name:str, fmt:str, size_byte:int, endian:StrFmtWithOutEndian=">"):
        self.name:str = name
        self.fmt:StrFmtWithOutEndian = fmt
        self.size_byte:int = size_byte
        self.endian:StrFmtWithOutEndian = endian
        self.item_obj:Item = None

    def unpack(self, data:bytearray):
        num = struct.unpack(self.endian + self.fmt, data[:self.size_byte])
        return num[0] if len(num)==1 else num
    
    def get_str(self, data:bytearray, item_obj=None):
        byteStr = data[:self.size_byte].hex()
        byteStr = byteStr if len(byteStr)<=16 else byteStr[:16] + "..."
        dataStrPrint = byteStr.ljust(16+4)
        num = self.unpack(data)
        name = item_obj.name if item_obj is not None else self.name
        return f"{dataStrPrint} {name} = {num}"
    
    def print(self, indents=0):
        print("\t"*indents + self.get_str())

class Primitive(Type):
    pass

Int8_t       = Primitive("int8_t",    "b", 1, endian=">")
Uint8_t      = Primitive("uint8_t",   "B", 1, endian=">")
Int16_t      = Primitive("int16_t",   "h", 2, endian=">")
Uint16_t     = Primitive("uint16_t",  "H", 2, endian=">")
Int32_t      = Primitive("int32_t",   "i", 4, endian=">")
Uint32_t     = Primitive("uint32_t",  "I", 4, endian=">")
Int64_t      = Primitive("int64_t",   "q", 8, endian=">")
Uint64_t     = Primitive("uint64_t",  "Q", 8, endian=">")
Float        = Primitive("float",         "f", 4, endian=">")
Double       = Primitive("double",       "d", 8, endian=">")

class Vector(Type):
    def __init__(self, name:str, item_type_obj:Type, endian:str=">", item_num=-1, length_field_size_byte=4):
        self.name:str = name
        self.fmt:StrFmtWithOutEndian = None
        self.size_byte:int = None
        self.endian = endian
        self.__item_obj:Item = None

        self.item_type_obj = item_type_obj
        self.number_of_items = None

        if length_field_size_byte<=0 and not item_num<0:
            raise Exception("Error: Please provide length_field_size_byte or item_num!")
        
        self.length_field_size_byte = length_field_size_byte

        if item_num >= 0 and self.item_type_obj.size_byte is not None:
            self.size_byte = self.length_field_size_byte + self.item_type_obj.size_byte * item_num
        
    @property
    def item_obj(self):
        return self.__item_obj
    
    @item_obj.setter
    def item_obj(self, obj):
        self.__item_obj = obj
        self.item_type_obj.item_obj = obj

    def unpack(self, data:bytearray):
        global global_indents
        TAB = "\t"
        self.fmt = ""
        if self.length_field_size_byte >= 1:
            lengthData = data[:self.length_field_size_byte]
            length_num = Uint32_t.unpack(lengthData)
            self.item_num = length_num
            self.fmt += Uint32_t.fmt
        else:
            length_num = self.item_num
        if DEBUG: print(TAB*global_indents + f"\033[7;33munpacked Vector size: {length_num} ({self.name})", "\033[0m")
        global_indents += 1
        item_nums = []
        idxStart = self.length_field_size_byte
        for i in range(length_num):
            if DEBUG: print(TAB*global_indents + "\033[7;33munpacking Vector", self.name, "Number", i+1, "of", length_num, self.item_type_obj.name, "\033[0m")    
            itemData = data[idxStart:]
            item_num = self.item_type_obj.unpack(itemData)
            item_nums.append(item_num)
            self.fmt += self.item_type_obj.fmt
            idxStart += self.item_type_obj.size_byte
        global_indents -= 1

        self.size_byte = self.length_field_size_byte + self.item_type_obj.size_byte * self.item_num

        return (length_num, item_nums)
    

def Struct(Type):
    def __init__(self, name:str, fields=[], endian:str=">"):
        self.name:str = name
        self.fmt:StrFmtWithOutEndian = None
        self.size_byte:int = None
        self.endian = None
        self.item_obj:Item = None

        self.fields = fields

    def unpack(self, data:bytearray):
        global global_indents
        TAB = "\t"
        self.fmt = ""
        self.size_byte = 0
        field_nums = []
        if DEBUG: print(TAB*global_indents + "\033[7;31munpacking Struct", self.item_obj.name, "of", self.name, "\033[0m")
        idxStart = 0
        global_indents += 1
        for field in self.fields:
            if DEBUG and not isinstance(field.type_obj, Struct) and not isinstance(field.type_obj, Vector):
                print(TAB*global_indents + "\033[1;31munpacking Struct", self.name, "Field", field.name, "\033[0m")
            fieldData = data[idxStart:]
            field_num = field.unpack(fieldData)
            field_nums.append(field_num)
            self.fmt += field.fmt
            idxStart += field.size_byte
        global_indents -= 1
        
        return field_nums
    
class Item:
    def __init__(self, name, type_obj=None, fmt=None):
        self.name = name
        self.type_obj:Type = type_obj
        self.type_obj.item_obj = self
        self.fmt = fmt

        self.unpack = self.type_obj.unpack

    @property
    def size_byte(self):
        return self.type_obj.size_byte
    
    def get_str(self, data:bytearray):
        return self.type_obj.get_str(data, self)
        
if __name__ == "__main__":
    main()
        
    