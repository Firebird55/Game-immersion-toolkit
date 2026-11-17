// Toolkit-owned glue for separately downloaded, checksum-verified UEExtractor.
// It reads installed archives or checked private publisher streams. No game data
// or archive metadata is bundled.
using System.Collections;
using System.Reflection;
using System.Text.Json;
using System.Security.Cryptography;
using System.Text.RegularExpressions;

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
            if (args.Length != 4 || args[0] is not ("index" or "voice" or "voices" or "inventory" or "publisher-tables" or "publisher-dialogue-inventory" or "wuwa-list" or "wuwa-extract")) throw new ArgumentException();
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
            var input = new char[64 * 1024 + 1];
            var count = Console.In.ReadBlock(input, 0, input.Length);
            if (count > 64 * 1024) throw new ArgumentException();
            using var request = JsonDocument.Parse(new string(input, 0, count));
            var voiceLanguage = request.RootElement.TryGetProperty("voice_language", out var requestedVoice) ? requestedVoice.GetString()! : "Chinese";
            if (voiceLanguage is not ("Chinese" or "English" or "Japanese" or "Korean")) throw new ArgumentException();
            var assembly = Assembly.LoadFrom(Path.Combine(tools, "UEExtractor.dll"));
            var wuwa = args[0].StartsWith("wuwa-", StringComparison.Ordinal);
            var metadata = request.RootElement.GetProperty("archive_metadata");
            var archiveKeys = wuwa ? metadata.EnumerateArray().Select(v => v.GetString()).ToArray() : [metadata.GetString()];
            if (archiveKeys.Length is < 1 or > 512 || archiveKeys.Any(key => key == null || key.Length != 66 ||
                !key.StartsWith("0x") || !key[2..].All(Uri.IsHexDigit))) throw new ArgumentException();
            var filter = wuwa ? WuwaFilter(request.RootElement.GetProperty("filter").GetString()!, args[0] == "wuwa-list") : null;
            var publisher = args[0] is "publisher-tables" or "publisher-dialogue-inventory" || args[0] == "inventory" &&
                request.RootElement.TryGetProperty("publisher_streams", out _);
            var provider = CreateProvider(assembly, install, wuwa ? "GAME_WutheringWaves" : "GAME_NevernessToEverness", archiveKeys!,
                publisher ? request.RootElement.GetProperty("publisher_streams") : null);
            try
            {
                provider.GetType().GetMethods().Single(m => m.Name == "Mount" && m.GetParameters().Length == 0).Invoke(provider, null);
                var save = provider.GetType().GetMethod("SaveAsset", [typeof(string)])!;
                Directory.CreateDirectory(destination);
                if (wuwa)
                    ReadWuwa(provider, save, destination, filter!, args[0] == "wuwa-list");
                else if (args[0] == "publisher-dialogue-inventory")
                {
                    var names = ((IEnumerable)Property(provider, "Files")).Cast<object>()
                        .Select(pair => (string)Property(pair, "Key")).ToHashSet(StringComparer.OrdinalIgnoreCase);
                    var cue = AppDomain.CurrentDomain.GetAssemblies().Single(a => a.GetName().Name == "CUE4Parse");
                    var sha = request.RootElement.GetProperty("dialogue_registry_sha256").GetString();
                    var nonce = request.RootElement.GetProperty("inventory_nonce").GetString();
                    if (nonce is null || !Regex.IsMatch(nonce, "\\A[0-9a-f]{32}\\z")) throw new ArgumentException();
                    var index = Property(provider, "Files");
                    var sources = NteDialogueSources(provider, cue, names, destination, sha, includeStringTables: true);
                    var packages = new SortedDictionary<string, long>(StringComparer.Ordinal);
                    long total = 0;
                    foreach (var name in sources)
                    {
                        var file = index.GetType().GetProperty("Item")!.GetValue(index, [name])!;
                        var size = Convert.ToInt64(Property(file, "Size")); total += size;
                        if (size is < 1 or > 4*1024*1024 || total > 128*1024*1024) throw new UnsupportedGameFormatException();
                        packages.Add(name, size);
                    }
                    File.WriteAllText(Path.Combine(destination, "dialogue-inventory.json"), JsonSerializer.Serialize(new {
                        schema="nte-original-dialogue-inventory-v1", complete=true, registry_sha256=sha, nonce=nonce,
                        package_count=packages.Count, packages=packages }));
                }
                else if (args[0] == "publisher-tables")
                {
                    var files = (IEnumerable)Property(provider, "Files");
                    var names = files.Cast<object>().Select(pair => (string)Property(pair, "Key"))
                        .ToHashSet(StringComparer.OrdinalIgnoreCase);
                    var cue = AppDomain.CurrentDomain.GetAssemblies().Single(a => a.GetName().Name == "CUE4Parse");
                    var events = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    string? usageNonce = null;
                    if (request.RootElement.TryGetProperty("capture_schema_usage", out var captureUsage) && captureUsage.GetBoolean())
                    {
                        usageNonce = request.RootElement.GetProperty("schema_usage_nonce").GetString();
                        if (usageNonce is null || !Regex.IsMatch(usageNonce, "\\A[0-9a-f]{32}\\z")) throw new ArgumentException();
                    }
                    ReadNteDialogueTables(provider, cue, names, destination, events, readMovies: true,
                        expectedSchema: request.RootElement.GetProperty("type_schema_sha256").GetString(), usageNonce: usageNonce,
                        readGraphs: request.RootElement.TryGetProperty("capture_dialogue_graphs", out var graphs) && graphs.GetBoolean(),
                        registrySha: request.RootElement.TryGetProperty("dialogue_registry_sha256", out var registrySha) ? registrySha.GetString() : null);
                    File.WriteAllText(Path.Combine(destination, "voice-events.json"), JsonSerializer.Serialize(events.Order()));
                }
                else if (args[0] == "inventory")
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
                    if (request.RootElement.TryGetProperty("read_dialogue_tables", out var readTables) && readTables.GetBoolean())
                        ReadNteDialogueTables(provider, cue, names, destination, keys, readMovies: true);
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
    static void ReadNteDialogueTables(object provider, Assembly cue, HashSet<string> files, string destination,
        HashSet<string> voiceEvents, bool readMovies = false, string? expectedSchema = null, string? usageNonce = null,
        bool readGraphs = false, string? registrySha = null)
    {
        expectedSchema ??= "7651a4e56f79b2c6c9d7bde31a8dadbfc929b2e923691461c6970ce0bdb0ff58";
        var profile = Path.Combine(destination, "dialogue.usmap");
        if (!Regex.IsMatch(expectedSchema, "\\A[0-9a-fA-F]{64}\\z") || new FileInfo(profile).Length > 8 * 1024 * 1024 ||
            !Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(profile))).Equals(
                expectedSchema, StringComparison.OrdinalIgnoreCase))
            throw new UnsupportedGameFormatException();
        var type = cue.GetType("CUE4Parse.MappingsProvider.Usmap.FileUsmapTypeMappingsProvider", true)!;
        var usage = usageNonce is null ? null : new SchemaUsageComparer();
        using var schemaLog = usage is null ? null : SchemaParseLog.Capture();
        var mappings = Activator.CreateInstance(type, [profile, (StringComparer?)usage ?? StringComparer.Ordinal])!;
        provider.GetType().GetProperty("MappingsContainer")!.SetValue(provider, mappings);
        if (usage is not null)
        {
            _ = Property(mappings, "MappingsForGame");
            usage.Names.Clear();
            usage.Enabled = true;
        }
        var exportClasses = new Dictionary<string, string>(StringComparer.Ordinal);
        var index = Property(provider, "Files");
        var load = provider.GetType().GetMethods().Single(m => m.Name == "LoadPackage" &&
            m.GetParameters().Length == 1 && m.GetParameters()[0].ParameterType.Name == "GameFile");
        var converter = AppDomain.CurrentDomain.GetAssemblies().Single(a => a.GetName().Name == "Newtonsoft.Json")
            .GetType("Newtonsoft.Json.JsonConvert", true)!.GetMethod("SerializeObject", [typeof(object)])!;
        object ExportNamed(string name, string objectName)
        {
            var file = index.GetType().GetProperty("Item")!.GetValue(index, [name])!;
            var size = Convert.ToInt64(Property(file, "Size"));
            if (size is < 0 or > 512 * 1024 * 1024) throw new UnsupportedGameFormatException();
            var package = load.Invoke(provider, [file])!;
            var slot = (int)package.GetType().GetMethod("GetExportIndex")!.Invoke(package,
                [objectName, StringComparison.Ordinal])!;
            if (slot < 0) throw new UnsupportedGameFormatException();
            var export = Property(((Array)Property(package, "ExportsLazy")).GetValue(slot)!, "Value");
            if (usage is not null)
            {
                var implementation = export.GetType().FullName!;
                var exportType = Property(export, "ExportType").ToString()!;
                if (implementation.StartsWith("CUE4Parse.UE4.Assets.Exports.", StringComparison.Ordinal) &&
                    export.GetType().Name == "U" + exportType)
                {
                    if (exportClasses.TryGetValue(exportType, out var known) && known != implementation)
                        throw new UnsupportedGameFormatException();
                    exportClasses[exportType] = implementation;
                }
            }
            return export;
        }
        object Export(string name) => ExportNamed(name, Path.GetFileNameWithoutExtension(name));
        IEnumerable<(string, JsonElement)> Rows(string name)
        {
            var table = Export(name);
            if (table.GetType().Name != "UDataTable") throw new UnsupportedGameFormatException();
            var rows = (IDictionary)Property(table, "RowMap");
            if (rows.Count > 100_000) throw new UnsupportedGameFormatException();
            foreach (DictionaryEntry row in rows)
            {
                var key = row.Key.ToString()!;
                if (key.Length is 0 or > 512) throw new UnsupportedGameFormatException();
                var json = (string)converter.Invoke(null, [row.Value])!;
                using var record = JsonDocument.Parse(json);
                yield return (key, record.RootElement);
            }
        }
        var aliases = new Dictionary<string, HashSet<string>>(StringComparer.OrdinalIgnoreCase);
        var tables = files.Where(n => n.StartsWith("HT/Content/DataTable/", StringComparison.Ordinal) &&
            Regex.IsMatch(Path.GetFileName(n), @"^(DialogSoundTable|BubbleVoiceMsgTable)(_[A-Za-z0-9_]+)?\.uasset$")).Order().ToArray();
        if (tables.Length > 128 || !tables.Contains("HT/Content/DataTable/DialogSoundTable.uasset")) throw new UnsupportedGameFormatException();
        foreach (var name in tables)
        {
            foreach (var (identity, record) in Rows(name))
            {
                var key = identity.ToLowerInvariant();
                if (aliases.Count > 250_000 || !record.TryGetProperty("DialogSoundEvent", out var sound) ||
                    !sound.TryGetProperty("AssetPathName", out var path) || path.ValueKind != JsonValueKind.String)
                    throw new UnsupportedGameFormatException();
                var asset = path.GetString()!;
                var match = Regex.Match(asset, @"^/Game/WwiseAudio/Events/(?:[\w/-]+/)?(Play_Vo_[A-Za-z0-9_]+)\.\1$",
                    RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
                // An unsupported sound or conflicting table must block the conventional name fallback.
                var value = match.Success ? match.Groups[1].Value.ToLowerInvariant() : asset.Length == 0 ? "" : "?";
                if (!aliases.TryGetValue(key, out var choices)) aliases[key] = choices = new(StringComparer.Ordinal);
                choices.Add(value);
                if (match.Success) voiceEvents.Add(match.Groups[1].Value);
            }
        }
        File.WriteAllText(Path.Combine(destination, "dialogue-events.json"), JsonSerializer.Serialize(aliases));
        ReadNteSequences(files, Rows, Export, voiceEvents, destination);
        if (readMovies)
        {
            var movies = new Dictionary<string, object>();
            foreach (var name in new[] { "DT_MediaFFmpegInfo", "DT_MediaFFmpegInfo_Quest" })
            {
                var path = "HT/Content/DataTable/Skill/" + name + ".uasset";
                if (!files.Contains(path)) continue;
                var rows = Rows(path).ToDictionary(row => row.Item1, row => row.Item2.Clone(), StringComparer.Ordinal);
                movies[name + ".json"] = new[] { new { Type = "DataTable", Rows = rows } };
                foreach (var row in rows.Values)
                {
                    if (!row.TryGetProperty("PlayVoice", out var voice) || voice.ValueKind != JsonValueKind.Object ||
                        !voice.TryGetProperty("AssetPathName", out var asset) || asset.ValueKind != JsonValueKind.String)
                        continue;
                    var voiceEvent = NteCinematicVoice(asset.GetString()!);
                    if (voiceEvent is not null) voiceEvents.Add(voiceEvent);
                }
            }
            movies["StringTableNamespaces.json"] = ReadNteMovieNamespaces(files, Rows, (path, name) =>
            {
                var table = ExportNamed(path, name);
                if (table.GetType().Name != "UStringTable") throw new UnsupportedGameFormatException();
                var json = (string)converter.Invoke(null, [table])!;
                if (json.Length > 16 * 1024 * 1024) throw new UnsupportedGameFormatException();
                using var parsed = JsonDocument.Parse(json);
                return parsed.RootElement.Clone();
            });
            File.WriteAllText(Path.Combine(destination, "movie-tables.json"), JsonSerializer.Serialize(movies));
        }
        if (readGraphs)
        {
            if (usage is null) throw new UnsupportedGameFormatException();
            ReadNteDialogueGraphs(provider, cue, files, destination, index, load, converter, ExportNamed, registrySha);
        }
        if (usage is not null)
        {
            if (schemaLog!.HasFailures) throw new UnsupportedGameFormatException();
            // Probes belong to the frozen codec contract, not extraction
            // lookups or parse-failure evidence from original packages.
            usage.Enabled = false;
            schemaLog.Dispose();
            var codecs = FrozenSchemaCodecs(cue, mappings, provider, usage);
            WriteSchemaUsage(destination, expectedSchema, usageNonce!, usage, exportClasses, schemaLog, codecs);
        }
    }

    static SortedSet<string> NteDialogueSources(object provider, Assembly cue, HashSet<string> files,
        string destination, string? registrySha, bool includeStringTables = false)
    {
        // AssetRegistry is a checked original pak member; publisher package
        // streams expose IoStore assets only. The caller stages this member.
        var registryPath = Path.Combine(destination, "dialogue-registry.bin");
        if (registrySha is null || !Regex.IsMatch(registrySha, "\\A[0-9a-f]{64}\\z") ||
            new FileInfo(registryPath).Length is < 1 or > 256*1024*1024) throw new UnsupportedGameFormatException();
        var bytes = File.ReadAllBytes(registryPath);
        if (Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() != registrySha) throw new UnsupportedGameFormatException();
        using var archive = (IDisposable)Activator.CreateInstance(cue.GetType("CUE4Parse.UE4.Readers.FByteArchive", true)!,
            [registryPath, bytes, Property(provider, "Versions")])!;
        var registry = Activator.CreateInstance(cue.GetType("CUE4Parse.UE4.AssetRegistry.FAssetRegistryState", true)!, [archive])!;
        var entries = (Array)registry.GetType().GetField("PreallocatedAssetDataBuffers")!.GetValue(registry)!;
        if (entries.Length is < 1 or > 2_000_000) throw new UnsupportedGameFormatException();
        var sources = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var item in entries)
        {
            object Field(string name) => item!.GetType().GetField(name)!.GetValue(item)!;
            var assetClass = Field("AssetClass").ToString();
            if (assetClass != "DlgDialogue" && !(includeStringTables && assetClass == "StringTable")) continue;
            var package = Field("PackageName").ToString()!;
            if (!package.StartsWith("/Game/", StringComparison.Ordinal) || package.Contains('\\') ||
                package[6..].Split('/').Any(p => p is "" or "." or "..")) throw new UnsupportedGameFormatException();
            var path = "HT/Content/" + package[6..] + ".uasset";
            if (!files.Contains(path) || !sources.Add(path) || sources.Count > 8192) throw new UnsupportedGameFormatException();
        }
        if (sources.Count == 0) throw new UnsupportedGameFormatException();
        return sources;
    }

    static void ReadNteDialogueGraphs(object provider, Assembly cue, HashSet<string> files, string destination,
        object index, MethodInfo load, MethodInfo converter, Func<string, string, object> exportNamed, string? registrySha)
    {
        var sources = NteDialogueSources(provider, cue, files, destination, registrySha);
        long totalSize = 0;
        var namespaces = new SortedDictionary<string, string?>(StringComparer.Ordinal);
        var tableReferences = new SortedSet<string>(StringComparer.Ordinal);
        void References(JsonElement value)
        {
            if (value.ValueKind == JsonValueKind.Object)
            {
                if (value.TryGetProperty("TableId", out var table) && table.ValueKind == JsonValueKind.String)
                {
                    var reference = table.GetString()!;
                    if (reference.Length > 1024 || tableReferences.Count > 4096) throw new UnsupportedGameFormatException();
                    tableReferences.Add(reference);
                }
                foreach (var property in value.EnumerateObject()) References(property.Value);
            }
            else if (value.ValueKind == JsonValueKind.Array)
                foreach (var child in value.EnumerateArray()) References(child);
        }
        var pathOut = Path.Combine(destination, "dialogue-graphs.json");
        using var output = new FileStream(pathOut, FileMode.CreateNew);
        using var writer = new Utf8JsonWriter(output);
        writer.WriteStartObject(); writer.WriteString("schema", "nte-original-dialogue-graphs-v1");
        writer.WriteNumber("graph_count", sources.Count); writer.WriteStartArray("graphs");
        int totalExports = 0;
        foreach (var path in sources)
        {
            var file = index.GetType().GetProperty("Item")!.GetValue(index, [path])!;
            var size = Convert.ToInt64(Property(file, "Size")); totalSize += size;
            if (size is < 1 or > 4*1024*1024 || totalSize > 128*1024*1024) throw new UnsupportedGameFormatException();
            var package = load.Invoke(provider, [file])!;
            var exports = (Array)Property(package, "ExportsLazy"); totalExports += exports.Length;
            if (exports.Length is < 1 or > 4096 || totalExports > 200_000) throw new UnsupportedGameFormatException();
            writer.WriteStartObject(); writer.WriteString("asset", path); writer.WriteStartArray("exports");
            foreach (var slot in exports)
            {
                var json = (string)converter.Invoke(null, [Property(slot!, "Value")])!;
                if (json.Length > 16*1024*1024) throw new UnsupportedGameFormatException();
                using var parsed = JsonDocument.Parse(json);
                References(parsed.RootElement); parsed.RootElement.WriteTo(writer);
            }
            writer.WriteEndArray(); writer.WriteEndObject(); writer.Flush();
            if (output.Position > 256*1024*1024) throw new UnsupportedGameFormatException();
        }
        writer.WriteEndArray();
        foreach (var reference in tableReferences)
        {
            namespaces[reference] = null;
            var match = Regex.Match(reference, @"^/Game/([\w/-]+)\.([A-Za-z0-9_]+)$");
            if (!match.Success || match.Groups[1].Value.Split('/').Any(p => p is "" or "." or ".."))
                continue; // Preserve invalid authored references as unresolved.
            var path = "HT/Content/" + match.Groups[1].Value + ".uasset";
            if (!files.Contains(path)) continue;
            var original = exportNamed(path, match.Groups[2].Value);
            if (original.GetType().Name != "UStringTable") throw new UnsupportedGameFormatException();
            var json = (string)converter.Invoke(null, [original])!;
            if (json.Length > 16*1024*1024) throw new UnsupportedGameFormatException();
            using var parsed = JsonDocument.Parse(json);
            var ns = parsed.RootElement.GetProperty("StringTable").GetProperty("TableNamespace").GetString()!;
            if (string.IsNullOrEmpty(ns)) continue;
            if (ns.Length > 512 || ns.Any(char.IsControl)) throw new UnsupportedGameFormatException();
            namespaces[reference] = ns;
        }
        writer.WritePropertyName("namespaces"); JsonSerializer.Serialize(writer, namespaces);
        writer.WriteEndObject(); writer.Flush();
        if (output.Position > 256*1024*1024) throw new UnsupportedGameFormatException();
    }

    static Dictionary<string, string?> ReadNteMovieNamespaces(HashSet<string> files,
        Func<string, IEnumerable<(string, JsonElement)>> rows, Func<string, string, JsonElement> owner)
    {
        const string registry = "HT/Content/DataTable/DT_TextTable.uasset";
        var result = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        var owners = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (!files.Contains(registry)) return result;
        int count = 0;
        foreach (var (alias, row) in rows(registry))
        {
            if (++count > 4096 || alias.Length is 0 or > 512 || alias.Any(char.IsControl) ||
                row.ValueKind != JsonValueKind.Object || !row.TryGetProperty("TextTable", out var table) || table.ValueKind != JsonValueKind.Object ||
                !table.TryGetProperty("AssetPathName", out var asset) || asset.ValueKind != JsonValueKind.String ||
                !table.TryGetProperty("SubPathString", out var subpath) || subpath.ValueKind != JsonValueKind.String || subpath.GetString() != "")
                throw new UnsupportedGameFormatException();
            string? ns = null;
            var reference = asset.GetString()!;
            if (reference is not ("" or "None"))
            {
                var match = Regex.Match(reference, @"^/Game/([\w/-]+)\.([A-Za-z0-9_]+)$");
                if (!match.Success || match.Groups[1].Value.Split('/').Any(part => part is "" or "." or ".."))
                    throw new UnsupportedGameFormatException();
                var path = "HT/Content/" + match.Groups[1].Value + ".uasset";
                if (files.Contains(path))
                {
                    var name = match.Groups[2].Value;
                    var identity = path + "\0" + name;
                    if (owners.TryGetValue(identity, out var known)) ns = known;
                    else
                    {
                    var original = owner(path, name);
                    if (original.ValueKind != JsonValueKind.Object ||
                        !original.TryGetProperty("Type", out var kind) || kind.ValueKind != JsonValueKind.String || kind.GetString() != "StringTable" ||
                        !original.TryGetProperty("StringTable", out var content) || content.ValueKind != JsonValueKind.Object ||
                        !content.TryGetProperty("TableNamespace", out var value) || value.ValueKind != JsonValueKind.String)
                        throw new UnsupportedGameFormatException();
                    ns = value.GetString();
                    if (string.IsNullOrEmpty(ns) || ns.Length > 512 || ns.Any(char.IsControl))
                        throw new UnsupportedGameFormatException();
                    owners[identity] = ns;
                    }
                }
            }
            // Conflicting FName aliases or missing owners must never select a
            // table merely because its asset basename resembles the alias.
            if (result.TryGetValue(alias, out var previous))
                result[alias] = previous == ns ? ns : null;
            else result[alias] = ns;
        }
        return result;
    }

    static string? NteCinematicVoice(string path)
    {
        // The authored CG reference establishes ownership; released events do
        // not all repeat CG in their object names.
        var match = Regex.Match(path, @"^/Game/WwiseAudio/Events/CG/[\w/-]+/(Play_Vo_[A-Za-z0-9_]+)\.\1$");
        return match.Success ? match.Groups[1].Value : null;
    }

    static void ReadNteSequences(HashSet<string> files, Func<string, IEnumerable<(string, JsonElement)>> rows,
        Func<string, object> export, HashSet<string> voiceEvents, string destination)
    {
        const string folder = "HT/Content/DataTable/";
        var events = new Dictionary<string, HashSet<string>>(StringComparer.Ordinal);
        foreach (var name in new[] {"DT_StorySequenceData", "DT_StorySequenceData_World"})
        {
            if (!files.Contains(folder + name + ".uasset")) continue;
            foreach (var (_, row) in rows(folder + name + ".uasset"))
            foreach (var info in row.GetProperty("SequenceInfo").EnumerateArray())
            {
                // Optional slots can be empty in released sequence tables.
                if (info.ValueKind == JsonValueKind.Null) continue;
                if (info.ValueKind != JsonValueKind.Object) throw new UnsupportedGameFormatException();
                if (!info.TryGetProperty("CaptionsID", out var id)) continue;
                var group = id.GetString()!;
                if (string.IsNullOrEmpty(group) || group == "None") continue;
                var settings = info.GetProperty("Settings");
                var path = info.GetProperty("VoiceSource").GetProperty("AssetPathName").GetString()!;
                var voiceEvent = NteCinematicVoice(path);
                var regularClock = settings.GetProperty("PlayRate").GetDouble() == 1 &&
                    settings.GetProperty("StartTime").GetDouble() == 0 && !settings.GetProperty("bRandomStartTime").GetBoolean();
                if (!events.TryGetValue(group, out var names)) events[group] = names = new(StringComparer.Ordinal);
                names.Add(regularClock && voiceEvent is not null ? voiceEvent : "");
                if (regularClock && voiceEvent is not null) voiceEvents.Add(voiceEvent);
            }
        }
        const string captionsFile = folder + "DT_VoiceCaptionDataTable.uasset";
        if (!files.Contains(captionsFile)) return;
        var strings = new Dictionary<string, object>();
        var groups = new Dictionary<string, List<object>>();
        foreach (var (group, row) in rows(captionsFile))
        {
            if (!events.TryGetValue(group, out var names) || names.Count != 1 || names.Contains("")) continue;
            groups[group] = new List<object>();
            foreach (var cue in row.GetProperty("Captions").EnumerateArray())
            {
                var text = cue.GetProperty("Text");
                var key = text.TryGetProperty("Key", out var textKey) ? textKey.GetString() : null;
                var owner = text.TryGetProperty("TableId", out var tableRef) ? tableRef.GetString() : null;
                var match = Regex.Match(owner ?? "", @"^/Game/(Text/(?:[A-Za-z0-9_]+/)*(ST_[A-Za-z0-9_]+))\.\2$");
                string? ns = null;
                var assetPath = "HT/Content/" + match.Groups[1].Value + ".uasset";
                if (!string.IsNullOrEmpty(key) && match.Success && files.Contains(assetPath))
                {
                    if (!strings.TryGetValue(assetPath, out var stringTable))
                        strings[assetPath] = stringTable = Property(export(assetPath), "StringTable");
                    var entries = (IDictionary)stringTable.GetType().GetField("KeysToEntries")!.GetValue(stringTable)!;
                    if (entries.Contains(key)) ns = (string)stringTable.GetType().GetField("TableNamespace")!.GetValue(stringTable)!;
                }
                // Keep even unowned cue intervals so an overlapping line cannot be exported as clean speech.
                groups[group].Add(new { ns, key, start_ms = cue.GetProperty("StartTime").GetInt32(),
                    end_ms = cue.GetProperty("EndTime").GetInt32(), starts = cue.GetProperty("CultureStartTimes").Clone(),
                    ends = cue.GetProperty("CultureEndTimes").Clone() });
            }
        }
        File.WriteAllText(Path.Combine(destination, "sequence-cues.json"), JsonSerializer.Serialize(new { events, groups }));
    }
    static object CreateProvider(Assembly supplier, string install, string gameName, string[] keys, JsonElement? publisherStreams = null)
    {
        // Initialize only the embedded-assembly resolver. The supplier's
        // UnrealArchiveReader constructor invokes native-code downloaders;
        // constructing CUE4Parse directly preserves its managed Oodle/Zlib
        // defaults and keeps preparation independent of those suppliers.
        System.Runtime.CompilerServices.RuntimeHelpers.RunModuleConstructor(supplier.ManifestModule.ModuleHandle);
        var wrapper = supplier.GetType("UnrealArchiveReader", true)!;
        var providerType = wrapper.GetField("_provider", BindingFlags.NonPublic | BindingFlags.Instance)!.FieldType;
        var cue = providerType.Assembly;
        var game = Enum.Parse(cue.GetType("CUE4Parse.UE4.Versions.EGame", true)!, gameName);
        var versionType = cue.GetType("CUE4Parse.UE4.Versions.VersionContainer", true)!;
        var versionCtor = versionType.GetConstructors().Single();
        var versionArgs = versionCtor.GetParameters().Select(p => p.IsOptional ? Type.Missing : (object?)null).ToArray();
        versionArgs[0] = game;
        var version = versionCtor.Invoke(versionArgs);
        if (publisherStreams.HasValue)
            providerType = cue.GetType("CUE4Parse.FileProvider.StreamedFileProvider", true)!;
        var providerCtor = providerType.GetConstructors().Single(c => {
            var parameters = c.GetParameters();
            return publisherStreams.HasValue
                ? parameters.Length == 3 && parameters[0].ParameterType == typeof(string) && parameters[1].ParameterType == versionType
                : parameters.Length == 4 && parameters[0].ParameterType == typeof(string) && parameters[2].ParameterType == versionType;
        });
        var provider = providerCtor.Invoke(publisherStreams.HasValue
            ? ["HT", version, StringComparer.OrdinalIgnoreCase]
            : [install, SearchOption.AllDirectories, version, StringComparer.OrdinalIgnoreCase]);
        try
        {
            providerType.GetMethod("Initialize")!.Invoke(provider, null);
            if (publisherStreams.HasValue) RegisterPublisherStreams(provider, publisherStreams.Value);
            var submit = providerType.GetMethod("SubmitKey")!;
            var guid = Activator.CreateInstance(submit.GetParameters()[0].ParameterType)!;
            foreach (var key in keys)
            {
                var aes = Activator.CreateInstance(submit.GetParameters()[1].ParameterType, key)!;
                submit.Invoke(provider, [guid, aes]);
            }
            // Downloaded patches can declare a nonzero archive identifier.
            // Snapshot the remaining identifiers before submission mutates the
            // unloaded collection; each still needs its installed-version key.
            var remaining = ((IEnumerable)Property(provider, "UnloadedVfs")).Cast<object>()
                .Select(archive => Property(archive, "EncryptionKeyGuid")).Distinct().ToArray();
            foreach (var archiveGuid in remaining)
                foreach (var key in keys)
                    submit.Invoke(provider, [archiveGuid,
                        Activator.CreateInstance(submit.GetParameters()[1].ParameterType, key)!]);
            return provider;
        }
        catch
        {
            (provider as IDisposable)?.Dispose();
            throw;
        }
    }

    static void RegisterPublisherStreams(object provider, JsonElement streams)
    {
        if (streams.ValueKind != JsonValueKind.Array || streams.GetArrayLength() is < 1 or > 128)
            throw new UnsupportedGameFormatException();
        var register = provider.GetType().GetMethods().Single(m => m.Name == "RegisterVfs" &&
            m.GetParameters().Length == 3 && m.GetParameters()[0].ParameterType == typeof(string) &&
            m.GetParameters()[1].ParameterType == typeof(Stream[]));
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        string? server = null;
        var number = 0;
        foreach (var item in streams.EnumerateArray())
        {
            var name = item.GetProperty("name").GetString()!;
            if (name.Length > 160 || !Regex.IsMatch(name, @"^[A-Za-z0-9_/-]+\.utoc$") ||
                name.StartsWith('/') || name.Contains("..") || name.Contains("//") || !seen.Add(name) ||
                (number == 0) != (Path.GetFileName(name) == "global.utoc")) throw new UnsupportedGameFormatException();
            var tocLength = item.GetProperty("toc_size").GetInt64();
            var ucasLength = item.GetProperty("ucas_size").GetInt64();
            if (tocLength is <= 0 or > 64 * 1024 * 1024 || ucasLength is <= 0 or > (1L << 40))
                throw new UnsupportedGameFormatException();
            var toc = new PublisherRangeStream(item.GetProperty("toc_url").GetString()!, tocLength);
            var ucas = new PublisherRangeStream(item.GetProperty("ucas_url").GetString()!, ucasLength);
            server ??= toc.Server;
            if (toc.Server != server || ucas.Server != server) throw new UnsupportedGameFormatException();
            var before = ((IEnumerable)Property(provider, "UnloadedVfs")).Cast<object>().Count() +
                         ((IEnumerable)Property(provider, "MountedVfs")).Cast<object>().Count();
            try
            {
                register.Invoke(provider, [name, new Stream[] {toc, ucas}, null]);
                var after = ((IEnumerable)Property(provider, "UnloadedVfs")).Cast<object>().Count() +
                            ((IEnumerable)Property(provider, "MountedVfs")).Cast<object>().Count();
                if (after != before + 1) throw new UnsupportedGameFormatException();
            }
            catch { toc.Dispose(); ucas.Dispose(); throw; }
            number++;
        }
    }

    sealed class PublisherRangeStream : Stream, ICloneable
    {
        static readonly HttpClient Client = new(new SocketsHttpHandler {
            AllowAutoRedirect = false, UseProxy = false, MaxConnectionsPerServer = 4 })
            { Timeout = TimeSpan.FromSeconds(120) };
        readonly string endpoint;
        readonly long length;
        long position;
        bool disposed;
        public string Server { get; }
        public PublisherRangeStream(string endpoint, long length)
        {
            if (!Uri.TryCreate(endpoint, UriKind.Absolute, out var uri) || uri.Scheme != "http" ||
                uri.Host != "127.0.0.1" || uri.Port is < 1 or > 65535 || uri.UserInfo.Length != 0 ||
                uri.Query.Length != 0 || uri.Fragment.Length != 0 ||
                !Regex.IsMatch(uri.AbsolutePath, @"^/[A-Za-z0-9_-]{43}/[a-f0-9]{32}$"))
                throw new UnsupportedGameFormatException();
            this.endpoint = endpoint;
            this.length = length;
            Server = uri.GetLeftPart(UriPartial.Authority) + uri.AbsolutePath[..uri.AbsolutePath.LastIndexOf('/')];
        }
        public override bool CanRead => !disposed;
        public override bool CanSeek => !disposed;
        public override bool CanWrite => false;
        public override long Length => length;
        public override long Position { get => position; set => Seek(value, SeekOrigin.Begin); }
        public override int Read(byte[] buffer, int offset, int count)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            ArgumentNullException.ThrowIfNull(buffer);
            if (offset < 0 || count < 0 || offset > buffer.Length - count) throw new ArgumentOutOfRangeException();
            var amount = (int)Math.Min(count, length - position);
            for (var done = 0; done < amount;)
            {
                var size = Math.Min(amount - done, 4 * 1024 * 1024);
                using var request = new HttpRequestMessage(HttpMethod.Get, endpoint +
                    "?offset=" + position.ToString(System.Globalization.CultureInfo.InvariantCulture) +
                    "&size=" + size.ToString(System.Globalization.CultureInfo.InvariantCulture));
                using var response = Client.Send(request, HttpCompletionOption.ResponseHeadersRead);
                if (response.StatusCode != System.Net.HttpStatusCode.OK || response.Content.Headers.ContentLength != size)
                    throw new UnsupportedGameFormatException();
                using var input = response.Content.ReadAsStream();
                input.ReadExactly(buffer.AsSpan(offset + done, size));
                if (input.ReadByte() != -1) throw new UnsupportedGameFormatException();
                position += size;
                done += size;
            }
            return amount;
        }
        public override long Seek(long offset, SeekOrigin origin)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            var next = origin switch { SeekOrigin.Begin => offset, SeekOrigin.Current => checked(position + offset),
                SeekOrigin.End => checked(length + offset), _ => throw new ArgumentOutOfRangeException() };
            if (next < 0 || next > length) throw new ArgumentOutOfRangeException();
            return position = next;
        }
        public object Clone() => new PublisherRangeStream(endpoint, length) { Position = position };
        protected override void Dispose(bool disposing) { disposed = true; base.Dispose(disposing); }
        public override void Flush() { }
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }
    const string WuwaRoot = "Client/Content/Aki/";
    const string WuwaVoices = WuwaRoot + "WwiseAudio_Generated/WwiseExternalSource/";
    static string WuwaFilter(string filter, bool list)
    {
        if (list && filter == "WwiseExternalSource/") return WuwaVoices;
        if (filter == null || filter.Length > 512 || filter.Contains("..") ||
            !filter.All(c => char.IsAsciiLetterOrDigit(c) || c is '_' or '-' or '.' or '/')) throw new ArgumentException();
        if (filter.StartsWith(WuwaVoices, StringComparison.Ordinal))
        {
            var clip = filter[WuwaVoices.Length..];
            if (clip.Length <= 3 || clip.Contains('/') ||
                !(clip.StartsWith("en_") || clip.StartsWith("zh_") || clip.StartsWith("ja_") || clip.StartsWith("ko_"))) throw new ArgumentException();
            return filter;
        }
        if (list) throw new ArgumentException();
        if (new[] {"db_plot_audio.db", "db_flowState.db", "db_cgVedio.db", "db_infodisplay.db", "db_FloatingSubtitle.db"}
            .Any(name => filter == "ConfigDB/" + name)) return WuwaRoot + filter;
        var parts = filter.Split('/');
        if (parts.Length == 3 && parts[0] == "ConfigDB" && parts[2] == "lang_multi_text" &&
            new[] {"en", "zh-Hans", "zh-Hant", "ja", "ko", "fr", "de", "ru", "th", "vi", "id", "es", "pt"}.Contains(parts[1]))
            return WuwaRoot + filter;
        throw new ArgumentException();
    }
    static void ReadWuwa(object provider, MethodInfo save, string destination, string filter, bool list)
    {
        var selected = new SortedDictionary<string, long>(StringComparer.OrdinalIgnoreCase);
        var files = Property(provider, "Files");
        foreach (var pair in (IEnumerable)files)
        {
            var name = (string)Property(pair, "Key");
            if (!name.StartsWith(filter, StringComparison.OrdinalIgnoreCase)) continue;
            if ((filter.EndsWith(".wem", StringComparison.OrdinalIgnoreCase) || filter.EndsWith(".db", StringComparison.OrdinalIgnoreCase)) &&
                !name.Equals(filter, StringComparison.OrdinalIgnoreCase)) continue;
            // Restrict prefix selection to the same authored DB/WEM surfaces
            // used by the Python binding reader. No arbitrary asset export.
            if (name.StartsWith(WuwaVoices, StringComparison.OrdinalIgnoreCase) ? !name.EndsWith(".wem", StringComparison.OrdinalIgnoreCase)
                : !name.EndsWith(".db", StringComparison.OrdinalIgnoreCase)) continue;
            if (name.StartsWith(WuwaVoices, StringComparison.OrdinalIgnoreCase) && name[WuwaVoices.Length..].Contains('/')) throw new InvalidDataException();
            if (name.Contains('\\') || name.Contains(':') || name.Split('/').Any(p => p is "" or "." or "..")) throw new InvalidDataException();
            // Enumeration can include multiple patch versions. Resolve through
            // the provider's indexer, exactly as SaveAsset does, so size checks
            // and extraction use the same winning archive entry.
            var current = files.GetType().GetProperty("Item")!.GetValue(files, [name])!;
            selected[name] = Convert.ToInt64(Property(current, "Size"));
            if (selected.Count > (list ? 2_000_000 : 256)) throw new InvalidDataException();
        }
        long total = 0;
        if (!list)
            foreach (var (name, size) in selected)
            {
                if (size < 0 || size > (name.StartsWith(WuwaVoices, StringComparison.OrdinalIgnoreCase) ? 64L : 256L) * 1024 * 1024 ||
                    (total += size) > 1024L * 1024 * 1024) throw new InvalidDataException();
                var target = Path.GetFullPath(Path.Combine(destination, name));
                if (!target.StartsWith(destination.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException();
                for (var path = target; path != null; path = Path.GetDirectoryName(path))
                    if ((File.Exists(path) || Directory.Exists(path)) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException();
                var bytes = (byte[])save.Invoke(provider, [name])!;
                if (bytes.LongLength != size) throw new InvalidDataException();
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                File.WriteAllBytes(target, bytes);
            }
        File.WriteAllText(Path.Combine(destination, "files.json"), JsonSerializer.Serialize(selected.Keys));
    }
    static object Property(object value, string name) => value.GetType().GetProperty(name)!.GetValue(value)!;

    internal sealed class SchemaUsageComparer : StringComparer
    {
        internal bool Enabled;
        internal readonly System.Collections.Concurrent.ConcurrentDictionary<string, byte> Names = new(StringComparer.Ordinal);
        public override int Compare(string? left, string? right) => StringComparer.Ordinal.Compare(left, right);
        public override bool Equals(string? left, string? right) => StringComparer.Ordinal.Equals(left, right);
        public override int GetHashCode(string value)
        {
            if (Enabled)
            {
                if (value.Length is 0 or > 256 || Names.Count >= 100_000) throw new UnsupportedGameFormatException();
                Names.TryAdd(value, 0);
            }
            return StringComparer.Ordinal.GetHashCode(value);
        }
    }

    internal static Dictionary<string, string> FrozenSchemaCodecs(Assembly cue, object mappings, object provider,
        SchemaUsageComparer usage)
    {
        var types = (IDictionary)Property(mappings, "MappingsForGame").GetType().GetField("Types")!
            .GetValue(Property(mappings, "MappingsForGame"))!;
        if (types.Count > 100_000) throw new UnsupportedGameFormatException();
        var byteArchive = cue.GetType("CUE4Parse.UE4.Readers.FByteArchive", true)!;
        var assetArchive = cue.GetType("CUE4Parse.UE4.Assets.Readers.FAssetArchive", true)!;
        var script = cue.GetType("CUE4Parse.UE4.Assets.Objects.FScriptStruct", true)!;
        var fallback = cue.GetType("CUE4Parse.UE4.Assets.Objects.FStructFallback", true)!;
        var constructor = script.GetConstructors().Single(c => c.GetParameters().Length == 4);
        var readType = Nullable.GetUnderlyingType(constructor.GetParameters()[3].ParameterType)!
            ?? constructor.GetParameters()[3].ParameterType;
        var zero = Enum.Parse(readType, "ZERO");
        var versions = Property(provider, "Versions");
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (DictionaryEntry pair in types)
        {
            var name = (string)pair.Key;
            if (name.Length is 0 or > 256 || !Regex.IsMatch(name, @"^[A-Za-z_][A-Za-z0-9_]*$"))
                continue;
            if (usage.Names.ContainsKey(name)) continue;
            try
            {
                var bytes = Activator.CreateInstance(byteArchive, ["owned-codec-probe", Array.Empty<byte>(), versions])!;
                var archive = Activator.CreateInstance(assetArchive, [bytes, null, 0, null])!;
                var value = constructor.Invoke([archive, name, null, zero]);
                var concrete = script.GetField("StructType")!.GetValue(value)!.GetType();
                var implementation = concrete.FullName!;
                if (Convert.ToInt64(Property(archive, "Position")) == 0 && concrete.Assembly == cue &&
                    !fallback.IsAssignableFrom(concrete) && implementation.StartsWith("CUE4Parse.", StringComparison.Ordinal) &&
                    implementation.Length <= 512 && Regex.IsMatch(implementation, @"^[A-Za-z_][A-Za-z0-9_.]*$"))
                    result[name] = implementation;
            }
            catch (TargetInvocationException error) when (error.InnerException is not OutOfMemoryException)
            {
                // An unknown/ordinary fallback needs package/schema state.
                // A failed empty probe supplies no custom-codec evidence.
            }
        }
        return result;
    }

    internal static void WriteSchemaUsage(string destination, string schema, string nonce, SchemaUsageComparer usage,
        Dictionary<string, string> classes, SchemaParseLog log, Dictionary<string, string>? codecs = null)
    {
        if (log.HasFailures) throw new UnsupportedGameFormatException();
        var packet = new Dictionary<string, object> {
            ["schema"] = codecs is null ? "nte-schema-usage-v1" : "nte-schema-usage-v2",
            ["complete"] = true, ["nonce"] = nonce, ["schema_sha256"] = schema.ToLowerInvariant(),
            ["lookups"] = usage.Names.Keys.Order(StringComparer.Ordinal).ToArray(), ["classes"] = classes };
        if (codecs is not null)
        {
            packet["codecs_origin"] = "zero-without-package-v1";
            packet["codecs"] = codecs;
        }
        File.WriteAllText(Path.Combine(destination, "schema-usage.json"), JsonSerializer.Serialize(packet));
    }

    internal sealed class SchemaParseLog : IDisposable
    {
        readonly PropertyInfo loggerProperty;
        readonly object prior, current;
        int failures;
        internal bool HasFailures => System.Threading.Volatile.Read(ref failures) != 0;
        SchemaParseLog(PropertyInfo property, object before, object after) => (loggerProperty, prior, current) = (property, before, after);
        internal static SchemaParseLog Capture()
        {
            // The fixed supplier deliberately turns failed instanced-struct
            // reads into null. Authored null slots produce no such warning.
            // This scoped sink prevents a partial parse from claiming complete
            // usage evidence, without changing legacy/installed/Wuwa logging.
            var assembly = AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault(a => a.GetName().Name == "Serilog")
                ?? Assembly.Load("Serilog");
            var sinkType = assembly.GetType("Serilog.Core.ILogEventSink", true)!;
            var sink = DispatchProxy.Create(sinkType, typeof(NteSchemaLogProxy));
            var configuration = Activator.CreateInstance(assembly.GetType("Serilog.LoggerConfiguration", true)!)!;
            var writeTo = Property(configuration, "WriteTo");
            var method = writeTo.GetType().GetMethods().Single(m => m.Name == "Sink" && !m.IsGenericMethod &&
                m.GetParameters().Length == 3 && m.GetParameters()[0].ParameterType == sinkType &&
                m.GetParameters()[1].ParameterType.IsEnum);
            var parameters = method.GetParameters();
            var arguments = new object?[parameters.Length];
            arguments[0] = sink;
            for (int i = 1; i < parameters.Length; i++)
                arguments[i] = parameters[i].HasDefaultValue ? parameters[i].DefaultValue : null;
            method.Invoke(writeTo, arguments);
            var logger = configuration.GetType().GetMethod("CreateLogger", Type.EmptyTypes)!.Invoke(configuration, null)!;
            var property = assembly.GetType("Serilog.Log", true)!.GetProperty("Logger")!;
            var result = new SchemaParseLog(property, property.GetValue(null)!, logger);
            ((NteSchemaLogProxy)sink).OnEvent = value => {
                try
                {
                    var text = Property(Property(value, "MessageTemplate"), "Text").ToString()!;
                    if (text.StartsWith("Failed to read FInstancedStruct", StringComparison.Ordinal) ||
                        text.StartsWith("Failed to load FInstancedStruct", StringComparison.Ordinal))
                        System.Threading.Interlocked.Increment(ref result.failures);
                }
                catch { System.Threading.Interlocked.Increment(ref result.failures); }
            };
            property.SetValue(null, logger);
            return result;
        }
        public void Dispose()
        {
            loggerProperty.SetValue(null, prior);
            (current as IDisposable)?.Dispose();
        }
    }
    static string TextKey(object value) => (string)value.GetType().GetField("Str")!.GetValue(value)!;
    sealed record LocalizedRow(string ns, string key, string value);
    sealed class UnsupportedGameFormatException : Exception { }
}

// DispatchProxy generates a subtype in its own assembly, requiring a public,
// non-sealed proxy base. The reflected interface belongs to the fixed supplier.
public class NteSchemaLogProxy : DispatchProxy
{
    public Action<object>? OnEvent;
    protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
    {
        if (targetMethod?.Name == "Emit" && args is [object value]) OnEvent?.Invoke(value);
        return null;
    }
}
