// Authored reflection fixture, NOT CUE4Parse code or a locres implementation.
using System.Text;
using System.Text.Json;

namespace CUE4Parse.UE4.Readers
{
    public sealed class FByteArchive : IDisposable
    {
        public byte[] Bytes;
        public long Position { get; set; }
        public long Length => Bytes.LongLength;
        public bool Disposed { get; private set; }
        public FByteArchive(string name, byte[] bytes, object versions) { Bytes = bytes; }
        public void Dispose() { Disposed = true; }
    }
}
namespace CUE4Parse.UE4.AssetRegistry
{
    public sealed class FixtureAssetData
    {
        public string AssetClass;
        public string PackageName;
        public string AssetName;
        public Dictionary<string, string> TagsAndValues;
        public FixtureAssetData(string assetClass, string packageName, string assetName, Dictionary<string, string> tags)
        { AssetClass = assetClass; PackageName = packageName; AssetName = assetName; TagsAndValues = tags; }
    }
    public sealed class FAssetRegistryState
    {
        public FixtureAssetData[] PreallocatedAssetDataBuffers;
        public static CUE4Parse.UE4.Readers.FByteArchive? LastArchive;
        public FAssetRegistryState(CUE4Parse.UE4.Readers.FByteArchive archive)
        {
            if (archive.Disposed) throw new InvalidDataException();
            LastArchive = archive;
            using var data = JsonDocument.Parse(archive.Bytes);
            if (data.RootElement.GetProperty("schema").GetString() != "owned-registry-fixture-v1") throw new InvalidDataException();
            PreallocatedAssetDataBuffers = data.RootElement.GetProperty("assets").EnumerateArray().Select(row =>
                new FixtureAssetData(row.GetProperty("assetClass").GetString()!, row.GetProperty("packageName").GetString()!,
                    row.TryGetProperty("assetName", out var name) ? name.GetString()! : "Unused",
                    row.TryGetProperty("tags", out var tags) ? JsonSerializer.Deserialize<Dictionary<string,string>>(tags.GetRawText())! : new())).ToArray();
            archive.Position = archive.Length - (data.RootElement.TryGetProperty("unconsumed", out var suffix) && suffix.GetBoolean() ? 1 : 0);
        }
    }
}
namespace CUE4Parse.UE4.Assets.Readers
{
    public sealed class FAssetArchive
    {
        public long Position { get; set; }
        public FAssetArchive(CUE4Parse.UE4.Readers.FByteArchive archive, object? owner, int offset, object? payload)
        {
            if (archive.Disposed || archive.Bytes.Length != 0 || owner is not null || offset != 0 || payload is not null)
                throw new InvalidDataException();
        }
    }
}
namespace CUE4Parse.UE4.Assets.Objects
{
    public enum FixtureReadType { NORMAL, ZERO }
    public sealed class FStructFallback { }
    public sealed class FOwnedZero { public int Value { get; } = 0; }
    public sealed class FOwnedConsumesArchive
    {
        public FOwnedConsumesArchive(CUE4Parse.UE4.Assets.Readers.FAssetArchive archive) { archive.Position++; }
    }
    public sealed class FScriptStruct
    {
        public object StructType;
        public static List<string> Created { get; } = new();
        public FScriptStruct(CUE4Parse.UE4.Assets.Readers.FAssetArchive archive, string name, object? schema, FixtureReadType? readType)
        {
            if (schema is not null || readType != FixtureReadType.ZERO) throw new InvalidDataException();
            Created.Add(name);
            StructType = name switch {
                "OwnedConcrete" => new FOwnedZero(), "OwnedFallback" => new FStructFallback(),
                "OwnedConsumesArchive" => new FOwnedConsumesArchive(archive), "OwnedForeign" => new object(),
                _ => throw new InvalidDataException("An ordinary fixture fallback requires unavailable package state.")
            };
        }
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
    public sealed class FixtureGameFile
    {
        public long Size { get; }
        public FixtureGameFile(long size) { if (size < 1) throw new InvalidDataException(); Size = size; }
    }
    // Authored transport witness only: no IoStore, AES or game package parser.
    public sealed class StreamedFileProvider : IDisposable
    {
        public CUE4Parse.UE4.Versions.VersionContainer Versions { get; }
        public Dictionary<string, FixtureGameFile> Files { get; } = new();
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
            if (item.TryGetProperty("metadata_only", out var metadataOnly) && metadataOnly.GetBoolean())
            {
                foreach (var file in item.GetProperty("fixture_files").EnumerateObject())
                    Files[file.Name] = new FixtureGameFile(file.Value.GetInt64());
                UnloadedVfs.Add(new FixtureVfs());
                return;
            }
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
            Files[item.GetProperty("member").GetString()!] = new FixtureGameFile(data.LongLength);
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
        public FixtureMappings MappingsForGame { get; }
        public FileUsmapTypeMappingsProvider(string path, StringComparer comparer)
        {
            var usage = comparer.GetType();
            if (!File.Exists(path) || !(ReferenceEquals(comparer, StringComparer.Ordinal) ||
                usage.FullName == "NteReader+SchemaUsageComparer" && usage.Assembly == System.Reflection.Assembly.GetEntryAssembly()))
                throw new InvalidDataException();
            MappingsForGame = new FixtureMappings(comparer);
        }
    }
    public sealed class FixtureMappings
    {
        public Dictionary<string, object> Types;
        public FixtureMappings(StringComparer comparer) { Types = new(comparer); }
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
        VerifyDialogueRegistryFixture(marker);
        VerifyOriginalTableRegistryFixture(marker);
        VerifyFrozenCodecsFixture(marker);
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
        var prefix = kind == "named-voice" ? "Play_Vo_" : "Play_Vo_CG_";
        object Sequence(string name, string? source = null) => new {
            CaptionsID = name,
            Settings = new { PlayRate = 1, StartTime = 0, bRandomStartTime = false },
            VoiceSource = new { AssetPathName = source ?? $"/Game/WwiseAudio/Events/CG/Owned/{prefix}{name}.{prefix}{name}" }
        };
        object? slot = kind switch {
            "nulls" => null, "named-voice" => Sequence("owned_middle"), "string" => "owned invalid slot", "number" => 7,
            "boolean" => true, "array" => Array.Empty<object>(), _ => throw new InvalidDataException()
        };
        var row = JsonSerializer.SerializeToElement(new {
            SequenceInfo = new object?[] { null, Sequence("owned_first"), slot, Sequence("owned_last"), null,
                kind == "named-voice" ? Sequence("music", "/Game/WwiseAudio/Events/CG/Owned/Play_Sfx_owned.Play_Sfx_owned") : null,
                kind == "named-voice" ? Sequence("outside", "/Game/WwiseAudio/Events/Dialogue/Owned/Play_Vo_outside.Play_Vo_outside") : null,
                kind == "named-voice" ? Sequence("mismatch", "/Game/WwiseAudio/Events/CG/Owned/Play_Vo_first.Play_Vo_second") : null,
                kind == "named-voice" ? Sequence("escape", "/Game/WwiseAudio/Events/CG/../Owned/Play_Vo_escape.Play_Vo_escape") : null }
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
            (kind is not ("nulls" or "named-voice") && error.InnerException?.GetType().Name == "UnsupportedGameFormatException") { return; }
        var expected = kind == "named-voice" ? new[] { prefix + "owned_first", prefix + "owned_middle", prefix + "owned_last" } :
            new[] { prefix + "owned_first", prefix + "owned_last" };
        if (kind is not ("nulls" or "named-voice") || !voices.SetEquals(expected))
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
    void VerifyDialogueRegistryFixture(Dictionary<string, JsonElement> marker)
    {
        if (!marker.TryGetValue("dialogue_registry_case", out var selected)) return;
        var kind = selected.GetString();
        var entries = new List<object> {
            new { assetClass = "DlgDialogue", packageName = kind == "escape" ? "/Game/../Escaped" : "/Game/Dialogue/Owned" },
            new { assetClass = "StringTable", packageName = "/Game/Text/Owned" },
            new { assetClass = "Other", packageName = "/Game/NotSelected" }
        };
        if (kind == "duplicate") entries.Add(new { assetClass = "DlgDialogue", packageName = "/Game/Dialogue/Owned" });
        if (kind == "empty") entries.Clear();
        var destination = Path.Combine(install, "owned-dialogue-registry");
        Directory.CreateDirectory(destination);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(new { schema = "owned-registry-fixture-v1", assets = entries,
            unconsumed = kind is "unconsumed" or "legacy-unconsumed" });
        File.WriteAllBytes(Path.Combine(destination, "dialogue-registry.bin"), bytes);
        var sha = kind == "hash" ? new string('0', 64) :
            Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant();
        var files = new HashSet<string> { "HT/Content/Dialogue/Owned.uasset", "HT/Content/Text/Owned.uasset" };
        if (kind == "missing") files.Remove("HT/Content/Dialogue/Owned.uasset");
        CUE4Parse.UE4.AssetRegistry.FAssetRegistryState.LastArchive = null;
        var method = System.Reflection.Assembly.GetEntryAssembly()!.GetType("NteReader", true)!
            .GetMethod("NteDialogueSources", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        try {
            var result = (SortedSet<string>)method.Invoke(null, new object[] {
                this, typeof(FixtureProvider).Assembly, files, destination, sha, kind == "all-text",
                kind is "strict-eof" or "unconsumed" })!;
            var expected = kind == "all-text" ? files : new HashSet<string> { "HT/Content/Dialogue/Owned.uasset" };
            if (kind is not ("valid" or "all-text" or "strict-eof" or "legacy-unconsumed") || !result.SetEquals(expected) ||
                CUE4Parse.UE4.AssetRegistry.FAssetRegistryState.LastArchive?.Disposed != true) throw new InvalidDataException();
        }
        catch (System.Reflection.TargetInvocationException error) when
            ((kind is "hash" or "duplicate" or "escape" or "missing" or "empty" or "unconsumed") &&
             error.InnerException?.GetType().Name == "UnsupportedGameFormatException")
        {
            if (kind == "hash" && CUE4Parse.UE4.AssetRegistry.FAssetRegistryState.LastArchive is not null)
                throw new InvalidDataException("Registry authentication must precede parsing.");
            if (kind != "hash" && CUE4Parse.UE4.AssetRegistry.FAssetRegistryState.LastArchive?.Disposed != true)
                throw new InvalidDataException("A rejected registry must dispose its archive.");
        }
    }
    void VerifyOriginalTableRegistryFixture(Dictionary<string, JsonElement> marker)
    {
        if (!marker.TryGetValue("original_table_case", out var selected)) return;
        var kind = selected.GetString();
        object Claim(string name, string structure, string package = "/Game/FutureFolder/RenamedPackage", string assetClass = "DataTable") =>
            new { assetClass, packageName = package, assetName = name, tags = new Dictionary<string,string> { ["RowStructure"] = structure } };
        var assets = new List<object> {
            Claim("DifferentExport", "/Script/HTGame.BubbleVoiceMsgDetail"),
            Claim("SiblingExport", "/Script/HTGame.MediaFFmpegInfo"),
            Claim("NotSupported", "/Script/HTGame.UnimplementedFormat"),
            Claim("WrongClass", "/Script/HTGame.BubbleVoiceMsgDetail", assetClass: "Other") };
        if (kind == "duplicate") assets.Add(Claim("DifferentExport", "/Script/HTGame.BubbleVoiceMsgDetail"));
        else if (kind == "case-collision") assets.Add(Claim("differentexport", "/Script/HTGame.BubbleVoiceMsgDetail"));
        else if (kind == "escape") assets.Add(Claim("Escaped", "/Script/HTGame.BubbleVoiceMsgDetail", "/Game/../Escaped"));
        else if (kind == "bad-object") assets.Add(Claim("Bad/Object", "/Script/HTGame.BubbleVoiceMsgDetail"));
        else if (kind == "empty") assets.Clear();
        else if (kind is not ("valid" or "missing" or "hash")) throw new InvalidDataException();
        var destination = Path.Combine(install, "owned-original-table-registry"); Directory.CreateDirectory(destination);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(new { schema = "owned-registry-fixture-v1", assets });
        File.WriteAllBytes(Path.Combine(destination, "dialogue-registry.bin"), bytes);
        var sha = kind == "hash" ? new string('0',64) : Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant();
        var files = new HashSet<string> { "HT/Content/FutureFolder/RenamedPackage.uasset" };
        if (kind == "missing") files.Clear();
        var method = System.Reflection.Assembly.GetEntryAssembly()!.GetType("NteReader", true)!
            .GetMethod("NteOriginalTableClaims", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        CUE4Parse.UE4.AssetRegistry.FAssetRegistryState.LastArchive = null;
        try {
            var claims = ((System.Collections.IEnumerable)method.Invoke(null, new object[] {
                this, typeof(FixtureProvider).Assembly, files, destination, sha, false })!).Cast<object>().ToArray();
            string Read(object claim, string name) => (string)claim.GetType().GetProperty(name)!.GetValue(claim)!;
            if (kind != "valid" || claims.Length != 2 ||
                Read(claims[0], "object_name") != "DifferentExport" || Read(claims[0], "role") != "voice" ||
                Read(claims[1], "object_name") != "SiblingExport" || Read(claims[1], "role") != "movie" ||
                claims.Any(c => Read(c, "path") != files.Single()) ||
                CUE4Parse.UE4.AssetRegistry.FAssetRegistryState.LastArchive?.Disposed != true)
                throw new InvalidDataException("Original table discovery lost its exact export owners.");
        }
        catch (System.Reflection.TargetInvocationException error) when (kind != "valid" &&
            error.InnerException?.GetType().Name == "UnsupportedGameFormatException") {
            if (kind == "hash" && CUE4Parse.UE4.AssetRegistry.FAssetRegistryState.LastArchive is not null)
                throw new InvalidDataException("Authentication must precede table discovery.");
            if (kind != "hash" && CUE4Parse.UE4.AssetRegistry.FAssetRegistryState.LastArchive?.Disposed != true)
                throw new InvalidDataException("Original table discovery did not dispose its rejected source.");
        }
    }
    void VerifyFrozenCodecsFixture(Dictionary<string, JsonElement> marker)
    {
        if (!marker.TryGetValue("schema_codec_case", out var selected)) return;
        if (selected.GetString() != "complete") throw new InvalidDataException();
        var bridge = System.Reflection.Assembly.GetEntryAssembly()!.GetType("NteReader", true)!;
        var usageType = bridge.GetNestedType("SchemaUsageComparer", System.Reflection.BindingFlags.NonPublic)!;
        var usage = (StringComparer)Activator.CreateInstance(usageType, nonPublic: true)!;
        var enabled = usageType.GetField("Enabled", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!;
        enabled.SetValue(usage, true); usage.GetHashCode("OwnedPreviouslyRead"); enabled.SetValue(usage, false);
        var path = Path.Combine(install, "owned-codec-description");
        File.WriteAllText(path, "authored reflection fixture; not an actual usmap");
        var mappings = new CUE4Parse.MappingsProvider.Usmap.FileUsmapTypeMappingsProvider(path, usage);
        foreach (var name in new[] { "OwnedConcrete", "OwnedFallback", "OwnedConsumesArchive", "OwnedForeign",
                "OwnedPreviouslyRead", "OwnedUnknownPackage", "Owned-invalid-name" })
            mappings.MappingsForGame.Types.Add(name, new object());
        CUE4Parse.UE4.Assets.Objects.FScriptStruct.Created.Clear();
        var method = bridge.GetMethod("FrozenSchemaCodecs", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        var result = (Dictionary<string, string>)method.Invoke(null, new object[] {
            typeof(FixtureProvider).Assembly, mappings, this, usage })!;
        if (result.Count != 1 || result.GetValueOrDefault("OwnedConcrete") != "CUE4Parse.UE4.Assets.Objects.FOwnedZero" ||
            CUE4Parse.UE4.Assets.Objects.FScriptStruct.Created.Count != 5 ||
            CUE4Parse.UE4.Assets.Objects.FScriptStruct.Created.Contains("OwnedPreviouslyRead") ||
            CUE4Parse.UE4.Assets.Objects.FScriptStruct.Created.Contains("Owned-invalid-name"))
            throw new InvalidDataException("Concrete ZERO codec evidence did not preserve the actual reflection guards.");
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
