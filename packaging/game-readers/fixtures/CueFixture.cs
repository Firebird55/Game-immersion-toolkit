// Authored reflection fixture, NOT CUE4Parse code or a locres implementation.
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
