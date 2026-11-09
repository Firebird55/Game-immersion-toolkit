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
