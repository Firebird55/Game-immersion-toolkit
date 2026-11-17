// Owned logging/comparer stand-ins. No supplier or game assets are loaded.
using System.Text.Json;

internal static class UsageFixture
{
    static void Check(bool value) { if (!value) throw new Exception("Schema usage fixture failed"); }
    public static void Main(string[] args)
    {
        var root = args[0];
        var comparer = new NteReader.SchemaUsageComparer();
        var mapping = new Dictionary<string, int>(comparer) { ["Known"] = 1 };
        Check(comparer.Names.Count == 0);
        comparer.Enabled = true;
        Check(mapping.TryGetValue("Known", out _) && !mapping.TryGetValue("NewDynamic", out _));
        Check(!mapping.TryGetValue("known", out _));
        Check(comparer.Names.Keys.Order(StringComparer.Ordinal).SequenceEqual(new[] { "Known", "NewDynamic", "known" }));
        Check(comparer.Compare("A", "a") == StringComparer.Ordinal.Compare("A", "a"));
        Check(!comparer.Equals("A", "a"));
        var prior = Serilog.Log.Logger;
        var classes = new Dictionary<string, string> { ["EngineTable"] = "CUE4Parse.UE4.Assets.Exports.Engine.UEngineTable" };
        var good = Path.Combine(root, "good"); Directory.CreateDirectory(good);
        using (var capture = NteReader.SchemaParseLog.Capture())
        {
            Serilog.Log.Warning("Authored optional null slot");
            Check(!capture.HasFailures);
            NteReader.WriteSchemaUsage(good, new string('a', 64), new string('b', 32), comparer, classes, capture);
        }
        Check(ReferenceEquals(prior, Serilog.Log.Logger));
        using var report = JsonDocument.Parse(File.ReadAllText(Path.Combine(good, "schema-usage.json")));
        Check(report.RootElement.GetProperty("complete").GetBoolean());
        Check(report.RootElement.GetProperty("nonce").GetString() == new string('b', 32));
        var codecs = Path.Combine(root, "codecs"); Directory.CreateDirectory(codecs);
        var actualLookups = comparer.Names.Keys.Order(StringComparer.Ordinal).ToArray();
        using (var capture = NteReader.SchemaParseLog.Capture())
        {
            NteReader.WriteSchemaUsage(codecs, new string('a', 64), new string('d', 32), comparer, classes, capture,
                new Dictionary<string, string> { ["CustomPath"] = "CUE4Parse.UE4.Objects.UObject.FCustomPath" });
        }
        using var codecReport = JsonDocument.Parse(File.ReadAllText(Path.Combine(codecs, "schema-usage.json")));
        Check(codecReport.RootElement.GetProperty("schema").GetString() == "nte-schema-usage-v2");
        Check(codecReport.RootElement.GetProperty("codecs_origin").GetString() == "zero-without-package-v1");
        Check(codecReport.RootElement.GetProperty("lookups").EnumerateArray().Select(x => x.GetString()).SequenceEqual(actualLookups));
        foreach (var prefix in new[] { "Failed to read FInstancedStruct", "Failed to load FInstancedStruct" })
        {
            var bad = Path.Combine(root, prefix.Contains("read") ? "read" : "load"); Directory.CreateDirectory(bad);
            using (var capture = NteReader.SchemaParseLog.Capture())
            {
                Serilog.Log.Warning(prefix + " of type Owned, skipping it");
                Check(capture.HasFailures);
                bool rejected = false;
                try { NteReader.WriteSchemaUsage(bad, new string('a', 64), new string('c', 32), comparer, classes, capture); }
                catch { rejected = true; }
                Check(rejected && !File.Exists(Path.Combine(bad, "schema-usage.json")));
            }
            Check(ReferenceEquals(prior, Serilog.Log.Logger));
        }
        Console.WriteLine(JsonSerializer.Serialize(new { exact_ordinal = true, actual_missing_lookup_recorded = true,
            authored_null_allowed = true, failed_read_and_load_refuse_complete_marker = true, prior_logger_restored = true }));
    }
}

namespace Serilog.Core { public interface ILogEventSink { void Emit(Serilog.Events.LogEvent value); } }
namespace Serilog.Events
{
    public enum LogEventLevel { Verbose, Debug, Information, Warning, Error, Fatal }
    public sealed class MessageTemplate(string text) { public string Text { get; } = text; }
    public sealed class LogEvent(string text) { public MessageTemplate MessageTemplate { get; } = new(text); }
}
namespace Serilog
{
    public interface ILogger { void Warning(string text); }
    public sealed class FixtureLogger(Core.ILogEventSink? sink = null) : ILogger, IDisposable
    {
        public void Warning(string text) => sink?.Emit(new Events.LogEvent(text));
        public void Dispose() { }
    }
    public static class Log
    {
        public static ILogger Logger { get; set; } = new FixtureLogger();
        public static void Warning(string text) => Logger.Warning(text);
    }
    public sealed class LoggerConfiguration
    {
        internal Core.ILogEventSink? SinkValue;
        public Configuration.LoggerSinkConfiguration WriteTo { get; }
        public LoggerConfiguration() => WriteTo = new(this);
        public FixtureLogger CreateLogger() => new(SinkValue);
    }
}
namespace Serilog.Configuration
{
    public sealed class LoggerSinkConfiguration(Serilog.LoggerConfiguration owner)
    {
        public Serilog.LoggerConfiguration Sink(Serilog.Core.ILogEventSink sink,
            Serilog.Events.LogEventLevel minimum = Serilog.Events.LogEventLevel.Verbose, object? levelSwitch = null)
        { owner.SinkValue = sink; return owner; }
        // Match the supplier's extra overload: selection must use the exact
        // supported signature rather than a broad Single(Name == "Sink").
        public Serilog.LoggerConfiguration Sink(Serilog.Core.ILogEventSink sink) => owner;
    }
}
