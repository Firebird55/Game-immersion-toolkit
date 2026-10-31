// Toolkit-owned glue for separately downloaded, checksum-verified UEExtractor.
// It only reads installed archives. No game data or archive metadata is bundled.
using System.Collections;
using System.Reflection;
using System.Text.Json;
using System.Security.Cryptography;

internal static class NteReader
{
    static int Main(string[] args)
    {
        var output = Console.Out;
        Console.SetOut(TextWriter.Null);
        Console.SetError(TextWriter.Null);
        try
        {
            if (args is ["--runtime-identity"])
            {
                var core = typeof(object).Assembly.Location;
                var local = Path.GetFullPath(core).StartsWith(Path.GetFullPath(AppContext.BaseDirectory), StringComparison.OrdinalIgnoreCase);
                Console.SetOut(output);
                Console.WriteLine(JsonSerializer.Serialize(new { schema = "proxy-nte-runtime-identity-v1",
                    runtime_version = Environment.Version.ToString(), runtime_origin = local ? "app-local" : "external",
                    corelib_sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(core))).ToLowerInvariant(),
                    game_execution_approved = false }));
                return local ? 0 : 2;
            }
            if (args.Length != 4 || args[0] is not ("index" or "voice" or "voices" or "inventory")) throw new ArgumentException();
            var install = Path.GetFullPath(args[1]);
            var tools = Path.GetFullPath(args[2]);
            var destination = Path.GetFullPath(args[3]);
            if (tools.Equals(install, StringComparison.OrdinalIgnoreCase) ||
                tools.StartsWith(install.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException();
            // The supplier assembly is fixed by the application inventory.
            // Its embedded managed codecs need no external DLLs or downloads.
            Directory.SetCurrentDirectory(tools);
            if (destination.Equals(install, StringComparison.OrdinalIgnoreCase) ||
                destination.StartsWith(install.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Choose an output folder outside the game installation");
            foreach (var immutable in new[] { tools, Path.GetFullPath(AppContext.BaseDirectory) })
                if (destination.Equals(immutable, StringComparison.OrdinalIgnoreCase) ||
                    destination.StartsWith(immutable.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) ||
                    immutable.StartsWith(destination.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new ArgumentException("Choose a separate private output folder");
            using var request = JsonDocument.Parse(Console.In.ReadToEnd());
            var voiceLanguage = request.RootElement.TryGetProperty("voice_language", out var requestedVoice) ? requestedVoice.GetString()! : "Chinese";
            if (voiceLanguage is not ("Chinese" or "English" or "Japanese" or "Korean")) throw new ArgumentException();
            var assembly = Assembly.LoadFrom(Path.Combine(tools, "UEExtractor.dll"));
            var key = request.RootElement.GetProperty("archive_metadata").GetString();
            if (key == null || key.Length != 66 || !key.StartsWith("0x") || !key[2..].All(Uri.IsHexDigit)) throw new ArgumentException();
            var provider = CreateProvider(assembly, install, key);
            try
            {
                provider.GetType().GetMethods().Single(m => m.Name == "Mount" && m.GetParameters().Length == 0).Invoke(provider, null);
                var save = provider.GetType().GetMethod("SaveAsset", [typeof(string)])!;
                Directory.CreateDirectory(destination);
                if (args[0] == "inventory")
                {
                    var files = (IEnumerable)provider.GetType().GetProperty("Files")!.GetValue(provider)!;
                    var names = new List<string>();
                    foreach (var pair in files)
                    {
                        var name = (string)pair.GetType().GetProperty("Key")!.GetValue(pair)!;
                        names.Add(name);
                    }
                    File.WriteAllText(Path.Combine(destination, "inventory.json"), JsonSerializer.Serialize(names.Distinct().Order()));
                }
                else if (args[0] is "voice" or "voices")
                {
                    var depots = args[0] == "voice" ? new[] { request.RootElement.GetProperty("depot").GetString()! }
                        : request.RootElement.GetProperty("depots").EnumerateArray().Select(x => x.GetString()!).ToArray();
                    if (depots.Length is < 1 or > 8) throw new ArgumentException();
                    var prefix = "HT/Content/WwiseAudio/Media/" + voiceLanguage + "/";
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
                    var localizationVersions = new Dictionary<string, int>();
                    var languages = request.RootElement.TryGetProperty("locales", out var requestedLocales)
                        ? requestedLocales.EnumerateArray().Select(x => x.GetString()!).Distinct().ToArray() : new[] { "en", "zh-CN" };
                    if (languages.Length is < 1 or > 40 || languages.Any(l => l.Length > 16 || !l.All(c => char.IsAsciiLetterOrDigit(c) || c == '-'))) throw new ArgumentException();
                    foreach (var language in languages)
                    {
                        var path = names.SingleOrDefault(n => n.EndsWith("/" + language + "/game.locres", StringComparison.OrdinalIgnoreCase));
                        if (path == null) continue;
                        var data = (byte[])save.Invoke(provider, [path])!;
                        // NTE's installed resources use the standard locres header
                        // with a game-specific encrypted string table. Fail with a
                        // stable code before a newer version becomes a partial index.
                        if (data.Length >= 17 && BitConverter.ToUInt32(data, 0) == 0x7574140E &&
                            BitConverter.ToUInt32(data, 4) == 0xFC034A67 &&
                            BitConverter.ToUInt32(data, 8) == 0x9D90154A &&
                            BitConverter.ToUInt32(data, 12) == 0x1B7F37C3)
                        {
                            localizationVersions[language] = data[16];
                            if (data[16] > 3) throw new UnsupportedGameFormatException();
                        }
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
                        // Shipped placeholder files do not constitute an
                        // installed text pack. Report them as unavailable.
                        if (rows.Count > 0) all[language] = rows;
                    }
                    File.WriteAllText(Path.Combine(destination, "localization.json"), JsonSerializer.Serialize(all));
                    File.WriteAllText(Path.Combine(destination, "reader-format.json"), JsonSerializer.Serialize(new { localizationVersions }));
                    var keys = all.Values.SelectMany(rows => rows).Select(row => "Play_Vo_" + row.key).ToHashSet(StringComparer.OrdinalIgnoreCase);
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
                    // An authored event can exist even when its requested dub's
                    // bank/media is absent. Never classify that absence as silence.
                    var declaredEvents = names.Where(n =>
                        (n.StartsWith("HT/Content/WwiseAudio/Events/", StringComparison.Ordinal) && n.EndsWith(".uasset")) ||
                        (n.StartsWith("HT/Content/WwiseAudio/Event/", StringComparison.Ordinal) && n.EndsWith(".bnk")))
                        .Select(Path.GetFileNameWithoutExtension).Where(n => keys.Contains(n!)).Distinct().Order().ToArray();
                    File.WriteAllText(Path.Combine(destination, "voice-events.json"), JsonSerializer.Serialize(declaredEvents));
                    foreach (var name in names.Where(n => n.StartsWith("HT/Content/WwiseAudio/Event/" + voiceLanguage + "/", StringComparison.Ordinal) &&
                        n.EndsWith(".bnk") && keys.Contains(Path.GetFileNameWithoutExtension(n))))
                        File.WriteAllBytes(Path.Combine(banks, Path.GetFileName(name)), (byte[])save.Invoke(provider, [name])!);
                    File.WriteAllText(Path.Combine(destination, "media.json"), JsonSerializer.Serialize(names.Where(n =>
                        n.StartsWith("HT/Content/WwiseAudio/Media/" + voiceLanguage + "/", StringComparison.Ordinal) && n.EndsWith(".wem"))));
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
            finally { (provider as IDisposable)?.Dispose(); }
            Console.SetOut(output); Console.WriteLine("Game reader completed"); return 0;
        }
        catch (UnsupportedGameFormatException) { Console.SetOut(output); Console.WriteLine("Unsupported NTE localization format; update the toolkit reader"); return 3; }
        catch { Console.SetOut(output); Console.WriteLine("Game reader failed; check the game files and reader version"); return 1; }
    }
    static object CreateProvider(Assembly supplier, string install, string key)
    {
        // Initialize only the embedded-assembly resolver. The supplier's
        // UnrealArchiveReader constructor invokes native-code downloaders;
        // constructing CUE4Parse directly preserves its managed Oodle/Zlib
        // defaults and keeps preparation independent of those suppliers.
        System.Runtime.CompilerServices.RuntimeHelpers.RunModuleConstructor(supplier.ManifestModule.ModuleHandle);
        var wrapper = supplier.GetType("UnrealArchiveReader", true)!;
        var providerType = wrapper.GetField("_provider", BindingFlags.NonPublic | BindingFlags.Instance)!.FieldType;
        var cue = providerType.Assembly;
        var game = Enum.Parse(cue.GetType("CUE4Parse.UE4.Versions.EGame", true)!, "GAME_NevernessToEverness");
        var versionType = cue.GetType("CUE4Parse.UE4.Versions.VersionContainer", true)!;
        var versionCtor = versionType.GetConstructors().Single();
        var versionArgs = versionCtor.GetParameters().Select(p => p.IsOptional ? Type.Missing : (object?)null).ToArray();
        versionArgs[0] = game;
        var version = versionCtor.Invoke(versionArgs);
        var providerCtor = providerType.GetConstructors().Single(c => {
            var parameters = c.GetParameters();
            return parameters.Length == 4 && parameters[0].ParameterType == typeof(string)
                && parameters[2].ParameterType == versionType;
        });
        var provider = providerCtor.Invoke([install, SearchOption.AllDirectories, version, StringComparer.OrdinalIgnoreCase]);
        try
        {
            providerType.GetMethod("Initialize")!.Invoke(provider, null);
            var submit = providerType.GetMethod("SubmitKey")!;
            var guid = Activator.CreateInstance(submit.GetParameters()[0].ParameterType)!;
            var aes = Activator.CreateInstance(submit.GetParameters()[1].ParameterType, key)!;
            submit.Invoke(provider, [guid, aes]);
            return provider;
        }
        catch
        {
            (provider as IDisposable)?.Dispose();
            throw;
        }
    }
    static object Property(object value, string name) => value.GetType().GetProperty(name)!.GetValue(value)!;
    static string TextKey(object value) => (string)value.GetType().GetField("Str")!.GetValue(value)!;
    sealed record LocalizedRow(string ns, string key, string value);
    sealed class UnsupportedGameFormatException : Exception { }
}
