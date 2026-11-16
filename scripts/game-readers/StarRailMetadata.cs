// SPDX-License-Identifier: GPL-3.0-or-later
// Metadata-only bridge to the separately acquired, pinned GPL reader. Native
// client files are data: this program never loads or invokes a client library.
using System.Text.Json;
using System.Text.RegularExpressions;
using HSRGlobalMetadata;
using HSRGlobalMetadata.Output;
using HSRGlobalMetadata.Structs;
using HSRGlobalMetadata.Utils;
using Iced.Intel;

internal static class StarRailMetadata {
    static string Existing(string value, bool directory = false) {
        if (!Path.IsPathFullyQualified(value)) throw new InvalidDataException();
        string path = Path.GetFullPath(value);
        for (string? parent = path; parent != null; parent = Path.GetDirectoryName(parent)) {
            if ((File.Exists(parent) || Directory.Exists(parent)) &&
                (File.GetAttributes(parent) & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException();
        }
        if (directory ? !Directory.Exists(path) : !File.Exists(path)) throw new InvalidDataException();
        return path;
    }
    static string NewOutput(string value) {
        if (!Path.IsPathFullyQualified(value)) throw new InvalidDataException();
        string path = Path.GetFullPath(value);
        Existing(Path.GetDirectoryName(path)!, true);
        if (File.Exists(path) || Directory.Exists(path)) throw new InvalidDataException();
        return path;
    }
    static void Metadata(string input, string output) {
        Existing(input, true);
        output = NewOutput(output);
        string native = Existing(Path.Combine(input, "GameAssembly.dll"));
        string metadata = Existing(Path.Combine(input, "StarRail_Data", "il2cpp_data", "Metadata", "global-metadata.dat"));
        string startup = Existing(Path.Combine(input, "StarRail_Data", "il2cpp_data", "Metadata", "startup-metadata.dat"));
        if (new FileInfo(native).Length > 1024L * 1024 * 1024 ||
            new FileInfo(metadata).Length > 512L * 1024 * 1024 ||
            new FileInfo(startup).Length > 64L * 1024 * 1024) throw new InvalidDataException();
        PEHelper.ReadPEHeader(native);
        MetadataContext.Initialize(metadata, startup, native);
        MetadataHeader.Initialize(native);
        MetadataRegistration.Initialize(native);
        CodeRegistration.Initialize(native);
        MetadataTables.Initialize(native);
        MetadataCache.Initialize();
        Directory.CreateDirectory(output);
        DumpWriter.WriteToDirectory(output);
        StringLiteralWriter.WriteToDirectory(output);
    }
    static void Keys(JsonElement item, params string[] names) {
        if (item.ValueKind != JsonValueKind.Object) throw new InvalidDataException();
        var actual = item.EnumerateObject().Select(p => p.Name).ToArray();
        if (actual.Length != names.Length || actual.Distinct().Count() != names.Length ||
            !actual.ToHashSet().SetEquals(names)) throw new InvalidDataException();
    }
    static void Disassemble(string input, string request, string output) {
        input = Existing(input); request = Existing(request); output = NewOutput(output);
        if (new FileInfo(request).Length > 1024 * 1024) throw new InvalidDataException();
        using var document = JsonDocument.Parse(File.ReadAllText(request));
        Keys(document.RootElement, "ranges");
        var ranges = document.RootElement.GetProperty("ranges");
        if (ranges.ValueKind != JsonValueKind.Array || ranges.GetArrayLength() is < 1 or > 4096) throw new InvalidDataException();
        using var source = File.OpenRead(input);
        if (source.Length > 1024L * 1024 * 1024) throw new InvalidDataException();
        var result = new List<List<object[]>>();
        long total = 0; int instructionTotal = 0;
        var formatter = new IntelFormatter();
        formatter.Options.HexPrefix = "0x"; formatter.Options.HexSuffix = "";
        formatter.Options.UppercaseHex = false;
        formatter.Options.SmallHexNumbersInDecimal = false;
        formatter.Options.AddLeadingZeroToHexNumbers = false;
        formatter.Options.LeadingZeros = false;
        formatter.Options.BranchLeadingZeros = false;
        formatter.Options.RipRelativeAddresses = true;
        formatter.Options.SpaceAfterOperandSeparator = true;
        formatter.Options.SpaceBetweenMemoryAddOperators = true;
        formatter.Options.SpaceBetweenMemoryMulOperators = false;
        formatter.Options.ShowBranchSize = false;
        formatter.Options.SignedImmediateOperands = false;
        foreach (var range in ranges.EnumerateArray()) {
            Keys(range, "offset", "address", "bytes");
            long offset = range.GetProperty("offset").GetInt64();
            ulong address = range.GetProperty("address").GetUInt64();
            int count = range.GetProperty("bytes").GetInt32();
            total += count;
            if (offset < 0 || count is < 1 or > 65536 || offset > source.Length - count ||
                total > 16 * 1024 * 1024 || address > ulong.MaxValue - (ulong)count) throw new InvalidDataException();
            byte[] data = new byte[count]; source.Position = offset; source.ReadExactly(data);
            var decoder = Decoder.Create(64, new ByteArrayCodeReader(data)); decoder.IP = address;
            var instructions = new List<object[]>();
            while (decoder.IP < address + (ulong)count) {
                decoder.Decode(out var instruction);
                if (instruction.Code == Code.INVALID || decoder.IP > address + (ulong)count || instructions.Count >= 8192 || ++instructionTotal > 262144) throw new InvalidDataException();
                formatter.Options.MemorySizeOptions = instruction.Mnemonic == Mnemonic.Lea ? MemorySizeOptions.Never : MemorySizeOptions.Always;
                var formatted = new StringOutput(); formatter.Format(in instruction, formatted);
                string text = formatted.ToString().ToLowerInvariant();
                int split = text.IndexOf(' ');
                string mnemonic = split < 0 ? text : text[..split];
                string operands = split < 0 ? "" : text[(split + 1)..].Trim();
                if (mnemonic is "lock" or "rep" or "repe" or "repne" or "bnd") {
                    int next = operands.IndexOf(' ');
                    mnemonic += " " + (next < 0 ? operands : operands[..next]);
                    operands = next < 0 ? "" : operands[(next + 1)..].Trim();
                }
                if (instruction.Mnemonic == Mnemonic.Mov && instruction.Op1Kind == OpKind.Immediate64) mnemonic = "movabs";
                // Capstone's canonical condition aliases are the public Python
                // description contract. This changes spelling only, never flow.
                mnemonic = mnemonic switch { "jz" => "je", "jnz" => "jne", "cmovz" => "cmove", "cmovnz" => "cmovne", "setz" => "sete", "setnz" => "setne", _ => mnemonic };
                operands = Regex.Replace(operands, @"\b(?:near|far) ptr ", "");
                instructions.Add(new object[] { instruction.IP, mnemonic, operands });
            }
            result.Add(instructions);
        }
        // Validate the complete request before creating any visible result.
        using var target = new FileStream(output, FileMode.CreateNew, FileAccess.Write);
        JsonSerializer.Serialize(target, result);
    }
    static int Main(string[] args) {
        try {
            if (args.Length == 3 && args[0] == "metadata") Metadata(args[1], args[2]);
            else if (args.Length == 4 && args[0] == "disassemble") Disassemble(args[1], args[2], args[3]);
            else return 2;
            return 0;
        } catch (Exception) {
            Console.Error.WriteLine("Original metadata preparation failed.");
            return 1;
        }
    }
}
