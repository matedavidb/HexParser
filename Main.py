import os
import string
import enum
import copy
import argparse

class VarDefinition:
    def __init__(self):
        self.name = str()
        self.core_type = None
        self.value = None
        self.attributes = list()
        self.array_size = ""
        self.fields = dict()
        self.parent = None

class DefinitionKind(enum.Enum):
    atomic_type = 1
    type_definition = 2
    structure = 3

class HexParser:
    def __init__(self, input_filepath, template_filepath, output_filepath):
        self.m_input_filepath = input_filepath
        self.m_template_filepath = template_filepath
        self.m_output_filepath = output_filepath
        self.m_name_to_type = dict()
        self.m_global = VarDefinition()
        self.m_global.name = ""
        self.m_definitions = dict()
        self.m_anonimus_sequence_number = 0

    def GetDefinitionKind(self, core_type:str):
        if core_type in ["hex", "char", "int"]:
            return DefinitionKind.atomic_type
        elif core_type == '{':
            return DefinitionKind.type_definition
        else:
            return DefinitionKind.structure

    def ReadByteList(self):
        self.m_bytes_list = list()
        with open(self.m_input_filepath, 'rb') as f:
            while True:
                chunk = f.read(1)
                if not chunk:
                    break
                self.m_bytes_list.append(chunk)

    def MakePrintable(self, b):
        try:
            c = b.decode()
            if c not in string.printable:
                c = '.'
        except Exception:
            c = '.'
        return c

    def PrintBytes(self, print_format:str, count = None):
        i = 0
        s = ""
        for byte in self.m_bytes_list:
            if count and i == count:
                break
            if "hex" == print_format:
                s += byte.hex() + " "
            if "char" == print_format:
                s += self.MakePrintable(byte)
            self.m_bytes_list.pop(0)
            i += 1
        self.PrintOut(s)

    def ParseTypeInfo(self, type_info:str) -> (str,list,int) :
        core_type = ""
        type_attributes = ""
        array_size = ""
        state = "core_type"
        for c in type_info :
            if '<' == c:
                state = "type_attributes"
                continue
            if '>' == c:
                continue
            if '[' == c:
                state = "array_size"
                continue
            if ']' == c:
                continue
            if "core_type" == state:
                core_type += c
            elif "type_attributes" == state:
                type_attributes += c
            elif "array_size" == state:
                array_size += c
        if len(array_size) == 0:
            array_size = "1"
        type_attributes = type_attributes.split(',')
        return core_type, type_attributes, array_size
    
    def GetValue(self, parent:VarDefinition, field_name:str):
        if field_name.isdigit():
            return int(field_name)
        p = parent
        while p:
            for k in p.fields.keys():
                if k == field_name:
                    return int(p.fields[k].value)
            p = p.parent

    def GetType(self, var:VarDefinition):
        return self.m_definitions[var.core_type]
        # raise Exception(F"Type not found! {var.core_type}")
    
    def Indent(self, size:int):
        s = ""
        for i in range(0, size):
            s += "\t"
        return s

    def PrintOut(self, text:str):
        with open(self.m_output_filepath, 'a') as out:
            out.write(text)

    def PrintVar(self, var:VarDefinition, indent:int):
        if not var:
            return
        var_indent = indent
        if len(var.name) > 0:
            if var.name != "_" and var.core_type != "comment":
                var_indent = indent + 1
                self.PrintOut(self.Indent(indent) + var.name + ":\n")
        for v in var.fields.values():
            self.PrintVar(v, var_indent)
        if not var.core_type or var.core_type == "":
            return
        t = var.core_type
        if "int" == t:
            byte_order = ""
            int_size = 0
            signed = False
            for a in var.attributes:
                if 'L' == a:
                    byte_order = "little"
                elif 'B' == a:
                    byte_order = "big"
                elif 's' == a:
                    signed = True
                elif 'u' == a:
                    signed = False
                else:
                    int_size = a
            int_size = int(int_size)
            array_size = self.GetValue(var, var.array_size)
            self.PrintOut(self.Indent(var_indent))
            for j in range(0, array_size):
                b = bytes(0)
                for i in range(0, int_size):
                    if len(self.m_bytes_list) == 0:
                        return
                    b += self.m_bytes_list.pop(0)
                i = int.from_bytes(b, byte_order)
                if array_size == 1:
                    var.value = i
                self.PrintOut(str(i) + " ")
        elif "char" == t:
            s = ""
            for i in range(self.GetValue(var, var.array_size)):
                s += self.MakePrintable(self.m_bytes_list.pop(0))
            self.PrintOut(self.Indent(var_indent) + s)
        elif "hex" == t:
            self.PrintOut(self.Indent(var_indent))
            for i in range(self.GetValue(var, var.array_size)):
                b = self.m_bytes_list.pop(0)
                self.PrintOut(b.hex() + " ")
        elif "comment" == t:
            self.PrintOut(var.value)

        self.PrintOut("\n")

    def ParseDefinition(self, template_file, name:str):
        type_def = VarDefinition()
        type_def.name = name
        type_def.parent = None
        while True:
            sub_line = template_file.readline()
            sub_line = sub_line.strip()
            if '}' == sub_line:
                break
            sub_var_name, sub_type_info = sub_line.split(':')
            co, at, ar = self.ParseTypeInfo(sub_type_info)
            def_kind = self.GetDefinitionKind(co)
            sub_var = VarDefinition()
            sub_var.parent = type_def
            sub_var.core_type = co
            if DefinitionKind.structure == def_kind:
                t = self.GetType(sub_var)
                sub_var = copy.deepcopy(t)
            sub_var.name = sub_var_name
            sub_var.parent = type_def
            sub_var.attributes = at
            sub_var.array_size = ar
            type_def.fields[sub_var.name] = sub_var
        self.m_definitions[type_def.name] = type_def
    
    def Start(self):
        with open(self.m_template_filepath, "r") as template_file:
            while True:
                line = template_file.readline()
                if not line:
                    break
                line = line.strip()
                if len(line) == 0 :
                    continue
                if line.startswith("##"):
                    var = VarDefinition()
                    var.core_type = "comment"
                    self.m_anonimus_sequence_number += 1
                    var.name = "comment" + str(self.m_anonimus_sequence_number)
                    var.value = line
                    self.m_global.fields[var.name] = var
                if line.startswith("#"):
                    continue
                line = line.strip()

                name, type_info = line.split(":")
                type_info = type_info.strip()
                name = name.strip()
                parent = self.m_global
                ct, at, ar = self.ParseTypeInfo(type_info)
                dk = self.GetDefinitionKind(ct)
                if DefinitionKind.type_definition == dk:
                    self.ParseDefinition(template_file, name)
                    continue
                else:
                    var = VarDefinition()
                    var.core_type = ct
                    var.attributes = at
                    var.array_size = ar
                    var.name = name
                    var.parent = parent
                    if DefinitionKind.atomic_type == dk:
                        pass
                    elif DefinitionKind.structure == dk:
                        t = self.GetType(var)
                        array_size = self.GetValue(var, ar)
                        if array_size == 1:
                            var = copy.deepcopy(t)
                            var.name = name
                            var.parent = parent
                            self.m_global.fields[var.name] = var
                        else:
                            for i in range(0, array_size):
                                var = copy.deepcopy(t)
                                var.name = name + '[' + str(i) + ']'
                                var.parent = parent
                                self.m_global.fields[var.name] = var
            with open(self.m_output_filepath, 'w') as out:
                out.write("")
            self.PrintVar(self.m_global, 0)
            if len(self.m_bytes_list) > 0:
                with open(self.m_output_filepath, 'a') as out:
                    out.write(F"Remaining {len(self.m_bytes_list)} bytes:\n")
                self.PrintBytes("hex")

def GetHex(filepath:str):
    result = ""
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(1)
            if not chunk:
                break
            result += chunk.hex() + " "
    return result

def ParseBytes():
    print("start")
    # root_folder = "/home/user/Platform/SGHW-Platform-1/build_VerTest"
    root_folder = "/home/user/Platform/SGHW-Platform-1/build_UK-WaveX_Devd"
    # filename = "XI70-0184-1736947874"
    filename = "ApplicationFile.bin"
    input_path = os.path.join(root_folder,"Input", filename)
    # input_path = os.path.join(root_folder,"LegacyOutput2", filename)
    # input_path = os.path.join(root_folder,"NewOutput2", filename)
    hex_parser = HexParser(input_path, "template.txt", "output.txt")
    hex_parser.ReadByteList()
    hex_parser.Start()
    print("end")

def Parse(input_filepath, template_filepath, output_filepath):
    print("start")
    hex_parser = HexParser(input_filepath, template_filepath, output_filepath)
    hex_parser.ReadByteList()
    hex_parser.Start()
    print("end")

def Compare():
    filename = "XI70-0184-1736947874"
    root_folder = "/home/user/Platform/SGHW-Platform-1/build_VerTest/"
    
    legacy_folder = os.path.join(root_folder, "LegacyOutput2")
    legacy_output_path = os.path.join(legacy_folder, filename)
    legacy_hex_path = os.path.join(legacy_folder, "hex.txt")
    legacy = GetHex(legacy_output_path)
    with open(legacy_hex_path, "w") as lo:
        lo.write(legacy)

    new_folder = os.path.join(root_folder, "NewOutput2")
    new_output_path = os.path.join(new_folder, filename)
    new_hex_path = os.path.join(new_folder, "hex.txt")
    new = GetHex(new_output_path)
    with open(new_hex_path, "w") as no:
        no.write(new)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_filepath",type=str)
    parser.add_argument("--template_filepath",type=str)
    parser.add_argument("--output_filepath",type=str)
    args = parser.parse_args()
    Parse(args.input_filepath, args.template_filepath, args.output_filepath)
