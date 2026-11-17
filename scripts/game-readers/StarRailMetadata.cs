// SPDX-License-Identifier: GPL-3.0-or-later
// Metadata-only bridge to the separately acquired, pinned GPL reader. Native
// client files are data: this program never loads or invokes a client library.
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Buffers.Binary;
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
            bool flow = range.TryGetProperty("control_flow", out var flowValue);
            if (flow) { Keys(range, "offset", "address", "bytes", "control_flow"); if (flowValue.ValueKind != JsonValueKind.True) throw new InvalidDataException(); }
            else Keys(range, "offset", "address", "bytes");
            long offset = range.GetProperty("offset").GetInt64();
            ulong address = range.GetProperty("address").GetUInt64();
            int count = range.GetProperty("bytes").GetInt32();
            total += count;
            if (offset < 0 || count is < 1 or > 65536 || offset > source.Length - count ||
                total > 16 * 1024 * 1024 || address > ulong.MaxValue - (ulong)count) throw new InvalidDataException();
            byte[] data = new byte[count]; source.Position = offset; source.ReadExactly(data);
            var pending = new Queue<ulong>(); pending.Enqueue(address);
            var decoded = new SortedDictionary<ulong, Instruction>();
            var occupied = new Dictionary<ulong, ulong>();
            var branchTargets = new SortedSet<ulong>();
            var guardedRegions = new List<(ulong First, ulong Last)>();
            while (pending.Count != 0) {
                ulong entry = pending.Dequeue();
                if (decoded.ContainsKey(entry)) continue;
                if (entry < address || entry >= address + (ulong)count) throw new InvalidDataException();
                int skip = checked((int)(entry - address));
                var reader = new ByteArrayCodeReader(data); reader.Position = skip;
                var decoder = Decoder.Create(64, reader); decoder.IP = entry;
                var path = new List<Instruction>();
                while (decoder.IP < address + (ulong)count) {
                    if (decoded.ContainsKey(decoder.IP)) break;
                    decoder.Decode(out var instruction);
                    if (instruction.Code == Code.INVALID || decoder.IP > address + (ulong)count || decoded.Count >= 8192 || ++instructionTotal > 262144) throw new InvalidDataException();
                    for (ulong at = instruction.IP; at < instruction.NextIP; at++) {
                        if (occupied.ContainsKey(at)) throw new InvalidDataException();
                        occupied.Add(at, instruction.IP);
                    }
                    decoded.Add(instruction.IP, instruction);
                    path.Add(instruction);
                    if (!flow) continue;
                    if (instruction.NextIP == address + (ulong)count && instruction.FlowControl is FlowControl.Next or FlowControl.Call or FlowControl.IndirectCall or FlowControl.ConditionalBranch) throw new InvalidDataException();
                    if (instruction.FlowControl == FlowControl.XbeginXabortXend) throw new InvalidDataException();
                    if (instruction.FlowControl == FlowControl.IndirectBranch) {
                        // Bounded compiler switch: unsigned index guard, then a
                        // RIP-relative signed-32 table and an indirect jump.
                        // Enumerate all authored edges, never evaluate an index.
                        if (path.Count < 6) throw new InvalidDataException();
                        var guard = path[^6]; var fallback = path[^5]; var pointer = path[^4];
                        var load = path[^3]; var add = path[^2];
                        if (guard.Mnemonic != Mnemonic.Cmp || guard.Op0Kind != OpKind.Register || guard.Op0Register.GetSize() != 4 ||
                            fallback.Mnemonic != Mnemonic.Ja || pointer.Mnemonic != Mnemonic.Lea || pointer.MemoryBase != Register.RIP ||
                            pointer.MemoryIndex != Register.None || pointer.Op0Register.GetSize() != 8 ||
                            load.Mnemonic != Mnemonic.Movsxd || load.Op0Register.GetSize() != 8 ||
                            load.MemoryBase != pointer.Op0Register || load.MemoryIndex != guard.Op0Register.GetFullRegister() ||
                            load.MemoryIndexScale != 4 || load.MemoryDisplacement64 != 0 ||
                            add.Mnemonic != Mnemonic.Add || add.Op0Register != load.Op0Register || add.Op1Register != pointer.Op0Register ||
                            instruction.Mnemonic != Mnemonic.Jmp || instruction.Op0Register != load.Op0Register) throw new InvalidDataException();
                        ulong maximum = guard.GetImmediate(1), table = pointer.IPRelativeMemoryAddress;
                        if (maximum > 255 || table < address || table > address + (ulong)count || (maximum + 1) * 4 > address + (ulong)count - table) throw new InvalidDataException();
                        for (ulong i = 0; i <= maximum; i++) {
                            int relative = BinaryPrimitives.ReadInt32LittleEndian(data.AsSpan(checked((int)(table - address + i * 4)), 4));
                            ulong edge = unchecked((ulong)((long)table + relative));
                            if (edge < address || edge >= address + (ulong)count) throw new InvalidDataException();
                            pending.Enqueue(edge); branchTargets.Add(edge);
                        }
                        guardedRegions.Add((pointer.IP, instruction.IP));
                        break;
                    }
                    if (instruction.FlowControl is FlowControl.Return or FlowControl.Interrupt or FlowControl.Exception) break;
                    if (instruction.FlowControl is FlowControl.UnconditionalBranch or FlowControl.ConditionalBranch) {
                        if (instruction.Op0Kind is not (OpKind.NearBranch16 or OpKind.NearBranch32 or OpKind.NearBranch64)) throw new InvalidDataException();
                        ulong branch = instruction.NearBranchTarget;
                        branchTargets.Add(branch);
                        if (branch >= address && branch < address + (ulong)count) pending.Enqueue(branch);
                        else if (instruction.FlowControl == FlowControl.ConditionalBranch) throw new InvalidDataException();
                        if (instruction.FlowControl == FlowControl.UnconditionalBranch) break;
                    }
                }
            }
            foreach (var region in guardedRegions) {
                using var entries = branchTargets.GetViewBetween(region.First, region.Last).GetEnumerator();
                if (entries.MoveNext()) throw new InvalidDataException();
            }
            var instructions = new List<object[]>();
            foreach (var instruction in decoded.Values) {
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
