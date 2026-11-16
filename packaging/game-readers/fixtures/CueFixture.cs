// Authored reflection fixture, NOT CUE4Parse code or a locres implementation.
using System.Text;
using System.Text.Json;

namespace CUE4Parse.UE4.Readers
{
    public sealed class FByteArchive
    {
        public byte[] Bytes;
        public FByteArchive(string name, byte[] bytes, object versions) { Bytes = bytes; }
    }
}
namespace CUE4Parse.UE4.Localization
{
    public sealed class TextKey { public string Str; public TextKey(string value) { Str = value; } }
    public sealed class Entry { public string LocalizedString; public Entry(string value) { LocalizedString = value; } }
    public sealed class FTextLocalizationResource
    {
        public Dictionary<TextKey, Dictionary<TextKey, Entry>> Entries;
        public FTextLocalizationResource(CUE4Parse.UE4.Readers.FByteArchive archive)
        {
            // The first 17 bytes exercise the owned bridge's real version gate;
            // the remaining JSON is authored fixture data, never actual locres.
            var row = JsonSerializer.Deserialize<Dictionary<string, string>>(archive.Bytes.AsSpan(17))!;
            Entries = new() { [new TextKey("owned")] = new() { [new TextKey("owned01")] = new Entry(row["text"]) } };
        }
    }
}

namespace CUE4Parse.UE4.Versions
{
    public enum EGame { GAME_NevernessToEverness }
    public sealed class VersionContainer
    {
        public EGame Game { get; }
        public VersionContainer(EGame game) { Game = game; }
    }
}

namespace CUE4Parse.FileProvider
{
    // Authored transport witness only: no IoStore, AES or game package parser.
    public sealed class StreamedFileProvider : IDisposable
    {
        public CUE4Parse.UE4.Versions.VersionContainer Versions { get; }
        public Dictionary<string, int> Files { get; } = new();
        public List<FixtureVfs> UnloadedVfs { get; } = new();
        public List<FixtureVfs> MountedVfs { get; } = new();
        readonly List<Stream> streams = new();
        bool initialized, defaultKey;
        public StreamedFileProvider(string name, CUE4Parse.UE4.Versions.VersionContainer versions, StringComparer comparer)
        {
            if (name != "HT" || !ReferenceEquals(comparer, StringComparer.OrdinalIgnoreCase)) throw new InvalidDataException();
            Versions = versions;
        }
        public void Initialize() { initialized = true; }
        public void RegisterVfs(string name, Stream[] source, Func<string, object>? unused = null)
        {
            if (!initialized || source.Length != 2) throw new InvalidDataException();
            streams.AddRange(source);
            using var toc = new MemoryStream();
            source[0].CopyTo(toc);
            using var row = JsonDocument.Parse(toc.ToArray());
            var item = row.RootElement;
            if (item.GetProperty("schema").GetString() != "proxy-owned-publisher-stream-v1") throw new InvalidDataException();
            var member = source[1];
            member.Seek(item.GetProperty("offset").GetInt64(), SeekOrigin.Begin);
            var data = new byte[item.GetProperty("size").GetInt32()];
            member.ReadExactly(data);
            if (Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(data)).ToLowerInvariant() !=
                item.GetProperty("sha256").GetString()) throw new InvalidDataException();
            var previous = member.Position;
            using var clone = (Stream)((ICloneable)member).Clone();
            clone.Seek(0, SeekOrigin.Begin);
            var prefix = new byte[8]; clone.ReadExactly(prefix);
            if (member.Position != previous || Convert.ToHexString(prefix).ToLowerInvariant() != item.GetProperty("prefix").GetString())
                throw new InvalidDataException();
            member.Seek(-8, SeekOrigin.End);
            var suffix = new byte[8]; member.ReadExactly(suffix);
            if (member.ReadByte() != -1 || Convert.ToHexString(suffix).ToLowerInvariant() != item.GetProperty("suffix").GetString())
                throw new InvalidDataException();
            var refused = false;
            try { member.Seek(1, SeekOrigin.End); } catch (ArgumentOutOfRangeException) { refused = true; }
            if (!refused) throw new InvalidDataException();
            Files[item.GetProperty("member").GetString()!] = 0;
            UnloadedVfs.Add(new FixtureVfs());
        }
        public void SubmitKey(Guid guid, FixtureKey key)
        {
            if (!initialized || key.Value != "0x" + new string('0', 64)) throw new InvalidDataException();
            if (guid == Guid.Empty) defaultKey = true;
            else if (!defaultKey || UnloadedVfs.RemoveAll(v => v.EncryptionKeyGuid == guid) == 0) throw new InvalidDataException();
        }
        public void Mount()
        {
            if (!defaultKey || UnloadedVfs.Count != 0) throw new InvalidDataException();
        }
        public byte[] SaveAsset(string name) => throw new InvalidDataException();
        public void Dispose() { foreach (var source in streams) source.Dispose(); }
    }
}

namespace CUE4Parse.MappingsProvider.Usmap
{
    public sealed class FileUsmapTypeMappingsProvider
    {
        public FileUsmapTypeMappingsProvider(string path, StringComparer comparer)
        {
            if (!File.Exists(path) || !ReferenceEquals(comparer, StringComparer.Ordinal))
                throw new InvalidDataException();
        }
    }
}

// The real bridge resolves version types from the provider field's assembly.
public sealed class FixtureKey
{
    public string Value { get; }
    public FixtureKey(string value) { Value = value; }
}
public sealed class FixtureVfs
{
    public Guid EncryptionKeyGuid { get; } = new("00000000-0000-0000-0000-000000000001");
}
public sealed class FixtureProvider : IDisposable
{
    public Dictionary<string, int> Files { get; } = new();
    public CUE4Parse.MappingsProvider.Usmap.FileUsmapTypeMappingsProvider? MappingsContainer { get; set; }
    public CUE4Parse.UE4.Versions.VersionContainer Versions { get; }
    public List<FixtureVfs> UnloadedVfs { get; } = new();
    private readonly string install;
    private bool initialized, defaultKey, mounted, disposed;
    private byte version;
    private readonly Dictionary<string, string> texts = new() {
        ["en"] = "Owned NTE fixture", ["zh-CN"] = "中文测试", ["zh-Hant"] = "中文測試",
        ["ja"] = "日本語テスト", ["ko"] = "한국어 테스트" };
    public FixtureProvider(string directory, SearchOption search, CUE4Parse.UE4.Versions.VersionContainer versions, StringComparer comparer)
    {
        if (search != SearchOption.AllDirectories || versions.Game != CUE4Parse.UE4.Versions.EGame.GAME_NevernessToEverness ||
            !ReferenceEquals(comparer, StringComparer.OrdinalIgnoreCase)) throw new InvalidDataException();
        install = directory; Versions = versions;
    }
    public void Initialize()
    {
        if (initialized || disposed) throw new InvalidDataException();
        Dictionary<string, JsonElement> marker;
        try
        {
            marker = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(
                File.ReadAllBytes(Path.Combine(install, "owned-fixture.json")))!;
        }
        catch (JsonException)
        {
            // Private authored-fixture witness only. A constructor/reflection
            // failure cannot satisfy the malformed-marker assertion.
            File.WriteAllText(Path.Combine(install, "owned-initialize-rejected.txt"), "owned-malformed-json-rejected");
            throw;
        }
        if (marker["schema"].GetString() != "proxy-owned-nte-fixture-v1") throw new InvalidDataException();
        VerifySequenceFixture(marker);
        VerifyMovieRegistryFixture(marker);
        version = marker["localization_version"].GetByte();
        for (int i = 0; i < 100; i++) Files[$"Owned/Dummy/{i}"] = 0;
        foreach (var locale in texts.Keys) Files[$"Owned/Localization/{locale}/game.locres"] = 0;
        Files["HT/Content/WwiseAudio/Events/Play_Vo_owned01.uasset"] = 0;
        foreach (var voice in new[] { "Chinese", "English", "Japanese", "Korean" })
        {
            Files[$"HT/Content/WwiseAudio/Event/{voice}/Play_Vo_owned01.bnk"] = 0;
            Files[$"HT/Content/WwiseAudio/Media/{voice}/42.wem"] = 0;
            Files[$"HT/Content/WwiseAudio/Media/{voice}/43.wem"] = 0;
        }
        Files["HT/Content/SrtFile/FFMpeg/Story/owned.srt"] = 0;
        UnloadedVfs.Add(new FixtureVfs());
        initialized = true;
    }
    static void VerifySequenceFixture(Dictionary<string, JsonElement> marker)
    {
        if (!marker.TryGetValue("sequence_case", out var selected)) return;
        var kind = selected.GetString();
        object Sequence(string name) => new {
            CaptionsID = name,
            Settings = new { PlayRate = 1, StartTime = 0, bRandomStartTime = false },
            VoiceSource = new { AssetPathName = $"/Game/WwiseAudio/Events/CG/Owned/Play_Vo_CG_{name}.Play_Vo_CG_{name}" }
        };
        object? slot = kind switch {
            "nulls" => null, "string" => "owned invalid slot", "number" => 7,
            "boolean" => true, "array" => Array.Empty<object>(), _ => throw new InvalidDataException()
        };
        var row = JsonSerializer.SerializeToElement(new {
            SequenceInfo = new object?[] { null, Sequence("owned_first"), slot, Sequence("owned_last"), null }
        });
        const string table = "HT/Content/DataTable/DT_StorySequenceData.uasset";
        Func<string, IEnumerable<(string, JsonElement)>> rows = name =>
            name == table ? new[] { ("owned_row", row) } : throw new InvalidDataException();
        Func<string, object> export = _ => throw new InvalidDataException();
        var voices = new HashSet<string>();
        var method = System.Reflection.Assembly.GetEntryAssembly()!.GetType("NteReader", true)!
            .GetMethod("ReadNteSequences", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        try {
            method.Invoke(null, new object[] { new HashSet<string> { table }, rows, export, voices, "unused-owned-output" });
        }
        catch (System.Reflection.TargetInvocationException error) when
            (kind != "nulls" && error.InnerException?.GetType().Name == "UnsupportedGameFormatException") { return; }
        if (kind != "nulls" || !voices.SetEquals(new[] { "Play_Vo_CG_owned_first", "Play_Vo_CG_owned_last" }))
            throw new InvalidDataException();
    }
    static void VerifyMovieRegistryFixture(Dictionary<string, JsonElement> marker)
    {
        if (!marker.TryGetValue("movie_registry_case", out var selected)) return;
        var kind = selected.GetString();
        const string table = "HT/Content/DataTable/DT_TextTable.uasset";
        const string first = "HT/Content/Text/OwnedAsset.uasset";
        const string second = "HT/Content/Text/OtherOwnedAsset.uasset";
        JsonElement Row(string path) => JsonSerializer.SerializeToElement(new {
            TextTable = new { AssetPathName = path, SubPathString = "" }
        });
        var valid = Row("/Game/Text/OwnedAsset.DifferentObjectName");
        var data = new List<(string, JsonElement)> {
            ("FutureAlias", valid), ("SameOwner", valid),
            ("NamedSibling", Row("/Game/Text/OwnedAsset.SecondObjectName")),
            ("MissingOwner", Row("/Game/Text/Absent.Owned")), ("EmptyOwner", Row("None")),
            ("Conflict", valid), ("CONFLICT", Row("/Game/Text/OtherOwnedAsset.OtherObject"))
        };
        if (kind == "escape") data.Add(("Bad", Row("/Game/Text/../Escaped.Owned")));
        else if (kind == "missing-property") data.Add(("Bad", JsonSerializer.SerializeToElement(new { Unexpected = true })));
        else if (kind == "too-many") data.AddRange(Enumerable.Repeat(("FutureAlias", valid), 4097));
        else if (kind is not ("valid" or "wrong-owner" or "namespace-overflow")) throw new InvalidDataException();
        Func<string, IEnumerable<(string, JsonElement)>> rows = name => name == table ? data : throw new InvalidDataException();
        var reads = new Dictionary<string, int>();
        Func<string, string, JsonElement> owner = (path, name) => {
            if (!(path == first && name is "DifferentObjectName" or "SecondObjectName" ||
                  path == second && name == "OtherObject")) throw new InvalidDataException();
            var identity = path + "\0" + name;
            reads[identity] = reads.GetValueOrDefault(identity) + 1;
            return JsonSerializer.SerializeToElement(new {
                Type = kind == "wrong-owner" ? "DataTable" : "StringTable",
                StringTable = new { TableNamespace = kind == "namespace-overflow" ? new string('x', 513) :
                    path == first ? name == "DifferentObjectName" ? "Owned.Namespace" : "Sibling.Namespace" : "Other.Namespace" }
            });
        };
        var method = System.Reflection.Assembly.GetEntryAssembly()!.GetType("NteReader", true)!
            .GetMethod("ReadNteMovieNamespaces", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        Dictionary<string, string?> result;
        try {
            result = (Dictionary<string, string?>)method.Invoke(null, new object[] {
                new HashSet<string> { table, first, second }, rows, owner })!;
        }
        catch (System.Reflection.TargetInvocationException error) when
            (kind != "valid" && error.InnerException?.GetType().Name == "UnsupportedGameFormatException") { return; }
        if (kind != "valid" || result.Count != 6 || result["FutureAlias"] != "Owned.Namespace" ||
            result["SameOwner"] != "Owned.Namespace" || result["MissingOwner"] != null ||
            result["NamedSibling"] != "Sibling.Namespace" || result["EmptyOwner"] != null || result["Conflict"] != null ||
            reads[first + "\0DifferentObjectName"] != 1 || reads[first + "\0SecondObjectName"] != 1 || reads[second + "\0OtherObject"] != 1)
            throw new InvalidDataException();
    }
    public void SubmitKey(Guid guid, FixtureKey key)
    {
        if (!initialized || disposed || key.Value != "0x" + new string('0', 64)) throw new InvalidDataException();
        if (guid == Guid.Empty) defaultKey = true;
        else if (!defaultKey || UnloadedVfs.RemoveAll(archive => archive.EncryptionKeyGuid == guid) != 1)
            throw new InvalidDataException();
    }
    public void Mount()
    {
        if (!initialized || !defaultKey || UnloadedVfs.Count != 0 || disposed) throw new InvalidDataException();
        mounted = true;
    }
    public byte[] SaveAsset(string name)
    {
        if (!mounted || disposed || !Files.ContainsKey(name)) throw new InvalidDataException();
        if (name.EndsWith(".locres"))
        {
            using var output = new MemoryStream(); using var writer = new BinaryWriter(output);
            foreach (var word in new uint[] { 0x7574140E, 0xFC034A67, 0x9D90154A, 0x1B7F37C3 }) writer.Write(word);
            writer.Write(version); writer.Write(JsonSerializer.SerializeToUtf8Bytes(new { text = texts[name.Split('/')[2]] }));
            return output.ToArray();
        }
        if (name.EndsWith(".wem")) return Enumerable.Range(0, 256).Select(i => (byte)(name.EndsWith("/43.wem") ? 255 - i : i)).ToArray();
        if (name.EndsWith(".bnk")) return Encoding.ASCII.GetBytes("BKHD owned fixture bank");
        if (name.EndsWith(".srt")) return Encoding.UTF8.GetBytes("1\n00:00:01,000 --> 00:00:02,000\nOwned subtitle\n");
        throw new InvalidDataException();
    }
    public void Dispose() { disposed = true; }
}
