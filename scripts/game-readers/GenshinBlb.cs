using System.Buffers.Binary;
using System.Text.Json;
using AnimeStudio;

// The original executable and Unity runtime are never loaded. Codec arrays are
// data, supplied in a private bounded file; none is embedded in this assembly.
internal static class Program
{
    private static void Require(bool value) { if (!value) throw new InvalidDataException(); }
    public static int Main(string[] args)
    {
        try
        {
            Require(args.Length == 4 && args[0] == "decode" && args.Skip(1).All(Path.IsPathFullyQualified));
            Require(args.Skip(1).Select(Path.GetFullPath).Distinct(StringComparer.OrdinalIgnoreCase).Count() == 3);
            var input = new FileInfo(args[1]);
            Require(input.Length >= 84 && input.Length <= 160L * 1024 * 1024 && !File.Exists(args[3]));
            CryptoHelper.Load(args[2]);
            var raw = File.ReadAllBytes(args[1]);
            Require(raw.AsSpan(0, 4).SequenceEqual(new byte[] { 0x42, 0x6c, 0x62, 3 }));
            var size = BinaryPrimitives.ReadInt32LittleEndian(raw.AsSpan(4));
            Require(size >= 56 && size <= 1024 * 1024 && size <= raw.Length - 28);
            var header = raw.AsSpan(28, size);
            var key = raw.AsSpan(12, 16).ToArray();
            BlbUtils.InitKeys(CryptoHelper.Blb3RC4Key, CryptoHelper.Blb3SBox,
                CryptoHelper.Blb3ShiftRow, CryptoHelper.Blb3Key, CryptoHelper.Blb3Mul);
            BlbUtils.Decrypt(key, header);
            var count = BinaryPrimitives.ReadInt32LittleEndian(header.Slice(24));
            var table = 32 + BinaryPrimitives.ReadInt64LittleEndian(header.Slice(32));
            Require(BinaryPrimitives.ReadInt32LittleEndian(header) == raw.Length
                    && count >= 1 && count <= 8192 && table >= 56 && table <= size - count * 4);
            var body = 28 + size;
            var previous = 0;
            for (var i = 0; i < count; i++)
            {
                var end = BinaryPrimitives.ReadInt32LittleEndian(header.Slice((int)table + i * 4));
                Require(end > previous && end <= raw.Length - body);
                BlbUtils.Decrypt(key, raw.AsSpan(body + previous, end - previous));
                previous = end;
            }
            Require(body + previous == raw.Length);
            using var output = new FileStream(args[3], FileMode.CreateNew, FileAccess.Write);
            output.Write(raw);
            return 0;
        }
        catch (Exception)
        {
            // No source excerpts, filenames, codec values or original bytes.
            Console.Error.WriteLine("The bounded original container could not be decoded.");
            return 2;
        }
    }
}

namespace AnimeStudio
{
    // Adapter for the unmodified frozen MIT implementation. Only fixed named
    // byte arrays are accepted; the upstream CryptoHelper source is excluded.
    internal static class CryptoHelper
    {
        public static byte[] GF256Exp = [], GF256Log = [], Blb3AESSBox = [], Blb3AESShift = [],
            Blb3RC4Key = [], Blb3SBox = [], Blb3ShiftRow = [], Blb3Key = [], Blb3Mul = [];

        public static void Load(string path)
        {
            var file = new FileInfo(path);
            if (file.Length <= 0 || file.Length > 32 * 1024) throw new InvalidDataException();
            using var document = JsonDocument.Parse(File.ReadAllBytes(path));
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object) throw new InvalidDataException();
            var expected = new Dictionary<string, int> { ["GF256Exp"] = 256, ["GF256Log"] = 256,
                ["Blb3AESSBox"] = 256, ["Blb3AESShift"] = 16, ["Blb3RC4Key"] = 256,
                ["Blb3SBox"] = 1024, ["Blb3ShiftRow"] = 48, ["Blb3Key"] = 8, ["Blb3Mul"] = 8 };
            var values = new Dictionary<string, byte[]>();
            foreach (var item in root.EnumerateObject())
            {
                if (!expected.TryGetValue(item.Name, out var size) || values.ContainsKey(item.Name))
                    throw new InvalidDataException();
                var value = item.Value.GetBytesFromBase64();
                if (value.Length != size) throw new InvalidDataException();
                values.Add(item.Name, value);
            }
            if (values.Count != expected.Count) throw new InvalidDataException();
            GF256Exp = values["GF256Exp"]; GF256Log = values["GF256Log"];
            Blb3AESSBox = values["Blb3AESSBox"]; Blb3AESShift = values["Blb3AESShift"];
            Blb3RC4Key = values["Blb3RC4Key"]; Blb3SBox = values["Blb3SBox"];
            Blb3ShiftRow = values["Blb3ShiftRow"]; Blb3Key = values["Blb3Key"]; Blb3Mul = values["Blb3Mul"];
        }
    }
}
