// Toolkit-owned bridge. Pinned MIT reader sources are downloaded separately
// into private tool storage; no archive keys or game data are bundled here.
using System.Text.Json;
using System.Security.Cryptography;
using AnimeStudio.Endfield;
using AnimeStudio.Endfield.Processors;

internal static class EndfieldReader
{
    static BlockType LanguageBlock(string language) => language switch
    {
        "chinese" => BlockType.AudioChinese, "english" => BlockType.AudioEnglish,
        "japanese" => BlockType.AudioJapanese, "korean" => BlockType.AudioKorean,
        _ => throw new ArgumentException("Unsupported voice locale")
    };

    static int Main(string[] args)
    {
        try
        {
            if (args is ["--runtime-identity"])
            {
                var core = typeof(object).Assembly.Location;
                var hashing = typeof(System.IO.Hashing.XxHash64).Assembly.Location;
                var local = new[] { core, hashing }.All(path => Path.GetFullPath(path).StartsWith(
                    Path.GetFullPath(AppContext.BaseDirectory), StringComparison.OrdinalIgnoreCase));
                Console.WriteLine(JsonSerializer.Serialize(new { schema = "proxy-endfield-runtime-identity-v1",
                    runtime_version = Environment.Version.ToString(), runtime_origin = local ? "app-local" : "external",
                    corelib_sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(core))).ToLowerInvariant(),
                    hashing_sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(hashing))).ToLowerInvariant(),
                    game_execution_approved = false }));
                return local ? 0 : 2;
            }
            if (args.Length != 2 || args[0] is not ("inventory" or "voice")) throw new ArgumentException();
            using var request = JsonDocument.Parse(Console.In.ReadToEnd());
            var root = request.RootElement;
            var language = root.GetProperty("language").GetString()!;
            var selected = LanguageBlock(language);
            var loader = new VfsLoader(Path.GetFullPath(args[1]), Keys.ChaCha20Key);
            var basePath = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(args[1]))!, "StreamingAssets");
            var baseLoader = new VfsLoader(basePath, Keys.ChaCha20Key);
            var rows = new List<object>();
            // Main Audio holds large music/SFX streams; narrative packs live in
            // the selected locale, initial and hotfix groups.
            var blocks = new[] { BlockType.InitialAudio, selected, BlockType.HotfixAudio };
            foreach (var block in blocks)
            {
                if (args[0] == "voice" && (int)block != root.GetProperty("block").GetInt32()) continue;
                if (!loader.TryLoadBlockInfo(block, out var info)) continue;
                foreach (var chunk in info.Chunks)
                foreach (var file in chunk.Files)
                {
                    if (!file.FileName.EndsWith(".pck", StringComparison.OrdinalIgnoreCase)) continue;
                    if (args[0] == "voice" && (chunk.FileName() != root.GetProperty("chunk").GetString() ||
                        file.FileNameHash.ToString() != root.GetProperty("file_hash").GetString())) continue;
                    if (file.Length <= 0 || file.Length > int.MaxValue - 64L) throw new InvalidDataException();
                    // Patch indexes also reference unchanged base chunks and
                    // optional language chunks that have not been downloaded.
                    var actualLoader = loader;
                    var relative = Path.Combine(BlockHashes.GetDirName(block), chunk.FileName());
                    if (!File.Exists(Path.Combine(loader.VfsPath, relative)))
                    {
                        if (!File.Exists(Path.Combine(baseLoader.VfsPath, relative))) continue;
                        actualLoader = baseLoader;
                    }
                    var package = AkpkPackage.Parse(actualLoader.ExtractFileToBytes(block, chunk, file));
                    foreach (var entry in package.Entries)
                    {
                        if (entry.Size <= 0 || entry.Size > 64L * 1024 * 1024) continue;
                        if (args[0] == "voice")
                        {
                            if ($"{entry.Id:x16}" != root.GetProperty("file_id").GetString()) continue;
                            var bytes = package.GetWemData(entry);
                            if (bytes.Length < 12 || bytes[0] != 'R' || bytes[1] != 'I' || bytes[2] != 'F' || bytes[3] != 'F')
                                throw new InvalidDataException();
                            using var output = Console.OpenStandardOutput();
                            output.Write(bytes);
                            return 0;
                        }
                        rows.Add(new { block = (int)block, chunk = chunk.FileName(),
                            file_hash = file.FileNameHash.ToString(), file_id = $"{entry.Id:x16}",
                            size = entry.Size });
                    }
                }
            }
            if (args[0] == "voice") throw new InvalidDataException("Original voice was not found");
            Console.Write(JsonSerializer.Serialize(rows));
            return 0;
        }
        catch
        {
            Console.Error.WriteLine("Endfield reader failed; check installed voice data and refresh game tools.");
            return 1;
        }
    }
}
