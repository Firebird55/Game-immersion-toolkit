using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

[assembly: AssemblyTitle("Proxy Transcript")]
[assembly: AssemblyProduct("Proxy Transcript")]
[assembly: AssemblyDescription("Launches the Proxy Transcript game companion")]
[assembly: AssemblyCompany("Proxy Transcript")]
[assembly: AssemblyVersion("1.0.0.0")]

internal static class ProxyTranscriptLauncher
{
    [STAThread]
    private static int Main()
    {
        string launcherDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string projectPointer = Path.Combine(launcherDirectory, "project-path.txt");
        string projectRoot;

        if (File.Exists(projectPointer))
        {
            projectRoot = File.ReadAllText(projectPointer).Trim();
        }
        else
        {
            projectRoot = Directory.GetParent(launcherDirectory.TrimEnd(Path.DirectorySeparatorChar)).FullName;
        }

        string scriptPath = Path.Combine(projectRoot, "scripts", "start-companion.ps1");
        string powerShellPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Windows),
            "System32",
            "WindowsPowerShell",
            "v1.0",
            "powershell.exe"
        );

        if (!File.Exists(scriptPath))
        {
            return 2;
        }

        var startInfo = new ProcessStartInfo
        {
            FileName = powerShellPath,
            Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"" + scriptPath + "\"",
            WorkingDirectory = projectRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden
        };

        Process.Start(startInfo);
        return 0;
    }
}
