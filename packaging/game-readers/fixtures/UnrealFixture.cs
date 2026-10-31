// Authored stand-in for the reflected API. No upstream/game/decompression code.
using System.Text;
using System.Text.Json;
using CUE4Parse.UE4.Readers;

public sealed class UnrealArchiveReader : IDisposable
{
    public static bool EngineSpecified;
    public string AES_KEY = "";
    private readonly FixtureProvider _provider;
    public UnrealArchiveReader(string install, string game, string unused)
    {
        if (!EngineSpecified || game != "NevernessToEverness") throw new InvalidDataException();
        var marker = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(
            File.ReadAllBytes(Path.Combine(install, "owned-fixture.json")))!;
        if (marker["schema"].GetString() != "proxy-owned-nte-fixture-v1") throw new InvalidDataException();
        _provider = new FixtureProvider(marker["localization_version"].GetByte());
    }
    private void LoadAesKey(string install)
    {
        if (AES_KEY != "0x" + new string('0', 64)) throw new InvalidDataException();
        _provider.KeyWasSet = true;
    }
    public void Dispose() { }
}
public sealed class FixtureProvider
{
    public Dictionary<string, int> Files { get; } = new();
    public object Versions { get; } = new();
    public bool KeyWasSet;
    private bool mounted;
    private readonly byte version;
    private readonly Dictionary<string, string> texts = new() {
        ["en"] = "Owned NTE fixture", ["zh-CN"] = "中文测试", ["zh-Hant"] = "中文測試",
        ["ja"] = "日本語テスト", ["ko"] = "한국어 테스트" };
    public FixtureProvider(byte selectedVersion)
    {
        version = selectedVersion;
        GC.KeepAlive(new FByteArchive("owned", [], Versions));
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
    }
    public void Mount() { if (!KeyWasSet) throw new InvalidDataException(); mounted = true; }
    public byte[] SaveAsset(string name)
    {
        if (!mounted || !Files.ContainsKey(name)) throw new InvalidDataException();
        // Force a real load of the separately compiled fixture assembly before
        // the bridge enumerates AppDomain assemblies by its expected identity.
        _ = new FByteArchive("owned", [], Versions);
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
}
