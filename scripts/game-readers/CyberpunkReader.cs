// Owned, deliberately small entry point for the pinned WolvenKit dependency set.
// Do not call supplier Program.Main: it discovers/copies Oodle from the user's
// registry/KnownFolder. Reading uses only the bundled Kraken implementation.
using System;
using System.CommandLine;
using System.CommandLine.Builder;
using System.CommandLine.Hosting;
using System.CommandLine.Parsing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using Microsoft.Extensions.Hosting;

internal static class ToolkitCyberpunkReader
{
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 1 && args[0] == "--version")
            {
                Console.WriteLine("toolkit-cyberpunk-reader-v1 WolvenKit 9.0.1");
                return 0;
            }
            if (!(args.Length == 8 && args[0] == "unbundle" && args[2] == "-o" && args[4] == "-r" && args[6] == "-v" && args[7] == "quiet") &&
                !(args.Length == 5 && args[0] == "cr2w" && args[1] == "-s" && args[3] == "-v" && args[4] == "quiet") &&
                !(args.Length == 1 && args[0] == "--help"))
                throw new ArgumentException("Unsupported reader operation");
            string root = AppContext.BaseDirectory;
            Assembly core = Assembly.LoadFrom(Path.Combine(root, "WolvenKit.Core.dll"));
            NativeLibrary.SetDllImportResolver(core, (name, assembly, flags) =>
                name == "kraken" ? NativeLibrary.Load(Path.Combine(root, "kraken.dll")) :
                throw new DllNotFoundException("Unapproved reader native import"));
            Type compression = core.GetType("WolvenKit.Core.Compression.CompressionSettings", true)!;
            object settings = compression.GetMethod("Get")!.Invoke(null, null)!;
            compression.GetProperty("UseOodle")!.SetValue(settings, false);
            Assembly common = Assembly.LoadFrom(Path.Combine(root, "WolvenKit.Common.dll"));
            common.GetType("WolvenKit.Common.Model.Arguments.ImportExportArgs", true)!
                .GetProperty("IsCLI")!.SetValue(null, true);
            Assembly cli = Assembly.LoadFrom(Path.Combine(root, "WolvenKit.CLI.dll"));
            var rootCommand = new RootCommand();
            foreach (string command in new[] { "UnbundleCommand", "CR2WCommand" })
                rootCommand.AddCommand((Command)Activator.CreateInstance(cli.GetType("CP77Tools.Commands." + command, true)!, true)!);
            // The pinned command handlers consume this supplier verbosity option.
            rootCommand.AddGlobalOption((Option)cli.GetType("WolvenKit.CLI.Program", true)!
                .GetProperty("VerbosityOption")!.GetValue(null)!);
            MethodInfo hostFactory = cli.GetType("WolvenKit.CLI.GenericHost", true)!.GetMethod("CreateHostBuilder")!;
            return new CommandLineBuilder(rootCommand).UseDefaults()
                .UseHost(hostArgs => (IHostBuilder)hostFactory.Invoke(null, new object[] { hostArgs })!)
                .Build().Invoke(args);
        }
        catch (Exception)
        {
            // Runtime paths/game names are private. Detailed provenance is in the
            // verified package, not exception text copied into public reports.
            Console.Error.WriteLine("The owned Cyberpunk archive reader failed.");
            return 1;
        }
    }
}
