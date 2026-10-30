// Authored packaging probe only. It reads no game, account or user data.
using System.Security.Cryptography;
using System.Text.Json;

internal static class ToolkitReaderProbe
{
    static int Main(string[] args)
    {
        try
        {
            if (args.Length != 1 || args[0] != "--probe") throw new ArgumentException();
            var input = new char[4097];
            var count = Console.In.ReadBlock(input, 0, input.Length);
            if (count > 4096) throw new ArgumentException();
            var text = new string(input, 0, count);
            using var request = JsonDocument.Parse(text);
            var root = request.RootElement;
            if (root.ValueKind != JsonValueKind.Object || root.EnumerateObject().Count() != 2 ||
                root.GetProperty("schema").GetString() != "proxy-reader-probe-request-v1") throw new ArgumentException();
            var nonce = root.GetProperty("nonce").GetString()!;
            if (nonce.Length is < 1 or > 80 || !nonce.All(c => char.IsAsciiLetterOrDigit(c) || c is '-' or '_')) throw new ArgumentException();
            var home = Path.GetFullPath(AppContext.BaseDirectory);
            var core = Path.GetFullPath(typeof(object).Assembly.Location);
            if (!core.StartsWith(home.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar,
                                 StringComparison.OrdinalIgnoreCase) || Environment.Version.ToString() != "10.0.14")
                throw new InvalidOperationException();
            var resource = Path.Combine(home, "probe-resource.txt");
            byte[] bytes;
            try { bytes = File.ReadAllBytes(resource); }
            catch { Console.Error.WriteLine("The authored helper resource is missing or changed."); return 3; }
            if (!bytes.SequenceEqual(System.Text.Encoding.UTF8.GetBytes("R19 authored self-contained reader probe.\n")))
            { Console.Error.WriteLine("The authored helper resource is missing or changed."); return 3; }
            Console.Write(JsonSerializer.Serialize(new { schema = "proxy-reader-probe-result-v1", nonce,
                runtime_version = Environment.Version.ToString(), runtime_origin = "app-local",
                resource_sha256 = Convert.ToHexStringLower(SHA256.HashData(bytes)) }));
            return 0;
        }
        catch
        {
            Console.Error.WriteLine("The authored helper request or app-local runtime is invalid.");
            return 2;
        }
    }
}
