// SPDX-License-Identifier: GPL-3.0-or-later
// Metadata-only bridge to the separately acquired, pinned GPL reader. Native
// client files are data: this program never loads or invokes a client library.
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Buffers.Binary;
using System.Security.Cryptography;
using HSRGlobalMetadata;
using HSRGlobalMetadata.Output;
using HSRGlobalMetadata.Structs;
using HSRGlobalMetadata.Utils;
using Iced.Intel;

internal static class StarRailMetadata {
    static IntelFormatter NativeFormatter() {
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
        return formatter;
    }
    static object[] FormatInstruction(Instruction instruction, IntelFormatter formatter) {
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
        // Preserve the existing Python description spelling contract.
        mnemonic = mnemonic switch { "jz" => "je", "jnz" => "jne", "cmovz" => "cmove", "cmovnz" => "cmovne", "setz" => "sete", "setnz" => "setne", _ => mnemonic };
        operands = Regex.Replace(operands, @"\b(?:near|far) ptr ", "");
        return new object[] { instruction.IP, mnemonic, operands };
    }
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
        var formatter = NativeFormatter();
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
            foreach (var instruction in decoded.Values) instructions.Add(FormatInstruction(instruction, formatter));
            result.Add(instructions);
        }
        // Validate the complete request before creating any visible result.
        using var target = new FileStream(output, FileMode.CreateNew, FileAccess.Write);
        JsonSerializer.Serialize(target, result);
    }
    readonly record struct NativeSection(uint Rva, uint Bytes, uint Offset, bool Executable);
    readonly record struct NativeFunction(uint Start, uint End, uint Unwind);
    sealed record NativeRegion(NativeFunction Function, long Offset, byte[] Data);

    // Only PE metadata and explicitly reached instruction bytes are read. The
    // client image is never loaded as a library, invoked or emulated.
    sealed class NativeImage : IDisposable {
        readonly FileStream source;
        readonly NativeSection[] sections;
        readonly NativeFunction[] functions;
        public ulong ImageBase { get; }
        public NativeImage(string path) {
            source = File.OpenRead(path);
            try {
                if (source.Length > 1024L * 1024 * 1024) throw new InvalidDataException();
                byte[] dos = Read(0, 64);
                if (dos[0] != 'M' || dos[1] != 'Z') throw new InvalidDataException();
                uint pe = BinaryPrimitives.ReadUInt32LittleEndian(dos.AsSpan(60));
                if (pe > 1024 * 1024) throw new InvalidDataException();
                byte[] coff = Read(pe, 24);
                int count = BinaryPrimitives.ReadUInt16LittleEndian(coff.AsSpan(6));
                int optional = BinaryPrimitives.ReadUInt16LittleEndian(coff.AsSpan(20));
                if (BinaryPrimitives.ReadUInt32LittleEndian(coff) != 0x4550 ||
                    BinaryPrimitives.ReadUInt16LittleEndian(coff.AsSpan(4)) != 0x8664 ||
                    count is < 1 or > 96 || optional is < 240 or > 4096) throw new InvalidDataException();
                byte[] headers = Read((long)pe + 24, optional + count * 40);
                if (BinaryPrimitives.ReadUInt16LittleEndian(headers) != 0x20b ||
                    BinaryPrimitives.ReadUInt32LittleEndian(headers.AsSpan(108)) < 4) throw new InvalidDataException();
                ImageBase = BinaryPrimitives.ReadUInt64LittleEndian(headers.AsSpan(24));
                if (ImageBase > ulong.MaxValue - uint.MaxValue) throw new InvalidDataException();
                sections = new NativeSection[count];
                for (int i = 0; i < count; i++) {
                    var row = headers.AsSpan(optional + i * 40, 40);
                    var section = new NativeSection(BinaryPrimitives.ReadUInt32LittleEndian(row[12..]),
                        BinaryPrimitives.ReadUInt32LittleEndian(row[16..]), BinaryPrimitives.ReadUInt32LittleEndian(row[20..]),
                        (BinaryPrimitives.ReadUInt32LittleEndian(row[36..]) & 0x20000000) != 0);
                    if ((ulong)section.Rva + section.Bytes > (ulong)uint.MaxValue + 1 ||
                        (ulong)section.Offset + section.Bytes > (ulong)source.Length) throw new InvalidDataException();
                    sections[i] = section;
                }
                uint directory = BinaryPrimitives.ReadUInt32LittleEndian(headers.AsSpan(136));
                uint bytes = BinaryPrimitives.ReadUInt32LittleEndian(headers.AsSpan(140));
                if (directory == 0 || bytes == 0 || bytes > 64 * 1024 * 1024 || bytes % 12 != 0) throw new InvalidDataException();
                byte[] table = Read(Offset(directory, checked((int)bytes)), checked((int)bytes));
                functions = new NativeFunction[table.Length / 12];
                for (int i = 0; i < functions.Length; i++) {
                    var row = table.AsSpan(i * 12, 12);
                    var function = new NativeFunction(BinaryPrimitives.ReadUInt32LittleEndian(row),
                        BinaryPrimitives.ReadUInt32LittleEndian(row[4..]), BinaryPrimitives.ReadUInt32LittleEndian(row[8..]));
                    if (function.Start >= function.End || function.Unwind == 0 ||
                        i > 0 && functions[i - 1].Start >= function.Start) throw new InvalidDataException();
                    functions[i] = function;
                }
            } catch { source.Dispose(); throw; }
        }
        byte[] Read(long offset, int bytes) {
            if (offset < 0 || bytes < 1 || offset > source.Length - bytes) throw new InvalidDataException();
            byte[] data = new byte[bytes]; source.Position = offset; source.ReadExactly(data); return data;
        }
        long Offset(uint rva, int bytes, bool code = false) {
            var matches = sections.Where(s => s.Rva <= rva &&
                (ulong)rva + (ulong)bytes <= (ulong)s.Rva + s.Bytes && (!code || s.Executable)).ToArray();
            if (bytes < 1 || matches.Length != 1) throw new InvalidDataException();
            return (long)matches[0].Offset + rva - matches[0].Rva;
        }
        public uint Rva(ulong address) {
            if (address < ImageBase || address - ImageBase > uint.MaxValue) throw new InvalidDataException();
            return (uint)(address - ImageBase);
        }
        public NativeFunction Owner(uint address) {
            int lo = 0, hi = functions.Length;
            while (lo < hi) { int middle = (lo + hi) / 2; if (functions[middle].Start <= address) lo = middle + 1; else hi = middle; }
            if (lo == 0) throw new InvalidDataException();
            var owner = functions[lo - 1];
            if (address >= owner.End || owner.End - owner.Start > 32768) throw new InvalidDataException();
            return owner;
        }
        public NativeRegion Region(NativeFunction owner) {
            int bytes = checked((int)(owner.End - owner.Start));
            long offset = Offset(owner.Start, bytes, true); Offset(owner.Unwind, 1);
            return new NativeRegion(owner, offset, Read(offset, bytes));
        }
        public void Dispose() => source.Dispose();
    }
    static void NativeGraph(string input, string request, string output) {
        input = Existing(input); request = Existing(request); output = NewOutput(output);
        if (new FileInfo(request).Length > 1024 * 1024) throw new InvalidDataException();
        using var document = JsonDocument.Parse(File.ReadAllText(request));
        Keys(document.RootElement, "entry_rva");
        uint entry = document.RootElement.GetProperty("entry_rva").GetUInt32();
        using var image = new NativeImage(input);
        if (image.Owner(entry).Start != entry) throw new InvalidDataException();
        var regions = new SortedDictionary<uint, NativeRegion>();
        var instructions = new SortedDictionary<uint, Instruction>();
        var occupied = new Dictionary<uint, uint>();
        var edges = new SortedDictionary<uint, SortedSet<uint>>();
        var calls = new SortedDictionary<uint, (string Kind, ulong? Target)>();
        var returns = new SortedSet<uint>();
        var pending = new Queue<uint>(); pending.Enqueue(entry);
        int total = 0;
        while (pending.Count != 0) {
            uint address = pending.Dequeue();
            if (instructions.ContainsKey(address)) continue;
            if (occupied.ContainsKey(address) || instructions.Count >= 8192) throw new InvalidDataException();
            var owner = image.Owner(address);
            if (!regions.TryGetValue(owner.Start, out var region)) {
                // A new owner needs an original entry boundary. Interior
                // targets become admissible only through its decoded graph.
                if (address != owner.Start) throw new InvalidDataException();
                var candidate = image.Region(owner);
                total = checked(total + candidate.Data.Length);
                if (regions.Count >= 16 || total > 32768 || regions.Values.Any(r =>
                    r.Function.Start < owner.End && owner.Start < r.Function.End)) throw new InvalidDataException();
                region = candidate; regions.Add(owner.Start, region);
            }
            var reader = new ByteArrayCodeReader(region.Data); reader.Position = checked((int)(address - owner.Start));
            var decoder = Decoder.Create(64, reader); decoder.IP = image.ImageBase + address;
            decoder.Decode(out var instruction);
            uint next = image.Rva(instruction.NextIP);
            if (instruction.Code == Code.INVALID || instruction.IP != image.ImageBase + address ||
                next <= address || next - address > 15 || next > owner.End) throw new InvalidDataException();
            for (uint at = address; at < next; at++) {
                if (!occupied.TryAdd(at, address)) throw new InvalidDataException();
            }
            instructions.Add(address, instruction);
            var successors = new SortedSet<uint>();
            bool fallthrough = false;
            switch (instruction.FlowControl) {
                case FlowControl.Return:
                    if (instruction.Mnemonic != Mnemonic.Ret) throw new InvalidDataException();
                    returns.Add(address); break;
                case FlowControl.UnconditionalBranch:
                case FlowControl.ConditionalBranch:
                    if (instruction.Op0Kind is not (OpKind.NearBranch16 or OpKind.NearBranch32 or OpKind.NearBranch64)) throw new InvalidDataException();
                    successors.Add(image.Rva(instruction.NearBranchTarget));
                    fallthrough = instruction.FlowControl == FlowControl.ConditionalBranch; break;
                case FlowControl.Call:
                    if (instruction.Op0Kind is not (OpKind.NearBranch16 or OpKind.NearBranch32 or OpKind.NearBranch64)) throw new InvalidDataException();
                    calls.Add(address, ("direct", instruction.NearBranchTarget)); fallthrough = true; break;
                case FlowControl.IndirectCall:
                    // An opaque call is recorded, never followed or evaluated.
                    calls.Add(address, ("indirect", null)); fallthrough = true; break;
                case FlowControl.Next: fallthrough = true; break;
                default: throw new InvalidDataException();
            }
            if (fallthrough) {
                if (next >= owner.End) throw new InvalidDataException();
                successors.Add(next);
            }
            edges.Add(address, successors);
            foreach (uint target in successors) pending.Enqueue(target);
        }
        if (returns.Count == 0 || edges.Values.SelectMany(v => v).Any(v => !instructions.ContainsKey(v))) throw new InvalidDataException();
        var formatter = NativeFormatter();
        var result = new {
            schema = "proxy-starrail-native-graph-v1", image_base = image.ImageBase, entry_rva = entry,
            regions = regions.Values.Select(r => new { rva = r.Function.Start, bytes = r.Data.Length,
                offset = r.Offset, unwind_rva = r.Function.Unwind, sha256 = Convert.ToHexStringLower(SHA256.HashData(r.Data)) }).ToArray(),
            instructions = instructions.Values.Select(i => { var row = FormatInstruction(i, formatter);
                return new object[] { row[0], row[1], row[2], checked((int)(i.NextIP - i.IP)) }; }).ToArray(),
            edges = edges.Select(e => new object[] { image.ImageBase + e.Key, e.Value.Select(v => image.ImageBase + v).ToArray() }).ToArray(),
            calls = calls.Select(c => new object?[] { image.ImageBase + c.Key, c.Value.Kind, c.Value.Target }).ToArray(),
            returns = returns.Select(v => image.ImageBase + v).ToArray()
        };
        // Failure cannot expose a partial graph or replace an existing output.
        using var destination = new FileStream(output, FileMode.CreateNew, FileAccess.Write);
        JsonSerializer.Serialize(destination, result);
    }
    static int Main(string[] args) {
        try {
            if (args.Length == 3 && args[0] == "metadata") Metadata(args[1], args[2]);
            else if (args.Length == 4 && args[0] == "disassemble") Disassemble(args[1], args[2], args[3]);
            else if (args.Length == 4 && args[0] == "native-graph") NativeGraph(args[1], args[2], args[3]);
            else return 2;
            return 0;
        } catch (Exception) {
            Console.Error.WriteLine("Original metadata preparation failed.");
            return 1;
        }
    }
}
