// Toolkit-owned glue for separately downloaded, checksum-verified UEExtractor.
// It only reads installed archives. No game data or archive metadata is bundled.
using System.Collections;
using System.Reflection;
using System.Text.Json;

internal static class NteReader
{
    static int Main(string[] args)
    {
        var output = Console.Out;
        Console.SetOut(TextWriter.Null);
        Console.SetError(TextWriter.Null);
        try
        {
            if (args.Length != 4 || args[0] is not ("index" or "voice" or "voices")) throw new ArgumentException();
            var install = Path.GetFullPath(args[1]);
            var tools = Path.GetFullPath(args[2]);
            var destination = Path.GetFullPath(args[3]);
            if (tools.Equals(install, StringComparison.OrdinalIgnoreCase) ||
                tools.StartsWith(install.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException();
            // CUE4Parse locates its native dependencies in the working folder.
            // They were independently verified by setup before this process.
            Directory.SetCurrentDirectory(tools);
            if (destination.Equals(install, StringComparison.OrdinalIgnoreCase) ||
                destination.StartsWith(install.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Choose an output folder outside the game installation");
            using var request = JsonDocument.Parse(Console.In.ReadToEnd());
            var assembly = Assembly.LoadFrom(Path.Combine(tools, "UEExtractor.dll"));
            var key = request.RootElement.GetProperty("archive_metadata").GetString();
            if (key == null || key.Length != 66 || !key.StartsWith("0x") || !key[2..].All(Uri.IsHexDigit)) throw new ArgumentException();
            var readerType = assembly.GetType("UnrealArchiveReader", true)!;
            readerType.GetField("EngineSpecified")!.SetValue(null, true);
            var reader = Activator.CreateInstance(readerType, install, "NevernessToEverness", "")!;
            try
            {
                // Upstream 1.0.8.7 does not forward its AES argument to the provider.
                readerType.GetField("AES_KEY")!.SetValue(reader, key);
                readerType.GetMethod("LoadAesKey", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(reader, [install]);
                var provider = readerType.GetField("_provider", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(reader)!;
                provider.GetType().GetMethods().Single(m => m.Name == "Mount" && m.GetParameters().Length == 0).Invoke(provider, null);
                var save = provider.GetType().GetMethod("SaveAsset", [typeof(string)])!;
                Directory.CreateDirectory(destination);
                if (args[0] is "voice" or "voices")
                {
                    var depots = args[0] == "voice" ? new[] { request.RootElement.GetProperty("depot").GetString()! }
                        : request.RootElement.GetProperty("depots").EnumerateArray().Select(x => x.GetString()!).ToArray();
                    if (depots.Length is < 1 or > 8) throw new ArgumentException();
                    const string prefix = "HT/Content/WwiseAudio/Media/Chinese/";
                    foreach (var depot in depots)
                    if (!depot.StartsWith(prefix, StringComparison.Ordinal) || !depot.EndsWith(".wem") ||
                        !depot[prefix.Length..^4].All(char.IsAsciiDigit) || depot.Length <= prefix.Length + 4)
                        throw new ArgumentException();
                    for (int i = 0; i < depots.Length; i++)
                    {
                    var depot = depots[i];
                    var bytes = (byte[])save.Invoke(provider, [depot])!;
                    if (bytes.Length < 100 || bytes.Length > 64 * 1024 * 1024) throw new InvalidDataException();
                    File.WriteAllBytes(Path.Combine(destination, args[0] == "voice" ? "voice.wem" : $"{i}.wem"), bytes);
                    }
                }
                else
                {
                    var files = (IEnumerable)provider.GetType().GetProperty("Files")!.GetValue(provider)!;
                    var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    foreach (var pair in files) names.Add((string)pair.GetType().GetProperty("Key")!.GetValue(pair)!);
                    if (names.Count < 100) throw new InvalidDataException();
                    var cue = AppDomain.CurrentDomain.GetAssemblies().Single(a => a.GetName().Name == "CUE4Parse");
                    var archive = cue.GetType("CUE4Parse.UE4.Readers.FByteArchive", true)!;
                    var resource = cue.GetType("CUE4Parse.UE4.Localization.FTextLocalizationResource", true)!;
                    var versions = provider.GetType().GetProperty("Versions")!.GetValue(provider)!;
                    var all = new Dictionary<string, List<LocalizedRow>>();
                    foreach (var language in new[] { "en", "zh-CN" })
                    {
                        var path = names.Single(n => n.EndsWith("/" + language + "/game.locres", StringComparison.OrdinalIgnoreCase));
                        var data = (byte[])save.Invoke(provider, [path])!;
                        var ar = Activator.CreateInstance(archive, path, data, versions)!;
                        var parsed = Activator.CreateInstance(resource, ar)!;
                        var rows = new List<LocalizedRow>();
                        foreach (var nsPair in (IEnumerable)resource.GetField("Entries")!.GetValue(parsed)!)
                        {
                            var ns = TextKey(Property(nsPair, "Key"));
                            foreach (var pair in (IEnumerable)Property(nsPair, "Value"))
                            {
                                var entry = Property(pair, "Value");
                                var value = (string)entry.GetType().GetField("LocalizedString")!.GetValue(entry)!;
                                rows.Add(new(ns, TextKey(Property(pair, "Key")), value));
                            }
                        }
                        if (rows.Count == 0) throw new InvalidDataException();
                        all[language] = rows;
                    }
                    File.WriteAllText(Path.Combine(destination, "localization.json"), JsonSerializer.Serialize(all));
                    var keys = all["en"].Select(row => "Play_Vo_" + row.key).ToHashSet(StringComparer.OrdinalIgnoreCase);
                    if (request.RootElement.TryGetProperty("cinema_events", out var cinemaEvents))
                    {
                        if (cinemaEvents.GetArrayLength() > 2000) throw new InvalidDataException();
                        foreach (var value in cinemaEvents.EnumerateArray())
                        {
                            var name = value.GetString()!;
                            if (!name.StartsWith("Play_Vo_CG_") || !name.All(c => char.IsAsciiLetterOrDigit(c) || c == '_')) throw new InvalidDataException();
                            keys.Add(name);
                        }
                    }
                    var banks = Path.Combine(destination, "banks"); Directory.CreateDirectory(banks);
                    foreach (var name in names.Where(n => n.StartsWith("HT/Content/WwiseAudio/Event/Chinese/", StringComparison.Ordinal) &&
                        n.EndsWith(".bnk") && keys.Contains(Path.GetFileNameWithoutExtension(n))))
                        File.WriteAllBytes(Path.Combine(banks, Path.GetFileName(name)), (byte[])save.Invoke(provider, [name])!);
                    File.WriteAllText(Path.Combine(destination, "media.json"), JsonSerializer.Serialize(names.Where(n =>
                        n.StartsWith("HT/Content/WwiseAudio/Media/Chinese/", StringComparison.Ordinal) && n.EndsWith(".wem"))));
                    var subtitles = new Dictionary<string, string>();
                    foreach (var name in names.Where(n => n.StartsWith("HT/Content/SrtFile/FFMpeg/Story/") && n.EndsWith(".srt")))
                    {
                        var data = (byte[])save.Invoke(provider, [name])!;
                        if (data.Length > 512 * 1024) throw new InvalidDataException();
                        subtitles[name] = new System.Text.UTF8Encoding(false, true).GetString(data);
                    }
                    File.WriteAllText(Path.Combine(destination, "cinema-subtitles.json"), JsonSerializer.Serialize(subtitles));
                }
            }
            finally { (reader as IDisposable)?.Dispose(); }
            Console.SetOut(output); Console.WriteLine("Game reader completed"); return 0;
        }
        catch { Console.SetOut(output); Console.WriteLine("Game reader failed; check the game files and reader version"); return 1; }
    }
    static object Property(object value, string name) => value.GetType().GetProperty(name)!.GetValue(value)!;
    static string TextKey(object value) => (string)value.GetType().GetField("Str")!.GetValue(value)!;
    sealed record LocalizedRow(string ns, string key, string value);
}
